# Vulkan GS backend

Patch: `patches/ps2recomp-gs-vulkan.patch` (applied last). Code: `GSVulkanBackend`
(`ps2xRuntime/include/runtime/gs/gs_vulkan_backend.h`, `src/lib/gs/gpu/gs_vulkan_backend.cpp`).

## Decisions

- **VRAM model.** The GS has one 4 MiB swizzled local memory, and every format (frame, Z, textures,
  CLUT) is a view of it. The Vulkan backend keeps that model and doesn't map GS targets to `VkImage`s: VRAM is
  one 4 MiB storage buffer. Shaders address it with the OpenGL backend's GLSL helpers
  (`GSGpuShaders::kCommon`: `locate`/`readPixel`/`writePixelRaw` plus the same swizzle page tables).
  Both GPU backends therefore share one swizzle implementation, and copies, aliasing and feedback
  between formats work as on the GS.
- **Rasterization.** Each primitive is one compute dispatch over its scissored bounding box. Its state is
  one 232-byte record in a host-visible ring (16384 records per GPU run, binding 3), and a push constant
  holds the record index. Coverage
  uses the integer edge functions of `gs_triangle_rules.h` (64-bit, `shaderInt64`). Sprites use
  `gsSpriteAxis`. Gouraud weights are the correctly rounded `e/area`, and the colour sums are `precise`.
  The result is bit-exact against `GSCpuBackend`. A barrier between dispatches keeps GS draw order.
- **Texturing (phase B).** The kernel ports `SampleTexture`/`LookupCLUT`/`combineTexture` of the CPU
  backend: all PSMs (CT32/24/16/16S, Z aliases, T8/T8H/T4/T4HL/T4HH), CLUT CT32/24/16/16S with CSM1/CSM2
  and CSA, TEXA, REPEAT/CLAMP/REGION_CLAMP/REGION_REPEAT, TCC/TFX, nearest and bilinear (16.16 then 4-bit
  weights), FST UV and STQ. Per-vertex sprite texel coordinates are computed on the host with the CPU's
  own expressions. All shader float math is `precise` (the CPU build is `-march=x86-64-v2`, no FMA), and
  `1/Q` uses an exact integer division because GLSL division is not correctly rounded (2.5 ULP).
- **CLUT.** Binding 2 holds `GSCpuBackend::m_clut` (the backend is a friend), copied when a GPU run opens.
  A `LoadClut` that loads ends the run first, so the CLUT is constant within a run. A `LoadClut` that loads
  nothing (CLD=0/6/7, or CLD=4/5 with an unchanged CBP) and `TextureFlush` (only drops the CPU page cache)
  no longer end the run.
- **Pixel pipeline.** Alpha test with all AFAIL modes, alpha blending (PABE, COLCLAMP wrap/clamp, CT24
  destination alpha 0x80), Z test (NEVER/ALWAYS/GEQUAL/GREATER) and Z write on Z32/24/16/16S, FBMSK, FBA,
  in `WritePixel` order (frame, then Z). Interpolated Z uses 2^-34 fixed point instead of the CPU's double
  math (Intel Xe has no `shaderFloat64`): integer Z in [0, 2^32) and deltas below 2^28 are accepted, and the
  result can only differ from the CPU when the exact Z lies within the CPU's own double error (~2^-21) of a
  .5 boundary. Primitives that read texture pages they also write (frame or Z, same page test as
  `gowTextureAliasesTargets`) stay on the CPU because one dispatch would race.
  The OpenGL backend also rasterizes in compute (`kRaster`). A graphics pipeline would not give GS
  coverage rules or read-modify-write blending without extra work, so it is left for later as an
  optimization.
- **Authority.** Host VRAM, the pointer passed to `Initialize`, stays authoritative. The backend wraps a
  `GSCpuBackend`. A supported primitive opens a "GPU run": host VRAM is copied to the buffer and
  dispatches are recorded. Any other call (transfer, CLUT, `ReadVram`, `SnapshotVram`,
  `ConsumeLocalToHostBytes`, `Present`, `Flush`, `Sync`, state export, or an unsupported primitive)
  first submits the run, waits on its fence, copies the buffer back, and then calls the CPU backend.
  Correctness never depends on the GPU covering a feature. Cost: two 4 MiB copies per run.
