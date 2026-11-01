# Install with the AppImage

`gow-one-recomp-<version>-x86_64.AppImage` is attached to every
[release](https://github.com/igormcsouza/god-of-war-recomp/releases). It is a **builder**, not a game:

- It contains the launcher, the build and capture scripts, the patches and the generic recompiler config (about 4 MB).
- It contains **no game data and no recompiled game code**. The runner is generated from your own ISO on your own machine.

## First run

1. **Build tools.** The setup installs any missing ones for you (compiler, cmake, ninja, git and the GL/X11/ALSA
   headers) with `apt`, `dnf`, `pacman` or `zypper`; your system asks for your password. On another distro it prints
   what to install.
2. Run it:

    ```sh
    chmod +x gow-one-recomp-*.AppImage && ./gow-one-recomp-*.AppImage
    ```

3. A setup window asks for your God of War (NTSC-U, SCUS-97399) ISO and runs, once, for **roughly 30 minutes or more**
   depending on your CPU (the compile and two full links dominate):

    1. prepare the disc from the ISO (cached in `~/.cache/gow-one-recomp/`);
    2. recompile the game and build a first runner;
    3. capture the VU1 microcode and IOP modules in an unattended run (about 5 minutes; a game window opens by itself);
    4. rebuild with the native VU1 and IOP code and install the runner in
       `~/.local/share/gow-one-recomp/<version>/bin/ps2EntryRunner`.

4. Every later start opens the [launcher](../usage/launcher.md) and runs the game from that cache.

A failed step can be fixed and re-run: finished work is reused. A new release changes the runtime, so it builds its own
copy under its own version folder; delete old versions by hand.

## Options

| Option | Effect |
|---|---|
| `--setup` | run the setup again |
| `--self-test` | print versions and missing build tools |
| `python3 tools/linux/gow_setup.py --iso <file> --no-gui` | run the setup in a terminal |

## How a release is made

Pushing a `vX.Y.Z` tag (it must match the `VERSION` file) runs `.github/workflows/release.yml`: launcher tests, the
AppImage build (pinned `appimagetool`, checksum verified), a smoke test that the app starts and that no `.iso`,
`SCUS_*`, `.pak` or `.irx` file is inside, then a GitHub release with the AppImage and its `.sha256`.
