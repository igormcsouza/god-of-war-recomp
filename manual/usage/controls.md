# Controls

The game uses libpad2; the overrides in `src/gow_overrides.cpp` connect it to the runtime's input backend for the
first port. The second port stays disconnected and there is no rumble yet.

## Keyboard (no gamepad connected)

| PS2 control | Key |
|---|---|
| Left stick | WASD |
| Right stick | IJKL |
| D-pad | Arrow keys |
| X | X or Space |
| Circle | C |
| Square | Z or keypad 0 |
| Triangle | V or keypad 1 |
| L1 / R1 | Q / E |
| L2 / R2 | Left / right Shift |
| Start / Select | Enter / Tab |

With a gamepad at index 0 its buttons, sticks and triggers are used instead.

## In-game keys

| Key | Action |
|---|---|
| **F11** | toggle fullscreen / windowed (Alt+Enter is not used: Enter is Start) |
| **F2** | show or hide the FPS counter |
| **F1** | show or hide the runtime debugger |

## Cheats

Debug cheats are enabled from the launcher (God mode, No enemies) or with `GOW_CHEAT=god,noenemies`.
