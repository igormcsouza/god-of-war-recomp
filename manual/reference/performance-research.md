# Performance

## Selecting loaded-game windows

The menu and loading screens also call `vid::Flip`; counting those calls does not prove in-game
FPS. `tools/rendimiento/resumir.py --partida` keeps only complete windows enclosed by
`[gow-pad2:state]` reports with `state=11`, `pending=0` and `levelReady=1`. It excludes windows that
touch an observed transition and fails if none remain. The pad and profile clocks start at different
moments: the selection uses the order of the log lines.

```powershell
.\scripts\probar_rendimiento.ps1 -Renderer opengl -Segundos 240 -Etiqueta partida
python tools/rendimiento/resumir.py logs/perf_partida.log --partida --desde 100 --hasta 220
```

This filter checks sampled states; you still have to check the scene, use the same
executable and avoid builds or other games running during the comparison. Without `--partida` the
previous time-based selection is kept, which is also useful for studying loading. Nine
procedural checks verify loading, transitions, both limits, different clocks, rounding, the CLI
and the rejection of invalidated passes.
The script also removes `PS2X_GS_DISCARD_DRAWS` and the GS/VU1 diagnostics during profiling,
and restores their values when it finishes.

## Counters and timings with multiple threads

`guest_flip_hz` counts entries to `vid::Flip`; `host_hz` counts host iterations
finished after `EndDrawing`, which may repeat the texture. Neither
proves unique frames displayed. The summary keeps its weighted averages
and the filter by observed state, without equating the pad and profile clocks.

The EE/VU/GS/IOP scopes are exclusive within each thread, but VU/GS can
run on different threads. The sum can exceed the window time
and is neither CPU usage nor the total cost of a single thread. The JSON label
`porcentaje_hilo_juego` is removed; `reparto_tiempo_instrumentado_pct` splits only
the recorded instrumented times, including Upload and HostWait. That split is not
used to attribute CPU load or to compare renderers on its own.

With all-zero timings, the summary returns `null` in timings/split: the `frames`
mode disables timers and the absence of positive values does not prove the absence
of waits. A missing scope is also left `null`, instead of inventing a
zero. Missing mandatory counters, non-finite/negative values, repeated
fields or overlapping/restarted windows reject the log before
export. The hundredths tolerance for rounded timings is kept.

13 procedural tests pass. Re-reading profile105 without running the game: the
same 14 windows and Flip 29.19/host 13.69 averages; the manual test in frames
mode keeps its counters and no longer produces percentages from zero timings.
The summary provides no window monitor, close cause, poses or images:
that evidence requires the logs/artifacts of the corresponding control.

## Comparing RAM and shared presentation

`probar_rendimiento.ps1` sets `PS2X_GS_DIRECT_PRESENT` on every pass and restores its
value when it finishes. The default is `-Presentacion ram`, also with OpenGL;
`-Presentacion compartida` requires `-Renderer opengl`. Requesting it is not enough:
check for `[gs-present] host mode: shared texture (opt-in)` in the log, because
the backend can fall back to RAM if creating the shared context fails.

```powershell
.\scripts\probar_rendimiento.ps1 -Renderer opengl -Presentacion ram -SoloCuadros -Segundos 240 -Etiqueta ram_1
.\scripts\probar_rendimiento.ps1 -Renderer opengl -Presentacion compartida -SoloCuadros -Segundos 240 -Etiqueta compartida_1
python tools/rendimiento/resumir.py logs/perf_ram_1.log --partida --desde 100 --hasta 220
python tools/rendimiento/resumir.py logs/perf_compartida_1.log --partida --desde 100 --hasta 220
```

The profiler also sets the concurrency options and leaves them disabled by default,
even if the parent process has them enabled. To compare the base path with VU1/GS on threads,
use the same renderer, scene and executable in both passes:

```powershell
.\scripts\probar_rendimiento.ps1 -Renderer opengl -Presentacion compartida -SoloCuadros -Segundos 150 -Etiqueta base
.\scripts\probar_rendimiento.ps1 -Renderer opengl -Presentacion compartida -SoloCuadros -Vu1Hilo -GsFrente -FinishAsync -Segundos 150 -Etiqueta hilos
python tools/rendimiento/resumir.py logs/perf_base.log --partida --desde 50 --hasta 140
python tools/rendimiento/resumir.py logs/perf_hilos.log --partida --desde 50 --hasta 140
```

`-GsFrente` requires `-Vu1Hilo`. The script restores inherited variables when it finishes and shows
the mode used at the start. Use the same executable hash in both passes.

To diagnose GPU load you can enable `-GpuProfile -HardwareLog`. The profiler uses GPU timestamps
and changes the pace of the game; this mode is for locating raster/compute and variant
compilation times, not for measuring FPS. Both diagnostics are restored to their inherited value.

Use the same executable and initial card state in all passes,
keep its SHA-256 and alternate the order when repeating. `-SoloCuadros` reduces the
cost of the profile; `guest_flip_hz` counts real entries to `vid::Flip`, while
`host_hz` counts presentations and does not represent the game's FPS. The watchdog
rejects simultaneous builds or games and keeps an invalidity mark.
The script's checks verify both modes against inherited values,
their restoration and the rejection of the shared/CPU combination.

The [October 9 comparison](presentation-performance.md) repeats four
passes with the same executable: 6.848 FPS with RAM and 6.908 shared. The
observed difference of +0.88% does not demonstrate a stable improvement against the
variation between repetitions. The report keeps conditions, intervals and limits.

## Sampling profile (`tools/perfil/muestrear.cpp`)

`GOW_PERF_DIAG` splits time by subsystem, but does not say which function consumes it. This external
profiler suspends each game thread every ~1 ms, reads its program counter and groups
the samples by function with DbgHelp. It does not modify the game.

To see names, the executable needs its PDB. In your own working folder (`GOW_WORK`), after
`scripts\2_compilar.cmd`, you can reconfigure with debug information without regenerating the C++:

```bat
cmake -S %GOW_WORK%\PS2Recomp -B %GOW_WORK%\PS2Recomp\out\build "-DCMAKE_CXX_FLAGS=/Zi /DWIN32 /D_WINDOWS /EHsc" "-DCMAKE_C_FLAGS=/Zi /DWIN32 /D_WINDOWS" "-DCMAKE_EXE_LINKER_FLAGS=/DEBUG"
cmake --build %GOW_WORK%\PS2Recomp\out\build --target ps2EntryRunner
cl /nologo /O2 /EHsc /utf-8 /std:c++20 tools\perfil\muestrear.cpp /Fe:logs\muestrear.exe /Fo:logs\muestrear.obj
logs\muestrear.exe <pid de ps2EntryRunner> 30
```

The generated C++ units must be recompiled to include the debug information (touch the
`Unity\*.cxx` files of `ps2EntryRunner`, as `2_recompilar_rapido.cmd` does). Samples
in system DLLs are attributed, when the stack can be walked, to the first frame of the executable.

