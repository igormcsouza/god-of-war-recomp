# Linux launcher: settings window

`tools/linux/gow_launcher.py` opens a Tk settings window when a display is available
(`DISPLAY` or `WAYLAND_DISPLAY`) and neither `--iso`, `--prepare-only` nor `--no-gui`/`--last`
is given. ISO preparation and validation are described in `docs/LINUX_ISO.md`.

```sh
python3 tools/linux/gow_launcher.py            # settings window, ISO field prefilled
python3 tools/linux/gow_launcher.py --last     # no window: resolved ISO + saved settings (alias: --no-gui)
python3 tools/linux/gow_launcher.py --iso X.iso --runner R   # explicit ISO, no window
python3 tools/linux/gow_launcher.py --last --mute            # saved settings, audio muted this run only
```

Tk is not part of every Python install. On Debian/Ubuntu install `python3-tk`. If Tk or
the display is unavailable, the launcher falls back to the terminal flow (resolved ISO,
otherwise a numbered list or a prompt, otherwise an error asking for `--iso`).

## ISO resolution

Without `--iso` the launcher picks the ISO in this order:

1. `GOW_ISO` environment variable, if it is a supported ISO (otherwise a note is printed and the next source is used).
2. The `iso` saved in `settings.json`, if the file still exists and passes the header check.
3. A scan for `*.iso` files in `~/Games/Sony Playstation 2` (depth 3), `~/Games` (depth 1) and
   `~/Downloads` (depth 1), plus any colon-separated directories in `GOW_ISO_DIRS` (depth 3).
   Only files that pass the check count. Hidden entries and symlinked directories are skipped,
   and the scan stops after 2000 directory entries.

One match is used without asking. Several matches: the window prefills the first one; in a
terminal a numbered list is shown (Enter takes 1, or type a path); without a terminal `--last`
fails and asks for `--iso`. No match: the normal flow (window, then picker or prompt).

Each ISO that is successfully validated and prepared is saved as `iso` in `settings.json`,
whichever way it was chosen (window, `--iso`, terminal, `GOW_ISO`). Only that key is written:
the other saved settings and unknown keys are kept, and one-run flags such as `--mute` are never
saved. A later start with no `--iso` therefore loads the game without asking.

The header check reads only the ISO sectors that describe the root directory and
`SYSTEM.CNF`; it does not extract or hash files.

## Window

| Control | Effect |
|---|---|
| ISO + Browse | Prefilled with the resolved ISO (see above). Validated on Play with the normal ELF SHA-256 check; the error text is shown in red. |
| Fullscreen | Exports `GOW_FULLSCREEN=1` (borderless fullscreen at start; F11 toggles in game). |
| Scaling | Bilinear (default, exports nothing) / Sharp bilinear / Nearest: exports `GOW_SCALE_FILTER=sharp-bilinear` / `nearest`. Saved as `scaling` in `settings.json`; older files without it load as Bilinear. |
| Show FPS | Stored only (applies with the Vulkan backend). The window title already shows FPS. |
| Internal resolution 1x/2x/3x | Stored only (applies with the Vulkan backend). |
| Raster threads | `PS2X_GS_RASTER_THREADS` (0/Auto = unset). |
| Controller | Lists pads found in `/proc/bus/input/devices`; choosing one exports `GOW_PAD_INDEX`, "Auto" leaves it unset. |
| Debug UI | `GOW_DEBUG_UI=1`. |
| Mute audio | `GOW_AUDIO=0`: audio output is disabled, the SPU2 is still emulated. Unchecked leaves `GOW_AUDIO` unset. |
| Skip movies (FMV, workaround) | `GOW_SKIP_FMV=1`: skips the pre-rendered movies. Use it while movie audio and the screen after a cutscene are still being fixed. |
| GPU | `gpu` setting, `Auto` by default (discrete GPU first, then integrated). Any other value is a device index or a name substring and sets `PS2X_VK_DEVICE`. The list comes from `vulkaninfo --summary` (empty if it is not installed; you can still type a value). |

`--mute` forces audio off for a single run, with or without the window (and works with `--iso`
and `--last`). It is not saved: the settings file keeps the checkbox value.

The `mute_audio` key defaults to `false` when missing, so settings files written before it was
added still load.

Settings are saved on Play in `${XDG_CONFIG_HOME:-~/.config}/gow-one-recomp/settings.json`.
Invalid or unknown values are ignored on load. The ISO path is also written after any
successful preparation (see "ISO resolution"), without changing the other keys. The Tk window
itself has no automated test; the settings, env mapping, ISO resolution and `--last` flow are
tested without a display.

## Flatpak feasibility (read-only analysis)

Not feasible as a self-contained bundle of the game runner: the runner is C++ generated
from the user's `SCUS_973.99`, which AGENTS.md (Legal) forbids distributing. A Flatpak
could only ship what is game-independent: the launcher, the patched PS2Recomp runtime and
the recompiler tool, plus `src/gow_overrides.cpp`.

Viable design: ship those, and on first run (after the launcher extracts and verifies the
ELF from the user's ISO) run recompilation and compile into `$XDG_DATA_HOME` (per-user,
not distributed). The manifest would need:

- Runtime `org.freedesktop.Platform` + `org.freedesktop.Sdk` (build tools stay in the
  sandbox, so the Sdk and its extensions must be installed at runtime, which is heavy,
  roughly 1-2 GB with CMake/Ninja/a C++ compiler and the generated sources).
- Python with Tk (`python3-tk` equivalent module) for the window; SDL2, Vulkan/GL, ALSA/PulseAudio libs.
- Finish-args: `--device=dri`, `--socket=x11`/`wayland`, `--socket=pulseaudio`,
  `--device=all` (or `input` on newer Flatpak) for gamepads, and `--filesystem` access
  to the ISO (or the portal file chooser).
- Offline vendoring of PS2Recomp sources and the pinned commit with patches applied.

Risks: long first-run build with a visible progress UI needed; Flathub review is unlikely to
accept a package that compiles a commercial game on demand. A self-hosted repo or a plain
local build script (`docs/LINUX_COMPILACION.md`) is the lower-effort route.
