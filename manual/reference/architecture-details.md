# Architecture

## Build pipeline

`scripts/compilar_linux.py` runs these steps:

1. **Tool check** — `git`, `cmake`, `ninja` and a C++ compiler.
2. **PS2Recomp** — clones `ran-j/PS2Recomp`, checks out the commit in [`patches/PS2RECOMP_COMMIT`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/patches/PS2RECOMP_COMMIT)
   and initializes the submodules.
3. **Patches** — applies the patches listed in [`patches/series`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/patches/series), in that order.
   [`tools/ci/parches.py`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/ci/parches.py) prints the same list for CI and checks that no
   file in `patches/` is missing from it. From the repository root, `python3 tools/ci/parches.py` shows the patches
   and their order; that is the reference for preparing a change on top of the pinned runtime.

   The base is the **Waffle565/God-Of-War-Native-Port** runtime: `ps2recomp-waffle-runtime.patch` is the
   `c5a9d02..runtime` diff. On top go small per-topic patches (adapted tests, VU0 VF0/VI0, native VU1 entry list,
   GCC portability, native VU1 leak, and our fixes for presentation, frame pacing, pad mapping and rendering).
   The script re-applies only the patches that are not yet applied, so a series that grew is continued, not restarted.
4. **Native IOP (optional)** — if `GOW_IOP_MODULOS` (default `~/.cache/gow-one-recomp/iopdump`) holds a `modules.txt`,
   `tools/iop/iopn_gen.py` precompiles the game's 8 IRX modules to C++ in `ps2xIOP/src/native/`. The folder is
   produced by running the game once with `PS2X_IOP_DUMP_MODULES=<folder>` (`tools/linux/capture_microcode.py` does it
   for you). Without it the IRX modules run in the IOP interpreter.
5. **CMake** — configures the checkout in Release mode with the options the Linux build needs (unity build and
   precompiled header for the runner, no IPO, `-march=x86-64-v2`) and, when a VU1 microcode folder exists
   (`GOW_VU1_MICROCODIGO`, default `~/.cache/gow-one-recomp/vu1cap`), the native and compiled VU1 generators
   (`tools/vu1/vu1n_gen.py`, `tools/vu1/generar_vu1.cpp`, extra entries from `tools/vu1/vu1n_heads.txt`).
6. **Recompiler** — builds the `ps2_recomp` target.
7. **C++ generation** — fills in `config/recomp.template.toml` (`@ELF@`, `@MAP@`, `@OUT@`) and runs `ps2_recomp` on
   `SCUS_973.99`.
8. **Runtime** — copies the generated code, `src/gow_overrides.cpp` and `src/*.h` to `ps2xRuntime/src/runner` and builds
   `ps2EntryRunner`.

The `PS2X_ENABLE_RUNTIME_LOGS`, `PS2X_ENABLE_AGRESSIVE_LOGS` and `PS2X_ENABLE_IOP_RPC_TRACE` traces are `OFF` by
default; `--traces` enables them for investigation. The `GOW_PERF_DIAG` profile is independent of these options.

## Recompiler configuration

`config/recomp.template.toml` contains:

- **`stubs`** — Sony library functions (`sceMpeg*`, `sceIpu*`, `sceGs*`, `sceDma*`, `sceCd*`, libc…)
  that the runtime implements natively.
- **`skip`** and instruction patches generated with `ps2xAnalyzer` and tuned by hand.

`config/funcmap.csv` (`Name,Start,End,Size`) defines the boundaries of the ELF's 6,414 functions.

## Overrides (`src/gow_overrides.cpp`)

They are registered with `PS2_REGISTER_GAME_OVERRIDE` for the `SCUS_973.99` ELF (entry `0x00100008`).

| Address | Function | Reason |
|---|---|---|
| `0x00296C48` | `sceSifInitRpc` | The recompiler discards it: it starts in the delay slot of a stray `jr ra` |
| `0x00294990` | `iWakeupThread` | Same case as the previous one |
| `0x0027AB00` | `sceCdReadDvdDualInfo` | No handler in the runtime; returns dual layer with layer 1 starting at LBN `2080544` |
| `0x0026BF28` | `snd_SendIOPCommandAndWait` (`989snd`) | Logs every command (`[gow-snd]`) and calls the original; with `GOW_SND_STUB=1` it answers 0 without going through the IOP |
| `0x00298CE8` | `sceSifLoadStartModuleBuffer` | Embedded IOP module `ck01`: it is answered like a retail console (`NO_RESIDENT_END`) |

## Runtime base (Waffle565)

The Waffle565 runtime replaces every piece of hardware the game used with native code:

| Layer | Native replacement |
|---|---|
| GS | OpenGL renderer by render targets (adjustable internal resolution, 16:9), texture/CLUT store instead of a VRAM model |
| VU1 | Microprograms precompiled to C++ (`vu1n`); the exact VU1 remains as a fallback |
| IOP | The game's 8 IRX modules precompiled (`tools/iop/iopn_gen.py`) |
| SPU2 | Native sound engine driven by the game's LIBSD calls |
| Pad / memory card | Native services, no SIO2 model |
| DMA / VIF / GIF | Packets go straight to the VU1 and the GS; the recompiler turns accesses to DMA registers, timers and GS display registers into native calls |
| Disc | Files read from your own ISO, each at its original sector |

## Continuous integration

`.github/workflows/pruebas.yml` runs on every push to `main` and on every PR, without needing the game:

- **Quick checks** (seconds):
  - `tools/ci/validar_config.py` validates `config/funcmap.csv` (order, overlaps, sizes, names) and
    `config/recomp.template.toml` (`@ELF@/@MAP@/@OUT@` markers, `name@0xADDRESS` format, addresses
    inside some function). Stubs that do not start a function and repeated addresses are warnings.
  - The launcher, the setup wizard and the AppImage entry point (`tests/test_gow_launcher.py`,
    `tests/test_gow_setup.py`, an AppDir assembled without `appimagetool` that must hold no game files).
  - The GIF packet inspector, `tests/pad2_packet_test.cpp` and `tests/pad_script_test.cpp`.
- **Patches and runtime suite**: downloads PS2Recomp at the commit in `patches/PS2RECOMP_COMMIT`, applies the patches in
  the order of `patches/series` (`tools/ci/parches.py` prints them and fails if any `patches/*.patch` is not listed or
  does not apply), checks that every stub in `recomp.template.toml` has a handler in `ps2_call_list.h`
  (`validar_config.py --runtime`), builds `ps2x_tests` and runs the suite. It also builds `src/*.cpp` against the headers
  of the already-patched runtime (declaring the `sub_*` they use), so an override that uses a runtime function that no
  patch defines fails here. `tools/ci/comprobar_pruebas.py` only fails on tests that are not in
  `tests/fallos_conocidos.txt` (empty today: the whole suite passes). CI includes `tools/ci/pruebas_gs.cmake` and
  `tools/ci/pruebas_vu1.cmake` in its temporary checkout of PS2Recomp to build and run the GS FINISH checks and the
  compiled VU1 checks (pairs, DIV, FMAC), the latter with `GOW_VU1_NATIVE_OFF=1` because the native VU1 goes first.

`.github/workflows/estado.yml` regenerates the status map (`manual/status-map/`) when its data changes, and
`.github/workflows/manual.yml` builds and publishes this manual.
