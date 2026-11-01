# Comparison with PCSX2: one frame's VIF1 chain

_October 6, 2026_

## Goal

Separate VIF1/VU1/GS failures from the data the EE prepares. The tool takes the VIF1 DMA chain
of a frame already built by the game and runs it on the runtime's VIF1, VU1 and GS,
without running the EE:

- with a **PCSX2** chain (savestate), a correct image indicates that VIF1/VU1/GS draw those packets
  correctly;
- with a chain **from the port** (dump from `GOW_RENDER_DIAG`), the replay should reproduce the game's
  image, provided the chain of the corresponding frame has been identified. A visual similarity with a
  header chosen between two frames does not certify that correspondence.

## Usage

```powershell
scripts\compilar_repetir_vif.cmd            # requires scripts\2_compilar.cmd
python tools\render\extraer_cadena_vif.py --pcsx2 "<sstates>\SCUS-97399 (XXXXXXXX).01.p2s" logs\vif_pcsx2
logs\repetir_cadena_vif.exe logs\vif_pcsx2 logs\vif_pcsx2\imagen
```

For a dump from the port: run the game with `GOW_RENDER_DIAG=1` and, optionally,
`GOW_RENDER_DIAG_DESDE=<seconds>` (dumps the first pad capture in state 11 from that
moment on; without the variable, the first one in state 11). The dumps are left next to the executable:

```powershell
python tools\render\extraer_cadena_vif.py --volcado E:\gowport\PS2Recomp\out\build\ps2xRuntime logs\vif_port
logs\repetir_cadena_vif.exe logs\vif_port logs\vif_port\imagen
```

The extractor examines both headers. If both end in END, it stops and lists the candidates
to choose with `--inicio 0x450C00` or `--inicio 0x450A00`. In a savestate it also rejects the
selection if several chains end at the same `D1_TADR`. `--inicio` allows replaying a known chain,
but does not prove it is the one of the current frame. The port's dump does not yet save
`D1_TADR`: if both are valid, the two must be compared and that limitation kept in the result.

`repetir_cadena_vif` writes `imagen_antes.ppm` and `imagen_despues.ppm` of the given framebuffer
(by default `FBP=0`, `FBW=8`, PSMCT32, 512×448, the one used by gameplay). Everything extracted contains
game data and stays in `logs/`.

### Format details

- The game alternates the `0x450C00` and `0x450A00` headers (a 15-QW DIRECT with the GS configuration
  and a NEXT to the list). In a savestate, the END that `D1_TADR` points to is required.
  What VIF1 receives with `CHCR.TTE` is replayed: the upper 64 bits of each tag followed
  by its payload, following CALL/RET.
- In the savestate's `GS.bin` (PCSX2 v2.x), the VRAM is the 4 MB preceding the last `0x54` bytes
  (four 20-byte `GIFPath` entries and `Q`).
- The VIF1 registers are taken from `eeHwRegs.bin` (`0x3C00`). VU1 starts with zeroed registers; the
  frame's chain uploads the microcode and the constants it uses.
- The GS internal CLUT palette and the full set of VU1 registers are not restored.
- The GIF channel chain (PATH3) is not replayed: the textures the game uploads during the frame are
  not updated. Differences in colors and textures may come from those uploads as well as from
  the unrestored internal state; they are not attributed exclusively to PATH3.

## Results

| Input | Result |
|---|---|
| PCSX2, Aegean (Kratos on the mast, savestate `6C2355D5`) | Correct geometry: ship, mast, rocks, water and Kratos in place. Colors differ (Kratos and the water); the effect of PATH3 was not separated from the unrestored internal state. |
| PCSX2, Desert of Lost Souls (`C1CFCB84`) | Recognizable scene, in place, with a more intense haze and fire particles with a different texture. |
| PCSX2, Hades (`CBE116C1`) | Kratos and the HUD correct; the walls are missing. Not investigated. |
| Port, gameplay at 190 s | The replay produced a similar image (dark plank background and a black silhouette). Ambiguous control: both headers end in END and the previous extractor picked the first without identifying the current frame. |

The VU1 microcode that the port uploads matches that of the savestates in the first `0x24D8`
bytes; the rest is an area that the game replaces during gameplay.

**Conclusion:** with the PCSX2 packets tested, the runtime's VIF1, VU1 and GS draw the
Aegean geometry correctly. This does not certify other inputs nor rule out GS differences in
colors or textures. The port control at 190 s remains inconclusive as a same-frame comparison
because of the ambiguous selection. The EE cause of the deformed camera was checked afterwards by following
the sine table and verifying its fix in the game, as described below.

## Vertex colors (ruled out)

