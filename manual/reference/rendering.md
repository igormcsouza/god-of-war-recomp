# CPU and OpenGL renderer

`patches/ps2recomp-gs-opengl.patch` adapts `GSGpuBackend` and `GSThreadedBackend` from the fork
by [Taylor N. Albarnaz / LightVelox](https://github.com/LightVelox/PS2Recomp/tree/ac9efa070638ad3b3accd284de6f898d5ab271d1),
branch `sotc-port`, commit `ac9efa070638ad3b3accd284de6f898d5ab271d1`, under **GPL-3.0**.
Thanks to its authors for the backend and for the work on the
[sotc-vibe-pc](https://github.com/LightVelox/sotc-vibe-pc) port. The imported files carry
`// GOW-Port:` and the full origin commit. The GPU helpers are kept separate from those of
the existing CPU renderer so the comparison is preserved.

The CPU remains the default. The patch only modifies the GS, its CMake integration
and its tests. It does not modify EE, FPU, IOP, VIF, VU1 or `ps2recomp-fpu-roots.patch`.

## Selection

After `scripts\2_compilar.cmd`, in PowerShell:

```powershell
# Direct CPU: preserved reference.
$env:PS2X_GS_GPU = '0'; $env:PS2X_GS_THREAD = '0'

# CPU on the GS thread: lets you separate the effect of the queue from GPU rasterization.
$env:PS2X_GS_GPU = '0'; $env:PS2X_GS_THREAD = '1'

# OpenGL on the GS thread.
$env:PS2X_GS_GPU = '1'; $env:PS2X_GS_THREAD = '0'
scripts\ejecutar.ps1 -Segundos 150
```

This adaptation creates a **WGL context on Windows with OpenGL 4.6 shaders**. It uses graphics
rasterization when the required functions are available, with a compute path for the other
cases. If the context or the initial shader compilation fails, the wrapper switches to the CPU and
emits `[gow-gs] OpenGL no disponible; usando CPU en el hilo GS.`. That fallback does not count as
GPU validation. On Linux the backend is compiled, but its context is a stub and it uses the fallback.

Reads, FINISH and Flush respect the preceding commands. The queue copies the data sent
by the EE, preserves state changes and drains its last commands before destroying the context
on the owning thread. The VRAM tables are initialized once. Presentation is adapted to
the 640-pixel rows of the existing frontend; the shared presentation between
the fork's GL contexts is not integrated yet. The output goes through the port's usual pixel copy.

`ps2recomp-gs-presentation.patch`, applied after the backend, adds the frontend's
`preferredSource` selection with the same conditions as the CPU for a single active
circuit. That source is a texture based on **256 B blocks**; `DISPFB` uses **8 KB
pages**. The shader receives block bases: it converts the CRTC base once and keeps all
the bits of the preferred source. It uses its stride/format and zero origin, without altering the CRTC
destination. The supported formats are CT32, CT24, CT16 and CT16S. Two active circuits keep
the CRTC composition. The provenance of the image is kept in the deferred readback and
the selection is included in the shared presentation key, although the latter
remains disabled in the port's integration.

With `SMODE2 & 3 == 1`, the compositor duplicates the rows of the field selected by
`vsyncTick & 1`: even and odd alternate using the real GS parity. The shared
presentation key also includes the field. Progressive mode keeps its rows
and does not depend on that parity. With a single active circuit its RGB is shown directly,
without blending it against the background by the pixel alpha; with two, the PMODE blend is kept.

In the **initial test prior to this fix** the menu is seen with defects and, in state 11, dark water without
Kratos or the full environment. The late OpenGL captures from `56–130 s` are identical;
those of the CPU from `70–130 s` change. The improvement in `vid::Flip` does not equal more distinct images.

The presentation regressions run with a real GPU, both compute and graphics
rasterization. They compare the four formats against the CPU, a source not aligned to pages, a different
stride, a non-zero CRTC origin and later updates. They also check an incompatible
destination, a missing source, an unsupported format and the composition of two circuits. They compare
even/odd fields, progressive mode and pixels without alpha. Another sample uses the full
GoW timing with a synthetic 512×448 pattern, without game assets. Before the fix
both GPU tests fail (**472/474**); with the fix **474/474** pass.

The game's temporal observation found two active circuits, with no preferred source,
with `PMODE=0x8023` and field mode. Both compositors were compared on the **same VRAM
obtained from the GPU**: the images differed because the CPU selected the field and OpenGL
omitted that parity. This narrows
that difference to the compositor, without attributing it to VU1 or to a general vertex-write
failure. The temporary diagnostics were removed after the cause was located. Field alternation
on its own does not establish animation or a playable game.

A 155 s run with the fix, before integrating EE/FPU, initializes the real GPU
without fallback and reaches state 11. The four captures from `70–130 s` are distinct,
as opposed to the earlier identical late captures. Dark water still appears, without
Kratos or the full environment. This check verifies the compositor output;
geometry and a playable game remain pending.

After integrating Opus's EE/FPU patch and rebuilding the 6,418 units, the native suite
with a real GPU passes **481/481**, and the separate GS cache tests **45/45**. The
earlier figures of 474 correspond to the runtime prior to that integration.

The combined game test also reaches state 11 without fallback. With the
diagnostics enabled it saves three distinct captures at `94.85 / 95.19 / 110.10 s`,
with water and artifacts; still without Kratos or the full scene. It is not a performance
profile. The observed positions keep the loader's deliberate template
and the two changing non-zero buffers; see the log in `research-log.md`.

## Reproducible comparison

```powershell
scripts\probar_rendimiento.ps1 -Renderer cpu -SoloCuadros -Etiqueta gs_cpu
scripts\probar_rendimiento.ps1 -Renderer cpu-hilo -SoloCuadros -Etiqueta gs_cpu_hilo
scripts\probar_rendimiento.ps1 -Renderer opengl -SoloCuadros -Etiqueta gs_opengl
```

Runs must be consecutive, with the same ELF, ISO, binary, controllers and scene, with no
captures or heavy diagnostics during profiling. The script restores the variables when it finishes.
Compare `vid::Flip` in state 11 and host presentation separately. The exclusive
EE/IOP/GS/VU split of the original profile describes the game thread; when the GS is moved to another thread it no longer
accounts for all of its work and is not useful for comparing cost percentages between renderers.

Local test of 2026-10-05, AMD Radeon RX 5700 XT, same binary and three consecutive
runs. In each one, three complete 5 s windows are taken within `120–136 s`,
with the game in state 11. Captures and geometry diagnostics are omitted:

| Renderer | Game `vid::Flip`/s | Host presentations/s |
|---|---:|---:|
| Direct CPU | 2.40 | 56.33 |
| CPU with thread | 2.39 | 55.68 |
| OpenGL with thread | 3.26 | 59.12 |

In this sample, OpenGL improves by approximately 36% over the direct CPU. These are calls
to `vid::Flip`, not distinct images nor a measure of playability. One run per mode
and about 15 s of observation are an initial comparison, with no estimate of variability. The GS thread
with CPU does not provide an improvement in this sample. Captures are reviewed in separate runs.

The normal suite checks payload ownership, transfer order, compact states,
barriers, queue destruction and direct CPU/threaded CPU equivalence. It checks the
addressing and masks of the 13 VRAM formats against the existing implementation.

With a local GPU, enable the two additional tests before running `ps2x_tests` from
the PS2Recomp root:

```powershell
$env:GOW_GS_GPU_TEST = '1'
out\build\ps2xTest\ps2x_tests.exe
Remove-Item Env:GOW_GS_GPU_TEST
```

These tests require the real GPU to be initialized. They compare clear, sprites, transfers and
full VRAM; they check the inside/outside of a flat triangle, a CT32 texture and the presentation
pixels. They run both with compute forced and with graphics rasterization allowed.
They cover those synthetic cases; they do not certify full GS accuracy nor a playable game.

## Position producer

`GOW_EE_PRIM_DIAG=1` adds limited observation of `renEEPrim::InitUNPACKData` (`0x141350`) and
`GetUpdateAddress` (`0x1417D8`). It records object, caller, type, chunk, buffer and returned address;
for positions, it shows the first vector **before the caller fills it in**. A checkpoint
is labeled as such and is not treated as a return. It does not change the game's data.

Samples are limited to 64 initializations, 64 addresses before state 11 and 256 in that
state. With the automatic controller, up to 16 observed addresses are re-read every 5 s to see
later changes. Those buffers can be reused; the late read does not guarantee that the
original object is still their owner. The profile removes this variable to avoid mixing
the investigation with the measurement.
Zeros prior to the write can be a valid reservation: the buffer must be checked
after the producer and the DMA/VIF payload before attributing a failure. Repeat the test when
Opus integrates its EE/FPU semantics fixes.

The first run of this diagnostic records 64 initializations, 298 position returns and
192 later reads. The caller `0x12E258`, inside `LoadClient`
(`0x12DE70`), obtains 40 buffers. In the 14 addresses of that caller that the probe
keeps, all later reads show `(0,0,0,0x8000)`. Inspection of the original MIPS
confirms that the loop `0x12E270–0x12E288` writes precisely that template:
it is an explicit initialization by the game, not a computed position that the diagnostic
saw being lost. The first reservation includes the chunks previously observed in
the VIF payload with zero XYZ.

The caller `0x1FB800`, inside function `0x1FB4B8`, returns two buffers with non-zero,
changing XYZ, also in their later reads. No return of `GetUpdateAddress` from `goWater::InitEEPrim` or `UpdateEEPrim`
is observed in this sample. These results
narrow the investigation: follow the transformation of those templates, their data
selection and the result that VU1 delivers to the GIF; do not arbitrarily replace them with positions.

The later trace, with EE/FPU integrated, links two of
those templates (`0x812390` and `0x7F3220`) with their `LoadClient` buffers through the DMA addresses. They arrive as zero
at the UNPACK and are observed that way in VU1 memory before being transformed. The two buffers
updated by `0x1FB800` do not appear as a payload source in the eight sampled
chains; their sending remains to be identified. In the first 256 PATH1 packets
there are 2,654 vertices, 337 with kick and 2,317 without kick (ADC/XYZ3), with cases of repeated
XYZ and others of distinct positions. These results locate data and discards
prior to the GS backend; they do not by themselves demonstrate a VIF/VU1 failure nor fix
the missing scene. Addresses, replay and limits: [`research-log.md`](research-log.md).

The same variable also observes the entry of `renEEPrimContext::ProcessServer`
(`0x141B78`). It keeps up to 64 samples before state 11 and another 64 within it.
Per sample it walks up to 256 nodes, checks bounds and cycles, and records camera,
view ID/mask and membership of the objects observed by `GetUpdateAddress`.
`candidates` only counts those that pass the first camera, view and DMA index
filters in that snapshot; it does not establish later visits, rasterization or draws.
With `invalid`, `cycle` or `truncated` active, an absence from the sample does not allow
asserting that the object does not belong to the rest of the list. The records use the labels
`[gow-eeprim:context]` and `[gow-eeprim:member]`; they do not modify memory or indices and
resumptions after checkpoints call the original directly. Nor are they used to measure FPS.

## Offline GIF inspection

The inspector uses only the Python standard library and takes a binary packet
or a folder of local `gow_geo_gif_*.bin` captures:

```powershell
python tools/gs/inspeccionar_paquetes.py logs/gs_geometry_probe --json logs/gif_summary.json
python -m unittest discover -s tests -p test_gif_inspector.py
```

It validates the sizes of PACKED, REGLIST (including its padding) and IMAGE; format 3 is not
supported. It counts XYZF2/XYZ2/XYZF3/XYZ3 and A+D writes, distinguishing kick from ADC/XYZ3.
The JSON contains metrics, XYZ ranges, labels and a SHA-256 per file; it does not copy the
payloads. The PRIM types only count PACKED labels with PRE: they do not reconstruct the full
GS state nor the primitives that are actually rasterized. The X/Y values keep
their GS units, before applying XYOFFSET. A kick does not guarantee a visible triangle.

The capture for this investigation used temporary VIF/VU1 probes and a local replay, both
already removed. `GOW_GEOMETRY_DIAG` and `GOW_REPLAY_STEM` are not options of the published runtime.
Keep captures and reports under `logs/`; do not upload RAM, microcode or game data.

## PATH2 DIRECT transfers

`ps2recomp-vif-direct.patch` adapts Claude's fix in
[`540defd`](https://github.com/KIexster/god-of-war-recomp/commit/540defd): a pending IMAGE
only consumes the payload of the following DIRECT/DIRECTHL. The VIF commands between them
keep executing. The priority corresponds to the current command, even if it changes
between DIRECT and DIRECTHL when continuing the same image.

`ps2recomp-vif-direct-fragments.patch` separately keeps the pending size of a
DIRECT that arrives split between DMA blocks or FIFO writes. Its accumulator is limited
to 65,536 QW (1 MiB, also for IMMEDIATE=0). It only copies incomplete loads; the path
that receives a complete DIRECT still sends its bytes directly. Initializing memory
or writing VIF1_FBRST.RST discards that continuation and its priority.

These two patches complete the DIRECT before delivering it to the GS parser. The PACKED/REGLIST
continuation across different DIRECT commands is added later with `ps2recomp-gif-stream.patch`,
described below. Not all hardware stalls and cycles are reproduced, and no
continuation of other VIF commands is added. The behavior reference
is [PCSX2's `_vifCode_Direct`](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Vif_Codes.cpp),
which keeps the pending size and distinguishes DIRECT from DIRECTHL; its code has not been copied.
The credit for the GS port to Taylor N. Albarnaz / LightVelox given at the beginning is maintained.

The regressions check IMAGE pixels, intermediate MARK/STCYCL/ITOP commands, new
GIFtags after an image, DIRECTHL priority, PACKED/REGLIST with every byte cut
in a 32 B payload, FIFO writes, the maximum size and reset. They contain no
game data. `GOW_VIF_DIAG=1` adds up to 16 `[gow-vif-direct]` start messages and
another 16 completion messages for fragmented transfers. Do not enable it to measure FPS.

## GIF packet order

`ps2recomp-gif-order.patch` preserves FIFO order within PATH1, PATH2 and PATH3. The queue
groups by path with a strict comparison and then chooses among their heads: PATH1
has priority; a PATH2 DIRECTHL waits for an IMAGE that is at the head of PATH3.
A normal DIRECT keeps its priority over PATH3. An IMAGE is not moved ahead of its setup nor
a DIRECT after a previous DIRECTHL of the same channel.

The DIRECTHL/IMAGE exception previously used inside `std::stable_sort` did not satisfy the
[strict weak ordering required by C++](https://eel.is/c++draft/alg.sorting.general#3).
Two regressions cover all the permutations of those groups and the PATH1 priority.
This fix orders complete packets in the current abstraction; it does not reproduce all
the stalls, preemptions or cycles of the real GIF. The tests are synthetic and do not establish
on their own an improvement in the game's image or FPS.

## Empty GIF tags and PRE

`ps2recomp-gif-tag-semantics.patch` fixes the frontend shared by the CPU and
OpenGL backends. A tag with `NLOOP=0` emits no registers: it preserves PRIM, the pending vertices
and Q. The tag's `PRE/PRIM` is only applied in PACKED with data, and is ignored in REGLIST
and IMAGE. Both `processGIFPacket` and the validated native PACKED path are fixed. The
IMAGE upload shortcut also respects the PRE of the PACKED setup and the Q reset of
non-empty tags, keeping the uploaded bytes and ignoring the IMAGE's PRE.

The rule matches `GSState::Transfer` in
[PCSX2, commit 32ac6e2](https://github.com/PCSX2/pcsx2/blob/32ac6e23e4aaf8c8c5e74a6c1ed750ee7672120e/pcsx2/GS/GSState.cpp#L3371),
which references section 7.2.2 of the EE manual. The fix and the tests are our own;
no PCSX2 code is incorporated. Four regressions check the state, the preservation
of a triangle across empty tags and Q, the controls with non-empty PACKED and PRE,
and the effects of the setup on the native IMAGE upload.
This patch does not modify VIF; the continuation between distinct DIRECTs is added in the
next patch.

## GIF stream continuity per PATH

`ps2recomp-gif-stream.patch` keeps a separate cursor for PATH1, PATH2 and PATH3:
incomplete tag, format, current register, pending registers, REGLIST padding and
IMAGE bytes. Each cursor retains at most 15 bytes of an incomplete unit. Contiguous
IMAGE uploads still reach the backend in large blocks; no other copy of the complete
payload is stored in the frontend.

A new block continues the pending tag of its PATH, instead of reading its data
as another GIFtag. Q and PRE are applied when a tag completes, preserving the rules
for empty tags. The GS state and the registers remain shared; only
the read cursor is independent. Reset removes those cursors. The PACKED and DMA IMAGE
shortcuts are rejected when PATH3 has an incomplete stream, so that the general
parser completes it.

The arbiter callback keeps the PATH identifier; the earlier two-argument clients
keep their interface. VIF delivers the original bytes of each DIRECT:
the synthetic IMAGE tags that previously wrapped the continuations are removed, since
the frontend now keeps their pending size. The existing continuation test
therefore checks the original payload together with the following tag, instead of the wrapper.
MARK, STCYCL and ITOP between VIF commands keep executing.

Nine synthetic regressions check every byte cut of PACKED, ST/Q and
vertices, odd REGLIST and its padding, IMAGE and the following tag, NREG=0 (16 registers),
reset, three interleaved PATHs, the native shortcuts and a PACKED spread across three DIRECTs.
The frontend is common to CPU and OpenGL; these tests include no game files.

## Priority of IMAGE continuations

`ps2recomp-gif-image-order.patch` classifies the PATH3 stream through its tags and
pending sizes. A block of IMAGE pixels keeps its classification even if it does not
begin with a tag. PACKED/REGLIST registers and padding are not interpreted
as tags, even if their bits coincide with IMAGE. IMAGE is also recognized after a
setup within the same block. NLOOP=0 does not start an image nor block DIRECTHL.

The FIFO arbitration between heads from the previous patch is kept. The classification
covers the complete block; it remains the runtime's packet abstraction,
without reproducing the preemption or cycles of the real GIF. Reset discards the PATH3 cursor together
with the queue. Six regressions cover continuations between drains, setup followed by IMAGE,
data that looks like tags, empty IMAGE, padding/partial tag and reset. Four earlier
priority fixtures now use NLOOP=1 with pixels: their ordering expectations are
kept and the assumption that an empty IMAGE transmits data is removed.

## IMAGE2 compatibility

`ps2recomp-gif-image2.patch` treats FLG=3 as IMAGE2, following the compatibility of
[PCSX2's `GSState::Transfer`, commit 32ac6e2](https://github.com/PCSX2/pcsx2/blob/32ac6e23e4aaf8c8c5e74a6c1ed750ee7672120e/pcsx2/GS/GSState.cpp#L3489).
Its payload is consumed as IMAGE, without applying PRE, in the frontend and the complete
upload shortcut. The arbiter keeps that classification in its continuations. The earlier
name `GIF_FMT_DISABLED` is kept as an API alias. The fix is our own; no PCSX2 code is
copied nor is FLG=3 presented as a documented mode of normal use by the game.

Three regressions verify every byte cut and the following tag, the pixels
of the native upload on the CPU and on an observation backend, the setup's PRE and the arbitration
of the tag and its continuation. It has not been demonstrated that GoW emits IMAGE2 in the
observed scene; the change avoids desynchronizing the parser if it receives this format.

## Tag state in the DMA texture shortcut

`ps2recomp-gif-native-tag.patch` completes the tag effects in the
`tryProcessNativeGifImageUploadChain` shortcut. After validating the entire chain, it passes the
setup's PACKED tag to `uploadImageNative`: it resets Q and applies PRE under the same lock as
the upload. The image's PRE is ignored. It also supports IMAGE2, like the general frontend.
An optional argument preserves the earlier direct upload API without a tag.

A regression reproduces, before the fix, the loss of PRE and the old Q at the
next point, in addition to the rejection of IMAGE2. It covers IMAGE/IMAGE2 with PRE enabled and
disabled, pixels and color preservation. Another test rejects a chain with an invalid
terminator and checks that PRE/Q do not change, no pixels are uploaded and the native counter
is not incremented. The shortcut still validates all the data before applying its effects.

## 24-bit pixels across IMAGE blocks

`ps2recomp-gs-image-fragments.patch` keeps one or two bytes of a CT24/Z24 pixel
when an `UploadImage` load ends. The backend completes that pixel with the next
load and delivers the rest in blocks aligned to three bytes. CPU and OpenGL share
this small accumulator; the complete payload is not copied nor is the path of other
formats altered. Ending the transfer discards its padding. Reset and a new transfer
discard the pending bytes; exporting/importing OpenGL keeps the partial pixel.

The initial reproduction uploads 48 bytes: in one load it produces 16 pixels, but in three
loads of 16 B it produces 15 and leaves address 0 active, both on CPU and on real OpenGL.
Four regressions cover CT24/Z24 at every cut of the 48 bytes, repeated loads
of one byte and of one quadword, preservation of the high VRAM byte, reset/new transfer
and export of one or two pending bytes. Two tests require real OpenGL and two
always run on the CPU. Before the fix three fail; afterwards all 519 native tests pass,
also after the full build of 6,418 units. The audit
reproduces 26 patches and 73 sources without differences. The 175 s game control reaches
state 11 without CPU fallback; the captures at 90.15 and 110.13 s still show water
without Kratos or the full scene. The 64 observed calls to Clip in that phase
still discard with `0x80000000` and identical Y/Z. No FPS improvement is established.

## CPU triangles as a reference for OpenGL

`ps2recomp-gs-triangle-sampling.patch` removes the CPU's half-pixel offset,
preserves the four fractional bits of XYOFFSET and applies inclusion of top/left
edges. It reuses `gs_triangle_rules.h`, adapted from Taylor N. Albarnaz /
LightVelox, commit `ac9efa070638ad3b3accd284de6f898d5ab271d1`, the same as OpenGL.
The edges are computed in integers and advance by additions within each row; Z is
interpolated by differences to preserve flat 32-bit values.

The convention is described in sections 2.4.4 and 3.2.9 of the
[GS User's Manual](https://www.scribd.com/document/784545197/GS-Users-Manual):
the center of the screen pixel has integer coordinates and a shared edge
belongs to only one triangle. The conversion and traversal of the software renderer of
[PCSX2](https://github.com/PCSX2/pcsx2/blob/32ac6e23e4aaf8c8c5e74a6c1ed750ee7672120e/pcsx2/GS/Renderers/SW/GSRasterizer.cpp)
serve as an independent check; its code is not copied.

Three regressions fail on the CPU before the change and now pass on both OpenGL paths:
interpolated color at a known center, fractional XYOFFSET and two triangles with
alpha that must cover the shared edge only once, in both winding directions.
Two old STQ/linear filter fixtures are recomputed for the integer center, preserving
their ability to distinguish homogeneous interpolation from filtering. The fan fixture now
reads CT32 with its reference swizzled layout and requires exactly the interior
rectangle of integer centers; the earlier linear read invented gaps.

The synthetic full-VRAM comparison goes from 12 differences to **48/48 equal cases**
between CPU and OpenGL compute/hardware, with IIP, four Z tests and high Z32 values.
The patch's tests and the full build are recorded in `research-log.md`.

## CPU sprites as a reference for OpenGL

`ps2recomp-gs-sprite-sampling.patch` reuses the signed axes of `gs_sprite_rules.h`,
adapted from the same commit `ac9efa070638ad3b3accd284de6f898d5ab271d1` by Taylor N.
Albarnaz / LightVelox. The CPU keeps fractional XYOFFSET and UV, samples at the
integer center and computes the texture from the original extremes even when the
axes are inverted or it is clipped with scissor. A zero width or height no longer draws.
The coverage rules and the traversal are checked against GS manual 3.2.9 and the
PCSX2 software renderer linked in the previous section; OpenGL already used those axes.

Four CPU tests reproduce the failures before the change: fractional coverage,
zero area, UV with linear filter and inverted/clipped texture. Another test requires
real OpenGL in compute and hardware for the same cases. The constant sample
UV=0.75 gives `0x80000707` on OpenGL and `0x80006666` on the earlier CPU; the STQ path is
also checked. The separate full-VRAM probe goes from **14 differences
to zero in 16 cases**. The data is synthetic.

Eight old CT32 alias, CLUT, alpha and scissor fixtures used sprites with two
equal vertices and depended on the one-pixel minimum width/height that the CPU invented.
They now specify 1×1 rectangles without changing the assertions of those properties.
The new regression requires that an empty primitive not change the VRAM. The frontend,
VIF, VU1, the shaders and the EE/IOP patches are not altered.

## Constant color, alpha and fog in triangles

`ps2recomp-gs-triangle-constants.patch` interpolates Gouraud RGBA and the F coefficient
by differences between vertices, on the CPU and in the common code of the compute/
hardware shaders. It is our own adjustment to the renderer adapted from SotC. The sum of three
rounded float weights could fall below one: even with equal attributes
at all vertices it lost one unit of color, alpha or F.

It is reproduced with a 17×19 pixel triangle: on the CPU 17 centers with constant
color and 8 with constant F are altered; on each OpenGL path, 151 and 110 respectively.
The reference for color is exact RGBA; for fog it is compared with a point of the
same attributes, which uses the existing fog application without interpolating F.
The problem includes alpha 128 converted to 127, which can fail GEQUAL 128 and leave
holes even when the vertices have sufficient alpha.

Two CPU regressions and one OpenGL regression fail before the change. They verify both winding
directions, all interior centers, constant RGBA with alpha-test GEQUAL 128 and
constant F against the control without interpolation. The shader converts to float before
subtracting attributes to support negative differences without integer underflow.
The native suite passes **531/531**, including seven tests with real OpenGL. The separate probe
and the gradient comparison are recorded in `research-log.md`.

## Constant texture coordinates in triangles

`ps2recomp-gs-triangle-texcoords.patch` preserves UV 12.4 and constant S/T/Q through
interpolation by differences on the CPU and OpenGL compute/hardware. The subtractions keep
the sign to support descending UV. S, T and Q remain homogeneous values:
the division by Q is done after interpolating, when sampling the texture.

The constant Q = 1.5 regression also detected a low reciprocal on the GPU:
the first center already selected the previous texel. The shader refines `1/Q` with the
residual of an `fma` operation consumed by `precise`; it keeps the zero-reciprocal
path. It is our own GS adjustment, separate from the EE FPU. GLSL allows an error of
up to 2.5 ULP in division and specifies the use of `precise` with `fma` in
sections 4.7.1 and 8.3 of the [Khronos specification](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.4.60.pdf).

Two CPU tests and one OpenGL test fail before the change. They compare all interior
centers with a 1×1 textured sprite and explicit reference values,
in both winding directions, with nearest and linear filtering. They also check a
descending gradient and variable Q at a center far from texel boundaries.
The suite integrated with Opus's IOP patch passes **535/535**, including eight
tests with real OpenGL. Precision at exact boundaries with variable Q is still being
investigated separately; keeping attributes constant does not solve all those cases.
The independent probe confirms the hardware path using the counters of batches,
primitives and compute tiles, after a bounded wait for their asynchronous variants.

## Integration with MMI and VU0

The later integration with Opus's MMI and VU0 passes **545/545** native tests with
OpenGL. In state 11 the Y/Z duplication of the spheres disappears: 30 of the first
64 observed calls pass Clip, versus zero before. The captures now show
distinct polygons and textures, but they are still deformed and without a recognizable Kratos.
The VU1 stalls on EEXP are being investigated; see the integrated control in `research-log.md`.

`ps2recomp-vu1-efu-opcodes.patch` fixes that instruction selection and its
latencies in cached decoding and in execution. ERSQRT/ESIN/EATAN/EEXP are
checked against PCSX2's LowerOP table at `32ac6e2`, keeping the EFU formulas.
The tests use explicit binary words and also check WAITP and the
rejection of reserved instructions. Validation with the game is recorded separately
to distinguish it from the earlier MMI integration.

The later full build passes **548/548** with OpenGL. In the five-minute
control the reserved VU1 instructions disappear and distinct images are captured
up to 240 s of the PAD clock. The scene retains severe deformations and
Kratos is not recognizable; this fix does not complete 3D rendering.

A second five-minute control with the CPU also shows severe deformations,
without reserved VU1 instruction errors. The whole failure cannot be attributed to
OpenGL nor can pixels be compared between these independent runs. A
repetition with identical commands and initial state is being prepared to narrow the divergence.

## Local replay of GS commands

`ps2recomp-gs-cpu-state.patch` adapts the CPU export/import of the SotC fork
`ac9efa070638ad3b3accd284de6f898d5ab271d1`, with credit to Taylor N. Albarnaz /
LightVelox (GPL-3.0). It preserves the palette and its CBP, the cached texture page,
the transfer, the pending CT24 bytes and the readback buffer/cursor. Invalid
snapshots are rejected before modifying the target's state.

The optional diagnostic `GOW_GS_REPLAY_TRACE` installs a wrapper in the overrides,
preserving the CPU/thread/OpenGL selection. It starts after 150 s of the host
clock and only in state 11; it captures three seconds with a 64 MiB limit. The deadlines
can be chosen with `GOW_GS_REPLAY_AFTER` (0..3600 s) and `GOW_GS_REPLAY_SECONDS`
(0.1..60 s), using a decimal point. The clock starts when the backend is installed;
it is different from the clock of the PAD key presses. It saves the
initial and final state and the commands, including presentation and MXCSR mode.
It serializes the calls to the backend during this test: it is not used to measure FPS.
Without the variable it does not install the wrapper. The profile removes all these options.

`GOW_GS_REPLAY_TEXFLUSH=1` additionally waits for the first TEXFLUSH sent by the game
after the deadline, in state 11. The initial state is saved **after** that
command and after synchronizing the queue; the initial TEXFLUSH is represented by that
state. It does not add a TEXFLUSH nor invalidate the renderer's cache beforehand. The option
is `0` by default and allows capturing an input with the CPU page invalidated
in order to import the same state on the GPU. If the game does not send that boundary, the
capture does not start. Invalid options disable the diagnostic with a
message, before opening or replacing the output file.

```powershell
# First build the port with all the patches and then the tool.
.\scripts\compilar_replay_gs.cmd
$env:GOW_GS_REPLAY_TRACE = "$PWD\logs\tramo_gs.bin"
$env:GOW_GS_REPLAY_AFTER = '470'
$env:GOW_GS_REPLAY_SECONDS = '3'
$env:GOW_GS_REPLAY_TEXFLUSH = '1'
# Run the game control with the CPU; keep it open after the deadline
# until the log confirms start in state 11 and end completo=1.
# When finished, remove the variable before other controls.
Remove-Item Env:GOW_GS_REPLAY_TRACE, Env:GOW_GS_REPLAY_AFTER, Env:GOW_GS_REPLAY_SECONDS, Env:GOW_GS_REPLAY_TEXFLUSH
.\logs\repetir_gs.exe .\logs\tramo_gs.bin cpu --lockstep logs
.\logs\repetir_gs.exe .\logs\tramo_gs.bin compute --lockstep logs
.\logs\repetir_gs.exe .\logs\tramo_gs.bin hardware --lockstep logs
```

The tool first verifies that the CPU reproduces the original final VRAM.
It also checks the final palette, transfer and readback. The current GPU importer
does not restore the CPU page: if its initial bytes differ from the VRAM,
it rejects that comparison and requires capturing from a TEXFLUSH boundary.
It then compares the VRAM and the presentations of both backends. `--lockstep`
locates the first command that changes the VRAM differently; the exit
codes are 0 (match), 1 (divergence), 2 (invalid file/context) and 3
(the replay does not reproduce the capture or an expected read). The report of the
first draw includes TBP/TBW, dimensions/filter, TEX0/TEX1/TEXA, CLAMP,
FBP/FBW/PSM, mask, depth and scissor, to identify reads and writes
in the same VRAM region. It checks that
OpenGL is active; a CPU fallback does not certify GPU parity. The hardware variants
may use compute while compiling: the counters are shown to
check what work they executed. The binary format is local and requires the
same ABI and structure version; it is not a portable format.

The resulting binaries, VRAM, commands and captures remain in `logs/`, ignored
by Git. Never attach them to commits nor upload them to GitHub. The script's synthetic test
contains no game data and checks the parser and the rejection of truncated files
before replaying the commands on the CPU.

The first verified real capture (state 11, 47,207 primitives and two presentations)
reproduces the state and the final CPU VRAM exactly. Compute and the mixed path
with hardware enabled diverge at the same draw 561 (record 577), initially
by three bytes; it is an STQ triangle with a PSMT8 texture. The final differs by
166,763 and 164,227 bytes respectively, and in both presentations. Real
OpenGL is confirmed on the RX 5700 XT; the mixed path uses 7,749 compute tiles versus
11,937 for the compute path. These results delimit a GS difference, but
the large deformations also appear on the CPU and still require investigating
the data prior to the backend. This optional serialized capture does not measure FPS.

The CPU renderer is stabilized with `ps2recomp-gs-cpu-rounding.patch`: each `Submit`
uses SSE round-to-nearest and restores the caller's mode, including the
calls in the GS queue. It keeps FTZ/DAZ, masks and flags; the EE/VU modes continue
with their previous semantics. Two regressions fail without this isolation and compare
full VRAM for gradient, UV and STQ under the four MXCSR modes. It does not replace
a precise implementation of GS interpolation.

The earlier captures belong to the CPU version that produced them: after
changing its rasterization they must be captured again. The tool's final VRAM
verification refuses to certify them with a version that no longer reproduces them.

With the libm fix `3f349b2` and the 36 patches a new input is captured:
53,016 draws, three presentations and an exact final GS state when replaying on the CPU.
OpenGL compute and mixed already diverge at sprite 510 (917 bytes); their finals
differ by 387,242 and 386,914 bytes. This control combines the camera fix and
the SSE isolation. The CPU images show the ship and the cliffs
recognizable, although a later image retains deformations and does not yet
certify Kratos. It is used as the new reference for the following GS
fixes; the optional capture is not useful for measuring performance.

Two later patches delimit independent GS failures: `gs-triangle-precision`
keeps the reciprocal and numerators in double before the float weight, matching the
CPU reference in the Z32/Z24 regression for large triangles; `gs-packed-depth`
avoids losing Z32 bits in PACKED XYZ2/XYZ3 before reaching the backend. They are tested
separately before and after the fix and keep the CPU renderer for comparison.
The additional FP64 work requires a later profile to assess its cost.

`repetir_gs` compares and exports only the visible region of `PresentationFrame`:
the CPU reserves rows of 640×512 and the GPU uses 640×visible height. The helper
`tools/render/gs_frame_pixels.h` requires specifying the layout and avoids interpreting
padding as image differences. `scripts\compilar_replay_gs.cmd` also runs
`tests/gs_frame_pixels_test.cpp`, with layouts, padding, truncation,
PPM export and a real CPU presentation. A VRAM difference remains
independent of this diagnostic adjustment.

To check whether the same backend repeats the result, use several passes:

```powershell
.\logs\repetir_gs.exe .\logs\tramo_gs.bin hardware --repeticiones 8 logs\estabilidad_gs
```

The CPU/GPU instances and their VRAM vectors are kept. Before each pass it
waits for FINISH, copies the initial bytes and re-imports and verifies the entire state:
CLUT, transfers, CT24 carry, local read and CPU cache. The CPU cache absent on the
GPU is explicitly identified and a stale initial page continues to be rejected.
The CPU must reproduce the capture's End exactly in all passes.

CPU/candidate parity and stability between consecutive candidates are reported
separately. VRAM, state and all visible frames are compared, with bytes and
first differing index per frame. The counters are shown as per-pass deltas:
"hardware requested" does not guarantee that the variants are ready; observing
primitives and zero compute tiles makes it possible to recognize passes without that fallback. Equal
totals do not certify that the whole path is identical. The exact history is limited
to 64 MiB visible per pass; if exceeded, it returns 2 and requires a smaller segment.

To locate intermediate variation between passes, add `--checkpoints-sync`:

```powershell
.\logs\repetir_gs.exe .\logs\tramo_gs.bin compute --snapshot-feedback --repeticiones 3 --checkpoints-sync logs\controles_gs
```

It records FNV-1a64 fingerprints of the entire VRAM at the Flush, Sync, Present and
End boundaries. It reports the first record/op/draws that changes, and also rejects parity
if the intermediate difference disappears before the End. It does not store another
4 MiB copy per control: the history admits 4,096 fingerprints and the limit is checked
before creating the backend. It keeps the exact final comparisons and those of the
images. An equal fingerprint does not certify intermediate byte-for-byte identity.
The chosen commands already drain batches; TEXFLUSH is left out because on the current
GPU it does not. Readbacks add waiting and the test does not measure FPS.

To replay only a prefix, `--hasta-registro R` accepts a natural boundary
Flush, Sync, Present or End. `Initial` is record 0; the following ones start
at 1. For example, if the first variable control is at Flush 36:

```powershell
.\logs\repetir_gs.exe .\logs\tramo_gs.bin compute --hasta-registro 36 --repeticiones 64 --checkpoints-sync logs\prefijo_gs
```

The tool validates the index and its operation before creating the backend.
It rejects Submit and TEXFLUSH to avoid new cuts between draws. On reaching
the selected record, it compares exactly the 4 MiB and the portable state
of CPU/candidate, in addition to the presentations already executed. A prefix
before the End prints that it **does not validate the original End nor the rest of the
capture**. Selecting the End keeps the oracle of the complete capture.
The limit of synchronized controls is checked only for that prefix.
A differing result keeps exit 1; argument/capture errors,
exit 2; a CPU reference that does not reproduce the End, exit 3.
`tests/gs_replay_cli_test.py` checks boundaries, limits, invalid options
and that an altered End is detected when replaying the complete segment.

In the late segment of 146,015 records, CPU ×3 keeps the thirteen
controls, the End, the state and both images equal. Compute ×3 with snapshot changes
for the first time at the Flush of record 73,288, after 73,003 draws:
eight of the thirteen controls vary between passes, with equal raster
counters and the two visible images stable. This boundary locates VRAM
variation prior to the End; reducing the responsible batch remains pending. The
isolated initial sprite is also stable on effective hardware, with one
draw and zero compute tiles in the warm passes, although it keeps the
1,874 bytes that differ from the CPU. These are two differences that require their own tests.

The later reduction narrows a color/Z dependency: the prefix up to record
68,897 stays stable in five passes; adding the next sprite changes
64–128 bytes between some passes. Both sprites use FBP=ZBP=320, FBW=1 and
PSMCT24/PSMZ24, with Z test/write. Their XY rectangles are disjoint, but
their physical color and depth addresses overlap through the swizzle.
Separating them eliminates that variation in eight passes of the prefix. The search by
prefixes does not prove that the variation is monotonic nor that it is the first global failure.

`ps2recomp-gs-target-alias.patch` keeps separate bitsets for the color pages and
the batch's depth accesses. If the next primitive crosses
color with the previous batch's Z, it completes it before adding it, also when Z
is only read. Disjoint buffers and Z without read/write keep their batch.
It does not replace the internal order of a draw nor resolve aliasing between pixels of
a single primitive; nor does it implement the 8 KiB GS cache. Per-page
detection is conservative and may add synchronizations.

The procedural CT24/Z24 control differs by 6,144 bytes with the previous backend;
the integrated backend separates the two draws and matches the 4 MiB with the CPU.
The complete official build and the 582 native tests pass, including
twenty OpenGL tests with alias regressions in compute and effective hardware.
The complete real segment, in compute with four passes with snapshot and four
without it, preserves
the thirteen controls, all the final VRAM, the state and both images exactly
between passes. It still differs from the CPU by 739,502 bytes and two presentations.
Batches go from 632 to 648, with the same 99,402 primitives/53,757 tiles: this
fix protects ordering and does not establish an FPS improvement.

The directory can go with or without `--lockstep`, before or after the options.
It is created if missing; a failure to create/export and invalid options return 2.
The images from several passes carry `replay_pasada_N_` to preserve them. If the
directory is omitted, `replay_*.ppm` is excluded from Git. The game's captures and outputs
remain exclusively local.

The FULL45 control of the first historical frame reproduces CPU/state exactly
in three passes and exports six valid visible PPMs. In eight OpenGL passes, the
last two use 34 batches, 734 primitives and zero compute tiles, but differ in
545 bytes of VRAM and 358 visible, with equal final state. The tool returns
1 and shows both results; it does not hide the difference nor interpret it as FPS.

The previous cuts locate that variation: up to record 519 everything matches;
the first feedback sprite (520) is repeatable although it keeps the 917 bytes of
CPU/GPU difference. Adding the second (521) already produces 36 variable bytes between
hardware passes with exact restorations and final state. The 16 sprites read
and write CT32 over the same framebuffer and their result then passes to the
visible frame. The instrumentation of the original ring observes zero reuses in
the capture: its recycling does not explain this variation.

The [Khronos interlock specification](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_fragment_shader_interlock.txt)
guarantees ordering and visibility of `coherent` buffers within the critical section
for fragments of the same pixel; it does not order distinct pixels nor reads prior
to that section. The current shader samples before entering the interlock. This narrows
the feedback investigation, but does not certify a GS cache policy nor justify
adding a barrier or changing the filtering without a reference control.

To investigate bilinear feedback without game dumps, the same script compiles
`logs\comparar_feedback_gs.exe`. Running it compares a sprite over a procedural
64×64 CT32 texture with the source in the framebuffer itself and with a disjoint copy,
on the CPU and OpenGL compute. It prints per-row differences, VRAM bytes and
GPU repetitions; it requires a real GPU. Exit code 0 indicates that the comparison
finished, even if there are differences; 2 indicates an invalid control or GPU not
available. It does not certify which output has the GS semantics.

The same helper compiles `generar_feedback_gs.exe` and checks on the CPU three
procedural captures of two sprites over a 64×416 CT32 texture. `self` reads and writes
the same framebuffer with bilinear; `disjoint` keeps the filter and copies the source
to another region; `nearest` keeps the feedback and changes only the filter. The
copy checks its 27,588 neighbors after CLAMP. It requires no game files:

```powershell
scripts\compilar_replay_gs.cmd
.\logs\repetir_gs.exe logs\feedback_sintetico\feedback_gs_self.bin hardware --repeticiones 12 logs\feedback_sintetico\hw_self
.\logs\repetir_gs.exe logs\feedback_sintetico\feedback_gs_disjoint.bin hardware --repeticiones 12 logs\feedback_sintetico\hw_disjoint
.\logs\repetir_gs.exe logs\feedback_sintetico\feedback_gs_nearest.bin hardware --repeticiones 12 logs\feedback_sintetico\hw_nearest
```

The generator can be run separately with `generar_feedback_gs.exe [directory] [--pcsx2]`;
the captures use the ABI of the runtime they were compiled with. On the RX 5700 XT, CPU ×3
reproduces the three Ends and frames exactly. Hardware ×12 keeps parity and
stability for `disjoint` and `nearest` (exit 0). `self` returns 1: it differs from
the CPU and also varies between passes with two batches, two primitives and zero compute
tiles. For example, passes 4→5 differ by 19 bytes of VRAM and 19 visible;
7→8, by 34 each. Restoration and final portable state remain exact.
The initial pass mixes compute while the variant is compiled and is reported
separately. The variable quantities are not fixed expected values: the case
reproduces the instability, without yet certifying the correct GS cache policy.

The [GS manual supplement, §§1.2 and 1.4](https://www.scribd.com/document/718537990/GS-Users-Manual-Supplement)
describes a one-page texture buffer and groups of 4×2 pixels for textured
drawing; the bilinear filter may reload pages because of its neighbors. This supports
investigating cache and access order, but does not fix the result of the synthetic
feedback pattern. The current CPU loop writes one pixel after each sample and does not yet
model those groups nor their pipeline. The [PCSX2 note on the GS cache](https://github.com/PCSX2/pcsx2/discussions/4311)
also distinguishes the texture cache from the framebuffer cache. A control
of that pattern is needed to decide the next change.

## Bilinear precision and independent reference

`ps2recomp-gs-bilinear-precision.patch` fixes the interpolation of the RGBA channels
on the CPU and OpenGL. The previous filter interpolated in floating point and rounded
at the end. It now uses a four-bit fraction and truncates each horizontal stage and
the vertical one, like the software renderer of
[PCSX2 v2.8.2](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/Renderers/SW/GSDrawScanline.cpp),
with its operation
[`lerp16_4`](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/GSVector8i.h).
It does not incorporate code from those functions: it uses positive integer weights to obtain
the same truncation without depending on the shift of negative integers.

The reference was run with PCSX2 software, without BIOS or game files, over
four procedural RGBA texels and the 256 combinations of UV fractions. The
input texels were also verified. The 1024-byte RGBA image has
SHA256 `9de1ca132c07706433d8e86fedde114379437d2f869884342e2ec0c2353004d6`
and FNV-1a64 `fdde85267aad850d`. The previous filter differs by 780 bytes; the new one
matches in all. The regressions check that external fingerprint on direct CPU,
CPU with thread and OpenGL compute/hardware, with FST and STQ and the four
SSE rounding modes, keeping the producer's controls. All three fail before the
fix; afterwards the 568 tests pass, including ten OpenGL with a real GPU.
The literal texture control of an earlier test changes from R/G=44/73 to
43/72 due to the truncation; nearest keeps 58/87.

`generar_feedback_gs --pcsx2` also exports the three patterns as `.gs`. The
helper generates them in `logs\feedback_sintetico` and runs
`gs_feedback_dump_test`: it checks the initial freeze and sends the A+D packets
to the GIF PATH3 frontend, comparing the four MiB of VRAM with the End of the CPU
capture. The own serialization uses the legacy format and freeze v8 of
[GSState.cpp](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/GSState.cpp) and
[GSDump.cpp](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/GSDump.cpp).
It is an export of these specific patterns, not a converter of game traces
nor of arbitrary GS states. The generated binaries stay in `logs/`.

The independent comparison separates the precision of the feedback: nearest already
matched; with the corrected filter, the disjoint source also matches PCSX2
software. Bilinear feedback keeps differences and requires deciding the
cache policy and the access order. PCSX2 software serves here as an executed
reference; it does not replace a capture from a PS2 to certify that feedback.
This change does not demonstrate an FPS improvement.

## Negative coordinates with nearest

`ps2recomp-gs-nearest-stq.patch` fixes the texel choice on the CPU and OpenGL
for negative STQ coordinates. The direct cast to integer chose 0 for a
coordinate such as −0.25 instead of texel −1 which REPEAT then wraps. The software
reference of [PCSX2 v2.8.2](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/Renderers/SW/GSDrawScanline.cpp)
first converts to 16.16 and then extracts the signed integer part. That conversion
is reproduced with truncation and `floor`, without shifts of negative integers.
Applying only `floor` is also not enough: with a 4×4 texture and REPEAT, −1/65536 chooses
texel 3, while −1/131072 loses its fraction in the conversion and chooses 0.

Two 16×16 controls, without feedback, compare negative coordinates in quarters
of a texel and values near the 16.16 limit. The original differs from PCSX2 software
by 624 RGBA bytes/156 pixels in each control. The external fingerprints are:

| Control | SHA256 of the 1024 RGBA bytes |
|---|---|
| Negatives | `9d1cc63a5a081dbe2e59c8117fadcd6bd8ae49c87b9a08dc60dcb326239d8c81` |
| Limits | `119eae34f160a97fa9991d028d8a7f514d739f77d1e73f429bd7d854dad22bdc` |

Three new regressions fail before the adjustment and afterwards the 571 tests pass.
They check both fingerprints on direct CPU, CPU with thread and OpenGL, for sprites and
triangles, Q=1/2 and the four SSE modes. The OpenGL control also requires counters
of the compute and hardware paths; having a created context is not enough.

The helper also compiles `generar_oraculos_gs.exe [directory=logs/oraculos_gs]`.
It exports four reference patterns —bilinear, negatives, limits and bilinear STQ— as
replay captures `.bin`, PCSX2 `.gs` dumps and 16×16 `.rgba` matrices.
The texels and commands are procedural. `gs_feedback_dump_test logs\oraculos_gs --oraculos`
checks freeze/GIF/End and the helper repeats the four controls on CPU ×3. This makes it possible to
regenerate the reference inputs without the ISO or game dumps. The
external RGBA comparison remains independent of the port's renderer.

The first three generated `.gs` files are identical by SHA256 to those run in the isolated
reference, and their CPU matrices have the documented external RGBA fingerprints.
Freeze/GIF/End and CPU ×3 are exact in the six patterns of the helper; the earlier
feedback controls keep their dump bytes. On the RX 5700 XT, the three
hardware oracles ×8 have exact parity, stability and final state; the
warm passes use 256 primitives and zero compute tiles. These controls do not
change the pending result of bilinear feedback on the destination itself.

## Bilinear STQ conversion before the half texel

`ps2recomp-gs-bilinear-stq.patch` extends the 16.16 conversion already used by nearest
to the bilinear filter, on both the CPU and GLSL. It first truncates the scaled coordinate
and then subtracts half a texel and extracts the four-bit weights. With
u=−1/16−1/131072, converting before the shift chooses weight 7; using
the previous float directly chose 6. The FST 12.4 data are already exactly
representable and the nearest results keep the same conversion.

The executed reference of PCSX2 v2.8.2 software uses 16×16 constant STQ samples,
a disjoint 4×4 procedural RGBA texture and REPEAT. The 16 input RGB/alpha texels
are checked, as is that the GIF dump reproduces the previous CPU End byte by byte.
The previous renderer differs by **611 RGBA bytes/156 pixels**. The external fingerprint
of the 1024 bytes is SHA256
`3566bc0c748d3948c2180c311562175df43c745a28bc8d7ad165d165b57d4e28`,
FNV-1a64 `c6e49fa0342e621f`. The conversion and shift sequence is in
[PCSX2's GSDrawScanline.cpp](https://github.com/PCSX2/pcsx2/blob/v2.8.2/pcsx2/GS/Renderers/SW/GSDrawScanline.cpp).
It is a comparison with that software implementation; not a capture of the physical GS.

The three new regressions fail before (**573/576**) and pass after the adjustment
(**576/576**, fourteen real OpenGL controls). They compare the external fingerprint on
direct CPU, CPU with thread, compute and hardware, for sprites/triangles, Q=1/2
and the four SSE modes. The counters require 256 primitives per matrix and,
on hardware, at least one matrix without compute tiles. The public generator adds
`feedback_gs_oraculo_bilinear_stq` as `.bin`, `.gs` and `.rgba`.

The full build regenerates the 6,418 units and ends with code 0;
49 patches/84 sources match and the subsequent suite passes 576/576. The seven
tools pass the 18 image controls and the thirteen freeze/GIF/End with
CPU ×3. The four `.gs` match by SHA256 the inputs run in
PCSX2 and the four `.rgba` matrices match the reference byte for byte.
The six damaged-dump controls continue to be rejected.

The new pattern is exact and stable on compute ×8 and hardware ×8, including
the full VRAM, the portable state and the visible frame. Eight quick passes
selecting hardware still ended up on compute: the asynchronous compilation
of its shader had not finished. `--pausa-ms 1000` makes it possible to wait between passes
of the same backend; seven of the eight repetitions then rasterize their
256 primitives with zero compute tiles and match the external RGB. The option
requires several passes and a wait of 1..1000 ms; nine invalid uses return
2. CPU ×2 with wait is exact and optional feedback with wait keeps exit
1 because of its known difference from the CPU. These waits are a control of the path,
not a measure of FPS nor a game policy.

The later control of the full executable lasts 510 s on OpenGL, with FMV
skipped and snapshot feedback disabled. It loads a private copy of the card,
without modifying the original. The sixteen 512×448 captures are distinct; the
last one shows Kratos during an attack, the HUD, weapon trails, R2 and the
save point, with state 11 and no pending load. The 128 Clip samples
are finite and complete, the first 768 late triplets are non-zero and
the 192 game contexts have no invalid pointers, cycles or truncations.
No reserved VU is recorded. The controller receives the three planned square
presses; this verifies the image of an attack animation, without certifying
combat against enemies nor sustained FPS.

## Regional texture pages and OpenGL batches

`ps2recomp-gs-region-pages.patch` reduces the conservative set of pages that
a regional texture may read. Before, REGION_CLAMP and REGION_REPEAT declared
the whole 0..1023 range of each axis: a framebuffer unrelated to the accessible texels
could cause a batch split due to nonexistent feedback.

A valid REGION_CLAMP uses MIN..MAX; REGION_REPEAT, whose result is
`(coordinate & MIN) | MAX`, stays within MAX..(MIN | MAX). The gaps in
REGION_REPEAT remain covered by the conservative rectangle. MIN>MAX keeps
the previous full range. Ordinary REPEAT and CLAMP keep their coverage.
The key of the page-set cache includes both extremes of each
axis, so that it also renews if only MIN changes. This cache stores a bitset of
access risks; it does not reproduce the data of a PS2 texture cache.

The control uses three colored sources outside the framebuffer and an optional fourth
that reads an already written page. On the 13 PSMs, nearest/bilinear and bitset
cache enabled/disabled, the three disjoint draws go from three batches
and two texture flushes to **one batch and zero flushes**. The fourth real read
keeps the necessary separation: **two batches and one flush**. The
REGION_CLAMP control keeps MAX=700 and changes only MIN to check that key.
The indexed formats load a CSM2 palette of distinct colors, preventing
an empty image from hiding failures.

Other controls cross page boundaries, use non-zero REGION_REPEAT masks
and TBP bases 0, 31 and 16383, including the wraparound of the 4 MiB. They run
with snapshot feedback enabled and disabled. Three one-pixel sprites on a
page that is really read keep three batches and two flushes; TEXFLUSH renews
the source of the CPU control between Submits. All the comparisons include the
full 4 MiB, not only the visible pixels.

There are 208 batch cases and 384 boundary cases per path, 1,184 combinations on compute
and hardware. The number of primitives and effective hardware without compute
tiles is required; creating the context or falling back to the CPU renderer does not satisfy the control.
The two batch regressions fail with the previous backend. A first attempt
coincided with Claude's build and also exhausted two shader deadlines;
when repeating the isolated controls with the machine free, only the unnecessary
batches fail, while hardware boundaries and external feedback pass.

The full build regenerates the 6,418 units and ends with code 0.
The later audit confirms 50 patches and 84 identical sources; the final
suite passes 580/580, with eighteen real OpenGL controls. The seven tools
pass the 18 image controls and the thirteen freeze/GIF/End patterns with CPU ×3;
the six damaged copies are rejected.

The later control lasts 510 s on OpenGL, with FMV skipped and experimental
snapshot disabled. It loads a private copy of the card, whose original
keeps its SHA256. The sixteen 512×448 captures are distinct; the last one
shows Kratos attacking with HUD, weapon trails, R2 and the save point,
in state 11 with no pending load and with hardware active. 128 finite/complete
Clip samples, 736 non-zero late triplets and 192 contexts
without invalid pointers, cycles or truncations are preserved. No reserved VU appears.
This verifies the image of an attack; combat against enemies and sustained FPS
remain pending.

The improvement demonstrates fewer submissions in these patterns; it does not establish an FPS gain
in the game nor resolve the physical GS cache. The CPU renderer and the
experimental feedback policy remain available for comparison.


## Batch separation and optional protected source

`generar_feedback_gs --pcsx2 --separaciones` keeps the three previous patterns
and adds six controls. The `_texflush` suffix inserts TEXFLUSH between the sprites;
`_scissor` changes SCISSOR1 from x1=511 to 510 before the second. Both sprites still
draw x=0..63/y=0..415, so that this state change does not clip the image.
`gs_feedback_dump_test [directory] --separaciones` validates the nine freeze/GIF/End,
including the separation records. It also checks the complete bytes of
the contexts, the empty GIF queues, Q=1 and the three privileged blocks; preserving
VRAM is not enough if PMODE or DISPLAY were damaged. The helper runs CPU ×3 for
each capture; the generated files remain inside `logs/`.

The reference run with PCSX2 v2.8.2 software shows one batch with the two
sprites for `self` and `self_texflush`, and two for `self_scissor`. In the first
case the image matches the disjoint source; TEXFLUSH keeps that result
in this pattern. The SCISSOR change renews the source between draws and changes
1,238 RGB bytes of the 79,872 observed. The original source of the
first draw is checked and, for the second, the already drawn left half plus the original
right one, without differences in the sampled texels. The final RGB of the
separate control has SHA256 `75fb49353fd21ec38c8d4b413f657b57d5fc168bb24c9eba8279edc747079197`
and FNV-1a64 `f1dd4b246679e740`. It is evidence of the grouping of this reference;
it does not establish a universal TEXFLUSH policy nor reproduce a PS2 cache.

`ps2recomp-gs-feedback-snapshot.patch` adds an **optional policy, disabled
by default** to isolate simultaneous read/write. Before a primitive
that reads pages that it also writes, it completes the previous batch and copies only
those pages to the shadow memory already used by the transfers. Its state
keeps the epoch prior to the copy: the sampler reads the protected source and the
raster writes the normal VRAM. It applies to points, sprites and triangles; lines
keep their subdivision into points and protect the source per point, not
per whole segment. Draws without overlap follow the previous path. The shader's interlock
orders writes of the same pixel, but not its texture neighbors, so
a barrier between sprites did not resolve the simultaneous access within each sprite.

In the executable it is enabled before startup with `PS2X_GS_FEEDBACK_SNAPSHOT=1`.
The replay tool requires its explicit option:

```powershell
.\logs\repetir_gs.exe logs\feedback_sintetico\feedback_gs_self_scissor.bin hardware --snapshot-feedback --repeticiones 12 logs\feedback_sintetico\snapshot_scissor
```

The exit code still checks parity with the CPU renderer, which keeps
a single 8 KiB texture page. A source frozen per primitive may
be stable and match the separate reference, and still return 1 because
it differs from the CPU. It does not turn that difference into success nor change the CPU renderer.
The policy does not freeze a common source for all the sprites in a batch and
it remains pending to compare it with the cache and pipeline of the real GS before
enabling it by default. Nor does it demonstrate an FPS improvement.

The native hardware regression fails before the fix because of RGB and variation
between passes; the compute one already passed that pattern. Afterwards both pass against
the external fingerprint, with eight restorations per pattern, nearest/disjoint source
controls and points/triangles against a disjoint CPU copy. At least one
hardware pass without compute tiles is required; a CPU fallback does not count as validation.

After the full build, 48 patches and 84 sources match exactly and
the suite passes 573/573 again, with thirteen real OpenGL controls. The seven
tools compile and pass the 18 image controls, twelve freeze/GIF/End
and CPU ×3. Six damaged copies are rejected: PMODE disabled in its three blocks,
initial TEX0, a pending GIF queue, altered Q, a reserved privileged byte
and missing EOP. The three earlier `.gs` keep their SHA256.

Compute and hardware with snapshot repeat `self_scissor`, `disjoint`
and `nearest` twelve times: 72 passes preserve the full VRAM, the portable state and the
visible frame between restorations; their 64×416 RGB regions match the three
executed references. The warm hardware passes have two
primitives and zero compute tiles. `self_scissor` keeps exit 1 and 4,557 bytes
different from the CPU, even when matching the separate reference; the other two
cases keep exit 0. Duplicate options and snapshot in CPU mode return 2.

With the full executable and the option enabled, a 390 s OpenGL control
loads a private copy of the saved card. The fifteen 512×448 images
are distinct; the last one shows Kratos, the save point and R2, with
hardware active and state 11 with no pending load. 128 finite/complete
Clip samples, 416 non-zero late triplets and 192 game contexts
without invalid pointers, cycles or truncations are preserved; no reserved VU is recorded
nor does the original card change. The final capture does not show the health
bar and neither combat nor sustained performance has been tested with this option.
The earlier 330 s script chose a new game and was repeated by delaying
the key presses; that intro does not count as loading a saved game.

## Tobiichi-Port reference

[YYOzcan/Tobiichi-Port](https://github.com/YYOzcan/Tobiichi-Port/tree/9f02797f8ab7481fddad4d2daf7afad82d11699f)
is reviewed at `9f02797f8ab7481fddad4d2daf7afad82d11699f`. The five compared files
(`gs_cpu_backend.cpp`, `ps2_vif1_interpreter.cpp` and the VU1 core/upper and
lower instructions) are identical to those of the PS2Recomp pinned at `c5a9d025`.
Its README declares the menu and the game pending; this describes what is published,
not a test run here. The GoW hooks include filler objects/virtual table
and boot shortcuts. They are not incorporated as a rendering fix nor has
its executable been tested. It may serve to contrast boot hypotheses, but the reviewed
files do not yet provide a different solution for GS/VIF/VU1.

## Model context selection

`GOW_MODEL_DIAG=1` records `[gow-model:server]` at the entry of
`renModelServer::ProcessServer` (`0x159C58`), with a maximum of 64 samples prior to state
11 and another 64 within it. It observes the selected table, group and slot, the context,
its virtual table and the call's target/adjustment, checking RAM bounds.
The indices are computed in 64 bits to avoid wraparound.

The same variable observes the real entry of `renGROBMasterContext::ProcessServer`
(`0x1511F0`): `[gow-model:grob-master]` summarizes up to 256 contexts of its list, the
non-null filter at `cliente+0x2C`, cycles, invalid pointers and truncations. It keeps the limit
of 64 samples per phase for each of the first eight distinct contexts;
the first eight samples detail each client as
`[gow-model:grob-client]`, with its server, view and virtual method. `validRoute` indicates
only that the observed pointers fit in RAM, without certifying the registration of the
method in the runtime nor its later invocation. The nodes are compared by physical
address to also detect cycles between RAM aliases.

`[gow-model:context]` observes the entry of `0x159878`, whose list and filters match
`renModelServerContext::ProcessServer` of the GoW 2 reference, although the retail
map does not assign it that name. It records the view masks, the candidate models for the
direct call and those destined for the static tree, with the same limits per context
and per list. `[gow-model:client]` details the first eight samples.
`[gow-model:process]` records up to 64 entries per phase at `0x157A60`, equivalent
in structure to `ProcessModel`, with the model and its number of groups. These candidates
are computed from the observed memory: they also do not prove that the internal filters
or the sphere tree allow the model to be drawn.

The processing entry also observes the skeleton, its root visibility and the
first block of group visibility bits. `[gow-model:clip]` records up to 64
calls per phase to `renView::Clip` (`0x169120`) coming from `0x157FA8`. It keeps the
bits of the sphere and of ten coefficients/limits of the view. It only records a result
as valid when the original returns to its caller (`completed=1`); `0x80000000`
is the code this path uses to discard. No probe changes the computations, the
FPU registers or the filters. It does not collect here other calls to Clip nor all the internal
discards of parts/static models.

It is an entry observation: it does not certify that the method was invoked, that there are visible
models nor that geometry was sent or drawn. It preserves the game's registers and memory
and always calls the original, also on resumptions. The performance profile
removes the variable to avoid mixing this diagnostic with the measurement.

## Different coordinates on the same destination

`ps2recomp-gs-coordinate-alias.patch` orders primitives whose color or Z
share physical pages when the coordinates exceed the FBW width or
the 512 logical pages of VRAM. For example, with FBW=1, CT32 `(0,32)` and
`(64,0)` are the same address: neither the compute tiles nor the per-pixel
XY interlock protected that access. Before the patch, the procedural control
loses 6,144–8,192 bytes against the CPU. Afterwards the 4 MiB match.

The detection is conservative per page, separates color and depth and is
reset with each batch. It keeps batches of normal coordinates and disjoint
pages, even when FBP crosses the end of VRAM. Two real OpenGL controls
cover CT32/24/16/16S, Z32/Z16, both directions of the alias,
inactive Z and memory wraparound. They fail with the previous backend; the integrated
native suite passes 587/587, with 22 OpenGL controls.

In the compared game trace, the Ends and images are exactly
equal to the previous backend and are still 648 batches. It does not certify an
FPS gain. The alias within a single primitive and the feedback difference
between CPU and GPU remain pending.

## Read-only depth trial

Separating Z reads from their writes made it possible to go from 648 to 543
batches in a local trace. The trial passed the procedural controls and
kept the Ends and images in eight compute and eight hardware passes with
snapshot. It does not establish more game FPS nor a GS cache faithful to the PS2.

It was removed entirely from the published chain: the long replay without
snapshot varied 200 final bytes, and a version limited to snapshot
also varied 128 bytes in its usual mode. GS56 keeps a prior
limitation: one of 24 presentations varied 190 bytes although the Ends were
identical. Resolving the feedback remains pending. The code and data
of the trial remain in `logs/`, outside Git.

## Wait for the hardware STQ control

`ps2recomp-gs-stq-hardware-test.patch` gives up to 12 s to the asynchronous
shader compiler so that the bilinear STQ control uses hardware.
Each repeated matrix keeps its RGBA comparisons and SSE controls;
compute alone is still insufficient to pass the test.
The change affects validation and keeps the production renderer.

## Integrated control with compiled VU1 and IOP scheduler

The official build of `main` at `9f0ebc4` applies 60 patches and generates/links
VU1 from 501 local micromemories. The 87 modified sources match
the published chain; 587/587 native tests, 22 real OpenGL controls
and 60 exact VU1 cases pass. The clean 430 s control produces 15 distinct
images. The last one shows Kratos and enemies on the ship with rain and
HUD, in state 11, with no pending load and with hardware active. No stretched
geometry is observed in that image; checking the full combat remains pending
and resolving the feedback. The captures and the game data remain local.

## GPU timing attribution

`PS2X_GS_GPU_PROF=1` enables timestamps and a report every four presentations.
`ps2recomp-gs-hardware-profile.patch` separates each hardware variant of a batch
and records its primitives, FBP, formats and flags. Compute attaches the data
before resolving the queue of 4,096 queries; before, those of the last
batch were lost. The two optional regressions of `GOW_GS_GPU_TEST=1` check those
cases with effective OpenGL and keep the 4 MiB exact against the CPU.

The groups are by destination/flags and the GPU times are expressed per frame;
the counters of the `target` line add up the report interval. Hardware
uses the state of the first primitive of each variant; compute, that of the first
state of the batch. They do not constitute per-primitive attribution. The profiler waits for
the query results and alters the game's pace: it must be disabled
when measuring FPS. The fix improves the diagnostic, without establishing more performance.
