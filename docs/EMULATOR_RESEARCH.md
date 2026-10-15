# Emulator research for the two top problems (2026-10-15)

Research only, no code changed, game not run. Sources: PCSX2 master (`GameIndex.yaml`, `GSRendererHW.cpp`,
`Gif_Unit.h`, `IPU_Fifo.cpp`) read through raw.githubusercontent.com. Web search for GoW-intro-FMV bug reports, Play!
IPU internals and recompilation write-ups returned nothing useful; claims marked (memory) come from general
knowledge and were NOT verified in this session. Treat them as leads.

## 0. Known GoW1 settings in PCSX2

Source: https://github.com/PCSX2/pcsx2/blob/master/bin/resources/GameIndex.yaml, entry `SCUS-97399`.

| Setting | Value | Meaning for us |
|---|---|---|
| `halfPixelOffset` | 5 ("special, texture") | Fixes misaligned effects. Our bit-exact GS does not need it; shows GoW effects are sub-pixel sensitive. |
| `autoFlush` | 1 | "Sun goes through walls": the sun occlusion test reads back the depth/colour written by earlier prims of the same frame. This is exactly our feedback/z-alias class. |
| `speedHacks` / `gameFixes` | none | No MPEG, IPU, GIF, VIF or EE-timing fix is needed for GoW1 in PCSX2 (compat 5 = perfect). |

GoW2 (`SCUS-97481`) adds `mvuFlag: 0` (MVU flag hack off, fixes attacks turning into squares), `alignSprite: 1` (water
vertical lines), `nativeScaling: 1` (light blooms). Same engine family: blooms are made of sprites that sample the
frame, so strip/page alignment matters (see B).

Consequence for A: PCSX2 plays the GoW1 intro with default settings, using its normal IPU + GIF PATH3 paths. The
bug is therefore most likely in our IPU/MPEG/DMA emulation or ordering, not an engine quirk that needs a hack.

## A. Intro FMV garbage

### What PCSX2 does that matches the GoW path

1. **IPU FIFOs and DMA** (`pcsx2/IPU/IPU_Fifo.cpp`). Two 8-quadword rings. IPU1 (DMA ch4, bitstream in) refills when
   the level drops to <=1 qword; data-request is cleared when full. IPU0 (DMA ch3, decoded macroblocks out) writes
   raise an IPU0 interrupt when ch3 is running. There is an explicit hack on a magic value in the ch4 cycle counter
   to model a "waiting" DMA state. Takeaway: the stream is consumed in small credit-based bursts; a stub that
   swallows the whole PSS ring or decodes at call time skips the DMA-completion interrupts/tag progress the game's
   `sub_00188B80` state machine may wait on (it polls the ring state at `0x30DE38`).
2. **GIF arbitration** (`pcsx2/Gif_Unit.h`, https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Gif_Unit.h).
   Fixed priority PATH1 > PATH2 > PATH3. PATH3 holds the GIF until EOP; only if `IMT` is set and PATH3 is in IMAGE
   state can it be sliced at the image tag by PATH1/2. A masked PATH3 (`MSKPATH3` via VIF1, or GIF_MODE.M3R) is never
   started; if it reaches EOP while masked it goes to wait and **unread DMA data after EOP is rewound** (`dmaRewind`)
   so the DMA pointer equals what was consumed. `CanDoPath2HL` (DIRECTHL) never interrupts PATH3.
   Takeaway: GoW FMV frames are typically uploaded as PATH3 IMAGE (via a DMA chain with MSKPATH3 toggles from VIF1
   `MSKPATH3` / `FLUSH` codes). If our model consumes bytes past the EOP of a masked packet (or interleaves a DIRECT
   packet into the middle of a PATH3 IMAGE packet without IMT), the DMA chain desyncs: later qwords of image data
   get read as GIF tags, which produces exactly "thousands of line/point prims with flat colours". Our patches
   `ps2recomp-gif-stream.patch` / `vif-direct-fragments` model `m_path3Masked` + `m_path3MaskedFifo`; compare their
   EOP/rewind behaviour with the rule above.
