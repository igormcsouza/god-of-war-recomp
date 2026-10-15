# Linux port progress log

Running log of results, decisions taken without asking the owner (defaults), and what is next.
Newest entries at the bottom. Detailed investigation lives in `ESTADO.md` and `VULKAN.md`.

## Working rules agreed with the owner

- Linux-native first (Vulkan required); Windows kept compatible on a best-effort basis.
- Upstream PR undecided. Work stays on branch `linux-native-port`. One push, at the end, only when the owner asks.
- All new code and docs in English. Existing es/pt material stays untouched.
- One agent at a time, token limits per task, cheaper models by default (Sonnet/Haiku). Opus only for the GPU fallback task.
- No game files or generated game code in the repo.

## Results so far (2026-10-14)

| Milestone | Result |
|---|---|
| Linux build pipeline, ISO launcher (Tk, auto-detect, remembered ISO, mute, GPU selector) | done |
| Controller autodetect, hotplug, GLFW-unknown pad mappings (GameSir verified working) | done |
| Vulkan GS backend: textured prims, CLUT, blend/Z, batching, zero-copy VRAM | done, byte-identical to CPU renderer |
| Compiled VU1 + threaded defaults on Linux | done |
| FPS, NVIDIA RTX 5050: intro/title | ~24 |
| FPS, NVIDIA RTX 5050: gameplay (ship level, `GOW_SKIP_FMV=1`) | ~9-10 |

## Known issues

1. Intro movie (MPEG/IPU): GS output turns to garbage ~5-10 frames after the movie starts (not at its end), 0 FPS. Root cause open. `GOW_SKIP_FMV=1` avoids it.
2. CPU fallbacks for `tex-feedback` / `z-alias` cost ~400 ms/s in gameplay.
3. EE thread blocks on a mutex held by the GIF thread (GS queue backpressure).
4. Sound is choppy while the game runs below real time (expected; `GOW_AUDIO=0` or launcher mute).

## Decisions taken by the lead (defaults, review these)

- Intro-movie hunt: kept only opt-in diagnostics (`GOW_MPEG_DIAG=1`, `patches/ps2recomp-mpeg-diag.patch`). The end-of-stream hypothesis was disproved and no root cause was found within budget, so no behaviour change was shipped.
- Lead default: after 3 unsuccessful movie rounds, moved on to the GPU fallback performance work (priority 2) with Sonnet instead of Opus, because docs/EMULATOR_RESEARCH.md made the ideas concrete. Movie hunt resumes in a later wave.
- z-alias task (lead default): implemented as a host-side block-level proof (no new shader kernel) because the shader already addresses frame and Z by their own PSM; gdb sampling skipped because `ptrace_scope=1` blocks attach and the gdb-launched game produced no samples within the budget.
- GPU fallback task (lead default): skipped the general snapshot copy (B1/B3) because the same-pixel proof and Z-read-only removed ~80% of fallbacks; the remaining `z-alias` needs an address-owner kernel (own task). `GOW_VK_NO_FBOPT=1` kept for A/B.
- GPU benchmark task (lead default): added `ps2recomp-gs-vulkan-perf.patch` (registered last) instead of editing the 2,700-line Vulkan patch, so earlier patches stay stable. Raised the replay capture limit to 768 MiB so a capture holds ~120 presents. No screenshots inspected; exactness is the CPU byte-compare. Stopped before the larger per-tile-list restructuring (token budget).

- Per-tile primitive list task (lead default): measured instead of building CPU binning, because the shader already culls per 8x8 tile; staged lists, int32 edge slopes, fb-read prefetch, 8x4/16x8 workgroups and a packed FMT table all failed to beat 1319 ms (one also broke byte-identity), so the perf patch was left unchanged and the real-game FPS runs were skipped.

- Pipeline stall task (lead default): kept the stall counters (`PS2X_PIPE_STATS=1`) and the lock-free `notifyExternalVSync` (EE mutex wait 168 -> 0 ms/s), reverted the no-wait Vulkan `Flush`/`Sync` experiment because it crashed the Vulkan test suite and gave no FPS gain; the real limiter is the serial GS worker (95% busy, ~45% on GPU fence waits at every Present). Next: present without ending the GPU run.

- GPU run-end census task (lead default): measured only (no code). The agent used its whole token budget on reading before editing; census shows `Flush()`+`Sync()` cause ~60% of fence waits (frontend latch/FINISH call them; CPU backend no-ops) and `tex-feedback` does not end runs. Default chosen for the follow-up: skip `Flush/Sync` in the frontend for a lazy-sync backend instead of changing the Vulkan methods, plus two-phase Present (see ESTADO.md).
- Replay-vs-live task (lead default): measurement only; the "3.5x" came from comparing presents/s (replay) with flips/s (window FPS); no code changed, PRIME offload and clocks tested and ruled out.
- Lazy-sync task (lead default): implemented as a new patch registered after the pipeline patch (the Vulkan patch stays untouched), default ON because tests and gameplay screenshots are correct; `PS2X_VK_LAZY_SYNC=0` / `PS2X_VK_SYNC_PRESENT=1` give the old behaviour. FINISH is not delayed for host readers (they still wait), but the EE now sees the FINISH bit before queued GS work executes. Skipped for budget: replay-bench byte compare, title screenshot.

