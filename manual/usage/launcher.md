# Launcher

`tools/linux/gow_launcher.py` opens a settings window (the AppImage opens it for you). Settings are saved when you press
Play in `${XDG_CONFIG_HOME:-~/.config}/gow-one-recomp/settings.json`.

```sh
python3 tools/linux/gow_launcher.py            # settings window
python3 tools/linux/gow_launcher.py --last     # no window: saved settings
python3 tools/linux/gow_launcher.py --last --mute   # audio muted for this run only
```

## Window

| Control | Effect |
|---|---|
| ISO + Browse | Prefilled with the ISO it found. Validated on Play; the error is shown in red. |
| Start in fullscreen | Borderless fullscreen at start, or windowed (default). **F11** toggles in game. |
| Scaling | Sharp (default) or Bilinear. |
| Show FPS counter | On-screen counter with the **1% low**: the frame rate of the slowest 1% of game frames over the last 5 minutes. It counts gameplay only (menus, movies and loading are left out), so it shows `--` until gameplay starts. **F2** toggles it. |
| Render scale | 1080p (default), 2x, 3x, 4x of the PS2's 448 lines. |
| Mute audio | Disables audio output. |
| Skip movies | Skips the pre-rendered movies. |
| Cheats (debug) | God mode, No enemies. |

## Render scale, measured

RTX 5050 laptop, ship zones: **56.0 FPS** at 2x and at 1080p, 55.2 at 3x, 53.9 at 4x. GS and upload time grow with the
scale, but the cost is small. All four looked good in play.

## How the ISO is found

In order: the `GOW_ISO` variable, the ISO saved in the settings, then a scan of `~/Games/Sony Playstation 2`,
`~/Games` and `~/Downloads` (plus `GOW_ISO_DIRS`). Only files that pass a header check count. One match is used without
asking; several are offered as a list.

## Pads

Controllers are autodetected. Pads without an SDL mapping (for example a GameSir dongle) get a generic Xbox-like
layout. `GOW_PAD_MAPPINGS=<gamecontrollerdb.txt>` overrides it and `GOW_PAD_DIAG=1` logs what the game reads.
