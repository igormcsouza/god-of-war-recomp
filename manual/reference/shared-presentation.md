# Shared OpenGL presentation

The patch `ps2recomp-gs-shared-host.patch` connects the textures of the GS
producer to the game's raylib consumer. It is applied after Opus's PR #31 and
#32, without modifying its VU1 nor the EE, FPU, IOP or the FMV decoders.

## Selection and ownership

The path is optional: `PS2X_GS_DIRECT_PRESENT=1`, together with the GPU backend,
requests sharing the WGL context on Windows. The raylib window is created
before initializing the GS. If the effective backend does not share, the host
keeps the RAM presentation. The CPU renderer remains available as a
reference. The log `[gs-present] host mode` indicates the effective path;
selecting the variable alone does not prove that it is being used.

`GSHostPresentation` performs the same drawing in production and in the tests:
it acquires the published texture, keeps its dimensions, draws with a
NEAREST filter and keeps the aspect ratio and the bars. The shared
textures are borrowed and never passed to `UnloadTexture`. The previous frame
finishes its `EndDrawing` before another slot is acquired. The GS worker
is destroyed with the host context still alive; afterwards the fallback's own
texture is unloaded and the window is closed.

The display being off keeps the magenta placeholder of the RAM presentation,
640 x 448. When PMODE is re-enabled the producer's texture is recovered.
The metadata and the debug tick correspond to the acquired frame, which
may be older than the most recent presentation request.

## Queue and captures

The shared latch enqueues Present after the previous draws, without a blocking
Flush/Sync on the host. The capacity is queried on the backend's instance,
not only through the global WGL state. FINISH, VRAM reads, backend
replacement and shutdown keep their barriers.

The diagnostic captures use `forceReadback` and run on the backend's
owning thread. They compose the **current VRAM with the CRTC saved at
the last latch**, cached per generation; they are not a historical copy of
the displayed texture. This read is only done when a capture
is requested, even if the usual asynchronous readback is enabled. The
shared drawing path does not request pixels from the CPU on every frame.

## Controls without game files

Twelve controls are added: three for the shared compositor, five for the
frontend/queue and four for the real raylib consumer. They cover color
formats, offsets and FBP units, blending of the two circuits, fields,
explicit captures, FIFO with a held worker, FINISH, RAM fallback,
metadata, 1/2/non-integer scales and PMODE transition.

On Windows they run with `GOW_GS_GPU_TEST=1`. They require a raylib OpenGL 3.3
host and a truly shared OpenGL 4.6 producer; they do not replace
OpenGL with mocks. The five queue controls also run without GL.
The integrated chain contains 75 patches on the pinned PS2Recomp commit.
The base includes the upload ring and Opus's VU1 optimizations.

The twelve specific controls pass locally. Restoring LINEAR on the
published textures makes three of them fail with image differences.
The rebuilt native suite passes **623/623**, with 33 real OpenGL
controls, and the initial CI passes on Linux. Forcing Flush in the shared latch
makes two of the five queue controls fail; its bounded wait allows
finishing even with that regression. The repetition linked with the runtime
of the official build also passes **623/623**. No FPS improvement is attributed to this
path.

In incremental builds with Spanish-locale MSVC, check that Ninja
records header dependencies. On this machine it recorded zero: when
changing the size of `PS2Runtime`, old test objects caused an access
violation. The runtime and test objects were rebuilt
before repeating the suite. The old PCH of the runner also caused C3668
upon seeing the previous GS interface. `compilar.ps1` discards the
runtime/test objects and both the `.pch` and its creation object before building
the runner; deleting only the `.pch` does not force its generation in this Ninja.
`2_compilar.cmd` now returns the real build code after the pause.
Runs with old objects are not counted as validation of the
integration.

The OpenGL backend keeps the credit and the GPL-3.0 license of the code by
Taylor N. Albarnaz / LightVelox, `sotc-port` at
`ac9efa070638ad3b3accd284de6f898d5ab271d1`. The host connection and its specific
controls carry `// GOW-Port:` comments.

## Functional check of the game

`scripts\2_compilar.cmd` finishes with code 0 on revision `343404f`,
the 75 patches and the 501 private VU1 micromemories used in the
previous build. The 103 patched files match the tested
reference, normalizing only line endings and the runner include
that the script adds. The script also disables LTCG according to its
usual configuration.

The executable measures 70,469,120 bytes; its SHA-256 is
`33C012EF1BB0DC01C325027480893CDB427F406745C686FC4D8296F1BFFFE5A5`.
The functional test lasts **241.18 s**, with private card and shader cache,
FMVs skipped, GS profiler and captures active. The log confirms
`shared GPU textures active` and `host mode: shared texture (opt-in)`.
It repeatedly reaches state 11, `pending=0`, `levelReady=1`.

Thirteen 512 x 448 diagnostic captures are generated. Numbers
8 and 12 are reviewed: they show Kratos, enemies, ship, cliffs, rain and HUD without
visible stretched polygons in that scene. These captures use the on-demand read
described above; the raylib framebuffer controls verify
the presentation path and its scaling separately. No errors,
ring degradation or partial profiler reports appear in this pass.
When the time limit expires that instance is forcibly closed. The test does not
certify completing the game, FMV playback or an FPS improvement.

## Next investigation: rasterization

The log of that functional test, with diagnostics, shows in its last
reports about 50-56 ms of rasterization per presented frame and 0.02-0.03 ms of
composition. The dominant group has destination FBP 0 and flags `0x4b`: color
interpolation, texture, blending and linear filtering, according to the backend's `FIip`, `FTme`,
`FAbe` and `FLinear` bits. These are GPU times from the previous profile, not a clean
FPS measurement nor a RAM/shared comparison.

The active path reports `hardware rasterization active, expanded triangles`.
The shader checks the real coverage before shading, but keeps the
ordered interlock section even for fragments without coverage. Before
experimenting with discards or texture caches, repeat the GS chain and
compare pixels/VRAM against CPU: subpixel coverage,
filtering, texture/destination aliases and blend order must be preserved.

Do not move `beginInvocationInterlockARB`/`endInvocationInterlockARB` inside
an `if` nor place an earlier `return`. The
[ARB_fragment_shader_interlock specification](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_fragment_shader_interlock.txt)
forbids that control flow; it allows an earlier `discard`. This delimits
a future experiment; it does not yet vouch for an optimization nor its performance.
