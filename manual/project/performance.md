# Performance

Measured on an RTX 5050 laptop (hybrid graphics: window on the Intel GPU, GS on NVIDIA, frames cross through RAM).

| Build | Result |
|---|---|
| Vulkan-era `main` | about 21 FPS |
| Adopted native runtime | average 53-59 FPS in ship zones; 56.1 average over 9.5 minutes of real play (67% of seconds at 57 or more) |
| Released v0.1.1 AppImage, 4-zone scripted run | average 59.0, minimum 49.2, 85% of seconds at 57 or more |

## Render scale

| Scale | FPS (ship zones) |
|---|---|
| 2x (runtime default) | 56.0 |
| 1080p (2.41, launcher default) | 56.0 |
| 3x | 55.2 |
| 4x | 53.9 |

## What limits it

- **VU1 microcode capture.** Without it the VU1 is interpreted (about 10 FPS). The capture covers 1178-1797 microprograms
  depending on the run; programs missed run on the slow path (about 1.2 s of VU1 time per 5 s window in one test, with no
  visible FPS cost).
- **Dips to 44-50 FPS** in heavy scenes, from EE and guest wait. Not yet analysed.
- **Cross-GPU readback** on hybrid laptops: its cost is not measured in isolation.

## Measuring yourself

`GOW_PERF_DIAG=1` prints a per-window profile (`vu_ms`, GS and upload time). Turn on the FPS counter to see the
average and the 1% low.
