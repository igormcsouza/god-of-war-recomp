# Contributing

The conventions live in [`AGENTS.md`](https://github.com/igormcsouza/god-of-war-recomp/blob/main/AGENTS.md). In short:

| Change | Where |
|---|---|
| Game function replacements and diagnostics | `src/gow_overrides.cpp` |
| Runtime changes | one patch per topic in `patches/`, listed in `patches/series` |
| Recompiler stubs and entry points | `config/recomp.template.toml`, `config/funcmap.csv` |
| Launcher, setup, AppImage | `tools/linux/`, `tools/appimage/`, `.github/workflows/release.yml` |
| Tests | `tests/` (runtime tests live inside the patch, in `ps2xTest/`) |
| Any documentation | `manual/` (English only; `README.md` and `AGENTS.md` are the only docs outside it) |

A change of runtime behaviour needs a regression test in `ps2xTest/` that fails without it. Mark patched code with
`// GOW-Port:`. `main` takes squash merges only.

## Releases

Raise `VERSION`, update `CHANGELOG.md`, merge, then `git tag vX.Y.Z && git push origin vX.Y.Z`; the workflow builds and
publishes the AppImage.

## Updating the runtime base

The runtime comes from PS2Recomp at the commit in `patches/PS2RECOMP_COMMIT` plus Waffle565's runtime patch. This project
is independent: changes from other forks are picked on purpose, one topic at a time, as a new patch with a regression
test. To move to a newer PS2Recomp commit, change the pin, rebase the patches in order (see `AGENTS.md`) and run the CI
checks.

## Building this manual

```sh
pip install mkdocs-material
mkdocs serve          # http://127.0.0.1:8000
mkdocs build --strict
```
