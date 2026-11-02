# How it evolved

A short history of the Linux port, from the first commit to the first playable release.

| Date | Milestone |
|---|---|
| 2026-10-05 | First commit: *God of War* recompiled with PS2Recomp, Windows first ([KIexster](https://github.com/KIexster/god-of-war-recomp)) |
| 2026-10-09 to 10-15 | Research on Windows: native VU1, native IOP, exact game speed, controls, FMV and audio work |
| 2026-10-14 | **Linux starts**: build pipeline, ISO launcher, gamepad autodetect, Tk settings window, CI steps |
| 2026-10-14 | A **Vulkan GS renderer** is built in three phases (compute prims, textured prims, batching), with the compiled VU1 and threaded GS on by default. Result: about **20-30 FPS** |
| 2026-10-15 | Debug cheats (god mode, no enemies), mute option |
| 2026-10-31 | **Decision: adopt Waffle565's native runtime** (OpenGL render-target GS, native VU1 and IOP, native SPU2/DMA) in place of our Vulkan renderer. Same controls, same movies, same cheats; average moves from ~21 to **~55 FPS**. ([#22](https://github.com/igormcsouza/god-of-war-recomp/pull/22)) |
| 2026-11-01 | English FPS overlay, fullscreen toggle, render scale (1080p default), 1% low overlay |
| 2026-11-01 | **AppImage builder** and automated release on a version tag; **v0.1.0**, then **v0.1.1** (fixes a first-run crash) |
| 2026-11-01 | Setup installs missing build packages itself; English-only READMEs; this manual |
| 2026-11-02 | **Grid lines and the halo around characters fixed** (desert haze, then the fog/DOF pass: high-resolution depth read, self-copy for feedback passes, extended copy clamp); repository cleanup: Linux and English only |

[`v0.0.1`](https://github.com/igormcsouza/god-of-war-recomp/releases/tag/v0.0.1) is a source snapshot of the
Vulkan era, kept for history.

## Why the Vulkan renderer was dropped

The Vulkan GS was a real step up from the CPU renderer, but the frame was still limited by VU1, GS and upload work (about
21 FPS on `main`). Waffle565's runtime removes that bottleneck by compiling the VU1 and IOP ahead of time and drawing
through render targets, so it was adopted wholesale and our launcher, pad mapping, cheats and overlay were carried over.
The Vulkan-era history is preserved on the `adopt/upstream-runtime` branch.

!!! note "A correction worth keeping"
    An early "GPU choice" A/B test looked like a win but was a silent fallback to the CPU renderer: forcing NVIDIA
    offload variables breaks the GS EGL context. Always confirm `[gs-hw] render-target renderer ready` in the log before
    trusting a measurement.

## What is next

See [Status](status.md): other pads, longer microcode capture and the 44-50 FPS dips.
