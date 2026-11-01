# Linux AppImage (builder)

`gow-one-recomp-<version>-x86_64.AppImage` is attached to every release. It is a **builder**, not a game:

- It contains the launcher, the build and capture scripts, the patches and the generic recompiler config (about 4 MB).
- It contains **no game data and no recompiled game code**. Releases never carry the runner, the extracted disc,
  the captured microcode or any generated C++: the runner is generated from your own ISO on your own machine.

## First run

1. Install the build tools (Debian/Ubuntu):
   `sudo apt install build-essential cmake ninja-build git python3-tk libgl-dev libegl-dev libx11-dev libxrandr-dev libxi-dev libxcursor-dev libxinerama-dev libasound2-dev libpulse-dev`
2. `chmod +x gow-one-recomp-*.AppImage && ./gow-one-recomp-*.AppImage`
3. A setup window asks for your God of War (NTSC-U, SCUS-97399) ISO and runs, one time and for 30-60 minutes:
   1. prepare the disc from the ISO (cached in `~/.cache/gow-one-recomp/`);
   2. recompile the game and build a first runner;
   3. capture the VU1 microcode and IOP modules in an unattended run (about 5 minutes, a game window opens by itself);
   4. rebuild with the native VU1 and IOP code and install the runner in
      `~/.local/share/gow-one-recomp/<version>/bin/ps2EntryRunner`.
4. Every later start opens the launcher (`docs/LINUX_LAUNCHER.md`) and runs the game from that cache.

A failed step can be fixed and re-run: finished work is reused. A new release changes the runtime, so it builds
its own copy under its own version folder; old versions can be deleted by hand.

Options: `--setup` runs the setup again, `--self-test` prints versions and missing build tools, and
`python3 tools/linux/gow_setup.py --iso <file> --no-gui` runs the setup in a terminal.

## How a release is made

`.github/workflows/release.yml` runs when a `vX.Y.Z` tag is pushed (the tag must match the `VERSION` file):
launcher tests, `tools/appimage/build_appimage.sh` (pinned `appimagetool` 1.9.1, checksum verified), a smoke test
that the app starts and that no `.iso`, `SCUS_*`, `.pak` or `.irx` file is inside, then a GitHub release with the
AppImage and its `.sha256`. "Run workflow" on the same file builds the AppImage as a downloadable artifact only.

To cut a release: raise `VERSION`, update `CHANGELOG.md`, merge, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
