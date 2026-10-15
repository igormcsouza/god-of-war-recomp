# Hybrid hardware-style GS renderer: feasibility and plan (2026-10-15)

Research only. No code changed, game not run. Inputs: docs/VULKAN.md (architecture, measurements),
docs/EMULATOR_RESEARCH.md (PCSX2 notes), PROGRESS_LOG 'Strategy note'. PCSX2 file/function names below are from
EMULATOR_RESEARCH.md (read from master then) or from memory (marked "(memory)"); WebFetch was not used, so
re-verify before building on any (memory) claim.

## 0. Problem and idea

The exact compute path (one thread per pixel, ordered prim walk, 4 MiB VRAM storage buffer) costs ~10 ms GPU per
Present, ~2.7 Presents per displayed frame, so ~25-30 FPS at best at native res and no cheap route to 1080p
(cost scales with shaded pixels: 2.25x at 1080p). Rain/particles give ~17x overdraw: ~2.26M textured+blended
triangles, ~600 Mpx shaded per 121 Presents (~5 Mpx per Present). A graphics pipeline spends the same work in
ROP/blend hardware, early-Z and tile-based caches, which is what makes PCSX2's Vulkan HW renderer fast.

Proposal: a second backend `PS2X_GS_BACKEND=vulkan-hw` (`vulkan` = exact compute stays; `cpu` stays reference).
`vulkan-hw` wraps the same `GSCpuBackend` frontend and the exact Vulkan backend. Per draw it either rasterizes
through the graphics pipeline or, if the state is unsupported, flushes HW targets into VRAM and hands the draw to the
exact path (which still sees correct VRAM). Correctness is never lost, only exactness of supported draws.

## 1. Architecture

### 1.1 Render targets
- Target = (FBP, FBW, PSM, kind colour|depth) -> `VkImage` of size (FBW*64) x height, R8G8B8A8_UNORM (CT32/CT24/CT16
  all stored as 8-bit-per-channel RGBA, CT16 expanded 5-5-5-1 to 8888 and quantised on writeback). Height from
  scissor/draws seen, grown on demand (PCSX2 `GSTextureCache::LookupTarget`, memory).
- Upscale factor `PS2X_HW_SCALE` (1,2,3). Image size = native * scale; all coordinates multiplied; scissor/viewport
  scaled; sprites/textures sampled with the same scale-independent UVs. 1080p ~= x2.25 of 640x448 -> use 3x for
  1920x1344 downscaled at present, or x2 + linear upscale. Upscaling is free of exactness concerns (no readback).
- Lifetime: target is created on first draw, kept in a list keyed by (FBP, FBW, PSM). Overlapping a different
  target (e.g. same FBP with another PSM, or a Z target used as colour) triggers conversion/resolve (1.5, 1.6).
- Page-granular dirty ranges (8 KiB pages, 512 per VRAM) are tracked per target: `gpuDirty` (image newer than VRAM)
  and `hostDirty` (VRAM newer than image).

### 1.2 Depth
- Z formats: Z32 -> D32_SFLOAT (exact for 24-bit-ish values only if scaled; use R32_UINT-free approach: store
  z/2^32 as float: loses low bits beyond 24; compare is monotonic so ZTST is still right except near-equal cases),
  Z24 -> D32_SFLOAT or D24; Z16/Z16S -> D16/D32. Prefer D32_SFLOAT everywhere (NVIDIA supports D32S8).
- ZTST: NEVER -> compare NEVER; ALWAYS -> ALWAYS (ZWRITE kept as set); GEQUAL -> GREATER_OR_EQUAL; GREATER -> GREATER.
  PS2 Z is larger-is-nearer; map z' = z/2^32 and use GREATER_OR_EQUAL directly (no reversing) or flip with
  `1 - z`. ZMSK=1 -> depth write off. FBMSK -> colour write mask (full channels only; partial bit masks need shader
  emulation, see 1.5).