- **Presentation.** The final image takes the existing path: `Present` runs the CPU compositor on host
  VRAM, and raylib uploads the `PresentationFrame` as today. This has the lowest risk because it needs
  no Vulkan swapchain on the GLFW/OpenGL window, no second window, and no changes to the screenshots
  (`GOW_SCREENSHOT_AT`) or the window title FPS. A Vulkan swapchain or a GPU compositor is worth it only
  after rendering moves to the GPU and the readback shows up in profiles.
- **Shaders.** `gs_vulkan_shader_export` (a build-time tool) writes `kCommon` plus the kernel to a
  `.comp` file. `glslangValidator -V` compiles that file to a SPIR-V header that is embedded in the
  runtime. There is no runtime dependency on glslang.
- **Device.** One process-wide `VkInstance`/`VkDevice`. The default device prefers discrete, then
  integrated, then CPU (llvmpipe). `PS2X_VK_DEVICE=<index or name substring>` forces a device (see
  "Device selection" below). Each backend owns its VRAM
  buffer, command buffer and fence.

## Selection and build

- `PS2X_GS_BACKEND=vulkan|cpu`. When unset, the Linux runner (`main.cpp`) selects Vulkan, and other
  programs, including `ps2x_tests`, keep the CPU. If Vulkan fails, the log shows
  `[gow-gs] Vulkan unavailable: ...` and `[gow-gs] Vulkan GS backend not available; using CPU.`
  `PS2X_GS_THREAD=1` wraps Vulkan in the GS thread the same way it wraps the CPU backend.
  `PS2X_GS_GPU=1` still selects OpenGL (Windows).
- CMake: the option `PS2X_GS_VULKAN` is ON by default on Linux. It needs `find_package(Vulkan)` and
  `glslangValidator`. Without them, a status message is printed and the backend is not compiled.

## Statistics

`PS2X_GS_VULKAN_STATS=1` logs once per second
`[gow-gs-vk] gpu=<n> cpu=<n>: <fallback reason>=<n>... | runs=<n> ended by: <cause>=<n>...`: primitives drawn
on the GPU and on the CPU (with the reason from `gpuUnsupported`, e.g. `tex-feedback`, `line/point`, `fog`,
`depth`/`z-range`, `dest-alpha-test`, `frame-psm`), and what ended each GPU run (the fallback reason, or the
CPU call such as `BeginTransfer(command)`, `LoadClut`, `Flush()`, `Present(request)`, `record-ring`).

## Validation

`GSCpuBackend` is the reference. `ps2x_tests` → "GS Vulkan backend" renders the same scene with both
backends from the same noisy VRAM and requires identical bytes. "Textured Vulkan VRAM equals CPU VRAM"
covers every texture PSM, CLUT loads (CSM1/CSM2, CSA, CLD=0 between GPU draws), wrap modes, TFX/TCC,
bilinear, perspective STQ, alpha test and blending over textures. The scene has a flat sprite with
fractional edges, a Gouraud triangle, a flat strip with XYOFFSET and scissor, FBMSK+FBA, a blended
sprite (CPU fallback in the middle of a GPU run, overlapped later), and CT16 and CT24 targets. It skips
when no device exists. It passes on Intel RPL-P (Mesa), NVIDIA RTX 5050 and llvmpipe. Running the whole
suite with `PS2X_GS_BACKEND=vulkan` and a finish after each primitive (a temporary local change) also
passes 628/628. Without that change, three frontend tests fail: they read the host `vram` array
directly, without `Flush`, which is why the library default stays CPU.

## Phases

- **A (done):** device/scaffold, untextured sprites and triangles (flat/Gouraud) on CT32/24/16/16S with
  FBMSK/FBA, and CPU fallback for everything else.