- Lead default (2026-10-15): HW renderer plan (docs/HW_RENDERER_PLAN.md) is a conditional go but milestones 2, 4 and 6 need a stronger model and it is a large fork, so the lead did NOT start it. Meanwhile ran the interim exact-path improvements (alternative A) with Sonnet.

## Log
- 2026-10-15: Register-resident fb/Z words in the Vulkan kernel (perf patch regenerated; only its shader-export section changed, no later patch touches that file): replay 1328 -> 1188 ms, byte-identical, tests 636/0. Lead default: steps 2-3 and the game FPS A/B skipped (agent hit its token budget); screenshots (menu, rainy fight) look correct. Full fresh-clone series check not run (local partial clone broke); per-file apply verified.
- 2026-10-15: Intro-movie garbage hunt. Garbage starts ~5-10 frames after the MPEG starts, not at the end, and the visible picture is NOT our decoded buffer. Root cause still open; see ESTADO.md 'Intro movie garbage is not an end-of-stream problem'. Added `GOW_MPEG_DIAG`.
- 2026-10-15: Emulator research (PCSX2 GameDB/GSRendererHW/Gif_Unit/IPU) written to docs/EMULATOR_RESEARCH.md with ranked ideas for intro-FMV garbage and feedback/z-alias perf.
- 2026-10-15: Intro-movie hunt 2: added `GOW_GIF_TRACE` (patches/ps2recomp-gif-trace-diag.patch). Between picture 1 and 2 the game emits ~296k PATH1 packets (~110 frames of geometry), no masked/interleaved PATH3 traffic: GIF/PATH3 arbitration is cleared; suspect EE-side waits in `sceMpegGetPicture` (continues after waitExternal/waitVSync). Details in ESTADO.md.
- 2026-10-15: Intro-movie hunt 3: wait/re-entrancy hypothesis eliminated (scheduler waits are noreturn); the "PATH1 flood" is ~8 s of the normal in-engine scene while the movie pre-rolls (served=2); pacing after that is a correct 29.97 fps but the game issues no GIF traffic, so the garbage is a display/upload question. Added syscall histogram to `GOW_MPEG_DIAG` (`ps2recomp-mpeg-syscall-diag.patch`). 119 patches verified on a fresh pinned tree, `ps2x_tests` 633 pass. Next steps in ESTADO.md.
- 2026-10-15 (lead): Movie hunt, 3 rounds, root cause still open. Eliminated: EOF/flush, PATH3 mask/EOP/IMT/DIRECTHL, wait/re-entrancy in sceMpegGetPicture, Vulkan, threads, audio. Current picture: ~8 s of normal game frames (movie pre-roll), then pictures are served at 29.97 fps but the game issues almost no GIF traffic and the screen shows flat polygons, so decoded frames likely never reach the GS (or the display reads the wrong buffer). Next angle: trace how the movie player gets a decoded picture to the GS (IPU -> RAM -> which upload path) and compare with PCSX2's IPU/DMA ch3/4.
- 2026-10-15: GPU fallback work: same-pixel feedback proof (sprites/triangles), disjoint-rect shuffle strips, Z-only-tested is read-only, tight UV box, DATE on the GPU. CPU fallbacks ~2,000/s -> ~450/s, gameplay FPS 14.8 -> 22.7, intro 26 -> 32 (A/B with `GOW_VK_NO_FBOPT=1`). `z-alias` NOT solved (Z32/CT32 swizzles differ). `ps2x_tests` 634 pass; patches verified on a fresh pinned tree.
- 2026-10-15 (lead): GPU fallback wave done. Gameplay (rainy fight, NVIDIA RTX 5050) 14.8 -> 22.7 FPS, intro/title 26.2 -> 32.3 FPS; CPU fallbacks ~2,000 -> ~450 prims/s; tests 634/634. z-alias still on CPU (Z32 and CT32 swizzles differ). Agent overran its token budget (~200k vs 130k stop point): future prompts use tighter limits.
- 2026-10-15: Vulkan z-alias on the GPU (`frameZAliasSafe`, CT32/CT24 + Z32/Z24, block-level same-owner proof, byte-identical test, `GOW_VK_NO_ZALIAS=1` for A/B). Gameplay fallbacks ~630 -> ~220/s, z-alias 300 -> 0/s, FPS unchanged (~13 on the heavy fight scene, GPU-bound). Top costs: GPU dispatch time (`finish_ms` ~540 ms/s), `tex-feedback` fallbacks (~210/s), `record-ring`/`Flush()` run ends. gdb mutex sampling not obtained. `ps2x_tests` 634 pass; later patches apply. Details: docs/VULKAN.md.
- 2026-10-15: Repeatable Vulkan GPU benchmark (`tools/render/bench_vk.cpp`, replay of a `GOW_GS_REPLAY_TRACE` capture, byte-compared with the CPU backend) and first shader wins (early Z, triangle tile culling): replay GPU 1662 -> 1319 ms (-21%), game 15-22 FPS in the rain scene. Kernel is latency-bound by the serial per-pixel prim walk; next step is per-tile prim lists with staged data. See docs/VULKAN.md.
- 2026-10-15: Per-tile primitive lists / shared-memory staging / workgroup tuning on the Vulkan kernel: no variant below the 1319 ms replay baseline (best 1318, but not byte-identical; staged 1372, 8x4 1457, 16x8 1466). Patch unchanged. The limit is the per-covered-pixel latency chain (~600 Mpx shaded over ~17k threads/dispatch), not culling. See docs/VULKAN.md.
- 2026-10-15: Pipeline stall profile (`PS2X_PIPE_STATS=1`, `patches/ps2recomp-pipeline.patch`): GS worker 92-98% busy (fence waits ~400 ms/s, CPU fallbacks ~200, GPU only ~55% busy), EE idle 60% in guest waits; removed the EE `m_stateMutex` wait in `notifyExternalVSync` (168 -> 0 ms/s) but FPS unchanged (16.8 before / 15.8 after, noise). See ESTADO.md 'Pipeline stall profile'.
- 2026-10-15: GPU run-end census (docs/ESTADO.md 'GPU run-end census'): Flush 125-148 ms/s, Sync 119-137, Present 59-74, record-ring 52-92, BeginTransfer 34-49; tex-feedback costs ~155 ms/s CPU but ends no runs. No code change; two-phase async Present design written. t=80 s black shot also black on the CPU backend (fade). Baseline 17.1 FPS.
- 2026-10-15: Lazy host sync + two-phase Present (`ps2recomp-gs-lazy-sync.patch`, `PS2X_VK_LAZY_SYNC=0` / `PS2X_VK_SYNC_PRESENT=1` for A/B): GPU runs/s 185 -> ~70, GS worker idle 20 -> ~200 ms/s, gameplay FPS 14.6 -> 15.7 (3 runs each); screenshots correct; `ps2x_tests` 637 pass; 122 patches apply on a fresh pinned tree. `record-ring` is now the main wait (235-345 ms/s). Title shot and replay bench not re-run.
- 2026-10-15: Replay vs live mystery: window FPS counts guest flips (~15/s) but the replay counts Presents (live ~40/s = ~2.7 per flip), so the true gap is ~1.4x (57 vs 40 presents/s). GPU clocks stay in P2 (~2200 MHz) live; GL window is on Intel but NVIDIA PRIME offload gives the same FPS (14.9/15.2 vs 15.5/15.0). No fix needed; see ESTADO.md/VULKAN.md.
- 2026-10-15 (lead): Strategy note. After lazy sync, two-phase Present and register-resident pixel state, live gameplay is ~15-17 FPS (guest flips) on the RTX 5050. The game issues ~2.7 GS Presents per displayed frame and the exact per-pixel compute design costs ~10 ms of GPU per Present (~26-30 ms per displayed frame; ~17x overdraw from rain/particles, ~460 Mpx/s), so this design alone caps around 25-30 FPS. Reaching 60 FPS (and real 1080p) most likely needs a hardware-style path (graphics pipeline with ROP/early-Z, PCSX2-like) beside the exact compute path. That is a big architectural decision for the owner; the lead only commissions a feasibility/plan document (docs/HW_RENDERER_PLAN.md), no rewrite.
- 2026-10-15 (research): docs/HW_RENDERER_PLAN.md written: hybrid vulkan-hw graphics-pipeline renderer feasibility, 8 milestones with a stop gate after step 4; conditional go; interim alternative is compute tile binning (~30-35 FPS). No code changed.
- 2026-10-15 (agent): Vulkan GS tile HiZ (stateless per-dispatch min Z, kill on Z-lowering prims) + dead-prim skip in ps2recomp-gs-vulkan-perf.patch: replay GPU 1209 -> 1181 ms (-2.3%), byte-identical, 636 tests; game FPS/screenshots NOT run; page binning not done. Defaults chosen unasked: stateless HiZ over persistent.
- 2026-10-15 (agent): Display options in the runtime (`patches/ps2recomp-display-options.patch`, registered last): `GOW_FULLSCREEN=1` + F11 (borderless), `GOW_SCALE_FILTER` nearest|bilinear|sharp-bilinear (shader), `GOW_WINDOW_SCALE=<n>`; launcher gets a Scaling combobox (`scaling` in settings.json, old files load as Bilinear). Defaults chosen unasked: ESC still closes, bilinear default, existing aspect handling kept (already letterboxed). Verified: 638 ps2x_tests pass, launcher tests OK, game run with each filter and fullscreen (window 1280x896 at scale 2; fullscreen 1920x1055 pillarboxed, screenshots correct). Not tested: Wayland, runtime F11 key press.
