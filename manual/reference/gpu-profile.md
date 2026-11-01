# GPU profile without waits during rendering

The `PS2X_GS_GPU_PROF=1` option emitted timestamps for every operation and
collected them with `GL_QUERY_RESULT` on every presentation. If the GPU had not finished,
that read could block. The limit of 4096 samples also caused a forced
collection inside command submission. The profiler could modify
the synchronization of the work it was trying to measure.

The patch `ps2recomp-gs-profile-async.patch` is added after
`ps2recomp-gs-hardware-profile.patch`, as patch 67. It is our own implementation. The idea of keeping pending measurements together with their frame data comes
from the [ICO PC profiler by nathanialf](https://github.com/nathanialf/ico-pc/blob/46de16d393b817290e1bbf5de63a6de10cf9575c/port/render/rd_perf.c).
No ICO code is copied nor are its shaders or game algorithms carried over.

## Collection and limits

Windows of four presentations are frozen with their timestamps, raster
metadata, primitives, tiles, pairs, maxima, flush reasons and upload hazards.
`GL_QUERY_RESULT_AVAILABLE` of each window's last timestamp is queried
before reading results. All timestamps are emitted in the same context.
The [ARB_timer_query specification](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_timer_query.txt)
guarantees that the availability of a query implies that of the earlier
queries of the same type.

Collection consumes ready windows in order, without waiting for the first
pending one. At most three closed windows are waiting, plus one active.
Each window accepts up to 4096 timestamp pairs. If capacity runs out, rendering
continues and samples are omitted; the work and frame counters keep
counting. When space is freed, the active window is closed, which may
have more than four frames, and its real divisor is used.

A report with `partial profile` has incomplete GPU times: it must not be used
to compare performance with a complete report. The `window` line shows
the real number of frames. The `per frame` format, the groups
by FBP/flags and the batch details are kept.

The print time corresponds to the **collection**, which may happen after
the measured execution. It must not be directly correlated with external
samples of the game state using only the temporal proximity of the log.
To select windows by state again, that attribution will have to be validated
or a shared frame identifier captured. The report's internal counters
do belong to the original window.

Only the backend's destruction allows pending results to be collected in a
forced way, including the last short interval. Afterwards all of the profiler's
query objects are deleted before destroying the OpenGL context.

## Verification

Eight native regressions are added in `ps2xTest/src/ps2_gpu_profile_tests.cpp`,
with simulated timestamps and without game assets:

- Busy GPU: one availability query, no result reads
  nor reuse of pending handles.
- Ready and pending windows: order, correct times and single collection.
- Original metadata and counters, even if work from another window already exists.
- Full queue: no work is lost; real divisor of a prolonged window.
- Sample limit and explicit accounting of omissions; unique handles.
- Close with a short window, full recycling and no duplication.
- Empty close without inventing frames or queries.
- Window without timestamps, with its frames and flush reasons.

The isolated Windows check builds with MSVC, C++20, `/O2 /W4 /WX`
and ends with **8/8 tests passing**. It needs neither OpenGL nor game assets.
A negative control inverts the availability guard only in a temporary
copy: it compiles and runs the eight tests, but fails four, including
the premature read. The copy is restored afterwards. This checks that the
regressions detect the failure that is meant to be avoided.

[PR #25](https://github.com/KIexster/god-of-war-recomp/pull/25) was integrated
in `43c3a47`. The proposal's CI passed both jobs. The official Windows build
with `scripts\2_compilar.cmd`, on `2f6579d` and **67 patches**, finished
with code 0 after resuming the same build after restarting the PC. The
executable is 70,229,504 bytes and SHA256
`6C035DDFFBE4FC706CAA8171AD3A6FFA642911605A3F86CE8AD3CEAC2634A470`.

When the VU1 flags changes were integrated afterwards, a run on
**68 patches** passed 596 of 597 tests: the working directory prevented
finding `instructions.h` in the VU0 mappings control. The **24 effective
OpenGL controls** passed. The next suite, already with the thirteen ring
regressions and run from the runtime root, passed **610/610** without changing
the VU0 code. The ring's final validation is recorded separately in
[Upload ring protection](render-upload-ring.md).

The functional test of the 67-patch executable lasted **240.31 s**, with a
read-only ISO, private cards, FMV skipped and the profiler enabled.
It reached state 11, `pending=0`, `levelReady=1`, and produced windows of four
frames. The reviewed captures show Kratos, enemies, ship, rain and
HUD without visible stretched polygons in that scene. Only that
instance was closed when the time limit ran out; it was not a natural shutdown of the game.

The hardware raster was active, but **the game's presentation still copies
to CPU**: the runtime does not capture the raylib context nor call the shared
texture consumer. `PS2X_GS_DIRECT_PRESENT=1` alone does not connect that
path. The OpenGL controls share contexts explicitly; their result
does not prove that the game already uses shared presentation. This will be investigated
in a separate patch. There were unrelated builds running during the test, so
these logs are not used to compare FPS.

The modification affects the profiler enabled by an environment variable. No
FPS improvement is claimed with the profiler off, and shaders,
VU1, FPU, EE, IOP or FMV playback are not modified. `PS2X_GS_GPU_FINISH_ASYNC`
is not enabled by default either.

### 2026-10-09: shared consumer connected in PR #33

The RAM presentation limitation described above corresponds to the
earlier profiler test. PR #33 connects the raylib host with the shared
textures when selecting the GPU backend and
`PS2X_GS_DIRECT_PRESENT=1`. The 241.18 s functional pass confirms the
effective mode in the log and reaches the ship scene; the diagnostic
captures remain available on demand. The CPU/RAM path remains
as the reference. Validation and limits in
[shared presentation](shared-presentation.md). The times of that pass with diagnostics
are not used to attribute an FPS improvement.
