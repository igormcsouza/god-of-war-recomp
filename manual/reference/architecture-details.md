# Architecture

## Build pipeline

`scripts/compilar.ps1` runs these steps:

1. **Tool check** — `git`, `cmake`, `ninja` (MSVC environment loaded by `2_compilar.cmd`).
2. **PS2Recomp** — clones `ran-j/PS2Recomp` into `<drive>:\gowport\PS2Recomp`, checks out commit
   `c5a9d02573410a2085a4b4b831b0b68ba3515440` and initializes submodules.
3. **Patches** — applies the full list in the order defined by [`scripts/compilar.ps1`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/scripts/compilar.ps1).
   [`tools/ci/parches.py`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/ci/parches.py) obtains that same list for CI and checks that no
   file in `patches/` is missing. From the repository root, `python tools/ci/parches.py` shows the patches
   and their order; that is the reference for preparing a change on top of the pinned runtime.

   Since 2026-10-15 the base is the **Waffle565/God-Of-War-Native-Port** runtime (`runtime` branch):
   `ps2recomp-waffle-runtime.patch` is the `c5a9d02..runtime` diff and already includes the stack
   of patches of this repository as of 2026-10-09. On top go small per-topic patches (adapted tests,
   VU0 VF0/VI0, native VU1 entry list, GCC portability, native VU1 leak).
   The previous stack is kept in `patches/anteriores/` as a reference and is not applied. See "Runtime base".

   Before reapplying the list, the script removes the files that some patch creates (`new file mode`),
   keeping a common cleanup for new patches. Every change to the patches requires the
   full build with `scripts\2_compilar.cmd`; the fast build only updates the overrides.

4. **CMake adjustments** — adds `src/runner` to the includes of `ps2EntryRunner` and disables `/GL` and `/LTCG`
   to build in parallel (with LTCG, linking ~6,400 files is infeasible).
5. **Recompiler** — builds the `ps2_recomp` target.
6. **C++ generation** — fills in `config/recomp.template.toml` (`@ELF@`, `@MAP@`, `@OUT@`) and runs
   `ps2_recomp` on `SCUS_973.99`.
7. **Native IOP (optional)** — if `GOW_IOP_MODULOS` points to a folder with `modules.txt`,
   `tools/iop/iopn_gen.py` precompiles the game's 8 IRX modules to C++ in
   `ps2xIOP/src/native/`. The folder is obtained by running the game once with
   `PS2X_IOP_DUMP_MODULES=<folder>`. Without it the IRX modules run in the IOP interpreter.
8. **Runtime** — copies the generated code and `src/gow_overrides.cpp` to `ps2xRuntime/src/runner` and builds
   `ps2EntryRunner` (unity build + PCH). With `GOW_VU1_MICROCODIGO`, CMake also generates the native VU1
   (`tools/vu1/vu1n_gen.py`, with the extra entries from `tools/vu1/vu1n_heads.txt`) and the compiled VU1.

The `PS2X_ENABLE_RUNTIME_LOGS`, `PS2X_ENABLE_AGRESSIVE_LOGS` and `PS2X_ENABLE_IOP_RPC_TRACE` traces
are set to `OFF` by default; `scripts\2_compilar.cmd -Trazas` enables them for investigation.
The `GOW_PERF_DIAG` profile is independent of these build options; it is described in
[`ESTADO.md`](research-log.md).

The CPU / threaded CPU / OpenGL selection, the GPL-3.0 provenance of the SotC fork and its limits
are described in [`RENDERIZADO.md`](rendering.md). This GS patch is kept separate from Opus's
EE/FPU/IOP fixes; it does not modify the existing FPU operands patch.

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
| GS | OpenGL renderer by render targets (2x internal resolution, 16:9), texture/CLUT store instead of a VRAM model |
| VU1 | Microprograms precompiled to C++ (`vu1n`); the exact VU1 remains as a fallback |
| IOP | The game's 8 IRX modules precompiled (`tools/iop/iopn_gen.py`) |
| SPU2 | Native sound engine driven by the game's LIBSD calls |
| Pad / memory card | Native services, no SIO2 model |
| DMA / VIF / GIF | Packets go straight to the VU1 and the GS; the recompiler turns accesses to DMA registers, timers and GS display registers into native calls |
| Disc | Files extracted next to the ELF (`tools/iso_extract.py --layout`, `.disc_layout`), each at its original sector |