- **B (done):** textured sprites and triangles, CLUT on the GPU, plus alpha test, blending and Z (pulled
  forward from C because the stats showed almost every draw needs them).
- **C (partly done, see below):** destination alpha test, fog, lines and points; transfers (`BeginTransfer`/`UploadImage`) and
  CLUT loads on the GPU so runs are not split. Adopt the batching and tile binning
  of the OpenGL backend (`kRaster`) instead of one dispatch per primitive. Track dirty pages instead of
  whole-VRAM copies, and add a GPU compositor/swizzle readback for `Present`. Validate each step
  against the CPU, both with the test scene and with in-game screenshots.

## Phase C: batching, zero-copy VRAM, exact feedback (2026-10-14)

- **Zero-copy VRAM.** With `VK_EXT_external_memory_host` and a page-aligned host VRAM array, the backend imports the
  array as the GPU buffer: a GPU run no longer copies 4 MiB each way, and the CPU and the GPU see the same
  memory (host-coherent type required, else the copy path). The runtime allocates its VRAM 4096-aligned
  (`ps2_memory.cpp`, in this patch). `PS2X_VK_NO_IMPORT=1` forces the copy path; the test covers both.
- **Batches.** Consecutive primitives with the same frame/Z targets form one dispatch over their union rectangle. Each
  thread owns one pixel and applies the batch's primitives in order, so overlapping draws keep GS order without
  barriers. A batch ends (barrier before the next) when a primitive's texture pages overlap pages a batch-mate writes,
  the reverse, or its frame pages overlap a batch-mate's Z pages (or the reverse). Limit: 1024 primitives and
  `count * unionPixels <= 64 * sumPixels + 1M`, so threads don't walk long lists for tiny rectangles.
- **Exact feedback.** `tex-feedback` is now a page-level overlap between the texture rectangle and the primitive's own
  written pages (bounding box, not the whole scissor). `z-alias` (new) is a primitive whose frame pages overlap its own
  Z pages, which needs the CPU's row order.
- **Async submission.** A run is submitted every 512 primitives without waiting (up to 32 command buffers); the
  CPU waits only when it needs VRAM (`Finish`). The next dispatch's barrier orders it after the submitted work.
- Stats line now adds `batches`, `finish_ms` (time waiting for the GPU), `record_ms` and `cpudraw_ms`.

Still open: CLUT versions per primitive and non-conflicting transfers (so `LoadClut`/`BeginTransfer`, ~100-160 run
ends per second, don't wait for the GPU), page-level CPU/GPU overlap checks, fog, lines/points, destination alpha
test, a GPU compositor for `Present`.

## GPU timing and tile culling (2026-10-14)

- **GPU timestamps** (`PS2X_GS_VULKAN_STATS=1` only; zero overhead otherwise, no query pool is created). A `VkQueryPool` holds
  a begin/end pair per command buffer plus a pair around each dispatch (barrier + dispatch, so intervals tile the busy time).
  `timestampValidBits` (36 on Intel RPL-P) and `timestampPeriod` (52.08 ns) are read from the queue family/device limits. Two
  extra lines per second: `[gow-gs-vk-gpu] gpu_busy_ms dispatches avg_dispatch_ms prims/dispatch union_Mpx covered_Mpx
  walk_Mpx avg_union`, and a histogram by union/covered ratio (<=2x, <=8x, <=32x, more) with GPU ms per bucket. Run ends
  now print their CPU wait: `LoadClut=144(350ms)`.
- **Tile culling.** Each 8x8 workgroup tests the batch's rectangles against its tile cooperatively (shared bitmask, up to 1024
  prims) and each thread walks only the hits, in order. Output is byte-identical (ps2x_tests 630/630).

## Device selection (2026-10-14)

