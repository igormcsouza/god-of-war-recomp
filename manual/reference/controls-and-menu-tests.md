# Scripted pad, diagnostics and reproducible scenes

The keyboard and pad mapping is in [Controls](../usage/controls.md). This page covers the display options, the FPS
meter, and how to drive the game without touching the pad so a scene can be reproduced and measured.

## Display and debugger

The game starts in **borderless full screen**: the window covers the whole monitor. **F11** toggles between full screen and windowed. `GOW_PANTALLA_COMPLETA=0` starts windowed, as does
requesting a size with `GOW_WINDOW=<width>x<height>`;
`GOW_PANTALLA_COMPLETA=1` forces full screen even if a size is requested. Alt+Enter is not used because Enter is Start.

**Widescreen.** The game always runs in 16:9 with its own widescreen mode, which crops the image at the top and bottom.
`GOW_PANORAMICO=ampliado` enables the extended widescreen mode: the camera recovers the 4:3 height and widens the view to
the sides, an idea by nemesis2000 and CRASHARKI. More of the scene is visible, so it draws
more: in the ship combat the median dropped from 59.9 to 54.9 game frames per second (2026-10-18).

## 120 Hz

`GOW_HZ=120` (experimental) generates the EE VBlank every 8.34 ms instead of every 16.68 ms: the game loop, which
waits for one VBlank per frame, can run up to 120 iterations per second. The game's time step (0x17D778) becomes
the elapsed guest time, clamped to [1/120, 4/60] s, so the speed does not change. The IOP, the sound
and the movie clock stay on NTSC fields, and the host presentation rises to 120 images per second (without
vertical sync: on a 60 Hz monitor you see tearing). In the ship combat the game gives 65-73
frames per second on a Ryzen with an RX 5700 XT; in light scenes, 120. Not thoroughly reviewed: physics, in-engine cutscenes
and all levels.

The **runtime debugger** ("Runtime Debugger") no longer opens at startup: **F1** shows or hides it.

## FPS meter

**F2** shows or hides, at the top left, the game's frames per second (entries to `vid::Flip`, the game's frame
function; `GOW_PERF_FRAME_PC` changes it) and the window refreshes. Green from 57, yellow from 45 to 57,
red below that. `GOW_FPS=1` shows it from the start. While it is visible, every second a line is written to the log
(the runner's stderr): `[gow-fps] t=<s> juego=<fps> min=<minimum in 0.25 s windows> pantalla=<Hz>`, to
locate afterwards where the stutters happened.

Since 2026-10-16 it also shows the **images** per second that actually reach the window (`imagenes=` and
`min_imagenes=` in the log); the color follows the worse of the two figures. If the game runs at 60 and the images do not, the
stutter comes from the presentation, not from the game. `PS2X_GS_PRESENT_LATEST=1` goes back to always showing the most recent frame
(previous behavior, with images lost when the game's pace is irregular).

## Scripted pad

`GOW_PAD_GUION` is a comma-separated list of `second:action[:duration]` (0.7 s presses when the duration is omitted).
Buttons: `start`, `select`, `arriba` (up), `abajo` (down), `izquierda` (left), `derecha` (right), `x`, `circulo`,
`cuadrado`, `triangulo`, `l1`, `r1`, `l2`, `r2`. For example, to open Load in the menu:

```sh
GOW_PAD_TEST=1 GOW_PAD_GUION='5:start,13:abajo,20:x' python3 tools/linux/gow_launcher.py --no-gui
```

`mover_izquierda`, `mover_derecha`, `mover_arriba` and `mover_abajo` drive the corresponding axis of the **left
stick** to 0/255, keeping the other axis. Example: `180:mover_izquierda:3,181:cuadrado` holds the stick for three
seconds and presses attack at 181 s. The duration must be positive and finite; invalid entries are ignored. When two
actions on the same axis coincide, the last active one in the list wins. When they finish, each read returns to the
pad's base state, or to neutral with `GOW_PAD_SOLO_GUION=1`, which also ignores the real pad and keyboard.

`GOW_PAD_GUION_DIAG=1`, together with `GOW_PAD_TEST=1`, logs up to 128 changes of the packet returned by libpad2 under
`[gow-pad2:guion]`. It shows that the script is delivered, **not** that the game accepted it. Times are host times and
do not align animations between runs. `tests/pad_script_test.cpp` checks buttons, the stick separate from the D-pad,
pressures, duration, overlap, end of window and invalid entries.

### A reproducible scene (no hands)

This reaches the rainy deck fight of the first level and then stands still, which makes it a good scene for comparing
two builds or settings (the picture is steady after about 35 s):

```sh
GOW_PAD_TEST=1 GOW_PAD_TEST_NO_CAPTURE=1 GOW_PAD_SOLO_GUION=1 GOW_SKIP_FMV=1 \
GOW_PAD_GUION='8:x,16:x,24:x,32:x,40:x,48:x' python3 tools/linux/gow_launcher.py --no-gui --mute
```

The main menu accepts buttons without pressing Start, and how long it takes to appear depends on the machine's load.
With a fast boot, the Start of `5:start` already lands in the menu and picks New Game.

## Capturing frames

- `import -window <id>` (ImageMagick, X11 or XWayland) grabs the game window losslessly; find the id with
  `xwininfo -root -tree | grep PS2-Recomp`. This is the picture exactly as you see it.
- `GOW_HOST_SHOT=<n>` writes the window's back buffer at host frame `n` to `host_shot.png` in the working directory.
- `GOW_GS_HW_DISPDUMP=<n>` writes the whole internal render target (before the scaling to the window) at the `n`-th
  present to `gs_hw_disp_<fbp>_<w>x<h>.ppm`. At render scale 4 this is 2048 pixels wide.
- `GOW_GS_HW_DUMPAT=<seconds>` prints the list of draws of three presents (state, size, texture block), and
  `GOW_GS_HW_SKIPTBP=<hex>` skips every draw textured from that block, to find which pass produces an artefact.

Faint artefacts are easier to see with a high-pass view: subtract a Gaussian blur from the frame and multiply the
difference by about 14 (`convert in.png -blur 0x5 ...` or a few lines of Pillow). See the
[research log](research-log.md) for how this found the fog pass behind the grid lines.

## Path diagnostic

`GOW_PATH_DIAG=1` logs `[gow-path]` and saves `gow_path_failure.bin` next to the executable if an attempt is made to
attach a NULL node. The dump contains the game's RAM and must not be published.
