# Next steps to 60 FPS: inventory, fresh profile, ranked plan (2026-10-15)

Planning only. Inputs: PROGRESS_LOG.md, VULKAN.md, HW_RENDERER_PLAN.md, EMULATOR_RESEARCH.md, ESTADO.md, PCSX2_GS.md,
one fresh profile run (below), and the paraLLEl-GS write-up (themaister.net, 2024-07-03, summarised by the lead).

## 1. Fresh profile (this session)

Gameplay, `GOW_SKIP_FMV=1 GOW_PAD_TEST=1 GOW_AUDIO=0`, `PS2X_GS_VULKAN_STATS=1 PS2X_PIPE_STATS=1 GOW_DELTA_DIAG=1`, RTX 5050,
defaults (Vulkan GS, compiled VU1, VU1 thread, GS front thread, lazy sync). Medians over t=55-88 s, one runner only on
the machine (checked every 3 s). Per-thread CPU from `/proc/PID/task/*/stat` over 30 s.

| Metric | Value | Meaning |
|---|---|---|
| guest flips/s | 22 (other run, heavier scene: 15) | window FPS |
| game speed | 1.00, `last_delta` 0.048 s | game runs in real time; it simply produces ~3 vblanks per frame |
| VU1 worker thread CPU | **83.5%** (`vu1_busy` 835 ms/s) | **most loaded CPU thread; caps ~26 FPS in this scene on its own** |
| GS worker thread CPU | 45.7% (`gs_busy` 684, `gs_idle` 324 ms/s) | not saturated now; `finish_ms` 249, `cpudraw_ms` 238, `record_ms` **182** |
| EE thread CPU | 41.7% (`guest_wait` 587 ms/s) | ~1.9% per frame: would cap ~50 FPS |
| GIF front thread CPU | 10.1% (`publish_wait` 338 ms/s) | blocked on the 8-chunk GS queue |
| render thread CPU | 15.6% | ~50 Presents/s (~2.3 per flip), `drain_wait` 194 ms/s |
| GPU busy | 523 ms/s, 6,400 dispatches/s, 780k prims/s | ~24 ms GPU per displayed frame (~36 ms in the 15 FPS scene) |
| CPU fallbacks | ~370 prims/s (`tex-feedback` ~350, line/point ~20) | |

Conclusions:
1. **No single bottleneck.** VU1 (84%), GS worker (68% busy), GPU (52%) and EE (42%) are all mid-to-high loaded at 22 FPS.
   Per displayed frame: VU1 ~38 ms, GPU ~24-36 ms, GS-worker CPU ~21 ms, EE ~19 ms. 60 FPS needs every one of them under
   ~14 ms, i.e. VU1 ~2.7x, GPU ~2-2.6x, GS-worker CPU ~1.5x, EE ~1.4x faster, plus better overlap between stages.
2. **The GPU is not the only wall.** A perfect renderer (own HW path or PCSX2) leaves VU1 capping ~26 FPS in rain scenes.
   Previous docs called VU1 "not limiting" from intro/title profiles; gameplay (rain, ~80k prims per frame) says otherwise.
3. "~10 ms GPU per Present" was an accounting unit (GPU draw time / Presents). Presents themselves are cheap on the GPU
   (4 MiB copy); merging or skipping Presents saves render-thread CPU and drain time, not GPU draw time.
4. `record_ms` (Vulkan recording on the GS worker) is now 100-250 ms/s, not the 1-6 ms of older notes: ~0.23 us per prim.
5. Measurement hygiene: another agent ran the game concurrently and used `pkill -f ps2EntryRunner`, which killed this
   session's gdb sampling run. Only one game-running agent at a time; kill your own PID only.

## 2. Inventory

Tried (result):
- GPU kernel: early Z before texture (-15%), triangle edge tile culling (-7%), register-resident fb/Z words (-10.6%),
  stateless tile HiZ (-2.3%), dead-prim skip (0), per-tile ordered lists + shared-memory staging (worse), int32 slopes (0),
  fb-read prefetch (worse), 8x4 / 16x8 workgroups (worse), packed FMT table (broke exactness), memoised `locate` (0),
  64-bit division replacement (0), `restrict` (0), `kMaxPrims` 64k (0).
- Run structure: zero-copy VRAM, batching, async partial submit, CLUT versions, non-conflicting transfers, lazy host sync,
  two-phase Present (runs/s 185 -> 70, +7% FPS), no-wait `Flush/Sync` in the backend (crashed, reverted).