The runtime logs every Vulkan device (`[gow-gs] Vulkan device N: name (type T)`) and the chosen one
(`[gow-gs] Vulkan device: name (index N, discrete|integrated|cpu[, forced])`). The default order is discrete,
integrated, virtual, CPU. `PS2X_VK_DEVICE=<index>` or `PS2X_VK_DEVICE=<substring>` (case-insensitive, against the
device name) forces one; a value that matches no usable device logs a warning and uses the default order.
Host VRAM is imported with `VK_EXT_external_memory_host`, so a discrete GPU works without a copy path of its own.
The launcher's `gpu` setting maps to this variable. `PS2X_VK_DEVICE` must be set before the first backend starts.

Measured on the Intel RPL-P iGPU vs the NVIDIA RTX 5050 Laptop (Linux, X11, `GOW_DELTA_DIAG=1`
`GOW_PERF_FRAME_PC=0x001837B8`, `PS2X_GS_VULKAN_STATS=1`, steady state of the intro/menu scene, ~11 s windows):

| Device | FPS (vid::Flip/s) | GPU ms per second (sum of `gow-gs-vk-gpu` gpu_ms) | Zero-copy import |
|---|---|---|---|
| NVIDIA RTX 5050 (default now) | 16.9 | ~102 | yes |
| Intel RPL-P | 7.1 | ~262-283 | yes |

The presentation path (CPU compositor + raylib/OpenGL texture upload) works unchanged on either device and the
menu screenshot (`GOW_SCREENSHOT_AT`) is correct on NVIDIA. `ps2x_tests` (631 with the new fallback test, all pass
on the NVIDIA default) includes both "Vulkan VRAM equals CPU VRAM" byte-identical tests. Observation, not
investigated: on Intel, runs started with `GOW_SCREENSHOT_AT` set together with `PS2X_GS_VULKAN_STATS=1`
closed the window cleanly after about 15 s (no screenshot written), while the same Intel run without
`GOW_SCREENSHOT_AT` ran the full 40-50 s. NVIDIA runs with it were fine.

## Gameplay profile, CLUT versions and transfer fences (2026-10-14)


Gameplay reached with `GOW_SKIP_FMV=1 GOW_PAD_TEST=1` (default pad script): the ship level with Kratos and the HUD is on
screen by t=50-75 s (checked in PNGs from `GOW_SCREENSHOT_AT`). Before: **~7.5 FPS** (`vid::Flip`/s from `gow-delta`
`frames`/`wall`). Per-thread CPU: GS worker 59%, EE 39%, VU1 worker 38%, render 3%. Costs per second: GPU ~550k prims/s
(rain particles), `gpu_busy` ~425 ms; CPU fallbacks ~1,500-1,900 prims/s (`tex-feedback` ~1,300-1,600, `z-alias` ~110-130,
`dest-alpha-test` ~110-140) = `cpudraw_ms` ~375-430; fences `finish_ms` ~390-435, of which `LoadClut` 660-680 ends/s =
~300 ms; 1,000 runs/s.

Changes (`patches/ps2recomp-gs-vulkan.patch`, `gs_vulkan_backend.cpp` and the shader):
- **CLUT snapshots.** The CLUT buffer holds 64 versions; an indexed primitive records the current version in `tmode`
  bits 25-31 and the shader reads that slot. `LoadClut` (CSM1) ends the run only if the run writes the CLUT's pages.
- **Non-conflicting transfers.** With the zero-copy import, `BeginTransfer`/`UploadImage` proceed without a fence when
  their pages are neither read nor written by the open run (`runReads`/`runWrites`; src checked against writes, dst
  against both). The copy path always fences (its end-of-run copy would overwrite the upload).
- **`tex-feedback` uses the sprite's UV box** (+1 texel if bilinear; only CLAMP or in-range UVs) instead of the declared
  texture size for the page test.

After: runs 900-1,000/s -> 250-300/s, `LoadClut` and `BeginTransfer` run ends gone; gameplay **~9-10 FPS**; intro/title
**~24 FPS** (was ~17). `ps2x_tests` 633/633 (the CLUT-between-GPU-draws cases now exercise the versions path).
Gaps: no new test for non-conflicting transfers (only exercised in the game); the UV box rarely helped, because the
remaining `tex-feedback` is real: 32-px strips of the frame sampling itself (same pixels, or bilinear neighbours), and
CT24 reads of the Z buffer (`tbp` = `zbp`, different `tbw`).

