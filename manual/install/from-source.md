# Build from source

[`scripts/compilar_linux.py`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/scripts/compilar_linux.py)
prepares PS2Recomp at the pinned commit, applies the ordered patch list, and builds the recompiler and the runner.

## Dependencies

Python 3 (with Tk for the windows), Git, CMake, Ninja, a C++20 compiler and the X11, OpenGL and audio development
libraries. `python3 tools/linux/gow_setup.py --check` lists what is missing and the command that installs it.

## Steps

```sh
python3 scripts/compilar_linux.py --elf /path/to/SCUS_973.99           # build (slow the first time)
python3 tools/linux/capture_microcode.py --iso "God of War (USA).iso"  # once, unattended, ~5 min
python3 scripts/compilar_linux.py --elf /path/to/SCUS_973.99           # rebuild with full-speed VU1/IOP
python3 tools/linux/gow_launcher.py                                     # settings window and Play
```

The `SCUS_973.99` ELF comes from your ISO (the launcher can extract it); it is never distributed.

!!! info "Why the capture step"
    Without captured VU1 microcode the runner interprets the VU1 and runs at about **10 FPS**. The capture saves
    the game's VU1 microprograms and IRX modules from your ISO into `~/.cache/gow-one-recomp/{vu1cap,iopdump}`, so the
    second build compiles them ahead of time. Verified from an empty cache: 1178-1797 microprograms depending on the run.
    These captures come from your copy of the game: never commit them.

## Good to know

- Every relink of the runner is a full link-time-optimization link and takes **10-15 minutes**, even for a one-file
  change. **Never interrupt it**: that deletes the binary.
- Generated code goes to `build-linux/generado/`; the runner is built in `PS2Recomp/build/`.
- Useful flags: `--runtime-only` (build the runtime tests without the game), `--jobs N`, `--traces`, `--work-dir`.
- Override the capture folders with `GOW_VU1_MICROCODIGO` and `GOW_IOP_MODULOS`.
