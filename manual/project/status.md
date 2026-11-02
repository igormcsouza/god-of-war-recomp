# Status

## Works (verified on Linux)

Menus, new game, combat, audio, movies with sound, save and load, controller and keyboard, the FPS overlay, fullscreen
toggle, render scales, and the released AppImage's first-run setup from a clean home.

## Not verified or open

| Item | Notes |
|---|---|
| Full playthrough | not done |
| Other game pads | only a GameSir dongle was tested |
| Windows | not supported: this project is Linux only |
| Orb-pickup freeze | seen once, did not come back in over 10 minutes of play; `GOW_THREAD_WATCH=5` is the diagnostic if it does |
| Microcode capture coverage | varies per run (1178-1797 programs); accumulating or longer capture planned |
| FPS dips (44-50) | EE and guest wait, not analysed |
| PAL languages | on hold |

## Library-level map

The per-library and per-component status map of the Sony SDK functions is generated from
`manual/status-map/datos.toml`: see the [status map](../status-map/detalle.en.md).

## Research log

The detailed investigation record (about 8,000 lines) is in the
[research log](../reference/research-log.md).