The profiler prints that attribution under `marcos del ejecutable desde DLL`:
it is a second view of the samples, with the percentage relative to the total
of the same thread, and is neither additional time nor exclusive CPU. It also keeps
the program counter view. The revision fixes the duplicate
DbgHelp initialization (error 87) and the omission of those frames in the output.
`scripts\probar_perfil.cmd` runs a Windows regression without the game: a
wait in a DLL recovers the procedural caller itself. It fails with the previous
profiler and passes with both fixes.

## getenv in hot loops (2026-10-07)

With OpenGL, `GOW_SKIP_FMV=1` and `GOW_FAST_BOOT=1`, the in-game profile showed **38% of the
game thread in `ucrtbase!strchr`**. It was `getenv`, which walks the whole environment on every call:

- the IOP idle loop (`iop_emulator.cpp`, no ready threads) queried `PS2X_IOP_PC_EVERY`
  on every iteration;
- every VU1 XGKICK queried `GOW_XGKICK_IMMEDIATE`;
- some frequently called overrides (`GOW_FAST_BOOT`, `GOW_PATH_DIAG`, `GOW_ANM_DIAG`,
  `GOW_EE_PRIM_DIAG`).

`patches/ps2recomp-getenv-hot.patch` reads those variables once. To keep the tests that
change `GOW_XGKICK_IMMEDIATE` during execution, `ps2Vu1ReloadEnvironmentOptions()` re-reads
it. `src/gow_overrides.cpp` stores its values in static variables.

Measurement with `scripts\probar_rendimiento.ps1 -Renderer opengl -Segundos 240` (5 s windows in
state 11, between 220 and 235 s):

| | IOP | VU | `vid::Flip`/s |
|---|---:|---:|---:|
| Before | 2.1–2.3 s | 2.4–2.6 s | 1.6–1.8 |
| After | 0.26–0.38 s | 3.5–4.2 s | 1.8–2.6 |

The time freed from the IOP goes to VU1, which now takes more than 80% of the game thread. In the profile,
VU1 is split among `commitReadyPipelines`, `normalizeOperand`, `calculatePairReadyCycle`,
`updateFmacFlags` and the rest of the interpreter with a latency model. The native suite passes
**545/545** with the patch.

## VU1 interpreter (2026-10-07)

`tools/render/repetir_cadena_vif.cpp` accepts `GOW_REPETIR_VECES=N`: it repeats the frame's VIF1 chain
N times and measures the time. With `PS2X_GS_THREAD=1` and `PS2X_GS_DISCARD_DRAWS=1` rasterization does not
count, so it is a deterministic test bench for VIF1/VU1. With the frame from the savestate of the
start of the Aegean (`D6385328`, 1,972 VU1 launches per frame):

| Change (`patches/ps2recomp-vu1-perf.patch`) | ms per frame |
|---|---:|
| Before | 775 |
| `commitReadyPipelines` walks only the pending entries (bit mask per queue) | 594 |
| `normalizeOperand` inlined | 550 |
| `calculatePairReadyCycle` walks only the registers and components read | 503 |

The resulting image is byte-for-byte identical to the one from before the changes (same frame, CPU
renderer) and the native suite passes **545/545**. In the game the difference stays within the variation between
windows (the scene changes and other processes compete for the CPU); the test bench is the
reference measurement. Next in the VU1 profile is the FMAC flag calculation
(`updateFmacFlags`, `calculateFmacProductSticky`, `calculateFmacExactResult`) and `execUpper`.

## VU1 without write queues (branch `vu1-rapido`, 2026-10-07)

`patches/ps2recomp-vu1-direct.patch`, with the same test bench (frame `D6385328`, 30 passes):

| Change | ms per frame |
|---|---:|
| Before (main) | 503 |
| VF/VI/ACC are written on execution instead of being queued with their latency | 427 |
| `commitReadyPipelines` does nothing before the nearest expiry; no sticky bits if nobody reads the status | 396 |
| The exact FMAC operation (flags) is decoded once per instruction, not per component | 386 |
| Free entries and written VI registers derived from bit masks | 339 |
| ADD/SUB/MUL with a normal result: flags without the exact long double calculation | 333 |

**Direct writes.** The VF/VI/ACC queues do not change the program's result: whoever reads a
register stalls until it is ready (`m_vfReady`, `m_viReady`, `m_accReady`) and only the
last issued write is committed. What does change is the intermediate state seen by whoever cuts execution
by cycle budget (the latency model tests). That is why it is optional:
`VU1Interpreter::setDirectRegisterWrites(true)` enables it and `PS2Runtime` does so for VU1 except with
`GOW_VU1_COLAS=1`. VU0 keeps the queues (the EE reads its registers in macro mode). The flag,
Q, P and store queues are kept.

