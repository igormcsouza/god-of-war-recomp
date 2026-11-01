# God of War, natively on Linux

A native port of *God of War* (PS2, NTSC-U `SCUS-97399`) made by **statically recompiling** the game's MIPS code to C++
with [PS2Recomp](https://github.com/ran-j/PS2Recomp). No emulator runs the game: every PS2 chip is replaced by native code.

This fork is **Linux first**. It continues [KIexster/god-of-war-recomp](https://github.com/KIexster/god-of-war-recomp)
on top of [Waffle565's native runtime](https://github.com/Waffle565/God-Of-War-Native-Port).

## What you get

| | |
|---|---|
| Speed | about 55-59 FPS average in gameplay on an RTX 5050 laptop (about 21 before the native runtime) |
| Image | OpenGL renderer, 1080p render scale by default, up to 4x |
| Tools | launcher, FPS overlay with the 1% low, fullscreen toggle, cheats, generic pad mapping |
| Install | one **AppImage** that builds the game runtime from *your* ISO on first run |

## Start here

1. [Install with the AppImage](install/appimage.md) (or [build from source](install/from-source.md)).
2. [Use the launcher](usage/launcher.md) and learn the [controls](usage/controls.md).
3. Curious how it got here? Read [how it evolved](project/evolution.md) and the [architecture](project/architecture.md).

!!! warning "You need your own copy of the game"
    This project contains **no game files and no code generated from them**. You supply your own legal
    ISO; everything else is built on your machine. See [Credits and legal](project/credits.md).
