# Environment variables

The launcher sets most of these for you. They are read by the runner.

| Variable | Effect |
|---|---|
| `GOW_ISO` / `GOW_ISO_DIRS` | ISO to use / extra folders to scan |
| `GOW_PANTALLA_COMPLETA` | `1` fullscreen, `0` windowed |
| `GOW_SCALER` | `bilinear` (default is sharp) |
| `PS2X_GS_HW_SCALE` | render scale: `2` (default), `2.41` (1080 lines), `3`, `4` |
| `GOW_FPS` | `1` shows the FPS counter from the start |
| `GOW_FPS_LOW_SECS` | window for the 1% low (default 300 s) |
| `GOW_GS_HW_SEAMFEEDBACK` | `1` restores the old strip-seam handling for sprites that sample a render target (debug: the grid lines in the haze passes come back at render scale above 1) |
| `GOW_GS_HW_ZSUB` | offset of the high-resolution depth read for the fog/DOF strips (default `0.375`); `off` restores the old per-texel read (debug: the pale halo around characters and the grid lines in fog come back) |
| `GOW_GS_HW_SELFCOPY` | `0` makes a pass that samples the render target it draws into read the target itself again instead of a copy taken before the draw (debug) |
| `GOW_GS_HW_RTCLAMPEXT` | `0` restores the old UV clamp of sprites that copy a render target (debug: a flat one-pixel plateau at every strip border at render scale above 1) |
| `GOW_AUDIO` | `0` mutes |
| `GOW_SKIP_FMV` | `1` skips movies |
| `GOW_CHEAT` | comma list: `god`, `noenemies` |
| `GOW_PAD_MAPPINGS` / `GOW_PAD_DIAG` | pad mapping file / log what the game reads |
| `GOW_PERF_DIAG` | `1` prints a per-window performance profile |
| `GOW_VU1_MICROCODIGO` / `GOW_IOP_MODULOS` | folders with the captured VU1 microcode / IOP modules (build time) |
| `GOW_VU1_CAPTURA` | folder where a run saves VU1 microprograms |
| `GOW_HOST_SHOT` / `GOW_GS_HW_DISPDUMP` | write the window picture / the internal render target at a given frame (see [capturing frames](../reference/controls-and-menu-tests.md)) |
| `GOW_PAD_GUION` / `GOW_PAD_TEST` / `GOW_PAD_SOLO_GUION` | scripted pad (see [scripted pad](../reference/controls-and-menu-tests.md)) |
| `GOW_WARP` | jump to a zone for capture and tests (`ZONE;ZONE`) |
| `GOW_THREAD_WATCH` | seconds between thread dumps when hunting a freeze |

!!! note
    Names keep their original Spanish form (`PANTALLA_COMPLETA`, `MICROCODIGO`) so existing settings keep working.