**Sticky bits.** If the loaded microcode has no `FSAND`/`FSEQ`/`FSOR`, the product sticky
bits (`calculateFmacProductSticky`) are not computed. It is checked again every time
the microcode changes; a later program that reads the status would see the sticky bits that were not
computed earlier (with this frame's microcode it does not happen: there are none of those instructions).

Check: the image is byte-for-byte identical with and without queues in two frames (`vif_pcsx2_inicio2`
from PCSX2 and `vif_port_480s` from the port) and in queued mode it matches the previous reference. The
suite passes **551/551** with the new test `direct register writes finish a VU1 program like the
queued model` (same result, same cycles and same memory writes).

In the game (OpenGL, 5 s windows between 220 and 235 s of the same executable): `vid::Flip` goes from
2.2–2.4 per second with `GOW_VU1_COLAS=1` to 2.4–3.2 without queues. VU1 still takes almost the whole thread;
reaching real time requires a VU1 recompiler.

## Compiled VU1 microcode: first prototype (branch `vu1-compilado`, 2026-10-08)

Data from the reference frame (`D6385328`): **1,972 VU1 launches and 3.34 million instruction
pairs** (4.40 million cycles with the stalls), 1,188 distinct addresses. The hottest loops are `0x2840–0x28E8` (~22 pairs × 26,500 iterations) and `0x2B90–0x2C10` (~19,000 iterations). At
~330 ms per frame, each pair costs ~100 ns: for 30 frames per second it would need to be ~10 times less.

Checks:

- **The timing model matters.** Without the dependency stalls (`GOW_VU1_SIN_ESPERAS`, only in the
  experiment) more than 80% of the frame's pixels change: Q, P and the flags arrive on another cycle.
  A recompiler has to preserve the same latency model.
- **Interpreter tweaks exhausted.** Normalizing operands with SSE2 and reusing them was *slower*
  (369 versus 336 ms); skipping `execUpper` on upper NOPs changed nothing (330–337 ms).

`patches/ps2recomp-vu1-compiled.patch` separates an interpreter step (`stepPair`, in
`ps2_vu1_step.inl`) and allows registering a compiled dispatcher. `tools/vu1/generar_vu1.cpp` generates
C++ from micromemories captured with `GOW_VU1_CAPTURA=<folder>` (27 distinct images in three
frames: the game loads several microprograms per frame). Each pair is compiled already decoded and the
dispatcher checks on each pair that the two micromemory words are the compiled ones; if not, it
interprets that pair. The generated code comes from game data and is not published.

Result: **byte-for-byte identical image, but slower (525 ms versus 336)**. With `stepPair`
copied into each of the 4,360 pairs, the hot code takes several MB and does not fit in the cache. The suite
passes 563/563 and, with no generated code linked, the interpreter behaves as before.

What would be needed (plan): a recompiler that, like PCSX2's microVU, computes per block the stalls
and the visibility of flags/Q/P from the pipeline state on entry, generates only the arithmetic
of each instruction (SSE, with the same normalization and round-toward-zero rules) and omits the
flags nobody reads. It is several days of work; the prototype leaves the capture, the generator,
the dispatcher and the image comparison ready.

### Recompiler stage 1 (2026-10-08)

- **VU arithmetic without `/fp:fast`.** The runtime is compiled with `/arch:AVX2 /fp:fast`, and MSVC fused
  `acc + a*b` into an FMA or not depending on the site: the compiled microcode and the interpreter gave values
  differing by 1 ulp and the state diverged after 80 launches. `#pragma float_control(precise)` in the
  VU files (and in `ps2_vu1.h`) rounds the product and the sum separately, like the PS2's FMACs
  and PCSX2. It changes ~3% of the frame's pixels by 1–8 levels (0.3% by more than 8) compared with the FMA
  version; it should be reviewed with the comparisons against PCSX2.
- **Compiled = interpreted, checked launch by launch.** `GOW_REPETIR_HUELLAS=<file>` in
  `repetir_cadena_vif` writes a fingerprint of the VU1 state (VF, VI, flags, cycles and data memory)
  after each launch; the frame's 1,972 fingerprints match between the compiled code and the
  interpreter. `GOW_VU1C_RANGO=start-end` limits the compiled code to an address range to
  narrow down a difference.
- `stepPairT<pair>` (in `ps2_vu1_compiled.inl`) resolves at compile time everything that depends on
  decoding and specializes the FMAC operations; the others call the interpreter.
- Interpreter: circular queue for the flags (committed in issue order), exact shortcut for
  `acc ± product` and cheap checks before calling `commitReadyPipelines`/`progressXgkick`.

Timings (frame `D6385328`, 30 passes): interpreter 304 ms, compiled 304 ms. Measured with cycle
counters, each pair costs ~170 cycles split among stalls (~20), upper instruction (~65),
lower (~35) and cycle bookkeeping (~50). The per-pair code is no longer the problem: the
next stage is needed, with stalls and flag/Q/P visibility computed per block in
local variables, flags nobody reads eliminated and lower instructions specialized.


### Recompiler stage 2 (2026-10-08)

- **Blocks.** The generator groups the pairs into blocks (they break at jump targets, delay slots,
  the E bit and the D/T bits). A block is entered only if its words match the micromemory, there is no pending jump
  or end and cycle budget remains; otherwise it executes pair by pair.
- **Flags nobody reads.** An FMAC whose MAC flags are overwritten by a later FMAC in the same block with
  nobody reading MAC in between (FMAND/FMEQ/FMOR) does not compute them; if the program does not use FSAND/FSEQ/FSOR/FSSET,
  it only accumulates the status sticky bits.
- **Specialized lower instructions.** LQ, SQ, ILW, ISW, IADDIU/ISUBIU, B, IBxx, IADD/ISUB/IADDI,
  IAND/IOR, MOVE, MR32, LQI, SQI, WAITQ, MTIR and MFIR are generated with the fields already resolved; the rest
  call the interpreter.

Timings (same frame): interpreter 304 ms, compiled 237 ms with blocks and dead flags, 224 ms with the
specialized lower instructions. The 1,972 fingerprints remain identical to the interpreter and the suite passes 563/563.

### Integration and persistent flags (October 8)

PR #18 includes #17 and is integrated after the current GS patches.
On review, a MADD whose product underflows and whose sum stays normal
keeps `status=0x140` with queues, but gave `0x000` with direct writes if
the microprogram contained no FSAND/FSEQ/FSOR. The absence of readers
in the current program does not guarantee that a later program will not observe those bits.

`ps2recomp-vu1-sticky-preserve.patch` keeps the calculation of the product flags
in the interpreter and in the compiled pairs; blocks that eliminate
temporary MAC/status also accumulate the product's persistent bits.
A regression executes the product and then a different reader program.
The earlier timings describe the original branch: they must be measured again with
this fix before attributing them to the integrated executable.

`tests/vu1_compiled_test.cpp` builds procedural microcode, passes it through
the real generator and compares **60 cases** with the interpreter: blocks, jump with
delay, stores, modified words, reserved instruction, zero/short budgets
and resumption. VF/VI/ACC, scalars, flags, cycles, PC and
data memory match. On Windows, 139 compiled pairs and 22 interpreted pairs are executed;
the CLI requires both paths to be used. Run `scripts\probar_vu1_compilada.cmd`
and, with Python, `tests/vu1_compiled_cli_test.py logs/vu1_compiled_test.exe`.
CI includes the generator, the thirteen procedural generated units and the
path check; it does not link or publish game microcode.

The official build adds the infrastructure and the direct writes.
The dispatcher needs to generate and link C++ from local microprograms
to speed up the game; without those units it uses the interpreter.

### Stage 2b: one block, one function (October 8)

`ps2recomp-vu1-blocks.patch` and the generator write each block as a single function with the steps
inlined, in the same file as its pairs (previously, each pair was a call into another file). The
intermediate pairs that neither jump nor end (`stepPairT<..., Plain=true>`) only advance the PC: on entering the
block there was no pending jump, E bit or end, and only the last pair can create them.

Timings with the current main chain, which already includes the persistent flags fix (frame
`D6385328`, 30 passes): interpreter 357 ms, compiled before this stage 233 ms and with it 206 ms. The
per-launch fingerprints of `vif_pcsx2_inicio2` (1,972) and `vif_port_480s` (1,986) match the
interpreter, `scripts\probar_vu1_compilada.cmd` gives 60 exact cases and the suite passes 565/565.

**Persistent product flags without `long double`.** `productStickyFlags` obtains the Z/S/U/O flags
of the exact product: if the already-rounded product is normal and far from the extremes, they are just its sign;
otherwise it is computed in `double` (the product of two `float`s fits exactly). It gives the same as
`normalizeFmacExactResult` (fingerprints identical to those from before the change). The compiled pairs
compute it in the same component, with the operands already loaded. Measured alternating the two executables
(20 passes, median): compiled 203 → 180 ms, interpreter 357 → 346 ms.

**Inline expansion.** A sampling profile of the frame showed that, inside the (large) block functions,
MSVC exhausted its inlining budget and called `normalizeOperand`,
`productSumFlagsFast`, `productStickyFlags` and `applyDest` (~12% of the time). They are now
`__forceinline` (`VU1_HOT_INLINE`), `applyDest` has a version with the mask constant in the compiled
pairs, and the generated functions carry `__declspec(safebuffers)` (without the `/GS` check of their
fixed-size local arrays). Measured alternating executables: 180 → 168 ms. Identical fingerprints.

**More cases without the interpreter.** A sampling profiler (RIP of the main thread every millisecond,
with the PDB symbols) pointed to `execUpper` (~6%) and `commitReadyPipelines` (~7%). ITOF, FTOI, ABS and CLIP
are now generated with the fields resolved (previously `execUpper` normalized 12 operands for each one), and
`commitReadyPipelines` has a path for when only flags are pending, the case of dense FMAC code
with direct writes. Measured alternating executables: 168 → 158 → 154 ms. Identical fingerprints.

In the same profile, ~15% of the main thread is the wait in `GSThreadedBackend::Drain` on the
GS thread; that is not VU1.

**XGKICK without clearing 64 KB.** `m_xgkick = {}` zeroed the packet's 64 KB buffer on every XGKICK and
on every `resetScheduler` (~2,000 times per frame). Now `XgkickPipeline::reset()` resets only the
counters: from the buffer only already-copied bytes are read (the GIFtags and the send up to `totalBytes`, which does not
exceed `copiedBytes`). The qword is copied at once when it does not wrap around the data memory, and the
committed flag entries are only invalidated (`pushFlagEntry` already initializes all fields). Measured
alternating executables: compiled 156 → 128 ms, interpreter 337 → 308 ms. Identical fingerprints and images.
This also speeds up the interpreter the game uses today.

### Compiled VU1 in the game (October 8)

`ps2recomp-vu1-runner.patch` adds the generated C++ to the game build: with the variable
`GOW_VU1_MICROCODIGO=<folder>` (micromemories captured with `GOW_VU1_CAPTURA=<folder>`), `compilar.ps1`
passes the folder to CMake, which compiles `tools/vu1/generar_vu1.cpp`, generates `programa0..12.cpp` in the build
folder and links them into `ps2EntryRunner`. Without the variable the game uses the interpreter, as before.
`GOW_VU1_SIN_COMPILAR=1` disables the compiled code at run time. The micromemories and the generated C++ are
game data: they are not published.

The game uploads different microcode almost every frame: 90 s of play gave 474 distinct micromemories,
but only ~6,000 distinct pairs (11 MB of C++). To capture them:

```powershell
$env:GOW_VU1_CAPTURA = 'D:\vu1_micro'   # local folder
.\scripts\probar_rendimiento.ps1 -Segundos 90 -Renderer opengl -Etiqueta captura
Remove-Item Env:GOW_VU1_CAPTURA
$env:GOW_VU1_MICROCODIGO = 'D:\vu1_micro'
.\scripts\2_compilar.cmd
```

With `ps2recomp-vu1-captura-nativa.patch` (2026-10-18), capture also works with the native VU1 active: with an
executable already built with micromemories, playing with `GOW_VU1_CAPTURA` adds to the folder only the missing ones, at the
game's normal speed. Before, it only saved with the exact engine (`GOW_VU1_NATIVE_OFF=1`).

Measured in the game (`probar_rendimiento.ps1 -Renderer opengl`, game frames per second, between
10 and 35 s):

| VU1 | frames/s | VU (ms per 5 s) |
|---|---|---|
| interpreter | 5.6–5.8 | ~3,450 |
| compiled, 27 micromemories from the recordings | 6.8–7.4 | ~3,050 |
| compiled, 501 micromemories (recordings + 90 s of play) | 9.6–10.0 | ~2,430 |

With the CPU renderer (`cpu-hilo`) the GS is the limit (~2.2 frames/s in both cases).

## IOP scheduler (October 8)

A sampling profile of all the game's threads (OpenGL renderer, compiled VU1) showed 41%
of the main thread in `IopKernel::beginNextReady` and `nextWakeCycle`. The EE advances the IOP ~1.5 million
times per second in steps of ~4 cycles and there are almost never ready threads, but each call walked
the 21 threads twice (a `std::map`) and a third time for the next wakeup.

`ps2recomp-iop-scheduler.patch`: `beginNextReady` makes a single pass (waking the expired Delays and
choosing the ready thread with the lowest priority and id do not depend on order) and, if none is ready, remembers the
first wakeup. Each kernel operation that can change the threads increments `m_version`; as long as it
does not change and that wakeup has not arrived, `beginNextReady` returns the same without walking and `nextWakeCycle`
uses the stored value. The result is identical by construction; the suite passes 565/565.

In the game, `iop_ms` drops from ~1,300–1,500 to ~570–650 ms per 5 s and both functions disappear from the
profile. Frames per second could not be compared properly: another build was occupying the machine.

## Asynchronous GS FINISH (optional, October 8)

With the OpenGL renderer, every write to the FINISH register does a synchronous `Flush` and `Sync` and
`glFinish`: the game thread waits for the GS thread and the GPU to finish. In the game profile that was
14% of the main thread. `GOW_GS_FINISH_ASINCRONO=1` (`ps2recomp-gs-finish-async.patch`, disabled
by default) queues FINISH on the GS thread and the EE sees the bit right away; the GS thread keeps the order
and VRAM reads from the EE still synchronize. Measured in the game alternating the variable: 12.1 →
12.7–13.1 frames/s. It remains to be decided whether it is safe to enable it always.

`tests/gs_finish_async_test.cpp` checks both modes in separate processes: a procedural backend
holds FINISH, checks when the write returns and when CSR is published, and requires a VRAM
read to wait. Draws, FINISH and the read must keep their order. With the runtime prior to
PR #22, the default check passes and the async check fails. On Windows run
`scripts\probar_finish_gs.cmd`. This check does not prove the completion moment of a real GPU:
the optional mode publishes FINISH before it completes and remains disabled by default.

## Integrated in-game profile without other compilers (October 8)

The executable of `9f0ebc4` (60 patches, GS56, compiled VU1 with 501 micromemories and IOP scheduler),
OpenGL and synchronous FINISH, is tested for 180 s with FMV skipped and a private card copy.
Compilers, linkers, Ninja/CMake and other game instances are watched every second. None are
detected during the first pass; the second does not start because another build appears.

The `--partida` selector keeps 12 complete windows between 104.79 and 164.84 s, 60.04 s in total,
enclosed by states 11 with no pending load and with the level ready. Weighted average: **7.13
`vid::Flip`/s**; host presentations: **58.45/s**. These are different counters. The exclusive elapsed
time of the game thread is split as follows:

| Subsystem | Percentage |
|---|---:|
| VU1 | 49.08% |
| GS, including its waits | 31.08% |
| EE | 13.71% |
| IOP | 6.13% |

The scene changes during the segment; this pass does not demonstrate a gain against another executable
nor sustained FPS of the full game. The next profile must separate the GS work from its
wait and repeat the same segment after each improvement.

## VIF1 unpacking (October 8)

`ps2recomp-vif1-unpack-fast.patch`: in an unmasked UNPACK, with data and without an STMOD that adds the row, each
component is the unpacked value; the qword is written at once instead of the per-component loop.
Same result: VU1 fingerprints and images of `vif_pcsx2_inicio2` and `vif_port_480s` identical, suite
565/565. Replay alternating executables: 136 → 133 ms per frame.

**EE timers.** `advanceEeTimers` is called at every checkpoint of the recompiled code
(~1.5 million times per second) and looked up GIF_STAT in the register `unordered_map` every time.
`ps2recomp-ee-timers-fast.patch` stores the element's address (the elements of an `unordered_map` do not
move; only `clear()` at initialization invalidates it). Same behavior; suite 565/565.

