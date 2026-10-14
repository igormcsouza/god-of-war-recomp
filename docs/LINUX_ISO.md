# Launching from an ISO on Linux

`tools/linux/gow_launcher.py` prepares the files required by the runtime and starts a
**prebuilt native Linux** `ps2EntryRunner`. The launcher does not compile anything or
modify the ISO.

```sh
python3 tools/linux/gow_launcher.py \
  --iso "/path with spaces/God of War.iso" \
  --runner "/path/to/ps2EntryRunner"
```

If `--iso` is omitted, the settings window opens (see `docs/LINUX_LAUNCHER.md`; needs `python3-tk`). A terminal prompt is used when a
graphical display is unavailable. If `--runner` is omitted, the launcher looks for
`bin/ps2EntryRunner` in the repository; `GOW_RUNNER` can also specify its path. To
validate and prepare the files without starting the game:

```sh
python3 tools/linux/gow_launcher.py --iso "/path/God of War.iso" --prepare-only
```

The supported edition is NTSC-U `SCUS-97399`, with `SYSTEM.CNF` booting
`cdrom0:\SCUS_973.99;1` and an ELF whose SHA-256 is
`ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c`.
The image must use ISO 9660 with 2048-byte sectors and place `SCUS_973.99` and its
IRX modules in the root. At least `SMPD_IOP.IRX`, `989NOMID.IRX`, and `LIBSD.IRX`
are required. Other revisions and layouts produce an explicit error.

The ELF and all root IRX files are extracted to
`${XDG_CACHE_HOME:-~/.cache}/gow-one-recomp/SCUS-97399/` under a private directory.
The IRX modules are stored in `IOP_MOD/` beside the ELF, as the runtime expects. The
cache records a SHA-256 for each file and reextracts damaged files. A change to the
ISO size, modification time, or file identity creates a new cache entry. The original
ISO stays in place; the launcher passes its absolute path through `GOW_ISO` so the
IOP can read sectors from it.

Run the synthetic tests without game files:

```sh
python3 -m unittest discover -s tests -p test_gow_launcher.py
```
