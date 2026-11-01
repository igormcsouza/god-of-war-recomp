# Discarding fragments outside coverage

The hardware renderer generates conservative geometry and checks GS coverage
in the fragment shader. On thin triangles, a good part of the rectangle does not
cover triangle pixels, but those fragments still entered the ordered
section of the interlock even though they wrote neither color nor depth.

`patches/ps2recomp-gs-discard-uncovered.patch`, after the per-folder
generator, adds `discard` when `coversPixel`/`shadePrim` reject the fragment.
It keeps the existing coverage check, shading and blending.
`beginInvocationInterlockARB` and `endInvocationInterlockARB` stay outside
branches; the write condition for helper invocations is also kept. The [ARB specification](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_fragment_shader_interlock.txt)
allows earlier discards, but forbids wrapping those calls in an `if`
or placing an earlier `return`.

`PS2X_GS_HW_DISCARD_UNCOVERED=0` keeps the previous shader for comparison.
The default value enables the discard. The selection is read when the
renderer is prepared; it is part of the GLSL source and, therefore, of the shader cache
key. It does not change the CPU renderer or the compute path.

## Procedural control

The new control draws eight thin triangles with subpixel coordinates,
both winding directions, color interpolation, blending, clipping and a degenerate
primitive over non-zero initial VRAM. It compares the 4 MiB exactly
against CPU, including pixels outside the coverage. It requires observing
a real hardware pass, without increasing the compute tiles.

The cold variants start in compute while the shader is compiled on
another thread. The control resets the VRAM and repeats with a bounded wait of
20 seconds until hardware is observed; it checks the pixels of each pass.
It does not accept equality obtained solely through the compute fallback. The discard
is an optimization that must preserve the outputs: the image control
must also pass with the previous shader.

## First timing trial

A private trial on an RX 5700 XT prepares the variant before the stopwatch,
submits 4096 thin triangles about 124 pixels on a side and ends with FINISH.
It is checked that the measured samples do not fall back to compute. Five samples
with the previous shader give 25.04-25.94 ms; with discard, 16.63-18.35 ms.
Both variants pass the CPU VRAM control. These are elapsed times
of that synthetic batch, not game FPS nor an estimate for the whole scene.

The existing OpenGL adaptation keeps its GPL-3.0 license and the credit to
Taylor N. Albarnaz / LightVelox, `sotc-port` at
`ac9efa070638ad3b3accd284de6f898d5ab271d1`. The discard and its control are
our own changes marked with `GOW-Port`.

## Integrated verification

The Windows suite with real OpenGL passes **624/624** with discard disabled
and **624/624** enabled; it includes 34 OpenGL controls. The CI of `54b7107` passes
both of its jobs. The official build with `scripts/2_compilar.cmd` finishes
with code 0 and 77 patches, keeping the 501 private VU1 micromemories.
The 103 patched files match the tested reference, normalizing
line endings and the runner include; the script's usual LTCG deactivation
is left out of that source comparison.

The executable of `54b7107` measures 70,469,632 bytes; its SHA-256 is
`706ACF0D64CD601E935C2050ACF184730B5698DBF2BE3D82A57C5BD68427D3F6`.
This same binary is used with the 0/1 option in the game comparison.

## Selecting the game segment

All four passes use shared presentation, a frames-only profile, an initially absent
card and the same private cache folder. They alternate
discard 0, 1, 1, 0 for 180 seconds per process, without captures or
GPU diagnostics, with monitoring for other games and builds.

The preload separates the profile clock from the controller clock by about 38 seconds in
the first passes and about 5 after preparing the cache. The planned
initial profile interval of 100-170 seconds mixes different moments
of the entry sequence; it is not used to attribute an improvement to the shader.

Instead, controller reports between its seconds 100 and 125 are delimited,
with state 11, `pending=0` and `levelReady=1`. The first profile report
after the first state bounds the start, and the last one before the final
state bounds the end. `resumir.py --partida` selects the complete windows
between those limits by line order, without equating both clocks. This leaves
about 15 measured seconds per pass; the effective interval is kept.

The controller uses real time and is not a deterministic replay of the game.
The sampled states do not prove equality of all enemies or animations.
The short sample and the two repetitions per mode limit the conclusion to this
observed segment; they do not certify a stable percentage for the whole game.

| Pass | Discard | Profile limits (s) | Windows | Measured time (s) | `guest_flip_hz` |
|---|---|---|---|---|---|
| 1 | 0 | 143.55-158.58 | 3 | 15.03 | 6.857 |
| 2 | 1 | 143.01-158.01 | 3 | 15.00 | 7.200 |
| 3 | 1 | 105.02-120.03 | 3 | 15.00 | 7.333 |
| 4 | 0 | 105.02-120.04 | 3 | 15.01 | 7.060 |

The time-weighted average is **6.958 frames/s without discard** and
**7.267 with discard** (+4.43 %). It counts `vid::Flip` calls at
`0x001837B8`, not the host's 60 Hz refreshes. Both modes confirm
hardware rasterization and a loaded game. The monitoring detects no builds
or other game during the four runs.

The limits in the table allow repeating the selection with
`python tools/rendimiento/resumir.py <registro-privado> --partida --desde <inicio> --hasta <fin>`.
The alignment was chosen upon detecting the clock separation, before completing
the fourth pass. The logs and cards are private. The comparison uses the
same new executable and does not attribute to the discard differences with earlier binaries.


## Functional control of the executable

A 240-second run with discard 1, shared presentation,
GS diagnostics and captures uses the binary with the indicated SHA. The real ISO is
confirmed in the log; the test controller goes through the menu and reaches
state 11, `pending=0`, `levelReady=1`. The captures at controller seconds
90, 160 and 190 show Kratos, the deck, rain, HUD and enemies in combat.
They are diagnostic captures of the current VRAM with the CRTC latched, not an exact
CPU comparison of the game nor a certification of all its effects.
The process is closed by the trial's time limit: it does not prove normal shutdown.
The diagnostics rule out using this run as an FPS measurement.

The first private attempt did not load the ISO because of a path with accents read
with the wrong encoding in its PowerShell launcher. It is excluded from the functional
control and kept separately; the repetition fixes the encoding.
The four performance passes do confirm a real ISO and a loaded game.
