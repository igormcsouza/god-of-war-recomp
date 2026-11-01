# Contributing

The conventions live in [`AGENTS.md`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/AGENTS.md). In short:

| Change | Where |
|---|---|
| Game function replacements and diagnostics | `src/gow_overrides.cpp` |
| Runtime changes | one patch per topic in `patches/`, added to `scripts/compilar.ps1` |
| Recompiler stubs and entry points | `config/recomp.template.toml`, `config/funcmap.csv` |
| Launcher, setup, AppImage | `tools/linux/`, `tools/appimage/`, `.github/workflows/release.yml` |
| Tests | `tests/` (runtime tests live inside the patch, in `ps2xTest/`) |
| This manual | `manual/` (English only) |

A change of runtime behaviour needs a regression test in `ps2xTest/` that fails without it. Mark patched code with
`// GOW-Port:`. `main` takes squash merges only.

## Releases

Raise `VERSION`, update `CHANGELOG.md`, merge, then `git tag vX.Y.Z && git push origin vX.Y.Z`; the workflow builds and
publishes the AppImage.

## Syncing upstream

Upstream's tip is merged into this fork on purpose, not continuously. Spanish and Portuguese READMEs were deleted here:
if a merge brings them back, `git rm` them. This manual lives in `manual/` and `mkdocs.yml` so upstream's `docs/` can
merge without touching it.

## Building this manual

```sh
pip install mkdocs-material
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict
```
