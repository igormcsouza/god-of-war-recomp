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
- GPU fallback task (lead default): skipped the general snapshot copy (B1/B3) because the same-pixel proof and Z-read-only removed ~80% of fallbacks; the remaining `z-alias` needs an address-owner kernel (own task). `GOW_VK_NO_FBOPT=1` kept for A/B.

## Log
- 2026-10-15: Intro-movie garbage hunt. Garbage starts ~5-10 frames after the MPEG starts, not at the end, and the visible picture is NOT our decoded buffer. Root cause still open; see ESTADO.md 'Intro movie garbage is not an end-of-stream problem'. Added `GOW_MPEG_DIAG`.
- 2026-10-15: Emulator research (PCSX2 GameDB/GSRendererHW/Gif_Unit/IPU) written to docs/EMULATOR_RESEARCH.md with ranked ideas for intro-FMV garbage and feedback/z-alias perf.
- 2026-10-15: Intro-movie hunt 2: added `GOW_GIF_TRACE` (patches/ps2recomp-gif-trace-diag.patch). Between picture 1 and 2 the game emits ~296k PATH1 packets (~110 frames of geometry), no masked/interleaved PATH3 traffic: GIF/PATH3 arbitration is cleared; suspect EE-side waits in `sceMpegGetPicture` (continues after waitExternal/waitVSync). Details in ESTADO.md.
- 2026-10-15: Intro-movie hunt 3: wait/re-entrancy hypothesis eliminated (scheduler waits are noreturn); the "PATH1 flood" is ~8 s of the normal in-engine scene while the movie pre-rolls (served=2); pacing after that is a correct 29.97 fps but the game issues no GIF traffic, so the garbage is a display/upload question. Added syscall histogram to `GOW_MPEG_DIAG` (`ps2recomp-mpeg-syscall-diag.patch`). 119 patches verified on a fresh pinned tree, `ps2x_tests` 633 pass. Next steps in ESTADO.md.
- 2026-10-15 (lead): Movie hunt, 3 rounds, root cause still open. Eliminated: EOF/flush, PATH3 mask/EOP/IMT/DIRECTHL, wait/re-entrancy in sceMpegGetPicture, Vulkan, threads, audio. Current picture: ~8 s of normal game frames (movie pre-roll), then pictures are served at 29.97 fps but the game issues almost no GIF traffic and the screen shows flat polygons, so decoded frames likely never reach the GS (or the display reads the wrong buffer). Next angle: trace how the movie player gets a decoded picture to the GS (IPU -> RAM -> which upload path) and compare with PCSX2's IPU/DMA ch3/4.
- 2026-10-15: GPU fallback work: same-pixel feedback proof (sprites/triangles), disjoint-rect shuffle strips, Z-only-tested is read-only, tight UV box, DATE on the GPU. CPU fallbacks ~2,000/s -> ~450/s, gameplay FPS 14.8 -> 22.7, intro 26 -> 32 (A/B with `GOW_VK_NO_FBOPT=1`). `z-alias` NOT solved (Z32/CT32 swizzles differ). `ps2x_tests` 634 pass; patches verified on a fresh pinned tree.
- 2026-10-15 (lead): GPU fallback wave done. Gameplay (rainy fight, NVIDIA RTX 5050) 14.8 -> 22.7 FPS, intro/title 26.2 -> 32.3 FPS; CPU fallbacks ~2,000 -> ~450 prims/s; tests 634/634. z-alias still on CPU (Z32 and CT32 swizzles differ). Agent overran its token budget (~200k vs 130k stop point): future prompts use tighter limits.
