# Status

## Works (verified on Linux)

Menus, new game, combat, audio, movies with sound, save and load, controller and keyboard, the FPS overlay, fullscreen
toggle, render scales, and the released AppImage's first-run setup from a clean home.

## Not verified or open

| Item | Notes |
|---|---|
| Full playthrough | not done |
| Other game pads | only a GameSir dongle was tested |
| Windows with this runtime | the Windows scripts exist but were not run with the adopted runtime |
| Orb-pickup freeze | seen once, did not come back in over 10 minutes of play; `GOW_THREAD_WATCH=5` is the diagnostic if it does |
| Microcode capture coverage | varies per run (1178-1797 programs); accumulating or longer capture planned |
| FPS dips (44-50) | EE and guest wait, not analysed |
| PAL languages | on hold |

## Library-level map

The per-library and per-component status map of the Sony SDK functions is generated from `docs/estado/datos.toml`:
[`detalle.en.md`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/docs/estado/detalle.en.md).

## Research log

The detailed investigation record is upstream's `docs/ESTADO.md` (Spanish, about 7,900 lines), kept as the source for
this manual. See the [upstream docs map](upstream-map.md) for what has been ported.
