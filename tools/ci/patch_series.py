#!/usr/bin/env python3
"""Print, in order, the patches in patches/series (the order they are applied on PS2Recomp).

The Linux build (scripts/build_linux.py) and CI both read the list from here, so there is a single
ordered list. Fails when a patches/*.patch is not listed in the series or a listed file is missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERIES = ROOT / "patches" / "series"


def main() -> int:
    names = [line.strip() for line in SERIES.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    errors = []
    patches = []
    for name in names:
        path = ROOT / "patches" / name
        if not path.is_file():
            errors.append(f"patches/{name} is listed in patches/series but does not exist")
        patches.append(path)
    if len(set(names)) != len(names):
        errors.append("patches/series lists a patch twice")
    for path in sorted(set((ROOT / "patches").glob("*.patch")) - set(patches)):
        errors.append(f"patches/{path.name} is not listed in patches/series")
    if not patches:
        errors.append("patches/series is empty")
    for error in errors:
        print(f"::error::{error}", file=sys.stderr)
    if errors:
        return 1
    for path in patches:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
