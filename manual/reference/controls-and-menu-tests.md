# Gamepad input and menu tests

God of War uses **libpad2** (sockets), while PS2Recomp's input backend delivers libpad packets
(port/slot). The overrides in `src/gow_overrides.cpp` connect both interfaces for the
first port. The second port stays disconnected; there is no rumble yet.

## Keyboard

When no gamepad is connected to the backend:

| PS2 control | Key |
|---|---|
| Left stick | WASD |
| Right stick | IJKL |
| D-pad | Arrow keys (WASD also drives the backend's D-pad) |
| X | X or Space |
| Circle | C |
| Square | Z or numpad 0 |
| Triangle | V or numpad 1 |
| L1 / R1 | Q / E |
| L2 / R2 | Left / right Shift |
| Start / Select | Enter / Tab |

The backend uses the gamepad at index 0 when it is available. Its buttons, sticks and triggers are
adapted to the libpad2 packet. Pressures are simulated as 0 or 255 depending on whether the button is released or pressed.

## Display and debugger

Since 2026-10-16 the game starts in **borderless full screen**: the window covers the whole monitor and hides the
taskbar. Before, it was a 1920x1080 window on a monitor of the same size, with the title bar off the
screen and the taskbar on top of the bottom strip of the image. **F11** toggles between full screen and windowed. `GOW_PANTALLA_COMPLETA=0` starts windowed, as does
requesting a size with `GOW_WINDOW=<width>x<height>`;
`GOW_PANTALLA_COMPLETA=1` forces full screen even if a size is requested. Alt+Enter is not used because Enter is Start.

**Widescreen.** The game always runs in 16:9 with its own widescreen mode, which crops the image at the top and bottom.
`GOW_PANORAMICO=ampliado` enables the extended widescreen mode: the camera recovers the 4:3 height and widens the view to
the sides, like the "enhanced native widescreen" by nemesis2000 and CRASHARKI for PCSX2. More of the scene is visible, so it draws
more: in the ship combat the median dropped from 59.9 to 54.9 game frames per second (2026-10-18).

## 120 Hz

`GOW_HZ=120` (experimental) generates the EE VBlank every 8.34 ms instead of every 16.68 ms: the game loop, which
waits for one VBlank per frame, can run up to 120 iterations per second. The game's time step (0x17D778) becomes
the elapsed guest time, clamped to [1/120, 4/60] s, so the speed does not change. The IOP, the sound
and the movie clock stay on NTSC fields, and the host presentation rises to 120 images per second (without
vertical sync: on a 60 Hz monitor you see tearing). In the ship combat the game gives 65-73
frames per second on a Ryzen with an RX 5700 XT; in light scenes, 120. Not thoroughly reviewed: physics, in-engine cutscenes
and all levels.

The **runtime debugger** ("Runtime Debugger") no longer opens at startup: **F1** shows or hides it.

## FPS meter

**F2** shows or hides, at the top left, the game's frames per second (entries to `vid::Flip`, the game's frame
function; `GOW_PERF_FRAME_PC` changes it) and the window refreshes. Green from 57, yellow from 45 to 57,
red below that. `GOW_FPS=1` shows it from the start. While it is visible, every second a line is written to the log
(`logs\ejecutar_err.log`): `[gow-fps] t=<s> juego=<fps> min=<minimum in 0.25 s windows> pantalla=<Hz>`, to
locate afterwards where the stutters happened.

