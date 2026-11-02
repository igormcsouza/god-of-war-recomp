#!/usr/bin/env python3
"""One-time setup: build the native runner from your own ISO and install it for the launcher.

Steps (30+ minutes depending on the CPU, mostly compiling): check the build tools (installing missing packages), prepare the disc from your ISO, build a first
runner, capture the VU1 microcode and IOP modules in an unattended run, rebuild with them, and install the runner in
~/.local/share/gow-one-recomp/<version>/bin. Nothing from the game is ever uploaded or shipped: the runner is
generated here, on your machine, from your own copy.
"""
from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gow_launcher as launcher  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ["git", "cmake", "ninja", "c++", "python3"]
# Package names per package manager: compiler, cmake, ninja, git, Tk and the window/audio headers the runtime needs.
PACKAGES = {
    "apt-get": ("apt-get install -y", "build-essential cmake ninja-build git python3-tk libgl-dev libegl-dev libx11-dev "
                "libxrandr-dev libxi-dev libxcursor-dev libxinerama-dev libasound2-dev libpulse-dev"),
    "dnf": ("dnf install -y", "gcc-c++ make cmake ninja-build git python3-tkinter mesa-libGL-devel mesa-libEGL-devel "
            "libX11-devel libXrandr-devel libXi-devel libXcursor-devel libXinerama-devel alsa-lib-devel "
            "pulseaudio-libs-devel"),
    "pacman": ("pacman -S --needed --noconfirm", "base-devel cmake ninja git tk mesa libx11 libxrandr libxi libxcursor "
               "libxinerama alsa-lib libpulse"),
    "zypper": ("zypper --non-interactive install", "gcc-c++ make cmake ninja git python3-tk Mesa-libGL-devel "
               "Mesa-libEGL-devel libX11-devel libXrandr-devel libXi-devel libXcursor-devel libXinerama-devel "
               "alsa-devel libpulse-devel"),
}
HEADERS = ["GL/gl.h", "EGL/egl.h", "X11/Xlib.h", "X11/extensions/Xrandr.h", "X11/Xcursor/Xcursor.h",
           "X11/extensions/Xinerama.h", "alsa/asoundlib.h", "pulse/pulseaudio.h"]
INCLUDE_DIRS = [Path("/usr/include"), Path("/usr/include/x86_64-linux-gnu"), Path("/usr/local/include")]


def package_manager() -> str | None:
    return next((name for name in PACKAGES if shutil.which(name)), None)


def install_command() -> list[str] | None:
    """The root command that installs everything, or None on a distro we do not know."""
    manager = package_manager()
    if manager is None:
        return None
    command, packages = PACKAGES[manager]
    gui = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    elevate = "pkexec" if gui and shutil.which("pkexec") else "sudo"
    return [elevate, *command.split(), *packages.split()]


def install_hint() -> str:
    command = install_command()
    return " ".join(["sudo", *command[1:]]) if command else "install: a C++ compiler, cmake, ninja, git, python3-tk, GL/EGL/X11/ALSA/Pulse headers"


def version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / "gow-one-recomp" / version()


def installed_runner() -> Path:
    return data_dir() / "bin" / "ps2EntryRunner"


def missing_tools() -> list[str]:
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if any(not any((d / header).exists() for d in INCLUDE_DIRS) for header in HEADERS):
        missing.append("development headers")
    return missing


def install_missing(log) -> bool:
    """Install the missing packages as root (the system asks for the password). True when nothing is missing after."""
    command = install_command()
    if command is None:
        return False
    log(f"Installing the missing build packages ({package_manager()}); you will be asked for your password:\n"
        f"  {' '.join(command)}\n")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    assert process.stdout is not None
    for line in process.stdout:
        log(line)
    process.wait()
    return not missing_tools()


def steps(iso: Path) -> list[tuple[str, list[str]]]:
    work = data_dir() / "src" / "PS2Recomp"
    out = data_dir() / "build"
    runner_path = work / "build" / "ps2xRuntime" / "ps2EntryRunner"
    elf = launcher.prepare(iso)
    build = [sys.executable, str(ROOT / "scripts/build_linux.py"), "--elf", str(elf), "--work-dir", str(work),
             "--out-dir", str(out)]
    return [
        ("Build 1/2: recompile the game and build a first runner (slow)", build),
        ("Capture VU1 microcode and IOP modules (about 5 minutes, a game window opens by itself)",
         [sys.executable, str(ROOT / "tools/linux/capture_microcode.py"), "--iso", str(iso), "--runner", str(runner_path)]),
        ("Build 2/2: rebuild with the native VU1 and IOP code (slow)", build + ["--install", str(installed_runner())]),
    ]


