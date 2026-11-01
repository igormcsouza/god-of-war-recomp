# Comparison of RAM and shared presentation

Measurement of 9 October 2026, after merging PR #33 and #34.
Only the presentation is compared; both modes use the same OpenGL
renderer, the same 501 VU1 micromemories and the same executable.

## Conditions

- CPU: AMD Ryzen 7 5800XT, 8 cores and 16 threads.
- GPU: AMD Radeon RX 5700 XT; Windows driver `32.0.21045.5002`.
- Executable of the official build of `343404f`, with 75 patches:
  70,469,120 bytes, SHA-256
  `33C012EF1BB0DC01C325027480893CDB427F406745C686FC4D8296F1BFFFE5A5`.
- Script based on `main` `c8ce1d5`, with explicit presentation selection.
  PR #34 modifies how the folders are passed to the generator; this comparison
  keeps the earlier binary to isolate the presentation.
- Four 180-second runs: RAM, shared, shared, RAM.
  Private card absent at the start of each pass and the same private shader
  cache, already used in the earlier functional control.
- `GOW_FAST_BOOT=1`, `GOW_SKIP_FMV=1`, test controller with a fixed sequence,
  `GOW_PAD_TEST_NO_CAPTURE=1` and profile `-SoloCuadros`.
  No captures, dumps, GPU profiler or detailed GS statistics.
- Monitoring of compilers and other instances throughout the run.
  The logs must confirm the effective RAM or shared mode; requesting
  the shared mode is not enough if OpenGL falls back to RAM.

## Selection and limits

Complete windows between seconds 100 and 170 of the profile clock are selected,
enclosed by reports `state=11`, `pending=0`, `levelReady=1`.
The clock starts after the process starts; therefore a 180-second run
may have fewer valid windows up to 170. The summary
keeps the effective interval and weights `guest_flip_hz` by its duration.

`guest_flip_hz` counts entries into SCUS-97399's `vid::Flip`. The host
presentations are another counter and do not equal gameplay FPS. With
`-SoloCuadros`, the per-subsystem times are deliberately left at zero:
they are not useful to attribute the bottleneck.

The button sequence uses real time, not a deterministic replay of the game
state. The sampled states confirm a loaded game, but not identity
of all enemies, animations or frames between passes. Two repetitions
per mode also do not allow generalizing a percentage to the whole game. The
logs, cards, shaders and other files derived from the game remain
private.

## Result

| Order | Presentation | Windows | Effective interval (s) | Selected duration (s) | Game FPS |
|---|---|---:|---:|---:|---:|
| 1 | RAM | 12 | 100.09-160.19 | 60.12 | 6.756 |
| 2 | Shared | 13 | 100.02-165.08 | 65.04 | 6.918 |
| 3 | Shared | 13 | 100.01-165.11 | 65.08 | 6.898 |
| 4 | RAM | 13 | 100.07-165.14 | 65.06 | 6.932 |

The weighted averages are **6.848 FPS with RAM** and **6.908 FPS shared**:
an observed difference of **+0.88 %**. The two RAM passes differ from each other by
about 2.6 %; this sample does not demonstrate a stable FPS improvement.
The host presents about 59.9 times per second in both modes, keeping
frames when the game advances more slowly.

The four passes confirm their effective mode, keep the hash before and
after, generate no captures and contain no marks of external load nor
fatal errors. An Opus game starts after the fourth pass ends,
seven seconds later; it is neither stopped nor included in the measurement.
The closing of our instances when the time limit expires is forced and is not
a new test of the backend's normal shutdown.

Shared presentation retains value as a path without per-frame pixel
readback and as a basis for future improvements, but it does not by itself solve
the performance of this scene. The next render investigation is
aimed at [rasterization and the dominant texture group](shared-presentation.md).

## Repeating

Use `scripts/probar_rendimiento.ps1 -Renderer opengl -Presentacion ram` or
`-Presentacion compartida`, both with `-SoloCuadros -Segundos 180` and different
labels. Restore the same initial card state before each pass
and verify the executable's hash before and after. Then run:

```powershell
python tools/rendimiento/resumir.py logs/perf_ram_1.log --partida --desde 100 --hasta 170
python tools/rendimiento/resumir.py logs/perf_compartida_1.log --partida --desde 100 --hasta 170
```