- Z and colour are separate images; PCSX2 does the same (`GSRendererHW::DrawPrims` ds/rt, memory).
- Depth as texture: sample the depth image (separate sampler/format view), or on aliasing copy to a colour temp
  (PCSX2 `LookupDepthSource`, `m_using_temp_z`, `SetTemporaryZ`, per EMULATOR_RESEARCH B).
- Z written by the vertex shader from the GS 24/32-bit integer Z (`gl_Position.z` or `gl_FragDepth` when Z is
  interpolated non-linearly for textured Q: not needed, GS Z is screen-linear).

### 1.3 Texture cache
- Key: (TBP0, TBW, PSM, TW, TH, CBP, CPSM, CSM/CSA, TEXA, clamp mode-independent) -> linear RGBA8 image. Source is either
  a live render target (preferred, zero copy, 1.6) or VRAM.
- Upload from VRAM: a compute shader reads the 4 MiB VRAM buffer using the existing GLSL helpers
  (`GSGpuShaders::kCommon` `locate/readPixel`, swizzle tables) and writes the linear image; paletted T8/T4 variants
  apply the CLUT during upload (either CLUT-expanded RGBA8 or R8 index + 256x1 palette texture sampled in shader,
  as PCSX2 does for palette textures, memory). Bake palette into RGBA8 first (simple); switch to index+palette only
  if CLUT churn shows in profiles. CLUT already versioned per primitive in the exact backend (VULKAN.md).
- Invalidation: any VRAM write overlapping a cached page range (transfers, local-to-local, CPU-fallback draws, resolves)
  bumps a per-page write counter; entry stores counters of its pages, revalidated at lookup. Same counters drive
  `hostDirty`. The exact backend's `BeginTransfer/UploadImage/LoadClut` hooks in the wrapper are the choke points.
- Eviction: LRU by frame age and total bytes. Region clamp/repeat (CLAMP MINU/MAXU...) is done in the shader on the
  linear image; texture is uploaded for the bounding region only (PCSX2 `GSTextureCache::Source`, memory).
- Hash-check on reuse: for tiny textures that change in place (palette animation, scrolling), compare page contents
  by cheap XOR hash of source pages when counters changed, before re-uploading.

### 1.4 Keeping the 4 MiB VRAM coherent
- Invariant: before ANY exact-path consumer touches VRAM (CPU fallback draw, `Present` via CPU compositor, `ReadVram`,
  `SnapshotVram`, `ConsumeLocalToHostBytes`, host->local/local->local transfers that read, CLUT load), every
  `gpuDirty` target page range it can read is resolved: compute shader swizzles image -> VRAM (inverse of upload,
  using `writePixelRaw`), quantising to the target PSM. Resolve is lazy and page-ranged, never whole VRAM.
- Reverse: a transfer, fallback draw or host write that lands on a target's pages marks those pages `hostDirty`; on next
  HW draw the affected target region is re-uploaded from VRAM (unswizzle compute) before use.
- Upscaled targets: resolve downsamples (point sample centre of each native pixel) so VRAM holds the native image.
  Quality: lossy vs exact; fine for transfers that move data back to textures (bloom reads), wrong for CT24-as-Z or
  bit tricks, which must fall back (1.9).
- CT24-as-Z / Z-as-colour tricks (EMULATOR_RESEARCH B3): detect FRAME and ZBUF overlapping pages or a texture
  sourced from an active Z target with colour PSM: do a per-draw resolve of Z to VRAM, run the draw on the exact
  path. First milestone supports only clean cases; GoW bloom/blur likely uses these (risk R2).

### 1.5 Blending, alpha test, feedback
The GS blend is `Cs = (A-B)*C + D`, A/B/D in {Cs,Cd,0}, C in {As,Ad,FIX}, result /128 with COLCLAMP/wrap, plus PABE and FBA,
MSB-set, Ad from the dest alpha channel in 8888 and the fixed 0x80 for CT24.
- Fixed function covers most: add/sub/revsub with src factor from {1,0,SRC_ALPHA,DST_ALPHA,CONSTANT_ALPHA} and dst factor from
  {…, ONE_MINUS_*}. The classic blends (Cs*As + Cd*(1-As), Cs*As + Cd, etc.) map exactly except the GS factor
  range: As/128 can exceed 1 (As up to 255 -> 1.99) => needs shader pre-scaling or clamp; PCSX2 solves by
  `ColorCorrection`/`HWBlend` classification tables in `GSDevice` (memory). Use PCSX2's approach: classify
  A/B/C/D into a mode; if fixed function can't do it, run `blend_hw`-style shader blend.