def run_steps(iso: Path, log) -> int:
    missing = missing_tools()
    if missing:
        log(f"Missing: {', '.join(missing)}\n")
        if not install_missing(log):
            log(f"Could not install them automatically. Run this, then start the setup again:\n  {install_hint()}\n")
            return 2
    try:
        plan = steps(iso)
    except launcher.IsoError as exc:
        log(f"ISO problem: {exc}\n")
        return 2
    data_dir().mkdir(parents=True, exist_ok=True)  # the steps run in it, and it does not exist on a fresh machine
    for number, (title, command) in enumerate(plan, 1):
        log(f"\n=== Step {number}/{len(plan)}: {title}\n")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   errors="replace", cwd=data_dir())
        assert process.stdout is not None
        for line in process.stdout:
            log(line)
        if process.wait() != 0:
            log(f"\nStep {number} failed (exit {process.returncode}). Fix the problem above and run setup again: "
                "finished work is reused.\n")
            return 1
    log(f"\nDone. Runner installed at {installed_runner()}\n")
    return 0


def gui(iso_hint: Path | None) -> int:
    import tkinter
    from tkinter import filedialog, scrolledtext, ttk

    root = tkinter.Tk()
    root.title(f"God of War (recomp) setup {version()}")
    iso = tkinter.StringVar(value=str(iso_hint or ""))
    status = tkinter.StringVar(value="The runtime is built on your machine from your own ISO (one time, 30+ min).")
    result = {"rc": 1}
    lines: queue.Queue[str] = queue.Queue()
    frame = ttk.Frame(root, padding=10)
    frame.grid(sticky="nsew")
    ttk.Label(frame, textvariable=status, wraplength=640).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="ISO").grid(row=1, column=0, sticky="w")
    ttk.Entry(frame, textvariable=iso, width=70).grid(row=1, column=1)
    ttk.Button(frame, text="Browse...", command=lambda: iso.set(filedialog.askopenfilename(
        filetypes=[("ISO image", "*.iso"), ("All files", "*")]) or iso.get())).grid(row=1, column=2)
    text = scrolledtext.ScrolledText(frame, width=100, height=26, state="disabled")
    text.grid(row=3, column=0, columnspan=3, pady=6)
    start = ttk.Button(frame, text="Build")
    start.grid(row=2, column=2, sticky="e")

    def pump() -> None:
        while not lines.empty():
            chunk = lines.get()
            text.configure(state="normal")
            text.insert("end", chunk)
            text.see("end")
            text.configure(state="disabled")
        root.after(150, pump)

    def work(path: Path) -> None:
        result["rc"] = run_steps(path, lines.put)
        lines.put("\n(close this window to continue)\n" if result["rc"] == 0 else "")

    def go() -> None:
        message = launcher.validate_iso(iso.get()) if iso.get() else "choose an ISO"
        if message:
            status.set(message)
            return
        launcher.remember_iso(Path(iso.get()))
        start.configure(state="disabled")
        status.set("Building. This takes a while; the window stays open until it finishes.")
        threading.Thread(target=work, args=(Path(iso.get()).expanduser(),), daemon=True).start()

    start.configure(command=go)
    pump()
    root.mainloop()
    return result["rc"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iso", type=Path, help="your original ISO image")
    parser.add_argument("--no-gui", action="store_true", help="run in the terminal")
    parser.add_argument("--check", action="store_true", help="only report the missing build tools")
    args, _ignored = parser.parse_known_args(argv)  # launcher options may be passed through by gow_app.py
    if args.check:
        missing = missing_tools()
        print("Build tools OK" if not missing else f"Missing: {', '.join(missing)}\n{install_hint()}")
        return 1 if missing else 0
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.no_gui or not display:
        if args.iso is None:
            print("--iso is required without a window", file=sys.stderr)
            return 2
        return run_steps(args.iso.expanduser().resolve(), lambda line: print(line, end="", flush=True))
    hint = args.iso
    if hint is None:
        try:
            hint, _ = launcher.resolve_iso(launcher.load_settings())
        except launcher.IsoError:
            hint = None
    return gui(hint)


if __name__ == "__main__":
    raise SystemExit(main())