## VU1 FMAC with SSE (October 8)

`ps2recomp-vu1-simd.patch`: the compiled pairs compute the four components of an FMAC (ADD, SUB, MUL,
MADD, MSUB, MAX, MINI, OPMULA and OPMSUB without the w component, with their bc/q/i/A variants) with SSE: the same
operand normalization, and each product and sum rounded separately with the VU's MXCSR, so the
result is bit-for-bit the same as in `fmacLaneT`. The flags are computed in vector form when all the active
lanes are on the interpreter's fast path (result and product far from zero and from the extremes, or
result exactly zero); otherwise the instruction is redone with the scalar code. Without SSE4.1 (GCC without
`-msse4.1`) only the scalar code is compiled.

Check: identical per-launch fingerprints in both replays, GPT's 60-case test and
a new test, `tests/vu1_fmac_test.cpp`, which compiles the 252 FMAC variants (all sources, three
DEST masks, crossed) and compares them with the interpreter using random boundary values (signed zeros,
subnormals, FLT_MIN/FLT_MAX, Inf/NaN and arbitrary bit patterns): 504,000 exact cases with 1,000
trials. A deliberately injected fault (the product's Z flag) is detected on the first trial. CI
runs it with 200 trials.

Opus's measurements on his segments, alternating executables: 131 → ~100 ms per frame
in the replay; in the game with OpenGL, 11.5–12.0 → 13.2–14.4 frames/s.
These are different segments from the loaded-game profile documented above.

The integration review finds an additional case: with the PC's FTZ/DAZ
enabled, ADD/SUB can round a subnormal cancellation to zero without
the exact operation being zero. The SIMD shortcut then omitted VU1's persistent
U flag. A random trial detects it at trial 15; the targeted
regression fails before the fix with `status=1c0/c0`, even though the
register values match.

The patch requires opposite/equal operands to recognize an exact zero
of ADD/SUB and keeps the scalar path for those underflows. The test adds
2016 targeted cases with FTZ/DAZ, both signs and direct/queued writes,
and restores the process's MXCSR. Those cases and 100,800 random cases pass
with the corrected code, linked against the local runtime. The EE's
FPU is not changed and asynchronous FINISH is not enabled by default.

On Windows, after building the patched runtime, it is reproduced with
`scripts\probar_vu1_fmac.cmd`; the output goes to `logs/vu1_fmac_test.log`.

`scripts\probar_rendimiento.ps1` rejects the start of the profile if it observes a
build or another game instance and watches those processes every second
during execution. If external load appears, it closes only its own PID,
keeps the profile with the `[gow-perf:invalid]` mark, restores the environment and
exits with an error. The selector rejects the whole marked pass, even if
windows prior to the interference are requested, and does not export a summary.
The private checks that back the earlier figures in this document
also watch processes every second. It is sampled monitoring; an external
load shorter than the interval can go unnoticed.

Four PowerShell checks, without running the game, verify a prior
build, a build started during the profile, another game and the own PID
without interference. They verify the marked log, the environment restoration
and that only the own process is stopped. Two additional selector checks
verify the rejection of the profile and of the JSON export: nine in total.

With the verified integration of 64 patches (`247a9b3`, including the FTZ
fix), a private 180.55 s pass with OpenGL and synchronous FINISH keeps
twelve complete windows in state 11, with no pending load and with the level
ready: **7.58 vid::Flip/s** and **57.71 presentations/s**, over 60.04 s
(103.06–163.12 of the profile clock). The every-second monitoring observes no
builds or another game. Exclusive distribution of the game thread:

| Area | Elapsed time |
|---|---:|
| VU | 43.24% |
| GS, including waits | 38.20% |
| EE | 12.20% |
| IOP | 6.36% |

It is a single pass with a changing scene. It does not demonstrate a gain attributable
to SIMD against the previous profile nor replace Opus's measurements. The
next diagnosis must separate submission cost, GS waits and GPU.

The first timestamp diagnosis (180 s with the same executable) confirms
an attribution limitation: hardware batches were grouped under FBP=0,
flags=0 and zero primitives even though the game was being drawn. The
[GPU attribution](rendering.md) patch keeps the state
per variant and also fixes the 4096-query compute boundary.
The figures from that diagnosis are kept locally; they are not interpreted
as FPS nor are their empty groups used to choose an optimization.

With the corrected profiler on the 65-patch executable, a 240.21 s diagnosis
keeps 280 complete GPU reports enclosed by loaded-game states.
The raster queries average 39.26 ms/frame of the profiler.
The main groups observed are:

| FBP (hex) | Flags (hex) | Mean GPU timestamp per frame |
|---|---|---:|
| 0 | 4b | 30.13 ms |
| 0 | 5a | 2.15 ms |
| 0 | 12 | 2.08 ms |
| 0 | c8 | 1.81 ms |

`4b` combines IIP, texture, alpha blending and bilinear filtering. The diagnosis
includes some compute batches during shader preparation. The monitoring
observes no compilers or another game and the original card remains intact.
These figures come from synchronized queries, with additional logging
and a changing scene. They serve to choose where to investigate; they do not prove FPS nor
a performance improvement and are not compared with the previous profiler.

### DIV compiled integration (PR #23)

The `DIV` specialization of commit `754c970` keeps the component selectors,
the interpreter's normalization, signed saturation, the D/I flags and `queueQ(..., 7, ...)`.
Opus reports identical fingerprints and 98 → 96 ms in his replay alternating executables.
This figure belongs to his capture and is not extrapolated to the loaded-game profile.
The integration keeps the FTZ/DAZ fix of `247a9b3` and its 2016 targeted cases.

The previous 60-case check did not execute `DIV`. It is extended with **38,144 cases**
that compare registers bit by bit, Q, flags, cycles and memory between compiled and
interpreter: the 16 selectors, signed zeros, subnormals, limits, Inf/NaN,
random patterns, WAITQ and cuts/resumptions, with FTZ/DAZ enabled and disabled.
A private fault that changes seven to six cycles fails on the first case, with
`cycles=19/18`, even though final Q and flags match. The generator compiles both
blocks and real pairs; the CLI requires the complete DIV check to appear.
It is reproduced with `scripts\probar_vu1_compilada.cmd` on Windows or in CI.
Passing these tests confirms semantic parity in those cases; it does not measure an FPS gain.

**Compiled DIV.** DIV was the only frequent lower instruction that was still going to `execLower`
(~130,000 per frame). It is now generated with the fields resolved, as a copy of the interpreter's case. Identical
fingerprints; replay alternating executables 98 → 96 ms.

## VU1 flags committed on read (October 8)

`ps2recomp-vu1-lazy-flags.patch`: the flag queue entries (MAC, status and clip) no longer force a
call to `commitReadyPipelines` on their cycle. They are applied, in order and only those already ready on the current cycle,
when someone reads them (FSEQ/FSAND/FSOR, FMEQ/FMAND/FMOR, FCEQ/FCAND/FCOR/FCGET), when
`commitReadyPipelines` runs for another queue (Q, P, stores), when the queue fills up, at the end of each
execution and in `resetScheduler`. What a read sees is the same as with cycle-by-cycle commit.
The other status writes commute with them: Q/P touch other bits and the sum of sticky bits from the
dead flags only exists in programs without FSSET.

VU1 fingerprints (interpreter and compiled) identical to the previous ones, FMAC test (151,200 cases), procedural
60-case test and suite 565/565. Replay with the interpreter, which is what the game uses without
captured microcode: 333 → 293 ms per frame. With the compiled code the difference is small (~1%).

## In-game profile after PR #24 and direct FMAC flags (October 8)

Sampling profile of main's executable after PR #24 (compiled VU1 with 501 micromemories, OpenGL,
synchronous FINISH), without `GOW_PERF_DIAG` (its `steady_clock` cost ~10% of the thread) and only between 105 and
170 s (game loaded). Split of the game thread:

| Part | Percentage |
|---|---:|
| Waits on the GS thread (`GSThreadedBackend::Sync`), which in turn waits on the driver | ~31% |
| Compiled VU1 blocks (`vu1c_gen::b*`) | ~15% |
| Rest of VU1: queues (`commitReadyPipelines` ~6%), dispatch (`vu1c_gen::run` ~5%), flags (~3%), XGKICK (~2%) | ~20% |
| VIF1, GS on the game thread, IOP and EE | ~10% |

In `vu1c_gen::run`, 55% of its samples are in the `switch` that looks up the next block. In
`commitReadyPipelines`, a third is in the per-component merge of the pending stores.

`ps2recomp-vu1-fast-flags.patch`:

- The compiled code no longer calls `updateFmacFlags`, which walks the four lanes. On the SSE path the
  MAC comes from the sign and zero masks (`movemask`) by inverting their 4 bits. On the scalar path, DEST
  is constant and each lane is placed with fixed shifts. `pushFmacFlags` fills the queue entry the
  same way as `pushFlagEntry` + `updateFmacFlags`, including the full-queue case.
- `progressXgkick` (every cycle of an XGKICK) read `GOW_VIF_DIAG` in two local `static`s, with their initialization
  check on every call, and computed the address with a modulo. Now it is a
  file-scope variable and a mask when the size is a power of two.