Left, in order: (1) `tex-feedback` (~430 ms/s CPU plus a GPU drain each time): the Z-copy case is order-safe as a snapshot,
and in-place same-pixel strips are race-free when the UV-to-pixel map is the identity; both need an exact test or a
scratch-copy dispatch; at minimum split fallback rows across the idle raster workers. (2) `z-alias` (~190 run ends/s in
the intro). (3) EE vs the GIF mutex (not touched). GPU alone is ~425 ms/s in gameplay, so fallbacks must go before more
GPU-side work pays off.

## Feedback, DATE and tight texture boxes on the GPU (2026-10-15, Linux, NVIDIA RTX 5050)

Changes in `patches/ps2recomp-gs-vulkan.patch` (`gs_vulkan_backend.cpp`, shader, test):
- **Same-pixel feedback proof (B2).** A FST sprite or triangle that samples the frame buffer itself (same base, width and
  swizzle class) no longer counts as `tex-feedback` when every pixel provably reads its own texel. Sprites: the host
  evaluates the shader's own UV expressions per column and row (12.4 re-quantisation included); nearest needs
  `floor(u) == x`, bilinear `u - 0.5 == x` (zero weights). Triangles: all vertices must satisfy `u = x + cu`,
  `v = y + cv` in raw 12.4 with `cu, cv` in [1,14] (nearest only; interpolation error stays below one raw unit). The thread
  reads the pixel it is about to write, so no cross-thread hazard and batch order is kept.
- **Disjoint read/write rectangles.** The 8-px "channel shuffle" strips (read the columns 8 px left) are detected by
  rectangle: UV box vs written box in the same buffer. Batch-mates still use page sets, so each strip is its own batch.
- **Z only tested is read-only.** Z pages count as written for the feedback test only when Z is written. This removed the
  Z-as-colour (`tbp` = `zbp`) fallbacks of the post-effects.
- **Tight UV box.** Exact sampled texel interval (first value to one step short of the far vertex, bilinear
  `floor(u - 0.5)` .. +1) instead of +-1 texel; the old padding made the first row of every strip look like a wrap.
- **Destination alpha test (B5)** in the shader (CT32 bit 31, CT16/CT16S bit 15, CT24 passes), `rec.test` keeps bits 14-15.
- **Not done:** `z-alias` (frame and Z pages overlap): Z32/Z24 pages are swizzled differently from CT32/CT24, so "same base"
  is NOT "same pixel" (a first attempt failed the byte compare); it needs the CPU's row order or an address-owner kernel.
  The general snapshot copy (B1) was not needed: no remaining `tex-feedback` is a snapshot candidate except a few
  d0/CT24 strips whose UV box is not provable (REPEAT past the edge).
- `GOW_VK_NO_FBOPT=1` restores page-level rules and the DATE fallback (A/B). `GOW_VK_FBDIAG=1` logs the first 80 distinct
  fallback shapes (`[fbdiag]`).
- Test: "Feedback and Z-as-colour Vulkan VRAM equals CPU VRAM" (identity nearest/bilinear/triangle, shuffle strips, overlap,
  one real feedback and two Z aliases on the CPU, Z read as colour, DATE CT32/CT16); asserts 11 GPU primitives.
  ps2x_tests 634 pass.