3. **PATH3 masking history**: https://pcsx2.net/blog/2011/path-masking-geometry-syncing - garbled textures/geometry
   were traced to PATH3 packets lumped together without stalling on the mask. Same class of bug.
4. **FMV in software renderer** (PCSX2 game fix "Switch to software renderer when FMV plays", memory: `FMVinSoftware`;
   wiki: Silent Hill 3). It exists because the HW renderer cannot cope with FMV frames written as
   uploads+draws; it is a renderer-level workaround and tells us nothing about the IPU. We already show the bug on
   the CPU renderer, so the renderer is not the cause.
5. **"Skip MPEG hack"** (memory, unverified): PCSX2 has a game fix that skips MPEG decode for titles whose FMV hangs.
   It is an emulation-side stub of the IPU decode, similar to our `GOW_SKIP_FMV=1`.

### Ranked ideas (A)

| # | Idea | Where | Expected effect | Risk |
|---|---|---|---|---|
| A1 | Audit what the recompiled game does to guest RAM during the movie: log every VIF1/GIF DMA chain tag address and every IOP->EE SIF DMA destination (PSS stream, sound `cmd=0x40`) and flag any write inside a live DMA-list buffer or the ring `[0x30DE10+0x14]`. Garbage prims appear because a PATH1/VIF packet contains data that is not a GIF packet; the usual cause is a data buffer (decoded frame, ring, IOP copy) overlapping a display list. | diag in a new `patches/ps2recomp-*-diag.patch` (do not extend runtime patch); SIF code is in `ps2recomp-dma-iop-timers-cache.patch`/`iop-*` | Pinpoints the producer of bad qwords; the ESTADO "next step 1". | Low |
| A2 | Check PATH3 EOP/mask/rewind rule (point 2 above) and IMT slicing against `ps2recomp-gif-stream`, `gif-arbiter-buffers`, `gif-image-order`, `gif-image2`. Write a unit test (ps2xTest): masked PATH3 chain with data past EOP must not consume past EOP; DIRECTHL must not split a PATH3 IMAGE. | patches above + `ps2xTest/` | Fixes desync if our DMA pointer advances past a masked packet. | Medium (touches hot GIF code) |
| A3 | Decode-side contract: PCSX2 completes IPU1 DMA (ch4) in credit bursts and raises IPU0 completion interrupts. Make our `sceMpegGetPicture`/IPU stub (`Kernel/Stubs/MPEG.cpp`, `ps2recomp-mpeg-*.patch`) honour the same: advance the game's ring read pointer in 16 KB chunk steps, fire the registered `sceMpegAddCallback` types (Nodata/Restart/Stop DMA/Background/TimeStamp) in the order the real libmpeg would, and update the DMA channel registers (CHCR/QWC/MADR of ch3/ch4) the game polls. The `a2=0` argument is the callback user pointer, not a buffer, so ignoring it is probably fine, but check `mult $zero` anyway. | MPEG patches | Explains why only the movie's concurrent work (not our pixels) triggers corruption: wrong DMA register state makes the game DMA over its own lists. | Medium |
| A4 | Compare with a reference run: PCSX2 can dump GS packets (`.gs` dump, "Save GS dump"); diff the first 12 frames of GIF packets against ours with `PS2X_GS_DIAG` on the CPU backend. Requires the user's PCSX2 and the ISO. First differing packet tells which path (VIF1 unpack, DIRECT, PATH3) diverges. | tools/, no repo code | Best localizer, no guesswork. | Needs user action; keep out of repo (legal) |
| A5 | Check VIF1 `MSKPATH3` handling when the chain mixes `FLUSHA`/`MSKPATH3`/`DIRECT`: a movie frame upload usually is `MSKPATH3 off; FLUSHA; DIRECT(...); PATH3 IMAGE via ch2 tag; MSKPATH3 on`. A lost un-mask or a stale queued PATH3 packet after a re-mask (our `m_path3MaskedFifo`) would replay stale data later. | `ps2recomp-gif-stream.patch` | Same class as A2; cheap to log (`[gow-gif]` counters of masked-queue depth per frame). | Low |
| A6 | Last resort / fallback product decision: keep `GOW_SKIP_FMV` default-on until A1-A4 land, like PCSX2's "skip MPEG" fix. | launcher default | Playable game now. | Loses the intro (accepted by owner? ask later) |