- Fallbacks: same-pixel feedback proof, shuffle strips, Z read-only, DATE on GPU, z-alias on GPU (fallbacks 2,000 -> ~370/s).
- CPU/threads: compiled VU1 (+5% intro), VU1 thread, GS front thread, async FINISH, lock-free vsync notify (0 FPS),
  queue depth 8/64/256 (0), raster threads (0), `GOW_XGKICK_IMMEDIATE`, compact queue (0), PRIME offload / clocks (0).

Not tried yet:
- **Dispatch size / occupancy.** Batches average ~112 prims and ~17k px union (~6% of the screen); the per-tile list
  experiment kept those batch boundaries, so it never tested more parallelism per dispatch. paraLLEl-GS bins up to 64k prims
  per pass into 32x32 tiles (u16 indices) and gets its speed from full-screen dispatches plus few barriers.
- **Barrier elision** between consecutive dispatches via page/block read-write hazard masks (paraLLEl-GS: 500+ -> 18
  barriers per frame). Ours puts a barrier after every batch (~300-400 per frame).
- **Texture cache** (unswizzle + CLUT-expand into linear images once per page version). Ablation: texture fetch is ~30% of
  kernel time.
- Lazy/deferred shading (opaque overwrite cancels pending shading): little value here, the overdraw is blended rain.
- `tex-feedback` GPU snapshot copy (EMULATOR_RESEARCH B1), double-buffered prim ring, cheaper per-prim recording.
- VU1 worker breakdown on Linux (VIF unpack vs compiled microcode vs XGKICK/arbiter) and codegen work for gameplay programs.
- Ceiling test with a null GS backend (how fast is the game with an infinitely fast renderer?).
- Present dedupe (skip compositor/copy when nothing new was drawn) and 60 Hz frame pacing.
- Subgroup ballots for tile culling (culling is only ~7%: low value), async compute queue / concurrent independent dispatches.
- PCSX2 GS on Linux/Vulkan. The Windows/DX11 bridge already exists (PCSX2_GS.md: pinned PCSX2 `2954ebe`, module recipe in
  `tools/render/pcsx2_probe/`, ABI 1 DLL, `GSExternalObserver` patch, client/queue headers in `src/`, GoW scenes rendered as a
  mirror). HW_RENDERER_PLAN.md listed it as "not evaluated"; it is in fact the most advanced alternative.

## 3. Renderer decision

