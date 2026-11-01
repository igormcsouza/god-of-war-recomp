# Guide for agents and contributors

Port of *God of War* (PS2, `SCUS-97399`) by static recompilation with
[PS2Recomp](https://github.com/ran-j/PS2Recomp). This repository contains no game files and no generated C++: only
what is specific to God of War. All documentation lives in the English manual (`manual/`, built with MkDocs and
published at <https://igormcsouza.github.io/god-of-war-recomp/>). Status and research: `manual/reference/research-log.md`.
Architecture and CI: `manual/project/architecture.md` and `manual/reference/architecture-details.md`.

Several agents work on `main` at the same time. Before starting, `git pull`; before pushing, fetch `main` again and
integrate the changes (merge, never rewrite published history). `main` takes squash merges only.

## Where each thing goes

| Change | Where |
|---|---|
| Replacements and diagnostics of game functions | `src/gow_overrides.cpp` (`applyGowOverrides`) |
| Changes to the PS2Recomp runtime/IOP | one patch per topic in `patches/` |
| Recompiler functions, stubs and entry points | `config/recomp.template.toml`, `config/funcmap.csv` |
| Game-independent tests | `tests/` (runtime tests go inside the patch, in `ps2xTest/`) |
| Port status (the README map) | `manual/status-map/datos.toml` |
| Linux launcher, setup wizard and AppImage | `tools/linux/`, `tools/appimage/`, `.github/workflows/release.yml`; tests in `tests/test_gow_launcher.py` and `tests/test_gow_setup.py` |
| **Any documentation** | `manual/` (see "Documentation" below) |

## PS2Recomp patches

- They are applied on the commit pinned in `scripts/common.ps1` (`$PS2RecompCommit`), **in the order of
  `scripts/compilar.ps1`**, with `git apply --ignore-whitespace`. Each patch is generated against the tree with the
  previous ones already applied.
- **New patch:** add its variable in `scripts/compilar.ps1` (`$xxxPatch = Join-Path $RepoRoot
  'patches\ps2recomp-xxx.patch'`) and its `Run $git @('apply', ...)` line. CI reads the list from there
  (`tools/ci/parches.py`) and fails if a `patches/*.patch` does not apply.
- Prefer a new patch per topic over growing `ps2recomp-runtime.patch`: changes from other agents collide less.
- **Editing an existing patch** (`N` = the one you change), from the repository root (`PS2Recomp/` is in
  `.gitignore`):

  ```sh
  git clone https://github.com/ran-j/PS2Recomp.git PS2Recomp   # first time only
  git -C PS2Recomp checkout -qf <pinned commit> && git -C PS2Recomp clean -fdq
  # apply, in order, the patches before N and make a "base" commit
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
- Patch changes need `scripts\2_compilar.cmd`; `2_recompilar_rapido.cmd` only copies `src/gow_overrides.cpp` and
  `src/*.h`.

## Overrides (`src/gow_overrides.cpp`)

- Call the original function for everything you do not replace, and respect resumptions after a checkpoint (`ctx->pc`
  different from the entry address: call the original, nothing else).
- Diagnostics are optional: enable them with an environment variable (`GOW_*_DIAG`) or with a message limit, and use a
  `[gow-xxx]` tag in the log. Document the variable in the manual (`manual/usage/env-vars.md` or the research log), and
  remove the diagnostic once the problem is solved.
- If you use a new runtime function, it must exist in some patch: CI compiles `src/*.cpp` against the patched runtime.

## Checks (CI: `.github/workflows/pruebas.yml`)

On every push to `main` and every PR, without the game. They must stay green:

- `python3 tools/ci/validar_config.py`: `funcmap.csv` and `recomp.template.toml`.
- `pwsh -File tools/ci/analizar_ps1.ps1`: syntax of the `.ps1` files.
- `tests/pad2_packet_test.cpp` (on Windows: `scripts\probar_pad2.cmd`).
- The patches apply, every stub has a handler in the runtime, `src/*.cpp` compiles against the patched runtime and
  the whole `ps2x_tests` suite passes. `tests/fallos_conocidos.txt` is empty: do not add a test there to hide a
  regression, fix it.
- `mkdocs build --strict` (workflow `manual.yml`): the manual builds with no broken links.

The suite can be reproduced on Linux (or WSL): apply the patches as above, then

```sh
cmake -S PS2Recomp -B PS2Recomp/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPS2X_BUILD_STUDIO=OFF \
  -DCMAKE_C_FLAGS=-march=x86-64-v2 -DCMAKE_CXX_FLAGS=-march=x86-64-v2
ninja -C PS2Recomp/build ps2x_tests
(cd PS2Recomp && ./build/ps2xTest/ps2x_tests 2>/dev/null) | python3 tools/ci/comprobar_pruebas.py tests/fallos_conocidos.txt
```

The suite runs from `PS2Recomp/`, as in CI: some tests read sources by relative path (for example `VU0 macro mappings
cover all S1/S2 enums`) and fail when started from the root.

(Ubuntu packages: the ones in "Instalar dependencias" in `pruebas.yml`).

## Testing with the game (Windows)

What CI cannot check: it needs the ELF, the IRX modules and the ISO (see the README).

1. `scripts\2_compilar.cmd` (or `2_recompilar_rapido.cmd` if you only changed `src/`).
2. `scripts\probar_menu.ps1 -Segundos 115`: walks through the menu and saves GS captures in `logs\`.
3. Review `logs\ejecutar_err.log` and the captures. A non-black capture or a clean log does not prove the game is
   playable: record in the research log exactly what was verified.

## Documentation

**All documentation is in English and lives in the MkDocs manual, `manual/` (config: `mkdocs.yml`).** The only
documentation files outside it are `README.md` and this `AGENTS.md` (plus `CHANGELOG.md` and `LICENSE`).

- **Do not create documentation under `docs/`.** That folder no longer exists. If a merge from upstream brings it
  back, port its content (below) and delete it.
- A new page goes under `manual/` in the right section and is added to `nav` in `mkdocs.yml`:
  `install/` (getting it running), `usage/` (using it), `project/` (evolution, performance, architecture, status),
  `reference/` (detailed technical notes and the research log).
- Write in English. Keep code, commands, paths, identifiers and environment variable names exactly as they are.
- Link to other pages with relative `.md` links and to repository files with
  `https://github.com/igormcsouza/god-of-war-recomp/blob/main/<path>`. `mkdocs build --strict` must pass.
- `manual/reference/research-log.md` is the investigation log: add what was tried, with what result, and the next
  steps. Do not delete findings; correct them if they turn out wrong. State exactly what was verified and what was not.
- If a component or library changes state (works / partial / pending), update `manual/status-map/datos.toml` and run
  `python tools/estado/generar.py` (the "Mapa de estado" action does it too when pushing to `main`).
- The README and the manual must agree. The README is English only (the Spanish and Portuguese ones were removed; if a
  merge brings them back, `git rm` them).
- New code comments and commit messages are in English (existing Spanish comments stay as they are).

### When you merge upstream

Upstream (`KIexster/god-of-war-recomp`) writes its documentation in Spanish under `docs/`. **Every merge from upstream
must also port the new documentation**; this extra effort is part of the merge, not optional:

1. After merging, run `git diff <previous merge-base>..upstream/main --stat -- docs README*.md` to see which
   documentation files upstream added or changed (and `git status` for `docs/` files that came back).
2. Translate every new or changed page into English and put it in the matching page under `manual/` (new topics get a
   new page and a `nav` entry). Keep the research log in order: append upstream's new entries to
   `manual/reference/research-log.md`.
3. Delete the Spanish originals (`git rm`), including `README.es.md`, `README.pt-BR.md` and any `docs/estado/*.es.*` or
   `*.pt-BR.*` file that came back. Conflicts on files deleted here are resolved with `git rm`.
4. Run `mkdocs build --strict` and the checks above before the merge commit is pushed.

`git config rerere.enabled true` helps replay repeated conflict resolutions.

## Versions

`VERSION` and `CHANGELOG.md` rule. A version = raise `VERSION`, write `CHANGELOG.md`, merge and push the
`vX.Y.Z` tag: `release.yml` builds the AppImage (builder only, no game files) and attaches it; see
`manual/install/appimage.md`. A release never attaches the runner, the extracted disc, the captured microcode or any
generated C++.

## Legal

Never commit game files (ELF, IRX, ISO, `.PAK`, `.WAD`), code generated from it, RAM/VRAM captures or microcode
dumps. `game/` and `logs/` are in `.gitignore`.