VU1 fingerprints (interpreter and compiled) identical to those of PR #24 in `vif_pcsx2_inicio2` and
`vif_port_480s`; `probar_vu1_compilada.cmd`, `probar_vu1_fmac.cmd` and suite 565/565. Replay of
`vif_port_480s` without rasterizing (`PS2X_GS_THREAD=1`, `PS2X_GS_DISCARD_DRAWS=1`, 200 passes, 8 rounds
alternating executables): median 104.4 → 100.1 ms per frame.

### Chained compiled blocks (October 8)

`tools/vu1/generar_vu1.cpp`: each `case` of the `vu1c_gen::run` dispatch carries a label. When a
block ends (`r == 1`) at one of its successors known at generation time (the pair after the last and, if it
ends in a jump with its delay slot, the jump target), the words of that pair are loaded and execution
jumps to its label instead of returning to the top of the loop and going through the `switch` again. The work
is the same as with `continue`: the jump only happens if the PC matches and the label repeats the same
block and pair checks. JR/JALR still return to the `switch`.

VU1 fingerprints (compiled and interpreter) identical in `vif_pcsx2_inicio2` and `vif_port_480s`;
`probar_vu1_compilada.cmd` (60 cases, 17 chained jumps in its dispatch, and 38,144 of DIV) green.
Replay of `vif_port_480s` without rasterizing, alternating executables with a noisy machine: median
107.7 → 105.9 ms and minimum 103.0 → 99.7 ms per frame (10 rounds); in another batch of 8, minimum 101.7 → 98.4 ms.

## FMAC with a zero factor without the exact path (October 9)

A profile of the `vif_port_480s` replay (without rasterizing) showed ~3% in the exact path of the FMACs
(`productStickyFlagsExact`, `normalizeFmacExactResult` and `signbit`, with `double` and `long double`). Its most
common case is a zero factor: the game's matrices and vectors have many components at 0.

`ps2recomp-vu1-zero-factor.patch`:

- `productStickyFlags` (interpreter and compiled code): with a ±0 operand the exact product is zero with the
  sign of a XOR b, so the flags are Z and S without computing in `double`. The operands arrive normalized
  (finite and without subnormals), so there is no 0 × ∞.
- Scalar path of the compiled FMACs (`fmacLaneT`): in MUL/OPMULA and in MADD/MSUB/OPMSUB with a zero factor,
  the `float` result is already the exact one (adding ±0 is exact with the same sign rules, and ACC is zero or
  normal), so `normalizeFmacExactResult` would not change the value: the flags are Z if it is zero, and S.
- `commitReadyPipelines` marks the Q and P entries as free without zeroing all their fields
  (`queueQ`/`queueP` write them all).

Tried and discarded because it made the timing worse: writing VU1's stores component by component (in the
interpreter an XGKICK later reads the whole qword) or with a shortcut for xyzw, and calling `progressXgkick` only
on cycles with credit (more inline code in each compiled pair).

VU1 fingerprints (compiled and interpreter) identical in `vif_pcsx2_inicio2` and `vif_port_480s`;
`probar_vu1_fmac.cmd` (100,800 cases with boundary values + 2,016 FTZ/DAZ), `probar_vu1_compilada.cmd` and suite
573/573. Replay alternating executables: compiled 103.2 → 99.0 ms per frame (6 rounds of 150 passes),
interpreter 313.9 → 307.0 ms (5 rounds of 40).

### Compiled VU1 stores written immediately (October 9)

`queueStore` queues each SQ/SQI/ISW with one cycle of latency, but the same step advances that cycle and
`commitReadyPipelines` writes it right away: before the next pair reads memory, PATH1 (XGKICK reads
after committing) or the VIF does. Also, there is only one lower instruction per pair. In the compiled code,
`ps2recomp-vu1-direct-store.patch` writes the store immediately (`vu1c::storeT<DEST>`: xyzw at once, or
read-merge-write of the qword with the constant lanes), so it no longer goes through the queue nor through the
commit on every cycle. The interpreter does not change: `queueStore` is also used by paths without a
guaranteed cycle advance in the same step.

VU1 fingerprints (compiled and interpreter, which include data memory) identical in `vif_pcsx2_inicio2` and
`vif_port_480s`; `probar_vu1_compilada.cmd` (queues, budget and resumption) and `probar_vu1_fmac.cmd`
green. Replay alternating executables (6 rounds of 150 passes): median 99.9 → 93.0 ms per frame.

### Scalar path of the compiled FMACs moved out of line (October 9)

The disassembly of the hottest block of the replay (`b3C20_1`, 31 pairs) took ~74 KB: each FMAC
carried inline, besides the SSE path, the four scalar lanes with their exact paths, which are only used
when some lane leaves the fast path. This overran the 32 KB instruction cache.
`ps2recomp-vu1-cold-scalar.patch` moves that part into `fmacScalarT<Upper, DeadFlags>`, which is not inlined
(`VU1C_NOINLINE`), and forces `vu1c::reverse4` inline (MSVC left it as a call in each FMAC). The
block drops to ~6,600 instructions and `repetir_c.exe` from 55 to 36 MB.

