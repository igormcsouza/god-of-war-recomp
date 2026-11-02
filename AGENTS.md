# Guide for agents and contributors

Native Linux port of *God of War* (PS2, `SCUS-97399`) by static recompilation with
[PS2Recomp](https://github.com/ran-j/PS2Recomp). This repository contains no game files and no generated C++: only
what is specific to God of War. All documentation lives in the English manual (`manual/`, built with MkDocs and
published at <https://igormcsouza.github.io/god-of-war-recomp/>). Status and research: `manual/reference/research-log.md`.
Architecture and CI: `manual/project/architecture.md` and `manual/reference/architecture-details.md`.

The project is **Linux only** and **English only**. It is independent: it started from KIexster/god-of-war-recomp and
runs on Waffle565's native runtime, but it does not track either; a change from another fork is picked on purpose,
as its own patch with a test. Several agents may work on `main` at the same time. Before starting, `git pull`; before
pushing, fetch `main` again and integrate the changes (merge, never rewrite published history). `main` takes squash
merges only.

## Where each thing goes

| Change | Where |
|---|---|
| Replacements and diagnostics of game functions | `src/gow_overrides.cpp` (`applyGowOverrides`) |
| Changes to the PS2Recomp runtime/IOP | one patch per topic in `patches/`, listed in `patches/series` |
| Recompiler functions, stubs and entry points | `config/recomp.template.toml`, `config/funcmap.csv` |
| Game-independent tests | `tests/` (runtime tests go inside the patch, in `ps2xTest/`) |
| Port status (the README map) | `manual/status-map/data.toml` |
| Linux launcher, setup wizard and AppImage | `tools/linux/`, `tools/appimage/`, `.github/workflows/release.yml`; tests in `tests/test_gow_launcher.py` and `tests/test_gow_setup.py` |
| **Any documentation** | `manual/` (see "Documentation" below) |

## PS2Recomp patches

- They are applied on the commit in `patches/PS2RECOMP_COMMIT`, **in the order of `patches/series`**, with
  `git apply --ignore-whitespace`. Each patch is generated against the tree with the previous ones already applied.
  `scripts/build_linux.py` and CI both read the list through `tools/ci/patch_series.py`.
- **New patch:** add the file to `patches/` and its name at the end of `patches/series`. CI fails if a
  `patches/*.patch` is not listed, a listed file is missing, or a patch does not apply.
- Prefer a new patch per topic over growing `ps2recomp-waffle-runtime.patch`: changes from other agents collide less.
- **Editing an existing patch** (`N` = the one you change), from the repository root (`PS2Recomp/` is in `.gitignore`):

  ```sh
  git clone https://github.com/ran-j/PS2Recomp.git PS2Recomp   # first time only
  git -C PS2Recomp checkout -qf "$(cat patches/PS2RECOMP_COMMIT)" && git -C PS2Recomp clean -fdq
  # apply, in order, the patches in patches/series before N and make a "base" commit
  git -C PS2Recomp apply --ignore-whitespace "$PWD/patches/<previous patch>"   # one per patch
  git -C PS2Recomp -c user.name=x -c user.email=x commit -qam base
  git -C PS2Recomp apply --ignore-whitespace "$PWD/patches/<N>"
  # ... edit ...
  git -C PS2Recomp diff > patches/<N>
  ```

  Then check that the patches after `N` still apply.
- Mark changes with a `// GOW-Port:` comment to tell them from the original code.
- A runtime behaviour change comes with a regression test in `ps2xTest/` that fails without the change. If you
  deliberately change something an existing test checked, adjust the test and explain why.
- Patch changes need a rebuild of the runner (`python3 scripts/build_linux.py --elf ...`, with the runtime link
  taking 15-25 minutes).

## Overrides (`src/gow_overrides.cpp`)

- Call the original function for everything you do not replace, and respect resumptions after a checkpoint (`ctx->pc`
  different from the entry address: call the original, nothing else).
- Diagnostics are optional: enable them with an environment variable (`GOW_*_DIAG`) or with a message limit, and use a
  `[gow-xxx]` tag in the log. Document the variable in the manual (`manual/usage/env-vars.md` or the research log), and
  remove the diagnostic once the problem is solved.
- If you use a new runtime function, it must exist in some patch: CI compiles `src/*.cpp` against the patched runtime.

## Checks (CI: `.github/workflows/tests.yml`)

On every push to `main` and every PR, without the game. They must stay green:

- `python3 tools/ci/validate_config.py`: `funcmap.csv` and `recomp.template.toml`.
- `python3 tools/ci/patch_series.py`: the patch series.
- The launcher, setup wizard and AppImage tests, `tests/pad2_packet_test.cpp` and `tests/pad_script_test.cpp`.
- The patches apply, every stub has a handler in the runtime, `src/*.cpp` compiles against the patched runtime and
  the whole `ps2x_tests` suite passes. `tests/known_failures.txt` is empty: do not add a test there to hide a
  regression, fix it.
- `mkdocs build --strict` (workflow `manual.yml`): the manual builds with no broken links.

The suite can be reproduced on Linux: apply the patches as above, then

```sh
cmake -S PS2Recomp -B PS2Recomp/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPS2X_BUILD_STUDIO=OFF \
  -DCMAKE_C_FLAGS=-march=x86-64-v2 -DCMAKE_CXX_FLAGS=-march=x86-64-v2
ninja -C PS2Recomp/build ps2x_tests
(cd PS2Recomp && ./build/ps2xTest/ps2x_tests 2>/dev/null) | python3 tools/ci/check_tests.py tests/known_failures.txt
```

The suite runs from `PS2Recomp/`, as in CI: some tests read sources by relative path and fail when started from the
root. (Ubuntu packages: the ones in "Install dependencies" in `tests.yml`.)

## Testing with the game

What CI cannot check needs your own ISO and a built runner (see `manual/install/from-source.md`):

1. Build with `python3 scripts/build_linux.py --elf <SCUS_973.99>` (after `tools/linux/capture_microcode.py` once).
2. Start with `python3 tools/linux/gow_launcher.py`, or reproduce a scene without touching the pad (the scripted pad in
   `manual/reference/controls-and-menu-tests.md`).
3. Judge visual changes on **lossless window grabs** (`import -window`) and, for faint artefacts, a high-pass view; the
   FPS overlay (F2) and `scripts/measure_fps.sh` give the numbers. A non-black capture or a clean log does not prove the
   game is playable: record in the research log exactly what was verified.

## Documentation

**All documentation is in English and lives in the MkDocs manual, `manual/` (config: `mkdocs.yml`).** The only
documentation files outside it are `README.md` and this `AGENTS.md` (plus `CHANGELOG.md` and `LICENSE`).

- A new page goes under `manual/` in the right section and is added to `nav` in `mkdocs.yml`:
  `install/` (getting it running), `usage/` (using it, screenshots), `project/` (evolution, performance, architecture,
  status), `reference/` (detailed technical notes and the research log).
- Write in English. Keep code, commands, paths, identifiers and environment variable names exactly as they are (some
  keep their original Spanish form so existing settings keep working).
- Link to other pages with relative `.md` links and to repository files with
  `https://github.com/igormcsouza/god-of-war-recomp/blob/main/<path>`. `mkdocs build --strict` must pass.
- `manual/reference/research-log.md` is the investigation log: add what was tried, with what result, and the next
  steps. Do not delete findings; correct them if they turn out wrong. State exactly what was verified and what was not.
- If a component or library changes state (works / partial / pending), update `manual/status-map/data.toml` and run
  `python3 tools/status/generate.py` (the "Mapa de estado" action does it too when pushing to `main`).
- The README and the manual must agree. New screenshots go in `manual/images/` (lossless grabs saved as JPEG, no personal
  paths visible) and are listed in `manual/usage/screenshots.md`.
- New code comments and commit messages are in English (existing Spanish comments stay as they are).

## Versions

`VERSION` and `CHANGELOG.md` rule. A version = raise `VERSION`, write `CHANGELOG.md`, merge and push the
`vX.Y.Z` tag: `release.yml` builds the AppImage (builder only, no game files) and attaches it; see
`manual/install/appimage.md`. A release never attaches the runner, the extracted disc, the captured microcode or any
generated C++.

## Legal

Never commit game files (ELF, IRX, ISO, `.PAK`, `.WAD`), code generated from it, RAM/VRAM captures or microcode
dumps. `game/` and `logs/` are in `.gitignore`. Screenshots of gameplay are fine for the documentation; the game itself
is never distributed.
