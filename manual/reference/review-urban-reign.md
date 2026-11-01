# Review of the Urban Reign GS integration (2026-10-12)

The author `thiagordsfx` publishes the link in
[PR #68](https://github.com/KIexster/god-of-war-recomp/pull/68).
Hand-written files of
[urban-reign-recomp at `8fcce75`](https://github.com/thiagordsfx/urban-reign-recomp/tree/8fcce75fcbcca3e558073180becb8654f3c396a8)
are reviewed, without cloning game data or running its port. GPL-3.0 license compatible;
if code of theirs is incorporated, keep the license and credit the author.
Our own existing adaptation is kept.

Its [GS document](https://github.com/thiagordsfx/urban-reign-recomp/blob/8fcce75fcbcca3e558073180becb8654f3c396a8/docs/GS_PCSX2.md)
describes a DX11 renderer, a child window of the raylib window, raw GIF,
privileged registers, FIFO, VRAM saving and scaling options.
The figures of 60 FPS and 8x are its Urban Reign checks; they are not
God of War measurements nor a prediction of EE/VU performance.
It uses the same PCSX2 `2954ebe` as our independent recipe.

## Finding that affects our mirror

In [Bridge.cpp](https://github.com/thiagordsfx/urban-reign-recomp/blob/8fcce75fcbcca3e558073180becb8654f3c396a8/thirdparty/pcsx2-gs/compat/Bridge.cpp),
VSync uses `CSR.FIELD ? 0 : 1`. This is independently confirmed in the
[original pinned MTGS, line 503](https://github.com/PCSX2/pcsx2/blob/2954ebe6965669219f1bbd256e958fbd8f83a85d/pcsx2/MTGS.cpp#L503).
Our EE sets CSR.FIELD with the counter's parity, but the earlier client
passed that parity directly to GSvsync: inverted convention.

The client is adjusted to select the field from the **same copy
of CSR that the DLL receives**, with MTGS's convention. It does not change the EE
counter, the IRQs, the usual renderer or the VRAM/FIFO authority. A procedural
DLL receiver is added to check four real deliveries from the client:
field change, held field, return, unrelated bits and independent ticks.
Validation when preparing this entry was pending; verified afterwards:
six CTests without GPU correct, including the client/queue/DLL delivery; a negative
that returns to the previous field compiles/fails and, restored, passes. Public header
intact. The runtime/DLL/DX11 fixture keeps two exact 2,048 RGBA images,
reset, fragments, direct register and shutdown without failure. The earlier captures keep their identity and
do not certify interlacing parity. This mirror failure is not presented
as the cause of the original port's spasm or framing.

Corrected client `89ffb57` rebuilt on the complete chain of 103; CI of
that correct code. Later controls with the game and their limits
are recorded in [ESTADO.md](research-log.md); do not attribute to it the captures of the earlier client.

## Useful parts for the next integration

- The child window avoids presenting DX11 and OpenGL on the same surface; it requires
  testing input, size, focus and recovery. Our module has only verified
  hidden window and PCRTC mirror; the visible backend is later work.
- `ReadFifo` and `ReadLocal` show the original PCSX2 points needed
  to return GS->EE transfers. `SaveVram` forces cache write-back
  before copying; `LoadVram` resets targets. Do not replace a full copy
  of the GS state with a VRAM copy: parser, registers, fragments and transfer cursor
  also need verified restoration.
- It keeps SIGNAL/FINISH/LABEL in the core. This matches our mirror
  separation and avoids assuming that the renderer's handlers generate those IRQs.

Its fixes `alignSprite`, `textureInsideRT`, `halfPixelOffset` and
`GSC_UrbanReign` are pinned for SLUS-21209. Do not carry them over to SCUS-97399
on account of backend similarity. God of War's configuration must be contrasted
with its original entry and with the observed scene.

In [gs_pcsx2_backend.cpp](https://github.com/thiagordsfx/urban-reign-recomp/blob/8fcce75fcbcca3e558073180becb8654f3c396a8/runtime/ps2xRuntime/src/lib/gs/gs_pcsx2_backend.cpp),
the cadence log counts a new draw if it received at least 4 KiB
of GIF. It is a heuristic; that counter is not a pixel hash nor does it prove
that an image is different. Do not use it to declare resolved a return
of old content. The review does not reproduce its full transport,
thread stability nor scene equivalence.

## What the SDK coverage means

The [map and its details](https://github.com/thiagordsfx/urban-reign-recomp/blob/8fcce75fcbcca3e558073180becb8654f3c396a8/docs/status/details.en.md)
classify 983 functions of static libraries linked into SLUS-21209.
`functions.csv` contains address/size; the status is assigned by groups in
`data.toml`. That 100% is not a complete Sony SDK for PC nor an independent
validation of all its functions in SCUS-97399.

In [hle_bindings.cpp](https://github.com/thiagordsfx/urban-reign-recomp/blob/8fcce75fcbcca3e558073180becb8654f3c396a8/src/urban/hle_bindings.cpp)
functions are identified by name and runtime services are bound.
GS/DMA/VIF, libpad, libmc and newlib keep original recompiled code.
Therefore what is reusable is the implementation of common services and the identification
method; not its addresses, game modules or generated C++.
SIF/RPC/IOP, files, controller and MPEG/IPU require per-service comparison and
tests with our own edition. EE/IOP/VU will be coordinated with Opus before changing
their areas; this review does not modify their checkout.

An example of a limit: its alias of `sceCdLayerSearchFile` discards the layer
argument, because Urban Reign uses a single-layer disc. Do not carry that assumption over to
God of War's 8.5 GB ISO without validating searches/reads. The map also
marks several library boundaries as approximate. Keep our status
based on what is verified; do not automatically import its green labels.

## Credits

To **thiagordsfx**, author of [urban-reign-recomp](https://github.com/thiagordsfx/urban-reign-recomp),
for publishing their integration and sharing it with this project. Their Bridge.cpp
made it possible to detect our mirror's incorrect field convention;
our own fix was contrasted with the original MTGS. The GS used comes
from PCSX2 and keeps its GPL-3.0+ notices. This review does not import game code.