In a more advanced Aegean savestate (`6C2355D5`), several meshes have vertex colors rewritten
in PCSX2 (`0x80606060`), while the port keeps those from the disc. With the savestate from the start of
the game (`D6385328`), PCSX2 also keeps the colors from the disc: it is a later recalculation by the
level, not a port failure. It is ruled out as the cause of the dark scene.

## Camera matrix: cause and fix (2026-10-06)

In the port's gameplay, the camera matrix that reaches VU1 had orthogonal axes of length
1.27, 1.52 and 1.93; in PCSX2 they measure 1. This stretched the whole scene, also in the intro without
`GOW_FAST_BOOT`. Following the writes (a temporary watch in `ps2TraceGuestWrite`, since
removed) led to joint 1 of the skeleton that animates the intro camera, computed by
`makeAnimMatricesRot` (`0x10B9C0`). That function takes sine and cosine from a table of 4096 floats that is
copied to the scratchpad (`0x70000000`) from `*(0x304638)` = `0x52C600`.

In the port the table contained the angle and not its sine (`0.1963 / 0.3927 / 0.7854 / 1.5704` versus
`0.1951 / 0.3827 / 0.7071 / 1.0` in PCSX2). It is filled by `0x118798` with
`dptofp(sin(fptodp(x)))`: the game's libm is **software double** (argument in `$a0`,
result in `$v0`), but `config/recomp.template.toml` replaced `sin@0x00287378` with the runtime's
float handler (`$f12 -> $f0`). `$v0` kept the argument, so `sin(x)` returned `x`.
`fabs` and `floor` had the same problem; only that libm uses them (`__ieee754_rem_pio2`,
`__kernel_rem_pio2`).

**Fix:** `sin`, `fabs` and `floor` stop being stubs and the original recompiled libm is run.
`tools/ci/validar_config.py` now rejects replacing functions of the double libm.

Check with the full build and `GOW_SKIP_FMV=1`, `GOW_FAST_BOOT=1`: the port's table
matches PCSX2 (`0 / 0.1951 / 0.3827 / 0.7071 / 1.0`), the camera matrix at 190 s measures
1 on all three axes and the captures at 160 and 190 s show the ship's deck, the cliffs, the
sky and the rain without stretched polygons. Kratos's and the enemies' animations use the same
table; their appearance in gameplay remains to be verified.

## Start of the game without `GOW_FAST_BOOT` (2026-10-07)

With the `sin` fix and the performance improvements, the intro finishes on its own: at ~480 s (OpenGL,
`GOW_SKIP_FMV=1`) the HUD appears. The camera matrix matches that of the PCSX2 savestate from the
start (`D6385328`): same position `(1530.2; 49.8; 1973.8)` and same axes. When replaying the VIF1
chain of that frame, the port's image reproduces the game's: Kratos appears as giant red polygons in front
of the camera, while PCSX2's chain draws him correctly. The failure is again in the EE data.

Among the 4×4 V4-32 matrices that each chain uploads, the port has many with uniform scale
0.1–0.2 at VU addresses `0x106`–`0x12E` that PCSX2 does not have (there they are 1.0, 0.3 or 0.5). Still
open: identify Kratos's skeleton and compare its bone palette with PCSX2's in the
same frame. The port's `makeAnimMatrices*` outputs have unit rotations; the 0.1/0.3/0.5 scale
appears in the root joint of the `NonUnitScale` variants.

### Cause: scratchpad DMA in chain mode (2026-10-07)

In the gameplay frame, Kratos's bone palette uploaded to VU1 (`UNPACK V4-32`, 36 QW at
VU `0x106`) arrived entirely zero in the port; in PCSX2's chain they are valid matrices.
`CalcSkinHierarchy` (`0x137508`) leaves the bones in the scratchpad (`0x70000010`) and the game
copies them into the packets with the fromSPR channel in **destination chain** mode (`CHCR=0x104`; it also uses toSPR
in source chain mode, `CHCR=0x105`). The runtime only implemented normal mode for channels 8 and 9
and copied nothing in chain mode.

`patches/ps2recomp-spr-chain.patch` implements both modes: fromSPR reads `{QWC, ID, IRQ, ADDR}`
tags from the scratchpad and writes each block to its RAM address (`cnts`, `cnt`,
`end`); toSPR walks tags in RAM (`refe/cnt/next/ref/refs/call/ret/end`, with TTE) and writes
the data consecutively into the scratchpad. Two regressions fail without the patch; the suite passes **547/547**.

With the full build, OpenGL and `GOW_SKIP_FMV=1` (without `GOW_FAST_BOOT`), the captures at 240,
360, 480 and 580 s show the intro, Kratos on the deck, the undead and gameplay with the
HUD, all with their correct shape.