VU1 fingerprints (compiled and interpreter) identical in `vif_pcsx2_inicio2` and `vif_port_480s`;
`probar_vu1_fmac.cmd`, `probar_vu1_compilada.cmd` and suite 573/573. Replay alternating executables
(6 rounds of 150 passes): median 92.7 → 90.8 ms per frame.

### MADD/MSUB with a zero factor on the SSE path (October 9)

With the scalar path out of line, the profile showed which FMACs used it often: MADDA.y and MADD.w (for
example `ACC + VF29 × VF0.w`) with lanes where a factor is zero, especially when the result is also
zero. The SSE check of MADD/MSUB/OPMSUB required a result with exponent 2..0xFD, so those lanes
redid the whole instruction through the scalar path. `ps2recomp-vu1-simd-zero.patch` accepts on the SSE path the
lanes with a zero factor (the same reasoning as in the scalar one: ACC ∓ 0 is exact in float and ACC is zero
or normal) and gives them Z if the result is zero, besides S. It also accepts lanes with a ±1 factor, where
the product is exact: with result exponent 2..0xFD the value does not change and the flags are the sign, and if ACC
exactly cancels the product the result is an exact zero (+0, Z). This last one adds ~1% (82.8 → 82.1 ms).

VU1 fingerprints (compiled and interpreter) identical in `vif_pcsx2_inicio2` and `vif_port_480s`;
`probar_vu1_fmac.cmd` (boundary values with ±0) and `probar_vu1_compilada.cmd` green. Replay alternating
executables (6 rounds of 150 passes): median 90.3 → 82.7 ms per frame.

### Pending PATH1 at program end, all at once (October 9)

When a VU1 program ends, `flushPipelines` advances cycle by cycle until the queues are empty, and almost always
only the XGKICK in progress remains: one `advanceOneCycle` and one `progressXgkick` per cycle, one qword every two. The
replay profile gave it as 95% of `VU1Interpreter::run` and a good part of `progressXgkick`.
`ps2recomp-vu1-xgkick-flush.patch`: if only PATH1 remains (with no Q, P, flags, stores or writes pending, which
can no longer fill up), the rest of the packet is transferred at once and the cycles it would have
taken are added: n iterations with initial credit c0 end at cycle 2n − c0. Packet errors cut the
transfer at the same iteration as before. It holds for the interpreter and the compiled code.

VU1 fingerprints (compiled and interpreter, which include the cycles) identical in `vif_pcsx2_inicio2` and
`vif_port_480s`; `probar_vu1_compilada.cmd`, `probar_vu1_fmac.cmd` and suite 573/573. Replay alternating
executables (6 rounds of 150 passes): median 82.2 → 78.2 ms per frame.

### More captured microcode: Final battle (October 9)

With a copy of a PCSX2 card and `GOW_PAD_GUION`, a Final battle save was loaded with
`GOW_VU1_CAPTURA`, without playing by hand. In 300 s, 1,801 new micromemories came out (there were 501), but no new
pair: the 5,991 pairs (address and words) were already captured. The game builds its VU1 programs from the
same pieces in other combinations, so only new blocks appear (1,294 → 1,417) and the generated C++
grows from 11.6 to 12.2 MB. With what has been captured so far, the Final battle does not go through the interpreter.

`generar_vu1` accepts a folder (all its `*.bin`, by name) and `ps2recomp-vu1-generator-dir.patch` makes
CMake pass it the `GOW_VU1_MICROCODIGO` folder instead of each file: 2,302 paths exceed the 32 K
characters of the Windows command line. With the 501 micromemories from before the generated C++ is byte-for-byte
identical.

## DMA chains and IOP timers (October 9)

With `GOW_GS_FINISH_ASINCRONO=1` and `PS2X_GS_DIRECT_PRESENT=1` the game thread stops waiting for the GPU (7.3 →
11.1–11.4 frames/s in game) and is ~90% busy. Its profile showed two fixed costs that are easy to
remove without changing behavior:

- **DMA chains.** Each send in chain mode (VIF1, VIF0, GIF) built a new `std::vector` and grew it
  copy by copy (`_Insert_counted_range` under `writeIORegister`, ~1.6%). Now the already-processed buffers return
  to a pool (`thread_local`, at most 16) and the next send reuses their capacity.
- **IOP timers.** `IopTimrman::serviceDue` runs on every IOP slice and walked all six
  timers even if nothing expired (~1.6%), as did `nextEventCycle`. Now the first scheduled event is stored
  and recomputed after any timrman import, service or reset; if the current cycle is
  earlier, `serviceDue` returns without walking.

`ps2recomp-dma-iop-timers-cache.patch`. Suite 590/590. In game, with both GS options active and
alternating executables (two valid 3 min rounds): 11.59 → 11.90 and 11.19 → 11.37 frames/s (~2%).

## VIF1 UNPACK by format and EE timers without divisions (October 9)

`ps2recomp-vif1-ee-timers-fast.patch`:

- **VIF1 UNPACK.** Without mask, without adding the row (STMOD 0/3) and with CL >= WL, each write has its
  source vector and the general loop only reads the qword, replaces the unpacked components and writes it. Now the
  same is done per format before the general loop: V4-32 is copied at once; V3 keeps W from memory, V2
  writes XYXY, V1 repeats X and V4-5 expands as before.
- **EE timers.** `advanceEeTimers` runs at every checkpoint. With BUSCLK/2, /32 and /512 (the timer
  clock exactly divides the EE's, clock = Hz / d), with R = q · clock + r it holds that
  floor((cycles · clock + R) / Hz) = (cycles + q) / d, and the new remainder is ((cycles + q) mod d) · clock + r: no
  64-bit divisions by a variable divisor. HBLANK still uses the general count. Checked against the original
  formula with 200,000 random steps per mode, including arbitrary remainders after changing mode.

VU1 fingerprints (compiled and interpreter, with the data memory that VIF1 writes) identical in
`vif_pcsx2_inicio2` and `vif_port_480s`; suite 590/590. In game, alternating executables, with asynchronous FINISH:
11.26 → 11.33 and 10.75 → 11.08 frames/s with shared presentation, and 6.91 → 7.21 without it (~2%, noisy).

## VIF1 and VU1 on their own thread (optional, October 10)

With `GOW_GS_FINISH_ASINCRONO=1` and `PS2X_GS_DIRECT_PRESENT=1` the game thread no longer waits for the GPU and VU1 becomes
~59% of it. On the PS2 (and in PCSX2 with MTVU) VU1 works in parallel with the EE; in the port the same
thread did it, one after the other. `ps2recomp-vu1-thread.patch` (`PS2X_VU1_HILO=1`, disabled by default) separates it:

- When launching the VIF1 DMA, the EE copies the data (the chain was already copied; in normal mode it is now copied from
  RAM or the scratchpad) and queues it. The DMA is still considered finished immediately, as before.
- A thread processes the queue in order: VIF1 unpacking, VU1 microprograms and their GIF packets (PATH1 via
  XGKICK and PATH2 via DIRECT), and drains the GIF arbiter after each send.
- When each send finishes it wakes the EE scheduler (`EeEventType::Dmac`, which does nothing else). Without this the
  EE, waiting for the FINISH interrupt that this thread had just produced, slept until the next vsync and the
  dedicated thread came out slower than without it.
- The EE waits for the thread to finish before touching anything of its own: VU memory (`mapVuMemory`), the
  VIF1 registers and its DMA channel, the VIF1 FIFO, the GIF from the EE (PATH3 and its native paths) and when destroying the runtime
  (the GS is destroyed before the memory).
- **Fix:** the first version never assigned the thread's owner, so those waits were never performed (and a
  diagnostic that counted them gave zero). In some games VU1 ended up executing garbage
  (`[VU1 reserved lower] pc=0xb0`, 48 to 377 times) and skipped work, which gave ~20 false fps. Now the thread
  knows which memory it belongs to, recognizes itself with a `thread_local` variable (its `id` is assigned after
  starting it) and the notice to the EE is per memory, not global.
