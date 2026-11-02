#!/usr/bin/env python3
"""Capture the VU1 microcode and IOP modules a full-speed build needs, with no one at the controller.

Runs the runner once with the built-in pad script: it enters gameplay, then warps through a few zones while
GOW_VU1_CAPTURA saves every VU1 microprogram it sees and PS2X_IOP_DUMP_MODULES saves the IRX modules. The
folders land in ~/.cache/gow-one-recomp/{vu1cap,iopdump}, which scripts/build_linux.py picks up by default.

    python3 tools/linux/capture_microcode.py --iso "God of War (USA).iso"    # about 5 minutes
    python3 scripts/build_linux.py --elf <ELF>                            # rebuild with them

The captured files come from your own copy of the game: never commit them.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gow_launcher as launcher  # noqa: E402

ZONES = "ATHN01B;ATHN04B;SEWR02;DEST00"  # ship, Athens, sewers, Gorgon/desert: the heavy VU1 users


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iso", type=Path, required=True, help="your original ISO image")
    parser.add_argument("--runner", type=Path, help="ps2EntryRunner (default: PS2Recomp/build/ps2xRuntime)")
    parser.add_argument("--seconds", type=int, default=270, help="length of the run (default 270)")
    opts = parser.parse_args()
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "gow-one-recomp"
    vu1, iop = cache / "vu1cap", cache / "iopdump"
    vu1.mkdir(parents=True, exist_ok=True)
    iop.mkdir(parents=True, exist_ok=True)
    elf = launcher.prepare(opts.iso.expanduser().resolve())
    runner = launcher._runner_path(opts.runner)
    env = dict(os.environ, GOW_ISO=str(opts.iso.expanduser().resolve()), GOW_AUDIO="0", GOW_SKIP_FMV="1",
               GOW_FAST_BOOT="1", GOW_PAD_TEST="1", GOW_PAD_TEST_NO_CAPTURE="1", GOW_PAD_SOLO_GUION="1",
               GOW_WARP=ZONES, GOW_WARP_DELAY="2", GOW_WARP_STAY="60",
               GOW_VU1_CAPTURA=str(vu1), PS2X_IOP_DUMP_MODULES=str(iop))
    print(f"Capturing for {opts.seconds}s into {cache} (a game window opens; do not touch the controller)")
    subprocess.call(["timeout", str(opts.seconds), str(runner), str(elf)], cwd=elf.parent, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    images = len(list(vu1.glob("*.bin")))
    print(f"VU1 microcode images: {images}; IOP modules: {'yes' if (iop / 'modules.txt').exists() else 'NO'}")
    if images < 500 or not (iop / "modules.txt").exists():
        print("Few images captured: re-run, or play for a while with GOW_VU1_CAPTURA set.", file=sys.stderr)
        return 1
    print("Now rebuild: python3 scripts/build_linux.py --elf", elf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
