# Experimental PCSX2 GS integration

The user proposes adapting PCSX2's GS while waiting for the code of the Urban Reign
port. The capture of that comment contains no repository, revision
or reproducible controls. Its resolution/FPS figures are the comment author's;
they are not attributed to God of War or to this work.

[PCSX2](https://github.com/PCSX2/pcsx2) is reviewed directly at
`2954ebe6965669219f1bbd256e958fbd8f83a85d`, GPL-3.0+, compatible with the port's
license. The downloaded sources stay in the private workspace. The two
bridge headers are our own code: they include the original GS interfaces
when building the external module, without importing sources from the game or from the other port.

## Integration point

The [PCSX2 GS](https://github.com/PCSX2/pcsx2/blob/2954ebe6965669219f1bbd256e958fbd8f83a85d/pcsx2/GS/GS.h)
receives GIF streams and privileged registers. Our `GSRasterBackend` interface
receives already-decoded primitives, CLUT and transfers separately. To use
the original frontend/cache, the bridge must receive the three PATHs after
arbitration, before they are reduced to primitives. It must also cover the
shortcuts of packed GIF and native IMAGE: hooking only `processGIFPacket`
does not guarantee coverage of those paths.

`tools/render/pcsx2_gif_bridge.h` keeps up to 15 pending bytes per PATH,
delivers complete quadwords in the order in which they arrive at the adapter and copies
the batches to 16-byte-aligned memory. Quantity in quadwords, maximum batches
of 256; it does not pad fragments nor decode/modify tags. A rejection by the
destination retains the failure: a prefix whose consumption is unknown is not repeated.
The reset requires resetting the GS as well. Checking the end of a stream is not equivalent
to VSync: packets may continue after it. The consumer must
finish using the pointer before returning; the bridge is not a thread queue.

`pcsx2_gif_sink.h` links to `GSState::Transfer<3/1/2>` of the open renderer.
PATH1 uses the continuous index 3 of `GSgifTransfer`; PATH2/3 keep their
indices 1/2. `GSgifTransfer1(span, size)` is not used: that function expects a
16 KiB VU ring and an address inside it. Calling
index 0 directly is not enough either: it cuts at the end of EOP, would ignore other packets of the
same batch and clears pending nloop when the span is exhausted. These are rules read
in the pinned body of GSState/MTGS, not proof of execution of the renderer.
The connection rejects an absent GS. **It does not create a device, import VRAM,
present a frame nor is it connected to the game's runtime.**

## Verified and pending

MSVC C++20 /O2 /W4 /WX: transport tests pass. All 65
boundaries of a 64-byte block are walked with a misaligned origin, interleaved PATH1/2/3 fragments,
a contiguous 32,784-byte stream and byte by byte, alignment, units,
invalid input, incomplete fragment, retained error and coordinated reset.
Syntax of the connection with the pinned **real** headers is correct in MSVC,
with the project's x86/SSE4.1 definitions and AVX2. CI additionally checks
that connection on Linux; it does not replace linking/execution of the renderer.

The first version of the link compiled with index 0 for PATH1. Review
of the real body detected those rules as incompatible with fragments/batches;
it is corrected to index 3 before using it in the port. The syntax checks
would not have detected that data loss. The real GSState.cpp is also compiled
as a private object with MSVC: correct; its linking and execution remain pending.

### Original parser executed on Windows (2026-10-12)

A private library of GS/common objects is extracted from the pinned sources
and linked with an explicitly windowless host. Configuration, repeated virtual
memory, CPU detection and dump registers use original implementations;
the Host services of this fixture offer default settings, errors to
stderr and reject window requests. Its counter must stay at zero.
The interface layer is built with ImGui's STB sources for this UI-less fixture.
The private codecs already available in PCSX2 use matching headers:
libpng 1.6.58/zlib 1.3.2. None of those DLLs or downloaded sources is published.

`tests/pcsx2_gif_parser_probe.cpp` runs the **real GSState** with a subclass
that counts draw requests without rasterizing them. It checks separate PATH1
tag/payload, retained nloop, two EOP packets in a batch, interleaved PATH2/3
fragments, their independent cursors and exact RGBAQ. Correct
in MSVC; draws and window requests: zero, as the test requires.

Isolated negative: changing only PATH1 from index 3 to 0 compiles and fails at
`PATH1 conserva nloop al cortar tras tag`. Restored, it passes. The restored executable
has SHA-256
`1289d908c425c0f1b138ff7dc4cf619f1a9341c443fe6145eae5c02d9b7e033c`.
CI checks the fixture's syntax with the real headers; **it does not yet reproduce
its native linking/execution**. The extraction context and its artifacts
remain private. This test confirms the parser's input selection,
not the DX11 device, pixels, full cache, FIFO/IRQ or game rendering.

### Original DX11 device executed (2026-10-12)

The private library incorporates the original GSDevice11, GSTexture11, D3D11ShaderCache and
GSTexture. `tests/pcsx2_dx11_device_probe.cpp` creates the device
in Surfaceless mode, with shaders from the pinned revision and the cache disabled.
It needs no window and does not run EE/VU. The host offers default settings,
identity translation and errors to stderr; static references to EE
registers use procedural storage, without running a substitute CPU.

Windows/MSVC Release, AMD Radeon RX 5700 XT: two create/close cycles
correct. Each cycle verifies **all 2,701 RGBA pixels** of a 73x37 texture
after Clear and after uploading a pattern with seven padding words per row
and drawing it with `StretchRectAuto`/Nearest. That second operation uses the original
COPY shader, not a direct DXGI copy. The readback respects the staging texture's
pitch. Channels/alpha and orientation are compared without tolerance.

Private negative: omitting only the draw call compiles and fails at
the first pixel of Shader COPY; restored, it passes both cycles. SHA-256 of the
restored executable:
`2be054f554e71ebdafc234998b84d4e7b53542f26a40c2f58403fcbead66db14`.
The fixture is published; its host/linking remain private and this GPU control is
not run in CI. It does not yet process GIF into GSRendererHW, import VRAM,
present in a window or draw the game. It is not a performance measurement.

### GIF into GSRendererHW and FIFO verified (2026-10-12)

The extraction incorporates the original GSRenderer, GSRendererHW, GSTextureCache and their helpers,
including the SW support objects. The drawing is not modified nor
is the cache replaced with fabricated values. The fixture initializes the original
SW tables before the renderer; its SW path is not covered by this control.
The configuration uses original extracted constructors, without loading settings,
cards or a VM. The absent optional services (capture, dumps, UI,
reopening and texture replacements) abort with a diagnostic if requested;
the capture/replacement settings are disabled. VSync is not called.

`tests/pcsx2_gif_draw_probe.cpp` sends a mosaic of 16 sprites to FRAME PSMCT32,
without texture/blending/depth test, through the original bridge and connection. It uses
13-byte fragments, regenerates different colors for PATH1/2/3 and reads through
BITBLTBUF/TRXPOS/TRXREG/TRXDIR plus the original InitReadFIFO/ReadFIFO. Each PATH
produces one GPU draw call and **2,048 exact RGBA pixels**, including alpha.
The delta of draws of each submission is verified, not an accumulated counter.

Windows/MSVC Release, RX 5700 XT: three PATHs correct. A private negative that
omits only the draw packet compiles and fails at the first FIFO pixel;
restored, it passes all three. Restored SHA-256:
`1d271fd05fcbf01cec0b688655c26337b99259a2545274ecccda423740ef01fb`.
This control verifies procedural drawing and download; it is not equivalent to presenting
a game frame, coherence with its RAM/VRAM, interrupts or performance.
Its host/linking are still private and CI does not run this GPU control.

### Public build recipe and IMAGE control (2026-10-12)

`tools/render/pcsx2_probe/` publishes the limited host, services, CMake and a
preparation that extracts only original GS/config sources from the clean revision.
It does not copy private DLLs or game data into the repository. Instructions and
dependencies in its [README](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/render/pcsx2_probe/README.md). Windows CI is added
to link all the fixtures and run parser/memory without a GPU;
the device/draw controls are run locally, explicitly.

This recipe builds and passes the four controls on Windows/MSVC on the
RX 5700 XT. The drawing widens its coverage: IMAGE PSMCT32 host→local, TEXFLUSH,
textured DECAL/nearest sprite and FIFO download. The full 2,048 pixels and
the 91 of a 13x7 region that crosses blocks match exactly, including
alpha. The partial end of a quadword does not write beyond the requested QWC.
Omitting only IMAGE compiles and fails at the first pixel; restored, correct.
SHA-256 of the restored drawing fixture:
`a7991d25961bdddddd8ce3631cf73287f057b8928c735df8724c818e575f3444`.

The close of the extracted Windows mapping had two local leaks: the handle and
three retained placeholders. The preparation adds GOW-Port fixes without
changing the original checkout: it closes the handle and joins the views before
freeing the range. The documented semantics of
[VirtualFreeEx](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfreeex) are followed.
Eight cycles of four alias views, stable handles and MEM_FREE over the whole
range: correct. Omitting each fix separately compiles and fails (eight
retained handles or view 1 reserved); restored, correct. It does not validate reservation
failures nor turn this limited host into the game's full host.

The four local executables work without dxcompiler.dll/dxil.dll in their
folder: DX11 uses the original SM4/5 compiler, with delayed DXC import for
other APIs. Delay loading does not prove DX12/Vulkan support.

### VSync/PCRTC without a window verified (2026-10-12)

The `gs_gif_draw_probe --frame` mode adds the **original** GSvsync: PCRTC update
and Flush before GSRendererHW::VSync, output cache and DX11 Merge.
Three different IMAGE patterns produce three composited 64x32 outputs with
2,048 exact RGBA pixels each. PMODE MMOD/ALP 255 determines a final alpha of
255; RGB keeps the pattern. The host counts the frame request, Surfaceless's FrameSkipped
and the metrics update; it runs no interface and measures no FPS.

The fixture configures DISPLAY with MAGH 3/DW 255 and DY 25 per NTSC in
PCSX2. The first procedural configuration used DW 63/DY 0: it gave a
16x32 output and a vertical offset of 25 lines. The registers of
**the test** are corrected per the original body; the renderer is not modified nor
is this case attributed to the framing observed in God of War.

Negative that omits only GSvsync: compiles and fails with a 0x0 output; restored,
it passes the three patterns. Restored SHA-256:
`cd46ebb2f58aa6bd80c5849e30d7ee5fc0659c644db030f65c8fed1c6701cffb`.
[CI of `08307ac` fully correct](https://github.com/KIexster/god-of-war-recomp/actions/runs/38243100981),
including native Windows linking and parser/memory. The pixel controls remain
local. Composited VSync does not yet validate the swapchain, visible image,
synchronization with the game or the FINISH/thread combinations.

### Procedural DX11 swapchain verified (2026-10-12)

`gs_gif_draw_probe --window` creates its own hidden Win32 window and uses the
original swapchain/Present. An empty ImGui context accompanies EndPresent,
with no emulator interface nor ini/log files. The control reads the resource
**actually bound as the DXGI render target before Present**, respecting
RowPitch; the read is limited to the fixture and is not proposed as a performance measurement.

Two full cycles of creating/drawing/closing the device, renderer and
window, with three different patterns each: the six backbuffers and the
six PCRTC outputs contain their exact 2,048 RGBA pixels. Presentation/metrics
callbacks consistent, closing of HWND/class verified. The hidden window
does not demonstrate a visible image or prolonged stability with the game.

Private negative: clearing the real backbuffer to magenta after drawing and
before comparing it compiles and fails, even though the PCRTC texture matches. Restored,
it passes window and Surfaceless. It confirms that the control distinguishes composition and
final buffer, without attributing the procedural alteration to a God of War failure.
Restored SHA-256 `74e92ae9a886b66f55079d06f6cbf0ddcbf9af18bfe2064e7d92137f94f3c543`.
[CI of `d1bf750` fully correct](https://github.com/KIexster/god-of-war-recomp/actions/runs/38244581430).
The new GPU control is local; the CI of the HEAD that publishes it is pending.

### IMAGE FLG 2/3 and hook review (2026-10-12)

The fixture now alternates IMAGE FLG=2 and FLG=3, keeping the tag in the bridge.
Both pass FIFO and, in window mode, exact composition/backbuffer. Omitting
only the FLG=3 submission compiles and fails: it receives the color of the previous pattern
instead of the new one. Restored, the no-VSync, Surfaceless and window modes pass.
Restored SHA-256 `77ecd2fa20509b18422d9ade62c8ee35db18f90a0a8ad19e6882be412d311bfd`.
It explicitly preserves the semantics that Opus's fix #55 needed;
it is not a reproduction of its FPS measurements nor an observed failure of the game.

Review of runtime 102: the arbiter delivers bytes in its decided order, but
`tryProcessNativeGifPackedChain` and `tryProcessNativeGifImageUploadChain` can
bypass it. The latter calls `uploadImageNative` with four registers, data
and only the low word of the setup tag: that point no longer offers the original GIF stream.
The generic path can also take an internal IMAGE shortcut, keeping the
input span. A single hook inside processGIFPacket would miss the two external
DMA paths. The first integration control must preserve bytes
and post-arbitration order, and ensure a single-threaded consumer; it is proposed to
disable those DMA shortcuts only when activating the optional bridge and
keep them when it is absent. That runtime change is not implemented yet.
Direct writes outside GIF, the privileged mirror, FIFO and IRQ are also missing.

### Rendering DLL and ABI verified (2026-10-12)

The isolated module now builds `gow_pcsx2_gs_module.dll`, with its own ABI 1
of fixed-size structures, handles, state and thread validation. It receives
fragmented GIF and an 8 KiB PS2 privileged mirror, calls the original GSvsync
and explicitly copies the composited texture. It does not exchange C++ objects with
the consumer. Resources and surface are configured at creation; it does not change the runtime.

Contract without a device: DLL loaded, exports/ABI and arguments/handles
rejected correctly. GPU via GetProcAddress, without using the GS globals:
two correct cycles; busy singleton, closed handles, another thread, incomplete
registers and small buffer rejected; size/sequence query correct,
final guard intact and 2,048 exact RGBA pixels in each cycle.

Isolated negatives: omitting the thread or capacity guard compiles and makes the
control fail; restored, correct. The capacity negative physically reserves
more memory than the declared capacity to test the contract without causing
an access outside its allocation. The DLL remains render-only: IRQ/FINISH,
runtime FIFO/VRAM, mid-game activation and device recovery
pending. Details in the [module README](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/render/pcsx2_probe/README.md).
The new CI loads only the contract without a device; GPU verified locally.

### Privileged mirror for the adapter (2026-10-12)

`src/gow_gs_pcsx2_mirror.h` packs the runtime's 19 real registers into
their 8 KiB PS2 offsets, explicitly little-endian and with gaps zeroed.
It excludes vsyncTick: it is a runtime counter that takes space between CSR/IMR
in its compact struct. CSR is read atomically; the caller must synchronize
the other registers with their writer. The helper is not installed in the game yet.

Independent test with distinct values and multibyte CSR: correct in MSVC.
Cross-check of the 19 offsets and size against the **original** GSPrivRegSet via
static_assert: correct. Portable controls and real-header controls
are added to CI, plus Windows CTest. A copy of the 160-byte struct is not turned
into a valid copy of 8 KiB registers by merely padding its end.

Pending for a functional adaptation:

1. Link the verified ABI with an optional runtime hook that preserves bytes,
   order and thread, including the DMA shortcuts. Complete the necessary Host services;
   the absent services of this fixture remain limited.
2. Extend presentation to a visible window, resizing and device
   recovery; extend formats, CLUT, blending and depth/alpha test.
3. Add a privileged register mirror, CSR/FINISH/SIGNAL, local→host FIFO,
   initial VRAM and write/read synchronization. `GSopen` receives memory of
   **privileged registers**, not the 4 MiB of VRAM directly.
4. Link all of the runtime's submission and presentation paths in an optional
   patch with regressions, keeping CPU/OpenGL as references.
5. Full build, menu/intro/gameplay controls and scene comparison;
   then measure GS and game with diagnostics disabled. Changing the GS
   does not remove the EE/VU cost nor fix incorrect input geometry.

This first bridge is a verifiable preparation of the integration, with no FPS
or fidelity improvement attributed yet and without declaring DX11/DX12/Vulkan available.

### Optional connection to the runtime: preparation (2026-10-12)

Patch 103 adds `GSExternalObserver`: it copies the original GIF spans before
the internal shortcut, reports direct writes from stubs and reset, and delivers
VSync from `EeScheduler::VBlankStart`, before the game's callbacks/IRQ. Both
DMA shortcuts and native PACKED reject without consuming when there is an observer; without it
they keep their behavior. The runtime's GS remains the authority on
VRAM, FIFO, CSR, SIGNAL and FINISH. It is not a change to the default renderer.

`GOW_PCSX2_GS_DIAG=1` links the DLL from startup. It requires an absolute path
`GOW_PCSX2_GS_DLL`; it supports `GOW_PCSX2_GS_RESOURCES` for shaders. A dedicated thread
creates/consumes/closes DX11. FIFO queue with its own copy, 64 MiB and backpressure when it fills;
a failure stops the mirror and is logged. `PS2X_VU1_HILO=1` and
`PS2X_GS_FRENTE=1` are rejected: the first control requires coherent EE registers.

Optional private capture: `GOW_PCSX2_GS_OUTPUT` must be a new absolute folder;
`GOW_PCSX2_GS_CAPTURE_COUNT=0..16` (8 if there is a folder, 0 without it) and
`GOW_PCSX2_GS_CAPTURE_FROM_TICK` (900 by default). It saves BMPs of the PCRTC
composition with tick/sequence; minimum 120 ticks between captures. It does not represent the
texture acquired from OpenGL nor a frame aligned with external PCSX2.

Later extension: `GOW_PCSX2_GS_CAPTURE_EVERY_TICKS=1..600` keeps 120
by default and allows a burst of up to 16 consecutive ticks with value 1.
The driver supports `--pcsx2-capture-interval`. It is an explicit readback and is not
used to measure FPS. Fixture with two colors/reset/ticks 1 and 2 correct;
negative that forces 120 again loses the second capture and fails. Restored,
correct. The 19 Python tests of preparation/option rejection pass.

ABI 1 extends exports with direct write and reset. The adapter uses the legacy
index 0 only for a complete A+D and keeps Q; the game's PATH1/2/3 use 3/1/2.
Parser and GPU DLL pass with a direct write during an incomplete tag. Queue
with a copy/FIFO/backpressure/drain regression; Windows syntax correct. New
runtime regressions and full build/game pending in this commit.
There is no FPS measurement nor accredited fix of animation/framing.

### Runtime/DLL walkthrough and Windows environment (2026-10-12)

`gow_gs_pcsx2_client_test` uses the runtime's real frontend, observer, queue,
DLL and PCRTC composition. Two different patterns separated by a reset, delivered
in 13-byte fragments and with a direct write during an incomplete tag:
the two 64x32 images match exactly in their 2,048 RGBA. It drains the queue and
closes the module without failures. Run locally on Windows/DX11, not in GPU CI.

The fixture configures the environment with a real path that contains accents and a
`capturas_ñ` folder. It reproduces the failure of interpreting ACP bytes from `getenv`
as UTF-8. Fixed to `_wgetenv` and UTF-16 paths; resources converted to UTF-8
for the ABI. Previous negative code 1; fixed positive code 0. It does not change
chain 103: it is a src/ update on top of the full build.

### VSync and game controls with corrected field (2026-10-12)

Client 89ffb57 selects the field with CSR.FIELD from the same snapshot
that the DLL receives: `CSR.FIELD ? 0 : 1`, per the original MTGS. Passing the EE
parity directly, as the previous client did, inverted that convention.
Four-delivery client/queue/DLL regression without a device correct;
previous negative compiles/fails and restored passes. Six Windows CTests correct
and runtime/DLL/DX11 fixture of two colors/reset, 2x2,048 exact RGBA and clean shutdown.

Full build 103 and src/ update verified. Two shared
420 s controls with the corrected field end at the limit, with no logged mirror
failure; private cards intact. Inspector: 714/417 acquisitions without
anomalies in the recorded samples. Intro burst: 15 matching tick pairs
and one acquired without a pair within the PCRTC quota. HUD/NPC burst:
16 pairs 2100..2115; OpenGL shows much more fog than DX11 and differences in
NPC visibility. There is no validated visual parity, nor is the
cause yet identified among fog, depth, blending or a command-prefix difference.

Keep CPU/OpenGL and follow that contrast before changing the main renderer.
These runs activate two renderers, hash and readbacks: they do not measure FPS. The mirror
uses generic DMA paths and rejects VU1/GS-front threads. Full results and
next control in research-log.md; review and credits in review-urban-reign.md.

### Runner 105 with compiled VU1 (2026-10-13)

Synchronous and asynchronous shared 420 s controls with runner 105
frozen, both threads off, same DX11 module and private cards.
The first offers 16 pairs 2100..2115 of the intro; the second, 15
pairs 4000..4014 with HUD/Kratos/enemies and one acquired 3999 without a PCRTC of the
same tick within the quota. Correlated metadata and reviewed images.
The more intense OpenGL haze persists. The matching tick within the
run does not prove the same command prefix nor pixel equivalence.

The combined 105 run completes another 420 s, but uses only OpenGL: the mirror
keeps the rejection of both threads for register coherence. The three
controls, hash returns, final states and limits are recorded in research-log.md.
They are not benchmarks nor do they validate prolonged stability or PS2 framing.

### Declared precision of the DX11 mirror (2026-10-13)

The previous module inherited `AccBlendLevel::Basic` from GSOptions. In a
procedural corpus of 24 cases, with ZTE already fixed, four blends differed by one level
against CPU/compute/hardware, including two without FOG. A separate private Maximum DLL
matches 24/24 with the three backends without changing their blending. The
Basic reference is kept: its differences alone do not justify
another runtime fix.

The isolated module now sets Maximum explicitly; CMake supports
`-DGOW_PCSX2_BLENDING=Basic` to repeat the earlier controls and rejects
other values. When creating the GS it declares its precision in the log. ABI 1 and the
port's renderer are preserved. The optional control
`tools/render/probe_pipeline_reference.py` checks 24 cells of 8×8:
ZTE/ZTST, Z write and FOG followed by blending. It does not verify framebuffer alpha.

Game control with the private Maximum DLL and frozen runner 106: 420.39 s
by limit, card intact, no searched failure signatures; first
state 11 report at 50.17 s and last 11 at 415.47 s. 16 pairs 4000..4015 with
HUD/Kratos/enemies, 16 distinct RGBA and correlated acquired metadata.
672 recorded acquisitions without regressions, inconsistencies, A–B–A
returns or size changes; maximum tick distance 0.

**OpenGL's more intense haze persists against Maximum**, along with
differences in lines and poses. Same tick and run do not prove the same
GIF prefix: DX11 receives the VSync in EE before callbacks/IRQ; OpenGL takes
its presentation request in the host loop. Follow that order, composition,
depth and later passes. This control uses two renderers and readbacks;
it does not demonstrate unique FPS, normal shutdown, PS2 framing or prolonged stability.

### Private contrast at the same boundary (2026-10-13)

A second frontend/OpenGL receives the same spans/reg/reset/VSync as the DX11
DLL, under the ABI mutex, and captures before the next event. Patterns
24/24 and two fragmented cycles correct. 600.405 s control with runner 106
unchanged, card intact, state 11 until the last report and 16 pairs
4000..4015: the OpenGL haze persists. The diagnostic uses hardware in that
burst and does not prove the prefix of the host's image nor measure FPS. Data,
hashes, review and limits in research-log.md.

Besides the field history of DX11 Automatic, there are limits in the alpha of the
hardware mirror: in 16 composition patterns CPU/OpenGL match each other,
but hardware and the original GSRendererSW disagree in several cases. The original
software passes the 24 pipeline patterns and 14 FOG ones, although its private fixture
only accepts GIF and rejects direct writes. Do not use Maximum as proof of
exactness of all alpha nor change the runtime on the basis of a single reference.
Follow the merge prior to deinterlacing and the state/passes of a bounded burst.

The full FOG control also detects a hardware discrepancy when varying
FOG between the two sprites of the batch: 16/28, versus 28/28 for the original software
and CPU/OpenGL. The 14 historical controls only observed the left half
and still pass with `--left-only`; both are now checked by default.
The software also restores a synthetic Freeze/GIF/VSync burst with its
four images identical to its fresh run. The hardware disagreement is not
due to the Freeze of that pattern. Do not extrapolate it yet to the game's background.

### Merge and original software in the scene (2026-10-13)

Another private DLL keeps the original DX11 Maximum and captures its merge before
deinterlacing alongside the OpenGL shadow of the same boundary. Runner 106
frozen, threads off, 600.391 s control ended by limit and card
intact. It saves the original Freeze at 3999, with cache destinations read to VRAM,
and a limited GIF/VSync burst up to End 4015: 114,804,229 bytes,
100,082 registers, no direct writes. The original GSRendererSW restores
and replays those events: code 0, 17 images 3999..4015. The initial
deinterlacing history is not serialized; it is not another renderer integrated into the game.

With 16 trios reviewed in contact sheets and four complete ones after several fields,
the original software's background stays close to the hardware merge and OpenGL
keeps more haze/brightness. In the background region of 4004, mean difference
OpenGL−software +31.03/+37.26/+32.57 RGB; mean absolute software−hardware
0.49/0.50/0.45. These are local descriptions, with no image equivalence.
In that 4000 background, current PCRTC and hardware merge have identical RGB:
the later deinterlacing does not explain there the contrast with OpenGL.

Constant PMODE `0x8023` (both circuits, MMOD=1, ALP=128, SLBG=0),
SMODE2 `0x21fed1`, DISPFB1 `0x800000090d0` and DISPFB2 `0x90d0`.
Do not adjudicate the scene by the mirror's synthetic disagreements. The next
control compares a runtime backend field on CPU/GPU with its own state/VRAM,
to separate frontend and rasterization. Hashes, limits and next
steps in research-log.md. Original CPU/DX11 preserved; no new fix for
haze, benchmark, normal shutdown nor validation of prolonged stability.

### Backend field, alpha and limits of the CPU reference (2026-10-13)

A private 106 capture with Initial/Present/End contains 78,181 draws of one
field, none with FGE. The PCRTC reads FBP208, copied from FBP0 inherited at the start;
its single-field CPU replay keeps that GPU input. To separate that
effect, a synthetic request reads freshly drawn FBP0. It does not represent another
presented image of the game nor authorize comparing runs by tick.

The background RGB matches between CPU/GPU during the main geometry and
diverges in the 64 late triangles that blend with destination alpha (ALPHA.C=Ad).
That alpha already differs when preparing the mask through CT24/Z16/CT16. The Z24
of the inspected regions stays the same in those controls. Prefixes,
data and limits in research-log.md; no global equivalence nor single accredited cause.

Additionally, CPU 106 saturates ALPHA with COLCLAMP=0, while original software and GPU
wrap the RGB. Four procedural patterns confirm the expected ones;
the hardware mirror fails the two negatives and does not replace the software
reference on this path. CPU patch 107 fixes that selection and has
negative 2/4/positive 4/4; full incremental suite 617/617 and 657/657 GPU.
It still requires the mandatory build, CI and a functional control. The darker
CPU before that fix did not prove
that its mask was faithful. GLSL is not modified nor is the GPU
haze declared resolved. Earlier references, captures and runner 106 preserved.

### Progressive PCRTC composition: reproducible probe (2026-10-14)

`tools/render/probe_pcrtc_reference.py` records 32 uniform CT32 patterns,
independent FBP0/32 sources and a 64×64 output. It uses the original module's ABI,
without assets or a game process; save the JSON and registers in a new private
folder. It requires Windows, local original resources and a free GPU.
Run sequentially, preferably with the original GSRendererSW:

```powershell
py -3 tools/render/probe_pcrtc_reference.py --module <DLL-original-SW> --resources <recursos-PCSX2>
```

The output contains the SHA-256 identity and EN/MMOD/SLBG/ALP/alpha/RGBA of each
case. The software still uses the original DX11 compositor. In the local
109 probe, the original hardware differs from the software in four cases with
framebuffer alpha. The ideal UNORM model matches 31/32 RGB and differs
by one red level at ALP 201; blending precision allowed by D3D11, section 17.5,
not a global scene tolerance. Source and results in research-log.md.
The control is progressive and uniform: it does not prove interlacing, different
rectangles, feedback, an image acquired by the host nor stability.

### Compositor 109 and title/ship controls (2026-10-14)

Patch 109 keeps RC1 blended with BGCOLOR even when RC2 is off,
and rounds the UNORM weighted sum in CPU/GLSL. Full 109 finished 0,
source 3fb7148, compiled VU1/501 private micromemories and 13 linked files.
The incremental suites 622/622 and 666/666 GPU and the negatives/positives of
PCRTC are closed; the full identity and the limits are in research-log.md.

The title was contrasted within a single run with DX11 merge,
109 shadow, restored original software and acquired: the four reviewed
sources show "New Game". The menu script's capture downloads the
current VRAM with latched CRTC; it is not the texture acquired by the window.
Its samples without options do not prove a title regression.

In scene 109, Freeze 3999..End 4015 and the same GIF/VSync produce 17 restored
SW fields. The 16 trios reviewed and the complete quartets 4004/4015
contain HUD/Kratos/enemies. The background stays close to the original software;
different lines/pose persist and no initial field history is kept.
The acquired image is not identical to the shadow merely by sharing a tick and does not yet
prove its GIF boundary. Do not declare global parity, an FPS improvement,
PS2 framing or prolonged stability from these captures.

### Original snapshot and effective mode: optional ABI1 extension

`gow_gs_read_video_info` returns the recognized mode, effective interlacing,
InterlaceMode, PCRTCAntiBlur and SMODE1/SYNCV/SMODE2 with the module's sequence.
`video_mode` uses the GSVideoMode enum of the pinned source; VESA is not equivalent
to confirming the PS2's physical mode if timing registers are missing.

`gow_gs_read_snapshot` calls the original `GSRenderer::SaveSnapshotToMemory`,
with Stretch 0/Auto 1/4:3=2/16:9=3. First call with nullptr/capacity 0:
BUFFER_SMALL delivers dimensions and saves the snapshot. The later read
requires the same handle, sequence, aspect and window. VSync/reset/close
invalidate the cache; it does not silently recompute another capture. Window 0/0
keeps the internal resolution, with aspect expansion if requested; both
dimensions must be zero or be in 1..2048. The original transparency filter,
rescaling and bands are applied, so it does not replace the raw output.
The earlier structs/calls keep ABI1. Check the new exports
when loading old DLLs; the game's client still uses the previous interface.

Control without assets, Windows/free GPU, sequential:

```powershell
py -3 tools/render/probe_snapshot_reference.py --module <DLL-nueva> --resources <recursos-PCSX2> --output <carpeta-nueva-privada>
```

Without `--output` it prints JSON without PNG and does not require Pillow. It produces 16 uniform
aspect/window cases and effective mode; it does not measure FPS nor establish the
game's framing. Local validation and limits in research-log.md. In the row
matrix it was verified that PCRTCAntiBlur changes the reference's offsets:
keep the configuration alongside the result, in addition to GIF/VRAM/VSync.
