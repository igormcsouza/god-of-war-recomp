# Bilinear feedback: procedural reduction

The generator `tools/render/generar_feedback_gs.cpp` accepts `--altura 1..416`.
It reduces only the geometry of its two 32-pixel-wide sprites; it keeps
the texels, freeze and initial registers. The default case remains at 416
rows and its three `.gs` dumps match byte for byte the explicit 416 option.
Invalid options are rejected before any files are created.

The `.bin` capture and the `.gs` dump share the same height. The verifier
`tests/gs_feedback_dump_test.cpp` takes `--altura` as an independent expected
value: it checks the exact freeze, the vertices, the GIF PATH3 and the
4 MiB of the CPU End. A different expected height must fail. It does not change the
file format or the size of the presentation (512×448).

## Reproduction on Windows

After `scripts\compilar_replay_gs.cmd`, from the checkout root:

```powershell
logs/generar_feedback_gs.exe logs/feedback_1 --pcsx2 --altura 1
logs/gs_feedback_dump_test.exe logs/feedback_1 --altura 1
logs/repetir_gs.exe logs/feedback_1/feedback_gs_self.bin hardware --repeticiones 3 --pausa-ms 1000 logs/feedback_1/live
logs/repetir_gs.exe logs/feedback_1/feedback_gs_self.bin hardware --snapshot-feedback --repeticiones 3 --pausa-ms 1000 logs/feedback_1/snapshot
```

Both replays return 1 because of a difference from the CPU; the generator and the
verifier return 0. A result of 1 does not mean an invalid capture: here
the End reproduces the CPU exactly and the GPU candidate is the one that differs.
Confirm that the hot passes do not use compute tiles before comparing.
Do not interpret their timings as game FPS.

## Observed result on RX 5700 XT

Previous shader (`PS2X_GS_HW_DISCARD_UNCOVERED=0`), three passes per policy,
full initial restore. The table uses pass 3 and compares 2/3 for
stability; in both there are two hardware primitives and zero compute tiles.

| Height | CPU/direct hardware: bytes | Direct 2/3 variation | CPU/snapshot: bytes | Snapshot 2/3 variation |
|---|---|---|---|---|
| 1 | 3 | 0 | 3 | 0 |
| 31 | 93 | 0 | 93 | 0 |
| 32 | 96 | 0 | 96 | 0 |
| 33 | 188 | 0 | 188 | 0 |
| 64 | 378 | 0 | 378 | 0 |
| 416 | 4,580 | 27 | 4,557 | 0 |

The variation is an observation of those repetitions; zero bytes in one sample
does not guarantee the absence of races. The one-row reduction does leave
a stable difference of a single pixel: `(32,0)`, CT32 byte 4096. The CPU gives RGB
`(141,90,98)` and the hardware `(132,87,86)`; alpha matches.

The CPU keeps its 8 KiB texture page between the two Submits. Its initial
texels `(31,0)` and `(32,0)` are `(123,85,197)` and `(160,96,0)`;
their integer average produces `(141,90,98)`. The first sprite writes `(104,79,172)`
at `(31,0)`: rereading that value in the second produces `(132,87,86)`, equal to the
observed GPU. This points toward cache persistence between primitives.
Freezing per Submit keeps the value already written by the previous one and does not
reproduce that persistence either. The CLI verifier also fixes the CPU RGBA of
that pixel as an independent control.

The 32/33-row boundary changes the first byte different from 4096 to 65540.
It is a hint for studying page replacements and neighboring bilinear accesses;
it does not justify freezing the whole texture until TEXFLUSH or changing the renderer's
policy by default. The next fix must preserve the CPU output of these cases and the
disjoint-source/nearest controls.

## Controls without the game

`tests/gs_feedback_height_cli_test.py` covers heights 1/31/32/33/64/416,
TEXFLUSH/scissor separations, wrong expected heights, limits and duplicated
options. It checks invariant freezes and the exact default; the previous
version of the generator fails when asked for the first reduced height.
The two executables and this control are integrated into CI. The tools are
built and tested on Windows without recompiling the game: the runtime, FPU, EE, IOP and
VU1 are not modified in this change. The patterns are our own and
procedural; they contain no bytes from the game.

## Causal persistence probe (2026-10-09)

The replay adds `--invalidar-cache-submit`, only with the `cpu` candidate. Before
each Submit it exports its state, invalidates only the page tag and restores it;
it keeps the cache bytes, as TEXFLUSH does. The CPU reference and the captured
End remain intact. It is a diagnostic intervention,
not a renderer fix nor an emulation of the cache on the GPU.

```powershell
logs/generar_feedback_gs.exe logs/feedback_cache --altura 1 --separaciones
logs/repetir_gs.exe logs/feedback_cache/feedback_gs_self.bin cpu --invalidar-cache-submit --repeticiones 2 logs/feedback_cache/sonda
```

It returns 1 because of a candidate difference. The reference must still give
`CPU vs captura final: bytes=0`. If it does not reproduce End/state, the replay returns
3 and does not accept that case as a causal result. The option is rejected with GPU,
if duplicated or if combined with `--snapshot-feedback`.

On 54 own patterns (six heights × three sources/filters × three separations)
each candidate is repeated twice, including full initial restore:

| Height | Bilinear self/scissor: different bytes due to invalidation | With TEXFLUSH between sprites | Disjoint source or nearest |
|---|---|---|---|
| 1 | 3 | 0 | 0 |
| 31 | 93 | 0 | 0 |
| 32 | 96 | 0 | 0 |
| 33, 64, 416 | 0 | 0 | 0 |

The intervened minimal case gives RGB `(132,87,86)`, equal to the observed GPU; the
reference keeps `(141,90,98)`. Scissor is not equivalent to TEXFLUSH. The bases
exported after each sprite confirm the page replacement: for CT32 with
width 512 they are `floor((altura-1)/32) * 65536`, plus 2 MiB for a disjoint source.
Both candidates end at the same base; in the small self and
scissor cases the bytes of that page differ after the second sprite.

From 33 rows on, the first primitive ends up reading another page and the second
already causes a natural miss. Invalidating between Submits does not change its output;
this intervention neither explains nor fixes the GPU divergence inside the
large primitive. The future implementation must preserve persistence
and the replacement order, including bilinear reads, before being extended
to multiple pages or enabled in the game.

`tests/gs_texture_cache_causality_test.py` integrates these checks into CI:
VRAM, page/cache bytes, RGB, images and repeatability. It also checks
that a tampered End still fails with code 3 and that invalid options do not
create files. On Windows it passes against the official 77-patch runtime;
the previous replay fails when asked for the new probe. It does not change the runtime
nor require recompiling the game executable. No FPS gain is attributed.

The one-row case is also repeated on the RX 5700 XT with the default discard:
three passes, 1 s pause, passes 2/3 with two hardware primitives and zero compute
tiles. Both keep three bytes different from the CPU, with no variation between
them. Its PPM image matches exactly that of the intervened CPU candidate.
The first pass uses four compute tiles and is excluded from the hardware
confirmation. This match is not extrapolated to the multi-page pattern.

The Windows suite of GS tools, previous CLI, height control,
configuration and PowerShell syntax passes. A private mutant keeps the tag
(it accepts the option but does not invalidate); the causal control fails at the first height,
so it checks the intervention and not just the presence of the option.
