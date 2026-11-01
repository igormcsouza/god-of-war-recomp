#!/usr/bin/env python3
"""AppImage entry point: build the runtime once from your ISO, then start the launcher from the cache."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gow_launcher as launcher  # noqa: E402
import gow_setup as setup  # noqa: E402


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        import tkinter  # noqa: F401  (the window needs it)
        print(f"god-of-war-recomp {setup.version()}: python {sys.version.split()[0]}, tkinter OK, "
              f"runtime {'installed' if setup.installed_runner().is_file() else 'not built yet'}")
        missing = setup.missing_tools()
        print("build tools: " + ("OK" if not missing else "missing " + ", ".join(missing)))
        return 0
    if "--setup" in argv or not setup.installed_runner().is_file():
        rest = [a for a in argv if a != "--setup"]
        rc = setup.main(rest)
        if rc != 0 or not setup.installed_runner().is_file():
            return rc or 1
        argv = [a for a in argv if a not in ("--setup",)]
    return launcher.main([*argv, "--runner", str(setup.installed_runner())] if "--runner" not in argv else argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