- From that thread, the MSCAL/MSCNT callbacks do not query the EE scheduler.

In game (asynchronous FINISH and shared presentation, alternating with and without the variable):

| Scene | Without thread | With thread |
|---|---:|---:|
| Athens docks, card save, Kratos still (160–230 s, 2 rounds), fixed version | 13.3 / 13.3 | 14.9 / 15.0 |

None of the four games had VU1 errors. The earlier figures (15.3–22.8 with thread) were from the version
without waits and are not valid. The 100–140 s segment of the automatic test varies too much between runs to compare. The suite
(590/590) passes with the variable disabled; with it enabled it still hangs on a VIF1 FIFO test.

## VU1 GIF packets on another thread (optional, October 10)

With the VU1 thread, the docks frame is pinned at 4 vsyncs (15 fps): the EE waits for vsync in a loop of the
game itself and the VU1 thread is busy ~75% of the time (~50 ms per frame). Part of that time is the GS
front end (`processGIFPacket`, `vertexKick`, `buildDrawBatch`, the backend queue), which processes the PATH1/PATH2 packets.
`ps2recomp-gs-front-thread.patch` (`PS2X_GS_FRENTE=1`, only with `PS2X_VU1_HILO=1`) moves it to a third thread:

- The packets that the GIF arbiter delivers from the VU1 thread are copied consecutively into a batch ([path][size][data])
  that is published on reaching 64 KB or when the send finishes; another thread processes them in order and returns the buffer. Those of
  PATH3 (from the EE) continue as before, after waiting for both threads.
- `syncVu1Worker()` also waits for that queue, so everything that already waited for the VU1 thread also waits for the GS.
- When the queue empties the EE is woken (FINISH/SIGNAL now come from that thread).

Docks, 160–230 s, with VU1 thread (four games per row, no VU1 errors):

| Send to the GS thread | Frames/s |
|---|---:|
| Without `PS2X_GS_FRENTE` | 15.0–15.1 |
| One vector and one notice per packet | 15.7–15.8 |
| Batch published only at the end of each send | 14.5–14.6 |
| 1 KB batches | 15.8 |
| 4 KB batches | 16.2–16.3 |
| 16 KB batches | 16.6 |
| **64 KB batches (chosen)** | **16.7–16.9** |
| 256 KB batches | 16.8–17.0 |

Per packet, the VU1 thread spent ~7% allocating memory and notifying the other thread. The captures
from the boot test look correct with and without the variable (they differ by the moment of capture).

## VIF1 UNPACK with one loop per format (October 10)

The UNPACK fast path (without mask, without adding the row, CL >= WL) read the destination qword and decided the format
component by component on every vector. `ps2recomp-vif1-unpack-formats.patch` chooses the format once per UNPACK and
uses a dedicated loop for each one (V4/V3/V2/V1 of 32, 16 and 8 bits and V4-5), with the same result: V3 keeps W,
V2 writes XYXY and V1 repeats X. Suite 590/590. Docks with VU1 and GS thread, frames only, alternating
executables: 17.0 / 16.7 → 17.3 / 17.2 frames/s, no VU1 errors.

## Compiled VU1 block check without repeated memcmp (October 10)

Each entry to a compiled block compared its microcode (up to dozens of bytes) with the micromemory, and at the
same PC several variants are tried. The micromemory only changes when its generation changes, which
`compiledProgramFor` records at the start of each run. `ps2recomp-vu1-block-check-cache.patch` remembers, per block
(a 2048-entry cache indexed by the address of its words), the result of the comparison and the generation in
which it was made. Identical VU1 fingerprints (compiled and interpreter, two recordings), suite 590/590, correct captures.
Docks with VU1 and GS thread, frames only, alternating executables: 17.4 / 17.3 → 18.4 / 18.3 frames/s, no
VU1 errors.
The check is forced inline in each block (`VU1_STEP_INLINE`), because MSVC left it as a call (~4% of the
VU1 thread): 18.4 / 18.2 → 18.8 / 18.8 frames/s.

## Chained pairs in the compiled VU1 blocks (October 10)

Each pair of a compiled block repeated the entry checks: cycle budget and pipeline commit. Within a block, the previous pair has just committed the pipelines on that same cycle, and
`blockPreconditions` left 16384 cycles of margin on entry (the waits still check the budget). The
generator now marks the pairs that do not open the block (`Chained`) and `stepPairT` only looks at `m_stopRequested` in
them (`ps2recomp-vu1-chained-steps.patch` and `tools/vu1/generar_vu1.cpp`). Identical VU1 fingerprints, suite
590/590. Docks with VU1 and GS thread, frames only, alternating executables, four rounds:
19.4 / 19.9 / 19.2 / 19.4 → 19.9 / 19.9 / 19.9 / 20.0 frames/s (+2%), no VU1 errors.

## Game speed and real-time VBlank (October 10)

Tobiichi-Port (YYOzcan), which follows this repository, added a game speed meter and `GOW_VBLANK_REALTIME`,
because in its Linux version the game ran in slow motion (38–43%). `ps2recomp-game-speed.patch` brings only the
meter: on each frame (`GOW_PERF_FRAME_PC`) it adds up the game's time step (float at `0x29C64C`) and, with
`GOW_DELTA_DIAG=1`, prints `[gow-delta] ... speed=` every second (game time / real time).

On the docks, with VU1 and GS threads, four games alternating: speed 1.00 with and without `GOW_VBLANK_REALTIME`, and
19.9 / 20.0 versus 19.9 / 19.9 frames/s. Here the game already runs in real time, so real-time VBlank is not
brought in.

## P4 texture transfers by row runs

The `WriteRun`/`UploadAligned` optimization of [Waffle565/God-Of-War-Native-Port](https://github.com/Waffle565/God-Of-War-Native-Port/blob/main/docs/performance.md)
avoids computing the coordinates of each P4 texel individually. In this port the usual path already sends the image to the
OpenGL compute shader, so `ps2recomp-gs-p4-row-runs.patch` adapts the idea to that path: the host splits the
transfer into row runs and each shader group receives the origin, the length and the destination coordinate. The
shader thus avoids the per-pixel division and modulo; the other formats keep the previous indexing.

The improvement has not yet been measured in this port. The same stretch of gameplay must be compared with and without the patch and it must be confirmed
that P4 transfers keep visual parity before attributing a performance improvement to it.