Patches on top of the base, in order:

| Patch | Contents |
|---|---|
| `ps2recomp-waffle-runtime.patch` | `c5a9d02..runtime` diff (49ca62c), without the generated registry |
| `ps2recomp-waffle-tests.patch` | Removes from `ps2xTest` the tests of pieces replaced by design and adapts `SifInitRpc` to the IOP running in batches of 512 cycles |
| `ps2recomp-vu0-vf0.patch`, `ps2recomp-vu0-vi0.patch` | VU0 VF0 and VI0 as constants (#79) |
| `ps2recomp-vu1n-heads.patch` | `-DPS2X_VU1N_HEADS_FILE` to pass `tools/vu1/vu1n_heads.txt` |
| `ps2recomp-waffle-gcc.patch` | Include path for `ee_ref/` and `VUflags`/`VUops` functions without `inline` for GCC |
| `ps2recomp-vu1n-leak.patch` | Native VU1 `NativeState` in a `std::shared_ptr` (it leaked with every `VU1Interpreter`) |

## Continuous integration

`.github/workflows/pruebas.yml` runs on every push to `main` and on every PR, without needing the game:

- **Quick checks** (seconds):
  - `tools/ci/validar_config.py` validates `config/funcmap.csv` (order, overlaps, sizes, names) and
    `config/recomp.template.toml` (`@ELF@/@MAP@/@OUT@` markers, `name@0xADDRESS` format, addresses
    inside some function). Stubs that do not start a function and repeated addresses are warnings.
  - `tools/ci/analizar_ps1.ps1` syntactically parses all the `.ps1` files with the PowerShell parser.
  - Builds and runs `tests/pad2_packet_test.cpp` with GCC.
- **Patches and runtime suite**: downloads PS2Recomp at the commit from `scripts/common.ps1`, applies the
  patches in the order of `compilar.ps1` (`tools/ci/parches.py` reads them from there and fails if any
  `patches/*.patch` does not apply), checks that every stub in `recomp.template.toml` has a handler in
  `ps2_call_list.h` (`validar_config.py --runtime`), builds `ps2x_tests` on Linux and runs the suite. It also builds
  `src/*.cpp` against the headers of the already-patched runtime (declaring the `sub_*` they use), so an override
  that uses a runtime function that no patch defines fails here and not only on Windows.
  `tools/ci/comprobar_pruebas.py` only fails on tests that are not in `tests/fallos_conocidos.txt`
  (empty today: the whole suite passes). When a test on the list passes, CI warns so it can be removed.
  CI includes `tools/ci/pruebas_gs.cmake` and `tools/ci/pruebas_vu1.cmake` in its temporary checkout of
  PS2Recomp to build and run the GS FINISH checks and the compiled VU1 checks (pairs, DIV, FMAC),
  the latter with `GOW_VU1_NATIVE_OFF=1` because the native VU1 goes first. The GS replay and feedback
  tools and the PCSX2 GS module client were removed with the migration: they used the CPU rasterizer and the
  external GS observer, which the Waffle565 runtime does not have.

`.github/workflows/estado.yml` regenerates the status map (`docs/estado/`) when its data changes.

PRs #17/#18 add optional direct writes and a compiled VU1 dispatcher, in separate patches after the GS ones.
#12 is integrated
keeping the equivalent current fixes and adapting only the
budget diagnostic to the new `StepContext`. The microcode and the generated
VU1 C++ remain private data, outside the repository.
