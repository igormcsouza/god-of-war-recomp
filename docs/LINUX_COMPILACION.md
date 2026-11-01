# Linux build

The [`scripts/compilar_linux.py`](../scripts/compilar_linux.py) helper prepares PS2Recomp at the commit pinned
in `scripts/common.ps1`, applies the ordered patch list from `scripts/compilar.ps1`, and builds the recompiler
and runner.

## Dependencies

You need Python 3, Git, CMake, Ninja, a C++20 compiler, and the development libraries required by PS2Recomp
(X11, OpenGL, and FFmpeg). The Linux CI workflow installs these packages with `apt`.

## Build runtime tests without game files

Configure PS2Recomp and build its runtime test suite without an ELF:

```sh
python3 scripts/compilar_linux.py --runtime-only
```

The checkout is kept in `PS2Recomp/`, with build artifacts in `PS2Recomp/build/`. The helper does not reset an
existing checkout: it requires the pinned commit and applies missing patches. An incompatible patch stops the
build.

## Build the game runner

A local copy of the `SCUS_973.99` ELF is required; it is not distributed with this repository. Provide its path
with `GOW_ELF` or `--elf`:

```sh
GOW_ELF=/path/to/SCUS_973.99 python3 scripts/compilar_linux.py
# or
python3 scripts/compilar_linux.py --elf /path/to/SCUS_973.99 --jobs 8
```

Generated code is written to `build-linux/generado/`, and the runner is built in `PS2Recomp/build/`. Every relink of
the runner is a full link-time-optimization link of all the generated code and takes about 10-15 minutes, even for
a one-file change: never interrupt it (that deletes the binary).

### Full speed: microcode capture (once)

Without captured VU1 microcode the runner interprets the VU1 and runs at about 10 FPS. Capture it once, unattended,
from your own ISO (about 5 minutes; verified from an empty cache: 1797 microprograms), then rebuild:

```sh
python3 tools/linux/capture_microcode.py --iso "God of War (USA).iso"
python3 scripts/compilar_linux.py --elf /path/to/SCUS_973.99
```

The capture stores the VU1 microprograms and the IRX modules in `~/.cache/gow-one-recomp/{vu1cap,iopdump}`;
`compilar_linux.py` uses those folders by default (override with `GOW_VU1_MICROCODIGO` and `GOW_IOP_MODULOS`). It
generates the native VU1 and native IOP code and passes the VU1N overrides that upstream's CMake needs. These
captures come from your copy of the game: never commit them.

`--traces` enables runtime tracing, and `--work-dir` selects another
PS2Recomp checkout.
