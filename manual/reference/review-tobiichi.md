# Review of Tobiichi-Port (2026-10-12)

Reviewed at the user's request: [YYOzcan/Tobiichi-Port](https://github.com/YYOzcan/Tobiichi-Port),
HEAD `ac6a8ada90d5ee6cf1417d77cf122a31c6734c9a`, GPL-3.0 license. Selective reading of code/diffs
through GitHub; its tree is not cloned and no game data is downloaded. Its `.kiexster-sync` records
`a42d77f7052fcf016dd829dd9c932f12f55f9388`:
it does not replace our later main nor authorize overwriting its fixes.

## Changes reviewed

The [commit `27ab4c0`](https://github.com/YYOzcan/Tobiichi-Port/commit/27ab4c04702f07c34acf653fd109e50659ad3824)
adds a Qt launcher, fullscreen/aspect ratio, FSR1 EASU+RCAS/FXAA, panoramic mode,
presentation mailbox, configurable 8x8 tiles and VIF/VU1/audio optimizations.
The [commit `017cbaf`](https://github.com/YYOzcan/Tobiichi-Port/commit/017cbafb0a52f675c7ba2976424d76b28297f47b)
introduced real-time VBlank, IOP batches and compiled VU1/audio adjustments.
Its performance figures are that author's measurements on Linux; they have not been
reproduced here nor do they vouch for our Windows executable with an interpreted VU1.

| Topic | Comparison and usefulness |
| --- | --- |
| FRAME/TEX0: pages versus blocks | Our runtime already normalizes those addresses; do not add the same fix again. |
| Reused GIF arbiter buffers | Already present in our runtime integrated with Opus. |
| VF0/VI0 and enabling compiled VU1 | Already restored after pairs and the APIs are enabled; our current controls contain no compiled game programs. |
| 8x8 tiles and split dispatch | A change different from ours, which keeps 16x16. Candidate for an independent pixel and performance test; preserve a 16x16 option and cover the 65,535-group limit. |
| FSR1/FXAA/aspect/launcher | Possible later presentation improvement. It does not fix input geometry or animation nor replace the GS rasterizer with DX11. Keep the original aspect in comparative controls. |
| Optimized VBlank/IOP/VIF/VU1 | Review by topic with regressions and EE/IOP/VU1 coordination; outside the current presentation change. |

## Limits observed in its presentation

In [gs_threaded_backend.cpp](https://github.com/YYOzcan/Tobiichi-Port/blob/ac6a8ada90d5ee6cf1417d77cf122a31c6734c9a/PS2Recomp/ps2xRuntime/src/lib/gs/gs_threaded_backend.cpp),
the mailbox and its flag are global. The constructor sets the flag, but the
destructor does not clear it nor flush the last frame; there is no mailbox reset
in the file. By inspection, a new instance may inherit earlier state or
contents. That case has not been run: it requires a creation/reset/close
regression before adapting the idea. Moreover, it is a RAM path for
Linux without a shared context, not the WGL shared-texture selection that we
investigated on Windows.

In [gs_gpu_backend.cpp](https://github.com/YYOzcan/Tobiichi-Port/blob/ac6a8ada90d5ee6cf1417d77cf122a31c6734c9a/PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_gpu_backend.cpp),
`throttleGpuFrames` ignores the result of `ClientWaitSync` and deletes the fence
after waiting at most 100 ms. If it expires, the amount of pending work
is not strictly bounded as its comment claims. The new
`frameFences` are also not explicitly deleted in the destructor observed.
These are review findings, not reproductions of game failures. Do not copy
that control as is, nor remove fences/global glFinish to hide problems.

Opus is not modified and no code from that fork is incorporated during this review.
Priority: first finish the functional controls of the PCSX2 mirror of #68;
then evaluate tiles or filters in separate changes and with our own evidence.
