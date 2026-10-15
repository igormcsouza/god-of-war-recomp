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

## Log
- 2026-10-15: Intro-movie garbage hunt. Garbage starts ~5-10 frames after the MPEG starts, not at the end, and the visible picture is NOT our decoded buffer. Root cause still open; see ESTADO.md 'Intro movie garbage is not an end-of-stream problem'. Added `GOW_MPEG_DIAG`.
- 2026-10-15: Emulator research (PCSX2 GameDB/GSRendererHW/Gif_Unit/IPU) written to docs/EMULATOR_RESEARCH.md with ranked ideas for intro-FMV garbage and feedback/z-alias perf.
- 2026-10-15: Intro-movie hunt 2: added `GOW_GIF_TRACE` (patches/ps2recomp-gif-trace-diag.patch). Between picture 1 and 2 the game emits ~296k PATH1 packets (~110 frames of geometry), no masked/interleaved PATH3 traffic: GIF/PATH3 arbitration is cleared; suspect EE-side waits in `sceMpegGetPicture` (continues after waitExternal/waitVSync). Details in ESTADO.md.
