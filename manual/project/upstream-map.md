# Upstream docs map

Upstream's `docs/` folder is a Spanish research log. This manual is meant to replace it over time. Until a page is ported
and checked here, the upstream file stays the source of truth.

| Upstream file (Spanish) | Topic | Here |
|---|---|---|
| `ARQUITECTURA.md` | pipeline, overrides, runtime base | condensed in [Architecture](architecture.md) |
| `CONTROLES.md` | pad, keyboard, menu tests, FPS meter | [Controls](../usage/controls.md) (core only; 120 Hz and widescreen not ported) |
| `LINUX_APPIMAGE.md`, `LINUX_LAUNCHER.md`, `LINUX_COMPILACION.md`, `LINUX_ISO.md` | Linux install and use (already English) | ported to [Install](../install/appimage.md) and [Launcher](../usage/launcher.md) |
| `ESTADO.md` | investigation log, about 7,900 lines | summarised in [Status](status.md) and [How it evolved](evolution.md) |
| `RENDIMIENTO*.md` | performance research | summarised in [Performance](performance.md) |
| `RENDERIZADO.md`, `PCSX2_GS.md`, `RENDER_*.md`, `FEEDBACK_BILINEAL_MINIMO.md`, `COMPARACION_PCSX2.md` | GS and rendering | not ported |
| `FMV_Y_AUDIO.md`, `MEMORY_CARD.md` | movies, audio, saves | not ported |
| `TRANSICION_COMPARTIDA.md`, `REVISION_*.md`, `REFERENCIA_PERSONA4.md` | cross-project notes and reviews | not ported |

When you port a page, translate it into `manual/`, update this table, and leave the upstream file untouched so merges stay
clean.