Since 2026-10-16 it also shows the **images** per second that actually reach the window (`imagenes=` and
`min_imagenes=` in the log); the color follows the worse of the two figures. If the game runs at 60 and the images do not, the
stutter comes from the presentation, not from the game. `PS2X_GS_PRESENT_LATEST=1` goes back to always showing the most recent frame
(previous behavior, with images lost when the game's pace is irregular).

## Validation

`scripts\probar_pad2.cmd` builds and runs a game-independent test. It checks the byte order
of X/Start, both sticks and the twelve pressures against the table used by the SCUS-97399
executable. It requires the same C++ tools as the normal build.

After building the port, the navigation test can be repeated:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -Segundos 115
```

The test temporarily enables `GOW_PAD_TEST=1`: it presses Start 5 seconds after the first read
of the pad and X at 12, 20, 28, 36, 52, 60, 68, 76, 84, 100, 116 and 132 seconds. It saves up to seventeen PPM images of the GS framebuffer in
`logs\`, together with `ejecutar.log` and `ejecutar_err.log`. The sequence is a diagnostic; it does not detect which
screen is active and **does not certify that a playable game was started**. A normal run
does not inject buttons. The images and logs must be reviewed.

`GOW_PAD_GUION` replaces that sequence with another one: a comma-separated list of `second:action[:duration]`,
with 0.7 s presses if the duration is omitted. Buttons: `start`, `select`, `arriba`, `abajo`, `izquierda`, `derecha`, `x`,
`circulo`, `cuadrado`, `triangulo`, `l1`, `r1`, `l2`, `r2`. For example, to open Load in the menu:

```powershell
$env:GOW_PAD_GUION = '5:start,13:abajo,20:x'
```

`mover_izquierda`, `mover_derecha`, `mover_arriba` and `mover_abajo` drive the corresponding axis
of the **left stick** to 0/255, keeping the other axis.
The old `izquierda`/`derecha`/`arriba`/`abajo` actions remain
D-pad. Example: `180:mover_izquierda:3,181:cuadrado` holds the stick for three
seconds and presses attack at 181 s. Duration must be positive, values finite;
invalid entries are ignored. When two actions on the same axis coincide,
the last active one in the list prevails. When they finish, each read returns to the
pad's base state, or to neutral with `GOW_PAD_SOLO_GUION=1`.

`GOW_PAD_GUION_DIAG=1`, together with `GOW_PAD_TEST=1`, logs up to 128 changes
of the packet returned by libpad2 under `[gow-pad2:guion]`: host time since
the first read, state, the two button bytes in packet order
and the RX/RY/LX/LY sticks. It lets you check that the script is delivered, **not that the game
already accepts control or that the action was performed**. Times remain
host times; they do not align animations between runs. The procedural test
`tests/pad_script_test.cpp` checks buttons, stick separate from D-pad,
pressures, duration, overlap, end of window and invalid entries.

The main menu accepts buttons without pressing Start, and how long it takes to appear depends on the machine's load (emulated time advances with real time during waits). With a fast boot, the Start of
`5:start` already lands in the menu and picks New Game. To load the first save on the card regardless of the
boot time: `13:abajo,20:x,62:x` (go down to Load, open it and pick the save). Performance
measurements at the docks use that script with no further presses, so that Kratos stays still.
`GOW_PAD_SOLO_GUION=1` (enabled by `scripts\probar_rendimiento.ps1`) additionally ignores the real pad and keyboard:
touching them during a measurement took the menu to a different save.

To investigate node lookups during transitions:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -DiagnosticoRutas
```

`GOW_PATH_DIAG=1` logs `[gow-path]` and saves `gow_path_failure.bin` next to the executable if an attempt is made to
attach a NULL node. The dump contains the game's RAM and must not be published.

## Dispatcher and checkpoints

`patches/ps2recomp-checkpoint.patch` is applied after the main runtime patch. It avoids treating
an EE yield at a function's entry point as an implicit return. The failure was
reproduced when navigating from the menu: a partial copy left `goimation` instead of `goHero` and the
node lookup ended in a virtual call to NULL (`0x00180D30`). The patch includes a regression
test in `ps2_runtime_expansion_tests.cpp`.

## IPU initialization

The generic `sceIpuInit` stub tried to call `0x00126428` and read tables from another executable.
In SCUS-97399 that address is a continuation of `FilteredCopyTile`: when choosing difficulty, the
call ran the drawing loop with initialization registers and blocked the EE.
`gowIpuInit` reproduces the initialization writes to MMIO and uses the game's tables at
`0x002A1610` and `0x002A1660`, without that call into foreign code. This does not implement FMV decoding.

To investigate level loading without waiting for the decoder, `GOW_SKIP_FMV=1` skips the movies
in the game's loading API, before reserving buffers and opening the stream. Its
buffer-ready/end queries return true. The option is disabled by default and does not implement videos.

```powershell
$env:GOW_SKIP_FMV = '1'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -Segundos 230
Remove-Item Env:GOW_SKIP_FMV
```

`GOW_FAST_BOOT=1` allows repeating diagnostics without waiting for the intro animation: only its completion
query (`ra=0x0021E714`) returns the total duration once the level is already loaded.
The option is disabled by default. The test without it reached the in-game state after
several minutes; it is not necessary to use it to complete that transition.

`GOW_ANM_DIAG=1` logs animation times and pause conditions. `GOW_RENDER_DIAG=1` logs
the recent GS contexts and primitives, and on entering the in-game state it saves
`gow_vu1_code.bin`, `gow_vu1_data.bin` and `gow_render_ram.bin` next to the executable. Those dumps
contain game data and must not be published.

`GOW_VU1_BUDGET_DIAG=1` (`ps2recomp-vu1-budget-diag.patch`) logs `[gow-vu1-budget]` when a VU1
program launched by MSCAL/MSCNT exhausts the fixed cap of 65536 cycles without reaching its E bit: it shows the entry
address, the PC where it was cut and the counter. It writes the first 32 occurrences and then one in every 1024.
If no line appears during the game, the cap is not cutting programs.

## Isolated XGKICK test

`patches/ps2recomp-xgkick.patch` adds `GOW_XGKICK_IMMEDIATE=1`: it copies and sends the GIF packet
when XGKICK is issued, before later instructions overwrite the VU buffer.
With the variable absent or set to `0`, the cycle-based transfer is kept.
The idea comes from the [SOCOM Unzipped runtime](https://github.com/Scotho/socom-unzipped/blob/main/third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp#L1074-L1083).
The adaptation uses the existing bounded parser and circular memory handling; it does not import
native VU programs or SOCOM-specific addresses.

```powershell
$env:GOW_SKIP_FMV = '1'
$env:GOW_FAST_BOOT = '1'
$env:GOW_RENDER_DIAG = '1'
$env:GOW_XGKICK_IMMEDIATE = '1'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -Segundos 140
# Save the logs/screenshots before repeating: the next run replaces them.
$env:GOW_XGKICK_IMMEDIATE = '0'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -Segundos 140
Remove-Item Env:GOW_XGKICK_IMMEDIATE, Env:GOW_SKIP_FMV, Env:GOW_FAST_BOOT, Env:GOW_RENDER_DIAG
```

The 140-second runs with the same executable, option `1` and `0`, reach state 11.
The in-game screenshots at 90 seconds from the first read of the pad are identical:
all their pixels are black. XGKICK packet errors and the menu defects persist.
The option remains an experiment, disabled by default.
A synthetic regression checks that a later SQ overwrites the VU memory, while the packet
already sent keeps its original bytes. The existing cycle-mode test still passes.

## VIF UNPACK fixes

`patches/ps2recomp-vif-unpack.patch` fixes two formats of the interpreter:

- V2-32/16/8 writes `X,Y,X,Y` instead of keeping the previous Z/W components.
  The expansion happens before applying the masks and the STMOD additions.
- V4-5 expands RGB to bits 3..7 and alpha to bit 7. For example, `31,17,9,1`
  produces `248,136,72,128`. This format still ignores STMOD.

References: [PCSX2 Vif_Unpack.cpp](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Vif_Unpack.cpp)
and [SOCOM Unzipped](https://github.com/Scotho/socom-unzipped/blob/main/third_party/ps2recomp/ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp).
These fixes are applied in the normal build.

Three synthetic tests failed before the fix and pass after it: they cover the three V2 widths,
signed/unsigned extension, masks, write protection, per-component addition and V4-5 alpha
on/off. The suite goes from 436/441 to 439/441; the two remaining failures are the previous ones.
The game run with FMVs skipped still reaches state 11, with menu defects
and the in-game image black. No visual improvement is attributed to these fixes.

## VIF diagnostics and draw buffers

`patches/ps2recomp-vif-diagnostic.patch` adds optional, bounded traces; it does not alter the execution
of VIF or VU. To repeat them:

```powershell
$env:GOW_SKIP_FMV = '1'
$env:GOW_FAST_BOOT = '1'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_menu.ps1 -Segundos 140 -DiagnosticoVif
Remove-Item Env:GOW_SKIP_FMV, Env:GOW_FAST_BOOT
```

The script restores the diagnostic variables when it finishes. In `logs\ejecutar_err.log`:

- `[gow-vif]` counts commands and interrupt requests (I bit).
- `[gow-vif-launch]` compares TOP/ITOP and the in-memory header before the first 24 MSCALs.
- `[gow-xgkick]` shows the first 96 GIF headers and a sample every 4096.
- `[gow-xgkick:reject]` identifies the first 32 rejections due to format, length or full buffer.
  A header with NLOOP=0 can be valid; it must not be counted as a rejection by itself.
- `[gow-gs:buffer]` logs the format, address and pixels with non-zero RGB of each context.

On first reaching state 11, `GOW_RENDER_DIAG` also saves `gow_render_vram.bin`
and `gow_render_context_0.ppm` / `gow_render_context_1.ppm` next to the executable. The context
images are only generated for PSMCT32/24 and non-zero FBW. They read memory using the GS
addressing, without changing the presented framebuffer. The files contain game data: keep them
locally and do not publish them.

The 140-second test logged 196608 VIF1 commands with no interrupt requests and reached
state 11. Both contexts drew at FBP=0, FBW=8, PSMCT32, while the screen presented
FBP=208. Their captures had 212992 pixels with non-zero RGB, but only showed a dark
background and scattered dots: no hidden 3D scene appeared in those buffers. The screen stayed black.
The suite keeps 439/441 tests passing and the same two known failures.

### VU1 register-jump fix

`patches/ps2recomp-vu-jump.patch` fixes JR and JALR to read the current value of the VI register.
The earlier copy used to compare conditional branches must not determine these targets.
The behavior was checked against [PCSX2's JR/JALR](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/x86/microVU_Lower.inl)
and its [jump analysis](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/x86/microVU_Analyze.inl).
The regression also covers JALR when the destination register and the link register coincide.

Repeating the previous 140 s test with this patch logs 212992 VIF1 commands, reaches
state 11 at roughly 70 s from the first read of the pad and produces no
`[gow-xgkick:reject]` or `[VU1 reserved lower]` messages. Before, packets rejected by
length and vertex loops that overwrote the headers at 0xF60 and 0x24B0 were observed.

The presented screen is still black. Context 0 keeps 212992 non-black pixels, but its
image is still a dark background with dots. This fix removes a VU1 runtime
failure; scene rendering still has to be solved. The suite stands at 440/442, with the
two previous heap/DMA failures. The temporary write traces have been removed from the runtime.

After also integrating `ps2recomp-heap.patch`, the set passes 443/443 tests. The
440/442 results above document the comparison before integrating that heap/DMA fix.

### GS command capture

`GOW_CAMERA_DIAG=1` logs the view matrices after the full return
of `renView::SetupPipeline` (`0x23B5E0`, SCUS-97399). It does not replace its calculations.
In states 4 (intro) and 11 (game), it observes up to 16 view/state pairs, with 32
samples per pair separated by at least two host seconds. `elapsed` counts
from the first observation of intro/game. It logs the active view, camera,
joint, update marks and the world, inverse, projection
and combined-product bits; it also compares the client buffers.
`stamp` corresponds to `0x29BDF8`; it is neither a frame counter nor simulated time.
Addresses are validated against RAM and floats are copied as bits, without normalizing them.
The absence or invalidity of a camera appears explicitly in `[gow-camera]`.
This diagnostic does not establish equivalence with PCSX2 and is cleared/restored when
running the performance profile. Its logs stay in local files.

To pick a stretch of GS commands, `GOW_GS_REPLAY_TRACE` gives the local
output file. `GOW_GS_REPLAY_AFTER` sets the wait since the backend was
installed (0..3600 seconds, 150 by default); `GOW_GS_REPLAY_SECONDS` sets the
duration (0.1..60 seconds, 3 by default). Values use a decimal point.
`GOW_GS_REPLAY_STATE` selects the game state that allows the capture to start
(32-bit decimal integer; `11` by default, game; `4` for the intro).
It does not change the game state nor stop the capture if the state changes afterwards.
`GOW_GS_REPLAY_TEXFLUSH=1` additionally requires a TEXFLUSH from the game in the selected state and saves
the initial state after that invalidation. It defaults to `0`. It does not force
an invalidation or a game transition. Presentation commands do not
start the capture. The limit remains 64 MiB and may close the stretch before
the deadline. Malformed options disable the capture with a message before
opening the file; without `GOW_GS_REPLAY_TRACE` the diagnostic is not installed.
The profile clears the five variables. This capture serializes the GS and is not suitable
for measuring FPS; the dumps stay in `logs/`, excluded from Git.
Example and replay: [RENDERIZADO.md](rendering.md).

### Experimental OpenGL feedback control

`PS2X_GS_FEEDBACK_SNAPSHOT=1`, set before launching the executable, protects
the texture source when a primitive writes to its own pages. It is
disabled by default. It freezes the source per primitive and is useful to contrast
OpenGL instability; the 8 KiB GS cache and the compatible batches still
require verification. The CPU renderer keeps its behavior.

The controls without the game and their limits are in
[RENDERIZADO.md](rendering.md).
`repetir_gs` explicitly selects this policy with `--snapshot-feedback`
in compute/hardware mode. It keeps flagging differences against CPU through
exit code 1, even if the GPU image stays stable across repetitions.

`--pausa-ms M` adds a wait of 1..1000 ms between `repetir_gs` passes;
it requires `--repeticiones N` with N greater than 1. It lets the shader compiler
finish while keeping the same backend. Eight passes without a wait
can complete their images in compute before hardware is ready:
`prims` and `tiles` must be checked, in addition to the exit code. The wait
does not change the initial state or the comparisons and does not measure the game's FPS.

`--checkpoints-sync`, together with `--repeticiones N` with N greater than 1, compares
FNV-1a64 fingerprints of the 4 MiB of VRAM after Flush, Sync, Present and End.
It reports the first checkpoint that varies between passes, with record, operation and
accumulated draws. The exact comparisons of End, state and frames
are kept. A different fingerprint also produces exit code 1, even if End matches.
The history is limited to 4096 checkpoints and an excess is rejected before
repeating draws. It adds readbacks and may change timings: it does not measure FPS.
TEXFLUSH is excluded because it does not drain a GPU batch in the current backend;
observing it with readback would introduce a new cut. The fingerprints serve to locate
variation and do not certify byte-for-byte equality of the intermediate states.

`--hasta-registro R` ends the repetition at a recorded Flush, Sync, Present or End,
with `Initial=0`. It lets you narrow a difference down to a short stretch
without adding a cut between draws. It checks the boundary before creating the
backend; it rejects Submit, TEXFLUSH, nonexistent indices and duplicate options.
On a prefix it compares exactly the 4 MiB and the CPU/candidate state and the
presentations that already happened. The original End and the rest of the capture
remain unvalidated; selecting its End record keeps the full
check. The limit of 4096 checkpoints applies only to the selected stretch.

## Explicit presentation during the profile (2026-10-09)

`tests/perf_guard_test.ps1` runs the real scripts with simulated processes.
It checks that RAM mode replaces an inherited `PS2X_GS_DIRECT_PRESENT=1`,
that shared mode replaces a value of 0, that both restore the environment
and that shared/CPU fails without starting processes. It keeps the checks for
initial and supervening external load, log mark and exclusive closing
of the script's own PID. The previous version of the script fails by inheriting the
shared mode in RAM; the corrected version passes. The game is not run in these
checks.

The real four-pass comparison is documented in
`presentation-performance.md`; its game-derived files are
private and are not used as CI fixtures.


## Hardware discard outside coverage (2026-10-09)

Patch 77 adds `OpenGL hardware preserves thin subpixel triangle coverage
and blending`. It compares the 4 MiB of VRAM exactly against CPU using thin
triangles, blending, scissor and non-zero initial VRAM. It repeats during asynchronous
preparation and requires a hardware pass without increasing compute tiles. The
Windows suite passes 624/624, with 34 real OpenGL checks, both with
`PS2X_GS_HW_DISCARD_UNCOVERED=0` and with the value 1. The pixel result
is equivalent in both modes; the timing measurement is done separately.

Full official build and conditions of the four game passes:
`render-fragment-discard.md`. The synthetic trial and the game
logs remain private and are not part of the CI fixtures.

## Presentation capability when recording GS (2026-10-09)

`tests/gs_replay_test.cpp` checks the decorator and `GS::usesSharedPresentation()`
with RAM/shared capability, both directly and inside
`GSThreadedBackend`. It is initialized before querying the effective capability.
The queries do not Flush/Sync/Present nor start the capture: the file
is left reduced to its header. The check fails with the previous decorator and
passes when forwarding `UsesSharedPresentation()` under its mutex. The query does not
require OpenGL nor change the capture format.

`scripts/compilar_replay_gs.cmd` passes in full, including parser, truncation,
TEXFLUSH, checkpoints, CLI, feedback and procedural oracles. The quick
recompilation of the executable finishes with code 0 on the already-validated private runtime of 77
patches; this change only affects the port's header.

The functional 140 s check confirms real ISO, host on shared texture
with the recorder active, level ready and a complete private capture of 27,553,921 bytes.
The capture at 90 s of the pad shows Kratos, deck, rain and HUD. The CPU replay
of the End differs by 343,007 bytes: the trial does not certify game parity.
That divergence is left as a separate render investigation; the file is not
published. Closing by limit does not prove normal closing nor measure FPS.


## Feedback pattern height (2026-10-09)

`tests/gs_feedback_height_cli_test.py` verifies heights 1/31/32/33/64/416,
freeze and invariant texels, exact default dumps, TEXFLUSH/
scissor separations and the equivalence of the 4 MiB between GIF and CPU End. An incorrect
expected height fails; limits and duplicate options fail before creating files.
The single-row case independently pins the CPU RGBA `(141,90,98,128)` of
pixel `(32,0)`. The previous generator fails when asked for a reduced height.
Local Windows checks and GPU reproduction: `minimum-bilinear-feedback.md`.

## Texture cache persistence across Submit (2026-10-09)

`tests/gs_texture_cache_causality_test.py generator replay` checks 54 procedural
CPU patterns, with two passes of the `--invalidar-cache-submit` probe per
pattern. Reference and End are strict: a tampered End returns 3. The differing
bytes (3/93/96 up to 32 rows; zero from 33), the cache bases and bytes,
the RGB of the single pixel, stability between passes and the checks for
TEXFLUSH, scissor, disjoint texture and nearest are pinned. GPU, incompatible options and
duplicates are rejected before creating output. The previous CLI fails this check.

The probe only acts on the CPU candidate; it does not alter the game's renderer.
Commands, results and limits: `minimum-bilinear-feedback.md`.

## Model sampling in the intro (2026-10-09)

`tests/model_probe_test.cpp` tests that exhausting the quota or the 64 menu slots
does not consume the intro ones. It checks aliases, independent views, two-second
intervals, 32 samples per pair and the slot limit. It also tests
reading matrices with synthetic NaNs, joint indices, truncated memory,
null pointers, addresses that cross the segment and intact RAM.
CI runs it without the game, with GCC; the local MSVC check passes with `/W4 /WX`.

`GOW_MODEL_DIAG=1` logs the pose and raw matrices on entry to ProcessModel.
It does not force its update nor change the view selection. Samples are
identified by phase, model, view and ordinal; the elapsed time is host time
and the object/skeleton marks are hierarchy marks, not frame numbers.
Do not use these runs to measure FPS.

Full Windows build with 78 patches succeeded. Two 95 s checks
on the same binary (SHA in ESTADO): with models active, 343
samples in the intro and 1,016 finite matrices in total are obtained; without models, 128
camera samples in the intro are obtained. Neither logs state 11. Ended by
controlled limit; game, visual equivalence and FPS are not verified here.
A mutation that shares quotas between menu and intro makes the test fail.

## PCSX2 local EE reference (2026-10-09)

In a private PCSX2 profile, enable PINE on a free port (local check:
28012), boot the SCUS-97399 edition and pause the desired scene. The tool
uses only identity, status and Read32 of the
[official PINE protocol](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/PINE.cpp).

```powershell
python tools/render/pcsx2_ee_reference.py --port 28012 --output logs/pcsx2_intro_01
python -m unittest discover -s tests -p test_pcsx2_ee_reference.py
```

The output directory must be new. Inside the repository only `logs/` is accepted;
do not upload `eeMemory.bin` or the savestates. It rejects a game that is not
paused, a different edition and a hierarchy/identity mark that changes
during the read. The pause and that stable mark do not amount to synchronization
with a port frame. `active_view=0x0` between frames is a valid
observation, not authorization to read a supposed view at address zero.

Nine game-free checks cover TCP fragmentation, Read32 and address,
ranges and alignment before sending, invalid/truncated responses, failure or
disconnection, pause, edition, strings with length/terminator, capture
stability and protection of tracked directories. CI runs them. The
real 32 MiB check in the intro passed and matched an independent read;
identity, hash, configuration and limits are recorded in ESTADO.

## Model joints and camera parent (2026-10-09)

`GOW_MODEL_DIAG=1` adds `[gow-model:joint]` for the first eight matrices
of the palette, up to the skin count and with RAM bounds per matrix. It keeps
phase, model, view, ordinal, index, address and the 16 components as bits.
It does not replace the root samples nor change their quota/interval.

`GOW_CAMERA_DIAG=1` adds `[gow-camera:parent]` and `parentJointWorld` after
SetupPipeline: client parent, skeleton, stamps, array and selected
joint. `validJoint` means that matrix could be read within RAM;
it does not by itself verify the identity of the hierarchy. The skin count is not
applied to the camera: the PCSX2 reference's parent has that field at zero and
its joint 1 is valid. A joint `0xFFFF` uses local and does not request
a matrix from the parent's palette.

The synthetic checks cover NaN bits without operating on floats, intact memory,
aliases, count 0/3/20, the eight-matrix limit, null pointers, exact read
of 64 bytes and segment crossing. The C++ reader over PCSX2's private RAM
obtains the eight matrices of models 125/103 and the same matrix by bits
in viewWorld, clientWorld and parentJointWorld. A mutation of the palette stride
from 64 to 32 bytes makes the model check fail.

Full Windows build with 79 patches succeeded. The native check of
95.612 seconds logs 656 finite, not entirely
null articulated matrices. The 32 valid camera samples match by bits in viewWorld,
clientWorld and parentJointWorld. In the intro there are 32 samples for each index
0..7 of both articulated models; joints 3..7 of model 125
change while their root stays constant. The check ends by
deliberate limit, with no state 11 records; it does not measure FPS nor validate the full palette.
Binary identity, comparison and limits: ESTADO.

## Full articulated palette (2026-10-09)

`GOW_MODEL_DIAG=1` together with `GOW_MODEL_PALETTE_DIAG=1` adds
`[gow-model:palette-joint]` and `[gow-model:palette]` in the same ProcessModel
samples. It includes the skeleton mark, index, address and bits of each
matrix. It reads up to the skin count or 256 joints, whichever is
reached first. That maximum limits the diagnostic output; it does not modify the game's
hierarchy. It stops at the first matrix outside RAM. `requested`, `read`
and `complete` distinguish a full read from a truncated one; they do not establish
fidelity or that VU1 received those matrices. It does not emit palettes without a
readable non-zero count. The previous eight records remain available.

Game-free synthetic check: last indices of palettes 103/125, aliases,
NaN bits, 256 matrices, truncation when requesting 257, missing last byte,
null pointer and segment crossing; RAM intact. Same quotas, interval and
original call. Do not use these runs to measure FPS nor to compare different
frames as if they were a synchronized sequence.

MSVC `/O2 /W4 /WX` passes. Limiting the full reader back to eight matrices
in a private copy makes the test fail. Quick rebuild succeeded on
the same 79 patches; native check of 95.948 s: 84 full reads,
9,598 finite, not entirely null matrices. In the intro there are 32 samples per
joint of palettes 125/103. Results, binary and limits: ESTADO.

## Shared presentation acquisitions (2026-10-10)

`PS2X_GS_PRESENT_DIAG=1` logs `[gs-present:shared]` when the host acquires
a sequence different from the previous one, up to 4,096 per instance. It uses the
metadata of that texture: published/rendered sequence, host and image
ticks, framebuffer/source, dimensions, hash/validity and blank. It adds no
readback, no extra acquisition and no glFinish. The existing hash requires
`PS2X_FRAME_HASH=1`; its cost and that of the logging make this check unusable for FPS.

Since the 2026-10-11 extension it also logs `preferred` of the acquired
frame. In this GPU path, `displayFbp` uses pages of 8,192 bytes;
`sourceFbp` uses pages with `preferred=0` or blocks of 256 bytes with
`preferred=1`. The inspector keeps the old records and counts their
units as unknown, without deducing them from equality of raw values.
`source_units` includes only consistent rows. It does not change the source
selection nor verify by itself that it is correct. Fifteen Python tests pass;
native build and check of the new format pending.

`dimension_changes` reports line, sequence/render and previous/new size
of the consistent rows. It does not turn a metadata contradiction into
a valid resolution change nor link sizes between separate modes.
The inspector now has 17 passing tests; the two new regressions
fail with the previous version. Dimensions do not establish framing or aspect.

Using `GOW_PAD_TEST_NO_CAPTURE=1` with the automatic script keeps inputs and
state records without periodic VRAM captures. Remove the other diagnostics from the
environment: some are activated by presence and stay active with
value `0`. The synchronous/asynchronous FINISH and RAM/shared presentation matrix,
the private card copies and the limits of interpretation are in
[TRANSICION_COMPARTIDA.md](shared-transition.md).

The launcher resolves `--output-root` and admits, inside this checkout,
only `logs/`; it also admits external directories. It rejects a
trackable output before creating the pass. Thirteen Windows tests pass; the
regression against the previous version intercepts the directory creation.

The inspector `tools/render/inspect_shared_frames.py` detects regressions,
contradictory metadata for a sequence, retention and A-B-A returns.
A hash return is a hint; it does not prove corruption, pixel equality
or old content. Later VRAM captures also do not show which
shared texture the host acquired.

Since the 2026-10-11 check, `tick_distance` reports the minimum and maximum of
`hostTick - frameTick` and the line/metadata of the first maximum. It includes
consistent retained rows and samples without hash; it excludes contradictory metadata.
The distance can be negative if the request samples the tick after the
host. It is not time, does not measure FPS nor prove sustained latency. Zero retentions
in the summary does not rule out retentions the diagnostic did not
record.

`tools/render/run_transition_control.py` automates the matrix in new
private folders, verifying manifest/ELF/executable and using independent
cards. It records the state of our window without captures, to
distinguish minimization from loss of focus. It only stops the process it
starts; creating `STOP` in the pass folder keeps a deliberate stop
in `result.json`. Variables, arguments, protocol and limits:
[TRANSICION_COMPARTIDA.md](shared-transition.md).

## GS presentation source bases (2026-10-11)

`ps2recomp-gs-source-address.patch` compares the physical bases of FRAME/DISPFB
and TEX0 in 256-byte blocks: converting the page with a factor of 32.
The metadata keeps its original units. Two equal raw numbers
can be different bases; two different numbers can be the same base.

The game-free regressions check 32/32, 32/1,024, 32/1,057 and 0/0
(page/block) through a frontend recording backend. The CPU compositor
uses distinct procedural pixels at addresses 8,192 and 262,144,
checks zero TBW and keeps the existing criterion when the width is explicit.
The existing GPU test adds the cases 32/32 and 32/1,024 with explicit read
and CPU comparison; that read only belongs to the procedural check.

The negative check runs in CI over the regressions without the fix;
`5f3d7de` builds and fails only the two new ones (591/593 passing).
Also check the CI of the corrected HEAD. Full Windows build,
GPU suite and transition with user data are still pending. Record a new
binary before the check; do not attribute this change to the previous executable.
The identification of `preferred` in diagnostic #51 allows observing afterwards
whether these cases occur in the game. The framing and the
alternation are not declared fixed by normalizing a comparison.

The shared GPU check also verifies zero TBW and both address pairs
through `LoadImageFromTexture` on the acquired texture,
comparing all rows with CPU and the expected selection explicitly.
It does not use `copyLatchedHostPresentationFrame` as a substitute for that texture.
This readback exists only in the procedural regression; its Windows execution
with the new chain is still pending. The earlier CI of the `e52527d` fix
passes 593/593; it does not by itself establish this Windows-exclusive GPU extension.

## FINISH test configuration (2026-10-11)

The full normal and GPU suite runs with a clean diagnostics environment
and synchronous FINISH (`GOW_GS_FINISH_ASINCRONO=0` or absent). Two recorders
require that draws and FINISH be finished on return. Under the
asynchronous option those assertions do not represent its contract and the recorders may be
queried while the worker modifies them. Do not skip tests nor add
exceptions to get a green suite in that configuration.

`tests/gs_finish_async_test.cpp` runs separate `default` and
`async` processes: it verifies return and CSR according to the mode, holds the backend through
a procedural gate and requires the order draws -> FINISH -> read and that the read
always waits. CI validates both. Reproduce that specific check on
Windows, in addition to the normal/GPU suite, before reporting asynchronous validation.
The additional Windows trial of the whole asynchronous GPU suite of 96 patches is
kept as 623/625, without declaring success nor modifying the runtime expectations.

## FINISH and shared pixels on Windows (2026-10-11)

With the full chain of 97 patches (`f51cc2c`), 593/593 normal,
627/627 real GPU and `gow_gs_finish_async_test default|async` in new processes pass.
A check with real GPU/WGL context and CPU reference is added:

```text
cmake --build <runtime-build> --target gow_gs_shared_finish_test
<runtime-build>\gow_gs_shared_finish_test.exe default
<runtime-build>\gow_gs_shared_finish_test.exe async
```

The build must include `tools/ci/pruebas_gs.cmake`, as CI does for the
procedural checks. This target is defined only on Windows; it needs
OpenGL 3.3 and texture sharing, and it fails if there is a fallback or no new
sequence arrives. It fixes FINISH and direct presentation before creating the backend;
run each mode in a separate process, with a clean GOW/PS2X environment.

Both modes pass: 16 FINISH/publications, alternating preferred/CRTC selection,
known pixel and all rows compared with CPU, ticks/sequences and the
64x64 -> 64x96 change when reusing the eight slots. Only this check downloads the
acquired texture; it does not change the host's normal path. Do not request heights
below 64 here: the CPU interprets them as invalid configuration.
The initial comparison with height 48 is kept as failed and non-equivalent,
without modifying the CPU renderer. Do not claim FPS, game fidelity, correct
camera or absence of alternation from these procedural tests.

## 97-patch matrix and wait sampling (2026-10-11)

The runner `f51cc2c`, SHA-256
`ba80364535c22d728058ad98bf8182937f36c2db9ada5a11063f684c1a57add0`,
completes 360 s checks: asynchronous/shared and both RAM report state 11;
synchronous/shared stops reporting after state 4 at 25.31 s.
The details, the minimization and the accidental overlap of ~30 s at the end
of synchronous/RAM are in ESTADO.md. The first asynchronous/RAM run, stopped at
34.35 s, is discarded and repeated in isolation. Do not use these times to compare FPS.

Per-PID sampling with symbols is performed after observing the wait,
only on our instance: two windows of 5 s. It locates EE work in
a COP0.Count loop; the GS worker waits for commands during those samples.
Keep the sampling perturbations and the captures together with the result.
Do not conclude driver blocking nor remove fences from a game
wait that has not yet been explained experimentally.

An external PrintWindow capture of our own visible, non-minimized window
allows reviewing the surface even if it is not in the foreground. Always check
PID, path and window ownership; reject a minimized capture
or one after closing. By itself it still does not identify the acquired
GS sequence nor replace an aligned comparison with PCSX2. Private images.

## COP0.Count counter (2026-10-11)

`ps2recomp-ee-cop0-count.patch` adds the counter clock to the runtime and changes
the MFC0/MTC0 emission. It requires `scripts\2_compilar.cmd`: the previously generated
executable keeps reading the stuck field even if overrides are recompiled.
The four game-free regressions check bounded advance/polling, global state
and wrap between contexts, reset and emission with $zero destination. The negative check
of #59 keeps the previous semantics through compatible APIs so that behavior
failures can be checked; it is not used with the game nor as the final HEAD.

The positive integration of 98 still has to complete build, suite,
CI and transition. The finding of the sampled loop does not by itself prove its
functional effect. Record another runner commit/hash and compare first
the synchronous shared wait, keeping the optional threads off.

Integrated Windows of 98 (`f36936e`, runner SHA-256
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`):
597/597 normal and 631/631 real GPU pass. FINISH/read
and FINISH/acquired texture also pass in both modes, each in a new process.

The game pass starts after builds and checks finish;
these procedural tests do not prove a solution to the wait or the camera.

First synchronous/shared pass with that runner: 360.08 s by limit,
card intact, none of the searched error signatures; it reaches report 11 at 145.14 s.
It gets past the 96/97 wait after 4. External captures show scene
progression and later HUD/Kratos/enemy, with no aligned comparison.
1,910 acquisitions, 25 A-B-A (none in stretches 4/11), no regressions,
inconsistencies or unknown hash; maximum distance 34 before the first
report, 1 in stretches 4/11. Asynchronous/shared is repeated afterwards, without
overlapping instances. Do not present this as a benchmark or a solution to the framing.

The isolated matrix of 98 is now complete: all four combinations reach
report 11, including both RAM checks (126.41/121.31 s) and the asynchronous
shared one (116.40 s). Each check lasts 360 s and ends by limit, cards
intact and none of the searched error signatures; none minimized or overlapped. #59
merged with final CI green. The times and private captures do not prove FPS,
camera fidelity or absence of alternation; details of each case in
`shared-transition.md` and `research-log.md`.

After the matrix, evaluate `--vu1-thread 1 --gs-front 0` in a new pass
with a different label. The GS front requires VU1 in a thread: its subsequent check
uses `--vu1-thread 1 --gs-front 1`. Do not attribute to isolated GS what is observed in
that combination nor use these checks with hash/diagnostics as benchmarks.
Keep runner/manifest/inputs/card and verify that the previous pass
finished before starting another; do not stop other collaborators' processes.

With threads it is observed that the diagnostic quota runs out before the game starts.
Chain 99 adds `PS2X_GS_PRESENT_DIAG_FROM_TICK` and the launcher
`--diag-from-tick <uint64>`: inclusive start according to `hostTick`, quota unchanged
at 4,096 per instance, without acquiring/reading/synchronizing more textures. Use a
different pass for the late window and keep the boot check;
ticks are not seconds nor an alignment mechanism with PCSX2. The option
does not exist in the 98 runner: it requires a full build of chain 99.

VU1 alone completes 360 s; VU1+GS front exits at 228.17 s with code 0 and unknown
cause, before the limit. Record `process_exit` and keep it as
incomplete, repeat in isolation; reaching state 11 does not establish stability.

The full chain 99 (`3dbac1a`, runner SHA-256
`cf063d2f03a1a78f455a9ff57a1378cd4a1ddaf71e6d279d305b34663b96fa07`)
passes 600/600 normal, 634/634 real GPU and the four independent contracts
of FINISH/textures; CI of the same code green. Game repetition pending.

The previous checks with `GOW_FAST_BOOT=0` included old
animation/flash-ready probes: the overrides registration checked for presence even though
the shortcut required `1`. The later `src/` adjustment requires `1` also to
register them. Quickly rebuild on the full runtime of 99 and
note another hash; verify that `[gow-animation]` and
`[gow-flash-ready]` do not appear when there is no explicit animation/path diagnostic.
Keep the previous results with that limitation, without using them as FPS.

## Parity of the A-B-A returns (2026-10-11)

The inspector keeps all returns and adds `frame_ticks` with the three
ticks of the acquired textures, plus `content_return_parity`: `alternating`
if the parity is 0-1-0 or 1-0-1, `same` if all three coincide and `other` for
the remaining cases. It uses `frameTick`, not the tick of the host that acquired afterwards;
a retained sequence does not add another acquisition to that history. Changes of
mode, dimensions, unknown hash or regressions keep the earlier separations
of the history. 20 Python tests of the inspector pass.

Field presentation can produce legitimate A-B-A content: the native GPU
suite includes a pattern with invariant VRAM and distinct even/odd fields,
compared against CPU, also with GoW timing. However, this record
does not contain SMODE2 nor does it show that the game is in that mode. The observed
parity does not confirm interlacing, cause of the return, pixel equality or
absence of an old image; it serves to select the next check.

The later chain of 100 keeps the request's SMODE2 in the published texture
and adds an optional `smode2` to the same acquired record. It requires a full
build; the runner of 99 lacks that metadata. The inspector's `smode2_values`
keeps the modes of the A-B-A and `content_return_modes` separates unknown,
three field modes (`(SMODE2 & 3) == 1`) and others. Old logs are accepted
without inventing their mode from the parity. 24 Python tests pass;
Windows/GPU real-texture regression and functional check pending.

The first native suite of 100 gets 600/600 normal and 634/635 GPU: the new test
detects a different CPU/GPU height in frame mode (`SMODE2 & 3 == 3`).
The initial result is kept in ESTADO/TRANSICION_COMPARTIDA. Its adjustment
validates all modes as metadata of new/retained textures and keeps
CPU pixel comparison in fields/progressive. For frame it prints the
dimensions through `[gs-test:mode-frame]`; **it does not certify CPU equivalence
in that mode**. The composition runtime does not change and its discrepancy remains
pending. The test revision requires a new full build and validation.

Revision `383c6b6` now completes the Windows build of 100, 600/600 normal,
635/635 GPU and four FINISH contracts. The API-compatible negative forces only
the stored mode to zero: 634/635 with a single failure of the new case. On restoring
the positive source and rebuilding, GPU returns to 635/635. The frame test
records CPU 64x128/shared 64x64; it explicitly keeps that difference open.
Game checks with this runner and acquired mode are still pending; details
and executable identity in `TRANSICION_COMPARTIDA.md`.

The three passes of 100 have now completed 360 s by limit with card intact:
no threads, VU1 alone and VU1+GS front. The late windows have 4,096
acquisitions each, all with SMODE2=2227921 (`&3=1`). Their 3,562 and 3,542
A-B-A alternate parity and keep field mode; no regressions of
sequence/render or inconsistent metadata. They validate that the bounded
diagnostic works during the game, not the visual cause, prolonged stability,
equivalence with PCSX2 or FPS. Runner identity, times and limits in
`TRANSICION_COMPARTIDA.md`. To compare pixels, an explicit capture
of the acquired pool must be used in another run; do not take as equivalent
a latched VRAM capture nor introduce its cost into the metadata record.

Chain 101 prepares a separate capture, disabled by default:
`--capture-acquired 6` saves RGBA PNG and JSON in `acquired/` of the private
folder of a shared pass. It starts from `--diag-from-tick`, at most
16 attempts; it does not capture retentions/blank nor overwrite files. It uses the
same pool as Acquire, not latched VRAM nor another Acquire. **It adds readback
and I/O**, so this pass is not suitable for measuring FPS. Without that option
no capture variables are installed, even if they were inherited. It requires
a full build of 101 and native validation before using it with the game;
regression prepared, execution pending. Details and limits in
`TRANSICION_COMPARTIDA.md`; do not publish PNG/JSON from the game.

The capture of 101 has now completed the Windows build, 600/600 normal,
636/636 real GPU, four contracts and a compatible negative that fails
exactly on PNG pixels; source restored and GPU again 636/636.
Three six-minute passes save six PNG/JSON each, correlated
against the acquisitions. The first had minimization; the repetition without
threads does not record it. In VU1 the PNGs of ticks 5999/6001 are identical and the
one of 6000 differs: finite A-B-A confirmed in bytes, in field mode.
It does not show the age of the content nor camera/scene equivalence.
The video tick and the last script state do not by themselves align two
passes; consult identities and limits in TRANSICION_COMPARTIDA.md.

## Separating poses, camera and rasterization (2026-10-11)

#60 is now merged and its final CI/merge is correct (see ESTADO.md).
The user also observes spasms/deformations of models/animations of the
protagonist and enemies. Review motion sequences, not just isolated
images, and locate where they appear: final skinning matrices, data that
reaches VU/GS, rasterization or presentation. The palette read on entering
ProcessModel is not equivalent to the later skinning output; a finite matrix
does not certify a correct pose. Do not identify characters just by number of
joints nor compare by host clock.

Dedicated camera check: `GOW_CAMERA_DIAG=1`, `GOW_ANM_DIAG=1`, fast boot 0,
synchronous FINISH/shared/threads 0. Finite/coherent sampling of the client, with no
aligned PCSX2 game reference; details and late minimization in ESTADO.
The intro uses an articulated camera; the main samples of 11 use a local
matrix. Do not automatically carry conclusions between both cameras.

To isolate rasterization, a single private trace is repeated without EE/IOP/VU nor
launching another game. Example: `repetir_gs <trace> hardware <new-folder>
--hasta-registro 12795 --repeticiones 3 --pausa-ms 250`; also compare CPU
and compute and record primitives/tiles to distinguish a mixed path from hardware.
The number 12795 belongs only to this trace; do not reuse it with another.
`--snapshot-feedback` is experimental, adds source protection per Submit,
does not emulate the PS2 cache and is not enabled to declare a fix or measure FPS.
The prefix does not check the file's End nor the whole transition. Keep
the code 1s due to discrepancy; do not count them as success. An exact GS
repetition keeps the poses it received fixed: it does not prove they were
correct before the trace was captured either.

### Later skinning diagnostic

`GOW_SKIN_DIAG=1` installs two observers of the retail calls 0x137508 and
0x137AF8 from 0x1590F0, only under state 11. The rest and all resumptions
call the original. `[gow-skin]` and `[gow-skin:slot]` are emitted only when returning
to the expected caller; a pause emits `[gow-skin:paused]` and its output is discarded,
without reconstructing arguments on resuming nor forcing the calculation to finish.

128 total attempts, 16 skeleton/view/variant combinations, up to 32
samples per combination and a minimum separation of 100 ms of host time. It is not an
exhaustive sampling nor a counter of simulated frames. It captures input a3,
f12, layout, sparse selection, mask, visibility and threshold; per slot,
previous source +0x50, world palette a1 and later real destination a2. It also
keeps the definition matrix through the ordinal of active bits,
not through the slot index; record index +4 and parent +8 are distinguished.
The
changed flag compares previous/later destination; it does not show that it was not written
if the bytes stay the same. ownerCandidate is s1 of the caller, with no confirmed
character identification. The raw data stays in private logs.

The slot count is u16 at skeleton+0x5C, limited to 256 for the diagnostic;
definition+0x10 has another meaning. Selection/mask/visibility do not prove
that the slot was updated: threshold and reuse are involved. Each
read validates 32 MiB EE RAM or 16 KiB scratchpad, including their aliases,
without normalizing invalid addresses through RAM_MASK. The observer does not
write memory nor modify calculations. It adds reads/I/O and does not measure performance.

Prepared with procedural tests of limits, non-contiguous selection, masks
and return/pause, and C++20 syntax. It requires a quick rebuild of src/ on
the full chain 101 and a functional check before using its records as
evidence; those results are still pending.

Later validation: src/ of `e0bf966` rebuilt on the full 101,
runner SHA-256 `063ea7299ffb9bb5bc413432df63f555a605225198557fc5cd753983ad2780a0`;
local tests and CI correct. A synchronous/shared pass, threads 0,
hash 0, menu script up to 68 s collects 128 complete returns of both
variants, five groups and no pause. Destination/world/source valid and finite;
world product per definition coherent for 5,629 selected and
changed slots. It does not identify characters nor certify correct animations.
The first attempt, which stayed in the menu, is kept separate; see ESTADO.md.

The acquired capture of 16 images from 1500 keeps its exact metadata
and full bytes. The log hashes are unknown by configuration;
compare explicit PNGs. Do not correlate by clock/tick coincidence
with another run or with the skinning samples. The current script only
expresses digital directions: `izquierda`/`derecha` is not equivalent to moving the
stick. Movement checks require explicit analog support
and verification of the received packet, in addition to a motion review.

The analog support described at the beginning is now being prepared for that check;
its build and functional pass will be recorded separately. The pose
probe accepts `GOW_SKIN_DIAG_FROM_TICK=<uint64 decimal>`: it waits for the runtime's
video counter without spending the quota on earlier calls, and adds
`videoTick` to `[gow-skin]`. Absent/invalid is equivalent to 0. It reuses the parser
of the GS window patch; it does not modify the clock. That counter is not the hierarchy
stamp nor does it automatically identify the acquired texture or a PCSX2
pose. It is a window selection, not proof of alignment.

Later validation of `73588d2`: quick rebuild on the full 101,
runner SHA-256 `0df18c12eb20455c0440fa26f9799f3b85be3babd7e0c0062f62f7cf5708d1be`,
local tests and CI correct. The prolonged pass records delivery through
libpad2 of the four stick directions with combined attacks; it does not collect
images/samples from 3000 and does not confirm visible movement. The window pass
of 1500 gets 128 complete returns of both variants and 16
acquired textures, with the counter recorded next to the samples. A posture
similar to the spasm pointed out by the user is reviewed. A coherent final
product does not show a correct pose nor automatically identify the model;
the prior hierarchy and VIF/VU/GS require more investigation. Full results and
limits in ESTADO.md; they are not benchmarks.

### Hierarchy update conditions

The probe adds `recordFlags` (u32 at record+0), `worldBeforeValid` and
`worldChanged`. Bits `0x6000` may call 0x136870 and transform the
computed matrix; a simple parent-by-source product is not enough in those slots.
`worldChanged` compares bytes before/after the same full call,
only if both reads are valid; false does not show that it was not written.
The previous source is kept, because the calculation may overwrite buffers.
It does not change the quota, the game, the math nor the resumptions. It adds reads
only to the requested diagnostic. Record the validation of src/ and of the check
before interpreting these fields; the earlier samples do not contain them.

Validation of `e73e844`: quick build, procedural test and CI correct;
five-minute check completes 128 returns and 16 acquired captures. In
the group of 111 slots, the large differences of the indiscriminate product
belong to four unselected slots whose bytes are retained.
The product of the changed slots without special transformation agrees
in the sample. It is not equivalent to a PS2 animation reference. In this pass, the
reviewed images already show the arm low: they do not reproduce the earlier raised
posture nor are they aligned by having the same tick. See ESTADO.md for identity,
quantities and limits; do not modify matrices based on that partial comparison.

### Selecting the GS trace by video

`GOW_GS_REPLAY_FROM_TICK=<uint64 decimal>` postpones the start of a trace
requested with `GOW_GS_REPLAY_TRACE`. It combines with state, seconds and
TEXFLUSH: all must be met. For a video window with no additional host
wait, use `GOW_GS_REPLAY_AFTER=0`, state 11 and TEXFLUSH 1. Absent is 0;
invalid values disable the capture with an error, with no partial options.
Commands before the threshold are not omitted: they reach the renderer without being recorded.
The start records the runtime's `videoTick`, not metadata of an acquisition.
It does not change the format, backend or limits nor automatically align poses with another
pass/PCSX2. The capture serializes/synchronizes and does not measure FPS; private data.
Procedural test and CPU replay correct; negative omitting the threshold fails
and restored passes. Src/ of `d5ab720` rebuilt on the full 101, CI correct.
Check with the game: start at tick 1500/state 11/TEXFLUSH, eight Presents
1500..1507 and full End. Replay up to the second Present with repeatable
CPU and hardware with differences between passes of constant path; it does not
certify parity. Both reviewed images show the raised pose of the ship
introduction. See ESTADO.md for identity, quantities and limits;
the finite matrices and that similarity neither resolve the spasm nor measure FPS.

## GOW_CHEAT: debug mode to skip combat (2026-10-15)

Disabled by default. `GOW_CHEAT` is a comma-separated list (`god`, `noenemies`, `diag`) and is used to quickly reach
later scenes without fighting (for example, after the movies Semo01 -> a01mp05 -> a01MP02):

```sh
GOW_CHEAT=god,noenemies ./ps2EntryRunner SCUS_973.99     # normal, with the movies
```

- `god`: Kratos does not lose health (the value never goes down; the HUD bar stays full).
- `noenemies`: each enemy is left with health 0 as soon as it appears, and the game's own death logic does the rest
  (scripts waiting for "all dead" advance; the following waves appear and die just the same). In addition, any damage
  to an enemy kills it. There is no need to attack.
- `diag`: logs `[gow-cheat:hp]` (health changes: object, caller, before/after; max. 300 per type) and
  `[gow-cheat] enemy spawned/kill`.
- `GOW_CHEAT_DUMP=<s1,s2,...>` (research): dumps the 32 MB of EE RAM into `GOW_CHEAT_DUMP_DIR` (or `.`) at those
  seconds since the first pad read.

Structures found (ELF SCUS-97399, by differences of RAM dumps and reading the recompiled code):
creatures (Kratos and enemies share a class, vtable at +4 = `0x2BA528`, size `0x360`, Kratos at `0x795800` in the
first level); current health at `+0x178` (float), maximum at `+0x17C`; Kratos = `[[0x29CD58]]`. `0x1E0A80` is SetHealth
(`a0`=this, `f12`=new value, clamps to `[0, max]`) and is the only health write: damage (`0x1E0A98`) and healing
(`0x1E0BA0`) go through it. `0x1DE718` resets the actor when it appears and calls SetHealth(max) from `0x1DE818`; this is how
enemies of any level are detected. The mod replaces `0x1E0A80` and, once per frame (pad read, EE
thread), sets the health of known enemies to 0.

Verified (new game with empty card, `GOW_SKIP_FMV=1`, first fight on deck): without the mod Kratos dies at around
110 s; with `god` he is still at full bar at 120 s with 47 hits received; with `noenemies` the 6 enemies of the
wave die on appearing and the later waves do too, and the tutorial/game continues. Not verified: advancing to the
crates/archers area nor other levels; enemies that are not of that creature class are not touched.