| Measurement (NVIDIA, `PS2X_GS_VULKAN_STATS=1`) | before (`GOW_VK_NO_FBOPT=1`) | after |
|---|---|---|
| gameplay CPU fallbacks, prims/s | ~1,800-2,200 | ~400-520 |
| gameplay `cpudraw_ms`/s | ~330-370 | ~160-200 |
| gameplay `tex-feedback` / `dest-alpha-test` / `z-alias` per s | ~1,470-1,870 / 160 / 160-176 | ~190-250 / 0 / ~190-250 |
| gameplay FPS (rainy fight, avg 12 s) | 14.8 | 22.7 |
| `gpu_busy` ms/s | ~425 | ~650 (work moved to the GPU) |
| intro/title FPS (avg 23 s, no FMV skip) | 26.2 | 32.3 |
Screenshots of the new build show correct bloom/rain/HUD; same-moment comparison with the CPU backend is not possible
(the pad script and loading are wall-clock, the CPU backend runs at 4 FPS), so exactness rests on the byte-identical tests.
Thread CPU% was not measured. Next: `z-alias` is now the biggest fallback (~200/s gameplay, ~500/s intro).

## Frame/Z alias on the GPU (2026-10-15)

- The shader already addressed the frame with its PSM and Z with the Z PSM (separate `readPixel`/`writePixelRaw`), so the
  only danger of `z-alias` is two different pixels owning one VRAM word. `frameZAliasSafe` (host, per primitive) proves
  it at 8x8-block level for CT32/CT24 frame + Z32/Z24: both share the column layout and differ only in the block table,
  so a frame block may equal a Z block only of the same pixel block (one thread owns the word, write order frame then Z
  as on the CPU). Any other match, 16-bit formats, or more than 20,000 blocks keep the CPU fallback. Textured reads of
  frame/Z pages of an aliasing primitive stay on the CPU (`tex-feedback`). Batch rules need no change: frames/depths
  page overlap already ends the batch.
- `GOW_VK_NO_ZALIAS=1` (or `GOW_VK_NO_FBOPT=1`) restores the fallback for A/B.
- Test: four extra aliasing sprites in the feedback scene (one block, 64x16 strip, CT24/Z24, Z only tested) must run on
  the GPU byte-identical (15 GPU primitives); the old multi-block aliases still fall back. `ps2x_tests` 634 pass.

| Gameplay (ship fight, `GOW_SKIP_FMV=1 GOW_PAD_TEST=1`, 30 s at ~55-85 s) | before (`GOW_VK_NO_ZALIAS=1`) | after |
|---|---|---|
| `z-alias` fallbacks/s | ~300 | 0 |
| CPU fallback prims/s | ~630 | ~220 (`tex-feedback` ~210, line/point ~13) |
| `cpudraw_ms`/s | ~255 | ~150 |
| window FPS | 13.8 (12.8 without the 20 FPS outliers) | 12.8 |

FPS did not move: this scene is heavier than the earlier 22.7 FPS measurement (same binary family, both A/B runs ~13)
and is GPU-bound, not fallback-bound. Thread CPU (10 s): EE `GameThread` 72-77%, `GSThread` 47-49%, two more game
threads 38-40% / 11%; others idle. Stats: `finish_ms` ~540 ms/s (EE waiting for the GPU), `gpu_busy` ~600+ ms/s.
gdb sampling could not be done: `ptrace_scope=1` forbids attach and the gdb-launched run never produced samples in
the budget; the EE/GIF mutex share is NOT measured.
Top costs (estimates, unverified): (1) GPU time per frame, ~600 ms/s busy and `finish_ms` ~540 ms/s: dispatch walk
(`walk_Mpx` >> `covered_Mpx`), a better tile/primitive culling is worth most (maybe +20-40%); (2) remaining `tex-feedback`
CPU fallbacks ~210/s, ~150 ms/s of `cpudraw_ms` (+5-10%); (3) `record-ring` and `Flush()` run ends (~100 ms/s each, +3-5%).
Intro/title was not re-profiled (out of budget).

## Repeatable GPU benchmark and shader profile (2026-10-15)