- Shader blend (read the destination): needs framebuffer fetch. On this host `vulkaninfo` lists
  VK_EXT_fragment_shader_interlock, VK_EXT_rasterization_order_attachment_access, VK_EXT_attachment_feedback_loop_layout
  and VK_KHR_dynamic_rendering_local_read (driver 580.178.04; per-device not checked, the list may mix GPUs). NVIDIA
  proprietary is known for interlock and feedback-loop layout (memory), but NOT for ARM-style
  rasterization_order_attachment_access (listed here is "ARM"; likely Mesa/Intel). Plan: (a) fixed function default,
  (b) `fragment_shader_interlock` (pixel-ordered) on NVIDIA for shader blend, (c) fallback = per-draw copy of the RT
  + texture barrier (PCSX2's "barrier / copy" modes), (d) else exact path. Query features at startup and pick.
  Interlock cost is real; use only for the unsupported-blend minority.
- Alpha test (ATE, ATST, AREF, AFAIL): in shader via `discard` for KEEP/FB_ONLY/ZB_ONLY cases: AFAIL=KEEP -> discard;
  FB_ONLY -> keep colour write, disable Z write (shader cannot disable Z write per-fragment; PCSX2 solves via
  `ps_alpha_fail` flags with a second pass, memory) -> support KEEP and ALWAYS only at first, fall back otherwise.
  RGB_ONLY (no alpha write) is a colour write mask.
- FBA / dest-alpha test (DATE): PCSX2 `EmulateDATESelectMethod` (stencil / primitive-ID / barrier). Use stencil
  initially; fall back when the pass is unsupported (exact path has it).
- FBMSK partial masks: shader (read dest); fall back unless the mask is 0 or 0xFF per channel.
- Fog: per-vertex fog factor -> shader mix with FOGCOL. PRIM FGE only; straightforward.
- Colour: Gouraud 8-bit interpolation differs from GS in LSB; acceptable; texture function (MODULATE/DECAL/HIGHLIGHT) in shader,
  `*2` modulate clamp, TCC with TEXA.

### 1.6 PRIM types, sampling, exactness issues
- Sprites -> two triangles (axis-aligned quad), triangles direct, strips/fans -> indexed triangles, lines/points -> quads
  (PCSX2 expands to `GS_TRIANGLE_CLASS`; sprite handling in `GSRendererHW::ConvertSpriteTextureShuffle*`, per notes).
  Lines/points rarely matter for GoW; first cut falls back to the exact path.
- Half-pixel offset: GS pixel centres at +0.5 vs raster conventions; use viewport/offset such that coverage matches (PCSX2
  GameDB sets `halfPixelOffset=5` for SCUS-97399 per EMULATOR_RESEARCH 0, so expect GoW needs the "special texture" mode).
- UV rounding: GS FST UV 12.4 fixed; texel centre sampling `(u + 0.5)` at x scale; nearest = exact mismatch only on tie;
  bilinear: GS uses 4-bit weights vs GPU 8-bit: tiny diffs. Perspective STQ: pass q, `uv/q` per pixel (screen-linear Q).
- Mipmaps: GoW seems to use few (assumed, unmeasured; check `MIPTBP` usage in replay). Implement base level only; fall back
  when MXL>0 and LCM selects higher levels.
- CLAMP REGION: shader clamp to region bounds (integer texel clamp in the shader before sampling).
- Texture feedback / channel shuffles (PCSX2 `DetectTextureShuffle`, `IsPossibleChannelShuffle`,
  `ConvertSpriteTextureShuffleImpl`, `DetermineBarriers`, `ComputeDrawlistGetSize`): the 8-px strip effects get merged into one
  quad. For v1 do NOT implement; detect "source overlaps own target" (`tex-feedback` stat today) and fall back to
  exact (flush targets, run the draw on compute). GoW1's `autoFlush=1` in PCSX2 GameDB signals sun-occlusion style
  reads of just-written pixels (EMULATOR_RESEARCH 0). Handle later with barrier modes.

### 1.7 Presentation and upscaling
- Today `Present` runs the CPU PCRTC compositor on host VRAM and raylib uploads the frame. In HW mode the visible FB
  (DISPFB, DISPLAY, merge circuit) comes from a render target image: resolve to native VRAM only when the CPU compositor is
  required (MODE: PCRTC merge of two read circuits, field/frame deinterlace, MAGH/MAGV).
- v1: GPU compositor shader samples the display target(s): single read circuit, optional alpha merge, handles
  interlace as weave/bob (field select), writes an RGBA8 image (possibly 1920x1080 via bilinear/Lanczos).
  Readback that RGBA to host (6-8 MB at 1080p) into raylib's texture: ~1 ms pci, acceptable, keeps raylib/GLFW.
- v2: direct Vulkan swapchain (needs window/surface ownership change from raylib/OpenGL; larger refactor). Not in plan v1.
- Screenshots (`GOW_SCREENSHOT_AT`) and window FPS continue to use the readback RGBA.

### 1.8 Pipeline structure
- Vertex shader: GS XYZ (+XYOFFSET) -> clip space, UV/ST/Q pass-through, RGBA, fog, z. One VkPipeline per (blend
  mode, depth test, alpha test, tex mode, FBMSK class, prim) hashed on state; precompile common ones, build rest
  on demand with pipeline cache (stall risk, see risks).
- Dynamic rendering + dynamic state (scissor/viewport/depth compare/blend constants) to limit pipeline count.
- Batching: coalesce consecutive prims with the same state into one draw call (like the exact path's batches);
  flush on any state change, target change, transfer, texture upload invalidating a live texture.

## 2. Reuse versus new

Reusable as-is:
- The frontend register parsing and state (`gs_frontend.cpp`, `GSCpuBackend` primitive setup, CLUT versioning,
  scissor/XYOFFSET, texture state structs, `Prim` records).
- The Vulkan device/instance/queue, zero-copy host VRAM import, upload ring, timestamp/stat infrastructure
  (`PS2X_GS_VULKAN_STATS`), the lazy host sync and two-phase `Present`.
- `GSGpuShaders::kCommon` swizzle helpers for texture upload and target resolve; the 8-bit PSM packers.
- `bench_vk` + `.gsr` replay capture (121 Presents, 1.93M prims) for timing and as a deterministic source of draws.
- The exact path itself as the reference and per-draw fallback; `ps2x_tests` GS Vulkan tests for the fallback.

New:
- Target and depth image manager, texture cache with dirty/page counters, pipeline cache and state-hash, shader generator
  (VS/FS variants), GPU compositor shader, resolve/upload compute passes, backend wrapper and `vulkan-hw` selection,
  image-diff harness.

Test change: byte-compare of VRAM no longer applies to `vulkan-hw`. Replace with:
(a) replay on exact path -> reference final display RGBA per Present (already available via the CPU compositor on VRAM) and replay
on HW -> RGBA; compute PSNR and SSIM per Present, report min/mean/p95; (b) fixed-pixel exact checks for CT32 flat-colour
cases (rects, sprites, alpha=1 blends) where equality should hold; (c) the existing exact tests unchanged (fallback path).
Add a `bench_vk --image-diff` mode (`tools/render/bench_vk.cpp`); thresholds in section 4.

## 3. Expected performance and risks

Reasoning: shaded fragments are the same ~5 Mpx/Present (600 Mpx / 121), but ROP blend rate on an RTX 5050 laptop
class GPU is of the order of 50-100 Gpx/s (memory; real laptop clocks lower, ~40 Gpx/s) => 5 Mpx ~ 0.1-0.3 ms fill
time, plus textured sampling (rain textures are small, L1-hot) and early-Z. Realistically vertex + setup + state change
dominate: 1.93M prims / 121 = 16k prims/Present; with ~112 prims/batch => ~140 draw batches per Present; pipeline
state flips and descriptor binding cost ~ 5-20 us each => ~1-3 ms. Upload/resolve compute passes add ~0.5-2 ms.
Estimate: 2-4 ms GPU per Present (vs 10 ms) at native res, 3-6 ms at 2x/1080p => 2.7 Presents ~ 6-11 ms per frame
in GPU, so 60 FPS is plausible IF the CPU/GS-worker side keeps up: today the GS worker is 92-98% busy (stalls, CPU
fallbacks ~200 ms/s) and EE idles 60% in guest waits; the live FPS gap to replay (1.4x) is Presents per flip. The
fallback rate is the decisive unknown: each fallback forces resolve + flush + exact + re-upload (~1-3 ms).
If > ~150 fallbacks/s the gain evaporates. Honest expected result: 45-60 FPS native, 35-55 at 1080p, unproven.

Top risks:
- R1 Fallback churn: tex-feedback/z-alias are currently ~200-400 prims/s on GPU path and CPU on the exact path; each one now
  costs a target resolve. Mitigate with targeted barrier modes (PCSX2 `DetermineBarriers`) in milestone 6.
- R2 GoW effects: bloom/blur via sprites reading frame and Z-as-colour (autoFlush, `nativeScaling` for GoW2 blooms);
  shadows (depth-as-colour tricks, stencil-like alpha writes); both stress sections 1.4/1.6. Visual diffs likely here first.
- R3 Rain/particles: blend correctness for 255-alpha-range, huge count of tiny textured triangles: setup rate and
  pipeline-state flips; 17x overdraw must not be resolved by readbacks.
- R4 Z precision (D32F vs 32-bit integer Z): z-fighting differences; ZTST on near-equal Z (decals) may flicker.
- R5 CT16 / CT24 alpha semantics (dest alpha 0x80, FBA) and partial FBMSK: fall back, keep a stats counter.
- R6 Pipeline compile hitching on NVIDIA: warm up from replays, use `VkPipelineCache` saved to disk.
- R7 Maintenance: two renderers; feature drift. The exact path stays the oracle; image-diff CI is mandatory.
- R8 Time: PCSX2's HW renderer is ~50k lines refined over a decade; a GoW-only subset is feasible, a general one is not.

## 4. Milestones (max 8; each for one Sonnet agent, ~120k tokens)

1. **Image-diff harness and reference.** Extend `bench_vk` with `--dump-presents DIR` (display RGBA per Present, CPU
   compositor on exact VRAM) and `tools/render/imgdiff.py` (PSNR/SSIM, per-Present table). Add `PS2X_GS_BACKEND=vulkan-hw`
   stub that delegates 100% to exact. Accept: exact-vs-exact diff PSNR inf; replay runs; selection env logged. (Sonnet.)
2. **Targets + upload/resolve + sprite pipeline.** Target manager (colour only, CT32/CT24/CT16, scale 1), VRAM-to-image and
   image-to-VRAM compute (kCommon), flat+textured sprite and triangle draws without blend/Z, everything else falls back
   per draw with correct flushes. Accept: replay PSNR >= 35 dB mean on prims it takes; zero crashes; fallback reasons
   histogram printed; `ps2x_tests` still pass. (**Stronger model recommended for design review of the coherence invariant 1.4**; the
   implementation is Sonnet work.)
3. **Texture cache + CLUT.** Swizzled -> linear upload, T8/T4 palette baked, page-counter invalidation, texture sampling
   modes (REPEAT/CLAMP/REGION, nearest/bilinear), TFX/TCC. Accept: textured prims of the replay match exact; mean PSNR
   >= 32 dB overall on the replay (blend/Z still partially falling back); screenshot of the menu and one gameplay frame
   visually fine.
4. **Depth + blending + alpha test.** D32F target pairs, ZTST/ZMSK, fixed-function blend table, alpha test KEEP, fog, FBMSK
   full-channel. Accept: >= 90% of replay prims on HW path; mean PSNR >= 30 dB, p5 >= 24 dB; gameplay screenshot
   (rain, fight) visually passes owner's side-by-side view. (**Stronger model advised** for the blend factor
   classification and Z mapping; it is subtle.)
5. **Presentation: GPU compositor + upscale.** PCRTC single/dual read circuit, deinterlace, DISPLAY/MAG, scale
   2x/3x targets, readback into raylib. Accept: window shows image; `GOW_SCREENSHOT_AT` works at x1 and x2; x1 matches
   milestone-4 diff; 1080p screenshot viewed OK.
6. **Feedback and coherence cases.** Detect self-overlap (tex-feedback) and Z-as-colour; barrier/copy modes
   (framebuffer-fetch via interlock/feedback-loop where available), merge strip sprites (shuffle) minimal; reduce fallbacks.
   Accept: fallback prims/s in gameplay replay < 100/s equiv; bloom/blur pass screenshot matches (PSNR >= 28 dB in those
   frames). (**Stronger model required**: PCSX2-level subtlety, design of barriers.)
7. **Performance pass.** Pipeline cache, draw batching, descriptor indexing, async texture upload, avoid host sync stalls
   on hot path, profile with timestamps. Accept: replay GPU ms/Present <= 4 ms (x1), <= 7 ms (x2); live FPS (guest flips)
   >= 45 native on RTX 5050; no hitch > 50 ms after warm-up.
8. **Hardening and defaults.** Fall-back statistics, `PS2X_HW_SCALE`, launcher settings, docs, tests; run 10-minute gameplay
   soak, compare screenshots with exact at chosen points. Accept: no crashes, VRAM-coherence assertion mode
   (`PS2X_HW_VERIFY=1` compares a resolve against exact periodically) shows no drift on replay; decision to make `vulkan-hw`
   the default only if FPS >= 55 and PSNR p5 >= 26 dB on replay and owner approves visually.

Strongest-model steps: design review of step 2 invariants, steps 4 (blend/Z) and 6 (feedback/barriers). Others are Sonnet-sized.

## 5. Recommendation

Conditional GO, staged with an explicit stop gate after milestone 4 (the cheap evidence point): by then the replay tells the
GPU ms per Present of the HW path for ~90% of draws and the fallback count. If GPU ms/Present is not < 5 ms at x1 or
fallbacks exceed ~150/s after milestone 4, stop and keep the exact path. Total: 8 Sonnet-sized sessions + 3 strong-model
reviews; the owner's visual sign-off is the real acceptance (not bit equality).

Honesty: 60 FPS at 1080p is not guaranteed. The CPU side (GS worker 92-98% busy, VU1/EE costs, ~200 ms/s fallbacks)
may become the limit once the GPU is fast; do the pipeline-stall work in parallel.

Alternatives:
- A. Improve the compute path: measured knobs already tried (tile culling, shared-memory staging, register-resident state)
  gave -10 to -20% GPU each; remaining ideas: bin prims per 64x32 page with per-page ordered lists
  (EMULATOR_RESEARCH B4), early-out on opaque Z fail via per-tile max-depth hierarchy (skips most of the 17x
  overdraw's occluded part), lower precision paths. Realistic: ~30-35 FPS native, no cheap 1080p. Cost: 2-3 Sonnet
  sessions. Fully exact. Recommended as the interim step while the plan is evaluated.
- B. Hybrid within compute: rasterize only the rain/particle class (alpha-blend triangles with no Z write, no feedback) with
  a graphics pass into the same 4 MiB buffer using storage image/atomic blend? Not exact; not recommended.
- C. Drop FPS target: accept 25-30 FPS and a 60 Hz present with frame pacing. Zero cost.
- D. Bridge to PCSX2's GS module: the repo has pcsx2 client/mirror/queue code in `src/` and `tools/render/pcsx2_*`;
  using PCSX2's actual HW renderer as a library would give the quality and speed, but a heavy dependency/licence (GPLv3)
  and architecture question for the owner; not evaluated here.
