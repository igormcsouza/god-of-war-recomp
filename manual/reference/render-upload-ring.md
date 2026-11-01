# OpenGL upload ring protection

The backend uses a persistent 64 MiB buffer divided into four 16 MiB chunks.
Before reusing a chunk, it waits for the fence of the previous work.
The original implementation ignored the result of `glClientWaitSync`:
a timeout or a failure allowed overwriting data the GPU could still
read. It also left the buffer and its fences undeleted when destroying the
backend. If the host context was still alive, the share group kept
those 64 MiB.

`ps2recomp-gs-upload-ring.patch` is applied after
`ps2recomp-vu1-fast-flags.patch`, as patch 69. It does not alter shaders, VU1,
EE, FPU or IOP. It keeps the reference CPU renderer.

## Behavior

Only `GL_ALREADY_SIGNALED` and `GL_CONDITION_SATISFIED` allow reusing
a chunk. The bounded five-second wait is kept. On timeout,
wait failure or null fence, the ring of that backend is permanently disabled,
without copying the payload nor advancing its cursor. Subsequent uploads
use the existing streaming buffers. A single line with the reason is emitted:

```text
[gs-gpu] persistent uploads disabled (...); using streaming buffers
```

This degradation protects the pending memory; it does not certify recovery
from a lost OpenGL context. It adds no unbounded wait loop nor
`glFinish` to the render. Oversized uploads and the absence of mapping
also keep the existing fallback.

When the backend is released, all retained fences and the persistent
buffer are deleted before tearing down its context. The ring's release
also runs if shader compilation fails after the buffer is created,
even if the backend had not yet been marked as initialized. OpenGL
internally keeps data that is still referenced by pending commands.

The fallback review detected another inconsistency: a streaming upload
can shrink `dataBuffer`, which is also used as presentation output
and copies. `dataCapacity` is updated with the size actually allocated so
that the next reservation grows the buffer again when appropriate.

## Regressions and evidence

The twelve independent OpenGL tests cover timeout and wait failure,
unchanged pending memory, degradation of subsequent uploads, null
fence, single release, alignment, padding, empty/null payload and size
limits. They pass with MSVC, C++20 and `/O2 /W4 /WX`. A negative control that
ignores the timeout in a temporary copy compiles and fails two of the twelve
tests: it detects the overwrite and the unsafe reuse.

The OpenGL control keeps a host context alive while it creates and destroys
the backend. It requires a truly mapped 64 MiB ring, renders a procedural
sprite of non-zero color and compares the 4 MiB of VRAM exactly against CPU.
The previous runtime fails because the buffer still exists after
destroying the backend; the fixed version passes. It uses no game assets
nor getters added to the product. The partial initialization case is reviewed
in the code; this test does not force a shader compilation error.

The GL fallback regression uses two reads of 33,546,240 bytes and, between
them, an upload of 16,785,408 bytes plus its descriptors. This exceeds the
chunk and actually shrinks the buffer through streaming. It uses the public
GS API and procedural colors that make the VRAM aliases idempotent.
It compares both complete reads and the 4 MiB of VRAM against CPU; it also observes
the real ID and size of the OpenGL object. The previous library
fails three checks: it does not grow the buffer, differs from the CPU on reading
and keeps bytes of the previous color. The first read and the upload do
match, so the failure is isolated to the later reservation.

The fixed library also passes the positive capacity control:
**1/1**, with both complete reads and the VRAM exact against CPU.
The final integration of `e1a9270` passed **611/611 native tests**, including
**26 effective OpenGL ones**, after the official build with
`scripts\2_compilar.cmd`, code 0 and the 501 local micromemories.
The executable is 70,229,504 bytes, SHA256
`4066E704CDF1357FE74ECC21D7FF4E0834811B2812B240389BB147676D4530A3`.
The 97 patch sources match the compiled runtime, normalizing
only CRLF and the runner include added by the script. Both CI jobs of
PR #30 pass.

The base later incorporated the changes published by Opus in `ca69e9b`.
The new official build of the joint version (`2c8a8c1`) finishes with
code 0, the same 69 patches and 501 micromemories. The executable is
70,457,856 bytes, SHA256
`6EFA10AF433560B7884AE3363BE856B0BEFA0AFE5F1C16E48C990CE341D0EB59`.
**611/611 tests** pass again, including the **26 OpenGL** ones, and the
97 audited sources match the chain.

A first functional attempt ended at 40.24 s, still on the initial
screens; it does not count as gameplay evidence. The repetition of `e1a9270`
lasted **240.25 s** and reached state 11, `pending=0`, `levelReady=1`.
The captures show Kratos, enemies, ship, rain and HUD, without visible stretched
polygons in that scene. The joint-version control lasts
**241.34 s**, reaches that state and its reviewed captures also show
Kratos, enemies and HUD on the ship. No ring degradation
warnings appear. The profiler emits a partial report with 2587 samples omitted,
per its capacity limit: those GPU times are incomplete and are not useful
for comparing performance.
Private cards and skipped FMV are used; the shutdown at the end of the time limit is
forced and does not certify completing the game. No FPS improvement is attributed to this
patch.
