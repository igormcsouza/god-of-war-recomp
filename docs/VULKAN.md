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
- **Device.** One process-wide `VkInstance`/`VkDevice`. The default device prefers integrated, then
  discrete, then CPU (llvmpipe). `PS2X_VK_DEVICE=<index>` forces a device. Each backend owns its VRAM
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