## B. Performance: feedback, Z-as-colour, z-alias

### What PCSX2's hardware renderer does

Source: https://github.com/PCSX2/pcsx2/blob/master/pcsx2/GS/Renderers/HW/GSRendererHW.cpp (function names only).

- Frame/Z sources are `GSTextureCache` targets. A draw is a "feedback" draw when the source target overlaps the
  current frame range (`draw_uses_target`, `tex_is_rt`). It then runs as a **real feedback loop**:
  `DetermineBarriers` picks none / one barrier / full barrier per draw, downgrades a full barrier to one barrier
  when the primitives do not overlap each other, and only builds a per-primitive draw list
  (`ComputeDrawlistGetSize`) when a full barrier is truly needed. Back-ends: framebuffer fetch, texture barrier
  (`VK_EXT_attachment_feedback_loop_layout` / texture-barrier), or a copy of the RT per draw.
- **Depth as colour** (the blur/bloom trick): `LookupDepthSource` creates a depth-format source; if Z and frame
  block offsets differ it uses a temporary Z (`m_using_temp_z`, `SetTemporaryZ`) that is copied back after the draw.
  `IsTBPFrameOrZ` decides whether an address is colour, depth or both from masks and test state.
- **Channel / texture shuffles** (`DetectTextureShuffle*`, `IsPossibleChannelShuffle`, `ConvertSpriteTextureShuffleImpl`):
  8-px wide sprite strips reading the frame at an offset are classified (Copy, Offset, RegionRepeat, Swizzle,
  TwoPixel...) and merged into ONE full-size quad. This is the PCSX2 answer to "32-px strip effects": the strips
  are recognized as a single page-aligned copy, so no per-strip sync is needed.
- **autoFlush** (GoW1 setting): flush the batch after every primitive whose source is the current target so the
  next primitive reads the previous result. Exact but slow; it is what our `tex-feedback` CPU path emulates.
- **DATE / dest-alpha test**: `EmulateDATESelectMethod` picks stencil, primitive-ID tracking, or barrier depending on
  overlap. Primitive-ID (first-pass marks, second-pass reads) avoids barriers; useful idea for our dest-alpha-test.
- Sprite/page alignment: `alignSprite`, `halfPixelOffset`, `nativeScaling` GameDB toggles show the effects are
  page-aligned sprites; PCSX2 relies on this alignment to batch them.

### How these map to our compute backend

Our backend already has exact serial semantics (one dispatch per prim, barrier between). The cost is the CPU
fallback, not a missing exact approach. Because VRAM is a bit-exact storage buffer, "feedback" only needs the
**source read to see the right version of pixels**, which a copy or ordering rule can give on the GPU.

### Ranked ideas (B)

