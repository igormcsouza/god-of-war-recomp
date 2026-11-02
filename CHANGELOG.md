# Changelog

## Unreleased

- Fix: grid lines in the desert haze at render scale above 1 (strip seams opened on sprites that sample a render target).
- Fix: faint grid lines and a pale outline around characters, strongest in fog, at night and with particles. They came from
  the fog/depth-of-field pass: its Z-buffer read is now done at host resolution, a pass that samples the target it draws
  into reads a copy taken before the draw, and the copy strips' UV clamp reaches the last host pixel (off switches:
  `GOW_GS_HW_ZSUB=off`, `GOW_GS_HW_SELFCOPY=0`, `GOW_GS_HW_RTCLAMPEXT=0`).
- Cleanup: the project is Linux only and English only. Removed the Windows build scripts, the PCSX2 research tooling and
  tests, the superseded patch archive (`patches/anteriores/`) and the pages of the manual that described them (they stay
  in git history). The patch order is now `patches/series` and the PS2Recomp commit is `patches/PS2RECOMP_COMMIT`.
- Docs: README rewritten for Linux, new screenshots page with how to take your own, scripted pad and reproducible scene
  recipe.
- Performance: a GIF packet with nothing queued reaches the GS in place instead of being copied into the arbiter queue (from Waffle565 `615b046`). About +0.75 FPS on the 4-zone run (see the research log); small but consistent.

- The first-run setup installs the missing build packages itself (apt, dnf, pacman or zypper; the system asks for your
  password) instead of only printing the command. It also checks the GL/X11/ALSA headers, not just the tools.
- Setup time is described as "30+ minutes, depends on your CPU" (the earlier "30-60" was an estimate).

## 0.1.1

- Fix: the first-run setup crashed on a fresh machine (its working folder did not exist yet). 0.1.0 is superseded.

## 0.1.0

First release of this Linux-first fork.

- Runtime base: Waffle565's native runtime (OpenGL render-target GS at 2x, native VU1 and IOP, native SPU2/DMA),
  replacing the earlier Vulkan compute GS. About 55 FPS on average in gameplay on an RTX 5050 laptop (about 21 before),
  60 in menus and movies.
- Launcher: start fullscreen or windowed, FPS counter, render scale (1080p default, 2x, 3x, 4x), scaler, mute, skip
  movies, debug cheats.
- Pads without an SDL mapping (for example a GameSir dongle) work with a generic Xbox-like layout; `GOW_PAD_DIAG=1`.
- FPS counter in English, with the 1% low of the last 5 minutes of gameplay.
- Unattended capture of the VU1 microcode and IOP modules (`tools/linux/capture_microcode.py`).
- AppImage builder: builds the runtime from your own ISO on first run, then starts the launcher from the cache.
  The release never contains game data or recompiled game code.