| Option | 60 FPS GPU side | 1080p | Exactness | Effort / risk |
|---|---|---|---|---|
| A. Exact compute, restructured (paraLLEl-GS style: big binned dispatches, hazard masks, texture cache) | plausible (2-2.5x needed; paraLLEl-GS shows the model can be fast) | no (native + filter; SSAA later is large work) | byte-identical, keeps every test | M-L, incremental, each step gated on the replay bench |
| B. PCSX2 GS bridge (Vulkan on Linux) | yes (mature HW renderer, GoW1 rated perfect with `autoFlush`, `halfPixelOffset=5`) | yes | PCSX2-level, not exact | L: Linux/VK port of the module recipe, then authority change (null raster in the runtime, VRAM reads served by PCSX2, mirror's VU1/front-thread restriction removed). Infrastructure exists. GPLv3 is compatible per PCSX2_GS.md |
| C. Own HW renderer (HW_RENDERER_PLAN.md) | plausible | yes | approximate | XL, re-implements a subset of B with less maturity. **Shelve**; only if B is rejected |

Recommendation: run A (cheap, exact, low risk) and a gated B spike in parallel; do not start C. Whatever the renderer,
the VU1/GS-worker/EE work is required for 60 FPS, so it starts now.

## 4. Ranked candidates (gain x likelihood / effort)

| Rank | Item | Expected gain | P(success) | Effort | First experiment | Stop gate |
|---|---|---|---|---|---|---|
| 1 | Ceiling + breakdown counters | information; decides every later step | 0.95 | S | `PS2X_GS_BACKEND=null` (frontend state kept, draws dropped); `[pipe]` sub-buckets in the VU1 worker (vif_unpack, vu1_exec, xgkick, arbiter) and batch-close reason counters in the Vulkan backend | none (measurement) |
| 2 | Big binned dispatches + barrier elision (exact) | GPU 1.5-2.5x | 0.5 | M-L | replay: count batch-close reasons, then relax the union heuristic and raise the 1024-prim cap (bitmask in chunks) without other changes | replay GPU ms < -20% after first variant, byte-identical; otherwise stop |
| 3 | VU1 worker speed | VU1 1.5-2.5x (mandatory above ~26 FPS) | 0.5 | M-L | per-program time histogram from item 1; optimise the top 3 programs' generated code (flag dead-code, register caching) or the unpack path, whichever dominates | VU1 ms/frame -30% on the same scene, VU1 tests and title/gameplay screenshots identical |
| 4 | Texture cache (exact) | GPU -15-25% | 0.6 | M | decoded RGBA8 linear cache keyed by (TBP, TBW, PSM, CLUT version) with page-version invalidation, used by the kernel for nearest/bilinear | replay -10% and byte-identical |
| 5 | GS-worker CPU: `tex-feedback` GPU snapshot (B1) + cheaper recording | GS-worker -40% (needed above ~40 FPS) | 0.7 | M | B1 on the remaining strips; profile `record_ms` per prim (state hashing, record copies) | `cpudraw_ms` < 50 and `record_ms` -50% |
| 6 | Present dedupe + 60 Hz pacing | +0-5% FPS, smoother output | 0.9 | S | skip `BeginPresent` + compositor when no GS work and same DISPFB since the last Present; present with swap interval 1 | no stale/torn frames in screenshots |
| 7 | PCSX2 VK bridge spike | solves GPU side + 1080p if adopted | 0.5 | M (spike), L (product) | port `tools/render/pcsx2_probe` to Linux + GSDeviceVK, surfaceless; run its procedural fixtures; then mirror mode in the game (VU1/front threads off) and read PCSX2 GPU time per frame at 1x and 3x | spike passes if fixtures pass and PCSX2 GPU <= 6 ms/frame at 3x in the rain fight with correct screenshots |
| 8 | Own HW renderer | as B | 0.3 | XL | none | shelved |

Low value, skip unless a counter points at them: subgroup culling, async compute queue, lane-per-(prim,pixel), more
fallback proofs (fallbacks are now ~370/s), queue depth, GPU clocks.

## 5. Wave plan

Rule for every wave: one agent runs the game at a time (others use the replay bench or no game); kill only your own PID;
each task stops at its token budget and writes results to VULKAN.md/ESTADO.md + one PROGRESS_LOG line.

**Wave 0 - measure (Sonnet, ~100k).** Item 1: null GS backend, VU1-worker sub-buckets with a per-microprogram time table,
batch-close reason counters, one 90 s gameplay run each (default and null). Output: FPS ceiling with an infinitely fast
GS, VU1 ms/frame split, batch-close histogram.

**Wave 1 - exact path and CPU side (sequential game runs; code tasks may overlap in worktrees).**
- 1a Item 2, binned dispatches + barrier elision (Sonnet, 150k; Opus 60k design review only if the first gate passes and the
  hazard-mask design is needed).
- 1b Item 3, VU1 speed, guided by Wave 0 (Sonnet, 150k).
- 1c Item 4, texture cache (Sonnet, 130k), after 1a lands (same kernel file).
- 1d Item 5, GS-worker CPU (Sonnet, 120k).
- 1e Item 6, Present dedupe + pacing (Sonnet, 60k).

**Wave 2 - PCSX2 spike, parallel to Wave 1 (no game needed for step 1).**
- 2a Linux/Vulkan build of the PCSX2 GS module + procedural fixtures (Sonnet, 150k).
- 2b Mirror run in the game, GPU ms/frame at 1x/3x, screenshots (Sonnet, 80k).
- 2c Only if 2b passes: authority design (null raster, VRAM reads/FINISH/CSR via PCSX2, removing the mirror's thread
  restriction) (Opus, 120k), then implementation tasks (Sonnet, 2-3 x 150k).

**Wave 3 - decision gate (lead, ~20k).** If Wave 1 gives >= 45 FPS native in the rain fight and the owner accepts native
+ filter, continue on the exact path (pacing, remaining items). If 1080p is required or the item-2 gate fails, productise
the PCSX2 backend (`PS2X_GS_BACKEND=pcsx2`), keeping the exact Vulkan backend as reference. The own HW renderer stays shelved.

Budget: Wave 0 100k; Wave 1 ~620k; Wave 2 ~230k to the gate (+~570k if adopted); Wave 3 20k. Opus only in 1a review and 2c.
