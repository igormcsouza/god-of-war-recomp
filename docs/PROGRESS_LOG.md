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

1. Intro movie (MPEG/IPU) end-of-stream corrupts the GS output (garbage polygons, 0 FPS). `GOW_SKIP_FMV=1` avoids it.
2. CPU fallbacks for `tex-feedback` / `z-alias` cost ~400 ms/s in gameplay.
3. EE thread blocks on a mutex held by the GIF thread (GS queue backpressure).
4. Sound is choppy while the game runs below real time (expected; `GOW_AUDIO=0` or launcher mute).

## Decisions taken by the lead (defaults, review these)

(none yet)

## Log