| # | Idea | Where | Expected effect | Risk |
|---|---|---|---|---|
| B1 | **Snapshot-copy feedback on the GPU.** When a sprite's source rect (the UV box, already used) overlaps its own target, `vkCmdCopyBuffer` that rect region (or its pages) to a scratch region of a second buffer before the dispatch and sample from it (a second descriptor for the "texture VRAM"). Valid when the sprite's reads of pixels it writes in the same prim are all from before the prim (true for non-overlapping dst/src or identical-pixel read-then-write per thread: each thread reads its own pixel then writes it). Matches PCSX2 "one barrier" case. | `gs_vulkan_backend.cpp` + new shader binding in `ps2recomp-gs-vulkan.patch` follow-up (new patch per AGENTS.md) | Removes most of ~1,000 `tex-feedback` prims/s (~430 ms/s CPU + GPU drains). Estimated 1.5-2x FPS at gameplay. | Medium. Bit-exactness for sprites that read a texel written earlier within the same sprite (CPU raster order); verify by CPU-vs-Vulkan byte compare in existing tests. |
| B2 | **Same-thread read-then-write detection.** If texel (u,v) maps to the thread's own pixel (identity or constant 32-px page remap) no copy is needed at all: the thread reads before it writes, so no race exists. Extend the old "overlap test" to prove identity mapping (cheap: compare TBP0/TBW/PSM with FRAME and UV == XY + const). | CPU decision function (`gowTextureAliasesTargets` callers) | Turns most 32-px strip effects into normal GPU draws with zero copies. | Low if identity is proven strictly; wrong proof = visible corruption, so test with the existing byte-identical harness. |
| B3 | **Z-as-colour via a batched Z snapshot.** For CT24/CT32 reads of the Z buffer (z-alias) where the destination is a different page range, snapshot the Z pages once per consecutive run of such sprites (PCSX2 `m_using_temp_z`/ `LookupDepthSource`) and use it for all following prims until a prim writes Z in that range. Our notes already say "the Z-copy case is order-safe as a snapshot". | backend run logic | Removes `z-alias` fallbacks (~255 prims/s). | Low-medium: invalidate on any Z write overlap |
| B4 | **Tile binning with per-tile ordered lists** (compute analogue of PCSX2's draw-list barrier downgrade): bin prims into 64x32 pages, run one workgroup per page that processes its prims in order. A page then owns its pixels for the whole batch: feedback within a page becomes ordinary sequential reads/writes in shared memory or L2 with no inter-dispatch barriers. Cross-page feedback (strip effects reading neighbouring pages) still needs a barrier or snapshot. | new kernel; large | Eliminates the per-prim barrier too (all other cost). Biggest win but biggest work; only for after B1-B3. | High |
| B5 | **Dest-alpha-test via primitive-ID style two passes** (PCSX2 DATE primitive-ID method) is not needed in compute: the thread reads dest alpha itself. Keep it in the single dispatch; only fall back when the prim writes alpha it also tests in an overlapping later prim. Review which condition forces the CPU path today. | `gs_vulkan_backend.cpp` support check | Cheap if the fallback condition is over-conservative. | Low |
| B6 | **Backpressure**: not an emulator topic; PCSX2 solves EE/GS decoupling with an MTGS ring plus a "GS sync" only at vsync/read-back. Replace the GIF-mutex handoff by an SPSC ring of full GIF packets (PCSX2 `AddCompletedGSPacket` queue) so the EE never blocks while GS has capacity; block only on Finish/read-back. | `ps2recomp-gif-arbiter-buffers.patch` / `gs-front-thread` | Removes the EE stall; helps frame pacing. | Medium (ordering with FINISH/signal) |

`VK_EXT_fragment_shader_interlock` and texture barriers are graphics-pipeline tools; we are in compute, so the
equivalent is "snapshot copy" (B1/B3) or "per-page ownership" (B4). Not worth switching pipelines.

## Recommended next tasks (max 6)

1. (A1) Diagnostic: log writes/DMA tags that alias live DMA lists during the movie (EE RAM write watch on ring and
   display-list buffers; SIF IOP->EE destinations). Sonnet. New diag patch only.
2. (A2+A5) Unit tests + review of PATH3 EOP/mask rewind, IMT slicing, DIRECTHL vs PATH3 IMAGE, stale masked queue.
   Sonnet; Opus if it needs to rewrite arbiter code.
3. (A3) Align MPEG stub with libmpeg semantics: chunked ring advance, callback order and types, ch3/ch4 register
   updates. Sonnet, after task 1 shows which side is wrong.
4. (B2+B1) Identity-mapping proof for tex-feedback, then GPU snapshot copy for the rest; byte-compare with CPU
   backend. Sonnet (Opus for the shader/barrier correctness review).
5. (B3) Z snapshot batching for z-alias. Sonnet.
6. (B6) SPSC GIF packet ring to end EE mutex stalls. Sonnet. B4 tile binning is deferred (Opus, own design doc).

Optional (user): capture a PCSX2 GS dump of the intro for task A4 (not stored in repo).
