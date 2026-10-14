#!/usr/bin/env python3
"""Prepare PS2Recomp and build God of War on Linux (requires a locally owned ELF)."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "PS2Recomp" / "build"
DEFAULT_COMMIT = "c5a9d02573410a2085a4b4b831b0b68ba3515440"


def run(args: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def pinned_commit() -> str:
    source = (ROOT / "scripts/common.ps1").read_text(encoding="utf-8-sig")
    match = re.search(r"PS2RecompCommit\s*=\s*'([0-9a-f]{40})'", source, re.I)
    if not match:
        raise RuntimeError("PS2RecompCommit was not found in scripts/common.ps1")
    return match.group(1)


def prepare_checkout(checkout: Path) -> None:
    commit = pinned_commit()
    if not (checkout / ".git").exists():
        if checkout.exists() and any(checkout.iterdir()):
            raise RuntimeError(f"Path exists and is not a Git checkout: {checkout}")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "https://github.com/ran-j/PS2Recomp.git", str(checkout)])
        run(["git", "-C", str(checkout), "fetch", "--depth", "1", "origin", commit])
        run(["git", "-C", str(checkout), "checkout", "--detach", "FETCH_HEAD"])
        run(["git", "-C", str(checkout), "submodule", "update", "--init", "--recursive"])
    actual = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if actual != commit:
        raise RuntimeError(f"PS2Recomp is at {actual}; expected {commit}. The checkout was not reset.")

    patches = subprocess.check_output([sys.executable, str(ROOT / "tools/ci/parches.py")], text=True).splitlines()
    # Later patches can change earlier context. Find the latest applied patch in reverse order and
    # continue from the next patch, which also supports a patch series that has grown.
    applied_through = -1
    for index in range(len(patches) - 1, -1, -1):
        reverse = subprocess.run(
            ["git", "-C", str(checkout), "apply", "--reverse", "--check", "--ignore-whitespace", patches[index]],
            capture_output=True, text=True)
        if reverse.returncode == 0:
            applied_through = index
            break
    if applied_through == len(patches) - 1:
        print("The patch series is already applied.")
        return
    for patch_name in patches[applied_through + 1:]:
        patch = Path(patch_name)
        check = subprocess.run(["git", "-C", str(checkout), "apply", "--check", "--ignore-whitespace", str(patch)], capture_output=True, text=True)
        if check.returncode == 0:
            run(["git", "-C", str(checkout), "apply", "--ignore-whitespace", str(patch)])
            continue
        reverse = subprocess.run(["git", "-C", str(checkout), "apply", "--reverse", "--check", "--ignore-whitespace", str(patch)], capture_output=True, text=True)
        if reverse.returncode != 0:
            raise RuntimeError(f"Could not apply or verify {patch.name}: {check.stderr.strip()}")


def ensure_runner_include(checkout: Path) -> None:
    cmake = checkout / "ps2xRuntime/CMakeLists.txt"
    text = cmake.read_text(encoding="utf-8")
    marker = "# GOW-Port include (Linux build helper)"
    if marker not in text:
        text += f"\n{marker}\ntarget_include_directories(ps2EntryRunner PRIVATE ${'{'}CMAKE_CURRENT_SOURCE_DIR{'}'}/src/runner)\n"
        cmake.write_text(text, encoding="utf-8")

    text = cmake.read_text(encoding="utf-8")
    optimization_marker = "# GOW-Port: moderate runner optimization for practical first builds"
    if optimization_marker not in text:
        text += (f"\n{optimization_marker}\n"
                 "if(CMAKE_CXX_COMPILER_ID MATCHES \"GNU|Clang\")\n"
                 "    target_compile_options(ps2EntryRunner PRIVATE $<$<CONFIG:Release>:-O1>)\n"
                 "endif()\n")
        cmake.write_text(text, encoding="utf-8")


def ensure_release_ipo_disabled(checkout: Path) -> None:
    """Disable runtime Release IPO, which otherwise makes the generated runner link impractical."""
    release = checkout / "ps2xRuntime/cmake/ReleaseMode.cmake"
    text = release.read_text(encoding="utf-8")
    marker = "# GOW-Port: IPO disabled by Linux build helper"
    line = "    set_property(TARGET ${TargetName} PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)"
    if marker not in text and line in text:
        text = text.replace(line, f"    {marker}\n    # {line.strip()}")
        release.write_text(text, encoding="utf-8")


def prefer_shared_ffmpeg(build: Path) -> None:
    """Prefer shared FFmpeg libraries when pkg-config resolves local extracted development packages."""
    ninja = build / "build.ninja"
    if not ninja.exists():
        return
    text = ninja.read_text(encoding="utf-8")
    for library in ("avcodec", "avformat", "avutil", "swresample", "swscale"):
        static = f"/lib{library}.a"
        shared = f"/lib{library}.so"
        if static in text and not (build.parent.parent / "out" / "deps" / "root" / "usr" / "lib" / "x86_64-linux-gnu" / f"lib{library}.so").exists():
            # Standard system packages may install libraries outside the workspace dependency tree.
            if not any(Path(directory, f"lib{library}.so").exists() for directory in ("/usr/lib/x86_64-linux-gnu", "/usr/lib")):
                raise RuntimeError(f"Shared FFmpeg library {library} was not found")
        text = text.replace(static, shared)
    ninja.write_text(text, encoding="utf-8")


def find_elf(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else []
    env_elf = os.environ.get("GOW_ELF")
    if env_elf:
        candidates.append(Path(env_elf))
    candidates.extend([ROOT / "game/SCUS_973.99", ROOT.parent / "GOW ISO extraida/SCUS_973.99"])
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("SCUS_973.99 was not found. Use --elf PATH or set GOW_ELF (game files are not included).")


def vu1_cmake_args() -> list[str]:
    """Optional compiled VU1: GOW_VU1_MICROCODIGO is a local folder of microprogram dumps (*.bin) captured at
    run time with GOW_VU1_CAPTURA=<folder>. The C++ is generated at build time and never committed. Without
    it the runner only has the VU1 interpreter. Same contract as scripts/compilar.ps1."""
    folder = os.environ.get("GOW_VU1_MICROCODIGO")
    if not folder:
        return []
    path = Path(folder).expanduser().resolve()
    if not any(path.glob("*.bin")):
        raise RuntimeError(f"GOW_VU1_MICROCODIGO has no *.bin files: {path}")
    return [f"-DPS2X_VU1_MICROCODE_DIR={path}", f"-DPS2X_VU1_GENERATOR_SOURCE={ROOT / 'tools/vu1/generar_vu1.cpp'}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, help="Path to the SCUS_973.99 ELF")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "PS2Recomp", help="PS2Recomp checkout (default: ./PS2Recomp)")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="Number of parallel build jobs")
    parser.add_argument("--runtime-only", action="store_true", help="Configure the runtime and build ps2x_tests without an ELF")
    parser.add_argument("--traces", action="store_true", help="Enable runtime tracing")
    opts = parser.parse_args()
    checkout = opts.work_dir.resolve()
    try:
        for tool in ("git", "cmake", "ninja", "c++"):
            if shutil.which(tool) is None:
                raise RuntimeError(f"Required tool not found: {tool}")
        prepare_checkout(checkout)
        build = checkout / "build"
        ensure_release_ipo_disabled(checkout)
        logs = "ON" if opts.traces else "OFF"
        run(["cmake", "-S", str(checkout), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
             "-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF", "-DPS2X_BUILD_STUDIO=OFF",
             "-DCMAKE_FIND_LIBRARY_SUFFIXES=.so", "-DPKG_CONFIG_USE_STATIC_LIBS=OFF", "-UFFMPEG_*",
             f"-DPS2X_ENABLE_RUNTIME_LOGS={logs}", f"-DPS2X_ENABLE_AGRESSIVE_LOGS={logs}",
             f"-DPS2X_ENABLE_IOP_RPC_TRACE={logs}", "-DPS2X_ENABLE_RUNNER_UNITY_BUILD=ON", "-DPS2X_ENABLE_RUNNER_PCH=ON",
             "-DCMAKE_C_FLAGS=-march=x86-64-v2", "-DCMAKE_CXX_FLAGS=-march=x86-64-v2"] + vu1_cmake_args())
        if opts.runtime_only:
            run(["cmake", "--build", str(build), "--target", "ps2x_tests", "--parallel", str(opts.jobs)])
            print(f"Test suite built: {build / 'ps2xTest/ps2x_tests'}")
            return 0

        elf = find_elf(opts.elf)
        ensure_runner_include(checkout)
        work = ROOT / "build-linux"
        generated = work / "generado"
        if generated.exists():
            shutil.rmtree(generated)
        work.mkdir(exist_ok=True)
        generated.mkdir(parents=True)
        run(["cmake", "--build", str(build), "--target", "ps2_recomp", "--parallel", str(opts.jobs)])
        recomp = next(build.rglob("ps2_recomp"), None)
        if recomp is None:
            raise RuntimeError("ps2_recomp executable was not found after building")
        config = (ROOT / "config/recomp.template.toml").read_text(encoding="utf-8")
        config = config.replace("@ELF@", str(elf)).replace("@MAP@", str(ROOT / "config/funcmap.csv"))
        config = config.replace("@OUT@", str(generated) + "/")
        config_path = work / "config.toml"
        config_path.write_text(config, encoding="utf-8")
        run([str(recomp), str(config_path)])
        runner = checkout / "ps2xRuntime/src/runner"
        runner.mkdir(parents=True, exist_ok=True)
        for file in runner.iterdir():
            if file.is_file():
                file.unlink()
        for file in generated.iterdir():
            if file.is_file():
                shutil.copy2(file, runner / file.name)
        shutil.copy2(ROOT / "src/gow_overrides.cpp", runner / "gow_overrides.cpp")
        for header in (ROOT / "src").glob("*.h"):
            shutil.copy2(header, runner / header.name)
        run(["cmake", "-S", str(checkout), "-B", str(build)])
        prefer_shared_ffmpeg(build)
        run(["cmake", "--build", str(build), "--target", "ps2EntryRunner", "--parallel", str(opts.jobs)])
        print(f"Runner built in {build}")
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
