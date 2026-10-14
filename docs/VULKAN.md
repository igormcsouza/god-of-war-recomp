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
- **Rasterization.** Each primitive is one compute dispatch over its scissored bounding box. Coverage
  uses the integer edge functions of `gs_triangle_rules.h` (64-bit, `shaderInt64`). Sprites use
  `gsSpriteAxis`. Gouraud weights are the correctly rounded `e/area`, and the colour sums are `precise`.
  The result is bit-exact against `GSCpuBackend`. A barrier between dispatches keeps GS draw order.
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

## Validation

`GSCpuBackend` is the reference. `ps2x_tests` → "GS Vulkan backend" renders the same scene with both
backends from the same noisy VRAM and requires identical bytes. The scene has a flat sprite with
fractional edges, a Gouraud triangle, a flat strip with XYOFFSET and scissor, FBMSK+FBA, a blended
sprite (CPU fallback in the middle of a GPU run, overlapped later), and CT16 and CT24 targets. It skips
when no device exists. It passes on Intel RPL-P (Mesa), NVIDIA RTX 5050 and llvmpipe. Running the whole
suite with `PS2X_GS_BACKEND=vulkan` and a finish after each primitive (a temporary local change) also
passes 628/628. Without that change, three frontend tests fail: they read the host `vram` array
directly, without `Flush`, which is why the library default stays CPU.

## Phases

- **A (done):** device/scaffold, untextured sprites and triangles (flat/Gouraud) on CT32/24/16/16S with
  FBMSK/FBA, and CPU fallback for everything else.
- **B:** textured sprites and triangles. Bring sampling, CLUT and TEXA over from `kRaster`, upload
  CLUT to the GPU, and keep transfers on the GPU so runs are not split.
- **C:** blending, alpha/destination/Z tests, fog, lines and points. Adopt the batching and tile binning
  of the OpenGL backend (`kRaster`) instead of one dispatch per primitive. Track dirty pages instead of
  whole-VRAM copies, and add a GPU compositor/swizzle readback for `Present`. Validate each step
  against the CPU, both with the test scene and with in-game screenshots.
