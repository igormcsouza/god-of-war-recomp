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

Generated code is written to `build-linux/generado/`, and the runner is built in `PS2Recomp/build/`. The helper
uses runner-only `-O1` Release optimization for practical initial builds and disables interprocedural
optimization, which otherwise makes the generated runner link excessively slow. Runtime and recompiler targets
keep their normal Release optimization. `--traces` enables runtime tracing, and `--work-dir` selects another
PS2Recomp checkout.