**Tooling** (no game data in the repo; captures live under `logs/`, which is git-ignored):
1. Record gameplay GS input once, with the normal runner (`src/gow_gs_replay.h`, limit raised from 64 MiB to 768 MiB):
   `GOW_SKIP_FMV=1 GOW_PAD_TEST=1 GOW_GS_REPLAY_TRACE=logs/bench/gameplay.gsr GOW_GS_REPLAY_AFTER=65 GOW_GS_REPLAY_SECONDS=3 ps2EntryRunner SCUS_973.99`
   (cwd = the ELF directory, `GOW_ISO` set). It starts in game state 11, snapshots VRAM + backend state, then logs every
   backend call (primitives, CLUT, transfers, uploads, reads, presents) until the size limit: 121 presents, 1.93M
   primitives, 757 MiB in the rainy fight scene.
2. `scripts/compilar_bench_vk.sh` builds `logs/bench/bench_vk` (`tools/render/bench_vk.cpp`) against the built runtime.
3. `logs/bench/bench_vk logs/bench/gameplay.gsr [passes=5] [--no-cpu] 2>/dev/null` replays the capture headless through
   `GSCpuBackend` once (reference) and through `GSVulkanBackend` N times (zero-copy VRAM, same code as the game). Per pass it
   prints GPU ms from timestamps (`GSVulkanBackend::GpuTotals`, needs `PS2X_GS_VULKAN_STATS`, which the tool sets), dispatches,
   prims, wall ms, and `vram_diff_bytes` against the CPU replay (exit code 3 on any difference), then mean/sd. It also checks
   every `ReadVram`/`ClearFramebuffer`/`Consume` result recorded in the capture. Run to run the GPU time varies ~0.3-0.8%.

**Profile** (ablations on the capture, RTX 5050, GPU ms for the whole 121-presents replay; baseline 1662):

| Variant | GPU ms |
|---|---|
| shade() never called (tile culling + barriers only) | 115 |
| coverage only (edge tests + weights, no Z/tex/blend/write) | 690 |
| no pixel writes (blend/fb read dead-code removed) | 738 |
| no texture fetch | 1150 |
| full | 1662 |

Mix: 2.26M textured+blended tristrip triangles (rain), few sprites. Average batch: 112 prims, 17k px union, 0.097 ms per
dispatch, i.e. each pixel walks a serial chain of ~100 prims with only ~270 workgroups in flight: the kernel is
latency-bound (serial per-pixel prim walk), not ALU- or bandwidth-bound; culling/barriers are only ~7%.

**Kept optimizations** (`patches/ps2recomp-gs-vulkan-perf.patch`, registered last; byte-identical):

| Step | GPU ms | per presented frame |
|---|---|---|
| baseline | 1662 | 13.7 |
| Z test moved before the texture fetch (all pre-write returns are side-effect free) | 1415 | 11.7 |
| tile culling also tests the triangle edges at the tile's best corner | 1319 | 10.9 |
Total -21% GPU time; wall of the replay 2632 -> 2160 ms. `ps2x_tests` 634 pass; replay VRAM identical to the CPU backend.
Tried and dropped: exact float-estimate + integer-fixup replacement of the 64-bit division in `ratioMantissa` (no change:
the compiler/hardware is not division-bound), `restrict` on the prim/swizzle buffers (no change).

**Real game** (`GOW_SKIP_FMV=1 GOW_PAD_TEST=1`, NVIDIA RTX 5050, mean FPS over t>55 s, three runs, `gow-delta`):
17.9 / 21.8 / 15.0 (mean 18.2, scene and pad-script dependent; the pre-change rainy-fight figure was ~13; no same-scene A/B).
`gpu_busy` 550-620 ms/s.

**What is left** (ideas, ranked): (1) cut the per-pixel serial chain: per-tile prim lists with prim data staged in shared
memory (software-pipelined loads), or smaller dispatches split by independent tiles; (2) split thin-triangle tiles at 4x4
for better culling; (3) pack the `FMT_*` tables into one word and hoist per-prim format decode out of the pixel loop;
(4) skip bilinear/blend work for pixels whose Z test fails (already done for texture); (5) a graphics pipeline for large
opaque prims. The CPU side is not the limit: the replay with no shading runs 121 presents in ~1050 ms wall.
