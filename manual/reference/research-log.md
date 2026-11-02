# Project status

_Last updated: October 9, 2026_

## What works

- The full build finishes without errors (~11 min to compile the game on a machine with 8+ cores).
- `scripts\2_recompilar_rapido.cmd` recompiles only `src/gow_overrides.cpp` in ~1 minute.
- `ps2EntryRunner.exe` starts, initializes raylib 5.5 / OpenGL 3.3 and opens the window (640×448).
- **The IOP runs the game's original IRX modules** in the R3000A interpreter of `ps2xIOP`: `sio2man`,
  `dbcman`, `sio2d`, `mc2_d`, `ds2u_d`, `libsd`, `989nomid` (989snd) and **`smpd_iop`** (the data
  loader). `scripts\ejecutar.ps1` copies them to `IOP_MOD\` next to the ELF the first time.
- The IOP reads the **original ISO** (`God of War.iso` next to the ELF folder, or the `GOW_ISO` variable).
- smpd initializes: it reads the ISO9660 directory and `GODOFWAR.TOC`, and creates its threads.
- **The configuration is loaded from disk**: the `SMPD 0xF "R_Perm"` request returns handle 0
  and `HERO_HEAP_SIZE` / `SLOT_HEAP_SIZE` / `UPGRADE_HEAP_SIZE` are found (the provisional guard for the
  NULL dictionary no longer triggers and has been removed).
- **`R_PERM.WAD` is streamed in full** (smpd reads 16 sectors per `sceCdRead` call and sends them
  to the EE in blocks of `0x20000` that alternate between `0x530640` and `0x550640`).
- 989snd starts without errors (before, 15 × `cause 7` because of a badly built `argv`).
- **The game enters its main loop (`sys::GameLoop`) and draws its first screens**: the legal screen
  *"Sony Computer Entertainment America presents"*, the *"Please insert a DUALSHOCK®2…"* one and the
  *God of War* logo of the title screen. Some texts are missing letters.
- The runtime debugger is shown/hidden with **F1**.
- The **libpad2** HLE connects the first port to the runtime backend: keyboard or gamepad, buttons,
  both sticks and digital pressures. Navigation reaches the **main menu and the difficulty selection**.
  The controls and the reproducible test are in [controls-and-menu-tests.md](controls-and-menu-tests.md).
- The dispatcher preserves checkpoints that yield at a function's entry. This eliminates the partial
  copy of `Animation/goHero` and the virtual call to NULL when advancing from the menu.
- `gowIpuInit` fixes the IPU initialization: the generic stub jumped to an address of another
  executable and ran `FilteredCopyTile` with wrong registers. Now the FMV load is reached.
- With `GOW_SKIP_FMV=1` the **in-game state 11** is reached, with `pending=0` and the main thread active.
  After integrating Claude's fixes, the 330-second OpenGL control run loads a copy of its card
  and shows Kratos, the scenery, the HUD and the R2 prompt in "Docks of Athens". Performance is still
  low; combat controls, other scenes and sustained performance are missing.

## Symbols

The name maps in `01-retail-usa-SCUS97399/` (Ghidra export, matched against the E3 demo
and the European demo) **match the addresses of our ELF**. Some confirmed:

| Address | Name |
|---|---|
| `0x0026BF28` | `snd_SendIOPCommandAndWait` |
| `0x0026C940` | `snd_DoExternCall` |
| `0x00186710` | `wadContext::FindData` |
| `0x00175890` | `stdDynaStringDB::GetDynaStringNode` |
| `0x0017A940` | `sys::Boot2` |
| `0x00239F90` | `stdCList<wadCleanupData, …>` |
| `0x00299D08` | `cbTimerHandler` (libkernel alarms) |
| `0x0016AFD8` | `memcpy_asm` |
| `0x0016B120` | `ringBuffer::GetBytes` |
| `0x00183878` | `vid::WaitForDMAComplete` |

`GOW-Port/sym.py <addresses>` (outside the repository) translates addresses using these maps.

## Boot investigation timeline

### 1. The hang at `0x00176A80` was not a wait

`sub_001769F8(root, key)` is a search in a **binary tree** of 16-byte nodes stored in a
pool (created by `sub_00175CD0`, 8000 nodes):

| Field | Meaning |
|---|---|
| `node+0x0` | key (hash) |
| `node+0x4` | value |
| `node+0xA` / `node+0xC` | left / right child (u16 index into the pool) |
| `*0x29C4BC` | pool base (`child = base + index*16`) |
| `*0x29C4B4` | sentinel node (end of branch) |
| `*0x29C4B8` | pool handle |

`GetDynaStringNode` (`0x175890`) received a **NULL** dictionary from `wadContext::FindData`
(`0x186710`), which was looking up `HERO_HEAP_SIZE`, `SLOT_HEAP_SIZE` and `UPGRADE_HEAP_SIZE`. The root was read at
address `0x4` and that garbage formed a cycle. The dictionary is `node+0x4C` of the context of the `R_Perm`
WAD, which had not been loaded.

### 2. The configuration lives in `R_PERM.WAD` and smpd loads it

`R_PERM.WAD` is the first file of `PART1.PAK` (sector 0, `0x378530` bytes). The variables are
records of type `0x18` of the group `WAD_R_Perm`:

| Variable | Value |
|---|---|
| `HERO_HEAP_SIZE` | `0x1EC800` |
| `SLOT_HEAP_SIZE` | `0x100000` |
| `UPGRADE_HEAP_SIZE` | `0x14BC00` |

`GODOFWAR.TOC` is a table of 24-byte entries with the format `name[12]`, `u32`, `u32 size`,
`u32 sector`.

The EE does not read the disk: **`SMPD_IOP.IRX`** ("smpd file streamer"), a 989snd plugin, does.

### 3. EE ↔ 989snd ↔ smpd protocol

`snd_SendIOPCommandAndWait(cmd, size, data)` does `sceSifCallRpc(sid 0x123456, rpc = cmd)`: it sends
`size` bytes from `0x305640` and receives 12 bytes at `0x305600`. It returns word 1 of the reply.

Command **`0x68`** is a message for a plugin: `{u32 plugin, u32 type, u32 len, u32 ptr}` plus `len`
bytes copied from `ptr`. For smpd, `plugin = 0x534D5044` (`'SMPD'`).

| # | cmd | Contents | Meaning | Reply |
|---|---|---|---|---|
| 1 | `0x0` | `{0x30A1C0, 0}` | 989snd initialization | 0 |
| 2 | `0x68` SMPD `1` | `{mode, state, 0x20, table, 0x280, …}` | initialize smpd (EE buffers, see below) | 0 |
| 3–17 | `0xA` | `{0}` … `{14}` | 15 989snd commands | `0x400` |
| 18 | `0x68` SMPD `0xF` | `"R_Perm"` + `0x10000210, 0, 1` | **load the `R_Perm` WAD** (flag `0x200` = synchronous) | handle `0` |
| 19… | `0x4C` | 0x1C bytes | `snd_DoExternCall` | `0x20000` |

smpd buffers in the EE (`sub_001389D8`, the initialization): `*0x29BE4C` = state (0x20 bytes) and
`*0x29BE50` = table (0x280 bytes). They are accessed uncached (`| 0x20000000`) because smpd writes them
by DMA (`sceSifSetDma`). The table has a 0x100-byte header and 8 slots of 0x30 bytes. In the synchronous
load, `sub_0017AD70` reads `table + 0x12C + handle*0x30` (field `+0x2C` of the slot) and
`sub_00185F28` stores it in `node+0x4C`.

### 4. Running the original IRX modules instead of reimplementing them

`ps2xIOP` is designed to run the game's IRX modules ("Game-specific IOP code executes from IRX
modules"). They were not loaded only because the game requests them as `IOP_MOD/xxx.irx`. Once available,
four emulator bugs appeared, all fixed in `patches/ps2recomp-runtime.patch`:

| Bug | Symptom | Fix |
|---|---|---|
| IOP heap of only 832 KB (`HeapBase = 0x120000`) | smpd: "failed to allocate memory" (it requests `0x11ADF8` bytes) | `HeapBase = 0x70000` (the modules end around `0x56000`) |
| Cap of 2 M instructions per synchronous call (`kMaxCallInstructions`) | smpd's initialization, run inside the 989snd RPC, was cut off **silently** halfway through the TOC and the EE waited forever | cap of 400 M and a `[IOP] guest call … exceeded its budget` warning |
| `sprintf`/`vsprintf` of sysclib copied the literal format | smpd did `sprintf("%s.wad", name)` and looked for `%S.WAD` → `R_Perm` returned -1 | real formatter with o32 arguments (`iop_format.h`), also used by `printf` |
| No disk image | smpd reads by sector number | `configureGowCdImage` in `src/gow_overrides.cpp` uses the original ISO |

### 5. Virtual methods without an entry point

`sub_0023A000` makes a virtual call to `0x239FD0`, an empty method (`jr ra`) reached only
through a vtable. Neither our function map nor Ghidra had it as a function: it sat inside
`sub_00239F90` and the runtime considered it nonexistent (`[guest-branch:missing-target]`). Walking
the ELF's vtables (entries `{s16 adjustment, s16 index, u32 function}`) turned up **24 such targets**. They are now
in `entry_points` of `config/recomp.template.toml` (`vfunc_XXXXXXXX`), and the recompiler creates
an entry point for them inside the function that contains them.

### 6. The main thread died: a 205 MB copy

With the above, the game advanced until **the main thread died** (`Dormant`, `pc=0`) because of a
call to a NULL callback in `cbTimerHandler`. libkernel's alarm list (`0x2A5B08`–`0x2A5B14`)
was full of `R_PERM.WAD` data. The culprit was
`memcpy_asm(dst=0x6C190, src=0x530640, n=0xC478000)`, called from `ringBuffer::GetBytes` by the
WAD loader: the streaming buffer was **zeroed**, so the loader read a garbage size.

The data did arrive through `sceSifSetDma`, but **in the buffer of the next request**. On the real IOP,
the 989snd RPC server wakes smpd's reader thread (higher priority), which runs and points
the destination before the RPC thread replies. The emulator ran the RPC server as a
synchronous call and replied immediately, so the reader thread took the destination of the next request.
**Fix:** after each RPC, the emulator lets the ready IOP threads run
(`runReadyThreads`, cap of 4 M cycles) before copying the reply.

### 7. The video wait: the GS interrupt

`vid::WaitForDMAComplete` (`0x183878`) waits while `*0x29C7D0 == 1`. The flag is set to 1 by whoever launches
the DMA chain (`svrEpilogue::FlipAndKick`, `fxCameraFilter`…) and is only changed by the **GS
interrupt handler** (`0x182DD8`, code that Ghidra did not mark as a function): it reads `GS_CSR`, and if `FINISH`
is set it sets the flag to 2 and clears the bit. The runtime set `CSR.FINISH` but **never raised
INTC interrupt 0**. Fix: `EeScheduler::pollGsInterrupt()` raises it on the rising edge of
`CSR.SIGNAL/FINISH` not masked in `IMR`.

### 8. Interrupts trampled the main thread's stack

With the GS interrupt active, the main thread died by jumping to `0xF82`. The stacks of the interrupt
handlers are allocated from the top of RAM (`0x1FFFFF0`) downward, **right where
`SetupThread` places the main thread's stack**: each interrupt clobbered its oldest frames.
Fix: `SetupThread` lowers the ceiling of that area below the main stack
(`PS2Runtime::limitAsyncCallbackStackTop`; they now start at `0x1FE8000`).

### 9. Other IOP emulator fixes

- The modules started with `start(size, text)` instead of `start(argc, argv)`; now `argv` is
  `[path, arg1, …, NULL]`, as in `loadcore`.

In addition, the `snd_SendIOPCommandAndWait` override no longer discards commands: it logs them (`[gow-snd]`)
and calls the original. `GOW_SND_STUB=1` restores the old behavior.

## Diagnostic tools

| Tool | Use |
|---|---|
| `[gow-snd]` | commands sent to 989snd/smpd and their reply |
| `PS2X_IOP_TRACE=N` (+ `PS2X_IOP_TRACE_FROM=M`) | logs N IOP import calls starting from the M-th |
| `PS2X_IOP_TRACE_NOCLIB=1` | omits `sysclib` from that trace |
| `PS2X_IOP_TRACE_EVERY=N` | sampling: one out of every N calls |
| `PS2X_IOP_PC_EVERY=N` | IOP PC every N instructions and a warning when there are no ready threads |
| `PS2X_IOP_TRACE_DMA=1` | every `sceSifSetDma` IOP → EE transfer (source, destination, size, first bytes) |
| `[run:thread]` | state of all EE threads every ~10 s (in `ejecutar.log`) |

The provisional diagnostics of sections 1, 5 and 6 (`[gow-tree]`, `[gow-dict]`, `[gow-23a000]`,
`[gow-timer]`, `[gow-watch]`) were removed from `src/gow_overrides.cpp` once those problems were solved;
they remain in the git history in case they need to be recovered.

## Known issues

| Issue | Detail |
|---|---|
| Text with missing letters | some fonts/textures are drawn incompletely (controller screen, menu) |
| In-game image | state 11 is reached with FMVs skipped, but the framebuffer stays black |
| Controller | libpad2 works through HLE for the first port; pressures 0/255 and no vibration. In the emulated SIO2 the controller ports appear empty |
| Memory card unverified | SIO2 and the card are emulated (`ps2recomp-sio2.patch`, file `Mcd001.ps2`), but it has not been tested with the game |
| Audio unverified | the emulated SPU2 now outputs through the PC audio (`ps2recomp-spu2-output.patch`), but it has not been tested with the game; no reverb or ADMA |
| No FMV video | `sceMpeg*` / `sceIpu*` are stubs |
| Ninja dependencies | With MSVC in Spanish the `/showIncludes` dependencies are not registered: `2_recompilar_rapido.cmd` touches the overrides unity file and `compilar.ps1` deletes the unity objects after regenerating (changes to runtime headers require touching the `.cpp` files that include them) |
| Paths with accents | `ps2_recomp` does not open non-ASCII paths: `compilar.ps1` copies the ELF and the map to the working folder |

## Next steps

1. Investigate VIF/VU→GIF: in state 11 the GS contexts still have `FBP=0`, with no primitives
   in the recent trace, while `FBP=208` is presented. XGKICK rejects packets for exceeding
   its buffer or because of the header format. The warnings `0xFFFFFFFB` and `0xFFFFFFF8` are internal
   runtime codes, not invalid microcode instructions. `GOW_RENDER_DIAG=1`
   allows saving the microcode and RAM in order to compare them.
   The full recompilation reproduces the problem. A temporary XGKICK trace confirmed
   correct packets at the start and then vertex data interpreted as headers
   (`source=0x2AB0`, second header at `offset=0x10`). Review buffer preparation/rotation
   and UNPACK before enlarging the runtime buffer.
   The immediate transfer used by SOCOM Unzipped was tested separately:
   `GOW_XGKICK_IMMEDIATE=1` reaches state 11, but does not fix the black image and the XGKICK
   errors continue. The patch stays optional; the by-cycles transfer remains the default.
   See the comparison in [controls-and-menu-tests.md](controls-and-menu-tests.md).
   The I-bit check logged **196608 commands and zero VIF1 interrupt requests**
   up to state 11 (FMVs skipped, fast entry). The pause/resume mechanism of
   [SOCOM Unzipped](https://github.com/Scotho/socom-unzipped/blob/main/third_party/ps2recomp/ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp#L15-L20)
   does not explain the failure observed in that test. It has not been enabled.
   `-DiagnosticoVif` compares the headers before MSCAL and during XGKICK, distinguishes empty
   packets from real rejections and saves the drawing buffers when the game is reached.
   The FBP=0 contexts have data, but their captures do not show a 3D scene; FBP=208 is still
   black. The write trace found transformation loops that walked the buffers and
   overwrote their headers. `ps2recomp-vu-jump.patch` fixes the reading of JR/JALR: they used
   the previous value of VI, although that delay applies to the comparisons of conditional branches.
   With the fix, the 140 s test reached state 11 and logged 212992 VIF commands without
   XGKICK rejections or reserved VU instructions. The in-game screen is still black and the
   drawing contexts do not show a 3D scene. The next check is the coordinate transformation
   and the interpretation of the GIF registers/packets now that their headers are preserved.
   See [controls-and-menu-tests.md](controls-and-menu-tests.md).
2. Resolve the MPEG wait (`sceMpegGetPicture`, `0x0018A3D8`) and fix the rendering of
   fonts/3D. `GOW_SKIP_FMV=1` makes it possible to investigate the game while the decoder is pending.
   Hypothesis under way (`ps2recomp-mpeg-nodata.patch`): the `sceMpegGetPicture` stub waited for
   frames without ever calling the `sceMpegCbNodata` callback that the game registers with
   `sceMpegAddCallback`. In the original libmpeg that callback is what reads from the ring and calls
   `sceMpegDemuxPssRing`, so nobody fed the decoder (deadlock). The patch calls it
   on the thread that requests the picture; if it provides no data, it retries on the next VSync. Two regression
   tests cover it (without the patch the suite hangs on the first one). **It remains to be checked with the
   game:** run without `GOW_SKIP_FMV` and look in `ejecutar_err.log` for the lines
   `[MPEG:AddCallback] ... type=1` (the game registers the callback) and whether the wait disappears.
3. Memory card (SIO2 / `MC2_D.IRX`). **`ps2recomp-sio2.patch`:** before, the SIO2 registers
   (0x1F808200-0x1F8082FF) were simple latches, `dmacman` did nothing and there was no interrupt 17, so
   `sio2man` waited forever on every transfer. Now the IOP emulates the SIO2: command queue (SEND3),
   input and output FIFO, DMA 11/12 (`dmacman`'s `sceSetSliceDMA`/`sceStartDMA` for those two channels),
   `RECV1-3`, `ISTAT` and IRQ 17 when `CTRL` bit 0 is set. Controller and multitap commands answer as an
   empty port (libpad2 still goes through HLE in the EE). The memory card implements PCSX2's PS2 protocol (probing,
   pages of 512 + 16 bytes, erasing blocks of 16 pages, read/write, terminator, specifications
   and the authentication steps without encryption); secrman's `SecrAuthCard` returns success. Pages are stored
   raw in `Mcd001.ps2` next to the ELF, the same 8 MB format that PCSX2 uses (saves can be
   exchanged). If the file does not exist, the card starts unformatted and is created on the first write.
   Variables: `GOW_MC0=<path>` (another card; `GOW_MC0=0` leaves the port empty), `GOW_MC1=<path>` (second
   port, empty by default), `GOW_SIO2_DIAG=1` (logs every card command as `[SIO2] mc0 cmd=0x..`)
   and `GOW_SIO2=0` (restores the previous behavior). The protocol was tested against ps2sdk's `mcman`; God of
   War uses Sony's `MC2_D.IRX`, which could not be reviewed. **It remains to be checked with the game:** whether on saving or
   on startup the unformatted-card warning appears, whether formatting and saving finish, and whether
   `Mcd001.ps2` can be opened in PCSX2.
4. Audio over 989snd / SPU2. **Phase 1 (`ps2recomp-spu2.patch`):** the IOP emulates the SPU2: 2 MB of
   sound RAM, 16-bit registers of the two cores, manual data port, DMA of channels 4 and 7 which now
   copies the data (before it only marked the transfer as done; the `STATX` bit 0x80 and the deferred interrupt
   do not change), ADPCM voices with pitch, ADSR, fixed volume and dry mix, `ENDX`/`ENVX`/`NAX` readable
   and IRQ 9 on reaching `IRQA`. `GOW_SPU2_IRQ=0` disables that IRQ in case the game changes behavior.
   **Phase 2 (`ps2recomp-spu2-output.patch`):** the SPU2's 48 kHz mix goes out through a raylib `AudioStream`
   (stereo, 16-bit). The IOP produces the samples on the EE thread and the audio thread consumes them with a mutex;
   if more than 100 ms accumulate, the oldest are dropped, and if there are too few it fills with silence (if the
   emulation runs slower than real time, dropouts will be heard). `runCycles` advances the SPU2 up to the last cycle
   executed even if the IOP is waiting. The log shows `[SPU2] salida de audio a 48 kHz activa`. Not verified with the game: it must be checked whether
   the menu music is heard and whether it plays at the right speed.
   Missing: reverb, volume sweep, ADMA (streaming PCM) and Gaussian interpolation.

## VU1 interpreter audit

The upper and lower units of VU1 (`ps2_vu1_upper.cpp`, `ps2_vu1_lower.cpp`) were reviewed instruction by instruction
against the specification and against PCSX2 (`VUops.cpp`):
FMAC with broadcast, accumulator and `OPMULA`/`OPMSUB`, `CLIP`, `FTOI`/`ITOF`, `DIV`/`SQRT`/`RSQRT` (with the
latency of `Q`), flags (`FSAND`, `FMAND`, `FCAND`…), branches and links, loads and stores with
auto-increment, `MTIR`/`MFIR`, the `R` generator and the EFU. The only discrepancy was a typo in a
coefficient of the `EATAN` series (`-0.1308…` instead of `-0.1390…`), fixed in
`ps2recomp-vu-efu.patch` with its test. The semantics of those instructions do not explain the black image
of the game. Out of scope for this review remain the per-instruction latencies and the pipeline hazards.

## Validation of the progress to the menu

- `scripts\probar_pad2.cmd`: passes the test of button bytes, sticks and the twelve pressures.
- Build of `ps2EntryRunner` and `ps2x_tests`: successful.
- Runtime suite from its root directory: **435/437**. Two previous tests fail:
  `setup heap and allocator primitives track end-of-heap` and
  `IOP heap DMA uses private backing instead of aliasing EE RDRAM`.
- When removing only the dispatcher fix, the new checkpoint test fails and the total
  drops to **434/437**; the same two heap/DMA failures remain.
- `ps2recomp-checkpoint.patch` was checked on the pinned revision plus the project's original patch.
- The 200-second test with the fixed IPU reached choosing a difficulty and then waited in MPEG.
  The captures and logs are evidence of the menu, **not of a playable game**.
- The 600-second test skipping FMV reached state 11 without skipping the entry animation,
  with `pending=0`; the in-game captures are black. `GOW_FAST_BOOT=1` repeats the transition
  in approximately 70 s from the first controller read.
- With the experimental XGKICK patch, the full suite gives **436/438**: the new buffer-overwrite
  test passes and the same two previous heap/DMA failures remain.
- `ps2recomp-xgkick.patch` applies correctly on the pinned runtime revision.
- `ps2recomp-vif-unpack.patch` fixes the XYXY expansion of V2 and the color/alpha bits V4-5.
  Its three regressions fail before the fix (**436/441**) and pass after (**439/441**),
  keeping the two previous failures. The patch applies on the pinned revision.
  The game test reaches state 11; the menu defects and the black image remain.

- `ps2recomp-vu-jump.patch` preserves the current value of VI for JR/JALR, including the case where
  JALR reuses the destination register for its link. It keeps the delay slot and the existing
  rules for conditional branches. An incorrect expectation of the JR test was replaced and JALR
  coverage was added: both regressions fail before (**438/442**) and pass after (**440/442**),
  with the same two known failures. The patch applies on the pinned revision plus the previous ones.
  The executable was built and the 140 s test confirmed progress to state 11 without GIF rejections
  or reserved VU instructions; the captures still do not demonstrate a playable game.

- When integrating the changes published in parallel to `ps2recomp-heap.patch`, the suite passes
  **443/443**. The private heap keeps God of War's range and the DMA test uses the real
  IOP heap limit. The earlier 440/442 results correspond to the tree before that integration.
- The repeated full recompilation was fixed: `checkout -f` did not remove `iop_format.h`, created
  by the runtime patch, and `git apply` failed with `already exists in working directory`.
  `compilar.ps1` now removes that file together with `gow_stub_services.cpp` before reapplying the patches.

- The full build (`scripts\2_compilar.cmd`) regenerated the 6418 game units,
  reapplied the seven patches and linked `ps2EntryRunner.exe` correctly. It was verified separately
  that the seven patches apply, in that order, on the pinned revision and produce the sources used
  by the build. After rebuilding, the suite still passes **443/443**; the configuration has
  zero errors (four known warnings), the eight PowerShell scripts are analyzed without errors and the
  standalone libpad2 test passes.

- With the full executable and the integrated heap, the second 140 s test again reached
  state 11 in 70.32 s from the controller read. It logged 217088 VIF1 commands without XGKICK
  rejections or reserved VU instructions. The captures at 90 and 110 s are black; the drawing
  contexts keep the dark background. The game is still not playable.

## 3D rendering investigation: COP1 roots (October 5, 2026)

The local VU1 diagnostic at state 11 found a transformation matrix that already arrived
with `NaN` in its XYZ components. After being transformed, the geometry packets contained
null XYZ coordinates and the ADC discard bit set. The GS registers showed the copies
between buffers, but did not demonstrate that the game's triangles were drawn correctly.

Following the camera calculations, two errors in the COP1 recompiler were identified:

- The R5900's `SQRT.S` takes its radicand from **FT**, but a read of FS was emitted. With FS=0,
  the camera functions computed roots of register F0 instead of their sums of squares.
- `RSQRT.S` computes **FS / sqrt(FT)**; **1 / sqrt(FS)** was emitted, losing both operands.

`ps2recomp-fpu-roots.patch` fixes the operand selection and adds two regressions that decode
the binary instructions and check the emitted code, including destinations that coincide with
the sources. Both fail before the fix (**443/445**) and pass after (**445/445**, before
integrating the new EFU/MPEG tests). Reference for comparison:
[PCSX2's COP1 implementation](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/FPU.cpp#L316-L344).
This patch does not yet implement the particularities of flags and saturation of the R5900 FPU.

A separate test initializing `VF0.w=1` in new EE threads did not eliminate the matrix `NaN`s.
That experimental change was removed. The memory dumps, microcode and captures used for
this diagnostic remain local in the ignored folders; they are not part of the patch.

The full rebuild with the ten patches regenerated the 6418 units and linked the executable
correctly. The integrated suite, including the EFU/MPEG tests published in parallel, passes
**448/448**. The ten patches apply in order on the pinned revision; configuration and handlers
without errors (four known warnings), eight PowerShell scripts without syntax errors and the
standalone libpad2 test correct.

Two runs of 140 and 165 seconds with `GOW_SKIP_FMV=1` and `GOW_FAST_BOOT=1` reached state 11.
The matrix that used to contain `NaN` now contains finite values and non-zero vertex
coordinates appear. The GS logs thousands of triangle primitives during the game. The capture
presented at 90 seconds shows a dark background, with no recognizable scene or Kratos: this
**does not demonstrate a playable game**. The geometry buffers inspected still contain
vertices with ADC set; the next step is to correlate VU1 projection/clipping with the packets
that the GS actually receives. The temporary traces added to inspect the matrices were removed
and the executable was relinked; the published patch only changes the COP1 operands and their tests.

Before publishing, `ps2recomp-spu2.patch`, published by Opus during these
tests, was integrated by merge. Both patches were kept in `compilar.ps1`; the IOP, the executable and the
affected tests were rebuilt. The suite passes **456/456** and the eleven patches apply in an isolated copy of the pinned
revision. The new run with SPU2 again reaches state 11. The vertex trace of texture
13264 confirms that finite coordinates reach the GS, but it includes vertices with `draw=0`; they will have to be
correlated with clipping and with the primitives that are drawn, without assuming that every discard is
an error (they may be out of view).

### Tracking positions before projection (2026-10-05)

Claude's publications up to `a401182` (SPU2 output and SIO2) were integrated before editing the
project. The following diagnostics were run with the binary prior to those two integrations,
with the COP1 fix and SPU2 phase 1, to keep a comparable reference.

Three runs of 135/140 seconds, with `GOW_SKIP_FMV=1` and `GOW_FAST_BOOT=1`, reached state 11.
CLIP/FCGET and the entry of the VU1 transformations were temporarily instrumented:

- CLIP receives finite coordinates; in the sample examined, the points exceed the limits of the
  planes. FCGET observes the updates with the expected latency. This does not prove that all
  clipping is correct, but it does not justify clearing ADC or forcing the drawing of discarded vertices.
- The test of initializing `VF0.w=1` in new EE threads was repeated with the COP1 roots already fixed.
  It did not change the visual result; it was removed again.
- A complete VIF1 stream captured during state 11 contains 141 launches and uses UNPACK S,
  V2 and V4 in modes 0 and 1. It contains neither V3 nor STMOD mode 3. The differences detected in those two
  runtime paths do not explain this stream and were not modified as a supposed fix for the game.
- In a batch of the routine located at `0x3230`, the XYZ positions loaded for `ITOF4` are already
  zero. The camera matrix is finite and the subsequent transformation repeats its translation term.
  A dump from before the entry of that routine was kept to distinguish the input data from
  the packets overwritten during its execution. The write that produces those
  zeros remains to be identified; they are not yet attributed to a specific fault of the interpreter or of the game.

The GoW2 Europe Demo Ghidra export provided as a reference serves to identify the
camera, viewport and clipping functions; its types and pseudocode are contrasted with the GoW1
instructions. The export, the generated code, the VIF streams and the memory dumps are not published.
The temporary traces were removed from the runtime. The scene is still not recognizable: a playable
game is not demonstrated. The next step is to trace the producer of the positions buffer of that batch,
including the writes prior to projection, before changing its consumer.

Afterwards SPU2 output and SIO2 were applied to the local runtime, the affected sources were rebuilt and
the executable and the tests were linked. The integrated suite passes **465/465**. The **13 patches**
apply in order on the pinned revision; the **41 `.cpp`/`.h` sources** compared match the local
runtime (the function registry specific to the game build is excluded).
The integrated 150-second run again reaches state 11; the presented capture
keeps the dark background and does not show a recognizable 3D scene. The configuration passes without errors,
with the four warnings already documented. Claude's merge `a401182` has its GitHub checks
completed successfully.

<a id="performance-measurement-2026-10-05"></a>

## Performance measurement (2026-10-05)

The Release build kept the general traces, the entry/exit of each
function and the IOP RPC traces enabled. The function log flushes the file on every message; a
150-second run left about 204 MB. `compilar.ps1` now sets the three options to
`OFF` by default. `scripts\2_compilar.cmd -Trazas` allows enabling them for investigation.

`ps2recomp-perf.patch` adds an optional profile, independent of those traces:

- `GOW_PERF_DIAG=1`: emits a `[gow-perf]` line every five seconds with exclusive elapsed times of EE, VU, GIF/GS processing, IOP calls and scheduler wait. GS
  calls nested in VU are subtracted from VU; they are not counted twice.
- The image upload and `EndDrawing` times belong to the presentation thread and are reported
  separately. `EndDrawing` includes the refresh limiter and host waits.
- `GOW_PERF_FRAME_PC=0x001837B8` counts entries to `vid::Flip` of this ELF, both from the scheduler
  and from direct calls. Its resumptions do not count. `guest_flip_hz` measures those entries;
  `host_hz` measures the window refreshes. Neither by itself demonstrates correct 3D frames.
- `GOW_PERF_DIAG=frames` keeps both counters without per-subsystem timers, to check
  the cost of the profile; the time fields stay at zero because they are not measured. Without `GOW_PERF_DIAG`,
  it neither reads clocks nor accumulates these counters.
- The times include mutex and operating system waits; **they are not CPU usage
  percentages**. The work of a scope that is still open is accounted for when the scope changes, so
  it is advisable to compare several complete windows, not a single line.

Reproducible test, without VIF/RAM/VRAM dumps or periodic captures:

```powershell
powershell -File scripts\probar_rendimiento.ps1 -Segundos 150 -Etiqueta limpio
python tools\rendimiento\resumir.py logs\perf_limpio.log --desde 100 --hasta 145
powershell -File scripts\probar_rendimiento.ps1 -Segundos 150 -SoloCuadros -Etiqueta cuadros
python tools\rendimiento\resumir.py logs\perf_cuadros.log --desde 100 --hasta 145
```

The script preserves the `GOW_PAD_TEST` key presses, disables captures with
`GOW_PAD_TEST_NO_CAPTURE=1` and restores the environment when it finishes. It uses `GOW_SKIP_FMV=1` and `GOW_FAST_BOOT=1`;
these measurements do not evaluate FMV playback or a full game. The logs stay local
in `logs/`. A `[gow-pad2:state]` line reports the state roughly every five seconds
without writing images. The summary separates the game thread from the presentation thread.

Three 150 s runs were compared, summarizing eight complete windows between seconds
100 and 145 of the profile clock (about 40 s per sample). State 11 was verified in that stretch:

| Build / measurement | `vid::Flip` entries per second | Window refreshes per second |
|---|---:|---:|
| Traces enabled, full profile | 2.19 | 57.25 |
| Traces disabled, full profile | 2.37 | 56.60 |
| Traces disabled, counters only | 2.40 | 56.45 |

The observed difference with respect to the reference is about 8 %. The reference
kept the controller's periodic captures; the two new measurements disable them. They are
individual samples and do not isolate all the variation between runs, so they do not demonstrate a
guaranteed FPS improvement. The difference between the full profile and counters only is around 1 % in this
sample: the cost of the timers does not seem to explain the low performance observed.

With traces disabled, the exclusive time accounted for on the game thread is split as
**IOP 61.26 %, GIF/GS 27.94 %, VU 8.72 % and EE 2.08 %**. The scheduler wait is zero in those
windows. It is a split of elapsed time of the instrumented paths, not CPU usage nor
an internal CPU/SPU2 separation inside the IOP. The next IOP profile must distinguish
interpreter, services and SPU2 mixing; optimizing VU alone would have a small margin in this scene.

The full rebuild regenerated the 6418 game units. The 14 patches apply in order
in an isolated copy and their 42 `.cpp`/`.h` sources compared match the compiled runtime.
The integrated suite passes **467/467**, including two checks of exclusive accounting and
profile nesting. Configuration and handlers without errors (four known warnings), PowerShell
scripts without errors and standalone libpad2 test correct.

The final visual check, separate from the measurements and using the same FMV skip/fast
boot, again reaches state 11. The capture presented at 110 s from the controller read
shows the dark background with waves, with no recognizable 3D scene or Kratos. The profile and the removal
of traces improve observation and reduce costs, but **they do not yet demonstrate a playable game**.

### Positions present in the previous VIF stream

The complete VIF stream captured earlier at state 11 was reviewed offline. A `V4_32` UNPACK,
with 120 vectors and `STCYCL=0x0102`, already contains in its payload the 120 values
`(0,0,0,32768)`, before VIF/VU1 interpret them. The same command followed by the payload appears
in several buffers of the EE dump. Other `V4_16` batches of 81 vertices contain non-zero XYZ
positions. This narrows the zeros of that batch down to the EE/DMA input data; it does not yet demonstrate
which producer fails nor that an empty template is incorrect at that moment.

The symbols and the reference export help to follow `renEEPrim::InitUNPACKData`, `InitChunk` and
`GetUpdateAddress`. The first prepares instructions and offsets, reserving space for the data;
the routine that subsequently fills in the positions must be identified and checked. The clipping is not changed
and geometry is not replaced with invented data. The exports, streams and dumps remain
local and are not published.

### Shadow of the Colossus port reference

The user provided [sotc-vibe-pc](https://github.com/LightVelox/sotc-vibe-pc). Its
architecture, performance results and the exact runtime pinned by its submodule were reviewed:
[`LightVelox/PS2Recomp`, `ac9efa070638ad3b3accd284de6f898d5ab271d1`](https://github.com/LightVelox/PS2Recomp/tree/ac9efa070638ad3b3accd284de6f898d5ab271d1).
The reference copy stays in an ignored local folder; the GoW runtime keeps its pinned
revision and this project's integrated patches.

Concrete findings for the next stage:

- The `GSRasterBackend` interface matches ours. The fork contributes `GSGpuBackend`, a
  `GSThreadedBackend` wrapper, OpenGL rasterization and reference/replay tests. This makes it possible to study
  an incorporation by modules while keeping the CPU renderer to compare results. The common
  interface is not enough to guarantee compatibility of memory, synchronization, transfers or presentation.
- It contributes recompiled VU1 with fallback to the interpreter and verification tools. In our sample
  VU accounts for less than 9 % of the instrumented time, so it is not the first FPS optimization.
- The IOP and the audio clock also have changes. The interpreter,
  scheduler and SPU2 must be compared separately with Claude's changes before porting any fix in that area.
- Its [published results](https://github.com/LightVelox/sotc-vibe-pc/blob/main/Docs/PERFORMANCE_RESULTS.md)
  separate emulated fields, game updates, distinct images and host swaps. They record
  concrete presentation improvements, but do not demonstrate 60 real updates per second in the
  sanctuary samples. It is used as an implementation and validation reference, without transferring that
  performance figure to GoW.

Priority: contrast the rendering data and output with a correct reference; then
adapt the GS backend and generic improvements in independent patches, with tests and visual comparison.

### Adapting SotC's GS backend (2026-10-05)

`patches/ps2recomp-gs-opengl.patch` is incorporated as an independent patch after the profile.
It adapts `GSGpuBackend`, `GSThreadedBackend`, shaders, the WGL context and the VRAM addressing
tables from commit `ac9efa070638ad3b3accd284de6f898d5ab271d1` by Taylor N. Albarnaz / LightVelox,
under GPL-3.0. The imported files carry the `GOW-Port` comment and their provenance.
Selection, credits, tests and limits: [`rendering.md`](rendering.md).

The original CPU renderer is kept as the default and as the reference. The GPU runs
on the GS thread; it falls back to CPU if the context or shaders fail to initialize. Reads and FINISH
wait for the previous commands, Flush publishes and completes its block, and shutdown drains commands
before destroying the context on its thread. The fork's compact presentation is adapted to the
640-pixel stride of our frontend. The VRAM tables are initialized only once.
The shared GL presentation is left for a later stage.

The native suite passes **474/474**: five new normal tests and two optional tests with a
real GPU. On an AMD Radeon RX 5700 XT, OpenGL 4.6 is verified with forced compute and with
active graphics rasterization. Split/aligned transfers, clear, sprites,
full VRAM and presentation are compared; the interior/exterior of a flat triangle
and a CT32 texture are also checked. Without the three queue fixes, their regressions fail: **469/472**.
The 45 separate GS cache/CLUT/memory tests pass with the new integration.

The full rebuild generates the 6418 game units. The 15 patches apply in an
isolated tree and their 61 `.cpp`/`.h` sources compared match the local runtime.
Configuration and handlers: zero errors, four known warnings; PowerShell and libpad2 correct.

`GOW_EE_PRIM_DIAG=1` is added to observe `renEEPrim::InitUNPACKData` and `GetUpdateAddress`
without modifying data or their execution. It logs the callers and the returned buffers; the automatic
controller can re-read up to 16 addresses every 5 s. Those addresses can be reused,
so a late read needs to check its ownership before attributing the content
to a producer. The existing VRAM diagnostic now uses the public snapshot to also read
the updated memory of the GPU backend.

The scope respects the split: neither the recompiler, FPU, IOP, VIF nor VU1 is changed. The patch
`ps2recomp-fpu-roots.patch` stays intact. An additional remote branch from Claude
with EE/DMA/VIF/VU0 fixes was detected and is kept separate; it is not incorporated into `main` for this task.
Repeating the positions test when Opus integrates its EE/FPU changes comes before deciding
whether recompiling VU1 brings a useful improvement.

Local comparison without captures, with the same binary/ELF/ISO and three complete 5 s windows
in state 11, within `120–136 s`: direct CPU **2.40 `vid::Flip`/s**, threaded CPU
**2.39**, threaded OpenGL **3.26**. Host presentations: **56.33 / 55.68 / 59.12 Hz**.
The OpenGL improvement is approximately **36 %** in this short sample; variability is not measured
and distinct frames are not certified. The real GPU initializes without fallback. The captures are
taken in separate 155 s runs: both modes show dark water without Kratos or the
full scene. The late CPU ones change; the OpenGL ones from `56–130 s` are identical.
It remains pending to contrast the CPU's framebuffer selection/presentation (`preferredSource`)
with the GPU's CRTC, in addition to the geometry. The CPU keeps its role as the default reference.

The new trace logs **64 initializations, 298 returns and 192 subsequent reads**.
The caller `0x12E258`, in `LoadClient` (`0x12DE70`), obtains 40 buffers; the 14 addresses
of that caller kept by the probe afterwards show `(0,0,0,0x8000)`. It is verified in
the original MIPS that the loop `0x12E270–0x12E288` **deliberately writes that template**.
The initial reservation includes the chunks related to the earlier zero-XYZ V4-32 UNPACK.
This corrects the hypothesis that those zeros, by themselves, prove a broken EE producer:
they are an explicit initialization; their transformation and use in VU1/GIF remain to be followed.
The caller `0x1FB800` (function `0x1FB4B8`) returns two buffers with non-zero, changing XYZ,
also in the subsequent reads. No returns are observed from the two `goWater`
producers studied in this sample. ADC is not altered and no artificial positions are filled in.

### EE fixes taken from the SotC fork (2026-10-06)

With the user's authorization, the EE fixes from the SotC fork (TaylorNAlbarnaz/PS2Recomp, branch
`sotc-port`) are incorporated in `ps2recomp-ee-fixes.patch` (applied after
`ps2recomp-gs-opengl.patch`), marked with `// GOW-Port:` and the origin commit:

- **FPU (COP1) with PS2 semantics** (8b51cb9, 9bb389e, c419f26): the EE FPU has no NaN or
  infinities. ADD/SUB/MUL saturate to ±`FLT_MAX`; ADD/SUB align the operands without guard bits (as
  PCSX2); `DIV.S` by zero gives ±`FLT_MAX` and sets D or I in FCR31; `SQRT.S`/`RSQRT.S` use |FT| and round
  to nearest; `CVT.W.S` saturates; the `C.*.S` comparisons compare the bit pattern and never give
  "unordered". Before, a division by zero or an overflow produced infinities or NaN that
  propagated, for example into camera matrices. `ps2recomp-fpu-roots.patch` does not change: its two tests
  now expect the `ps2FpuSqrt`/`ps2FpuRsqrt` calls, which keep the same operands (FT for
  `SQRT.S`, FS/sqrt(FT) for `RSQRT.S`).
- **VU0 in macro mode:** VADD/VSUB/VMUL/VMULQ saturate; `VDIV`, `VSQRT` and `VRSQRT` use the same rules
  with the status register flags. `VRSQRT` computed 1/sqrt(FT) and **ignored FS**; it is now
  FS/sqrt(|FT|).
- **LQ/SQ/LQC2/SQC2 ignore the 4 low bits of the address** (9bb389e).
- **BLEZ/BGTZ/BLTZ/BGEZ (and their variants) compare the 64-bit register**, not the low 32 bits (3c46932).
- **Final jump to the entry of the called function** (c4c20e8): `dispatchGuestBranch` took a call
  that returned with the PC at its own entry as an implicit return; if inside there was a jump (`j` back
  to the function), the caller continued with the other function's stack. It now only applies if no
  jump was dispatched inside, in addition to the checkpoint condition that already existed.

Not yet incorporated are the delivery of each EE timer overflow (d328765), which
depends on other changes of the fork, nor the constant propagation with relocations (019867b), which
affects relocated modules that God of War does not use.

Tests: 6 new tests (comparisons, addition with alignment, division and root with rounding, LQ/SQ,
final jump, VU0 Q unit) and the fork's 64-bit branch one; the suite passes **479/479** with the 16
patches. **It remains to be checked with the game:** `scripts\2_compilar.cmd` is needed (it changes the code that
the recompiler generates and the 6,418 units are regenerated). Repeat the positions test and the camera
matrix test at state 11 and compare the captures.

### OpenGL presentation and interlaced fields (2026-10-05)

`ps2recomp-gs-presentation.patch` is added after the OpenGL backend, without modifying the
imported patch or the EE/FPU/IOP/VIF/VU1 scopes of the other task.

The first difference found was `preferredSource`: the GPU did not respect the source
selected by the frontend. It is fixed by preserving its units of **256 B blocks**,
distinct from DISPFB's **8 KB** pages, with its format, stride and origin. The test
uses a base not aligned to pages and the four color formats. That fix was not enough
for the game sample: the trace confirmed **two active circuits and no preferred
source**.

A temporary diagnostic compared the CPU compositor with OpenGL over **the same VRAM obtained
from the GPU**. The game uses `PMODE=0x8023`, CT24 and field mode (`SMODE2 & 3 == 1`), with a
vertical offset of one row between circuits. The CPU selected and duplicated the
rows of the even/odd field; the shader omitted that parity. This pins down a difference
in presentation without attributing it to VU1 or to vertex zeros.

The shader incorporates the field selected by `vsyncTick & 1`, including the parity in
the shared presentation key. In progressive mode no alternation is forced. The
single-circuit output is also fixed to show its RGB without blending against the background
by the pixel's alpha. The deferred readback preserves the source and destination of each image.
The temporary diagnostics were removed after locating the cause.

The two GPU tests fail before the fixes (**472/474**) and pass after (**474/474**),
both with compute and with graphics rasterization. They compare even/odd fields and progressive mode,
zero alpha, source selection and full pixels against the CPU. They include GoW's
timing registers with a synthetic **512×448** pattern, without game data. The 16 patches
apply in an isolated tree and their 61 compared sources match the local runtime.

The full rebuild of the fix regenerates the 6418 units and links correctly.
In a separate 155 s run, OpenGL initializes on the RX 5700 XT without fallback and
reaches state 11. The four captures from `70–130 s` are distinct; they still show
dark water, without Kratos or the full environment. These are results prior to the integration
of EE/FPU: that visual change is not attributed to Opus's later fixes.

Before publishing, `main` as updated by Opus (`d3fcfa9`, with
`ps2recomp-ee-fixes.patch`) is integrated. Both patches are kept and the
6418 units are rebuilt again. The combined native suite passes **481/481**, including the two real GPU
tests; the separate GS cache tests pass **45/45**. The **17 patches** apply in
order and the **65 sources** compared match the local runtime. Configuration and
handlers without errors (four known warnings); nine scripts without syntax errors.

The combined 155 s run, with position and render diagnostics enabled,
initializes OpenGL without fallback and reaches state 11. It saves three distinct late captures
at `94.85 / 95.19 / 110.10 s`; it does not manage to save the fourth before the limit.
Water and some artifacts are seen, with no Kratos or the full scene. That run with
diagnostics is not a performance measurement and does not change the initial FPS comparison.

The probe logs **64 initializations, 298 returns and 128 subsequent reads**:
the 14 addresses of caller `0x12E258` keep the `(0,0,0,0x8000)` template in
112 reads; the two of `0x1FB800` have non-zero, changing XYZ in the other 16.
The EE/FPU fixes do not eliminate that deliberate loader template. In the VU1 snapshot
at state 11, the 16 floats of the matrix at `0x1060` are finite; this check
of a single matrix does not certify all the transformations. It remains pending to correlate
the buffers written by their producers with VIF/VU1 and the triangles received by the GS.
The snapshots and captures stay in `logs/`, ignored by Git.

### Provenance of positions and PATH1 packets (2026-10-05)

The RAM → DMA/VIF → VU1 → GIF path is followed on `12d5da0`, with Opus's EE/FPU fixes
already integrated. Two instrumented runs of **165 s and 105 s** reach
state 11 with OpenGL. The local probes keep the first eight VIF1 streams,
48 VU1 input states and 256 complete PATH1 packets from that state. The second
run also observes the provenance of each DMA span, without changing its data or
the execution of EE/FPU/IOP. Those probes and the replay test are removed when done;
the dumps remain exclusively in `logs/`.

In VIF1 stream number 1, of **481,064 B**, the command `0x6C788002` at `0x62104`
unpacks 120 V4-32 vectors. Its payload at `0x62108` already contains 120 copies of
`(0,0,0,0x8000)`. The DMA trace places it in RAM at **`0x812390`**: the span starts at
`0x620E8`, comes from `0x812370` and contains 3,904 B. That address is exactly the one
returned to caller `0x12E258` of `LoadClient`, for object `0x8084C0`, chunk 0,
buffer 1. The template is thus linked to its origin, without deducing it from its content alone.

| Payload in stream 1 | RAM address | Observed caller | Chunk / buffer |
|---|---|---|---|
| `0x62108` | `0x812390` | `0x12E258` | 0 / 1 |
| `0x6BAD0` | `0x7F3220` | `0x12E258` | 0 / 1 |

There are eight payloads of that size and with that template in stream 1; they reappear with
the same origins in streams 3, 5 and 7. The reads observed in VU1, byte PC
`0x3240`, also find the template in data memory before transforming it.
The zeros in these samples already exist before the UNPACK: they are not introduced by the GS
renderer. This does not demonstrate that all those buffers must contain visible geometry nor
rule out later selection or transformation problems.

In contrast, the non-zero addresses `0x7FCEB0` and `0x81C020`, updated by `0x1FB800`,
do not appear as a payload origin in the eight sampled DMA chains. The sample
is limited; their selection and sending still have to be identified before linking them
with an output packet. No buffer change is forced and no positions are written.

The new inspector, `tools/gs/inspeccionar_paquetes.py`, validates tag and
payload limits and counts XYZ, ADC/XYZ3 and coordinate ranges. Both PATH1 captures give
**2,654 vertices: 337 with kick and 2,317 without kick**, in 256 packets; 220 contain no XYZ.
A kick requests drawing, but is not by itself equivalent to a valid triangle. Packets
252 and 254 have 120 identical XYZ each, with ADC set in all of them. Other packets
have distinct positions and kicks enabled. The discard in this sample is already present
in the VU1 output, before the GS backend processes it; it has not been demonstrated that all
those discards are incorrect nor that they alone explain the missing scene.

A local reproduction from VU1 input state number 5 generates exactly
original packet number 11: SHA-256
`3c6dab3532d876d6b914213fc96cb89af6cfdf92697d6fb0051532b82dff57cb4`.
The suite with that temporary test passes **480/480** (479 normal ones and the replay, without the two
GPU tests). This makes it possible to reproduce the interpreter's result; it does not certify its
equivalence with PS2 hardware. The Q trace shows later divisions and consumptions;
the initial value Q=2 observed before DIV does not prove that perspective is stalled.

The inspector includes eight synthetic tests of PACKED/REGLIST/A+D layout,
ADC versus fog/XYZ3, PRE, NREG=0, IMAGE, padding and truncation; they are also run
in CI. It includes no game data. Usage and scope: [`rendering.md`](rendering.md).
The next step is to correlate a discarded non-degenerate packet with its transformation/CLIP
inputs and follow the sending of the updated buffers. No behavior fix is published
with this investigation and a complete 3D scene is not demonstrated.

After removing the probes, their sources are rebuilt and the game and test executables
are linked again; neither keeps the temporary capture/replay options.
The native suite again passes **481/481**, including the two real GPU tests.
The 17 patches apply and the 65 audited sources match the local runtime.
The inspector passes 8/8, configuration and handlers have no errors (four known
warnings), the nine PowerShell scripts and libpad2 pass their checks.

### Provenance extension and VU1 clipping (2026-10-06)

A 175 s run with `GOW_SKIP_FMV=1`, `GOW_FAST_BOOT=1`, OpenGL and temporary probes
reaches state 11. It extends the sample to **128 VIF1 chains and 15,798 DMA spans**.
No observed payload includes `0x7FCEB0` or `0x81C020`, the two buffers with changing XYZ.
Their objects (`0x7FCCC0`, `0x81BE30`) keep `updated=0`, `rendered=1`, `view=1` in
all 128 samples. Both DMA buffers are non-zero. This is an observation of this sample,
not proof that they are never sent nor that they must draw a specific part of the scene.

Inspection of the MIPS of `renEEPrimContext::ProcessServer` (`0x141B78`) places the selection
at `0x141C18–0x141C34`: it reads the updated index from `object+0x146`, selects the DMA
and copies it to `object+0x147` before the object's view filter. It remains to observe whether the
context walks those objects and which filters it applies; the buffer swap is not forced.

The trace of VU1 replay number 5 observes the operands **after the issue stall**.
It keeps the SHA-256 of original packet number 11 and logs 1,576 instruction pairs.
The 86 CLIPs are split between byte PC `0xD28` and `0xD30`; FT.w is negative in all of them
(-427.592 to -75.934). CLIP changes are seen with their latency. This does not demonstrate a clipping
failure: first the expected space and sign of the transformation must be checked.
The packed integers that show up as NaN when read as floats do not prove
a positions error either. The probes and the replay are removed; the data stay in `logs/`.

### DIRECT continuation and IMAGE/VIF separation (2026-10-06)

Claude's fix
[`540defd`](https://github.com/KIexster/god-of-war-recomp/commit/540defd) is integrated in its own patch, without incorporating
the EE/IOP changes of its branch. Before, an IMAGE pending from GIF PATH2 consumed the VIF commands
following the DIRECT as if they were pixels. Now it only takes the payloads of the
following DIRECT/DIRECTHL, keeps MARK/STCYCL/ITOP and processes the GIFtags following
the image. Priority corresponds to the current DIRECT. Two old tests are fixed
because they expected pixels without the following DIRECT command.

The new regression and those two tests fail before the fix (**477/480**) and pass after
(**480/480**); when adding the priority test, the normal suite passes **481/481**.

It is also detected that DIRECT cut its size down to the available block and lost the rest.
`ps2recomp-vif-direct-fragments.patch` preserves the incomplete payload and DIRECTHL between
blocks, without copying the complete payloads and with a limit of 1 MiB. Six new regressions
fail without that change (**481/487**) and pass with it. They include all the byte cuts of
32 B PACKED/REGLIST, FIFO, IMAGE with VRAM check, priority, IMMEDIATE=0 and reset.
The suite with real OpenGL passes **489/489**. The **19 patches** apply and their **67 sources**
audited match the local runtime. Configuration and handlers without errors (four
known warnings), GIF inspector 8/8 and PowerShell scripts without syntax errors.

Scope, primary reference, credit and optional diagnostic: [`rendering.md`](rendering.md).
The full rebuild regenerates the **6,418 units** and finishes correctly. After it,
the native suite again passes **489/489**, including the two GPU tests. Libpad2 also passes.
A **175 s** game run, with `GOW_SKIP_FMV=1`, `GOW_FAST_BOOT=1` and `GOW_VIF_DIAG=1`,
initializes OpenGL on the RX 5700 XT without fallback and reaches state 11 with `pending=0`,
`levelReady=1` and `flashReady=1`. It saves two distinct late captures at **90.27 and 110.04 s**;
it does not save the 130 s one before finishing. Dark water is seen, with no Kratos or the full scene.

No `[gow-vif-direct]` messages appear in that run: **no truncated DIRECTs are observed**
in the sample. The regressions demonstrate the runtime defects, but this test does not prove
that they caused the missing scene nor does it allow a visual or FPS improvement to be attributed to them.
The captures and logs stay in `logs/`; the temporary geometry probes are no longer
in the rebuilt executable. The next step is to observe the membership of the buffers
updated in `renEEPrimContext::ProcessServer`.

### Render context membership (2026-10-06)

The optional diagnostic `GOW_EE_PRIM_DIAG=1` is extended to observe the list of
`renEEPrimContext::ProcessServer` at entry, without writing memory or changing the
original execution. The rebuild of `src/` finishes correctly. Up to
64 entries are logged before state 11 and another 64 in it, with at most 256 nodes per
entry and detection of pointers outside RAM, cycles and truncation.

A **175 s** run with OpenGL, `GOW_SKIP_FMV=1`, `GOW_FAST_BOOT=1` and automatic
controller without captures reaches state 11. The **64 samples** of that state belong
to context `0x7B8DC0`: view `0x75CD70`, ID `0x45`, context mask `0x3` and camera
`0x7A3950`. Its list contains **two objects** and ends without cycle, invalid pointer or
truncation. Both pass the first filters observed; that does not demonstrate drawing nor
the later material and transformation filters.

The objects `0x7FCCC0` and `0x81BE30`, updated by caller `0x1FB800`, **do not belong
to that list in any of the 64 samples**. Their `object+8` links are zero and they keep
`updated=0`, `rendered=1`. The producer keeps obtaining both buffers with changing XYZ.
This explains why that context does not alternate its indices in the sample; it does not demonstrate
that they must be registered in it nor that their absence causes the lack of Kratos.

The next step is to identify who creates and registers those clients, and to correlate
the two objects that the context does receive with the VU1 inputs. Their registration
and the buffer change are not forced. The results stay in `logs/`. The CI of VIF commit
`f5711bd` passes both the quick checks and the Linux runtime build and suite:
[run 37457211736](https://github.com/KIexster/god-of-war-recomp/actions/runs/37457211736).

### FIFO order and DIRECTHL in the GIF (2026-10-06)

The comparison in `GifArbiter::drain` mixed the numeric priority of the path with a
DIRECTHL/IMAGE exception inside `std::stable_sort`. DIRECT and DIRECTHL of the same path
were equivalent, but had different relations with a PATH3 IMAGE: the
comparator was not a strict weak ordering. In the regressions, this allows changing the
order of a single channel or serving DIRECTHL before the pending IMAGE.

`ps2recomp-gif-order.patch` groups only by path, keeping stability, and arbitrates
between the PATH2/PATH3 headers after PATH1. The exception no longer enters the
sorting comparator. It also preserves the packets added by a callback in order to
process them in the next batch. It does not change the CPU/OpenGL backends nor the EE/IOP semantics.

The two regressions test all the permutations of DIRECTHL/DIRECT/IMAGE and of
DIRECTHL/setup/IMAGE. They fail before (**487/489**, normal suite) and pass after. The suite
with the two real OpenGL tests passes **491/491**. The **20 patches** apply in order
and their **68 sources** audited match the local runtime. Scope and reference:
[`rendering.md`](rendering.md).

The CI of context diagnostic `f8a851a` also passes:
[run 37458210600](https://github.com/KIexster/god-of-war-recomp/actions/runs/37458210600).
The full rebuild regenerates the **6,418 units** and finishes correctly. After
it, the suite again passes **491/491**, including the two OpenGL tests, and a new
audit confirms the **68 sources** of the **20 patches** without differences.

A **175 s** run with OpenGL, `GOW_SKIP_FMV=1`, `GOW_FAST_BOOT=1`,
`GOW_EE_PRIM_DIAG=1` and `GOW_ANM_DIAG=1` initializes the RX 5700 XT without fallback and reaches
state 11 with `pending=0`, `levelReady=1` and `flashReady=1`. The late captures at
**110.19 and 130.27 s** are distinct and show dark water; Kratos and the full
scene are still absent. The **64 samples** of context repeat the valid two-object list
and the absence of `0x7FCCC0`/`0x81BE30`. No visual or FPS improvement is attributed to the new
order. Captures and logs stay in `logs/`.

The CI of GIF fix `701da8d` passes:
[run 37461636026](https://github.com/KIexster/god-of-war-recomp/actions/runs/37461636026).

The **600 s** control without `GOW_FAST_BOOT`, with the same executable, `GOW_SKIP_FMV` and
the same probes, shows progress of the intro up to **11.75 s** of animation in
the preserved messages and then reaches state 11. The **64 samples** repeat the
context, camera and valid two-object list; `0x7FCCC0` and `0x81BE30` are still absent.
The captures at **360.28 and 480.20 s** are distinct and show dark water, with no Kratos.
This control provides no evidence that the accelerated boot causes that absence in
the observed context. It does not demonstrate the registration of all the other objects of the level
nor does it allow FPS to be compared under diagnostics.

### Effects of empty GIF tags (2026-10-06)

On reviewing the parser, it is detected that it applied PRE and reset Q even if `NLOOP=0`.
Applying PRIM also discarded the pending vertices, even with the same topology.
REGLIST and IMAGE improperly applied PRE. The general parser and the native PACKED
path are fixed in `ps2recomp-gif-tag-semantics.patch`, keeping the frontend common to CPU
and OpenGL. The IMAGE upload shortcut in turn omitted PRE of the PACKED setup and the reset of
Q of non-empty tags; this is fixed without changing the image bytes.

The first three regressions fail before (**489/492**, normal suite). After those fixes,
the new IMAGE upload regression still fails (**492/493**), before fixing that
shortcut. They cover both paths, empty tags with and without PRE between vertices, Q, modes that
ignore PRE and non-empty controls. Scope and primary reference:
[`rendering.md`](rendering.md).

Review of the two earlier local captures of 256 PATH1 packets finds in
each **205 empty tags, 90 with PRE=1 and PRIM=0x5C**, with no packet truncations.
It is the same case that the fix turns into a tag with no emissions to the GS; that does not
demonstrate by itself that it caused the missing scene. The suite with real OpenGL passes
**495/495**. The **21 patches** apply and their **68 sources** audited match the
local runtime. Configuration/handlers without errors (four known warnings) and PowerShell
without syntax errors. The full rebuild regenerates the **6,418 units** and
finishes correctly. After it, the suite again passes **495/495** and the new audit
confirms the **68 sources** of the **21 patches** without differences.

The **175 s** run with the same OpenGL/SKIP_FMV/FAST_BOOT options and context/animation
probes initializes hardware rasterization on the RX 5700 XT without fallback and
reaches state 11 with `pending=0`, `levelReady=1` and `flashReady=1`. The captures at
**110.24 and 130.14 s** show dark water and are distinct, but Kratos
and the full scene are still absent. The **64 samples** keep the valid two-object list and
the dynamic buffers outside it. The fix corrects the effects of the tags;
this run does not demonstrate a visual or FPS improvement. The game data stay
in `logs/`.

### Identification of the producer of the dynamic buffers (2026-10-06)

The retail MIPS of `0x1FA8A8` calls `0x1FB4B8` with five vectors and then
`attachment::tChained::Connect` (`0x1FCD48`, name from the symbol map) and another routine
with four vectors. The five-vector routine obtains types 3 and 0 of the same `renEEPrim`,
chooses the index opposite to the one shown and writes seven UV coordinates with the same
constants as `attachment::tChained::DrawGapFiller` in the GoW 2 reference with symbols.

These matches probably link the buffers of `0x1FB800` with the filling of the
attachment chains. They do not confirm the retail name nor that those objects must be
registered in the observed context. The structures differ between versions; `funcmap.csv`
is not changed and no game code is replaced. The body of the scenery and of Kratos
must also be followed through the models path. `renModelServer::ProcessServer` is located
at `0x159C58` (name from the map): it selects a context from a table and calls its
virtual method before sending the DMA chain. The next diagnostic will observe that selection
and the discarding of models, preserving the original execution.

### Context selection by the model server (2026-10-06)

`GOW_MODEL_DIAG=1` is added as an optional observation of `0x159C58`. The recompilation of
`src/` finishes correctly and PowerShell passes without errors. The probe preserves the
checkpoints and always calls the original; it writes no registers or game memory.
The profile removes the variable. Scope: [`rendering.md`](rendering.md).

A **175 s** run with OpenGL, SKIP_FMV, FAST_BOOT and the context/animation probes
logs **64 samples in state 3 and 64 in state 11**. All observe server
`0x59D878`, table `0x59DBA8`, group/slot `0/0`, array `0x59DBC0`, context `0x59DDC8`
and virtual table `0x2C2468`, with pointers inside RAM. The `this` adjustment is zero and the
selected target is `0x1511F0`, identified by the map as
`renGROBMasterContext::ProcessServer`. The GoW 2 reference also calls a GROB
master context from this path: the observed target does not demonstrate an incorrect selection.

The captures at **110.16 and 130.04 s** again show dark water, with no Kratos or the
full scene. The logs keep `pending=0`, `levelReady=1` and `flashReady=1`.
The entry observation does not certify the later calls nor the culling of
models. The next step is to follow the contexts and instances that master walks,
and to correlate its discards with the VU1 packets. Captures and logs remain in `logs/`.

The CI of tag fix `f385fcc` passes:
[run 37465434359](https://github.com/KIexster/god-of-war-recomp/actions/runs/37465434359).

### Actual walk of the GROB master and model lists (2026-10-06)

`GOW_MODEL_DIAG=1` is extended to observe the entry of master `0x1511F0`, the
lists of `0x159878` and the calls to `0x157A60`. The retail map leaves the last two
as unnamed functions; their structure matches `renModelServerContext::ProcessServer`
and `ProcessModel` respectively in the GoW 2 reference.
The offsets of the filters are checked in the retail MIPS, without copying its generated
code. Scope and limits: [`rendering.md`](rendering.md).

The first **175 s** test confirms that the master is shared by several
servers. Each context is then limited separately so that other servers
do not exhaust the model samples. The second test, also **175 s**, logs
at state 11 four active model contexts. `0x1111B98` contains **14 models**:
one fails the view mask, eight are candidates for the static tree and five for the
direct call. The other contexts contain **1, 1 and 2 models**, all candidates
for the direct call in the samples observed. **64 real entries** are verified
to the processing routine in this phase, spread across nine distinct models,
with one group each. The observed lists show no cycles, invalid pointers
or truncations.

During the first 64 samples of the model master, the list grows from eight to
thirteen contexts and then settles at eleven, with three active. The 14-model context
is observed in **21 calls** before that reduction. It is a transition of the observed
state; it does not by itself identify a registration failure nor which models are
Kratos's. The captures at **110.25 and 130.21 s** continue to show dark water without
Kratos or the full scene. No registrations, visibility or indices are forced.

The next observation logs the skeleton root visibility and the return of
`renView::Clip` coming from model processing. An entry into that routine
does not yet prove that the model passes its internal filters nor that it emits geometry.

### PEXEW duplicates Y into the Z of the visibility spheres (2026-10-06)

The third **175 s** run adds the visibility and Clip observation. The **64
processing entries** at state 11 have a valid and visible skeleton root,
and the first group visibility block is `0xFFFFFFFF`. In the **64 observed
calls to Clip**, corresponding to seven distinct models, the four arguments
are finite, Y and Z have the same bits and the real return is **`0x80000000`**, discard.
Before state 11, 49 discards and 15 `0x20` returns are logged. These limits do not
cover all models nor all discards of the scene.

A concrete cause of the duplicated arguments is located: at `0x157F94`, PROT3W
extracts Y for `f13`; at `0x157FA0`, PEXEW should extract Z for `f14`. The current macro
`PS2_PEXEW` uses `_MM_SHUFFLE(2,3,0,1)`, which also copies Y into the low word.
An isolated native reproduction with words **[11,22,33,44]**, unrelated to the game, confirms
the incorrect permutation. It also detects that PROT3W rotates the four words, when
it should keep the fourth. The semantics are contrasted with
[PCSX2's PEXEW and PROT3W, commit 32ac6e2](https://github.com/PCSX2/pcsx2/blob/32ac6e23e4aaf8c8c5e74a6c1ed750ee7672120e/pcsx2/MMI.cpp#L1435).

| Instruction | Current result, from low word to high | Expected result |
|---|---|---|
| PEXEW | [22,11,44,33] | [33,22,11,44] |
| PROT3W | [22,33,44,11] | [22,33,11,44] |

**Resolved in `ps2recomp-mmi.patch` (see "Audit of the MMI instructions").** Original pending item: fix PEXEW in `ps2_runtime_macros.h`
(`_MM_SHUFFLE(3,0,1,2)`) and PROT3W both there and in the emission of
`mmi_translation_helpers.cpp` (`_MM_SHUFFLE(3,0,2,1)`), with regressions of the four
words, source/destination aliasing and register zero. PROT3W is emitted inline and requires
regenerating the functions; changing only the macro does not fix the executable. This turn
does not modify the recompiler, FPU, IOP or the EE patches.

The incorrect macro explains the badly extracted Z; it has not yet been proven how much the discard
or the image change after fixing it. The captures at **110.04 and 130.22 s** still
show water without Kratos or the full scene, with hardware OpenGL and state 11.
The probes compile on Windows and the data/reproductions stay in `logs/`. The next
render test must repeat these probes after integrating the EE fix and then follow
the models that pass Clip through to the parts and the VU1 packets.

### GIF continuations and equivalence of the DMA shortcut (2026-10-06)

Four patches are added at the end of the build list, without modifying the patches
of the EE, the FPU, the recompiler or the IOP:

| Patch | Verified change |
|---|---|
| `ps2recomp-gif-stream.patch` | PACKED/REGLIST/IMAGE cursors per PATH; preserves registers, Q, padding and pixels between blocks and distinct DIRECTs; VIF delivers original bytes without IMAGE wrappers. |
| `ps2recomp-gif-image-order.patch` | DIRECTHL recognizes IMAGE continuations and tags after setup; it does not confuse registers or padding with tags nor block on an empty IMAGE. |
| `ps2recomp-gif-image2.patch` | FLG=3 consumes the IMAGE2 payload in the general/native paths and preserves its classification in the arbiter. |
| `ps2recomp-gif-native-tag.patch` | The texture DMA shortcut preserves the setup's PRE, resets Q and accepts IMAGE2 after validating the whole chain; rejection with no effects on the GS. |

The failures are reproduced before fixing each topic: **4** fragmentation tests,
**4** classification tests, **3** IMAGE2 tests and **1** DMA shortcut state test. **20 regressions**
are added in total, with checks for reset, interleaved PATH, NREG=0 and rejected
chain. The native suite passes **515/515**, including two tests with real OpenGL.
The expectation of an old IMAGE wrapper and four priority fixtures
that used empty images are adjusted; the reasons are detailed in
[`rendering.md`](rendering.md).

The audit applies **25 patches** on the pinned commit and compares **71 sources**,
without differences with respect to the tested tree, also after the full build
with **6,418 generated units** and result zero. The **515/515** suite is repeated with
real OpenGL. A **175 s** run with SKIP_FMV, FAST_BOOT and the model probes
reaches state 11, `pending=0`, `levelReady=1` and `flashReady=1`, with no CPU fallback.
The captures at **90.13 and 110.09 s** show water, with no Kratos or the full scene.
The **64 observed calls to Clip** in that phase still discard the models with
`0x80000000`; Y and Z keep the same bits and the arguments are finite.

No FPS improvement nor the appearance of Kratos is demonstrated. The arbitration still works
with complete blocks, without reproducing all the cycles or preemptions of the hardware.
The positions and the model discards will have to be repeated after the pending MMI fix
in the EE. During validation another separate problem is reproduced on CPU and OpenGL:
48 CT24 bytes together produce 16 pixels, but in three 16 B blocks they produce only 15
and leave the transfer open. The work continues with the preservation of that partial pixel;
the synthetic data and the captures remain in `logs/`.

The CI of `1f009b4` passes:
[`Pruebas`, run 37497401093](https://github.com/KIexster/god-of-war-recomp/actions/runs/37497401093).

### CT24/Z24 pixels split across IMAGE uploads (2026-10-06)

`ps2recomp-gs-image-fragments.patch` keeps at most two pending bytes per
backend. It completes the pixel with the next upload and passes the rest directly to the
existing upload, without retaining a copy of the texture. The accumulator is cleared when
resetting or starting another transfer; exporting/importing the OpenGL state preserves it.
Formats other than CT24/Z24 keep using the previous path.

The suite reproduces **three failures** before the change: CPU uploads, OpenGL uploads and
export of a partial pixel. With the change **519/519 tests** pass, including
four with real OpenGL. Full VRAM and pixel counter are compared at all the
cuts of a 48 B upload, as well as repeated uploads of 1 B and 16 B, high byte preserved
in CT24/Z24, reset/new transfer and export/restore. The tests contain
synthetic data. The audit applies **26 patches** and reproduces exactly **73 sources**.
The full build finishes with **6,418 generated units** and code zero;
the **519/519 tests** are repeated with real OpenGL and the exact source audit.
The **175 s** game control reaches state 11, `pending=0`, `levelReady=1`
and `flashReady=1`, with no CPU fallback. The captures at **90.15 and 110.13 s** still
show water without Kratos or the full scene. The **64 observed calls to Clip**
at state 11 discard with `0x80000000`, with identical Y/Z and finite arguments.
This fix corrects fragmented uploads; it does not demonstrate an FPS improvement nor resolve
the model discarding that is being investigated separately in the EE.

The CI of `0a4f66c` passes:
[`Pruebas`, run 37501053476](https://github.com/KIexster/god-of-war-recomp/actions/runs/37501053476).

### Triangle centers and edges in the CPU renderer (2026-10-06)

`ps2recomp-gs-triangle-sampling.patch` shares with OpenGL the triangle rules
adapted from the SotC fork: integer center, full 12.4 XYOFFSET and shared edge
drawn only once. The previous CPU shifted the sample by half a pixel, truncated
the offset and accepted both sides of an edge. Three regressions reproduce those
failures; OpenGL compute/hardware already passed them. Now **523/523 tests** pass,
including five with real OpenGL. Three old fixtures are adjusted for the reasons
documented in [`rendering.md`](rendering.md).

The independent comparison of full VRAM in **48 cases** of flat/IIP triangles,
four Z test modes and Z32 values `7`, `0x80000001` and `0xffffff01`, on both
OpenGL paths, goes from **12 differences** to **zero**. This improves the CPU reference for
comparing the GPU renderer; it does not prove that all GS effects are equivalent.
The full build finishes with **6,418 generated units** and code zero;
the **523/523 tests** are repeated with real OpenGL. The audit reproduces **27 patches
and 74 sources** exactly. The **175 s** game control reaches state 11,
`pending=0`, `levelReady=1` and `flashReady=1`, with no CPU fallback. The captures at **90.02
and 110.00 s** still show water without Kratos or the full scene; the 64 calls
observed to Clip in that phase keep the `0x80000000` discard, identical Y/Z and
finite values. The synthetic comparison improves; the playable game and the FPS remain undemonstrated.

[Tobiichi-Port at `9f02797f`](https://github.com/YYOzcan/Tobiichi-Port/tree/9f02797f8ab7481fddad4d2daf7afad82d11699f) is also reviewed.
The five GS/VIF/VU1 files compared match our pinned base runtime.
Its README keeps menu and game pending; the GoW boot shortcuts are not
incorporated as a rendering solution. The review is documented without claiming that
its executable was tested here.

The CI of `5ada6aa` passes:
[`Pruebas`, run 37504095195](https://github.com/KIexster/god-of-war-recomp/actions/runs/37504095195).

### CPU sprite coverage and interpolation (2026-10-06)

`ps2recomp-gs-sprite-sampling.patch` preserves the XYOFFSET/UV fractions and shares
with OpenGL the signed axes of the SotC fork. The CPU stops drawing empty areas and
keeps the texture origin when inverting the axes or clipping with scissor. Four
regressions reproduce the failures before the fix. The synthetic comparison of
full VRAM goes from **14 differences to zero in 16 cases** with compute/hardware;
the suite passes **528/528**, including six tests with real OpenGL.

Eight old fixtures that drew empty sprites are adjusted: they now use a
1×1 rectangle while keeping their CT32 alias, CLUT, alpha and scissor checks.
The new test verifies that zero width/height changes no VRAM byte. The
reasons and provenance are detailed in
[`rendering.md`](rendering.md).
The full build finishes with **6,418 generated units** and code zero;
the **528/528 tests** are repeated with real OpenGL. The audit reproduces **28 patches
and 74 sources** exactly. The **175 s game control with the CPU renderer**
reaches state 11, `pending=0`, `levelReady=1` and `flashReady=1`.
The captures at **90.18 and 110.11 s** still show water without Kratos or the full
scene, and the 64 calls observed to Clip in that phase discard with `0x80000000`,
with identical Y/Z and finite arguments. The same blockage is observed with CPU and OpenGL;
these controls demonstrate neither a playable game nor an FPS improvement.

### Interpolation of constant attributes and alpha test (2026-10-06)

`ps2recomp-gs-triangle-constants.patch` computes Gouraud RGBA and F by differences
between vertices on CPU and OpenGL compute/hardware. The rounded sum of the weights
reduced constant values; alpha 128 could end up at 127 and fail GEQUAL 128,
leaving holes in the triangle. In the 17×19 pixel probe, 17 color centers and
8 fog centers fail on CPU, and 151/110 on each OpenGL path. For F a point with the same
attributes, without interpolation, is used as the reference.

Two CPU tests and one with real OpenGL reproduce the failure before the change; afterwards
**531/531 tests** pass, including seven with OpenGL. The interior centers
and both winding directions are compared; the color test enables GEQUAL 128 to
also detect the holes. The audit reproduces **29 patches and 74 sources**.
The independent probe passes **6/6 cases**: CPU, OpenGL compute and hardware, with constant color
or F. The comparison of gradients and depth keeps **48/48 cases**
equal between CPU and both OpenGL paths. The full build regenerated the 6418
units and finished with code 0; the subsequent suite again passes **531/531**.

The 175 s control uses real OpenGL, with no CPU fallback. The captures at **90.21 and
110.23 s** show water without Kratos; state 11 is reached with `pending=0`,
`levelReady=1` and `flashReady=1`. The 64 calls observed to Clip in that phase still
discard with `0x80000000`, finite arguments and equal Y/Z. The correction of
constant attributes is verified; the complete 3D scene is still missing.
This control uses the IOP prior to the acceleration patch incorporated by Opus;
the integration and its profile will be recorded separately.

The CI of the previous sprite patch also finished green:
[run 37507078237](https://github.com/KIexster/god-of-war-recomp/actions/runs/37507078237).

### IOP interpreter performance (2026-10-06)

The performance measurement profile attributes 61 % of the game thread to the IOP. An IOP with no ready
threads costs little (about 7 ms per emulated second, including the SPU2), so that time belongs to IOP
threads executing instructions. The interpreter ran at about **55 M instructions/s** on the CI machine;
the real IOP runs at 36.8 MHz, so a busy IOP needs almost two thirds of a core to keep up
in real time. With callgrind, each emulated instruction cost about 245 host instructions.

`ps2recomp-iop-fast.patch` (after `ps2recomp-gs-sprite-sampling.patch`) removes per-instruction costs without
changing behavior:

- The lookup of import stubs (`IopImportRegistry::decode`) was done on **every** instruction;
  now only when the instruction is `jr ra`, which is how the stubs begin.
- Instruction fetch and RAM loads/stores with an inline fast path (`fetch32`, `load*`,
  `store*`); hardware registers, scratchpad, SPU2 and SIO2 still go through `read*`/`write*`.
  Writes still mark the RAM as occupied as before.
- The pending DMA check is an inline flag; `PS2X_IOP_PC_EVERY` is read when the IOP is created
  instead of with a local `static` on every instruction; `physicalAddress` moves to the header.

Measured with callgrind (host instructions for the same IOP program): arithmetic loop
737 → 452 M (−39 %), loop with LW/SW 1513 → 907 M (−40 %), that is, about **1.65 times faster**. The
new test "IOP fast loads and stores match the generic memory paths" fixes that the fast accesses
are equivalent to the generic ones (KSEG0/KSEG1 mirrors, written-RAM flag, hardware registers and SIO2
FIFO). The suite passes **523/523** with the 29 patches.

Next step: find out which IOP threads are busy in the game. If they are busy-wait
loops (polling a register or memory), skipping them would yield much more than speeding up the interpreter.
For that, a run with `PS2X_IOP_PC_EVERY=1000000` is enough: the log will show `[IOP:pc]` with the
most repeated PCs. **It remains to be measured with the game:** repeat `scripts\probar_rendimiento.ps1` and compare the
IOP percentage and the `vid::Flip` calls per second.

### Constant coordinates and integration of the fast IOP (2026-10-06)

`origin/main` with Opus's IOP patch is integrated by merge, without modifying its
implementation. Both research logs are kept and the fast IOP is ordered
after sprites and before the new triangle attribute patches.

`ps2recomp-gs-triangle-texcoords.patch` fixes constant UV/STQ on CPU and both
OpenGL paths. The regression includes Q=1.5: it also requires refining the GPU reciprocal,
because the previous texel was selected even at the first center. Before, the
three new tests fail; afterwards the integrated suite passes **535/535**, including
eight tests with real OpenGL. The UV subtractions are signed and the homogeneous
interpolation before dividing by Q is preserved.

The independent probe verifies **24/24 cases of constant attributes**: UV or STQ
with Q=1.5, nearest/linear, both directions and CPU/OpenGL compute/hardware. It keeps
another 12 exploratory cases with variable Q and S/T proportional to Q on exact
texel boundaries: they still differ from the constant control, on both CPU and GPU.
They are not considered resolved by this patch. The regression's gradient avoids those
boundaries and checks that the division after interpolating is maintained.

The hardware variants are compiled asynchronously and may use compute at
the beginning. The probe waits in a bounded way and confirms each hardware draw through
the existing counters: primitives and batches increase without compute tiles increasing.
This also verifies the eight constant cases through the hardware path actually executed,
not just with that path enabled.

The audit reproduces **31 patches and 75 sources without differences**; the 14 PowerShell
scripts are analyzed without errors. The full build finishes with code 0,
regenerates the 6418 units and the subsequent suite again passes **535/535**.
The additional RGBA/alpha-test and F check passes **6/6**, also confirming hardware
with the counters after the asynchronous variants finish.

The first game control was interrupted when the usage limit of the automatic
approval review was reached; it only recorded the boot and did not manage to save
the visual control of the scene. It will be repeated after incorporating the MMI and
VU0 fixes published by Opus during that pause. The renderer remains in a partial state.

### VU0 in macro mode and long DMA chains (2026-10-06)

`ps2recomp-vu0-macro.patch` (after `ps2recomp-iop-fast.patch`) incorporates, with the authorization already given for the
SotC fork, two more commits that affect the EE code:

- **03d18df — VU0 in macro mode uses its data memory.** `VLQI`/`VSQI`/`VLQD`/`VSQD` and `VILWR`/`VISWR`
  read and wrote the **EE RAM from address 0** (`READ128((vi & 0x3FF) << 4)`) instead of the
  VU0 data memory (`(vi & 0xFF) << 4` within its 4 KB); in addition `VSQI`/`VSQD` had the Fs and It
  fields swapped, and VI0/VF0 could be written. In SotC this broke the matrix stack
  (push/pop) and the characters disappeared. If God of War uses those instructions, it was reading and
  clobbering the first 16 KB of the EE RAM.
- **e36fbf1 — DMA chains of more than 4096 tags.** The chain walk was cut off at 4096 tags and
  lost the end: the GIF stayed in IMAGE mode and swallowed the A+D setup of the next frame.
  The limit becomes 2^20 tags and it warns (`[dma] chain on ... stopped after ... tags`) if reached. The same
  commit fixes `VRNEXT`/`VRINIT`/`VRXOR`/`VRGET` (LFSR of the R register), `VFTOI` (saturation) and `VABS`
  (denormals), and shares VU0's R register between threads in `EeScheduler`. The fork's optional tool
  `vu0_audit` is not incorporated (it depends on its reference renderer).

The suite passes **528/528** with the 30 patches (tests from the fork that decode the instructions
`vsqi`/`vlqd`, long DMA chain, random numbers, `VFTOI`/`VABS`). **It remains to be checked with the game:**
it requires `scripts\2_compilar.cmd` (it changes the generated code). It is advisable to repeat the state 11 capture
and, if it appears, look for `[dma] chain` in the log.

### Audit of the MMI instructions (2026-10-06)

Following the PEXEW/PROT3W finding in the visibility sphere (section "PEXEW duplicates Y into the Z of the
visibility spheres"), the code that the recompiler emits for **60 MMI instructions**
(arithmetic, comparisons, saturation, permutations, packing and shifts) was compared with the semantics of
[PCSX2 `MMI.cpp`](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/MMI.cpp). A local differential test
(the code of each instruction was dumped with `CodeGenerator::translateInstruction` and compiled against
`ps2_runtime_macros.h`) ran it with 2000 pairs of random and edge values, with a distinct destination and
with the destination equal to each source, against a reference written from PCSX2. **15 instructions did not match:**

| Instruction | Failure |
|---|---|
| PEXEW, PROT3W, PEXCW | words in the wrong order (PEXEW copied Y into the Z of the visibility spheres) |
| PEXEH, PREVH, PEXCH | halfwords in the wrong order (PREVH reversed all 8 instead of each half) |
| PINTH, PINTEH | interleaved the wrong half of rs |
| PABSW, PABSH | read rs instead of rt and did not saturate 0x80000000 / 0x8000 |
| PADDUH, PSUBUH | added/subtracted without saturating |
| PSLLVW, PSRLVW, PSRAVW | shifted rs (not rt) and on all four words, without sign-extending to 64 bits |

`ps2recomp-mmi.patch` (after `ps2recomp-vu0-macro.patch`) fixes the macros of `ps2_runtime_macros.h` and the
emission of `mmi_translation_helpers.cpp`. With the patch, the 60 instructions match PCSX2 in all
the variants. The suite gains `PS2Mmi` (permutations with [11,22,33,44], PABS saturation, shifts
and emitted forms) and passes **533/533** with the 31 patches.

**It remains to be checked with the game** (it requires `scripts\2_compilar.cmd`, it changes the generated code): repeat
the Clip probes at state 11. With PEXEW fixed, the sphere's Y and Z should stop coinciding and
some models should pass Clip.

### Integrated GS, MMI and VU0 control (2026-10-06)

`origin/main` at `0421ec4` is integrated by merge, keeping Opus's patches
and the two new GS patches for constants and coordinates. The 33 patches reproduce
exactly the 78 modified runtime sources. The 6418 units are regenerated
and the full executable is rebuilt. MSVC initially interrupts `libsd.cpp` without
emitting a diagnostic; resuming compiles that unit and links correctly without
changing sources. The integrated native suite passes **545/545**, including eight OpenGL
tests on Windows; the configuration and the 14 PowerShell scripts pass their checks.

The 175 s OpenGL control reaches state 11. In its first 64 calls to Clip
from ProcessModel, the spheres are finite and **none has Y and Z with equal bits**.
**30 return `0` and 34 return `0x80000000`**, versus 64 rejections and 64 identical Y/Z
pairs in the previous control. The sample covers eleven models; it is not a census of
the whole scene. Model `0xD51C80`, group `0xD599C0`, passes Clip in its five samples.
The remaining discards may correspond to objects out of view and are not forced.

The observed positions also change: primitive buffers that
do belong to the contexts are updated, from calls such as `0x1644E0`, with non-zero data.
This goes beyond the previous diagnostic limited to the loader template and to the
buffers of `0x1FB800`; it does not certify that all the geometry sent is correct.

The capture at 138.75 s of the PAD clock is at state 11 (`pending=0`, `levelReady=1`,
`flashReady=0`) and shows deformed polygons/textures. The one at 110.02 s is still at
state 4 and shows an orange texture and large triangles. Real OpenGL is initialized
on the RX 5700 XT, with no fallback. **Kratos and the complete scene remain pending**;
passing Clip is not equivalent to a playable game. The logs and captures stay only
in `logs/integrated_mmi_gs_game/`, excluded from the repository.

The next control detects VU1 stops at `pc=0x288`, instruction `0x8040FFFE`.
The LowerOP table of [PCSX2 pinned at `32ac6e2`](https://github.com/PCSX2/pcsx2/blob/32ac6e23e4aaf8c8c5e74a6c1ed750ee7672120e/pcsx2/VUops.cpp)
identifies it as EEXP; the runtime considers it reserved. The codes of ERSQRT, ESIN and EATAN
are also crossed. A separate VU1 patch will be prepared with tests
of explicit binary instructions, without modifying the existing EFU formulas.
The profile prior to that fix includes the errors emitted by those stops and
must not be described as the performance of a correctly rendered scene.
The performance script also removes experimental geometry and replay diagnostic
variables, and restores their values when it finishes.

The 240 s OpenGL profile, with no captures or optional diagnostics and no other tests
or builds running concurrently, confirms state 11 before the measured interval. Its
eight complete windows from 180.31 to 220.38 s give **1.00 `vid::Flip` calls/s** and
**59.11 presentations/s**. The elapsed exclusive time of the game thread is split into
IOP 53.18 %, VU 40.59 %, EE 3.69 % and GS submission 2.53 %. It includes the VU1 errors
emitted by default; GS does not measure the execution of the OpenGL worker here. These
are not CPU/GPU utilization percentages. The old control of 3.45 Flip/s discarded
every observed model: the work now executed has changed and the difference cannot
be attributed to the IOP patch. The profile will be repeated after fixing EFU.

### VU1 EFU decoding (2026-10-06)

`ps2recomp-vu1-efu-opcodes.patch` separates an earlier interpreter bug: according to the
PCSX2 LowerOP table linked above, ERSQRT uses `0x79`, ESIN `0x7C`, EATAN `0x7D`
and EEXP `0x7E`; `0x77` is reserved. The runtime used `0x77`, `0x79`, `0x7C` and
`0x7D` respectively. This halted the GoW microprograms that execute EEXP at
`pc=0x288` and selected a different formula for the three earlier instructions.

Both the execution and the decoding used by the cache and the scheduler are fixed,
with the latencies of the existing operations. The formulas, access to P and the
EFU restriction on VU0 are kept. Three new regressions use explicit binary words:
they check the results and WAITP/continuation of the four instructions, the rejection
of `0x77`, and that EEXP remains reserved on VU0. Two earlier EATAN and EFU latency
fixtures are adjusted to the correct encodings without relaxing their assertions.
With those fixtures, four tests fail before the change;
with the fix **540/540** pass without enabling the eight OpenGL tests.

The full build with the 34 patches again regenerates the 6418 units
and finishes correctly. The later audit compares 78 sources with no differences;
the native suite passes **548/548**, including the eight OpenGL tests. The four
earlier failures are fixed and the reserved-instruction cases remain covered.

The 300 s OpenGL control reaches state 11 and records **zero reserved VU1
instructions** during the whole run. It keeps the results of the 64 Clip samples
(30 pass, 34 discarded; all finite, no duplicate Y/Z). It saves 14 distinct
captures; those at 190.71 and 240.36 s of the PAD clock are in state 11, with
`pending=0`, `levelReady=1` and `flashReady=0`. They show more geometry and textures than
the earlier control, but with huge polygons, stripes and distortions. Kratos
is not recognizable and the complete scene is still pending. The data stays in
`logs/vu1_efu_opcodes_game/`, excluded from Git.

The later 240 s profile, with no captures or optional diagnostics and no other
concurrent builds/tests, measures eight complete windows from 180.06 to 220.07 s
in state 11: **1.25 Flip/s and 59.99 presentations/s**. The elapsed exclusive time
of the game thread is VU 52.36 %, IOP 41.25 %, GS frontend 3.77 % and EE 2.62 %. This
control executes more geometry and removes the earlier VU1 stalls/errors; the previous
1.00 Flip/s did not correspond to a correct scene. The cost of the profile is confirmed
with a second run of frame counters, and CPU is kept as the next
control to locate the distortions versus OpenGL.

The repetition counting only frames (`GOW_PERF_DIAG=frames`) is also in state
11 during the interval: eight complete windows from 180.05 to 220.06 s, with **1.275
Flip/s and 59.99 presentations/s**. That is 51 Flips in 40 s versus 50 with the full profile;
this small difference between runs does not allow measuring an exact overhead,
but it rules out that the optional instrumentation alone explains the low rate
observed. The zero times in this mode mean disabled counters,
not absence of work. The two logs are kept in `logs/vu1_efu_opcodes_perf/`
and `logs/vu1_efu_opcodes_frames/`.

The later 300 s CPU control also reaches state 11 and records no reserved
VU1 instructions. It keeps the same 64 Clip observations (30
pass, 34 discarded, all finite, no duplicate Y/Z). The late captures
still show disproportionate polygons and deformed surfaces; Kratos is not
recognizable. This failure also occurs with CPU, although the images from two
independent runs do not allow a per-pixel comparison nor rule out a
problem in the common GS frontend. The next control must repeat the same
commands and the same initial state on both backends. Private data:
`logs/vu1_efu_opcodes_cpu_game/`. The CI for commit `94c9389` finishes green.

### CPU state and GS command replay (2026-10-06)

To compare the same geometry and the same commands, `ps2recomp-gs-cpu-state.patch`
is added, separate from the earlier fixes. The original CPU backend did not
implement `GSBackendStateAccess`: saving only its VRAM lost the palette, texture
cache, transfer and readback. The export/import by
Taylor N. Albarnaz / LightVelox, SotC fork `ac9efa0` (GPL-3.0), is adapted, keeping the original cache
and the pending CT24 bytes of this port. The import validates before
modifying the destination; a page outside VRAM, a misaligned one, an invalid CT24 pixel
or a cursor outside the buffer are rejected.

Three regressions fail before the change (**540/543**): a CT24 transfer split
in two bytes with direct CPU and with a thread, palette/cache/readback preserved, and rejection
without modifying the state. After the fix **551/551** pass, including the eight
OpenGL tests. The cache probe uses TBP0 in 256 B blocks and checks a cached
texel different from the VRAM content; the fix does not invalidate that page to
hide differences. The previous audit verifies **35 patches and 79 sources**
exactly. The full build and the game control are verified below.

The later full build regenerates the 6418 units and finishes correctly;
the audit again compares the 79 sources with no differences. The native suite on
that runtime passes **551/551**. The final diagnostic starts the capture only
from EE draw/transfer commands, to avoid reading its variables from the
presentation thread. After that `src/` adjustment, the quick rebuild and the synthetic test
also pass. Absolute Unicode paths are verified on Windows.

The synthetic capture also matches real OpenGL: zero differing bytes with both
compute and the hardware option enabled. This small sample adds one compute
tile in both runs: it does not demonstrate that the second control uses hardware
rasterization. The logs are kept in `logs/gs_replay_synthetic_*`; the capture of the
real GoW segment is verified next.

The optional diagnostic in `src/gow_gs_replay.h` keeps the commands, MXCSR,
palette, transfer and initial/final VRAM. The standalone tool replays
that input on CPU and OpenGL and can locate the first divergence. It has a
size/duration limit and is not installed without `GOW_GS_REPLAY_TRACE`; the profile
removes that variable. The synthetic test verifies full capture, the parser and rejection
of truncation, and the CPU replay obtains **zero differing bytes**. The complete
status, usage and format limits are described in `rendering.md`.

The 200 s CPU control reaches state 11 and saves a complete command capture
of 23.89 MB. It replays **47,207 primitive submissions and two presentations** with zero
differing bytes versus the original final VRAM; palette,
transfer, pending CT24 bytes and readback also match. Replaying it again on CPU keeps
the two images with no differences. The initial texture page is invalidated,
so there is no old CPU page preventing the import of this input on the GPU.

Real OpenGL on the RX 5700 XT diverges for the first time at **record 577, draw
561**, a textured triangle with STQ and PSMT8: only three VRAM bytes differ at
that point. At the end **166,763 bytes differ with compute** and **164,227 with hardware
enabled**; the two presentations differ. The second pass mixes hardware
and compute (7,749 compute tiles versus 11,937 in the first), and the log confirms that
hardware is activated. This mixed run is not interpreted as exclusive use of
hardware rasterization. These exit code 1 results indicate a localized divergence,
not a parser failure or loss of the capture.

The 12 captures of the control still show huge polygons and stripes; Kratos
is not recognizable. The 64 Clip samples are still finite, with 30 accepted and 34
discarded, no duplicate Y/Z, and there are no reserved VU1 instructions. The replay
allows isolating precision/interpolation in GS; it does not demonstrate that these differences
explain all the deformation that also appears on CPU. The next step is to
check the effect of the host rounding mode and reduce the first differing draw
to a synthetic test. The original commands, coordinates, VRAM and images remain
only in `logs/gs_cpu_state_game/`, excluded from Git.

The CI for commit `681c257` passes both jobs. The capture and replay can now be
reproduced with the public tool, without publishing the original dumps.

### Isolation of SSE rounding in the CPU renderer (2026-10-06)

A dependency of the CPU backend on the producer's MXCSR mode is confirmed.
VU runs with round-toward-zero and sends GS commands within that execution;
the GS queue also keeps MXCSR. In the previous capture **46,950 of the 47,207
draws** arrive with that mode, including the first one that differs from OpenGL. A
synthetic probe of 24 gradient/UV/STQ combinations, direct/threaded CPU and four
modes fails in four gradient cases: 178 color bytes change per case.
UV/STQ in that sample do not change; that result is not generalized to all textures.

Real draw 561 is also isolated after replaying all its earlier commands.
The cached CPU page matches VRAM. Changing only the CPU mode changes
four bytes between round-to-nearest and toward zero; OpenGL compute differs by one byte
from CPU with round-to-nearest. This confirms the influence of MXCSR on that
draw, but a precision difference still remains and full parity is not certified.
The runs with hardware enabled in this small probe use
compute (129 tiles); the earlier full mixed control is still the one that
verifies hardware activation.

`ps2recomp-gs-cpu-rounding.patch` scopes the SSE mode on entering `Submit`: it uses
the usual round-to-nearest of the CPU rasterizer and restores the caller's on
exit. It keeps masks, FTZ/DAZ and flags; it does not change EE, FPU, IOP or VU
execution. It is a stabilization of the approximate renderer, not a claim that the current
interpolation has the exact precision of the PS2 GS. Two new regressions
check independence with direct and threaded CPU, and preservation of the MXCSR
control. Before the fix both fail (**543/545** without OpenGL); afterwards **553/553**
pass, including the eight OpenGL tests. The audit verifies **36 patches
and 79 sources** with no differences; the scripts and the configuration pass, with the
four known warnings.

The full build of the 36 patches finishes correctly and regenerates
the 6418 units. The later audit keeps the 79 exact sources and the native
suite passes **553/553**. The standalone 24-combination probe now passes all of them,
without altering the caller's mode; the capture tool is rebuilt and its
synthetic test also passes. The first 200 s control does not manage to start the
capture in state 11 and is inconclusive; it is not useful for comparing renderers.

After Claude's libm fix (`3f349b2`), the joint full build
again applies the 36 patches and runs the original double functions of
`sin`, `fabs` and `floor`. The audit verifies the 79 exact sources. The 330 s
CPU control reaches state 11 with `pending=0` and saves a complete capture of
**53,016 draws and three presentations**. Replaying it on CPU exactly reproduces
final VRAM, GS state and the presentations. Compute and the mixed pass diverge
first at a sprite (draw 510, record 520), with 917 differing bytes; at the end
they differ by 387,242 and 386,914 bytes respectively and in all three presentations.
The mixed pass activates hardware and runs 17,679 compute tiles, versus 42,001
in pure compute. These are comparisons of the same input; they are not FPS measurements.

The CPU images at 160.48 and 191.27 s show recognizable deck, cliffs, sky and rain,
clearly improving on the earlier pre-libm control. A later image
again shows distortions; neither Kratos nor a playable game is verified yet. The original
controls are kept in `logs/gs_camera_libm_cpu_game/`,
excluded from Git, and the investigation of the GS disagreements and the models continues.

The full analysis of the earlier capture verifies 141,396 finite vertices. There are
5,284 primitives with XYZ entirely zero, all with PSMT8 state; the Q values of
magnitude greater than `1e10` used by STQ appear only in 5,260 of these degenerate
primitives. This locates zero positions in the final GS output, but does not yet identify
their model context nor demonstrate that they must be drawn. 210 STQ vertices with
negative Q are also observed; their sign is not forced. The earlier observations
of Clip and of non-zero members remain valid for the contexts that were measured.

A private probe of 12 large synthetic triangles reproduces Z differences in
three cases with the current shader. A draft that keeps the reciprocal and the integer
numerators in double before obtaining float weights eliminates those differences
in all 12 cases and in the isolated real draw 561. That draft is not yet part of the
executable of that control; it later becomes the separate patch described
below.

### OpenGL weight precision and PACKED Z32 depth (2026-10-06)

`ps2recomp-gs-triangle-precision.patch` keeps the area reciprocal in double in
two free words of the primitive record. The common shader reconstructs the integer
numerators in double inside the GS domain and converts the weights to float
only after multiplying by that reciprocal, as the CPU does. `Submit` prepares primitives
with round-to-nearest SSE and restores the producer's controls. The 40-word
stride is kept and the generated hardware shader uses the same computation.
The regression compares full CPU/OpenGL VRAM for two large areas, two XYOFFSETs,
Z32/Z24 and four SSE modes, with compute and hardware allowed. It fails on the
earlier renderer (**553/554**) and passes with the fix (**554/554**). The twelve-case
private probe and the earlier isolated real triangle also stop differing. This improves
GS precision; it does not yet demonstrate an FPS gain nor eliminate all the
disagreements of the new capture.

`ps2recomp-gs-packed-depth.patch` fixes another bug before the backend: PACKED XYZ2
and XYZ3 converted their Z32 to float before storing it in `GSVertex.z` (double).
For example, `0x01000001` lost a bit and `0xFFFFFFFF` ended up written as
zero. Both paths convert directly to double; 24-bit XYZF, REGLIST and A+D
keep their behavior. Two regressions check four depths on
the native path and on the 33 byte splits of the packet, plus the tail of XYZ3
and XYZ2 with ADC without a premature draw. Before the fix both fail (**545/547**
without the OpenGL tests); afterwards **556/556** pass, including the nine OpenGL ones.
The integrated audit rebuilds **38 patches and 79 exact sources**;
configuration and 14 scripts pass with the four known warnings. The joint full
build finishes correctly, generates the 6418 units and keeps the
79 exact sources when audited after building. The game control follows.

The suite rebuilt after that build passes **556/556**. The public helper
builds the three tools and passes the synthetic capture/replay. CPU again reproduces
the 53,016 original draws with no differences. Compute ends with
386,873 differing bytes, versus 387,242 before; the mixed pass ends with
390,713, versus 386,914. Both keep the first feedback difference (917
bytes in sprite 510) and the three distinct presentations. The mix of hardware/compute
paths also changes (17,783 compute tiles versus 17,679 before): its final
variation is not attributed exclusively to precision nor is hardware parity
declared. The game's OpenGL control uses the complete executable with these changes.

The 330 s OpenGL control reaches state 11 with `pending=0` and `levelReady=1`,
on RX 5700 XT with hardware active and no fallback. The only gameplay PPM is
the one at 249.35 s: sky, rain and scenery in the background are recognized, but a large dark object
covers the center and Kratos is not identifiable. The earlier ones remain
in the menu or transition; they are not compared as the same phase as the CPU control at 160/191 s.
The 64 Clip samples keep the earlier results and the 66 late
buffers observed have non-zero first triplets. No reserved VU
instructions, invalid paths, cycles or truncations appear. A playable
game or an FPS improvement is still not certified.

The final review also protects the diagnostics against the GPU fallback: the queue
can destroy the OpenGL backend when replacing it with CPU, so the tools
and the new regression first check `Inner()` before querying `IsReady()`.
It does not change rasterization. The second full build required to publish
the test fix finishes correctly; the suite again passes **556/556**
and the later audit keeps the 79 exact sources.

The joint camera control shows 64 finite and complete Clips: 22 results
`0`, six `20` and 36 discards `80000000`, no duplicate Y/Z. The 544 late
`InitUNPACKData` probes have a non-zero first triplet. There are 10,520
degenerate primitives with all their XYZ zero; the huge S values appear exclusively in them,
with no non-finite XYZ. This does not support forcing positions to another value. No invalid
paths or cycles appear in the model/GROB samples. The dark planes at
240.85 s remain pending comparison with the same reference frame to
distinguish framing, occlusion and defective geometry.

The first difference of the new trace is reduced to a bilinear sprite that reads and
writes the same CT32 framebuffer. The isolated private probe reproduces the 917 bytes
in 476 pixels of 24 rows, concentrated next to page boundaries; repeating it gives the
same result. With nearest it does not differ, a prior TEXFLUSH keeps the difference,
and copying the source to a disjoint region eliminates it. This localizes a CPU
feedback/cache difference versus OpenGL. The PCSX2 reference explicitly distinguishes
these destination-read cases, but it does not demonstrate which of our outputs
reproduces the GS; parity is not forced by changing the filtering or by disabling the cache.

The case is further reduced to a 64×64 procedural CT32 texture: CPU and GPU
differ in 63 pixels (186 bytes), only in rows 32 and 33. Mutable CPU
differs equally from its disjoint-source control, while OpenGL matches
that control in both repetitions. The 53,248 bilinear neighbors of the real case
are also verified after CLAMP, including negatives remapped to zero.
The new public tool `tools/render/comparar_feedback_gs.cpp` reproduces
the synthetic case and is built with `scripts\compilar_replay_gs.cmd`; it uses no
game data. The next step requires a GS reference for this read-and-write
pattern before changing the cache policy.

### Review of Claude's work and visible comparison (2026-10-07)

The `E:\gowclaude\repo` checkout is clean at `1bdcd72` and matches the new
`origin/main`: seven commits after `1968f03`. They are separate changes for
getenv in hot loops, VU1 performance, scratchpad DMA, MPEG input, PCM diagnostics, IOP sound and memory card. The VU1 improvement has a benchmark
of the same frame and identical output: 775 to 503 ms; it is not equivalent to a 35 % improvement
in gameplay FPS. The scratchpad fix explains the Kratos bone palette
that reached VU1 as zero. Claude's local captures show Kratos,
enemies and HUD with recognizable shapes, and those of the save reach "Save Complete".
Their results and controls are in `pcsx2-comparison.md`, `performance-research.md`,
`movies-and-audio.md` and `memory-card.md`. The joint executable with the
two new GS fixes still needs to be verified; the earlier reference is kept as historical.

The review of `repetir_gs` also detects that CPU reserves rows of 640×512 and GPU
returns rows of 640×visible height. Comparing the raw vectors could flag a
size difference even though the visible pixels were equal, and the exporter
rejected the CPU PPM. `gs_frame_pixels.h` requires the backend's explicit layout,
extracts only the visible image and rejects truncated or ambiguous buffers. Eighteen
synthetic controls, including the real 64×64 `GSCpuBackend::Present` and the RGB PPM,
pass; the synthetic CPU capture/replay is again exact. The earlier
VRAM figures do not change; the raw presentation comparisons are
checked again with this tool before being considered image differences.
The full compute replay of the historical trace now confirms three distinct
visible images, and exports both CPU and GPU (four valid PPMs). CPU again
reproduces final VRAM exactly. This control uses batch mode: its 387,310
final bytes are not compared as if it were the earlier run with per-draw
synchronization. In batch mode the first differing VRAM check is labeled,
without presenting it as the position of the real first divergence.

The integration keeps Claude's seven patches before the two GS fixes:
**45 patches and 84 exact sources** when rebuilding and comparing the tree. The
full build regenerates the 6418 units and finishes correctly. Afterwards
**565/565 tests** pass, including the nine OpenGL ones and the new regressions for
SPR, MPEG, sound and card. The four rendering tools are rebuilt;
their 18 image controls, synthetic CPU capture/replay and procedural feedback probe
keep the expected results.

The joint 225 s OpenGL control loads a "Docks of Athens" game from
a **copy** of Claude's ECC card, with the original checked by SHA256
as unchanged. RX 5700 XT uses hardware with no fallback. The last 512×448 capture
shows Kratos at the save point, the HUD and the R2 prompt; it reaches
state 11 with no pending load. It does not yet prove combat, sustained performance
or all scenarios. The 128 Clip samples between menu and game are finite
and complete; the 144 late `InitUNPACKData` probes have a non-zero first
triplet. The 64 game model contexts contain no invalid addresses,
cycles or truncations, and no reserved VU instructions are recorded.
The SDK and hardware treemap and the three READMEs now reflect these controls:
MPEG/IPU become partial because of the decoded intro; card and audio detail what was
verified and what is missing. GS stays partial because of the CPU/OpenGL differences still
open. The 65.4 % of libraries and 60.5 % of hardware represent the weightings
of the map, not the percentage of the game completed nor its speed.

The hardware replay with three passes in a single GL instance certifies the
restoration before comparing: initial VRAM, CLUT/CBP, transfers and portable
state exact in all three; initial/final CPU with exact cache and CPU versus the
final capture with no differences. The two hot passes both use 373 batches,
33,445 primitives and zero compute tiles, but differ from each other in **4617 bytes of
VRAM** and in **344/298/296 bytes of the three visible images**. It is no longer a matter of
comparing different buffer sizes. The cold pass mixes compute during the
compilation of variants, so it is not used as a control of the same path.
The investigation of the VRAM access order and of the upload buffers continues;
these replay times are not a measurement of the game's FPS either.

The new `repetir_gs --repeticiones N` brings that control to the public tool. It reuses
the same instances, checks the complete restoration and compares VRAM, state
and all visible frames between consecutive passes. The raster deltas
distinguish the passes that still use compute while they compile variants. The
output directory as the third argument is also fixed, and invalid
options and export failures are detected, keeping the exit codes.
The complete helper and its 18 controls pass; synthetic CPU ×3, compute ×3 and
hardware ×8 keep parity and stability. CPU on the first real frame ×3 is
exact and exports six valid PPMs; hardware ×8 detects 545 differing VRAM bytes and 358 visible ones
between the last two, both with zero compute tiles.

The search with valid CPU cuts narrows the case to the second feedback sprite:
519 (before) and 520 (first sprite) are repeatable; when 521 is included, 36 variable
bytes appear with 3 batches, 192 primitives and zero compute tiles. The restoration and the
final portable state remain exact. The 917-byte CPU/GPU difference of the first
sprite is stable and is distinguished from this variation. Zero reuses of the upload
ring in the capture rule out that recycling as the cause; a reference is still needed
to decide the correct treatment of destination reads.

Four procedural captures also check initial states that the simple control did not
cover: two pending CT24 bytes, local read with cursor 7 and nine
pending bytes, a fresh cache page and a page with one stale byte. All four
are exact on CPU ×3, including the visible image; the three compatible with GPU
are exact on compute ×3 and the stale one is rejected with code 2 before creating GL.
The directory as argument 3 exports the correct images; a file used
as a directory and nine variants of invalid options also return 2.

The new generator `tools/render/generar_feedback_gs.cpp` reduces the instability
to two sprites over procedural 64×416 texels, with no game files. It generates
bilinear feedback, disjoint source and nearest feedback, verifying the 27,588
copied neighbors. The helper now rebuilds five tools, passes the 18
image controls and replays the three captures on CPU ×3 with End, VRAM and frame
exact. On RX 5700 XT, hardware ×12 of disjoint source and nearest keeps parity
and stability; bilinear feedback returns 1 and varies between hardware passes with
two batches, two primitives and zero compute tiles (19 VRAM/visible bytes in 4→5 and
34 in 7→8). Restoration and final portable state remain exact. This way the
problem can be reproduced independently of the game before choosing a fix;
the renderer policy is not changed yet nor is an FPS improvement attributed.

The independent PCSX2 v2.8.2 software reference uncovers another problem:
the bilinear filter rounded at the end, while the reference uses four-bit
fractions and truncates each stage. `ps2recomp-gs-bilinear-precision.patch` changes
only GS CPU/GLSL and adds three regressions with an external RGBA fingerprint of 256
UV fractions, also for STQ and four SSE modes. All three fail before the
fix and afterwards pass **568/568**, including ten real OpenGL ones. The literal
bilinear control of an earlier test is adjusted to the documented truncation;
nearest does not change. The full build of the 6418 units finishes well
and the rebuilt tree matches in its **46 patches and 84 sources**.

The helper rebuilds six tools and keeps the 18 image controls
and the three exact CPU ×3 replays. `generar_feedback_gs --pcsx2` adds
procedural GS freeze v8/PATH3 export; the new test checks the initial
freeze and replays the GIF commands with exact final VRAM in the three cases.
The exported `.gs` files are identical by SHA256 to those used in the isolated
reference, with no BIOS or game data. The comparison with PCSX2 software is
exact for nearest and, after the fix, for bilinear with disjoint source.
Details and sources are in [rendering.md](rendering.md).

On RX 5700 XT, hardware ×12 is still exact and stable for disjoint source and nearest.
Bilinear feedback still returns 1 and varies: the last two passes differ in
89 bytes of VRAM and visible image, with two batches, two primitives, zero
compute tiles and equal final portable state. The cache policy is not changed nor
is an FPS improvement attributed. The treemap incorporates the verified precision
and keeps GS/textures as partial and their earlier coverage percentages.

The final 330 s OpenGL control loads "Docks of Athens" from a private copy
of the ECC card, whose original remains identical by SHA256. The 14 captures are
distinct and valid; the last shows Kratos, the HUD, the save point and R2,
in state 11 with no pending load. The 128 Clip samples are finite and complete;
the 352 late `InitUNPACKData` probes have a non-zero first triplet,
and the 192 game context samples contain no invalid pointers,
cycles or truncations. No reserved VU instructions appear. It does not yet prove
combat nor sustained FPS. The keypresses of the private script are delayed:
the first 225 s control lost the initial Start and ended up in the new-game
intro, so it is not used as evidence of a saved-game load.

The next reference control confirms a different bug with nearest STQ:
the direct cast to integer loses the sign of negative fractions. The new
`ps2recomp-gs-nearest-stq.patch` first converts to 16.16 and extracts the signed
integer part, both on CPU and in GLSL. Two procedural 16×16 matrices compare
negative texel quarters and the limits close to zero: the original differs
from PCSX2 software in 624 RGBA bytes/156 pixels in each one. Using only
`floor` fails on the values that lose the fraction during the fixed-point conversion.
The three new regressions fail before and pass after for sprites/triangles,
Q=1/2 and the four SSE modes. The OpenGL paths are also confirmed by counters.

The full build again regenerates the 6418 units and finishes well;
**47 patches and 84 sources** match, and the later suite passes **571/571** with
eleven real OpenGL controls. The helper builds seven tools: it keeps
the 18 image controls and adds a public generator of the three oracles.
Their `.gs` files are identical by SHA256 to those used in PCSX2 software; their CPU
matrices match byte by byte with the three external RGBA references. The six
patterns pass freeze/GIF/End and CPU ×3. Hardware ×8 of the three oracles is
exact and stable, with 256 primitives and zero compute tiles in the hot passes.
The three earlier feedback dumps keep their bytes. The treemap reflects
both sampling fixes without changing the partial coverage nor attributing FPS.

The final 330 s OpenGL control with this executable again loads the private
copy of "Docks of Athens", with hardware active and the original card intact.
The 14 captures are distinct; the last shows Kratos, HUD, R2 and save
point in state 11 with no pending load. 128 finite/complete Clip samples,
352 non-zero late first triplets and 192 game contexts with no invalid pointers,
cycles or truncations are kept. No reserved VU is recorded. Combat, sustained
performance and bilinear feedback remain pending.

### GS feedback: separate controls and optional protected source (October 7)

Opus's experimental VU1 branch is kept without integrating it or modifying EE/IOP.
The GS generator adds six controls to the three earlier procedural patterns:
TEXFLUSH or SCISSOR1 outside the drawn area between two sprites. All nine pass
freeze/GIF/End and CPU ×3. The dump validation now also checks the complete
freeze and the three privileged blocks, to detect changes in PMODE,
DISPLAY, contexts, GIF queues and Q that would not alter the final VRAM.

PCSX2 software v2.8.2 keeps a common source in `self`/`self_texflush`; changing
SCISSOR1 forces two draws and renews the source. The sources of both draws are
verified against the pattern and the first framebuffer, respectively. The separated
result differs in 1238 RGB bytes, demonstrating that copying per primitive is not equivalent
to freezing an entire batch. This control does not certify the real GS pipeline.

The new patch `ps2recomp-gs-feedback-snapshot.patch` keeps the source before
each primitive with overlapping read/write, using the shadow pages of the
OpenGL backend and the epoch prior to the copy. It is optional, disabled by
default, and is selected with `PS2X_GS_FEEDBACK_SNAPSHOT=1` in the executable or
`--snapshot-feedback` in the replay tool. The CPU renderer keeps
its one-page 8 KiB cache; the tool still reports its differences.

Before the change, the new hardware regression fails both by RGB and by
variation between passes (572/573); compute already passes that pattern. Afterwards it passes
573/573 with thirteen real OpenGL controls. Both paths reproduce the external fingerprint
of the separated case, keep all the restored VRAM stable, preserve alpha
and the disjoint source and pass the point/triangle controls against the disjoint
CPU copy. The experimental mode is not yet enabled by default and
does not demonstrate an FPS increase. The treemap keeps partial coverage and weights.

The full build regenerates the 6418 units and finishes with code 0.
The later audit confirms the 48 patches/84 sources, and the suite again
passes 573/573. The helper builds seven tools and validates the 18 image controls
and the twelve freeze/GIF/End patterns with CPU ×3; six damaged dumps are
rejected. The three original dumps remain identical by SHA256.

The 72 optional replay passes (compute/hardware × three patterns ×12)
keep VRAM, state and visible frame identical between restorations and match
the three RGB reference regions. Hot hardware confirms two
primitives and zero compute tiles. The separated case keeps its exit code 1 because of the
4557 bytes that differ from the CPU cache; nearest and disjoint source keep
exit 0. The duplicate option and its use in CPU mode are also rejected.

The game control with the option enabled lasts 390 s and loads a private copy
of Claude's card, whose original keeps its SHA256. The fifteen captures
are distinct and valid (512×448); the last shows Kratos, the save point
and R2, in state 11 with no pending load and with hardware active. The 128 Clip
samples are finite and complete, the 416 late first triplets of
`InitUNPACKData` are non-zero and the 192 game contexts present no invalid
pointers, cycles or truncations. No reserved VU is recorded. The health bar
does not appear in this final capture; combat and sustained FPS remain unchecked.
The first 330 s script lost the "Load" selection and reached the intro of a
new game: it is not used as evidence of a saved-game load. Only the keypresses
of the private control were delayed to repeat it.

### Bilinear STQ: convert before subtracting half a texel (October 7)

The next procedural comparison with PCSX2 v2.8.2 software confirms a different
precision bug: bilinear subtracted half a texel from the float coordinate before
quantizing it, even though nearest already used 16.16. A 16×16 matrix with disjoint 4×4
RGBA texels and values close to the signed limits differs in 611 RGBA
bytes/156 pixels. The RGB/alpha input of the 16 texels and freeze/GIF/End are
checked exact before attributing the difference to the filter.

`ps2recomp-gs-bilinear-stq.patch` performs the conversion before the half texel
on CPU and GLSL. The three new regressions fail before (573/576) and pass
after (576/576, fourteen real OpenGL controls). They use the external RGBA fingerprint,
without repeating the filter formula in the test, for sprites/triangles, Q=1/2
and four SSE modes. Hardware has to rasterize at least one matrix without
compute tiles. The public generator now also exports the bilinear
STQ control; the details and the reference are in [rendering.md](rendering.md).

The full build regenerates the 6418 units and finishes with code 0.
The audit confirms 49 patches/84 sources and the later suite passes 576/576.
The helper builds seven tools and validates thirteen freeze/GIF/End patterns
with CPU ×3, in addition to the 18 image controls and six corruptions rejected.
The four dumps are identical to those run in PCSX2 by SHA256 and their CPU
matrices match the 1024 RGBA bytes of each reference.

Compute ×8 and hardware ×8 of the new pattern keep VRAM, state and visible
frame between restorations, with exact external RGB. The eight fast passes
selecting hardware still used compute while its shader compiled.
The new option `--pausa-ms 1000` lets that compilation finish between passes
without changing the comparisons: seven of the eight repetitions use hardware
with 256 primitives and zero compute tiles. Nine invalid arguments are rejected;
CPU ×2 with pause keeps exit 0 and optional feedback keeps its exit 1.
The diagnostic wait does not intervene in the game nor measure performance.

The final 510 s control uses OpenGL, skips FMV and keeps the experimental snapshot
disabled. It loads a private copy of Claude's card; the original
keeps its SHA256. The sixteen 512×448 images are distinct and valid.
The last shows Kratos during an attack, with HUD, weapon trails, R2 and
save point, in state 11 with no pending load. The three
square presses are received; the 128 Clip samples are finite/complete, the
768 late triplets are non-zero and the 192 game contexts present no
invalid pointers, cycles or truncations. No reserved VU appears. The attack
image is verified; combat against enemies and sustained performance
remain pending. The architecture documentation now links the list
of patches in `scripts/compilar.ps1`, to avoid another incomplete manual list.

### Regional pages: reduce synchronizations without losing feedback (October 7)

`ps2recomp-gs-region-pages.patch` bounds the reads of REGION_CLAMP and
REGION_REPEAT and stores both U/V extremes in the bitset key. In the
procedural controls, three disjoint sources go from three batches/two flushes
to one/zero; the fourth read of a written page keeps two/one.
The complete 4 MiB are compared with CPU across the 13 PSMs, with colored CSM2
palettes, nearest/bilinear and bitset cache enabled/disabled. Changing
only MIN in REGION_CLAMP proves that the key is renewed correctly.

The edge controls include misaligned TBP bases, page crossings,
VRAM wraparound and non-zero masks, with and without snapshot. They keep the real
synchronizations and require effective hardware without compute tiles.
There are 1184 combinations between both paths. The new batch regressions
fail before; the isolated controls with the machine free rule out the shader
timeouts exhausted during a first run alongside Claude's
build. The details are in [rendering.md](rendering.md).

The full build finishes with code 0; 50 patches/84 sources match
and the final suite passes 580/580, with eighteen OpenGL controls. The seven
tools pass 18 image controls and thirteen freeze/GIF/End with CPU ×3;
the six damaged dumps are still rejected. The reduction in submissions is a
synthetic result; its effect on FPS and the check of the real GS cache are still to be done.

The later control lasts 510 s on OpenGL, with FMV skipped and experimental snapshot
disabled. It loads a private copy of the card, whose original
keeps its SHA256. The sixteen 512×448 captures are distinct; the last
shows Kratos attacking with HUD, weapon trails, R2 and the save point,
in state 11 with no pending load and with hardware active. 128
finite/complete Clip samples, 736 non-zero late triplets and 192 contexts
with no invalid pointers, cycles or truncations are kept. No reserved VU appears.
This verifies the image of an attack; combat against enemies and sustained FPS
remain pending.

### Late GS capture from TEXFLUSH (October 7)

The diagnostic allows choosing the wait and duration with `GOW_GS_REPLAY_AFTER` and
`GOW_GS_REPLAY_SECONDS`. `GOW_GS_REPLAY_TEXFLUSH=1` starts the segment after the
game's first TEXFLUSH in state 11 that meets the deadline. It does not add an
invalidation: it keeps the earlier commands in the initial state and the
later ones in the trace. Without a capture file the wrapper is not installed;
invalid options are rejected before opening it. The profile clears the
four variables. Values and limits: [controls-and-menu-tests.md](controls-and-menu-tests.md).

The regression fails with the earlier start behavior and passes with the
boundary. It checks old cache not cleared too early, menu TEXFLUSH
and one before the deadline, presentation without a start, pending CT24 bytes, earlier
commands excluded from the trace and exact replay of all the final VRAM.
The test closes its readers before deleting the files on Windows. The
helper now also rejects negative process errors: `ERRORLEVEL 1`
alone let the abnormal termination of a first version of this test slip through.
CI builds **and runs** the CPU control without the game or OpenGL.

After `2_recompilar_rapido.cmd`, the 520 s CPU control loads a private copy
of Claude's card, with FMV skipped. The original keeps its SHA256.
The sixteen images are distinct; the last shows Kratos attacking
next to the save point, with HUD and trails. Final state 11 with no pending
load, 128 finite/complete Clips, 368 non-zero late triplets and 192
contexts with no invalid pointers, cycles or truncations; zero reserved VU.

With a wait of 470 s and a duration of 3 s, the start occurs at 470.287 s from the backend,
after TEXFLUSH. The complete file takes 54,535,037 bytes: 146,015
records, 145,469 draws and two presentations. CPU ×3 reproduces the End, all
the VRAM, the state and both images exactly, between passes and against the
original. The initial page is invalidated and allows importing the state on GPU.

Compute still diverges: the first draw is a 32×416 PSMCT32 UV sprite,
with 1874 differing bytes from address 65540. The first divergence is
at record 3; the final ones and the two presentations differ from CPU. The
three passes keep the raster counters but vary some bytes
of VRAM, and one transition also changes the first visible frame. This trace
bounds a GS bug in a late scene; it does not establish GPU parity nor FPS.
The game data and the images remain under `logs/`, excluded from Git.

The sprite was reduced to a local one-draw trace: TBP=0/FBP=0, TBW=FBW=8,
CLAMP on both axes, bilinear, declared 1024×1024 texture and alpha mask.
CPU ×3 is exact. Compute ×3, with and without feedback snapshot, keeps
the same 1874-byte difference and remains stable between passes. The
reduced presentation stays identical because that write does not change the current
visible buffer. Protecting the source of the whole primitive does not solve this case;
the page read order and the 8 KiB CPU cache remain to be contrasted.

### Intermediate OpenGL variation controls (October 7)

`repetir_gs --checkpoints-sync --repeticiones N` compares fingerprints of the 4 MiB
at Flush, Sync, Present and End. The report identifies the first control that
varies between passes. The chosen commands already drain batches; TEXFLUSH does not
do so on GPU and is left out of this probe. The exact comparison
of End, state and images is kept. The history is limited to 4096 controls, with
rejection before the replay. It adds readback, does not measure FPS nor certify intermediate
byte-for-byte equality when the fingerprints match.

The public CLI passes five invalid arguments, three CPU runs and the
rejection of the excess before drawing. A C++ regression uses the real
comparison of the tool: an intermediate difference must fail even if End is
identical. It also verifies count and metadata. Both run in CI
without game data; the Windows helper builds and runs the C++ regression.

The real CPU ×3 segment passes its thirteen controls and keeps exact final and
visible equality. Compute ×3 with snapshot shows the first variable control
at the Flush of record 73,288, after 73,003 draws; eight controls vary,
the two visible images between passes remain identical and the counters
are 632 batches/99,402 primitives/53,757 tiles in the three passes. The consecutive GPU Ends
differ in 4296 and 3977 bytes. It does not establish stability of the whole
VRAM nor parity with CPU. The control reduced to the first sprite keeps
the 1874-byte difference also on hot hardware, with zero compute
tiles; that isolated draw remains stable between passes.
The private control that removes the CPU read cache alters 34,262
bytes of the End of that sprite and does not match OpenGL either: it was not incorporated into the
runtime. Next step: reduce the batch preceding the first variable Flush and
contrast it with protected sources and VRAM formats, keeping CPU.

### Color and depth dependency in OpenGL batches (October 7)

The reduction through CPU-derived Ends narrows the observed variation to
the prefixes 68,897/68,898: the first stays stable over five passes and the
second changes 64–128 bytes between some passes. The new sprite belongs
to a pair that uses FBP=ZBP=320, FBW=1, PSMCT24/PSMZ24 and Z enabled. Although
the XY rectangles are disjoint, color and Z reinterpret the same memory.
Completing the batch before the second sprite eliminates the variation in eight
passes. This bisection does not certify monotonicity nor a global first failure.

The procedural case, independent of the game, differs from CPU in 6144 bytes
before the change and matches in the 4 MiB after. The new patch
`ps2recomp-gs-target-alias.patch` splits batches when color and
depth pages cross between primitives. It keeps the CPU renderer and is applied
after the fifty earlier patches. The detection is conservative;
the internal alias of a single primitive remains outside the fix.

After the full official build (code 0), the integrated backend repeats the
real segment on compute four times with snapshot and four without it: thirteen stable controls, End, state and both images exactly
equal between passes. There are 648 batches versus the earlier 632 and
99,402 primitives/53,757 tiles are kept. It still differs from CPU in 739,502
bytes and the two presentations. It establishes neither parity nor FPS improvements.

Integrated validation: **582/582** native tests, including twenty OpenGL
tests; the new controls cover shared CT24/Z24 and CT32/Z32, read-only
Z, inactive Z and disjoint buffers, on compute and effective hardware.
The GS tools and the CLI argument/control tests also pass.
The default mode keeps thirteen stable controls just like the snapshot.

### Integration of PRs #12, #17 and #18 (October 8)

#18 (`bfee1bb`) contains all the commits of #17 (`b3d8cd6`). Its two VU1 patches
are kept after the 51 current ones, including the GS color/Z alias
fix. The merge of #12 (`927c7b93`) keeps the current versions
of DMA, VIF DIRECT, EE branches, VU0, FPU and queue jump: they were already
incorporated in `ps2recomp-vu0-macro.patch`, `ps2recomp-vif-direct.patch` and
`ps2recomp-ee-fixes.patch`; old copies are not added.

The new piece of #12 is `ps2recomp-vu1-budget-diag.patch`, adapted to
`StepContext` from #18. `GOW_VU1_BUDGET_DIAG=1` reports budget cuts
with limited messages; it does not increase the 65536 cycles nor modify the program.
The regression covers short/zero budget, resumption up to E and reset, with
direct writes and with queues. The generator requires the user's local data
and the game-derived C++ is never published.

The review detected a persistent-flags bug in #17/#18: MADD with a
subnormal product and a normal sum gave `status=0x000` with direct writes
and `0x140` with queues. `ps2recomp-vu1-sticky-preserve.patch` preserves the flags
of the product both in the interpreter and in the compiled pairs/blocks.
The new test also verifies that a later reader microprogram
observes them. The analysis of temporary MAC flags that nobody reads is kept.

Integrated result: **55 patches** apply in order and their **85 sources**
compared match the compiled runtime; `scripts\2_compilar.cmd`
finishes with code 0 and updates the executable. The native suite passes
**565/565**, with no failures excluded, and the generator passes **60 procedural cases**
with 139 compiled pairs and 22 real interpreted ones. CI receives the same
generator control; the earlier GS validation also passed twenty optional
OpenGL tests. Two historical VIF chains from the game (`vif_pcsx2_inicio2`
and `vif_port_480s`) produce exactly equal images with queues and
direct writes in the integrated runtime. This comparison establishes neither
parity with PCSX2 nor the FPS of a game; the historical images are
not an equivalent reference for the new arithmetic mode.

The official build uses the interpreter if no VU1 C++ derived from
local microprograms is linked. The compiled infrastructure is verified
with procedural code; it still needs to be integrated into the local build
flow and the performance measurements repeated with the corrected flags.

### Coordinate aliasing by width and VRAM wraparound (October 8)

The next procedural control detects a risk different from the color/Z crossing:
with FBW=1, `(0,32)` and `(64,0)` of CT32 point to the same pixel. An address
is also repeated when exceeding the 512 pages of the 4 MiB. Compute sorts
primitives by XY within a tile; the hardware interlock is also applied
to the XY pixel. Neither ordered those two different XYs of the same destination.

A batch with 64 sprites on the first XY and another on its alias loses
6144 bytes in CT32/CT24 or 8192 in CT16/CT16S versus CPU. The controls
with disjoint pages and repeated coordinates within the width match.
The base FBP=511 additionally allows checking the crossing of the end of VRAM.

`ps2recomp-gs-coordinate-alias.patch`, applied at the end of the 55 earlier ones,
keeps the coordinate risk in color and depth separate.
It completes the batch if the current destination shares pages with an earlier one and
any exceeds the row width or the 512 logical pages. The FBP base by
itself does not trigger the risk. The detection is conservative per page: two
writes outside the normal domain can split batches even if their pixels
are different. It does not order internal aliases of a single primitive.

The two optional regressions cover four color formats, both
directions of the alias, VRAM wraparound, Z32/Z16 with disjoint color, inactive Z
and controls that keep a single batch. They compare the 4 MiB and check
the rasterization counters, without accepting a CPU fallback as OpenGL.
The candidate passes **587/587** native tests, including 22 real OpenGL ones.
Both regressions fail, also by VRAM bytes, when linked with
the earlier backend and the same rest of the runtime.

The full official build finishes with code 0. The **56 patches**
apply in order and the **85 sources** audited match. The CPU ×2
replay keeps the thirteen controls, End and both images exact. Compute
×4 without snapshot and ×4 with it are also stable; the 4 MiB of End and
the images match byte for byte with the earlier backend. It adds no batches
to that trace: it keeps 648, with 99,402 primitives/53,757 tiles and the same
CLUT and synchronization counters. It still differs from CPU in 739,502
bytes and two presentations; this fix establishes neither parity nor more FPS.

The control of the GS56 executable lasts 510 s, with OpenGL, FMV skipped, direct
VU1 by default and a private copy of the saved card. The 16 512×448
images are distinct; Kratos is seen with correct shape, attacks and
HUD with green/blue bars, 87 orbs and R2 visible. The final state is 11 with no pending
load. There are 128 finite/complete Clip samples, 848 non-zero late
triplets and 192 contexts with no errors; no reserved VU is recorded. The
original card keeps its SHA256. These captures do not certify full
combat nor sustained FPS.

### Retained read-only Z trial (October 8)

`writePages` includes the pages queried by the Z test even with
ZMASK=1. A local trial separated reads and writes so that texture/CLUT
and depth could share a batch without modifying those pages.
Its procedural controls passed on CPU, compute and hardware, including
uploads over Z and writes before/after readers.

On the real trace, the trial reduces 648 to 543 batches and 53,757 to 46,543 compute
tiles, keeping 99,402 primitives. Eight compute passes and eight
hardware passes with snapshot keep the earlier End and images. These
counters do not measure FPS nor certify the physical PS2 cache.

However, the prototype without snapshot varied 200 final bytes and one
presentation in one of 24 passes. Limiting it to snapshot and keeping the earlier
cuts in the usual mode was not enough either: another long test
varied 128 final bytes and one presentation, from record 73,326,
Flush after 73,036 submissions. **The complete optimization was withdrawn from the
published chain**, including its two tests; code and data remain in
`logs/`, excluded from Git. No FPS improvement is announced for this trial.

The long control of the real GS56 also varies one presentation (190 bytes)
in one of 24 passes; its first differing control is at record 36,
Flush after 33 submissions. The End and the final state are identical in all 24.
There is bilinear feedback on the framebuffer in the segments investigated,
but the exact cause is still pending. Four equal passes do not
certify stability. The reference preceding the long control
did not yet include the coordinate alias patch; here GS56 is linked.

### Hardware STQ control and VU1 integration (October 8)

The bilinear STQ control finished its 16 matrices before the asynchronous
shader compiler offered hardware. The pixels and SSE
were correct, but the hardware control failed. The new patch
`ps2recomp-gs-stq-hardware-test.patch` repeats the matrices for a
maximum of 12 s, keeping all the RGBA oracles, SSE controls and the
requirement of hardware with no compute tiles. A result correct only on
compute still fails; the production renderer is not modified.

The seven finished commits of Opus up to `e507ac6` were integrated,
with their compiled blocks, helpers, XGKICK and optional VU1 linking.
The final official build uses its 501 local micromemories,
without modifying or publishing that data.

The final official build finishes with code 0: **59 patches** in
order and **87 sources** (`cpp/h/inl`) audited with no differences against the
runtime. It passes **587/587** native tests, with **22 effective
OpenGL controls**, **60 exact VU1 cases** (139 compiled pairs and 22
interpreted), PAD2 and the configuration, scripts, GIF and
VIF selection controls. Opus's FPS measurement is kept as the result
of its segment, without extrapolating it to the whole game.

### Scheduler integration and game control (October 8)

PR #20's `main`, `9f0ebc4`, is incorporated, keeping GS56, the hardware STQ test and the
compiled VU1. The official build finishes with code 0, with
**60 patches**, the 501 local micromemories and an executable of 67,710,976 bytes.
The **87 modified sources** (`cpp/h/inl`) match the ordered application
of the patches on the pinned commit. **587/587** native tests pass, with
**22 real OpenGL controls**, the **60 exact VU1 cases** (139 compiled pairs
and 22 interpreted), PAD2, configuration, PowerShell syntax, GIF inspector
(8 cases) and VIF selection (11 cases).

A clean 430 s control, with no geometry diagnostics and with a private copy of
the card, produces **15 distinct 512×448 captures**. The last one, at 360.10 s
of the controller clock, shows Kratos and several enemies on the ship, rain,
background and HUD; no stretched polygons are observed in that capture. The state is
11, with no pending load and the level ready. OpenGL uses hardware and no reserved
VU appears. The original card keeps its SHA256. The earlier test of the
59-patch executable also shows that scene with compiled VU1.

An earlier FPS comparison is discarded: it coincided with another build and
its windows corresponded to state 3 with pending load. The new selector
`resumir.py --partida`, covered by seven tests, requires loaded-game reports on both sides of
the windows without equating the profile and controller
clocks. These controls verify integration and the observed scene; they still
do not certify sustained performance, full combat nor faithful GS feedback.

### Validation of 61 patches and feedback reduction (October 8)

The official build of `main` at `63c8a02` finishes with code 0, with
**61 patches**, 501 local micromemories and an executable of 67,710,976 bytes.
The **87 sources** audited match the published chain. FINISH remains
synchronous by default; the test with retained backend passes in default mode and in
the optional asynchronous mode. PAD2 and the **60 exact VU1 cases** also pass,
with 139 compiled pairs and 22 interpreted.

The first local OpenGL control passes 584/587: three cases match in pixels
but do not meet their effective hardware requirement. That record is kept.
A later repetition passes **587/587**, including the **22 OpenGL tests**;
its variants compile in under two seconds. The deadlines are not extended
nor is the renderer changed to accept the first failure. The cause of the
intermittent hardware failure has not yet been demonstrated.

`repetir_gs --hasta-registro R` allows stopping a trace at an already recorded Flush, Sync,
Present or End. It compares the 4 MiB and the portable CPU/candidate state exactly
when the prefix ends, without validating the original End when it is not
executed. It rejects other commands and indices outside the file before creating the
backend. The limit of 4096 controls applies to the prefix. The CLI controls
cover eleven invalid arguments, boundaries, an altered End and limits.

The prefix up to Flush **36**, after **33 submissions**, reproduces the
CPU reference and is identical on CPU ×2. 64 passes are done per policy,
with exact initial restoration, the same 33 batches and synchronized readback:

| Path | Consecutive comparisons of the same path | Comparisons with different VRAM |
|---|---:|---:|
| Usual compute | 63 | 4 (59 or 890 bytes) |
| Compute with snapshot | 63 | 0 |
| Usual hardware, shaders ready | 61 | 61 |
| Hardware with snapshot, shaders ready | 48 | 0 |

The compute passes have 544 primitives/1760 tiles; those of hot hardware,
544 primitives/zero tiles. The first 2 usual hardware passes and the
first 15 with snapshot use compute while shaders compile; they are
excluded from those two rows, together with the transition to hardware. The policies
with snapshot keep **515,877 bytes different
from CPU**, so they still return 1: stability does not imply parity nor
fidelity to the PS2 cache. In this prefix no frame is presented and the
readbacks/pauses do not measure FPS. The cut reduces the feedback investigation
from 146,015 records to 36, without publishing the trace nor altering the usual mode.

### VIF1/timers and VU1 SIMD integrated (October 8)

The two finished commits of PR #21 (`8841ef0`, `b280247`) and
the first SIMD commit of PR #23 (`5e09b12`) are integrated, keeping their authors and
history. The documentation and patch-order conflicts are resolved
by including the three changes. The review detects and fixes in `247a9b3` an
underflow flag lost by SIMD ADD/SUB when the PC uses FTZ/DAZ: rounded
zero does not imply exact cancellation. The targeted regression fails before
the fix with `status=1c0/c0` and passes after; the register values
already matched, so checking only the image did not detect this failure.

The official build of `247a9b3` finishes with code 0: **64 patches**,
501 local micromemories and an executable of **70,182,400 bytes**, SHA256
`82ECCA22A4F4600FA60DB255D45176178971D60FF94382CC12D2E08BFC807074`.
The **87 sources** audited match the chain. **587/587 native tests**
pass, the **22 effective OpenGL ones**, the **60 VU1 cases**, **100,800 random
FMAC cases and 2,016 targeted FTZ/DAZ ones**, PAD2 and both FINISH controls.
The FMAC test uses 359,856 compiled pairs with no fallback to the interpreter.
Configuration and PowerShell syntax are also correct.

A clean 180.55 s profile, with synchronous FINISH, OpenGL renderer and a private
copy of the card, observes no compilers nor another game in its per-second
monitoring. Twelve complete loaded-game windows (60.04 s between
103.06 and 163.12 on the profile clock) measure **7.58 vid::Flip/s**, with **57.71
presentations/s**. The exclusive game-thread times are VU **43.24 %**,
GS **38.20 %** (including waits), EE **12.20 %** and IOP **6.36 %**. The original
card keeps its SHA256. No gain is attributed to SSE by comparing
this single pass with another scene; a controlled comparison is still missing, as is separating
the GS work from its waits. The treemap reflects SIMD and the feedback
reduction, keeping GS and VIF1/VU1 partial in all three languages.

During these tests Opus adds `754c970` (compiled DIV) to PR #23 and opens
the lazy-flags branch. **Those later changes are not yet in
this executable**: they require their own review and integration. Opus's working
tree is not altered nor is it announced that all of PR #23 is applied.

The clean control of the same 64-patch executable lasts 430 s and keeps
**15 distinct 512×448 captures**. The last one, at **360.14 s** of the
controller clock, shows Kratos, several enemies, ship, rain, background and HUD, with no
visible stretched polygons. It remains in state 11, `pending=0`, `levelReady=1`,
with hardware active and no reserved VU instructions in the log.
The original card keeps its SHA256; a private copy is used.
It is a check of that scene, with FMV skipped, and verifying
full combat, other scenarios and sustained performance remains pending.

### OpenGL profiler attribution (October 8)

The 180 s GPU diagnostic on the 64-patch executable discovers that
the hardware batches print FBP, flags and primitives as zero. One query
spans several shader variants without attaching their state; those lines do not
allow identifying the destination that consumes time. In compute, the last
batch of the 4096-query threshold also loses data when the queue is resolved.
This run synchronizes timestamps and adds records: it does not measure clean FPS.

`ps2recomp-gs-hardware-profile.patch` attributes a query to each hardware
variant and attaches the compute data before resolving the queries.
The CPU work of preparing that data stays outside the GPU interval. Without
`PS2X_GS_GPU_PROF=1`, the queries remain disabled. Two real OpenGL
regressions fail with the earlier backend and pass with the corrected draft:
two variants within the same batch and the 4096-compute-batch boundary.
In both cases they keep the 4 MiB exactly against CPU and require the effective
GPU path. The integrated official build is validated separately.

The official build of `23fbce4` finishes with code 0: **65 patches**,
501 local micromemories and an executable of **70,182,912 bytes**, SHA256
`6D7BA3034436D28141D4F429BD3D42ABD7BBA5F79166808CBD8410902F5736A1`.
The **87 sources** audited match the chain. **589/589 native tests**
pass, including **24 effective OpenGL ones**, the 60 VU1 cases, 100,800 random
FMAC and 2,016 targeted FTZ/DAZ, PAD2 and both FINISH modes.
The CPU renderer and the usual feedback policy are kept.

The corrected diagnostic of **240.21 s**, with a private copy of the card and
no compilers nor other games observed, reaches state 11 with the level
ready. The original card keeps its SHA256. **280 complete GPU reports**
are selected, bracketed by samples of that state. The average of
raster timestamps is **39.26 ms/profiler frame**; the group FBP=0,
flags=`4b` (texture, IIP, alpha blending and bilinear) accumulates **30.13 ms/frame**.
The following groups are `5a` (2.15 ms), `12` (2.08 ms) and `c8` (1.81 ms),
all at FBP=0. The selection also contains some compute batches while
variants are being prepared. It is a lead for investigating shaders; it is not equivalent to clean
FPS, exclusive CPU time nor per-primitive attribution. This figure is not
compared with the earlier profiler, which grouped empty data.

A private trial removes the earlier call to `coversPixel` from the hardware
fragment, because the shading functions already check coverage and edges.
The procedural control alternates original/candidate/original: **8.80 / 9.01 /
8.75 ms** median, 20 batches per run, 2000 IIP/STQ/
bilinear/ABE triangles per batch, effective hardware and exact 4 MiB against CPU.
It includes submission and synchronized readback; it does not measure gameplay FPS. It does not demonstrate
a gain, so it is not incorporated nor added to the patch chain.
The sources and logs of the trial remain in `logs/` and the published executable
keeps the 65 verified patches.

The public performance tool extends the previous check to a
per-second monitoring throughout the whole pass. Upon another build or
game, it closes only its own instance, marks the record as invalid and restores
the environment; the selector prevents using it to compute FPS or export JSON.
Four script controls with simulated processes and nine of the selector pass,
without launching or stopping other people's games or compilers.

The next CPU diagnostic uses a private copy linked with
public symbols from the optimized objects. It does not replace the
normal EXE nor is it useful for comparing FPS. The 30 s sampling in state 11 shows
waits in the main thread and the GS one, but uncovers two problems in the
tool: duplicate DbgHelp initialization (error 87) and caller frames
collected without being printed. The profiler is fixed to show
that second view and close its thread handles. The procedural wait of
`scripts\probar_perfil.cmd` fails before the changes and passes after, without
using the game. The sampling still needs to be repeated with that attribution to distinguish
queue waits, driver and synchronization; no cause is assigned yet.

### Review of compiled DIV and PR #23 (October 8)

The FMAC SSE part of `5e09b12` was already integrated; what is new in the PR is
`754c970`, which specializes the lower instruction DIV. Its conflicts
with `main` are resolved keeping the FTZ/DAZ fix of `247a9b3` and the later changes.
The separate flags optimization of `df8c740` is not included.

The 60 earlier controls did not exercise DIV. **38,144 cases** are added:
16 component selectors, limit and random values, Q before and after
WAITQ, D/I flags, direct/queued writes and cuts/resumptions, with and without
FTZ/DAZ. Registers, Q and memory match bit for bit; flags and cycles too.
A fault injected only in a private copy (latency 6 instead of 7) fails in
the first case: Q and flags match, but the cycles are `19/18`.

The integrated official build finishes with code 0, **65 patches** and the
501 local micromemories. The executable has **70,226,432 bytes**, SHA256
`EB8479487D9E572250BE1FFE618E2A8110386B5B1A14423A2AF924C45410068F`.
The audit of the **87 sources** finds no differences with the patches.
**589/589 native tests** pass, including **24 effective OpenGL ones**, the 60 earlier
VU1 cases and the new DIV ones, **100,800 random FMAC**, **2,016 FTZ/DAZ**,
PAD2 and FINISH default/asynchronous. The integration's CI also passes on Linux.
Opus's improvement figures belong to its captures; this review validates
parity and compilation and does not certify new FPS of the loaded game.

### Deferred GPU profile under review (October 8)

Patch 67 `ps2recomp-gs-profile-async.patch` is prepared as an isolated proposal:
it checks availability before reading timestamps, keeps windows and counters together,
limits the samples and removes the query objects on close. The inspiration comes from the
ICO PC profiler; the implementation is our own and does not alter the render.

Eight native controls with simulated timestamps are added. The official Windows
build, effective OpenGL and the game test remain pending:
the local tools could not start processes during this work.
GitHub rejected creating the blob and the branch with 403 on the first attempt.
The state of the components is not changed nor are new FPS certified.
Details and limits of temporal attribution:
[GPU profile without waits during render](gpu-profile.md).

On retrying, execution outside the sandbox works. The log identifies
a lock by `node_repl.exe` when updating its permissions (Windows error 32).
The base is updated to `9e34bff`, keeping PR #24 on VU1 flags; the
profiler now occupies position **67** in the chain. The GitHub CLI session is
valid even though the integration still rejects writing.

The eight isolated regressions pass with MSVC, C++20 and `/O2 /W4 /WX`. A
negative control inverts the availability guard in a temporary copy:
it compiles, runs the eight tests and fails in four, including the premature
read; afterwards the copy is restored. The official build is launched with
four simultaneous jobs in `E:\gowgpuprof`, which points to a private folder
of the workspace. The OpenGL and game controls remain pending on that build.

### Profiler verification and upload protection (October 8)

PR #25 of the deferred profiler was integrated in `43c3a47`, with CI green.
The official build of `2f6579d`, 67 patches, finishes with code 0 after
resuming the same build after the restart. The functional control of
240.31 s reaches state 11 with the level ready and produces complete profiler
windows. The reviewed captures show Kratos and enemies on the
ship, rain and HUD, with no visible stretched polygons in that scene.
A read-only ISO and private cards are used; FMV is skipped.
There were other people's builds and no new FPS are certified.

The review confirms that the game still presents via copy to CPU.
The raylib host's calls to the context capture and to the shared-texture
consumer are missing; setting `PS2X_GS_DIRECT_PRESENT=1` is not enough.
The tests do exercise a real share group explicitly. This difference is kept
so as not to confuse the capability of the backend with its real use.
Details: [profiler verification](gpu-profile.md).

A separate patch is prepared to prevent overwriting chunks of the persistent
ring whose fence has not been signaled and to release its 64 MiB even if
the host is still alive. The negative controls detect both problems.
The first integration passes 610/610 native controls, 25 with OpenGL.
The review also discovers that the streaming fallback could shrink
`dataBuffer`, leaving a stale capacity; it is fixed and its
regression is prepared. The official build of the final patch is pending
that control. EE/FPU/IOP nor Opus's work is altered.
Details: [upload ring protection](render-upload-ring.md).

### OpenGL ring validated with the joint version (October 9)

PR #30 incorporates the base `ca69e9b`, with Opus's new jumps between compiled
VU1 blocks. The official build of `2c8a8c1` finishes with
code 0, 69 patches and 501 local micromemories. 611/611 native
controls pass, including 26 real OpenGL ones, and the 97 audited sources match
the chain. The negative controls detect overwriting by timeout,
the ring leak with a live host and the stale fallback capacity.

The earlier functional test of 240.25 s reaches state 11 with the level ready;
its captures show Kratos, enemies, ship, rain and HUD with no visibly
stretched polygons. The joint version lasts 241.34 s, reaches that state and
also shows Kratos, enemies and HUD on the ship. FMV is skipped and
private cards are used. There are no ring degradation warnings; a partial GPU
report omits 2587 samples and its times are not used. Neither FPS nor a full game
are certified; the game's shared presentation is still
being prepared in a separate checkout and is not part of this PR.

### 2026-10-09: shared presentation on Opus's PRs #31 and #32

PR #33 connects the game's raylib consumer with the textures of the
OpenGL producer, with `PS2X_GS_DIRECT_PRESENT=1` and GPU backend. It keeps CPU
and RAM as reference/fallback. The shared latch stops forcing the
host wait; explicit reads and FINISH keep their barriers.
The diagnostic captures compose current VRAM with the latch's CRTC,
with per-generation cache: they are not historical snapshots of the acquired frame.
Details: [shared presentation](shared-presentation.md).

The base incorporates the already merged PRs #31/#32; their VU1
patches and EE/FPU/IOP/FMV are not modified. The rebuilt native suite passes **623/623**, with
33 real OpenGL controls. Restoring LINEAR fails in 3/12 specific
controls; forcing Flush in the shared latch fails in 2/5 queue
controls, which end with a bounded wait even under that regression. The
103 patched files match between the tested reference and the runtime
of the official build. The CI of the updated code passes.

The incremental cleanup of MSVC/Ninja in Spanish was also fixed:
it recorded zero header dependencies, so it mixed objects from
different interfaces. The script discards runtime/test objects and the PCH and
its creation object; the CMD wrapper keeps the real exit code.
The official build finishes with code 0; the suite linked with that
runtime repeats **623/623**. The **241.18 s** test confirms the effective shared
mode and repeatedly reaches state 11 with the level ready.
It produces thirteen diagnostic captures; those reviewed show Kratos,
enemies, ship, rain and HUD with no visibly stretched polygons in that
scene. There are no errors, ring degradation nor partial profiler reports.
A private card/cache is used and FMV is skipped; the close when the
deadline ends is forced. Completing the game or improving FPS is not certified.

### 2026-10-09 — Clean presentation comparison

After integrating `main` with PRs #33 and #34, the profile explicitly sets
RAM or shared presentation and restores the environment. Its controls pass;
the earlier script fails by inheriting the shared mode in a RAM pass.
The PowerShell analyzer and the nine window-selection controls pass.

Four alternating 180 s passes are completed with the same executable
of `343404f`, 501 micromemories, card initially absent, private cache
and frames-only profile, with no captures or GPU diagnostics. State 11/level ready
and the effective mode are confirmed in each. The weighted average
is 6.848 FPS RAM and 6.908 shared (+0.88 %), lower than the variation between
the two RAM passes: no stable FPS improvement is established. Conditions,
effective intervals and limits in `presentation-performance.md`.

The next GS investigation points to rasterization: the earlier diagnostic
shows 50–56 ms per presented frame and a dominant group FBP 0/flags
`0x4b`, with texture, linear filtering, interpolation and blending. It is a lead
to repeat GS chains and preserve their equality with CPU; no shader
optimization has been added yet. EE, FPU, IOP and FMV remain outside
this change.

### 2026-10-09 — Out-of-coverage discard trial

`ps2recomp-gs-discard-uncovered.patch` is prepared after the 76 earlier
patches. It adds a discard before the interlock when the fragment does not
cover the primitive, with `PS2X_GS_HW_DISCARD_UNCOVERED=0` to keep the
earlier shader. The new control compares the 4 MiB of VRAM against CPU with
thin/subpixel triangles, blending and clipping, and requires observing hardware after
the asynchronous compilation. The isolated control passes in both modes.

Five procedural samples with prepared shaders give 25.04–25.94 ms without
discard versus 16.63–18.35 ms with it for a batch of 4096 triangles. They are not
gameplay FPS. The full suite and the official build are started;
the detail and the interlock restrictions are in
`render-fragment-discard.md`.


### 2026-10-09 — Hardware discard: full validation

The native suite finishes 624/624 in both modes, including 34 real
OpenGL controls. The official build finishes with code 0 and 77 patches;
the 103 patched files match the tested reference. The same
binary is compared in four 0/1/1/0 passes of 180 s: the conservative segment
aligned by controller reports adds about 30 s per mode and gives 6.958 frames/s
without discard versus 7.267 with it (+4.43 %). The sample is short and is not a
deterministic replay: it does not establish a stable percentage for the full game.

The repeated functional control recognizes the real ISO and reaches a loaded game.
The controller captures at 90/160/190 s show Kratos, enemies in combat,
deck, rain and HUD. The trial uses diagnostics and ends by limit;
it does not validate FPS, all effects nor the normal close. The first attempt
with a badly encoded path is discarded. Hash, selection and limits of the trial:
`render-fragment-discard.md`.

It is detected as the next task that the GS capture decorator does not forward
`UsesSharedPresentation()`: when recording it could make the host choose RAM
over a backend that presents shared textures. It will be fixed separately
with a game-independent regression.

### 2026-10-09 — The GS recorder keeps shared presentation

The capture decorator inherited the default RAM capability even though its
backend presented shared textures. The host could choose a mode different
from the backend when activating `GOW_GS_REPLAY_TRACE`. It now forwards the effective capability
under the existing mutex; it keeps RAM when appropriate and does not force OpenGL.

The regression queries the decorator and the frontend with RAM/shared and direct
backend/on another thread. It fails before and passes after; querying does not synchronize,
present nor record commands. Full GS tool suite and quick rebuild:
code 0. The 140 s trial keeps the shared host, reaches level
ready and closes a short private capture during the game. The CPU replay
does not reproduce its final VRAM (343,007 differing bytes), so no chain
parity nor FPS improvement is claimed. Conditions in `controls-and-menu-tests.md`.


### 2026-10-09 — Game GS chain and feedback lead

The short private capture contains 60,389 Submits. CPU reproduces its own
output between repetitions, but differs by 343,007 bytes from the captured End.
A private probe continues after that divergence to compare variants;
it does not modify the public verifier nor certify the capture against CPU.

With hot shaders, complete initial restoration and 40,855 primitives,
289 batches and zero compute tiles per pass, the earlier shader varies
897 bytes between passes 2/3 and the discard varies 1,072. The comparison
between their last passes differs 1,047 bytes: this path does not allow certifying
equality between modes by a single repetition.

When repeating with the existing experimental option `--snapshot-feedback`, the
passes 2/3 of each mode match in the 4 MiB, and the last pass without/with
discard also matches exactly. The difference against CPU persists
(342,846 bytes in the candidate with discard); freezing per Submit does not emulate
the PS2 8 KiB cache. It is evidence pointing toward texture reads and
feedback within the primitive, it does not yet prove its exact cause. This policy
is not activated in the game nor is an FPS improvement attributed to this diagnostic.

Next task: isolate a procedural primitive with feedback and study the
visibility/cache of its reads, keeping the strict CPU control. Chains, VRAM, captures
and game-derived tools are not published.


### 2026-10-09 — Feedback reduced to one stable pixel

The GS pattern generator accepts `--altura 1..416`, keeping texture,
freeze and initial registers when reducing the two sprites. Capture and PCSX2 dump
match exactly through GIF/End CPU for six heights; the default
stays byte for byte. Controls for expected height, invalid inputs
and the independent CPU RGBA of the minimal case are added; both executables are integrated into CI.

With one row, the only differing pixel is `(32,0)`: CPU RGB `(141,90,98)` versus
hardware `(132,87,86)`, stable between repetitions and also with snapshot per
Submit. The average of the initial texels explains CPU; re-reading the pixel changed by
the first sprite explains GPU. A cache persistence difference between
primitives is isolated, separate from the variation of the large case. The game
renderer policy is not changed. Commands, table and limits:
`minimum-bilinear-feedback.md`.

### 2026-10-09 — Separating GS cache persistence and replacement

On main with PR38 integrated, the private cache intervention
is turned into a reproducible replay probe, exclusively for the CPU candidate.
Invalidating its tag before each Submit reproduces the GPU RGB of the
one-row case, keeping the End and state of the reference. The 54 procedural
patterns confirm persistence up to 32 rows and natural replacement from
33; TEXFLUSH eliminates the small difference, scissor keeps it. Cache
bases/bytes, VRAM, RGB and two complete initial restorations are verified.

The GPU cache is not implemented yet: the large case also needs
the order of reads and replacements within the sprite. Freezing per Submit or up to
TEXFLUSH does not reproduce both contracts. The test stays in CI to validate
that future fix without changing EE/FPU/IOP/VU1 nor the game executable.
Detail and limits: `minimum-bilinear-feedback.md`.

### 2026-10-09 — Intro capture and framebuffer check

`GOW_GS_REPLAY_STATE` is added to choose the state that allows starting a GS
capture. The default value is still 11 (game); state 4 allows studying
the preceding intro. Only commands sent by the EE can open the segment; a
presentation does not query its variables. The state limits the start, not the end.
The parser rejects empty, negative, fractional, overflowed entries or ones with
suffixes without partially applying the other options. The profile clears/restores
this variable together with the other capture options.

Local control on `fa07925`, runtime with 77 patches, executable with this change
SHA-256 `750ecf700585103d0c9ecdb3b7388aeb34d2e1d189ba3d8141c61784b4e61c95`:
`GOW_PAD_TEST=1`, `GOW_FAST_BOOT=0`, `GOW_SKIP_FMV=1`, OpenGL with RAM presentation,
real TEXFLUSH and state 4. Two own runs bounded to 45 and 70 seconds
captured complete segments from 24 and 35 seconds of the host. The byte limit
closed the segments before the two requested seconds: 141537/145221 records,
12/9 presentations and 54535167/54534992 bytes, respectively.

In the 21 presentations, PMODE is `0x8023`, the two DISPFBs point to page
208 and `hasPreferredSource` is false. Therefore, the rule that replaces the destination
with a preferred texture **does not explain those segments**. The private synthetic test
that shows a 75 % blend presented as a pure source demonstrates a defect
separate from that rule, but does not justify modifying it as a fix for this intro.

Replaying the prefixes up to the first/last presentation of each segment with CPU
produces the shifted framing: arm/back in front of the fire and enlarged head
in front of the sky. The two CPU instances match byte for byte in those prefixes;
this does not validate the complete GPU capture. In fact, replaying the GPU End of the
35 s segment with CPU differs by 498626 VRAM bytes. The discrepancy is kept as a
limitation, without automatically attributing it to the camera nor certifying fidelity.
The PCSX2 recording provided shows a different framing; the commands and the
camera/animation state at the same simulated time still need to be compared. That visual
bug has not been fixed nor an FPS improvement measured.

Validation: quick game build correct; Windows GS tool suite
(capture, checkpoints, pixels, feedback and oracles) correct; state selection
4/11 with synthetic memory, rejection of invalid values, TEXFLUSH boundary and
profile monitoring correct. Configuration: zero errors and four
pre-existing warnings; PowerShell syntax: zero errors. Dumps and images remain in
private folders excluded from Git. Next step: isolate Kratos's draws
before looking for a framebuffer or camera fix.
### 2026-10-09 — Observation of the cameras before drawing the scene

The private read of framebuffer 0 for the fire segment, before the first sprite
that copies it to 208 (record 10720 of the 24 s capture), already shows the arm/back
with the wrong framing. The next 16 sprites copy 512 columns in strips
of 32, without alpha blending. In the 21 presentations analysed, the complete
DISPFB/DISPLAY registers remain constant. The wrong image precedes that final copy.

`GOW_CAMERA_DIAG=1` is added, disabled by default, on the full return of
`renView::SetupPipeline` (`0x23B5E0`). The original always runs and
checkpoint resumes are not interpreted as returns. The probe observes the
world/inverse/projection/combined matrices of the `renView` and those of the camera
client, copying their bits without doing float operations in the game. The offsets come from the retail MIPS
at `0x1697F0`: view+0/0x40/0x100/0x240 and client+0x20 or +0x70 / +0xB0.
The list is taken from view+0x360, client at node+8; the sentinel is compared like
the `beq` instruction, with the full address. Reads validate the RAM range.

The `0x29BDF8` mark is incremented when hierarchies are updated; **it is not a frame
counter**. A first probe limited by that mark consumed its samples too
early. The final version limits each view/state pair to 32 observations separated
by two host seconds, with a maximum of 16 pairs. It also records the active view, the
view identifier and the world/inverse update marks. Views without a
camera are distinguished from those containing invalid nodes or clients.

Final functional check on `c035b3b`, runtime 77, executable SHA-256
`01046ba112c887041fef06acea9b5784bed7b3ff4c1ba175729955f3e78f64fd`:
95 seconds, OpenGL and RAM presentation, explicit synchronous FINISH, no fast boot,
FMV skipped and GS capture disabled. There are 148 samples: 86 in intro and 62 in game,
nine view/state pairs. The 42 samples with a camera client contain
finite matrices; their world/inverse matrices match those of the view bit for bit.
The largest deviation of their axis lengths from one is `2.22e-7`; the largest absolute
residual of the world×inverse product against identity is `2.58e-4`.
All the recorded matrices, including views without a camera, are finite.
No NaN and no previous stretched scale are detected in these observations.

This does not prove that the correct camera is selected or that the poses, the
bone hierarchy or the rasterization are equivalent to PCSX2. The three local
PCSX2 savestates are from the game; their captures do not correspond to the transition.
The next comparison requires isolating Kratos's pose and the view used at the
same instant of the intro. The visual fault remains open.

Validation: `camera_probe_test.cpp` with MSVC `/O2 /W4 /WX` passes exact bit copy
(including synthetic NaNs), local/articulated selection, aliases, sentinel, absence,
truncated memory, exact limits and intact memory. CI runs the same check
with GCC. Quick game build correct; profile monitoring correct, including
cleanup/restoration of `GOW_CAMERA_DIAG`; configuration with zero errors and four
pre-existing warnings; PowerShell syntax without errors. Logs, images and private
probes remain excluded from Git; EE, FPU, IOP and VU1 are not modified.

Performance figure relayed by the user: Claude reports two alternating rounds of
`GOW_GS_FINISH_ASINCRONO=1` together with `PS2X_GS_DIRECT_PRESENT=1`, from
7.3–7.4 to 11.1–11.4 frames/s. That combination remains a candidate for a
proper comparison of the four modes after resolving the transition. That figure is not
validated here and no default value is changed.
## Models during the menu/intro transition (2026-10-09)

The previous `GOW_MODEL_DIAG=1` check exhausted the 64 "early" samples
in the menu (state 3); no ProcessModel observations were left in the intro
(state 4). The quotas for intro, game (11) and remaining states are separated
for server, context, master and Clip. ProcessModel has one table per phase
with up to 64 model/view pairs, 32 samples per pair and two host seconds
between samples. Menu objects do not occupy the intro table.

The same variable adds `[gow-model:pose]` and `[gow-model:matrix]`: bits of
the object's local/world matrices and the world matrix of its root joint. The offsets
come from the retail MIPS of CalcWorldMatrix (`0x1303D0`) and CalcSkinHierarchy
(`0x137508`): object+0x20/0x70, skeleton at object+0x104, root at
skeleton+0x86 and articulated matrices from skeleton+0x8C in steps of 64 bytes.
The number of joints is read from definition+0x10, from skeleton+0x60.
The update marks are kept complete (64 bits). Ranges and indices are validated
without computing matrices, writing RAM or forcing updates.
These are snapshots at ProcessModel entry: they may include previous
buffers and do not by themselves prove which matrix ended up sent to VU1.

The synthetic check verifies that an exhausted menu lets the intro through,
separation by view and phase, physical aliases, interval, sample limit,
exact bit copy, intact memory and truncated or out-of-range matrices.
MSVC `/O2 /W4 /WX` passes; CI runs the same check with GCC.

`eebf73b` (Opus's PR #42) is integrated before the full game build.
REA is connected, but `open_binary` rejects this ELF as an unsupported
architecture: no decompilation or R5900 validation is attributed to REA.
The visual framing fault remains open.

Final native check: full `scripts/2_compilar.cmd`, 78 patches, return 0;
ELF SHA-256 `ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c`.
Executable of `eebf73b + 54c2dd1`, SHA-256
`b67f4e7b9b3377ecdc05b5d8a8033c8acf60f665050ec9ebf8174e51e70a4569`.
In 95 seconds with OpenGL, RAM presentation, synchronous FINISH, fast boot
off, FMV skipped and pad test: 123 model samples in menu and
343 in intro, with 15 and 11 model/view pairs respectively. The 466 objects
observed are readable; 84 root reads are valid. 1,016
matrices are recorded, none non-finite or entirely zero. The absence of a valid root
in the other objects is not interpreted as corruption: there are objects
without an articulated palette. The two articulated models observed in intro have
125 and 103 joints; their root matrices are constant across the 32
samples of each. It is not yet identified which resource is Kratos, nor are the
matrices of the other joints checked here.

The check ended at its deliberate time limit, with no samples of state
11. A second run of the same binary, another 95 seconds, with
`GOW_MODEL_DIAG=0` and camera active, does not record that state either (128 camera
samples in state 4, no model records). This does not establish a
cause nor is it equivalent to visually verifying the game. FPS are not compared.
Both own processes finished; Opus's checkout was not modified.

The local test that shares the menu/intro quota again fails, as
expected. The instructions of the two functions used to recover offsets
match the local ELF: 254 of `0x1303D0` and 380 of `0x137508`, with no gaps or
differing bytes. Ghidra 12.1.4 and `ghidra-emotionengine-reloaded` import that ELF
with `r5900:LE:32:default` and decompile both functions in a private project,
without global analysis. REA 6.2.0 does not support MIPS in its ELF reader, Ghidra
provider and evidence enums; moreover its server has no `GHIDRA_INSTALL_DIR` defined.
The direct Ghidra test does not demonstrate support in the REA bridge.

Next comparison: identify the character's model and joints,
and relate them to the camera client during the same PCSX2 instant.
The probe does not modify rendering nor fix the framing; logs and the Ghidra
project remain private.

## Paused PCSX2 reference for the intro (2026-10-09)

New reference with the local ISO `E:\gowport\God of War.iso`, PCSX2
`v2.9.114`, serial `SCUS-97399`, CRC `D6385328`. It was started from the menu,
New Game / Hero was selected and the intro was paused with Kratos facing front,
already separated from the very first close-up. Vulkan, internal resolution 3x,
the emulator's built-in patches active and cheats/widescreen disabled.
This frame is not synchronized with the port's previous frames:
it does not allow a pixel comparison nor one of the whole animation.

Profile and two new private savestates under
`E:\gowgpuprof\pcsx2_reference\PCSX2`; the user's slots were not used.
In this installation, `-datapath` appends `PCSX2` to the supplied directory.
The original installation has RUNASADMIN compatibility and the two initial
hidden instances could not be closed from the unprivileged process.
The reference was obtained with a local copy of the already installed PCSX2, without
modifying that compatibility or the original settings.

`tools/render/pcsx2_ee_reference.py` reads EE through local PINE, checks the pause,
serial/CRC, response lengths and stability of the hierarchy mark.
It does not write memory or load states. 32 MiB were captured in state 4,
mark 32537, SHA-256
`3219f816196c231b37ff6490f9b477fd7c6184b6a43044c499cb074958aa94c8`.
The repeated read matches the first private dump byte for byte.
The pointer `0x33104C` is zero in this pause between frames; do not interpret
that zero as null matrices or as camera corruption.

The persistent view `0x75CD70`, id `0x45`, links to the same camera client
`0x1116990` as the port; its parent is `0x1111F20`. The articulated objects
`0x1112470` and `0x753E20` have 125 and 103 joints respectively.
The root of 125 articulates the same translation as the previous 32 samples
of the port: `(1048.109985, 727.026001, 1007.25)`. Against one of those samples,
7/16 components match by bits and the largest absolute difference is
`3.725290298461914e-08`; the X/Z orientation signs are negative in both.
This bounds the hypothesis of a 180-degree turn of that root, but does not verify
the full palette, the selected visible model nor the VU1/GS computation.

When separating the main view from the empty views, the 32 native samples
in state 4 contain eight distinct world matrices: the position goes from
`(1047.542725, 761.248352, 1017.296326)` to
`(1047.589844, 754.348328, 1031.195313)`. The camera is not completely frozen
in that check. PCSX2 was paused later in the sequence, at
`(1047.635132, 749.300110, 1041.421509)`; subtracting those positions as if they were
from the same instant would produce a false discrepancy.

Next step: compare the non-root joints and the camera parent
with an aligned sequence. The reference and its capture remain outside
Git. The renderer is not changed and no FPS improvement is claimed with this check.

## First joints and camera parent (2026-10-09)

The optional model and camera diagnostics are extended, without writing RAM,
computing matrices or forcing updates. ProcessModel reads at most the
first eight palette matrices, limited by the skin count and the physical
RAM ranges. SetupPipeline records the parent joint matrix selected by the
camera client. The bits are kept without doing float operations; `validJoint` indicates a valid read, not a verified
semantic identity.
The camera does not use the skin count: in the PCSX2 reference it is zero, although
its joint 1 is readable and matches the view.

Local MSVC `/std:c++20 /O2 /W4 /WX` checks: camera and models pass,
including aliases, intact memory, synthetic NaNs, count 0/3/20, limit of eight,
null pointers and matrices that are truncated or cross the segment. A
private mutation of the palette stride from 64 to 32 bytes makes the models check fail.
The C++ reader over PCSX2's private RAM recovers both initial palettes
and confirms bit equality between view, client and parent joint.

Full build with `scripts/2_compilar.cmd`, 79 patches, return 0.
Probe code `1fc7ff7`, on top of `c8c9860`; retail ELF with the SHA-256 already
recorded above. Binary SHA-256
`5b1c81330f499fca55180dce830160bdeafbaa757ef8971e3e1692a95820cdbd`.
Native check of 95.612 seconds with camera/models active, OpenGL,
RAM presentation, synchronous FINISH, fast boot off, FMV skipped and pad test.
The own process is terminated on reaching the limit; the host log
has no ExitCode. No state-11 samples are recorded nor is the
limit attributed to a game fault. The final capture shows a frontal
close-up of Kratos, but it is not aligned with the PCSX2 reference and does not
demonstrate a correction of the previous framing.

656 joint matrices are read: none non-finite or entirely zero.
The 32 valid camera samples match by bits between viewWorld,
clientWorld and parentJointWorld. The parent `0x1111F20`, skeleton `0x1114130`,
palette `0x112ED00` and joint 1 (`0x112ED40`) match structurally
with the reference. In intro, the models `0x111B700` (125 joints) and
`0xD51C80` (103) have 32 samples for each index 0..7. In the first, indices
3..7 change and the root remains constant: a constant root does not
imply frozen animation. In the second, all eight matrices are constant
during this observed segment.

Against the single later PCSX2 frame, the maximum absolute difference
of the 125 root is `3.7253e-8`; at indices 1..4, the last sample lies
between `6.1035e-5` and `1.8311e-4`. The animated joints 5..7 reach
`0.048279` in the last sample. In the 103 palette the maximum of the eight
indices is `1.1444e-5`. These are descriptive differences of different instants,
not equivalence tolerances nor proof of animation fidelity.

The remaining 117/95 joints, the identity of the visible
resource and the data that ends up sent to VU1 remain unverified. The next step is to
align the sequence and follow the palette to InitUNPACKData/VIF; do not change
the math because of these differences without a same-instant comparison.
Performance is not measured and the renderer's state on the map does not change.
Logs, captures and dumps remain private; Opus's checkout is not modified.

## Full palette before ProcessModel (2026-10-09)

`GOW_MODEL_DIAG=1` and `GOW_MODEL_PALETTE_DIAG=1` allow reading up to 256
joints per sample, with the same quotas and frequency as before.
Each matrix keeps its bits and the skeleton mark; the requested count,
the matrices read and whether that count was reached are recorded. The limit of 256
only bounds the diagnostic. It stops before reading a matrix outside RAM,
without changing any matrix or the original execution. Each new matrix line
is emitted in a single write to avoid interleaving components with
records from other threads. A first test with per-component writes
produced interleaved lines and is not used for these figures.

MSVC `/O2 /W4 /WX` tests: palettes 103/125/256, a request of 257 truncated,
aliases, NaN bits intact, last byte missing, NULL, segment and intact RAM.
Limiting the full reader to eight matrices in a private copy makes
the test fail. The same reader over PCSX2's paused RAM reads the complete
125 and 103 joints without modifying the reference.

Integrated on top of `98d06c1`; probe code `4ea6204`, 79-patch runtime
unchanged. `scripts/2_recompilar_rapido.cmd` ends with return 0;
header/override equality between source and runtime is checked. SHA-256 of the
private executable used and of the recompiled binary:
`80c8cfa9bed8d53e25efdfbbfbf80f9bd1d81f46ff2d20d40d724d1953e1a4e1`.
The game sources are not regenerated nor is Opus's checkout modified.

Check of 95.948 s, OpenGL with RAM presentation and synchronous FINISH,
fast boot off, FMV skipped and pad test. The own process is terminated
at the deliberate limit; ExitCode is not available. 9,598 matrices are read
in 84 complete palettes, with no non-finite or entirely zero matrices.
States 3/4 are observed; there are no state-11 records. Performance is not
measured nor is the game or visual equivalence validated.

In intro, 32 samples are obtained for each of the 125/103 joints
of `0x111B700` / `0xD51C80`. 116 indices of the first palette change; the whole
second one remains constant during this segment. Against the single later PCSX2
frame, the last sample has maximum absolute difference
`0.0802001953125` (index 20) / `0.000011444091796875`. Since the instants
are different, these figures are not equivalence tolerances. The framing
and the identity of the visible resource remain pending.

Ghidra 12.1.4 with the R5900 language recovers, in read-only mode, the
retail routines `0x158DA8`, `0x1590F0`, `0x157100` and `0x166BE8`. The call
`0x158B94` updates the hierarchy at `0x1590F0` before processing the group
at `0x158D48`; the calls `0x159570` / `0x15958C` select
CalcSkinHierarchy / its variant according to visibility. The routine receives in
a2 a matrix buffer reserved for the packet, distinct from the world
palette observed at ProcessModel entry. Therefore the entry palette
does not demonstrate which transformations VU1 consumed. The next check must
read that destination after skinning and relate it to VIF, respecting the
function's resumes and aligning the sequence with PCSX2. Pseudocode,
RAM and logs remain private.

## Per-thread CPU profile at the docks: the bottleneck is VU1 (2026-10-10)

`tools/rendimiento/muestreo.cpp` is an external sampler for Windows: it suspends each thread of the process
every 1 ms, reads its RIP and at the end resolves functions, files and lines with the runner's `.pdb`. It gives the
real occupancy of each thread (samples outside the kernel wait functions). How to compile it
and use it is in the file's header. Unlike `GOW_PERF_DIAG=1`, it adds no code to the runner.

**Measured** (main `895bfad`, OpenGL with shared presentation, `GOW_GS_FINISH_ASINCRONO=1`,
`PS2X_VU1_HILO=1`, `PS2X_GS_FRENTE=1`, A/B pad script, 60 s starting at t=150 s at the docks,
20.0 fps):

| Thread | Busy | What it does |
|---|---|---|
| VU1/VIF1 (`PS2X_VU1_HILO`) | **91.5 %** | ~66 % in compiled microcode blocks (`programa1..12`), 8.6 % in the `vu1c_gen::run` dispatcher (the `switch (pc)` alone, ~1.4 %), 11.4 % in `ps2_vu1_core.cpp` (`commitReadyPipelines` 3.8 %, XGKICK, flags, interpreted pairs), 3.4 % in `processVIF1Data` |
| GameThread (EE + IOP) | 55 % | the rest waits; the IOP and its timers occupy ~25 % of this thread |
| GSThread | 20 % | |
| GS front (`PS2X_GS_FRENTE`) | 13.5 % | |

Consequences:

- **The critical path is the VU1 thread.** The frame lasts as long as VU1 takes (~46 ms), not the sum of EE and VU1:
  they already overlap.
- **The fps come in steps** because the game waits for VBlank: 60/30/20. At the docks it is pinned at 20.00
  (3 VBlanks). To go to 30 fps the VU1 thread must drop from ~46 to <33 ms per frame (**-28 %**). A
  smaller improvement does not change the fps: it must be measured with this sampler's occupancy, not with
  `guest_flip_hz`.
- The VU1 thread's profile is flat (no line exceeds 1.5 %): the cost is in each pair of each block.
  The next big improvement would have to reduce the per-pair cost in `stepPairT`, for example by resolving at
  generation time the waits and latencies of registers that are written within the same block.

**Negative result: batching the IOP cycles.** `iop_ms` from `GOW_PERF_DIAG=1` attributed to the IOP 2.2–3.2 s
of every 5 s, and `PS2X_IOP_PC_EVERY` showed that the IOP only executes ~0.6 M instructions/s: the cost is
the management of `runCycles`, which is called at every EE checkpoint (32 EE cycles = 4 IOP) and goes over SPU2,
DMA, callbacks, timers and the scheduler. Moreover, the measurement itself (two clock reads at each
checkpoint) greatly inflates `iop_ms`. Accumulating the IOP cycles in batches of 256 of its own cycles inside
`IopEmulator::runEeCycles` was tried (suite 591/591). In the same scene: **19.92 fps with the batch versus 19.97 without
it** (two alternating rounds). There is no improvement because the EE is not the critical path. Moreover, the batch caused
multi-second stalls in loading (host_hz < 1) that desynchronize the pad script. In one of the rounds
the game ended up in another scene (state 4 → 14) at 60 fps, which falsely looked like an improvement from 20 → 55 fps.
It was discarded and is not published. Lessons: always check in the log that the two variants follow the same
sequence of states (`[gow-pad2:state]`), and `scripts\probar_rendimiento.ps1` deletes `PS2X_IOP_PC_EVERY`
(to sample the IOP, call `ejecutar.ps1` directly).

## Faster compiled VU1: optimized dispatcher, impossible waits and table-based flags (2026-10-10)

With the per-thread sampler (`tools/rendimiento/muestreo.cpp`, which now also gives a per-instruction histogram with a fifth argument) the samples were cross-referenced with the disassembly (`dumpbin /disasm`).
Four changes, all exact:

- **The `vu1c_gen::run` dispatcher was unoptimized.** It was a single `switch` with thousands of cases and MSVC does not
  optimize functions that large: it compiled it as with `/Od` (`pc()` as a call, variables on the stack).
  It occupied 8–9 % of the VU1 thread. Now each address has a small function and `run` uses a table
  (`tools/vu1/generar_vu1.cpp`): 8.7 → 2.3 % on the bench.
- **Impossible waits.** Each pair in a block advances at least one cycle. If the last writer of a
  register that is read is an earlier pair of the same block at a distance >= its latency, that read cannot
  stall the pair: the generator removes it from `readyCycleT` (struct R, identical to pair K except for the reads).
  26,090 of 57,305 reads are removed.
- **MAC/status flags via table.** The bit inversion of the lane masks (~20 instructions per
  FMAC) becomes a lookup in a 256-entry table. `recordViWriteForBranch` is expanded inline
  (it was a call in every pair that writes a VI) and the store of `m_state.cycles` in every pair disappears
  (`run()` sets it on finishing and nothing reads it in the meantime). `patches/ps2recomp-vu1-fast-pairs.patch`.
- **16-byte VF writes.** `applyDestT`, `applyDest` and the VF0 reset wrote lane by lane.
  Now they merge and write 16 bytes, so that the 16-byte load of the next pair can be forwarded
  from the store. Measured effect small (~1 %).

**Verified:** identical per-launch fingerprints between the interpreter, main's compiled VU1 and the new one in
`vif_pcsx2_inicio2` and `vif_port_480s` (they include cycles and flags), suite 590/590, `probar_vu1_compilada` and
`probar_vu1_fmac` (with FTZ/DAZ) correct.

**Bench** (`repetir_cadena_vif`, VIF1/VU1 without rasterizing, 40 passes, median of 5 alternating rounds):
`vif_pcsx2_inicio2` 65.1 → 55.4 ms per frame and `vif_port_480s` 71.0 → 60.6 ms (**−15 %**).

**Game** (Athens docks, 60 s sampler from t=150 s, same script and same options as the A/B):

| | VU1 thread busy | fps | VU1 per frame |
|---|---|---|---|
| main | 90.8 % | 20.0 | ~45 ms |
| this version | 78.3 % | 20.5 | ~38 ms |

The game waits for VBlank and at the docks it stays on the 20 fps step: to move to 30 the VU1 must drop
to ~31 ms per frame, another ~19 %. Also measured: without normalizing operands (experiment, incorrect
result) the bench drops ~5 %; without checking waits, ~3 %.

**Misleading experiments.** Removing the VF0 reset seemed to give −41 %, but some microprogram
writes to VF0 and the game was doing other work; variants that change behavior (no flags, no
VF0) are useless for measuring. Fingerprints must be checked in experiments too.

**Pad script.** With a fast boot, `5:start` chooses New Game in the main menu and the A/B measures the
intro (moving camera, 16–57 fps, format-3 XGKICK errors in main and in the new version) instead of
the docks. The script `13:abajo,20:x,62:x` loads the game in both cases (see `controls-and-menu-tests.md`).

**Sporadic hangs** with `PS2X_VU1_HILO=1`, `PS2X_GS_FRENTE=1`, `GOW_GS_FINISH_ASINCRONO=1` and shared
presentation, in 2 of 8 runs: once with main the game stopped presenting frames (`guest_flip_hz=0`)
while the window stayed alive, and another time with this version the presentation thread stopped
(`[gow-perf]` at 15 s) while the game kept running at 20 fps. Pending investigation.

Next steps for VU1: lazy XGKICK (copy the packet when the VU writes to its memory or on
finishing, instead of calling `progressXgkick` on every pair), confirm flags in batches, non-normalized
operands with DAZ/FTZ, and blocks with static timing.

## VU1, round 2: dispatch by last variant, event-driven PATH1 and FLG=3 (2026-10-10)

`muestreo.cpp` now accepts a sixth argument `pilas` (stacks): it saves the stack of each sample (StackWalk64) and prints
the caller chains of the chosen functions (several separated by `|`). With that, the costs of the VU1
thread outside the blocks were located. All the changes are exact:

- **Dispatch by last variant** (`tools/vu1/generar_vu1.cpp`). An address can have up to 13
  block variants, one per microcode, and they were tried in order: for the hottest block of the
  docks, four failed calls before the good one. Now each address remembers the last variant that
  matched and tries it first. Bench: −5 % / −7 %.
- **Lazy decoding** (`ps2recomp-vu1-lazy-decode.patch`). On every microcode change the
  2048 pairs were decoded (~1 % of the VU1 thread) even though the compiled code does not use that cache. Now each
  pair is decoded the first time it is requested and `m_statusQuiet` no longer scans the words.
- **GIF arbiter buffers** (`ps2recomp-gif-arbiter-buffers.patch`): each packet (XGKICK, DMA) reserved
  a new vector; now the already-processed ones are reused.
- **Event-driven PATH1** (`ps2recomp-vu1-path1-events.patch`). While there is an active XGKICK (almost always),
  every pair called `progressXgkick`. The copy depends only on the number of cycles and on data memory, so
  now it is counted at once and brought up to date before the VU writes to its memory, before checking whether
  the send is still active, on finishing and at each event (copy of a GIFtag or end of the packet), which occur in
  the same cycle as before. The six XGKICK tests of the suite pass, including those for stores during the
  send and the wait for the second XGKICK.
- **FLG=3 in XGKICK.** A GIFtag with FLG=3 ("disable") works like IMAGE in the GS (and the frontend
  already treats it that way), but XGKICK rejected it as a reserved instruction (`0xFFFFFFF8`) and stopped the microprogram.
  It occurs in the intro and, depending on what is on screen, also at the docks: in those runs geometry was missing
  and the frame came out cheaper (false 29–30 fps). New regression test in `ps2_vu1_tests.cpp`.

**Verified:** per-launch fingerprints and images of `vif_pcsx2_inicio2` and `vif_port_480s` identical to main
(compiled and interpreter), suite 591/591, `probar_vu1_compilada` and `probar_vu1_fmac` (100,800 cases + 2,016 with
FTZ/DAZ) correct.

**Bench:** `vif_pcsx2_inicio2` 55.4 → 52.1 ms and `vif_port_480s` 60.6 → 55.7 ms per frame (from main, −20 %
and −22 %). **Game** (docks, same conditions as in round 1, no VU1 errors):

| | VU1 thread busy | fps | VU1 per frame |
|---|---|---|---|
| main | 90.8 % | 20.0 | ~45 ms |
| round 1 (#54) | 78.3 % | 20.5 | ~38 ms |
| round 2 | 82.3 % | 24.0 | ~34 ms |

For a stable 30 fps, ~3 ms per frame (~10 %) are still missing.

**Build dependencies broken with MSVC in Spanish.** `rules.ninja` has the prefix
`Nota: inclusión del archivo:` in UTF-8, but `cl.exe` writes it in the OEM code page: ninja does not
record any header dependencies (`ninja -t deps` gives `#deps 0`). `compilar.ps1` already deleted the
objects of the runtime, the tests and the unity build because of that, but not those of the compiled VU1 (`vu1_generado`, without
PCH): after changing `ps2_vu1.h`, the blocks were left with the previous layout of `VU1Interpreter` and the game
got stuck in an infinite wait loop on startup. `compilar.ps1` now deletes them too. With a manual
`cmake --build` they must be deleted likewise after changing headers.

**Discarded after analysis:**
- *Non-normalized operands with DAZ.* `normalizeOperand` is bitwise, but the interpreter computes in float
  products that may be subnormal and then adds them; with DAZ, `normalizeFmacExactResult` would keep a different
  last bit. It is not equivalent.
- *Skipping the normalization of FMAC results.* Only ADD/SUB/MUL/MAX/MINI/ITOF/ABS always give normalized values:
  a MADD/MSUB through the scalar path can leave a subnormal (two roundings with the exact value just
  above FLT_MIN), so it cannot be assumed in general.
- *Batching the IOP cycles* (see the previous entry).

Next: blocks with static timing (check the waits once at block entry instead of
at every pair), liveness of MAC flags between blocks and the PATH1 copy in chunks.

## Integration of the shared diagnostic with #55 (2026-10-10)

The branch `codex/shared-frame-diagnostics` integrates, via merge, `main`
`7800bc27c27ab5ddb0dd19338b834e0e2eff3829`. All the changes
of #55 are kept; the two insertion conflicts in `scripts/compilar.ps1` are resolved
by adding the host diagnostic after Opus's three new patches.
Its checkout is not modified nor are its processes stopped.

Local light check: six inspector tests correct (Python 3.14.7),
configuration with 0 errors and 4 existing warnings, syntax of 20 PowerShell
scripts with 0 errors. The 90 unique patches pass check and application
in order in a fresh worktree on the pinned commit
`c5a9d02573410a2085a4b4b831b0b68ba3515440`; the existing runtime diff
matches before and after. Private log: `logs/transition_review/patch_chain_90.txt`.

It is verified that `E:\gowgpuprof` is a junction to our
`E:\Decompilación de God of War\gow-gpu-work`. That runtime is not cleaned or
rebuilt. The PC remains reserved for Opus: no builds, games
or benchmarks are run. The full Windows validation and the transition with the
integrated HEAD are still pending; #51 keeps its draft status.
The protocol and the four-control matrix are in `shared-transition.md`.
The alternation, the framing and the intermittent hangs are not declared fixed.

In the later review of the inspector, an omission is reproduced with synthetic
inputs: a sequence that reappears after another was not checked against
its original metadata. `inspect_shared_frames.py` now keeps that
reference until the mode changes; the host tick may vary. Inconsistent
rows do not feed the return patterns. Eight tests pass; the
new regression fails with the previous version for hash, validity, dimensions
and render sequence. The runtime patch is not changed nor is the game run:
it is an analysis improvement, not a demonstrated visual fix.

## Windows validation of the 90-patch chain (2026-10-10)

The user confirms that the PC is free. `origin` is fetched again and the branch
remains synchronized with `main` at `7800bc2`, through the existing merge.
A private snapshot of the previous runtime changes is kept and the
cleanup targets under our `gow-gpu-work` are checked; Opus's checkout is not touched
nor are its processes stopped.

`scripts\2_compilar.cmd`, with `GOW_WORK=E:\gowgpuprof`, ends with code 0
for `76a25bedac7842e0a35cbd5eb56ca5941ebae429`, with the 90 patches, Release,
traces disabled, three parallel tasks and VU1 in interpreter. The ELF's SHA-256
matches the expected one. New executable:
`36e632cd39dfd73e3de3573c38b8c87715f9ef65b1eb6b2bba3ef776ed457c9f`.
Private manifest and log: `E:\gowgpuprof\transition90\build.json` and
`full_build.log`. This binary does incorporate the current chain; the
previous executable is not used to attribute these changes to it.

The Windows libpad2 packet test passes. The native suite passes **591/591**
in normal mode and **625/625** with `GOW_GS_GPU_TEST=1`, including real GPU,
shared compositor and raylib consumer. The first run from a
logs folder failed because a test looks for `instructions.h` through
relative paths; it was repeated from the runtime root, without modifying code or
tests. The optional diagnostic was enabled during the GPU check: six
analysed acquisitions, known hashes and no regression, inconsistency
or A–B–A return in those procedural samples. They do not vouch for game images.

The functional matrix is run in private folders, with one copy per pass
of the same unformatted procedural card (8,650,752 bytes), without user
saves; the user's original card is not written to. The other optional diagnostics and the periodic captures
are removed from the environment; `GOW_FAST_BOOT=0`, the wrappers it installs by presence and the default
debug panel are kept. VU1/GS front in threads remain off. The hash/log is not
used to measure FPS.

| FINISH / presentation | Process duration | First script state 11 | Shared acquisitions |
|---|---|---|---|
| Synchronous / RAM | 360.06 s | 146.64 s | — |
| Synchronous / shared | 360.04 s | 121.16 s | 2,186 |
| Asynchronous / RAM | 360.05 s | 116.32 s | — |
| Asynchronous / shared | 233.22 s | 111.31 s | 1,247 |

The first three passes are deliberately terminated at the 360 s limit.
The fourth is interrupted at the user's request, who needs the computer:
only our PID 11320 is validated and terminated. Its termination exit code
is not attributed to a spontaneous failure. All four reach state 11 and their
last reports remain in that state, without the sought VU1/GIF/exception
error signatures. The cards remain identical. The script uses the host
clock: those times do not align frames nor compare performance.

The two shared logs have known hashes, with no sequence/render regressions
nor inconsistent metadata. They record 105/109 A–B–A returns,
all before the first state-3 report. None appears in the
1,094/342 acquisitions after the first state-11 report; these
groups follow the last recorded state, not an exact alignment.
The diagnostic records only new sequences: its retention counter
equal to zero does not demonstrate that the host never retains a texture.

There is a clue distinct from the hash: in the asynchronous pass, sequence
906 is acquired with `hostTick=1365` and `frameTick=948`, a distance of 417 ticks; the synchronous
maximum was 3. The later acquisition goes back to close ticks. Investigate
the host waits and the GS queue before attributing it to a corrupt slot,
to alternating images or to sustained latency. Do not convert these ticks into FPS.

A single external capture of the RAM window shows HUD, scene and Kratos,
but the panel covers much of the framing; it does not vouch for camera fidelity.
The shared capture is rejected because our window was not in the foreground,
without capturing another application. A visual review with the panel collapsed,
repetition of the asynchronous combination and separate controls of the threads are missing.
Logs, manifests, execution and capture tools remain private in
`logs/transition_review/` and `E:\gowgpuprof\transition90`.
The PC is reserved for the user again; do not launch new loads until
their confirmation. #51 remains in draft and the transition, the framing
and the hangs are not declared fixed.

## VU1, round 3: fixed per-pair writes, specials with SSE and more (2026-10-11)

The sampler has a `linea` (line) mode (sixth argument): per-thread timeline of the first 1500 samples
(`#` busy, `.` waiting, one letter per chosen function). At the docks it shows that the EE and the VU1 thread
wait **at the same time** for VBLANK: the game is synchronized with the vertical and the fps come out quantized (60/30/20).
A frame whose VU1 work does not fit in two VBLANKs (33.3 ms) goes to three; the mix of 2- and 3-VBLANK frames gives
the 24–25 fps. A temporary diagnostic in `syncVu1Worker` confirmed that the EE never waits there for the VU1 at the
docks: the EE → VU1 chain is serialized through VBLANK, not through that synchronization.

`GOW_PAD_SOLO_GUION=1` (set by `probar_rendimiento.ps1`) ignores the real pad and keyboard: touching the mouse or
a pad during a measurement moved Kratos or changed the game in the menu, and the measured scene was not the same.

Changes, all exact (per-launch fingerprints and images identical in compiled and interpreter):

- **Fixed per-pair writes** (`ps2recomp-vu1-static-stores.patch` and the generator). Each pair reset
  VF0 and VI0 and cleared the VI copy for branches. Now it is decided at compile time: VF0 only if the upper
  or lower instruction can write it (FMAC with fd = 0, ITOF/FTOI/ABS with ft = 0, LQ/MOVE/MR32/LQI/MFIR
  with ft = 0 or a lower one that goes to `execLower`), VI0 only after `execLower` (the inline lower ones
  check `it != 0`), and the VI copy only in the first pair of the block or after a pair that activates it
  (`clearBranchBackup` in struct R). Bench: −5 % / −3.4 %.
- **ITOF/FTOI/ABS with SSE and SQ with partial DEST in registers** (`ps2recomp-vu1-simd-specials.patch`). The two
  hot spots of the transform loops were failed store→load forwards: FTOI was computed lane
  by lane on the stack (in double) and then read as 16 bytes, and SQ.xyz copied to the stack, changed lanes and
  read back. FTOI with `cvttps2dq`: x·2ⁿ in float is exact except for overflow and every value ≥ 2³¹ saturates
  to INT32_MAX (floats near 2³¹ are multiples of 128, so "≥ INT32_MAX" is equivalent to "≥ 2³¹"); below
  −2³¹ it gives INT32_MIN like `floatToInt`. Bench: −2.9 % / −1.9 %.
- **More inline lower instructions** (`ps2recomp-vu1-lower-specials.patch`): FCAND, FMEQ, FMAND, FCGET, BAL, JR and
  JALR went to `execLower` (85 % of the remaining calls).
- **Event-driven `advanceTo`** (`ps2recomp-vu1-advance-events.patch`): long waits (DIV, XGKICK)
  advanced cycle by cycle; now they jump to the next event (confirmation of a queue or of PATH1).
- **PATH1 copy in chunks** (`ps2recomp-vu1-xgkick-bulk.patch`): with spare cycle credit, the data
  qwords of a packet are copied with a `memcpy` (respecting the wrap-around to the start of data memory).
- **Masked VIF1 UNPACK with SSE4.1** (`ps2recomp-vif1-unpack-mask-sse.patch`): the mask, STMOD and
  ROW/COL are applied to the four lanes at once instead of word by word.
- **Dispatch**: each address remembers the last block that matched (`g_hot`) and `run` calls it without going
  through the dispatch function.

**Verified:** fingerprints and images of `vif_pcsx2_inicio2` and `vif_port_480s` identical (compiled and
interpreter), suite 591/591, `probar_vu1_fmac` (100,800 + 2,016 cases) and `probar_vu1_compilada`, which has a
new procedural program with ITOF/FTOI/ABS, SQ with partial DEST, FCAND/FCGET/FMAND/FMEQ and BAL/JR/JALR with
limit values (±0, subnormals, ±2³¹ and neighbors, maxima, Inf/NaN, limit integers), FTZ/DAZ and budget
cuts: 936 exact cases.

**Bench:** ~−15 % per frame compared with round 2 in both recordings (absolute figures vary between
sessions; the A/Bs are always done alternating the two versions). **Game** (docks, same conditions):

| | VU1 thread busy | fps | VU1 per frame |
|---|---|---|---|
| main | 90.8 % | 20.0 | ~45 ms |
| round 1 (#54) | 78.3 % | 20.5 | ~38 ms |
| round 2 (#55) | 82.3 % | 24.0 | ~34 ms |
| round 3 | 75.4 % | 25.2 | ~30 ms |

With the default configuration (OpenGL, RAM presentation, no optional threads or asynchronous FINISH), the
same game and the same script run at 11.6 fps, with no VU1 errors. These are the two figures in the READMEs (~12 and ~25).

For a stable 30 fps the VU1 work of each frame has to fit in two VBLANKs together with the part that
waits for the EE: ~3 ms (~10 %) are missing.

**Discarded:**
- *Table for the sticky bits of FMACs with dead flags*: no measurable gain.
- *Batching the IOP cycles*: no gain and with stutters in loads (see round 2).

**Next (analysed, not done):**
- *Already-normalized operands.* Every FMAC (also MAX/MINI), ITOF and ABS leaves a normalized value, and for those
  values `normalize4` changes nothing: within a block it can be known which lanes of each VF/ACC were written by one of those
  instructions and the normalization skipped. But the transform loops are software-pipelined (each iteration uses what the
  previous one computed, in another block), so within the block only the ACC of the MADDA chains is saved
  (2 of ~11 normalizations in the hottest loop).
- *Dead MAC flags between blocks.* In the hottest loop (two 9-pair blocks that jump to each other),
  the 3 FMACs at the end of each block save flags that the first FMAC of the other block overwrites without anyone
  reading them. The successors' code must be checked at run time (it is not in the block's
  words) and care must be taken with budget cuts between the two blocks, which would leave other flags visible than
  the interpreter.
- *Static timing* of blocks (check the waits at entry instead of at every pair).

## Integration of the GS diagnostic with #56 and #57 (2026-10-11)

Remote references are fetched and `origin/main` is integrated via merge at
`34cbe58a9a47e33d1a2ed70b34a9937f72293d43`, with #56 and #57.
The six new patches, the VU1 generator,
its regressions, the sampler and Opus's overrides are kept unmodified. The insertion
conflicts in `scripts/compilar.ps1` are resolved by leaving the six patches in
their original order and the host diagnostic at the end. The `ESTADO.md` conflict
keeps both investigations, in date order.

The integrated chain contains 96 unique patches. Complete check and application
correct in a fresh private worktree on the pinned upstream,
without touching the built runtime or Opus's checkout. Configuration:
0 errors and the 4 existing warnings. PowerShell syntax: 21 scripts,
0 errors. Private log: `logs/transition_review/patch_chain_96.txt`.

The CI of `ee079d21cecfbc7515f17e34db6490cc7c8a99fc` had finished green
before this merge. It does not validate the new integrated HEAD. The native tests
591/625 and the previous matrix correspond to **90 patches**; the saved binary
does not incorporate #56. A full build of the new chain will be necessary
before attributing images, stability or performance to it. The 25.2 FPS of #56
are Opus's measurements, not an independent reproduction by GPT.

The computer's availability is still pending confirmation: review and light checks
continue, without builds, games or benchmarks.
#51 remains in draft; the tick-distance clue and
the framing are kept as problems that still require visual control.

## Tick distance in the shared inspector (2026-10-11)

The 417-tick finding required until now an additional private analysis.
`inspect_shared_frames.py` now reports `tick_distance`: number of consistent samples,
signed minimum/maximum of `hostTick - frameTick` and the line, sequence,
render and ticks of the first maximum. It includes consistent retentions and records
without hash; it discards contradictory metadata. It does not compare ticks between images
of different epochs nor turn the result into time/FPS. A negative value
can be valid because the request samples the counter after the host.

Eleven Python tests pass. The three new ones fail with the inspector from
`cce2d68`: maximum with evidence, negative distance/unknown hash/mode
change and retention with a contradictory row that must not alter the maximum.
The new inspector reproduces 0..3 / 0..417 and the original lines in the two
preserved Windows logs of **90 patches**, without running the game again.
It is clarified that zero recorded retentions does not rule out those the
diagnostic does not emit. The runtime is not modified nor is a visual fault declared fixed.

The model-palette validation paragraph is also relocated under its original section
in `controls-and-menu-tests.md`; it does not belong to the shared presentation check.

## Reproducible transition control and host minimization (2026-10-11)

`tools/render/run_transition_control.py` is published, derived from the previous
private control: explicit manifest and hashes, fresh folders, copied ELF/IOP,
procedural card or private copy of the initial one, environment of
clean diagnostics and the same four-mode matrix. It adds thread selection,
collapsed panel and ignoring physical inputs with `GOW_PAD_SOLO_GUION=1` from #56.
It does not publish game data nor modify the runtime.

The Win32 query records each observed change of visibility/minimization
and foreground, only for the PID it launches. It does not capture images, activate
windows or use GS readback. In the built runtime's raylib, an event
wait on minimizing without `FLAG_WINDOW_ALWAYS_RUN` is confirmed; the EE continues
in another thread. It is a possible explanation for a host pause, not the demonstrated
cause of the 417 ticks: the earlier passes did not record minimization.
The background execution policy is not modified to hide the fault.

Eleven Windows tests of the tool pass in 0.13 s, including the execution
of a procedural Python child, without game or window. The following are checked: copy
without changes over the initial card, rejection of existing directories and
recursive copy, incorrect manifest, cleanup of variables by presence,
focus loss distinct from minimization and exclusive termination of the child.
The real Win32 query on our Python process finds no window and
keeps minimization as unknown. These are light checks; the game,
build or benchmark is not launched. Protocol and limits in
`shared-transition.md`; the tool is included in CI.

The CI of `e412a1f9b0579ed3dced7083ac3d7aaab140583e` passes both controls,
with the 96 patches and the eleven inspector tests. The earlier run
of merge `cce2d68` was cancelled by the new push; no result of its own
is declared for it. The Windows game control with this chain remains pending.

The launcher review detects that a valid SHA-256 written in uppercase
was rejected against Python's lowercase digest. The 64-digit format is
validated and only the hexadecimal text is normalized, keeping the identity
comparison. Twelve Windows tests pass; the new one checks acceptance of
uppercase and rejection of absent, non-textual, truncated or non-hexadecimal values.

## Preferred source of the shared texture (2026-10-11)

The static review of the GPU renderer confirms that `sourceFbp` keeps two
possible units: DISPFB pages of 8,192 bytes for the CRTC source, or TEX0
blocks of 256 bytes when `preferredSource` is used. `displayFbp` keeps
pages. The diagnostic omitted the indicator that the slots already carried:
the same raw number in both fields did not demonstrate equality of addresses.

The host diagnostic patch is extended with `preferred=%u` taken from the
`frame.usedPreferred` actually acquired. It keeps the optional condition,
a single acquisition and the limit of 4,096. It adds no readback, hash, fence or
`glFinish`; it does not modify source selection, pixels or the CPU renderer.
The inspector accepts the old and the new format, reports
unknown units/pages/blocks and keeps the indicator in the evidence of maxima
and content returns. An old omission neither contradicts nor erases a known
indicator; an explicit change under the same sequence is a conflict.

Fifteen Python tests correct. Three regressions fail with inspector
`60ce933`; invalid flags, unknown fields and duplicates are rejected.
The full chain of 96 patches passes check/application on the pinned upstream
in another fresh private worktree, without touching the built runtime or Opus.
The 90-patch native logs keep maxima 3/417 and have unknown
units in all their 2,186/1,247 rows; a missing datum is not reconstructed.

CI of `60ce9338f9c27d312a474cab40498f1cf6fdcdd7` correct in both controls.
That result precedes this change and does not validate it. Modifying the patch requires
another full Windows build and a functional control of the final HEAD.
The shared visualization and the framing inside the GS remain pending;
#51 remains a draft. Only light checks are performed while the user's
reservation of the computer continues.

## Dimension evidence in the inspector (2026-10-11)

`inspect_shared_frames.py` adds `dimension_changes`: line, sequence/render
and previous/new size. Before, it only cut the returns pattern on a size change;
now the datum is explicit in the summary. It includes samples without
hash, excludes contradictions of the same sequence and does not link epochs
separated by a mode change.

Seventeen tests correct, with two regressions that fail against `715e216`.
Reanalysing the preserved 90-patch Windows logs shows in both
a single 1×1 → 512×448 change at sequence 2, at the start. There are no later
changes among the captured samples; it does not prove correct aspect or camera.

The CI of `715e216fa72cec85e4112eb20b3fdcbba090a910` finishes green,
including the build of the new `preferred` format and the suite of the 96 patches.
([CI](https://github.com/KIexster/god-of-war-recomp/actions/runs/38114877209)).
It does not replace the pending Windows control. This adjustment only changes Python
and documentation; the game is not rebuilt or run on the reserved PC.

## Launcher private directory and source tracking (2026-10-11)

The transition control now resolves the output and allows, inside its
checkout, only `logs/`; it also accepts external folders. It keeps copies
of cards and results in the private area, like the PCSX2 reference
tool. Thirteen Windows tests pass in 0.11 s. The new one fails against `2930666`
with `mkdir` intercepted; the rejected output is not created in that control.
It does not change the runtime nor launch the game.

CI of `2930666cddd7d907a6576b2410ebed1a8695a61c` correct in both controls,
before this launcher adjustment. Check the CI of the final HEAD and keep
the Windows build of the current chain pending.

The units review produced a separate functional fix:
[PR #58](https://github.com/KIexster/god-of-war-recomp/pull/58).
`FRAME/DISPFB.FBP` uses 8,192-byte pages; `TEX0.TBP0` 256-byte blocks.
The comparison is normalized in the identification of full copies of the
frontend and in the CPU/GPU source selection without TBW. It does not change FINISH or fences.
Negative control `5f3d7de`: compiles, 591/593, only the two new ones fail.
Fix `e52527d1bf63b513facac380330b94bc2e998937`:
593/593, full remote CI correct
([38115778696](https://github.com/KIexster/god-of-war-recomp/actions/runs/38115778696)).
No test exception is added.

The fix is not integrated into this branch. Each PR has 96 patches of its own;
the joint private application of all 97 passes, without a joint build.
Windows GPU and the real transition pending. The old logs do not indicate
`preferred` and do not allow attributing the visual fault to these comparisons.
Both PRs remain drafts; the alternation and framing problems remain open.

## Comparison of GS presentation bases (2026-10-11)

The review of the shared diagnostic reveals three comparisons between
different units: `FRAME/DISPFB.FBP` in 8,192-byte pages and
`TEX0.TBP0` in 256-byte blocks. For example, 32 pages and 32 blocks
are 262,144 and 8,192 bytes; 32 pages and 1,024 blocks are the same address.
Comparing the raw values could miss a different source or accept a
copy onto its own base.

`ps2recomp-gs-source-address.patch` is added, a topic independent of
diagnostic #51. It normalizes the page by multiplying by 32 before comparing:
in the identification of the full-copy sprite, in the CPU source without TBW
and in the equivalent GPU selection. It keeps the metadata in its original
units, the existing criterion for explicit width and the CPU renderer
as reference. It does not change rasterization math, fences or FINISH.

Two game-independent regressions: the frontend uses a recording backend
to check four base pairs without rasterizing; the CPU presentation
checks selection, metadata and a procedural pixel with three cases of
zero/explicit TBW. The existing GPU control adds the two unit collisions
and compares pixels/metadata against CPU with explicit readback only
in the test. That readback is not introduced into game execution.

`5f3d7dedeced864133eb1d9887d49f892a0458a9` is published first, with the
regressions and without fixing the comparators, as a negative control in remote
CI. [Run 38115429132](https://github.com/KIexster/god-of-war-recomp/actions/runs/38115429132)
compiles correctly and passes 591 of 593 tests: exactly
`display copy compares FRAME pages with TEX0 blocks` and
`presentation source without TBW compares physical addresses` fail. No
exceptions are added to `fallos_conocidos.txt`. The CI of the fix is still pending.

The branch's own chain contains 96 patches: all pass check/application from the
pinned upstream in a fresh private tree. The #51 diagnostic also
applies afterwards, as patch 97 in a joint private check.
Configuration: 0 errors and 4 existing warnings; syntax of 10 scripts:
0 errors. Opus's checkout, verified clean at
`34cbe58`, and its VU1 patches are not modified.

Full Windows build and GPU/game control pending PC availability.
It is not known whether these base pairs appear in the real transition:
the 90-patch logs had no `preferred`. The units fault is independent of
proving that it explains the alternation or the framing; both
remain undeclared as resolved. There is no new performance measurement.

## Units control in the shared texture (2026-10-11)

Fix `e52527d1bf63b513facac380330b94bc2e998937` passes both CI controls
([38115778696](https://github.com/KIexster/god-of-war-recomp/actions/runs/38115778696)):
593/593 tests, no exceptions. It is remote validation without the game.

The user now frees the computer and confirms that Claude will not work
for 24 hours. A full build of the #51 reference is started first,
still without this fix, to compare afterwards with the integration.
The GPU control of this patch is extended to the shared path: the same pairs
32 pages/32 blocks and 32 pages/1,024 blocks with zero TBW, reading of the
texture actually acquired and comparison of its rows and metadata with CPU.
The explicit selection assertions prevent a common CPU/GPU fault
from being hidden by comparing only both renderers. The download belongs
exclusively to the procedural test, not to the game or to the host diagnostic.

The 95 patches of main plus this patch and the #51 diagnostic pass
check and application in order in another private tree: 97 in total.
This GPU extension has not yet been run; check the CI of the new HEAD
and complete the Windows build before attributing native results to it.

The same control adds 16 consecutive publications with distinct content and tick,
alternating both selections. It reuses the eight slots while
checking the pixels of each new texture against CPU; the waits and reads
exist only in the test. The extension still applies before the diagnostic
in the joint private chain of 97. It is procedural coverage pending
GPU execution, not a reproduction of the visual defect nor a benchmark.

## Current reference build and source merge (2026-10-11)

With the PC free, `scripts\2_compilar.cmd` is completed in our private runtime,
verifying the junction and keeping the previous sources. Reference:
`de5a89ad437c952a6ae384025ed602e4e62a9c1b`, 96 patches, Release, VU1 interpreter,
three parallel tasks, final code 0 and 886.33 s. The 54,542,336-byte executable
has SHA-256 `e5aae46440de86b0eeb97da91f742330ce0e95d22bbf70b368e83c44f082f0bd`.
A private copy is frozen with DLLs, manifest and build log.
The normal Windows suite passes 591/591; libpad2 also passes. The GPU control and
the new matrix with the game are still in progress/pending: the build
and the suite without the game do not vouch for the transition or the camera.

Afterwards #58, `fb8782525ed5b9ee7ac806675f4d58b1dfa5ac0d`, is integrated by merge,
keeping the documents of both branches and ordering the presentation source
before the diagnostic. The integrated chain has 97 patches. Its private
application check is correct and the CI of #58 passes both controls
([38131689081](https://github.com/KIexster/god-of-war-recomp/actions/runs/38131689081)).
This integration is not yet built on Windows; the earlier reference executable
does not include the fix nor the new shared-source checks.
Opus's checkout is not modified and remains clean. Both PRs remain drafts.

## Reference GPU suite and FINISH contract (2026-10-11)

On the same reference binary/sources `de5a89a`, 96 patches, the
Windows suite with real GPU and synchronous FINISH passes 625/625. The new diagnostic
records `preferred` and valid hashes in its procedural acquisitions.
An additional run of the whole suite with `GOW_GS_FINISH_ASINCRONO=1` passes
623/625: `FINISH and readback wait for the last compact draw state`
and `shared FINISH and reads retain barriers after held draws` fail. The full
log is kept and no exception is added.

Both tests explicitly require visible effects on FINISH's return,
a guarantee of the synchronous mode. The optional mode queues FINISH and returns earlier,
while reads keep their barrier; the project checks both
contracts separately with `tests/gs_finish_async_test.cpp` in CI. Running
the whole suite under the asynchronous option does not make those assertions valid and
may read its recorders while the worker modifies them. That run is not
declared green nor used to prove the game's stability. The
specific control must still be reproduced on Windows with the new integration.

First synchronous/RAM reference pass: 360.06 s, deliberate termination
at the limit (process code 1, launcher code 0), states
0 → 3 → 4 → 9 → 11; first report 11 at 149.78 s of the script and last 11.
Procedural card intact, without the sought VU1/GIF/exception error signatures.
Window visible from ~1 s, never observed minimized; foreground from
113.78 s. Two own external captures with the panel collapsed show scene,
Kratos and, in the later one, HUD/enemies. They are not aligned with PCSX2 nor
vouch for camera fidelity, playability or FPS. Captures and logs private.
The shared/asynchronous matrix is in progress; these results are not carried
over to the 97-patch executable pending build.

## Wait in the synchronous shared reference (2026-10-11)

The second pass of reference `de5a89a` (96 patches), synchronous FINISH and
shared texture, completes 360.05 s and ends deliberately at the limit.
The pad's last report is state 4 at 25.36 s of the script, with
`levelReady=0` and `flashReady=0`; it records no state 9 or 11 nor new reports
from the pad afterwards. This vouches for a wait with no observed progress, not the
exact RAM state at the end nor a demonstrated cause in GS/VU1/IOP.
There are no sought error signatures and the card remains intact.

The host keeps responding. The window is visible from ~1 s, is never
observed minimized and does not get foreground in this pass. Up to the quota
of 4,096: zero regressions, unknown hashes or contradictory metadata;
ticks 0..3 of distance; all sources are CRTC in pages
(`preferred=0`). A single initial dimension change 1×1 → 512×448.
There are 3,895 A–B–A returns; 3,792 correspond to the segment of the last state 4,
with two alternating hashes. They could be even/odd fields of static content;
they are not by themselves proof of an old slot or corruption.
The quota is exhausted at around 116 real seconds: it does not cover the rest of the control
nor the retentions that are never recorded.

After observing the wait for several minutes, an external 5 s sampling
is performed exclusively on own PID 13840, using `tools/perfil/muestrear.cpp`,
which selects by PID. Opus's by-name sampler is not used. The samples
lack symbols of the executable and do not identify a responsible function;
they are not published as a performance measurement. The sampling briefly suspends
threads and may disturb execution; that limit is kept alongside the log.
The next asynchronous/RAM pass is in progress. The wait must be repeated with
symbols before modifying synchronization or attributing it to the sources fix.

## Closing the current reference matrix (2026-10-11)

The four passes of `de5a89a` (96 patches) complete 360 s and end at a
deliberate limit; the private cards remain intact and the sought error
signatures do not appear. Synchronous/RAM reaches 11 at 149.78 s of the script;
asynchronous/RAM at 116.44 s and asynchronous/shared at 116.39 s. The synchronous
shared one remains a wait with no new reports after state 4 at 25.36 s.

The asynchronous shared one records 2,310 acquisitions, tick distance
0..3, zero regressions, contradictory metadata or unknown hashes.
113 A–B–A returns before the first state-3 report; none in
the 1,205 acquisitions of the last state-11 segment. Both shared ones
record only CRTC sources (`preferred=0`) and an initial change
1×1 → 512×448. The old maximum of 417 ticks is not reproduced nor is the
source selection that #58 fixes observed; do not yet attribute a real effect to it.

The window is not observed minimized in any case. Only synchronous/RAM is
in the foreground and has valid external captures: the rest keeps visual
review pending. State 11/hash and a capture do not vouch for fidelity or absence
of old images. There is no FPS measurement nor aligned comparison with PCSX2.
Full table, protocol and limits in `shared-transition.md`.

Another full build of the integrated code (97 patches) is started afterwards,
with private /O2 and PDB to investigate the wait. It must record another
commit/hash/configuration; the GPU tests of acquired source/slots and the
specific Windows control of FINISH for both contracts remain pending.
#51 remains a draft; the transition or the framing is not declared fixed.

## Windows integrated chain and FINISH contracts with GPU (2026-10-11)

Full build of 97 patches finished with code 0: code
`f51cc2cb7ee981c1cb6419926d46acc217de1f86`, 54,542,336-byte runner,
SHA-256 `ba80364535c22d728058ad98bf8182937f36c2db9ada5a11063f684c1a57add0`.
Optimized Release with /Zi and /DEBUG, VU1 interpreter, three tasks; about 902 s
between the log marks 07:58:20 and 08:13:22. The private helper fails
afterwards when saving metadata because it hides its arguments; that failure
is kept, the helper is fixed and the manifest is recovered from the log,
without repeating nor attributing a failure to the build. Flags and PDB are verified
and saved only in `E:\gowgpuprof\transition97`; the PDB is not published.

Native suite: **593/593 normal and 627/627 real GPU**, zero known failures.
It includes the new regressions of #58: physical address selection and
pixel comparison of the shared texture when reusing slots.
The separate control `gow_gs_finish_async_test` passes `default` and `async`
in fresh Windows processes: return, CSR, order and synchronized read.

`tests/gs_shared_finish_test.cpp` is added: real GPU/shared context,
without admitting CPU fallback as success; both modes pass 16 publications
with FINISH, sequences/ticks, expected source, all rows compared
with CPU and sizes 64×64 → 64×96 when reusing the eight slots. The readback
exists only in this game-free control. First run preserved: it requested
64×48, which the CPU decoder considers invalid and replaces with its default
size, while GPU uses 64×48. The premise is adjusted to valid heights;
the CPU reference is not modified nor is that run presented as equivalent.
That small-size difference does not by itself explain the 512×448 scene.

The game matrix begins with the identified 97 runner, initially
without VU1 thread/GS front. The procedural validation does not vouch for fidelity of
the scene, solution of the synchronous wait, visible alternation nor camera.
#51 remains a draft; its visual review and the CI of the next HEAD remain pending.

## Integrated matrix and wait located in Count (2026-10-11)

The 97-patch matrix is completed with the same runner `f51cc2c` and SHA-256
`ba80364535c22d728058ad98bf8182937f36c2db9ada5a11063f684c1a57add0`.
Each valid pass lasts 360 s; it ends at a deliberate limit (process 1,
launcher 0), without the sought error signatures and with the procedural card intact.
VU1 and GS front remain without their optional threads. First script report:

| FINISH / presentation | First state 11 | Last state |
|---|---:|---:|
| Asynchronous / shared | 135.35 s | 11 |
| Synchronous / shared | Not observed | 4, at 25.31 s |
| Synchronous / RAM | 126.78 s | 11 |
| Asynchronous / RAM, isolated repetition | 121.40 s | 11 |

These times are script reports, not comparable load times nor FPS.
The synchronous/RAM pass was minimized for a good part of the control and
its last ~30 s coincided, through a launcher coordination error, with
another own asynchronous/RAM instance. The entry into 11 happened before the
overlap, but a complete isolated pass is not claimed. Only the new
instance was stopped through its STOP file at 34.35 s and asynchronous/RAM was repeated
without overlap. Both logs are kept; the stop is not presented as
a hang. No valid capture of the minimized window was obtained.

Asynchronous/shared: 1,986 acquisitions, 20 A–B–A returns, none in the
segments of the last state 4 or 11; 1,056 acquisitions under the last state 11.
Tick distance 0..6. Synchronous/shared waits again without new reports
after state 4: it exhausts 4,096 records, with 3,896 A–B–A (3,800 in segment 4),
distance 0..3. In both: zero regressions, contradictory metadata or unknown
hashes; one initial 1×1 → 512×448 change and always `preferred=0`, CRTC
source in pages. The synchronous quota leaves the rest of the pass unobserved;
the alternation of two hashes could correspond to fields of a still scene.

Private external captures of our window's surface through
PrintWindow show HUD, Kratos and enemies in asynchronous/shared; two
synchronous captures show a flames/close-up scene without the expected
progress. PID, path, visibility and absence of minimization are verified before
capturing. The capture request may disturb that instant; the images
are not aligned with acquired sequences nor with PCSX2. They do not prove correct camera,
absence of old images, equivalence of the game's pixels or performance.

Two external 5 s samplings of own PID 12184, with private PDB, find
the EE executor walking `sub_00185A20` and IOP work; the GS worker waits for
commands. The second resolves lines of the loop 0x185D88..0x185DD8: it queries
COP0.Count to check a deadline. The current translation reads `ctx->cop0_count`,
but the EE cycle accounting does not update that field. It is a
pre-existing defect in the counter's semantics and a concrete clue for this wait;
it does not yet demonstrate that fixing it resolves the transition. The sampling briefly
suspends threads, and is not used as a benchmark nor as proof of a GL block.

A separate Count patch is being prepared, with game-free tests of cycles, wrap,
contexts, reset and MFC0/MTC0 translation. It must compile, demonstrate regressions
and fully regenerate the runner before attributing any effect to it.
It does not modify Opus's files or processes; its checkout was verified clean.
The CI of the published HEAD `10a7bec` is green. #51 remains a draft: resolving
the wait and comparing the scene/camera in an aligned way remain pending.

## COP0.Count regressions to investigate a wait (2026-10-11)

On the GS diagnostic branch, two full controls with synchronous shared
presentation stop reporting progress after state 4. The private sampling
with symbols finds EE work in a loop that queries Count.
The current translation reads `ctx->cop0_count`, but EE cycles do not update it.
This problem predates the recent VU1 changes: it is not attributed to Opus.

A separate patch is added with four game-free regressions: bounded advance and polling,
wrap/writes between contexts, reset and MFC0/MTC0 emission.
The first commit is a deliberate negative control, with compatible interfaces
and the earlier motionless read; it must compile and fail those expectations.
The per-cycle implementation will be published afterwards, keeping this history.

The effect on the transition has not yet been demonstrated. Validation
requires CI of the fixed HEAD, a full Windows build to regenerate
the reads and repetition with the game. FINISH and fences are not modified, camera
fidelity, general stability or FPS are not claimed, and the COP0.Compare
interrupt is not implemented here. Semantic reference of the counter:
[PCSX2 COP0.cpp](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/COP0.cpp).

The shared branch then integrates the positive implementation of #59:
runtime-global Count lazily updated by EE cycles, consecutive reads
with a minimum advance of one, 32-bit wrap, a write that changes
the base and reset together with the clock. MFC0 keeps sign extension and
performs the read even with $zero destination, outside the macro that discards
that register. It uses no wall clock nor alters timers, VU1, FINISH or
fences. The 98-patch chain applies in a fresh private tree; configuration
and PowerShell syntax pass (four existing warnings). Build, suite and
functional control of this code remain pending. A full private build
is started, regenerating C++; the frozen 97 runner remains separate.

The initial CI of integration `3690bc9` also fails due to the header missing
from the test, not due to an executed regression. The positive patch is updated
with `ps2recomp/types.h`. The private build started with that HEAD is
deliberately stopped at 333.15 s, verifying the PID of the own wrapper and
its descendants; an exit-1 manifest and partial sources are kept.
There is no validated new runner from that attempt. The full build is
restarted with the corrected patch, in another artifacts folder. Other
collaborators' processes are not stopped nor are their files modified.

First negative CI `e7e8914`/38137005221: it fails compiling the new test
because `ps2recomp/types.h` is missing (Instruction/Symbol/Section incomplete).
The header is added and it is repeated. That run does not vouch for behavior
regressions; the negative control must get to run the suite.

The corrected negative control `d496189` compiles and runs the suite in
[CI 38137285316](https://github.com/KIexster/god-of-war-recomp/actions/runs/38137285316):
591/595 pass; only the four new Count regressions fail.
No exceptions are added to `fallos_conocidos.txt`. The fix is published
afterwards: global Count lazily updated by EE cycles, minimum of one
in consecutive reads of the same block, 32-bit wrap, write/reset
of its base and MFC0/MTC0 emission through the runtime. MFC0 to $zero explicitly
performs the read, because SET_GPR_S32 skips evaluating the value there.
MFC0's sign extension is kept. It uses no host clock nor adds
Compare interrupts. The positive CI and native control remain pending.

The positive `5c64a2248f52ffb09921d439137116901d638012` passes
[CI 38137693634](https://github.com/KIexster/god-of-war-recomp/actions/runs/38137693634):
595/595, configuration, syntax, application of the 96 patches and complete
procedural controls correct. The 98 integration into #51, `f36936e`,
also passes 597/597 in CI. It remains a draft until Windows
and the transition are checked with the freshly generated runner; the wait is not declared resolved.

## Windows 98-patch runner with Count (2026-10-11)

Full build finished with code 0 from
`f36936e067aa283e4567e3b16700cfe4e546b629`: 898.79 s, 98 patches,
VU1 interpreter and three tasks. 54,542,848-byte runner, SHA-256
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`.
/O2 /Ob2 /DNDEBUG /Zi and link /DEBUG /OPT:REF /OPT:ICF are verified;
177,598,464-byte private PDB. Manifest/binary frozen in
`E:\gowgpuprof\transition98_validating`. The Count reads in the sampled
loop have been regenerated with the runtime API; the 97 runner is not reused.

The CI of that HEAD passes 597/597. The final documentation HEAD of #59, `00d5575`,
also passes full CI (38138091541). It is integrated by merge into #51,
keeping both records in the documentation conflict; the positive
patch is identical to the one used in the build and does not change the chain.
The build of the native tests is in progress. The transition must still
be repeated and it is not claimed that the Count defect explains the framing,
alternation or all the low FPS. Opus's measurements remain his:
he documents 11.6 FPS by default and 25.2 with his optimized configuration; these
controls with interpreter/threads off/hash/diagnostic are not comparable.

## Native Count suite and new game control (2026-10-11)

With the identified 98 runner and its sources `f36936e`, **597/597
normal and 631/631 real GPU** pass on Windows, zero known failures. Hash of the
test executable:
`8741cc50b8a5db8587dd989bd94b143bbda2a9f490bad9764ec84e62f2de4607`.
The four separate processes pass: FINISH/CSR/order/read `default|async`
and FINISH/pixels of the texture actually acquired `default|async`, each
with its 16 publications and slot reuse. The global
suite is not repeated under asynchronous FINISH nor are the recorders' contracts changed.

A new 360 s synchronous/shared pass begins with the same procedural card,
script, variables and threads off, after finishing the
builds and tests. It must check whether the wait observed in
96 and 97 persists; the earlier successes do not yet count it as resolved.

## First synchronous shared transition with Count (2026-10-11)

The 98 runner identified above completes 360.08 s, deliberate exit
at the limit (process 1/launcher 0), procedural card intact and no sought
error signature. It reports 0 → 3 → 4 → 11; first 11 at 145.14 s of the
script and last 11. In 96/97 the same case stopped reporting after 4 at ~25 s;
in this run that wait is overcome. Time is not used as a benchmark.
The window is never observed minimized; foreground between ~11 and ~40 s.

1,910 acquisitions: zero regressions, contradictory metadata or unknown
hashes; 25 A–B–A returns, none in the segments of the last state 4/11.
There are 952 acquisitions in segment 11. CRTC source only (`preferred=0`),
one initial 1×1 → 512×448 change. Tick distance 0..34; maximum at sequence
3 before the pad's first report. From state 0, maximum 3; in segments
4 and 11, maximum 1. This classification does not align frames nor prove sustained
latency; the diagnostic records only new acquisitions.

Three private external captures of the own surface show the intro,
enemies and then HUD/Kratos/enemy at the docks. PID, path,
visibility and absence of minimization verified, without activating the window. Their requests
may disturb that instant, and they are not aligned with PCSX2 or the GS sequence.
State 11/captures do not certify playability, camera fidelity nor absence
of alternation. An isolated asynchronous/shared repetition is started afterwards,
with the same runner and protocol. Both PRs remain drafts until the
validation and CI of the final HEAD are closed; hangs with threads remain unproven.

## Asynchronous shared repetition with Count (2026-10-11)

The same 98 runner completes 360.04 s without overlapping another instance. Deliberate
limit (process 1/launcher 0), card intact, no sought error signatures;
0 → 3 → 4 → 11, first 11 at 116.40 s and last 11. Window never observed
minimized; foreground only between ~344 and ~353 s. Two own external captures
show enemies and then HUD/Kratos/combat at the docks;
keep the capture disturbance and the absence of PCSX2/GS sequence alignment in mind.

2,325 acquisitions, zero regressions, contradictory metadata or unknown
hashes, 140 A–B–A: none in the segments of the last state 4/11.
1,198 acquisitions under the last state 11. Tick distance 0..3,
maximum 1 in segment 11; initial dimensions 1×1 → 512×448 and
CRTC source in pages (`preferred=0`) in all rows. This does not rule out
visible alternation, unrecorded retentions nor longer hangs/with threads.

Both shared presentations overcome the transition in these passes;
the Count fix has negative/positive regressions and native control,
without changing FINISH/fences. The two RAM controls of 98 remain to be closed and
the camera/scene compared in an aligned way before considering #51 closed.
Synchronous/RAM isolated is started after finishing asynchronous/shared.
## Controls incorporated from the #59 fix (2026-10-11)

The validation record of the Count branch is kept below,
incorporated by merge without rewriting its history nor deleting the
earlier controls. Its final HEAD `ab89804` passed full CI and #59 was merged at
`cee659a733be0ae9db4764ad99b4e570e9af7849`. The pending items that follow
describe the moment of each control; #51 keeps the visual investigation.

Native control of the 98 integration into #51, code `f36936e`: full Windows build,
898.79 s, exit 0, runner SHA-256
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`.
597/597 normal and 631/631 real GPU correct, including the four regressions
of Count. Separate controls of FINISH and of acquired-texture pixels
pass both modes. The integration is checked with two additional GS patches,
not an independent executable of this branch. The new transition begins
after finishing builds and tests; the functional effect remains pending.

First synchronous/shared pass with that runner: 360.08 s, deliberate
termination at the limit, private card intact and no sought error signature.
It reports state 11 at 145.14 s; the same case in the earlier 96/97 chains
stopped reporting after 4 at ~25 s. The wait is overcome in this control.
Own external captures show intro, enemies and finally HUD/Kratos
at the docks, without PCSX2/GS-sequence alignment and with capture disturbance.
Playability, camera fidelity, absence of alternation or FPS are not claimed.
An isolated asynchronous/shared pass is repeated afterwards; that pass remains to be completed and
the CI of the final HEAD checked before closing the review of this fix.

The asynchronous/shared repetition with the same runner ends at 360.04 s:
first report 11 at 116.40 s, last 11, card intact and no sought error signatures;
deliberate exit at the limit. Two own captures show scene
and then HUD/Kratos/combat, without aligned comparison nor FPS measurement.
2,325 acquisitions, zero regressions/inconsistencies/unknown hash,
140 A–B–A and none in segments 4/11. The synchronous pass also completed 360 s
and overcame the wait of the earlier chains. Review of the change: global
EE state, wrap, base write/reset, sign extension and effect with
$zero destination; without modifying FINISH/fences nor Opus's checkout.
The CI of the last documentation HEAD must pass before merging this topic.
The camera/alternation validation and the threads remain in #51.

## Closing the isolated 98 matrix and Count publication (2026-10-11)

Both RAM passes are completed with the same runner `f36936e`, SHA-256
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`:
synchronous 360.04 s, first report 11 at 126.41 s; asynchronous 360.05 s,
first 11 at 121.31 s. Last state 11 in both, deliberate exit at the
limit (process 1/launcher 0), cards intact and no sought error
signature. Not minimized; foreground from ~21/~41 s respectively.
One own capture of each RAM shows scene/enemies or HUD/Kratos at
the docks, without PCSX2/GS-frame alignment and with capture disturbance.

The new four-case matrix ends without overlapping games/build;
the two shared ones reached 11 at 145.14/116.40 s. The synchronous shared
wait of the 96/97 chains is overcome with the updated counter. This
is not equivalent to declaring correct camera, absence of alternation or better FPS.
Matrix and limits in `shared-transition.md`; the hashes do not certify
equal pixels and do not record retentions. VU1 in a thread is started separately,
still with interpreter and hash/diagnostic: functional control, not a benchmark.

[PR #59](https://github.com/KIexster/god-of-war-recomp/pull/59) reviewed and
merged by merge at `cee659a733be0ae9db4764ad99b4e570e9af7849`, after
[full CI of the final HEAD `ab89804`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38139636066).
#51 and #58 integrate that main by merge keeping both records; order
Count → GS addresses → diagnostic. Verified: the 97 patches of #58
match in order/content the compiled prefix of #51, and the 98 chain
of #51 remains identical to the runner's code. Opus was not modified. #51 remains
a draft for pending visual comparison and threads; check the CI of each HEAD.
## Integration and final review of GS units (2026-10-11)

The Count fix #59 was merged at `cee659a` after full CI of HEAD
`ab89804`. This branch integrates main by merge, preserving both investigations
and applying Count before the GS addresses patch: 97 patches. Branch
#51 already built that combination plus the host diagnostic (98) on Windows
from `f36936e`, runner SHA-256
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`.
597/597 normal, 631/631 real GPU and the separate controls of both forms
of FINISH/acquired textures pass. No later code change is attributed
to the executable: the Count and addresses patches remain identical.

The synchronous shared wait is overcome with Count; this units topic does not
fix it. The game's selection remains `preferred=0`, without proving
that the bases fix is causal for camera/alternation. The review checks
the three page/block conversions, explicit/zero TBW, metadata and the
negative/positive CPU and GPU controls. The physical semantics of both pairs
and the reuse of eight slots are covered without altering the
math of the CPU renderer nor FINISH/fences. The CI of the final
HEAD after this merge remains to be verified before merging #58.

## GS publication, controls with threads and new window (2026-10-11)

#58 is merged by merge at `fac216674e9d763ad418d9c1a9c9ce05088955d1`,
after [full CI of the final HEAD `957f9da`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38140210658).
#51 integrates the new main by merge (`a64ed52`), preserving records
and the already-built 98 chain. Both fixes (#58/#59) are published
in main; #51 remains a draft for pending visual investigation/stability.

Control 98 asynchronous/shared with VU1 in a thread, GS front off:
360.04 s at the limit, first report 11 at 80.90 s, last 11, card intact,
no sought error signatures or minimization; private HUD/Kratos/enemies capture
without alignment. The quota of 4,096 is exhausted before report 11 (`hostTick=4136`):
3,064 A–B–A, zero regressions/inconsistencies/unknown hash, all before
the game. Do not use that record to certify the presentation of state 11.

VU1+GS front reaches 11 at 80.83 s but closes earlier: 228.17 s, exit 0,
`process_exit`, no determined cause. Last 11, card intact, no sought
error/minimization signatures or valid own capture; it does not complete the 360 s
nor prove stability. Quota also exhausted before 11, 3,045 A–B–A. It is kept
as incomplete and must be repeated. Both controls use interpreter and hash;
their times are not FPS nor equivalence with Opus's optimized measurements.

A new diagnostic window patch is implemented, without varying Acquire,
FINISH/fences/readback nor the 4,096 limit: it allows starting from an
explicit hostTick to observe the game with threads. `PS2X_GS_PRESENT_DIAG_FROM_TICK`,
absent/invalid → 0; launcher `--diag-from-tick`, uint64 range validated before
writes. Three reduced MiniTest/MSVC regressions pass; negative with
the compatible previous semantics fails exactly two (1/3), without claiming a
complete suite. 14 Python tests of the launcher and 17 of the inspector correct,
configuration/syntax correct, new independent application on top of the
earlier 98. Chain 99 pending a full Windows build,
native suite/CI and repetition of the game with the window. The new
patch is not attributed to the existing executable nor is framing/alternation declared resolved.

## Full native chain 99 and fast boot disabled (2026-10-11)
Code `3dbac1a442add16518b0504975bfa715f1b32dc4`: full Windows build,
99 patches, exit code 0 in 1,005.59 s; VU1 interpreter, optimized Release/
private symbols/three tasks. Runner SHA-256
`cf063d2f03a1a78f455a9ff57a1378cd4a1ddaf71e6d279d305b34663b96fa07`.
600/600 normal and 634/634 real GPU passed; four separate controls
FINISH/read and FINISH/acquired texture `default|async`, all exit code 0.
[CI of the same HEAD passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38152876084).
The diagnostic window is already in this executable; the game run still has to be repeated.

Override review: `GOW_FAST_BOOT=0` does not enable the shortcut, but it installed
the probes merely by being present and emitted animation/flash-ready in the
earlier controls. Only its installation condition is fixed so that it requires `1`,
keeping the explicit diagnostics and original calls. It is not a
camera fix or an FPS measurement. The previous runner does not include
this `src/` change: it needs a private quick rebuild, a new commit/hash
and a control that checks the absence of those labels. Opus remains
clean and its checkout is not modified; main integrated by merge.

The Windows control through Computer Use fails to connect to its native pipe
(file missing); module import succeeded, two light queries
failed, no input sent. CLI/build/tests available.
That failure is not used as visual evidence nor attributed to the game.

## First 99 control with FAST_BOOT=0 isolated (2026-10-11)

Overrides rebuilt on the full 99 chain from `a37cd85`, exit code 0;
runner SHA-256 `a4ec4365273903d525ce19ecade3fb423fb871c5628a84e695b33ac777ca3598`,
[CI of the same HEAD green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38154314459).
Asynchronous/shared without threads, diagnostic from tick 0, complete 360.06 s by
limit; report 11 from 154.02 s, last 11, card intact, none of the searched
error signatures. Absence of animation/flash-ready probes is verified.
Window visible/never minimized, always without foreground; no own capture.

2,046 acquisitions, 27 A-B-A only before report 3, zero regressions/
inconsistencies/unknown hash. Under last report 11 there are 983 acquisitions
and no A-B-A; CRTC source in all. Maximum tick distance 37 at boot,
5 in segment 4 and 1 in 11. Details in TRANSICION_COMPARTIDA.md; FPS is not compared
and no visual solution is declared. Another private VU1 control is started on a
thread with a late window from 6000; front GS will be repeated afterwards, separately.

## Game acquisitions with VU1 on a thread (2026-10-11)

Same 99 runner/overrides `a37cd85`, asynchronous/shared, VU1 on a thread
and front GS off, window from 6000: 360.06 s complete by limit,
report 11 from 81.05 s, last 11, card intact. None of the searched error
signatures nor animation/flash-ready probes; not minimized, no foreground
or own capture, no overlaps. The first record is hostTick=6000,
frameTick=5999, seq/render=5880. 4,096 acquisitions all in segment 11, CRTC
source, 512×448/valid hash, zero regressions/inconsistencies/dimension changes,
tick distance 0..2. The filter now observes gameplay, unlike 98.

The 3,009 A-B-A returns alternate frameTick parity. The inspector keeps
the three ticks and adds the parity classification without hiding returns;
20 tests pass. This is compatible with alternating fields (the procedural GPU test
compares different fields with invariant VRAM against CPU), but
it does not identify SMODE2 nor demonstrate cause/corruption or absence of
old images. Keep hash/quota limits and camera separate. The
VU1+front GS repetition of 360 s with window from 6000 is started in isolation; still pending.

## Complete 99 control with both threads (2026-10-11)

Asynchronous/shared repetition with VU1+GS front and window from 6000,
same runner `a37cd85`: complete 360.04 s by limit, report 11 from 80.97 s,
last 11, card intact. There are no searched error signatures nor animation/
flash-ready probes; not minimized, no foreground/own capture and no overlap.
The shutdown of 98 at 228.17 s is not reproduced in this pass. A correct
repetition does not determine its cause nor prove prolonged stability.

4,096 acquisitions in segment 11, first hostTick=6000/frameTick=5999,
seq/render=5933. Zero regressions/inconsistencies/unknown hash or dimension
changes; 512×448/CRTC source, tick distance 0..1. The 3,506 A-B-A
alternate parity, compatible with fields but with no SMODE2 recorded and no proof
of cause. The CI of `6f30f5c` is green. The three finite passes of 99 have
already finished; aligned visual comparison/framing and longer duration
remain pending. #51 keeps a draft. Next control: SMODE2 of the acquired texture,
with a regression that rules out confusing it with the current CRTC. Details and limits
in TRANSICION_COMPARTIDA.md. No game data or FPS are published.

## Preparing acquired SMODE2, without changing presentation (2026-10-11)

The thousands of gameplay A-B-A returns in 99 alternate parity, but the
mode of the request was missing. New patch by topic `ps2recomp-gs-acquired-mode-diag.patch`:
store the full SMODE2 in the published slot and log it from the acquired
Frame. Do not infer it from the current CRTC nor add readback/Acquire/hash/barriers.
A real GPU regression checks fields/frame/progressive, pixels against CPU
and new/retained metadata; execution pending. The branch moves to 100 patches,
with independent application of the new one correct and syntax without errors.

Inspector 24/24 tests: optional decimal uint64 field, consistent metadata,
compatibility with previous logs and three modes per return, without hiding A-B-A.
The acquisitions of 99 do not vouch for this runtime; they need another full
build, suite/GPU/negative and a control with the game. #51 stays a draft.
The framing investigation is kept separate and no math is modified.

## First native control of 100: height difference in frame mode (2026-10-11)

Full Windows build from `4a000c48e2d111637a77318eb509dd88f35d653d`,
100 patches, exit code 0 in 943.29 s. Frozen runner SHA-256
`fb46a87ac6d80a600f8662ae3ee6b74bbb5b37b84f1cc10fa0eb0b0f3d4367b5`,
optimized Release with private symbols, VU1 interpreter. [CI of the same HEAD
passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38156407391).
600/600 normal; **634/635 real GPU: the new SMODE2 test fails**, due to a
different logical height and an empty CPU comparison. The later contracts and
the game with this runner are not run; it is not presented as full validation.

The review locates the difference in the `SMODE2=0x403` case: with DISPLAY of
64×128, GPU halves the height and CPU keeps the full height. It is
earlier composition code, unchanged in the metadata patch; it is still
not determined which output should be used nor whether the game uses that mode in the
transition. It is not attributed to framing nor is the renderer changed to make
a diagnostic test pass.

The scope of the new regression is made precise: all modes keep the
full SMODE2 in a truly acquired and retained texture; fields and
progressive keep a comparison of all rows against CPU. In frame
mode the CPU/GPU dimension is logged and only texture/metadata are validated,
with its equivalence explicitly left pending. The case is kept,
without adding exceptions to `fallos_conocidos.txt` nor hiding the initial result.
The corrected patch applies on an independent base of 99. It requires another
full build, suite/meaningful negative and game controls;
#51 stays a draft. The height difference is a separate investigation.

## SMODE2 diagnostic of 100 validated natively (2026-10-11)

Reviewed full build of `383c6b65986ffe2cddebaed987d9132ea791d100`,
exit code 0 in 928.11 s, runner SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`.
[CI of the same code green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38157988334).
Windows: 600/600 normal, 635/635 GPU and four independent
FINISH/read/acquired-texture contracts passed, with no known failures. The
objects of the private controls are renewed for the new Frame layout.

The private negative forces only the metadata to zero, keeps the API and compiles:
634/635, exactly the new SMODE2 case fails. Restoring the positive
file and another GPU suite: 635/635. The runner stays positive and frozen
during that control; the game is not run on the negative variant.
The test distinguishes the acquired/retained texture mode from the later request's.

The frame-case discrepancy is also measured: CPU 64×128, GPU texture 64×64
with SMODE2=1027. Its equivalence remains pending; fields/progressive do
keep a comparison of all rows. The renderer is not changed to close
that difference nor is it attributed to the game scene without logging its mode.
Next step: controls of 100 without threads, with VU1 and with both threads, late
window and private cards. #51 stays a draft until the validation of the
new diagnostic and the final CI close. Camera/alternation are not declared resolved.

## First game control of 100: fields in the acquired texture (2026-10-11)

Runner `383c6b6`/SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared without threads, window from 0: 360.06 s complete by limit,
first report 11 at 133.85 s, last 11, card intact. None of the searched error
signatures nor animation/flash-ready probes; never minimized, foreground
between 17.12 and 41.29 s, no own capture nor overlaps. Details in
TRANSICION_COMPARTIDA.md; a normal shutdown or visual equivalence is not claimed.

1,955 acquisitions, with no regressions/inconsistencies/unknown hash; six
A-B-A only before segments 4/11, all alternate parity and have field
mode. The 1,063 acquisitions of segment 11 log SMODE2=2227921 (`&3=1`),
512×448/CRTC source, no A-B-A and tick distance 0..1. The frame case
with different height (`&3=3`) does not correspond to these samples. This does not prove
the cause of the framing nor rule out old images outside the log.

[CI `6a53774` green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38159575279).
Another private pass continues with VU1 only and window from 6000; then both
threads. Keep #51 as a draft during the pending validation, without declaring FPS.

## VU1 only of 100: late window with field mode confirmed (2026-10-11)

Same runner `383c6b6`/SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared, VU1 on a thread, GS front 0 and logging from 6000. Completes
360.04 s by limit, first report 11 at 80.98 s and last 11 at 357.24 s.
Card intact, no searched error signatures nor old probes; window
visible/not minimized/no foreground according to the monitor. No own capture.

4,096 acquisitions of segment 11, all SMODE2=2227921 (`&3=1`, fields),
512×448/CRTC source/valid hash. 3,562 A-B-A: all alternate parity and have
field mode in the three textures. No regressions/inconsistencies or dimension
changes; tick distance 0..1. The fields hypothesis gains support,
but it does not demonstrate a visual cause nor absence of old images; the quota
does not cover the whole pass. Framing/FPS/equivalence with PCSX2 not vouched for.

[CI `e3678cb` green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38160245742).
Another isolated pass with both threads is in progress; do not use it yet as validation.
The earlier early exits and their pending causes are kept.

## Both threads of 100 complete; diagnostic ready for final review (2026-10-11)

Same runner `383c6b6`/SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared, VU1+GS front on a thread, window from 6000: 360.05 s
complete by limit, first report 11 at 80.92 s and last 11 at 357.49 s.
Card intact, no searched error signatures nor old probes; window
visible/not minimized/no foreground according to the monitor, no own capture.

4,096 acquisitions of segment 11, all SMODE2=2227921 (`&3=1`, fields),
512×448/CRTC source/valid hash. 3,542 A-B-A: all alternate parity and have
field mode in the three textures. No regressions/inconsistencies/dimension
changes; tick distance 0..1. The early exit of 98 is not
reproduced here, but its cause and prolonged stability remain pending.

The three passes of 100, full build, normal/GPU suite, meaningful negative
restored and four contracts close the functional validation
of the instrumentation of #51. [CI `bae5d74` green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38160854972).
Manual review of the change and CI of the final HEAD precede marking it ready and
merging it. The earlier references to a draft due to visual comparison are not
turned into a fidelity claim: #51 only diagnoses; it does not fix
the framing nor demonstrate absence of old content. Details in
TRANSICION_COMPARTIDA.md. Next topic: explicit, bounded capture of the
acquired texture to compare fields; keep the pixels private.

## #51 merged; next topic: pixels of the acquired pool (2026-10-11)

#51 merged in `05421940617e5ce69889600d9eb727b3c36c0b3b`, manual review,
earlier native/functional validations and [CI of its final HEAD `10edb76`
passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38161351218).
The instrumentation is closed; framing, the visual cause of A-B-A and prolonged
stability are not declared resolved.

Next branch with a separate patch `ps2recomp-gs-host-acquired-capture.patch`:
explicit, bounded download of the texture of that same pool, RGBA PNG and
metadata, with no VRAM query nor another Acquire. Disabled by default,
independent of the #51 diagnostic; at most 16 attempts, no overwriting.
Its cost prevents using it as a benchmark. The launcher's `--capture-acquired 6`
prepares the private folder and window from `--diag-from-tick`. Protocol and
variables in TRANSICION_COMPARTIDA.md.

A real GPU regression prepared to demonstrate that changing VRAM to B after
acquiring A does not change the PNG of A; compare all its pixels and then B.
C++20 syntax and independent application correct; launcher 17/17,
configuration 0 errors/4 existing warnings, PowerShell 0 errors.
Pending: full build of 101, native/negative/restoration, CI and
game captures. Do not attribute them to the runner of 100 nor change math.

## Pool capture validated with real GPU and pixel negative (2026-10-11)

Full build of 101 from `394779a6dca0fd8dcaf7415e06ad048fdd9ad7f8`,
exit code 0 in 916.19 s, runner SHA-256
`63e6a576307675f34b70e4671a5b34de30219627a2ca2a3a362c182effd27040`,
54,552,576 bytes, optimized Release/private symbols/VU1 interpreter.
[CI of the same code green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38161970774).
Windows 600/600 normal, 636/636 GPU and four FINISH contracts passed.
The PNG of A keeps all its pixels even though VRAM already holds B; the test
also publishes/exports B and verifies metadata, window/quota/retentions and
rejection of overwriting. The frame-mode height discrepancy remains open.

API-compatible negative: magenta image of the same size instead of reading
the texture; only the tests are rebuilt, without touching/running the runner. 635/636,
single failure of the new capture case due to different pixels. Positive file
fully restored and another GPU suite: 636/636. Hash of the restored source equal
to the backup; current runner and frozen copy identical.

Game pass without threads, six captures from 1500, in progress. Then VU1
from 6000; do not attribute results yet nor resolve framing/alternation.
Register private PNG/JSON against the acquisitions before comparing bytes;
no PCSX2 equivalence nor FPS. Identity and limits in TRANSICION_COMPARTIDA.md.

## Real captures: RGBA A-B-A equality in field mode (2026-10-11)

Two complete passes of 101, same runner `394779a`/SHA-256
`63e6a576307675f34b70e4671a5b34de30219627a2ca2a3a362c182effd27040`,
asynchronous/shared, cards intact and none of the searched error signatures:
without threads/from 1500 (360.07 s, report 11 from 131.78 s) and VU1 only/from
6000 (360.05 s, report 11 from 80.83 s). The first case was minimized
between 44.22 and 156.01 s; later captures, non-constant condition, repeat.
The second is neither minimized nor brought to the foreground according to the monitor.

Both save six RGBA PNGs and six JSONs that match the metadata of
their acquisition in the log; each image duplicates its 224 row pairs. In the
first one all contents are different, with no A-B-A in 643 records of
the window. In VU1 there are 4,096 records/3,204 A-B-A, all fields/alternating
parity, with no regressions/inconsistencies; tick distance 0..2. The PNGs
of ticks 5999/6001 are byte-for-byte identical and the one of 6000 is different:
finite confirmation of the A-B-A in pixels, in addition to the hash. Another odd pair
6003/6005 is identical. The first images reviewed show Kratos/deck
in the same camera within each triplet; not an alternating menu there.

It does not prove VRAM freshness, the cause of the original symptom, absence outside the
window, CPU/PCSX2 equivalence or correct framing. Nor are the
poses/cameras of windows 1500 and 6000 comparable between passes. [CI `ce23d73` green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38163566080).
Another repetition without threads is in progress; #60 stays a draft until it is closed and
the final CI is checked. Private pixels/JSON, no math changes or FPS.

## Repetition without minimization: functional control of #60 closed (2026-10-11)

Third pass of 101 with the same runner `394779a`/previous hash,
asynchronous/shared without threads, from 1500: 360.04 s by limit, first
report 11 at 116.48 s and last 11; card intact, none of the searched error
signatures nor old probes. The monitor records no minimization. 870
field acquisitions, with no regressions/inconsistencies/A-B-A/dimension
changes, tick distance 0. Six complete PNG/JSON correlated
against their acquisitions (1462..1467, ticks 1500..1505), different RGBA
contents and 224/224 duplicated row pairs in each image.

Visual review of the first two: same view of Kratos/deck within the
pair. A tick coinciding between passes does not align camera/animation,
because the script depends on the host clock; do not infer causes by comparing
those poses. The earlier minimization is kept as a separate limitation.

The full build, native/restored negative, contracts and three
passes close the validation of the optional capture of #60. Manual review
of the use of the Acquire pool correct; [CI `9332c1b` green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38164770068).
Check the CI of the final HEAD before merging. Framing, old content,
frame mode or prolonged stability are not declared resolved. Next
step: relate camera/animation to the scene actually drawn and an
aligned reference; avoid correcting matrices based on observations of different
instants. Details and hash in TRANSICION_COMPARTIDA.md; pixels private.

## #60 merged; camera, GS replay and model symptoms (2026-10-11)

#60 merged in `f41be4eefc31c0ebde3500b4c3b02f3815e9cfd9`: manual review,
full build and earlier controls; [CI of the final HEAD `8530914`
passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38175464970)
and [CI of the merge passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38175870557).
The optional capture is closed, without attributing the fix of the visual fault to it.
The runner is still `394779a`/101, SHA-256
`63e6a576307675f34b70e4671a5b34de30219627a2ca2a3a362c182effd27040`.
It includes #55 and later changes; these passes with the interpreter, probes and
threads disabled do not reproduce Opus's performance configuration.

Synchronous/shared control, without threads, with the existing camera
and animation probes: 360.05 s by limit, first report 11 at 126.83 s, card intact,
none of the searched error signatures. Late minimization from 325.28 s; do not claim
a constant window. 268 complete and finite camera samples. The main one
of 11 uses a local matrix (`joint=0xFFFF`), with 32 distinct positions and matrices
equal to the client's. Maximum world residual by inverse 0.0002045 and
combined 0.0001827: numerical description, not a fidelity tolerance. This does not
identify the correct camera. The saved PCSX2 references correspond
to menu/intro (states 3/4), not to an aligned gameplay 11.

Another synchronous/RAM pass, without threads nor hash/probes/acquired captures, uses
only `5:start,12:x,20:x`; it **changes the script** with respect to earlier controls.
240.04 s by limit, first report 11 at 126.29 s, card intact, none of the searched
error signatures. GS trace from real TEXFLUSH at 150.028 s, complete by
byte budget before the requested second: 54,535,090 bytes, six
Present and 145,452 Submit. Trace/pixels/game data remain private.

Repetition of the **prefix up to the first Present**, record 12795/12693 draws,
with native tools linked to runtime 101. CPU: two passes identical
to each other and to CPU in 4 MiB of VRAM, state and image. Requested compute:
two identical passes, but 326,270 VRAM bytes different from CPU and a
different image. Hardware: two passes with 7472 primitives/zero tiles differ
from each other in 1796 VRAM bytes and 1916 visible RGBA bytes, with the same state.
The first hardware pass uses a mixed path and is excluded from that comparison.

The existing experimental protection `--snapshot-feedback` freezes the source
per Submit: three hardware passes, all with zero tiles, are identical in
VRAM/state/RGBA; their RGB matches compute in this sample. **It is not a
fix enabled by default nor PS2 cache emulation**, it does not resolve the
CPU difference and does not prove the cause of the framing or of the original symptom.
Protected lockstep compute finds earlier a two-byte CPU divergence
in an untextured triangle (record 76/draw 73); separate that discrepancy from
the hardware variation. The rest of the trace and its original End are not validated
with this prefix. None of this measures FPS nor demonstrates PCSX2 fidelity.

The user widens the symptom: movements like spasms and deformations of
models/animations of Kratos and enemies, in addition to the framing. It is a
reported observation, still without an own aligned comparison. In the next
review observe a movement sequence: limbs, shape and position,
not only isolated captures. Prioritize real skinning inputs/outputs and their
indices, then submission to VU/GS. The palette read on entering ProcessModel precedes
the later computation: finite values there do not rule out this fault. Read
RAM/scratchpad with separate limits, respect checkpoints and observe only
real returns. Do not correct matrices nor enable protections by intuition.

`GOW_SKIN_DIAG=1` is prepared, a post-return observation of both variants and a read
of the destination a2 separate from palette a1. Limits, fields and discarding of pauses
in CONTROLES.md. Procedural Windows/MSVC tests with /W4 /WX and C++20
syntax of the override correct; still pending a quick rebuild of src/
with a new hash and a functional pass. No patch or math is modified.

## Skinning observed after the real return (2026-10-11)

The earlier optional probe is rebuilt from `e0bf966` through
`2_recompilar_rapido.cmd`, src/ only, on top of the full 101 build of
`394779a`. No differences in patches nor runtime.lib; finishes with code 0
in 19.12 s. Runner 54,559,744 bytes, SHA-256
`063ea7299ffb9bb5bc413432df63f555a605225198557fc5cd753983ad2780a0`.
[CI of that code passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38178208986),
including the build of src/, procedural tests and the runtime suite.
Do not confuse this src/ update with a new build of the patches.

First synchronous/shared attempt, threads 0, does not reach state 11: it stops
with a private STOP at 144.89 s, still in menu 3 and without skinning calls.
It is kept as a failed attempt. The next one adds menu X presses
at 28/36/44/52/60/68 s: it **changes the script**, it is not an aligned repetition. Ends
at 300.05 s by limit, first report 11 at 135.49 s and last at 294.36 s.
Private procedural card intact, none of the searched signatures fatal/exception/
deadlock/assertion failed/unhandled; the monitor records no minimization.
Game code 1 due to external shutdown, controller 0: not a natural exit.

128 complete samples, no pause observed, five combinations of
skeleton/variant/view/ownerCandidate. Both routes 0x137508 and
0x137AF8 are run. The 6,173 valid destination, world and source reads
are finite. 5,629 selected slots whose destination changed have a valid
definition matrix: the world-by-definition product matches the destination, with
maximum residual 0.0001361 using column product in double. It is a
numerical description of this sample, **not a PS2 tolerance nor proof of a
correct pose**. The 544 unread definition matrices belong to slots not
selected; they are not failed accesses nor evidence of corruption. The global
quota runs out before all groups reach 32 samples.

16 PNG/JSON of the acquired pool, sequences 1453..1468 and ticks 1500..1515:
metadata exact against the log, full and distinct RGBA, 224 duplicated
row pairs in each. Hash disabled: PNG bytes are compared,
not unknown hashes. The review of the sequence shows movement of
a nearby figure over the deck, but **its identity is not confirmed**
and the framing does not separate protagonist/enemies. The reported spasm is not
yet demonstrated nor is each PNG automatically aligned with a skinning sample.
The animation inputs or their later submission to VU/GS remain under suspicion;
this evidence neither rules out those points nor resolves the framing.

Another script with explicit attacks is prepared; the current directions in the
script are digital buttons, not an analog stick. Do not claim displacement
of the protagonist from them. Pixels, matrices, binaries and cards
remain private; controls with reads/I/O and interpreter do not measure FPS.

## Enemy control and analog movement preparation (2026-10-11)

#61 merged in `b29e27e3f4efab6ca4b482392cd4ff56ab174f88`, after manual
review, earlier controls and [CI of the final HEAD `63f32f1` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38179505671).
A procedural negative in a private copy changes the definition access to
slot index instead of ordinal: it compiles, the test fails (1); restored
it passes (0). The repository header stays intact. There was no game with
that copy nor changes in the runtime.

Another pass of runner `e0bf966` adds squares/triangles every four
seconds between 180 and 292 s; **the script changes**, hash 0, synchronous/shared,
threads 0. 300.05 s by limit, report 11 from 121.86 s to 295.60 s,
card intact, none of the searched error signatures nor registered minimization.
128 complete returns of both variants, five groups, no pauses:
6,150 valid finite reads and 5,606 selected/changed products,
maximum descriptive residual 0.0001457. The 544 unread binds are still
unselected slots. It does not define a PS2 tolerance.

16 PNG/JSON acquired in sequences 1701..1716, ticks 1750..1765, with
exact metadata, distinct RGBA contents and all row pairs
duplicated. Images of several enemies with arms/body in
movement are reviewed; an anomalous deformation against a reference is not yet confirmed.
The scene seems to correspond to the introduction. State 11 does not guarantee that
the protagonist is already controllable; nor does button delivery confirm
its effect. Do not compare the poses with the earlier capture by time/tick.

The optional script gains left stick and explicit duration, without changing the earlier
digital buttons, plus bounded logging of the returned packet.
A late window of the pose probe is also prepared so as not to spend its
quota during the introduction. Tests and the next long pass pending
documentation once completed; no patch or math is modified.

Procedural script/packet tests and skinning window correct on
Windows/MSVC /W4 /WX; C++20 syntax of the override correct and configuration
with 0 errors/4 existing warnings. Quick build and analog control
with the game are still pending. The proposed Persona 4 reference is also reviewed:
[scope and useful material](persona4-reference.md), without importing
its code nor attributing a fix to it.

The src/ update from `73588d2` finishes with code 0 in 19.97 s
on the same runtime 101 (runtime.lib intact). Runner 54,561,792 bytes,
SHA-256 `0df18c12eb20455c0440fa26f9799f3b85be3babd7e0c0062f62f7cf5708d1be`.
[CI of that code passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38180275266);
[CI of the #61 merge passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38179912408).
The first run is closed with STOP at 65.45 s due to a mistyped private
output path; it does not count as a completed control. It is relaunched in the
verified private directory with a new procedural card.

The user identifies as a spasm the raised-arm pose of Kratos in
a provided capture. A visually similar pose exists in the earlier
acquired sequence; it is kept as a pointed-out example, not as a verified
normal pose. The cross-reference by log order shows a concrete limitation:
the initial 32 samples of the candidate skeleton of 111 slots end near
host report 140.56 s; the acquisition of tick 1500 falls between reports
186.02 and 191.06 s. **They do not correspond to the same window**. They are approximate
limits by record order, not exact execution timestamps.
Do not use those correct products to rule out the computation of the pointed-out
pose. In addition to the late control in progress, collect another probe window
and capture from 1500; the model and an aligned PCSX2 reference are still
needed to locate the alteration.

The long analog control ends at 540.05 s by limit, state 11
from 132.06 s to 536.28 s, private procedural card intact and no searched
error signatures. 78 packet records, 43 with non-neutral stick: the
four directions are returned by libpad2, with combined attack buttons.
No minimization; the foreground changes six times and real inputs
are excluded by the script-only mode. **No skinning samples, registered
acquisitions nor PNGs are obtained from 3000**: it does not prove visible movement,
a correct late pose nor the cause of the absence of records. That
result is kept and not counted as visual validation of the window.

A new pass from 1500 is in progress, with the same runner and the nine-press
menu script, without added movements/attacks, to observe matrices
in the window of the pointed-out pose. There is still no aligned PCSX2 reference.

## Matrix window next to the pointed-out posture (2026-10-11)

The previous pass from 1500 ends at 300.04 s by limit, runner `73588d2`
and SHA-256 `0df18c12eb20455c0440fa26f9799f3b85be3babd7e0c0062f62f7cf5708d1be`.
Synchronous FINISH, shared, threads 0, hash 0; procedural card intact,
no searched error signatures nor registered minimization. It is not a natural
exit of the game nor an FPS control.

128 complete returns, both variants, five groups and no pause.
6,150 valid finite destination/world/source reads; 5,606 final products
selected and changed, maximum descriptive residual 0.0001419. The
candidate group of 111 slots contributes 32 samples in videoTick 1500..1531 and 3,296
products, maximum residual 0.000005588. The probe now does reach the same
counter window as the images; the identity of the skeleton is not yet demonstrated,
nor a one-to-one correspondence between its computation and each texture.

16 PNG/JSON acquired, sequences 1456..1471, frameTick 1500..1515, metadata
exact against its record and distinct full RGBA. Each image duplicates
the 224 adjacent row pairs. Initial, intermediate
and final positions are reviewed: Kratos on the deck goes from the raised arm/blade to a low position;
the initial one resembles the example the user identifies as a spasm.
Pixel equivalence with their capture nor a correct PS2 pose is claimed.

The coherent final product bounds that observed operation, but does not certify
the input animation, the previous hierarchy nor the later VIF/VU/GS submission.
An exploratory private check of parent world by local source gives
differences in some slots. **It is not yet a demonstrated fault**: the
record has `0x6000` flags that can transform the result, and selection,
threshold and reuse decide what gets updated. Record those flags and the
world change before evaluating the hierarchy; do not correct matrices from that
incomplete product. The Persona 4 reference helps review semantics, with no
external source incorporated. Framing and spasms remain open.

The quick build, packet and window controls, procedural tests,
manual review and [CI of `7df7894` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38181222772)
validate the scope of #63: script support and optional diagnostic. The control
from 3000 without samples is kept as a limitation; it is not presented as
validated visible movement. Also check the CI of the final documentation HEAD
before merging. No changes to patches or game math.

## Hierarchy conditions: diagnostic prepared (2026-10-11)

The earlier exploratory check motivates logging record flags and
the world matrix change. `recordFlags` keeps all bits of record+0;
`worldBeforeValid`/`worldChanged` separate invalid reads from retained bytes,
without claiming per-slot execution. A prior world read is added to the optional
probe, without modifying computation, arguments, buffers, checkpoints or patches.
The procedural test distinguishes flags/index/threshold and rejects truncated records;
Windows/MSVC /W4 /WX and C++20 syntax of the override correct. Pending:
quick rebuild, control and CI of the new code. It is not declared that
the exploratory differences are corruption.

## Hierarchy conditions observed (2026-10-11)

Src/ of `e73e844` is rebuilt on the full 101 with code 0 in 19.56 s,
no changes to patches/runtime.lib. Runner 54,562,304 bytes, SHA-256
`29a43df0d67b092b4ab67a02adf6bb24d39244d1a87b2ada1a15d7402982314e`.
[CI of the code passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38181839302).
#63 already merged in `bf6768b4e6af6fa834d5f555c92131c85c35fa2c`, after review
and [CI of the final HEAD `4857fdb` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38181681700).
That main is integrated by merge; #64 continues the observation.

Synchronous/shared control, threads 0, earlier menu script, hash 0 and 1500
window: 300.05 s by limit; procedural card intact, no searched error
signatures nor registered minimization. 128 complete returns of both variants,
five groups, no pause; 6,173 valid finite reads and 5,629 final
products, maximum descriptive residual 0.0001494. The group of 111 slots again
contributes 32 samples in 1500..1531 and 3,296 final products, maximum 0.000006007.

In that group, the four slots 107..110 keep the world and destination
bytes, are not selected; 107/109 have visibility 0. They are the slots
that gave the large differences when indiscriminately applying the parent product
by source. They have no `0x6000` flags in these samples. Excluding the retained
bytes and the special transformations, 3,392 changed hierarchy products
are evaluated: maximum 0.000004453. **These are magnitudes of this sample,
not PS2 tolerances nor proof of correct animation**; nor does absence of
change demonstrate that it was not written. It is not justified to correct that
incomplete product as if it revealed corruption.

16 PNG/JSON acquired, sequences 1458..1473/ticks 1500..1515, exact
metadata and distinct RGBA, 224 duplicated row pairs. Images 1/8/16
reviewed show the arm/blade already in a low position: they do not reproduce the exact
raised pose of the previous pass. Even sharing a video window,
the two runs are not aligned by animation state. Do not use this
control to rule out the earlier spasm.

As a resource identity check, the 103 definition matrices
of the earlier sample match in their 6,592 bytes a block of the
historical PCSX2 state .02, which is still in state 4. A compatible definition and
skeleton are located. This relates the static data, **it does not align poses,
confirm character identity nor turn that intro into a gameplay
reference**. All those data and analyses remain private. The next control
must follow the geometry received by GS during the pointed-out posture and separate
that input from rasterization/presentation; the source animation remains open.

## Fixed trace before the posture and video window prepared (2026-10-11)

#64 merged in `76f60218eabe2584ffe454de7bd986d349f49ff8`, after review,
earlier control and [CI of the final HEAD `17cd878` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38182260148).
A new pass of the same runner `e73e844` uses synchronous FINISH/RAM/GPU
presentation/threads 0, without skinning probe or hash, and the same menu script.
GS capture after TEXFLUSH from 175 s: start 175.023 s, full End,
54,535,097 bytes, 145,442 Submit and seven Present in ticks 1434..1440.
It is closed with a private STOP at 188.28 s after the trace finishes, to
free CPU before repeating it; card intact, no searched error signatures
nor minimization. It is not a completed five-minute control nor a natural exit.

The prefix is repeated up to **its second Present**, record 22360, 22,207
Submit/tick 1435; the index 12795 of the old trace is not reused. Two
CPU passes: 4 MiB VRAM, state and two frames equal. Hardware, three
passes: the first mixes compute tiles and does not count as a constant-path
comparison. The second/third have 17,362 primitives and zero tiles,
but differ in 1,081 bytes of VRAM and 1,288 RGBA bytes of the second frame;
semantic state equal. Code 1 due to difference, **not a correct result**.
The original End and rest of the commands are not checked with this prefix.
Image review shows Kratos even more distant on the deck; it
is not the exact pointed-out posture, nor does it demonstrate that this variation causes spasms.

The host's time limit in seconds chose a segment earlier than the sought 1500.
`GOW_GS_REPLAY_FROM_TICK` is added, an optional threshold of the runtime's video
counter, alongside the already existing state/deadline/TEXFLUSH. Absent equals 0;
an invalid decimal value disables the capture without applying partial options.
Before the threshold commands continue to be sent to the backend, without starting a snapshot
or recording; Present does not open a capture by announcing a different tick. It keeps
the trace format, limits, backend and earlier synchronization rules.
That threshold **does not align poses between runs or with PCSX2**.

Windows procedural control correct: earlier commands reach CPU without
being recorded, start at TEXFLUSH on reaching 1500, snapshot preserved, a single
later primitive recorded, valid End; uint64 parser and invalid options
without partial changes. CPU replay of the fixture and pixel layout
correct. Pending: src/ rebuild, window control with the game
and CI of the new code. No patch or game math is modified.

## Introduction window and pose reproduction (2026-10-11)

The user clarifies that the spasm example corresponds to the ship
introduction. This check is centered on that segment; the earlier notices
about NPCs and the controls with HUD remain separate cases.

Src/ of `d5ab720` rebuilt on the full 101 chain: code 0 in
19.47 s, runtime.lib and patches intact. Runner 54,562,816 bytes, SHA-256
`6c7a3119476351602683e81f8ad0a890059b83c4cf1f0d068c3f83c9e0b7f436`.
[CI of the code passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38182940840).
Procedural negative in a private copy: omitting only the threshold compiles and makes
the window test fail; restoring it passes. The public header is not altered.

Synchronous FINISH/RAM/GPU/threads 0 control, same menu script up to 68 s,
without hash or presentation diagnostic: 300.06 s, closed by the control's
limit, procedural card intact, no searched error signatures or
registered minimization. Capture from tick 1500, state 11 and TEXFLUSH:
start 177.069 s/tick 1500, full End, 54,535,181 bytes, 145,436 Submit and
eight Present in 1500..1507. The earlier format and limits are kept.

It is repeated up to **the second Present of this trace**, record 22797,
22,619 Submit/tick 1501. Two CPU passes: 4 MiB VRAM, state and two frames
identical. Hardware, three passes: first with mixed path, excluded from the
constant comparison; second/third with 17,605 primitives and zero tiles,
semantic state equal, but 1,408 bytes of VRAM and 1,512 RGBA bytes of the second
frame different. Code 1 due to difference: neither parity nor stability validated.
The prefix does not check the original End nor the rest of the trace.

**The same second Present** exported by CPU and hardware is reviewed: both
show the raised-arm pose with the blade crossing the head, very similar to
the one pointed out by the user. It is evidence to keep following the geometry input
to the GS and its EE/VU production; not an exact equivalence with the user's
capture, an aligned PAL/PCSX2 reference, nor a proof that the raster variation
causes the spasm. Nor does a still image demonstrate correct animation.
The PPMs and their PNG conversion with RGB intact remain private.

The probe completes 128 returns, five groups, both variants, no pause:
6,173 valid finite reads and 5,629 final products, maximum descriptive residual
0.0001441. The 111-slot candidate contributes 32 samples in 1490..1520,
3,296 final products and maximum 0.000005563. Its selected source bases
have determinants 0.6558639..1.0000008 and axis lengths from 0.8098543;
no zero/negative determinants in that sample. They are observed magnitudes,
not fidelity tolerances: scale or animation blending can produce
non-unit bases. Do not normalize nor correct matrices without identifying their
producer and contrasting a reference pose. The cause of the spasm remains open.

## PMULTH hint from Waffle565's port (2026-10-11)

The user provides [God-Of-War-Native-Port](https://github.com/Waffle565/God-Of-War-Native-Port),
reviewed at `811313597514940a4d6020fefc1ce5b83f5b4fe4`. Its
[fix entry `50b591d`](https://github.com/Waffle565/God-Of-War-Native-Port/commit/50b591d2bc679cc705b55764588716410df10d92)
identifies PMULTH as mistranslated in animation decoders; it reports
differential comparison and visual improvement in their port. Those are checks by
that contributor, not an independent reproduction of ours. The public commit
documents the fix, but does not include its runtime implementation.

It is independently checked in our regenerated NTSC code that four
PMULTH, in three decoders, still emit `_mm_madd_epi16` and add
their results into a scalar. It is a semantics fault: PMULTH produces eight
signed 16 by 16 bit products, LO={p0,p1,p4,p5}, HI={p2,p3,p6,p7} and
rd={p0,p2,p4,p6}. The order is contrasted with
[PCSX2 MMI.cpp pinned](https://github.com/PCSX2/pcsx2/blob/2954ebe6965669219f1bbd256e958fbd8f83a85d/pcsx2/MMI.cpp#L1292).

`ps2recomp-ee-pmulth.patch` is prepared, a separate topic at the end of the chain
(102), with its own implementation of that semantics in the runtime header
and emission by the recompiler. It preserves the eight results in both HI/LO
pairs, the zero register and the operands when rd coincides with rs/rt. It does not change
the context structure, addresses or game functions. Regressions with
distinct values per lane, negatives/extremes, both HI/LO pairs, aliasing and zero;
the emission test covers rd=0 with its side effects. No generated
code nor code from the other port is incorporated, nor is Opus's checkout modified.

Pending: a full build that regenerates the four instructions,
suite/negative, CI and a control of the introduction with the new executable. The
evidence confirms the instruction error, **not yet that it fixes all the
spasms, the framing or the asynchronous/shared presentation**.

## PMULTH closure and pending controls (2026-10-11)

#65 merged in `dbfbe719eea0483b768aa4eef3894db1221cf28c`, after review,
control and [CI of the final HEAD `396f594` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38183579985).
[PR #67](https://github.com/KIexster/god-of-war-recomp/pull/67) contains
PMULTH and stays a draft. The private full build of `2fd0fc9`
has already regenerated the four sites with the correct helper and is still compiling the
runner. There is still no final executable nor visual control of this fix.

The first CI of #67 fails compiling the regressions: `GPR_VEC(&ctx, ...)`
expands the pointer without parentheses. The argument of those tests is fixed to
`GPR_VEC((&ctx), ...)`; it does not change the helper, the emission or the game logic.
Pending: CI of the new HEAD, native suite and meaningful negative. Do not treat
the first failed CI as validation of the runtime.

[Issue #66](https://github.com/KIexster/god-of-war-recomp/issues/66) is also reviewed,
provided by another contributor: it separates cases measured on Transformers from their
hypotheses for God of War. In our runtime the VU1/VU0 budgets of
65,536/4,096 are confirmed and that the context constructor leaves vf0 at zero;
StartThread creates that context. **It has not been demonstrated that they cause this spasm**.
The next control will enable `GOW_VU1_BUDGET_DIAG=1`, without increasing budgets,
and will examine magnitudes in addition to finiteness. First verify PMULTH; the other
hypotheses require evidence separately and fixes are not incorporated in bulk.

## Constant VF0 in VU0 (2026-10-14)

Issue [#66](https://github.com/KIexster/god-of-war-recomp/issues/66) pointed out that
`R5900Context` left `vu0_vf[0]` at complete zero. The constructor now initializes
VF0 to `(0, 0, 0, 1)`; the VU0 translations ignore writes to the zero vector
without removing other effects of the instruction, and `LQC2` to VF0 does not load memory. Regressions
were added for the context and for LQC2, QMTC2, VADD, VITOF and VMFIR.
The `VI0` paths already ignored writes from `CTC2`, VI operations and memory
loads/increments; `VMTIR` could still write it. An additional patch
treats it as a constant destination and the regression also checks that VI destinations
other than zero keep writing.

Both patches were compiled with MSVC 19.44 and Ninja 1.12.1; `ps2x_tests` passed
622/622 with zero known failures. `tools/ci/parches.py`,
`tools/ci/validar_config.py` and the clean application of the two patches in order also pass.

Review of the VF0 filter (2026-10-14): the search for the generated string
`ctx->vu0_vf[0] =` and the deletion up to the next semicolon were removed. The
VU0 emitters now send writes to `PS2_VU0_VF_WRITE`, which checks the destination and
does not evaluate the value when the destination is VF0; writes to other VF stay
the same and side effects, such as updating R in VRNEXT, are preserved.
A regression verifies the behavior of VF0/VF1. The VF0+VI0 series applied
cleanly and compiled with Ninja passed `ps2x_tests` 623/623, with no known failures.

## PMULTH: full build and native regressions (2026-10-11)

Chain 102 finishes with code 0 in 959.94 s, regenerating the four PMULTH sites
with `ps2_pmulth`. Functional code of `2fd0fc9`, 54,565,376 bytes,
runner SHA-256 `3092e98bc53ff8e1109a71ee596d7bfa0a15263ac6a6f1a0bfc3fc91ee8cfc4f`.
That build identity is kept: the later HEAD fixes test arguments,
documents the closure and integrates main, without changing helper/emission.
VU1 interpreted, three tasks, /O2 /Ob2 /DNDEBUG /Zi; data and symbols private.
Do not attribute to this build the FPS measured with compiled VU1.

Final regressions of the PR applied to the native test tree: 602 normal
cases and 638 GPU, zero failures; four FINISH/presentation contracts correct.
Isolated negative with the public procedural assertions: the correct helper
passes, replacing it with the earlier scalar sum **compiles and fails**, restoring it
passes. Working runtime header intact. It is not a game control.
[Final CI `94cacf8` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38184150710).

A private control of the introduction is started: synchronous/shared FINISH,
threads 0, same menu script, matrix window 1490 and 16 acquisitions from
1500, hash 0; VU1 cut diagnostic enabled without increasing the budget.
Pending: finish, review poses/log and publish the result before
marking #67 ready. The spasm has not been declared resolved.

## PMULTH: first later visual control (2026-10-11)

The previous pass ends at 300.06 s by limit; procedural card intact,
no searched error signatures nor minimization. Focus is recorded for about
two seconds, without proving its cause. With `GOW_VU1_BUDGET_DIAG=1` no budget
cuts appear in this synchronous/shared configuration, threads 0;
this does not rule out cuts in other segments or with threads/performance enabled.

128 complete returns, five groups, both variants, no pause;
6,173 valid finite reads and 5,629 final products, maximum descriptive
residual 0.0001364. 111-slot candidate: 32 samples 1490..1520, 3,296 products
and maximum 0.000005823. It keeps non-unit source bases (minimum determinant
0.6596880, minimum axis 0.8122119), with no zeros/negatives in this sample: neither
do they now justify normalizing matrices by intuition.

16 acquired textures 512x448, sequences 1455..1470/ticks 1500..1515, exact
metadata and different RGBA; 224 duplicated row pairs per image. Images
1/8/16 reviewed show an upright head and blades in front of the body,
without the raised pose of the example. It is a favorable result of this window,
**not a full validation of animations/NPCs, camera or stability**.

Descriptive comparison with the window of the earlier trace: the 32 stamps
match, but no input matrix nor scalar matches exactly.
They are not aligned poses. The largest source step of slot 14 goes from 1.13344 to
0.0007890 and the largest position step observed in the group goes from 18.71 to
0.84; they are not used as a PS2 tolerance, improvement percentage or automatic causal
proof. PMULTH is indeed fixed by its semantics and regressions. The control still has to
be extended to other animations and contrasted with an aligned reference.

## PCSX2 GS: start of our own adaptation (2026-10-11)

#67 merged in `96853bad688305c1d62d9dad6faeb1f1e58e1de4` after controls,
review and [CI of the final HEAD `3ba1000` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38196063455).
Main is integrated without rewriting history. The user asks to adapt PCSX2's GS on our
own while the author of the Urban Reign port delivers their link.
Their code is not yet available nor are their FPS/resolution figures reproduced.

Our own GIF transport is prepared for the three PATHs, with fragments,
aligned quadwords, limits and errors; connection to `GSState::Transfer` of
PCSX2 `2954ebe`. Windows procedural tests and syntax with its real
headers correct; CI added for both. It does not change runtime/patches or the default
backend. It does not yet create a real GS nor draw the game: extraction of the
DX11 module, registers, FIFO/VRAM and coverage of native paths pending.
Architecture, conditions and limits in [PCSX2_GS.md](pcsx2-gs.md).

Later review: the first connection compiled but PATH1 used the legacy index
0. GSState cuts that index at EOP and clears an incomplete nloop at the end of
the span, incompatible with our batches/fragments. It is fixed to the continuous
index 3 used by GSgifTransfer/MTGS; the other two keep their cursors.
Correct syntax does not prove that behavior. The real GSState.cpp compiles
as a private object in MSVC; linking/running the module is still missing. The bridge had not been
connected to the game nor its renderer modified.

## PCSX2 GS: original parser tested (2026-10-12)

The private extraction of GS/common now links and runs the original GSState without
window/device. The procedural fixture is published, with no game data:
PATH1 retention when splitting tag/payload, two EOPs per batch, PATH2/3 fragments
and independent cursors, exact RGBAQ. The subclass counts drawing without
rasterizing; the test requires zero draws and zero window requests.
It is not a replacement renderer. Original libraries/services and private-host
reproduction limits detailed in [PCSX2_GS.md](pcsx2-gs.md).

PATH1 index 0 negative: compiles and fails on the pending nloop; restored
index 3 correct. SHA-256 of the restored procedural executable
`1289d908c425c0f1b138ff7dc4cf619f1a9341c443fe6145eae5c02d9b7e033c`.
The earlier CI `d4aab8e` complete and passed, including the syntactic link of
real headers; pending CI of the HEAD that adds fixture/results.
Still missing: hosting DX11, pixels, FIFO/VRAM/IRQ and connecting the runtime.

## PCSX2 GS: DX11 device with pixels verified (2026-10-12)

The private extraction now creates the original GSDevice11 in windowless mode on
the AMD Radeon RX 5700 XT. `tests/pcsx2_dx11_device_probe.cpp` is published:
two create/close cycles; Clear and a pattern uploaded with per-row padding,
drawn by the original COPY shader. The 2,701 RGBA pixels of each operation
match exactly, including alpha and orientation. Isolated negative that
omits the draw: compiles and fails on the first pixel; restored passes.
Restored SHA-256 `2be054f554e71ebdafc234998b84d4e7b53542f26a40c2f58403fcbead66db14`.

[Full CI of `6139073` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38200847766).
The new DX11 control was native and private, not a CI GPU run. Host,
dependencies, scope and pending items in [PCSX2_GS.md](pcsx2-gs.md). Still missing: sending
GIF to the full rasterizer/cache, VRAM/FIFO/IRQ and connecting the game.
It does not change the current renderer nor vouch for an FPS improvement.

## PCSX2 GS: first GIF draw on hardware verified (2026-10-12)

The private extraction of the original GSRenderer/GSRendererHW/GSTextureCache
links and draws on DX11. Published fixture `tests/pcsx2_gif_draw_probe.cpp`:
mosaic of 16 sprites, 13-byte fragments, different colors per PATH1/2/3
and original FIFO download. The three submissions each produce one GPU draw call
and 2,048 exact RGBA pixels. Negative that omits only the draw packet:
compiles and fails on the first pixel; restored passes all three PATHs. SHA-256
`1d271fd05fcbf01cec0b688655c26337b99259a2545274ecccda423740ef01fb`.

[Full CI of `72e4f55` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38238566117).
This GPU control remains native and private. Absent optional services
abort if used; VSync, window or reopening is not requested. The SW
objects are kept, with no validation of that path. Limits in [PCSX2_GS.md](pcsx2-gs.md).
Still missing: public reproduction of the module, IMAGE/textures, presentation and connection
to the runtime. No God of War rendering nor FPS improvement is attributed.

## PCSX2 GS: reproducible module, IMAGE and memory closure (2026-10-12)

The host/CMake/preparation of the isolated module is published and a Windows CI is added:
link of four fixtures, parser and memory run without GPU. Local build
of the recipe and four controls correct. IMAGE CT32, DECAL/nearest texture
and full/partial FIFO are also verified: 2,048 + 91 exact RGBA pixels,
GPU drawing confirmed. Omitting IMAGE compiles and fails; restored
correct. SHA-256 of the draw fixture
`a7991d25961bdddddd8ce3631cf73287f057b8928c735df8724c818e575f3444`.

The Windows extraction kept a handle and placeholders on close. It is
fixed only in the isolated host, with GOW-Port comments and regression: eight
alias cycles of 4x4 MiB, stable handles and the whole range free. Separate
negatives for handle and placeholder join compile and fail; restored
correct. No validation of the reservation failure path. The original sources
and the game runtime remain intact.

The local recipe runs the four fixtures without a DXC DLL; it does not vouch for other
APIs or performance. [Instructions](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/render/pcsx2_probe/README.md),
limits and next steps in [PCSX2_GS.md](pcsx2-gs.md). The CI of `4addf7b`
complete and passed; the new native job is pending for the HEAD that publishes it.

## PCSX2 GS: procedural VSync/PCRTC output (2026-10-12)

`gs_gif_draw_probe --frame` runs the original GSvsync, its CRT update/Flush
and DX11 Merge. Three different patterns, three 64x32 outputs: the 2,048 RGBA
pixels of each match exactly the input RGB and alpha 255 imposed
by PMODE. Surfaceless omits the window Present and the host checks its
callbacks. Negative omitting only GSvsync compiles and fails; restored passes.
SHA-256 `cd46ebb2f58aa6bd80c5849e30d7ee5fc0659c644db030f65c8fed1c6701cffb`.

DISPLAY is configured according to the NTSC units of the original body. The
first offset of 25 lines belonged to the fixture with DY 0, not to a run
of God of War. It does not change the game's renderer nor resolve its
framing by itself. [Full CI of `08307ac` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38243100981),
including Windows link; this new GPU test is local. Window/swapchain and
runtime integration remain pending; there is no FPS measurement.

## PCSX2 GS: DXGI backbuffer and two window cycles (2026-10-12)

The `--window` mode uses its own hidden procedural window and the original Present.
Two full device/renderer/window cycles, three patterns per cycle:
the six real backbuffers read before Present and the six PCRTC textures
match exactly in their 2,048 RGBA pixels. Empty ImGui context, no
interface files; callbacks and closing of HWND/class verified.

Negative clearing the backbuffer to magenta after drawing: compiles and fails even
with correct PCRTC output; restored passes window and Surfaceless. SHA-256
`74e92ae9a886b66f55079d06f6cbf0ddcbf9af18bfe2064e7d92137f94f3c543`.
[Full CI of `d1bf750` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38244581430).
The new GPU control remains local. God of War is not run, no
visible image is checked, nor resize/device loss nor the stability of the runtime's
asynchronous FINISH. FPS is not measured. Integration API/hook pending.

## PCSX2 GS: IMAGE FLG=3 and coverage of the future hook (2026-10-12)

IMAGE FLG=2/3 are checked with the original parser/rasterizer, without altering
the tags in the bridge. FIFO, PCRTC output and window backbuffer exact.
Negative omitting only FLG=3 compiles and returns the previous pattern; the test
fails. Restored, the three modes pass. SHA-256
`77ecd2fa20509b18422d9ade62c8ee35db18f90a0a8ad19e6882be412d311bfd`.
It keeps the semantics relevant to #55, without attributing FPS or a game fault.

Review confirms two DMA shortcuts that bypass the generic arbiter/frontend.
The native upload normalizes data/registers and loses part of the original tags;
the future hook cannot be limited to processGIFPacket. Proposal and pending items
documented in [PCSX2_GS.md](pcsx2-gs.md), without modifying the runtime for now.
[Full CI of `ada5c5e` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38246271325).

## PCSX2 GS: DLL ABI and independent consumer (2026-10-12)

An optional DLL with ABI 1 is built (sizes/handles/errors/thread). Contract
of loading/exports/arguments without device correct, added to CTest/CI. GPU
client through GetProcAddress, without GS globals: two cycles, fragmented GIF,
registers and output query correct; 2,048 exact RGBA pixels per cycle.
Busy singleton, closed handle, another thread and insufficient buffers rejected;
final guard intact. Thread/capacity negatives compile and fail; restored
correct. PS2Recomp is not yet modified nor is the game linked. The 8 KiB mirror
must be built from real PS2 registers; do not copy its GSRegisters struct.

[Full CI of `1f87036` passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38248274550).
New DLL contract pending for the HEAD that publishes it. GPU local, no FPS
measurement; IRQ/FINISH, FIFO/VRAM, recovery and hook pending. Scope in
[PCSX2_GS.md](pcsx2-gs.md) and [module README](https://github.com/igormcsouza/god-of-war-recomp/blob/main/tools/render/pcsx2_probe/README.md).

## PCSX2 GS: explicit privileged mirror (2026-10-12)

Helper not enabled in the game: packs 19 registers at PS2 offsets, in
little-endian, zero gaps and atomic CSR; omits vsyncTick of the compact struct.
Test with distinct values/multibyte CSR and tick changes correct in MSVC.
The 19 offsets and 8 KiB are contrasted with the original GSPrivRegSet through
static_assert. CI/CTest incorporated. The caller must synchronize the non-atomic
fields; the helper does not by itself fix concurrent access or presentation.

## PCSX2 GS: optional mirror link prepared (2026-10-12)

Patch 103: original GIF observer, direct writes/reset and EE
VSync. The two DMA shortcuts and PACKED are rejected while linked, without consuming
their input; usual behavior preserved when unlinked. Windows client
through DLL, owner thread and bounded queue; limited private PCRTC BMP capture. Rejects
VU1/GS front threads. IRQ/FIFO/VRAM remain in the runtime; usual backend intact.

Build of the Windows module/client correct. Parser keeps cursor and Q
with direct register, GPU DLL two cycles/2,048 exact RGBA, reset and rejection
of invalid address correct. Config 0 errors/4 existing warnings; 24 PS1
without errors. The suite of the new runtime and the full build of 103 are still
pending. Variables/protocol and limits in [PCSX2_GS.md](pcsx2-gs.md).

## Pause requested after full build 103 (2026-10-12)

Code HEAD `477e01372d3f4a58c460b126b8e459873e9b9286`: the four CI jobs
passed in run `38298178064`. Full Windows build through
`2_compilar.cmd` in a private workspace, 103 patches, exit code 0, 1,072.57 s.
Runner SHA-256 `e8e18d005dce8674de8df92be4522ec8f038b6a6aeedc3769915c5679988a471`.
The executable and its manifest are frozen; the game is not run yet.

Preparation of the full runtime/queue/DLL control is published, with two distinct
patterns separated by reset, and options of the transition control that log
DLL hash and private PCRTC captures. The 19 Python tests of the control pass.
The full native fixture has not been compiled/run yet. Still pending:
fixing the Unicode reading of the Windows environment in the client: the controller
may resolve the junction to a path with accents and `u8path(getenv(...))` does not
guarantee correctly interpreting the ACP bytes. The mirror is not enabled in
a game before fixing and validating that path.

Express pause by the user at the end of the build. Pending when resuming:
Unicode and regression with a non-ASCII folder, rebuild of src/ on top of this
full build, native suites/contracts, runtime/DLL procedural control
and then menu/introduction/gameplay. PR #68 stays a draft; no FPS
improvement nor resolution of framing, spasms or asynchronous FINISH is claimed.

## PCSX2 GS: runtime/DLL path and Unicode paths verified (2026-10-12)

Resumed at the user's request. The native link control reproduces the
configuration rejection with the DLL in a path with accents and a folder
`capturas_ñ`: the ACP bytes of `getenv` are not valid UTF-8 for `u8path`.
Those paths are read with `_wgetenv`/UTF-16 and only the resources are converted
to UTF-8 for the ABI. The earlier negative compiles and ends with code 1;
with the fix it ends with 0, without changing the runtime nor the DX11 module.

Full control with runtime 103: 28 GIF spans/352 bytes, two direct
writes during incomplete tags, two VSyncs and one reset; both 64x32
images have their 2,048 exact RGBA, with different colors before/after
reset. Queue drained and DLL closed with `failed=0`; non-ASCII folder correct.
DLL SHA-256 `cbbc2d060df61e479355479fc3ce5b054e5ce27302bf19d5accda735d21ecd62`.
It is not yet a game or FPS control. The src/ update of the
runner on the full build 103 and the native suites are pending.

The native suites of that full build finish correctly:
605/605 normal and 641/641 with the OpenGL GPU controls enabled, no known
failures. The four normal/asynchronous FINISH contracts, including real shared
presentation and CPU comparison of 16 textures, pass. These patterns do not
replace the transition with the game nor validate all thread combinations.

## PCSX2 GS: first transition and Tobiichi review (2026-10-12)

Src/ `e4cf8c14732771112bb87054b53edaae66ea6f35` updated on full
runtime `477e013`/103; runner SHA-256
`089b1cea9cd14bb3cf3e2fa387b3a6f7f303801dfbd24b67b3be3b2fa8916ca5`.
CI of e4cf8c1 complete and passed. Private negative omitting direct writes
and allowing shortcuts with observer: compiles and causes four failures. Sources
restored byte by byte, 605 normal and 641 GPU correct again.

First game control, synchronous FINISH/shared presentation, without VU1/GS-front
threads: 360.08 s up to the limit, no early exit. Private card
copied, same ELF verified, script without periodic captures. DX11 mirror
processes the game's GIF/VSync and saves 10 PCRTC 512x448 images, ticks 900..1980,
plus eight acquired OpenGL textures 1400..1407. Samples of
the introduction and enemies are reviewed; poses/animation or parity with PS2 are not certified.
State 11 includes the introduction: it does not demonstrate playable control/HUD.

Shared inspector: 610 acquisitions from tick 1400, without regressions,
inconsistent metadata, dimension changes or logged A-B-A returns.
It covers that sample; it does not demonstrate absence of retentions nor resolve all
the faults. EE tick of the mirror and host/acquisition tick do not align pixels
by themselves. Exit 1 corresponds to the termination of our own process at the limit;
normal closing of the game is not verified. It does not measure FPS.

Recent changes of Tobiichi-Port are reviewed at the user's request:
[comparison, candidates and limits](review-tobiichi.md). The global
mailbox or the fence control are not copied without their regressions. Equivalent
asynchronous shared control in progress; the build is not changed during the game.

Asynchronous/shared FINISH control on the same runner e4cf8c1: 360.06 s,
end at the limit without early exit, 12 PCRTC captures 900..2220 and eight
acquired textures. HUD, Kratos and enemies are observed in the DX11 output of
tick 2100; fidelity of animation or manual control is not claimed from that image.
Inspector: 918 acquisitions, without regressions, inconsistent metadata,
dimension changes or logged A-B-A. Same ELF/initial card and
isolation options. Both mirror controls use generic DMA paths:
do not extrapolate stability to the usual shortcuts, threads or a long game.

A configurable-interval capture is prepared to study consecutive poses:
`GOW_PCSX2_GS_CAPTURE_EVERY_TICKS=1..600`, default 120, maximum quota 16
kept. Controller updated and 19 Python tests correct. Runtime/DLL fixture
captures two exact colors at ticks 1 and 2 with reset; negative that
ignores the interval and forces 120 compiles/fails, restored correct. Change
only to src/ and control, no new runtime patch. Rebuild of the runner
and burst with the game pending; the e4cf8c1 executable does not contain this option.

## PCSX2 GS: first bursts compared within one run (2026-10-12)

Src/ `e5e040e5bd4ea56d13499bd827f9276fa4400ce7` rebuilt on the same
full chain 103 of `477e013`, without changing the runtime library.
Runner SHA-256 `4af9bd9bca230265db2bb4c9f8a3122bad0643e83a95c477d11eeae5c4641d09`;
VU1 interpreted, VU1/GS-front threads off. [CI of HEAD e5e040e passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38314554618).
Same ELF, ISO, script and initial card copy; DX11 mirror from boot,
16 consecutive PCRTC captures from tick 1400, no periodic pad captures.

Two finished controls: synchronous/RAM, 420.08 s, and asynchronous/shared,
420.07 s. Both reach the limit, without early exit nor logged mirror
fault; forced termination of our own process, not a normal game close.
The copied card keeps its hash. The asynchronous one logs 1,142 shared
acquisitions without regressions, inconsistent metadata, unknown hashes,
dimension changes or A-B-A in that sample. Zero retained rows does not prove
absence of retentions: the diagnostic only logs new acquisitions.

The 16 PCRTC images of the synchronous/RAM run and the 16 PCRTC/acquired texture
pairs of the asynchronous/shared run are reviewed, 512x448, ticks 1400..1415. In those pairs
from a single run similar framing and Kratos silhouette are observed, with
gradual movement, without the large jump or abrupt deformation sought in
this window. OpenGL shows more jagged edges and differences between lines.
It is a visual observation: it does not certify pixel equality, PS2 fidelity,
poses of all animations/NPCs nor the cause of those differences.

Between the RAM control and the earlier shared passes, the same tick
corresponds to different moments of the introduction. Do not attribute to the renderer
a camera or posture difference obtained that way. Even within the same
run, EE tick and acquisition tick do not guarantee an identical GIF prefix;
the visual contrast does not replace a reference aligned by state/commands.
Equivalent synchronous/shared and asynchronous/RAM remain in progress to complete
the matrix with this same executable. Diagnostics, hash, two renderers and readbacks
prevent using these controls to compare FPS with Opus's measurements.
The mirror forces generic DMA paths; stability of shortcuts and threads pending.

## PCSX2 GS: field convention reviewed with Urban Reign (2026-10-12)

The author publishes their integration; [review and references](review-urban-reign.md).
It is confirmed in the original MTGS that GSvsync receives `CSR.FIELD ? 0 : 1`. The earlier
mirror passed the parity of the EE counter directly, inverted with respect to
that convention. The client is adjusted to the same CSR snapshot sent to the
DLL. A producer/queue/DLL receiver regression without GPU is prepared, with four
fields including retention and independent ticks. Native validation,
negative and game afterwards pending. It does not change runtime, IRQ, counter or
the usual renderer, nor vouch for the cause of the game's spasm/framing.

Before that adjustment, the synchronous/shared e5e040e also ends at 420.06 s;
961 acquisitions without inspector anomalies, 16 capture pairs reviewed
with similar framing/silhouette in the 1400..1415 window. Both shared
controls present 224 duplicated RGB row pairs in each OpenGL image,
and zero duplicated pairs in their DX11 outputs. OpenGL duplicates the selected field;
PCSX2 uses automatic deinterlacing. Descriptive count, not pixel equality
nor proof that the difference is the cause of the model deformation. The
earlier captures keep the mirror's inverted field: do not certify interlace
parity with them. The equivalent asynchronous/RAM e5 is still in progress.

Later validation of client `89ffb57ab40577ea6bcb342d151f2217e14b0165`:
six Windows CTests without device correct, including delivery of four
VSync/CSR by the client and the queue. Negative in a private copy, passing
the runtime's field directly again: compiles and fails with code 1;
restored code 0, public header intact. Real runtime/DLL/DX11 fixture
rebuilt and correct, 2x2,048 exact RGBA, fragmented GIF, direct register,
reset and close without failure. It is not yet a comparison of fields with the PS2 scene.

The e5e040e matrix completes its four controls of 420 s: asynchronous/RAM,
420.08 s, reaches the limit without logged mirror fault; 16 PCRTC
captures reviewed, gradual movement in the window, copied card intact.
Each variant keeps 16 PCRTC 1400..1415; shared ones also 16 acquired
textures. Keep the inverted-field limit in those mirror captures.
Do not extrapolate to threads, optimized DMA paths or all animations/NPCs.

Src/ of the corrected client rebuilt on full 477e013/103, code 0 in
20.67 s, runtime library intact. Runner SHA-256
`0c2d81f875bd15032cd030be8a068cc08670a2185c2cfc428b36e6342e4299e7`.
Shared synchronous/asynchronous controls are started with this same executable:
introduction burst from 1400 and Kratos/NPCs from 2100, respectively.
Different deliberate windows; do not compare poses between passes by tick.
Captures and logs still pending review. The new CI is in progress.

Intermediate review of the synchronous/shared `89ffb57`, still running:
16 consecutive PCRTC 1400..1415 and 16 acquired textures 1400..1414/1416,
all 512x448. The 15 pairs that have both files for that tick are reviewed;
the acquired 1416 is not paired with PCRTC 1415. Similar framing and silhouette,
gradual movement of Kratos in this window, no abrupt deformation observed.
The difference between lines/filtering remains. It is visual inspection of the same
run, with no proof of equality of commands or pixels, PS2 fidelity or all
animations. Still missing: end at the limit and inspector of the full log,
and later asynchronous control of Kratos/NPCs. [CI of code 89ffb57 passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38317718747).

## PCSX2 GS: introduction and NPCs with corrected field (2026-10-12)

Both controls of `89ffb57`, same runner `0c2d81f...`, end at the limit
of 420 s: synchronous/shared 420.08 s; asynchronous/shared 420.06 s. No
early exit nor logged mirror fault; copied cards intact.
The forced termination of our own process is kept, without verifying normal
game close. [Earlier documentation CI f7ad52a passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38318710304).

Final inspector: 714 synchronous acquisitions from 1400 and 417 asynchronous from
2100, without sequence/render regressions, inconsistent metadata, A-B-A,
dimension changes or unknown hashes in those samples. Tick distance
0 in both; it is not a measure of latency, FPS or absence of retentions.
The mirror keeps generic DMA and VU1/GS-front threads off.

Introduction: the 16 PCRTC and 16 acquired textures are reviewed, with 15 pairs
of coinciding ticks and the acquired 1416 kept apart. Kratos keeps a coherent
silhouette and gradual movement in the window. It does not vouch for all his poses.

Asynchronous: the 16 PCRTC/acquired pairs 2100..2115, 512x448, are reviewed;
the outputs show HUD, Kratos and NPCs. There are visible differences larger
than the line filtering: the OpenGL image has much more fog and hides
details of some NPCs; DX11 shows them more clearly. The general framing and
the foreground objects are similar. The abrupt deformation sought is not observed
in these images, but **no visual equivalence is validated**.
The tick by itself does not guarantee the same GIF prefix or pose either; this
observation does not yet identify a concrete fog, depth or blending fault.

Next control: follow FOG/FOGCOL/FGE and raster, with comparable commands/state
and procedural patterns, before changing the camera or normalizing matrices.
The optional diagnostic of #68 now receives and draws the game's stream; it is not
a main backend, a benchmark or a general resolution of spasms/framing.
The Urban Reign review includes explicit credit to thiagordsfx, at the user's
request; own implementation of the link and field adjustment, contrasted
with the original PCSX2. No captures, dumps or game data have been published.

## Urban Reign: SDK and FOG reference (2026-10-12)

Their SDK map of 983 linked functions, metadata and HLE bindings is reviewed:
[scope, candidate services and credits](review-urban-reign.md).
Many libraries keep original recompiled code; reuse common services,
without transferring addresses or game assumptions. Their CD/DVD seek alias
ignores the layer on a single-layer disc: it requires its own control for GoW.
Credit to thiagordsfx and PCSX2 is added in the three READMEs, with the same scope.

The pinned original parser keeps FOG when alternating XYZF/XYZ: PACKED XYZF3→XYZ3,
XYZF2 with ADC→XYZ2 and A+D XYZF3→XYZ3. Control without device with one valid
primitive, distinct values 13/201/233/77 and no call to Draw: correct.
It is added to its public fixture. In our frontend, XYZF assigns the fog to the vertex
but does not update `m_curFog`, which uses the later XYZ. A regression check of our own
is prepared before fixing it in a separate topic. The observed fog difference
nor the original spasm is yet attributed to that omission.

## GS: retain FOG when writing XYZF, preparation (2026-10-12)

#68 merged in `578d4ec582da3b5c05f521b9aa33102046b40499`, after review,
controls and [final CI fe13f32 passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38331548876).
Main is integrated by fast-forward and an independent topic is opened for FOG.

Native procedural control of the previous frontend with explicit CPU renderer,
POINT/FGE, ALWAYS depth and distinct colors: six variants PACKED,
A+D and REGLIST, XYZF2/3→XYZ2, draw the control `805c2ec6`, but the later XYZ
produces `80c05f3b`. The reference is obtained by writing FOG explicitly,
with the same inputs; the values are synthetic, without game data.
The first test without configuring ALWAYS depth did not draw: it is discarded
as proof of the fault. The corrected control does draw and distinguishes the fogs.

`ps2recomp-gs-fog-latch.patch` is prepared, at the end of the chain (104), on
an intact base 103 in its own worktree. XYZF2 PACKED, XYZF3 PACKED and the common
A+D/REGLIST path update `m_curFog` before launching or discarding the vertex. XYZ2/3
keep preserving the attribute. It does not change camera, matrices, CRTC, fences or
performance options. The native PACKED shortcut shares that decoder.

Six group regressions cover the three PATHs, PACKED/A+D/REGLIST/direct/native,
ADC, context change and reset, checking drawn pixels and later FOG
update. Configuration 0 errors/4 existing warnings; syntax of 24 PS1,
0 errors. The patch passes check-mode application on 103. The suite with
regressions and earlier code is being built to check the negative.
Positive, full build of 104, CI and functional control still pending.
The game's fog difference, the spasms or the framing are not declared fixed.

Native validation of `1bfa0358f23a0c25604a7e69c7ab50890a2bfcbf`: the six
new regressions fail with the earlier code and the other 605 pass; library
103 SHA-256 `bf984c75fd78a3dc78502460e22390dfc16ea50b9653a850719724f7f517b2df`
intact. Applying only the fix, 611/611 normal and 647/647 with OpenGL GPU
controls correct. The private control of six variants also yields
six colors equal to the explicit control. No known failures added.
[CI of code 1bfa035 passed](https://github.com/KIexster/god-of-war-recomp/pull/69/checks).

These are runtime tests, not a new build of the game. The full build 104
is started with private `GOW_WORK` and earlier sources preserved;
its commit/hash will be recorded when it finishes. [PR #69](https://github.com/KIexster/god-of-war-recomp/pull/69)
stays a draft until build, scene and CI of the final HEAD are completed.

Full build finished of `9b80b05b7bd23a63d24af32a61495a3501b19c21`:
104 patches applied in order, final code 0 in 1,039.50 s, with private `GOW_WORK`
and VU1 interpreter. Runner of 54,589,952 bytes, SHA-256
`0e65c95d134daccfe3f6f295e299e6def27a77b46402c6e18f4cb66cd2ee8643`.
ELF SCUS_973.99 with expected hash; earlier sources preserved and executable,
symbols and manifest frozen before the control. Flags `/O2 /Ob2 /DNDEBUG /Zi`
and `/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`.
[CI of 9b80b05 complete and passed](https://github.com/KIexster/god-of-war-recomp/actions/runs/38333982967).

The synchronous/shared control of this executable is started, VU1/GS-front threads
off, private card copied, diagnostic and burst of 16 images from
2100. PCSX2 DX11 mirror with corrected field and earlier module identified.
It will then be repeated with asynchronous FINISH. Scene result still pending;
the two renderers, hashes and readbacks rule out an FPS comparison with Opus.

During this review, the user confirms that the Kratos spasms
and the NPC animation errors have disappeared in their test. It is kept as a
visual validation provided by the user; the message does not identify the executable's
hash nor duration. It is a favorable result of the set of improvements,
including the PMULTH fix of #67. It does not by itself allow attributing that improvement
to the new FOG nor closing the framing or stability with all the options.

First synchronous/shared control 104 finished: 420.08 s by controller
limit, process 1/launcher 0; copied card intact. First state 11 report
at 158.36 s and last 11. The monitor records minimization between
358.44 and 372.53 s, restored before the burst: do not claim a constant window.
No PCSX2 link faults are logged in the reviewed sample.

16 PCRTC and 16 acquired textures form 16 pairs 2100..2115, 512×448.
Each acquired JSON matches its record; the 16 RGBA are distinct.
18 total acquisitions from the threshold to the end: no regressions,
inconsistent metadata, A-B-A, size changes or unknown hashes;
tick distance 0, without interpreting that figure as latency or FPS.
The 16 pairs and the initial full outputs were reviewed: HUD, Kratos and
enemies, with gradual movements and no abrupt deformation observed in
this window. Similar general framing between outputs of the same run,
without certifying PS2 framing nor pose/pixel equivalence.

**The more intense haze of OpenGL versus DX11 persists with the FOG fixed.**
The semantic regression is real, but its repair does not resolve that visual
difference in this scene. Follow depth, blending and later passes, in addition
to the fog attribute. The asynchronous/shared control is started next
with the same runner, initial card copy, threads off and window 2100.
No game data published; these controls are not benchmarks.

Asynchronous/shared control 104 finished with the same runner: 420.06 s by
limit (process 1/launcher 0), copied card intact, first report 11 at
126.98 s and last 11. Minimization 49.30..241.88 s, restored before the
burst. There are no searched signatures of fatal fault, assertion, invalid access,
unimplemented/unknown opcode or link fault in the two records
reviewed; it does not replace checking all the game's paths.

16 PCRTC and 16 acquired, 16 pairs 2100..2115, correlated metadata and
16 distinct RGBA. 347 acquisitions from the threshold, with no inspector
anomalies and tick distance 0. All pairs and the initial full images
are reviewed: HUD, Kratos and four enemies, gradual movement without
abrupt spasm observed in that window. Similar general framing between
the two renderers of the same run. The excessive OpenGL haze is still
present. The poses of the two passes differ: the same tick between passes
does not align the scene; do not compare their pixels as an isolated effect of FINISH.

Local review of #69: the attribute is global, it is updated before ADC/kick,
all the decoders involved keep FOG and the negative cases
fail with the earlier code. Intact chain 104, full build and synchronous/asynchronous
controls completed. No game process of our own remains
open. Check the CI of the final documentation HEAD before taking it out of draft and
merging. This validation closes the FOG retention fix; still open are
the remaining haze, aligned framing reference, threaded modes, prolonged stability
and usual performance without diagnostics.
## GS: FOG accuracy against the original shader (2026-10-12)

#69 merged as `595fe5a03c80f36199ec727c1ff8672311001fae` after review,
build, functional controls and [final CI 3359e3c green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38336793501).
main is integrated by fast-forward and an independent arithmetic topic is opened.

CPU and GLSL use weights `F` and `255-F` and truncate both products separately.
With F=0 and FOGCOL=(50,100,200), they produce (49,99,199), even though the DX11 reference
produces exact FOGCOL. They also darken a channel whose color and FOGCOL are equal.
The public control `tools/render/probe_fog_reference.py`, through the ABI of the identified
original DLL, confirms 14 RGB patterns: FGE off and FOG
0/1/77/128/201/255, two colors and both difference directions.

The first private uniform-sprite reference does not allow deciding F=255:
PCSX2 treats it as a clear with no fog effect and skips the shader. That
limitation is kept; the final control sends two sprites with different fog values in the
same batch, verifies the uniform half and reproduces the shader, including the
two F=255 cases. The 14 final patterns match a sum of products
of weights `F` and `256-F`, truncated only once. DX11/PCRTC reference alpha255;
the runtime regressions keep framebuffer alpha128.

Patch 105, `ps2recomp-gs-fog-math.patch`, is prepared on top of the full base 104:
CPU, compute and hardware share the fix, without touching post blending,
matrices, CRTC or performance options. An old test expected
FOGCOL=(15,31,47) when programming (16,32,48) with F=0; that expected value is
corrected because it contradicts the verified exact retention, keeping the test.

Native negative before fixing the runtime: 612 normal cases, only the
new CPU regression fails; 650 GPU, exactly the three new CPU,
compute and hardware ones fail. The other 611/647 pass; library 104 untouched. After
fixing the code, the new ones pass, but the old expectation cited fails
in both suites; it is adjusted before repeating the positive. Configuration
0 errors/4 existing warnings; 24 PowerShell, 0 errors. Final normal positive:
612/612 green after adjusting that expected value. Final GPU:
650/650 green, including effective compute and hardware. No known failures are added.
Full build 105, CI and functional control pending.
This one- or two-level difference per channel does not by itself explain the
remaining strong haze nor does it establish animation or FPS improvements.

At the user's request to gather the performance options of both
collaborators, the next full build 105 will incorporate compiled VU1.
The clean Opus checkout is verified and the 501 16 KiB micro-memories listed by its CMake
are copied to a private folder of our own; original/copy identity
checked before and after. Its checkout, runtime or captures are not modified.
The previous controls incorporate its patches, but use the VU1 interpreter and
threads off: they do not represent its 24–25 FPS mode. The generated VU C++ and the
micro-memories will be kept only in the private workspace. Record
runner/hash, VU generation/link and functional control before attributing that
configuration to the new executable. #70 stays a draft until those steps are completed.

Full build 105 with compiled VU1 finished (2026-10-13): source
`3828e9ec499482e039c6d73a0eeb399aa6c42295`, final code 0 in 1169.19 s,
501 micro-memories from the private copy, 13 generated files compiled and
linked. The generator reports 5,991 pair functions and 1,294 blocks.
Runner of 66,302,976 bytes, SHA-256
`747c4224ee0ff19a15ac73dbb8df471a4ea5ce755fc6088e2547a8b9f26a3340`;
ELF with expected hash, symbols/manifest/executable frozen. Flags
`/O2 /Ob2 /DNDEBUG /Zi` and `/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`.
[CI for code/documentation 3828e9e green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38338896408).

The private launcher requested by the user is prepared: it verifies the manifest,
executable hash and ELF, uses a copied card and enables compiled VU1,
VU1/GS-front threads, asynchronous FINISH and shared presentation. It disables the
DX11 mirror, hashes, probes and captures; it allows only the frame counter
`GOW_PERF_DIAG=frames`/`GOW_PERF_FRAME_PC=0x001837B8` to show
`guest_flip_hz`. The `-PrepararSolo` check in Windows PowerShell is green,
without opening the game. No compilers, suites or games of our own remain active.
The PC is left available for its test. Functional control of the new executable,
combined mode and FPS still pending: #70 keeps the draft. Do not attribute
to this binary the scene tests performed with the 104 interpreter.

## Runner 105: review of the manual test and meaning of the counters (2026-10-13)

The remote references are fetched again and `origin/main` is integrated, already
contained in the branch, without rewriting history. The four checks of the documentation
HEAD `3b1715e` ended in SUCCESS, [run 38340666366](https://github.com/KIexster/god-of-war-recomp/actions/runs/38340666366).
Manifest, build result and SHA-256 of the frozen runner 105
match the previous entry; `-PrepararSolo` green. No rebuild.

The `err.log` and `out.log` of the private manual test
`prueba_usuario_0843bf95ada5435895db0bc966a91559` are reviewed. They show the hardware renderer,
shared presentation and active VU1/GS-front threads; they contain 166 pad2
reads, with real buttons and sticks. There are 20 profile windows, up to t=113.80
of the counter clock. The last six report 26.25..37.07 Flip entries/s and
9.06..14.80 host iterations/s. Three other windows record host
0.91/0.65/0.59 per second; the first two last 7.71/9.17 s. Do not omit
those slow stretches or present the maximum as sustained performance.

`ps2_perf::guestEntry` counts entries to `vid::Flip` (`0x001837B8`) from the
dispatcher or direct calls. The host increments `hostFrames` after
`renderFrame`/`EndDrawing`; it may draw the same texture again. Acquire
picks the most recent publication whose fence finished and may keep the
previous one. Therefore, **neither counter measures unique frames
displayed**, nor is there a mandatory one-to-one correspondence. The code
keeps fences and does not introduce a global `glFinish` to hide this difference.

All time scopes in the manual test log are zero: the
`GOW_PERF_DIAG=frames` mode disables its timers. Zero does not establish absence
of work or waits. The test lacks `pad2:state` reports, a window monitor
and a result with exit code/cause. out contains texture release,
but that only establishes part of the teardown. It does not allow attributing
the windows to a specific scene, minimization, GS wait or normal shutdown;
nor does it offer an aligned visual reference or prolonged stability.

The controls launcher supports `--perf off|frames|timing` and
`--presentation-diagnostics hash|sequence|off`, keeping hash/off as
options independent of the profile and disabling inherited diagnostics.
`timing` enables exclusive elapsed times per thread, not CPU usage;
scopes are accounted when switching/closing, not at the moment of the report.
Capture still requires an explicit option. Options and the
meaning of the metrics are recorded in the private result. 21 Python tests
green; configuration 0 errors/4 existing warnings; 25 PowerShell scripts,
0 errors. These checks test the tool, they do not yet validate #70.

`--pad-script` is added to register an explicit controller script in the
control, keeping `GOW_PAD_SOLO_GUION=1` and discarding inherited scripts.
Reason: the default script only presses Start/Cross at the beginning; the new
passes later reach state 14, which is not used as a sustained gameplay
sample. 22 preparation/isolation tests green after
extending it. The explicit script does not turn the control into a deterministic replay.

## GS: functional control of accurate FOG with runner 105 (2026-10-13)

Three sequential controls completed on the same frozen runner 105
from `3828e9e`/SHA-256 `747c4224...a3340`, compiled VU1 and private cards
copied from the same initial one. The user confirmed the PC was free; no
other local games, builds or suites were run simultaneously. CPU
and the DX11 mirror are kept. The passes with the mirror have both threads off;
the combined one has VU1/GS-front enabled and does not use the mirror.

| Shared control | Duration | First pad state 11 | Final state | Acquisitions | A–B–A | Max host/image distance |
|---|---:|---:|---:|---:|---:|---:|
| Synchronous FINISH, DX11 mirror | 420.07 s | 50.15 s | 11 | 3,313 | 0 | 0 |
| Asynchronous FINISH, DX11 mirror | 420.07 s | 45.14 s | 14 | 4,096 | 108 | 19 |
| Asynchronous FINISH, both threads | 420.04 s | 35.04 s | 14 | 4,096 | 6 | 32 |

All end at the limit (process 1/controller 0), with the card intact.
No monitor records minimization; focus varies in the synchronous one and does not
belong to the game in the other two. Visible does not prove an uncovered window.
The searched-for signatures of exception, assertion, invalid access,
unknown/unimplemented opcode or mirror failure do not appear. This is not proof of
normal shutdown or prolonged stability. Both 4,096 quotas are exhausted;
they do not cover all acquisitions until shutdown. No sequence regressions,
inconsistent metadata, size changes or unknown hashes are found.

The 108 returns of the asynchronous one appear after the last state
14 report; 107 have equal parity and one alternates, all in field mode. A hash
that returns does not establish pixel equality or old content. State 14
is not used as sustained gameplay. None of these passes measures FPS.

Synchronous: 16 acquired/PCRTC pairs 2100..2115, introduction camera/NPCs
without HUD. Asynchronous: acquired 3999..4014 and PCRTC 4000..4015, 15 pairs per
tick and one acquired 3999 without a pair within the quota; HUD, Kratos and enemies.
All pairs and the first full outputs are reviewed: gradual
movement with no abrupt deformation observed in those windows. **The OpenGL
haze, stronger than DX11, persists**. The coinciding tick within the
run does not guarantee the same command prefix or pixel equivalence.

Combined: 16 acquired 3989..4071 with jumps, HUD/Kratos/NPCs and gradual
movement in the reviewed images. The first acquired has
hostTick4001/frameTick3989: the threshold chooses when to capture on the host, it does not
force acquiring a later tick. The 16 images of each pass are
distinct in RGBA and their JSONs match the records. Do not compare poses
between runs because they share a tick.

Local review of #70: weights and sum match the 14 external patterns;
CPU and the shared compute/hardware shader keep alpha and post blending.
Negatives, positives 612/612 normal and 650/650 GPU, full build 105
and these controls close the local validation of the numeric fix.
Before ready/merge, check CI of the final HEAD. Still open: remaining haze,
PS2 framing, presentation freshness, full playability,
prolonged stability and unique frames displayed.

## Runner 105: host wait and new depth control (2026-10-13)

Separate profile without mirror, hash or captures, with both threads, timers
and an explicit Start/Cross script and attacks every two seconds. First attempt:
116.92 s until its own STOP, without reaching IRX, pad reads or states;
Flip=0/host≈60. Not usable as a gameplay profile. The second, with the same
options, does start and completes 240.06 s at the limit. The hang has no identified
cause; do not attribute it to the profile or the script from that single pair.

Repeat: card intact, window visible/not minimized without foreground,
no searched-for error signatures; last state 14. The line-order selector
keeps 14 complete state-11 windows between t=50.07 and 120.54 of the profile,
70.46 s. Weighted Flip 29.19 entries/s (15.80..35.55 per window), host
13.69 iterations/s (10.37..20.52). Upload accumulates 4,014.37 ms and HostWait
66,320.16 ms. The last scope contains `EndDrawing`, which includes drawing,
swap and limiter; the preparation contains selection/queue/acquisition.
It is a localization of the host's elapsed time, not CPU usage nor an isolated
GPU cause. Separate driver, limiter and GPU/queue without removing fences or adding
`glFinish`. VU/GS times may come from other threads and do not form
a split of the EE thread. The pass offers no aligned images, benchmark with
Opus or unique frames displayed; sampled states do not fix camera/poses.

Private procedural fixture of 24 cases per mode, same runtime 105 and DX11
DLL: CPU/compute/effective hardware give the same 11 differences.
Seven come from ZTE off: color is discarded with ZTST 0/2/3 and depth
is written with ZTST 1, while DX11 draws and keeps Z. The original GS
read also conditions the Z test and write on ZTE. Another four
differ by one level during blending, two with FGE off; track them separately
before changing blending. Neither runtime nor runner was modified, and it has not yet been
established that the game's fog pass uses those ZTE cases.

## GS: depth test and write enable (2026-10-13)

#70 merged as `4792988b83c26b318ec455c8666e945194a01323`, after local
review, controls and the four checks of the [final HEAD b6d1559 green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38390456236).
main is integrated by merge and an independent topic is opened in
`codex/gs-depth-enable`, first checking the tree is clean.

Patch 106, `ps2recomp-gs-zte.patch`, conditions the Z test and write
on TEST.ZTE. With ZTE=0, CPU and the shared compute/hardware shader ignore ZTST
and keep the existing Z value, even with ZMSK=0. It does not change alpha, FOG, blending,
fences, FIFO, performance options or the reference renderer.

The original DX11 procedural fixture/24-case corpus gave 11 differences
with 105: seven from ZTE and four one-level blending ones. After fixing ZTE,
CPU/compute/hardware match in the 16 depth cases; the four minor
blending differences remain, including two with FGE off.
They are kept for separate investigation. They do not yet establish a cause of the
haze in the game nor authorize changing blending without another contrast.

New regression: 16 ZTE/ZTST/ZMSK combinations, color/alpha, depth and neighboring
pixel; GPU requires effective compute/hardware, without CPU as an oracle.
Negative against untouched library 105: the three CPU, compute
and hardware groups fail. First normal positive: 612/613; GPU: 652/653. Only
the old PACKED XYZ2 fixture fails, which intended to write all Z32 bits but
programmed TEST=1<<17 without ZTE. ZTE=1 is explicitly enabled, keeping
all its expected values and native/fragmented paths; the test is not removed.

Final positives: **613/613 normal and 653/653 GPU**, codes 0. GPU
reuses only the private cache 106 from the first pass, with keys
that include the full shader; these times are not a benchmark.
Test SHA-256 `bd67ab7f3e9225767dc9c96f15d5c09297b008f8e0be66a961f439e90faef8a8`;
library `57022e3a794851038bc141600cf00069daa939c01073e03ee15ac3235c5dba69`.
Originals of sources/fixture/library/test 105 and identities kept
in a private snapshot before editing. The frozen runner 105 remains untouched.

106/106 patches checked/applied in order from the pin in a new private
worktree, without reset/clean of Opus's directories. Configuration
0 errors/4 existing warnings; 25 PowerShell, 0 errors. No known failures
added nor game data published. **Full build of runner
106, final CI and functional control still pending**; do not carry over the
105 scene results to the new behavior. Continue with the fog pass
with depth/blending state and a coherent command reference.

Full build 106 finished: source
`32be6ec31da2decf7b49e6ee4c190a39070e0526`, code 0 in 1175.59 s,
VU1 compiled with the same private copy of 501 micro-memories and 13
generated files compiled/linked. Runner of 66,302,464 bytes, SHA-256
`fc2436ee121feaa15e14e7f2dd0998ee6eb6b0c251a5e292af4397cb82e46f72`.
Manifest and ELF checked, binary/symbols frozen, flags
`/O2 /Ob2 /DNDEBUG /Zi` and `/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`.
Full-build library `5c3787e7ae5a47c427efd0cdd0c4de469bed33c132e34e0a4ea370d7a5ec67bc`;
the earlier suites used another artifact from the same sources/fix.
The first attempt failed before the compiler when reading Python CP1252 output
as UTF-8; it is kept and repeated with explicit encoding in a new
folder. The log of a previous build is not interpreted as that attempt.

[CI for the complete code 32be6ec green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38393297586).
After the full build, main with #72 is integrated by merge at
`834f6ec15529f497de08c11370615540f3aefb66`; the runner's source is still
32be6ec. #72 fixes the metrics summary, with 13 tests and
[final CI ed05d9f green](https://github.com/KIexster/god-of-war-recomp/actions/runs/38394545326),
merge `08103d113ebb57edbc2b8b2e810e4d08d7e24371`.

Controls 106 synchronous and asynchronous shared, original DX11 mirror,
both threads off, cards copied from the same initial one:

| Control | Duration | First report 11 | Final state | Acquisitions from 4000 | A–B–A | Max distance |
|---|---:|---:|---:|---:|---:|---:|
| Synchronous | 420.08 s | 91.19 s | 11 | 1,026 | 0 | 0 |
| Asynchronous | 420.08 s | 45.13 s | 14 | 4,096 | 110 | 10 |

Both end at the limit (process 1/controller 0), with the card intact,
without minimization or searched-for failure signatures. Windows visible without
foreground; that does not prove they were uncovered. No regressions of
sequence, inconsistent metadata, size changes or unknown hashes.
The asynchronous one exhausts the quota; its 110 returns appear after the last
report 14 and do not prove old content. Do not use state 14 as sustained gameplay.

16 acquired and 16 PCRTC from each pass, 16 pairs 4000..4015, all
correlated and with distinct RGBA. The pairs and the first full
outputs are reviewed: HUD, Kratos and enemies, gradual movement with no abrupt
deformation observed in the sample. **The stronger OpenGL haze persists
with ZTE fixed**. Comparing within a run does not guarantee the same
GIF prefix; do not compare pixels with another pass because they share a tick. These are not
benchmarks, normal shutdown, PS2 framing or prolonged stability.
Combined control 106 in progress; #71 keeps the draft until its
validation is completed and CI of the final HEAD is checked.

Combined 106 finished: 420.05 s at the limit, process 1/controller 0,
card intact, without minimization or searched-for error signatures. First
report 11 at 35.07 s of the pad; last 14 at 415.92 s. 4,096 acquisitions
(quota exhausted), 18 A–B–A returns after the last state 14 report,
max distance 27; zero regressions, inconsistent metadata, changing
sizes or unknown hashes. Do not turn those returns into proof
of old content nor state 14 into sustained gameplay.

Its 16 acquired 3989..4045, with jumps, have distinct RGBA and correlated
JSONs. All 16 images reviewed: HUD, Kratos and enemies,
gradual movement in the sample, no abrupt deformation observed; intense
haze remains. This control does not use the mirror because both threads are
active. The three completed 106 controls, together with negatives, native
positives and full build, close the local validation of **ZTE**.
They do not close host freshness, PS2 framing, full playability or prolonged
stability. Check CI of the final documentation HEAD before ready/merge #71.

The module's current reference reinitializes GSOptions, inheriting Basic blending
accuracy from Config.h at 2954ebe; it does not pin it to Maximum. The original
HLSL has hardware/software blending paths and documents GPU-dependent
hardware approximations. Therefore the four minor differences of the
Basic corpus are not enough to change CPU/GLSL. A separate Maximum DLL is prepared for that
contrast, keeping the original module and its hash; it is not
yet built or tested. Continue with command prefix, depth, blending
and later passes before attributing the remaining haze.

### Reproducible DX11 Maximum reference (2026-10-13)

The previous preparation was completed. Separate private Maximum DLL, SHA-256
`aa98175972b0c3c654861465cba83934ec5edffa9e74f5128458182492f93546`,
ABI/exports/rejections without a device and two GPU cycles of 2,048 RGBA
green. With the 24-case corpus, CPU/compute/hardware match 24/24;
the four minor Basic differences disappear without changing the runtime.
The original Basic DLL remains untouched, SHA-256
`cbbc2d060df61e479355479fc3ce5b054e5ce27302bf19d5accda735d21ecd62`.

Control with that private DLL and frozen runner 106: 420.386 s at the limit,
process 1/controller 0, card intact. Both threads off, synchronous
shared presentation; no other simultaneous loads detected. First state 11
report at 50.17 s; last 11 at 415.47 s. Window visible and not minimized
at the two recorded transitions; no searched-for failure signatures.
16 acquired and 16 PCRTC, pairs 4000..4015 reviewed plus the first full
pair. HUD, Kratos and enemies; distinct RGBA and correlation with metadata.
672 acquisitions, no regressions/inconsistencies/A–B–A returns/changing
sizes/unknown hashes; max distance 0. No exhaustive supervision
of focus or occlusion, normal shutdown, prolonged stability or unique FPS.

OpenGL keeps a stronger haze and line/pose differences compared
to Maximum. Do not compare with another run by tick nor claim an aligned prefix:
DX11 VSync is observed before EE callbacks/IRQ; OpenGL presentation is
requested from the host loop, which may find later commands.
This is a possibility established by the code order, not yet quantified
in this scene. Continue with composition/depth/later passes in addition to FOG.

`GOW_PCSX2_BLENDING=Maximum|Basic` is added to the isolated module's CMake:
Maximum explicit by default, Basic available to reproduce the earlier behavior,
other values rejected; the DLL declares the accuracy when creating GS. ABI 1
unchanged. New public procedural control of 24 cells, all its pixels,
with expected RGB values contrasted with the four renderers; historical Basic
20/24, private Maximum 24/24. It does not prove framebuffer alpha nor the game.
Building this tool does not replace that of runner 106; patches, runtime
blending and CPU references are not changed.

Isolated build of the tool complete: 107 units compiled/linked.
Final Maximum DLL `9f0130e26d34ce26c0ee3423d56a77358fd0fec2351661cd194a879328179bb7`:
24/24 pipeline, 14/14 FOG, two GPU cycles of 2,048 RGBA and six CTest green.
Basic configured by CMake
`b6f43f1778fa450db764cda512f5526cc8de1a3ef8e95e2e697e00ba42136cb7`
reproduces 20/24 with the same four one-level cases, and passes the contract
without a device. Invalid configuration rejected, Maximum restored and
final artifact verified again; historical Basic untouched. Port configuration
without errors/four existing warnings and 25 PowerShell scripts without
errors. The earlier scene control corresponds to aa9817, not to this DLL.
CI of the published HEAD pending before merging this stage.

### Fog with a common boundary and limits of the hardware mirror (2026-10-13)

[#73 merged](https://github.com/KIexster/god-of-war-recomp/pull/73),
merge `b41467f8b063c34ba553aa914a9d7f662042d9e8`, after local review and
[four green CI checks of HEAD 80a782f](https://github.com/KIexster/god-of-war-recomp/actions/runs/38449849007).

Separate private diagnostic, without changing runtime/runner 106: the DLL receives
each GIF span, direct write, reset and VSync under the same ABI mutex.
It delivers the stream to DX11 Maximum and to another GS frontend with OpenGL 106; it requests
its capture at that same boundary before accepting new events. The
19 privileged input registers, empty initial state and PATH order are kept.
It does not save the full stream of approximately 20 GB. The host's
presentation remains independent; this diagnostic adds a renderer and queue
cuts/readbacks, so it does not measure performance.

Private DLL `6c7e1ed41b75f6f0411c86f139684a5c7c9c94631f535ae3a767d09232a59be8`,
runtime library of the full 106. Patterns: DX11 and OpenGL shadow 24/24 RGB
and cell uniformity; two ABI/GPU cycles with fragmented GIF, direct write,
reset/close and 2,048 RGB per cycle green. The first pattern mixes
hardware/compute at startup; do not attribute that whole pattern to hardware.

Synchronous shared control, threads off, private card: 600.405 s at
the limit, process 1/controller 0, card intact. First report 11 at 55.34 s,
last 11 at 594.38 s. No searched-for failure or minimization signatures in the
recorded window changes; focus changed. 1,106 acquisitions, max
distance 0, no regressions/inconsistencies/A–B–A returns/changing sizes or
unknown hashes in the sample. It does not establish occlusion, normal shutdown,
full combat, combined mode for ten minutes or prolonged stability.

16 DX11/shadow pairs at boundary 4000..4015 and 16 host acquired frames,
512×448, distinct and with correlated acquired metadata. The
16 crops and four full triples are reviewed. At 4000 the shadow prefix contains
14,984,206 spans/17,393,025,344 bytes and zero direct writes; effective GPU,
151,982,196 primitives/0 tiles. In the following 15 intervals, 64,494..65,782
primitives and zero tiles: hardware in the burst. **The stronger haze
persists with that common stream and boundary**. In the background region of the
first pair, shadow exceeds DX11 on average by +31.50/+37.63/+32.92 RGB;
on the floor the mean difference is below one level per channel.
These are descriptions of regions, with no equivalence tolerance or single cause.
DX11 Automatic keeps field history; OpenGL duplicates rows. The host's
request offset does not by itself explain this diagnostic contrast.

Private composition corpus, 16 cases EN1/EN2/MMOD/SLBG/ALP/alpha: runtime CPU and
OpenGL match each other in 16/16. Against DX11 hardware they match
in 10/16; against PCSX2's original software with DX11 composition, in 11/16.
There are large differences when using RC1 alone with alpha zero or reduced ALP, one
minor rounding difference and hardware/software discrepancies with alpha 64.
Example dual/MMOD=0/alpha=64: hardware (240,64,128), original software and runtime
(128,112,80). RC1 alone/MMOD=1/ALP=64: both original renderers (210,54,100),
runtime (240,64,128). Do not attribute those results to the scene's haze
without its registers/passes; Maximum does not certify all alpha paths.

Private software reference `3ad27ad874ec7e8bcba35396bb2134f158156261d392965978cc43085587db55`:
uses the original GSRendererSW factory, zero extra threads and DX11
device/composition. It passes 24/24 pipeline and 14/14 FOG. Only tested with procedural inputs;
its fixture rejects direct writes, without simulating Q retention. It is not an
integrated renderer of the game nor a validation of the whole ABI. CPU and hardware
mirror are kept. Next contrast: merge output before
deinterlacing and a bounded burst with a verifiable initial state for the original
software; continue with depth, alpha, texture/FOG and later passes.

The full contrast of that procedural burst reveals another limit of the
hardware reference: the 14 historical FOG controls only verified the
left half. With both halves there are 28 controls; runtime CPU/OpenGL
and original software match in 28/28, hardware Maximum in 16/28. Its 12
right halves with FGE use the FOG of the first sprite. For example, F=0 on the
left and 17 on the right: hardware produces (50,100,200) in both,
original software and runtime (50,100,200)/(62,95,190). The 14 left
expected values, including those of the #70 math fix, remain valid;
the method does not exclude every hardware optimization of a batch with different fog values.
It does not prove this occurs in the scene's background nor justify reducing FOG globally.

`probe_fog_reference.py` now checks both halves by default, color and
uniformity of all pixels; `--left-only` reproduces the earlier 14.
Real hardware negative 16/28/code 1; original software positive 28/28/code 0;
private CPU/OpenGL 28/28 RGB and uniform. The historical mode keeps 14/14.
Runtime renderer/alpha is not modified. It remains explicit that PCRTC
does not by itself validate framebuffer alpha or interpolation inside a primitive.

Private merge/Freeze/GIF/VSync tool already built: it limits the burst
to 16 fields/160 MiB, requires complete outer fragments at the boundary and
a valid End. Original Freeze includes reading cache destinations to
capture VRAM; it is not published. A synthetic burst of four fields, 11 registers,
4,237,045 bytes, is restored in the original GSRendererSW: its four
64×32 images match entirely in RGB a fresh run of that software.
The disagreement with hardware is also reproduced without Freeze and is localized
in the right half; it is not attributed to restoration. A truncated End is rejected
before creating the device/directory. The initial deinterlacing history
is not serialized. Control of this tool with the game pending.

### Repeated scene burst with the original software (2026-10-13)

[#74 merged](https://github.com/KIexster/god-of-war-recomp/pull/74),
merge `6aaa1ed0f595f7f91a9e4e27d72481fd0fa92060`, after local review and
[four green CI checks of HEAD 622af4b](https://github.com/KIexster/god-of-war-recomp/actions/runs/38456073463).

New control with the frozen runner 106, synchronous shared presentation,
threads off and private card. Separate diagnostic DLL
`eeef73a7162c129f67f03da037765d20071682492b0c1e7b6bf9df3bf54786de`:
keeps the original DX11 Maximum renderer and the second frontend/OpenGL of the
common-boundary contrast. It also reads its merge output **before
deinterlacing**, saves the original Freeze at 3999 with cache destination
reads and records the later events until End 4015. It does not modify IRQ/FIFO,
runner, patches or the main renderer. The readback and the additional reference
may alter timings/caches; they are diagnostics, not a speed measurement.

It ends at 600.391 s at the limit, process 1/controller 0; card intact.
First state 11 report at 55.84 s, last 11 at 596.70 s; no searched-for failure
signatures or minimization in the recorded window changes.
1,167 acquisitions, no regressions/inconsistencies/A–B–A returns/changing
sizes/unknown hashes; max distance 0. 16 acquired, 16 PCRTC, 16 merges and
16 shadow frames are obtained, 512×448, in 4000..4015; the acquired ones are
correlated and there are 16 distinct RGBA. It does not certify occlusion, normal shutdown,
full game, prolonged combined mode, unique FPS or long stability.

The private burst has 100,082 records/114,804,229 bytes, under the
160 MiB limit, with initial Freeze, GIF, 17 VSync 3999..4015 and valid End. It
contains no direct writes: the software fixture still rejects them.
Private restoration reference
`894057dfb542ca43abd9d1b934301151c9c740cf6d67f8a5c212e860dd486a1c`,
original GSRendererSW and DX11 device/composition, ends with code 0 and
17 images. The format requires continuity and End before creating the device;
its synthetic restoration control and truncation rejection are recorded above.
The Freeze includes native VRAM and GS state; **it does not keep the initial
deinterlacing history**. It does not demonstrate equivalence of caches/optimizations between
hardware and software nor integrate that software as the game's renderer.

The 16 triples are reviewed in reduced contact sheets and four full ones of
4004/4007/4011/4015, after several warm-up fields of the reference.
The original software keeps a background close to the hardware merge;
**the excess brightness/haze remains in OpenGL**. In the background region
x=210..439, y=35..149 of 4004, OpenGL−software has a mean of
+31.03/+37.26/+32.57 RGB; software−hardware has a mean of
−0.44/−0.45/−0.41 and absolute mean 0.49/0.50/0.45. In the 16 images,
that absolute software/hardware mean is below 0.68 per channel.
These are descriptive measurements of that region, with no equivalence tolerance:
the full images also have differences and the initial fields
do not restore earlier history. In the background of 4000, current PCRTC and hardware
merge match in RGB; there the later deinterlacing does not explain the
brightness contrast with OpenGL.

The composition registers are constant across 3999..4015: PMODE `0x8023`
(EN1=EN2=1, MMOD=1, AMOD=0, SLBG=0, ALP=128), SMODE2 `0x21fed1`
(INT=1, FFMD=0), DISPFB1 `0x800000090d0`, DISPFB2 `0x90d0` and BGCOLOR=0.
This bounds the contrast to the real configuration; the procedural disagreements
of alpha and variable FOG of the mirror do not by themselves demonstrate the cause of the
background. As an inference, the persistent disagreement against both references
points the next control toward the runtime. The same backend
command field remains to be repeated, with its initial state/VRAM, on CPU and GPU to separate
frontend interpretation from rasterization; continue with depth, blending,
texture/FOG and later passes. **The haze is not fixed**.

### Freshly drawn destination, alpha and CPU reference (2026-10-13)

[#75 merged](https://github.com/KIexster/god-of-war-recomp/pull/75),
merge `9ac5585f1a8400922223e41719e6bc01c7e4e35d`, after local review and
[four green CI checks of HEAD 0f42d7f](https://github.com/KIexster/god-of-war-recomp/actions/runs/38460157286).

New private diagnostic, frozen runner 106: it records one backend field
after VSync 4002 and until Present/End 4003, with its own state/VRAM.
DLL `7bb35c83b832fa1b055e8fc269f1640d1bcd94952b80d67701f28d33d261edb6`;
64×64 pattern validated first, two CPU/compute/hardware repetitions with final
state and images green. The previous DLL is kept and the game is not changed.
Synchronous shared control, threads off: 450.224 s, stopped by its own
STOP after completing the capture and 16 samples; process 1/controller 0,
card intact, first report 11 at 55.21 s, last 11 at 442.00 s. It is not a
full 600 s control nor a normal shutdown. 283 acquisitions without searched-for
anomalies, max distance 0; 16 acquired/PCRTC 4003..4018 correlated and
distinct. No FPS, prolonged stability or validation of combined mode.

Record of 33,391,712 bytes: Initial, 78,181 Submit, 23 TEXFLUSH, 139 CLUT,
three transfers/three uploads, Present and End. No Submit enables FGE.
The CPU reference and the candidate are restored from that same initial state.
Two hardware repetitions up to Present have RGB/VRAM/state differences;
the first mixes compute while shaders warm up, the second records zero
tiles. A full CPU replay returns code 3 because it does not reproduce the GPU End.
**Parity is not declared nor is that code turned into success**.

The PCRTC image of 4003 copies inherited FBP0 to FBP208 at the start of the field;
afterwards the new scene is drawn in FBP0. That the CPU repeats the haze when presenting
FBP208 does not exclude a previous GPU problem. A probe changes only the
two Present DISPFBs to read the freshly drawn FBP0 destination as CT32:
it is a diagnostic request, **not the game's presented image**.
CPU/GPU have 122,960 distinct RGB pixels, absolute mean
9.92/11.71/10.34; two warm hardware passes have the same RGB even though
their final VRAM differs by 1,151 bytes. Requested compute produces the same final
RGB as hardware in this probe. It does not establish global stability.

Independent prefixes with the same previous input and readback at the end
bound the background contrast: after clear 54, RGBA and Z are zero in
the inspected regions; the background RGB stays the same until 76158.
The large difference appears in the 64 triangles 76160..76223, with FGE=0,
T8 and ALPHA `0x54`, whose equation uses the destination alpha. Before that pass,
the background alpha already differs: after 76158, CPU mean 63.43 and GPU 102.24;
after 76223, GPU exceeds CPU by +26.77/+31.78/+27.88 RGB.
The Z24 read in the regions remains identical in the four prefixes
76076/76142/76158/76223. These are local descriptions, without global equivalence.
Experimental snapshot per Submit does not change this probe's RGB; invalidating
the CPU texture page per Submit does not change its result either.

The alpha divergence is introduced in block 75983..76076: preparation
CT24 in FBP320 and Z16 read towards a CT16 destination in FBP0 with FBMSK `0x3fff`.
A first reduced Z16/CT16/mask pattern does not reproduce the whole disagreement of
the scene and also shows differences with the original software. Therefore,
it is not yet attributed to a specific conversion, mask or synchronization.

Meanwhile the audit identifies an error in the CPU reference: it always
applies saturation to the ALPHA result, even with COLCLAMP=0. Four full
64×64 procedural patterns contrasted with original GSRendererSW and GPU
match the wrap/clamp expected values. For example, −(32,64,128) wrapped gives
(224,192,128), not zero; (200,220,240)+(80,64,32) wrapped gives (24,28,16), not 255.
CPU 106 fails those two controls and passes the two saturation ones. The Maximum
hardware mirror fails the two negative ones even with saturation, through a
path that keeps the source color; do not use it as the sole authority here.

Separate patch 107 `ps2recomp-gs-cpu-colclamp.patch`: CPU selects wrap or
saturation of the ALPHA RGB and keeps alpha/Z and the rest of the pipeline.
Regression without the game: CPU 106 fails 2/4, code 2; new CPU object with the
rest of library 106 passes 4/4, code 0. It does not modify GLSL. COLCLAMP=0
appears in this scene's mask preparation: the darker CPU
did not certify that GPU was wrong in that block. Runner/runtime
106 are kept while the reference fix is validated.
Full incremental suite relinked with CPU/main/regression/table 107 and
remaining libraries 106: 617/617 normal and 657/657 with GPU controls,
codes 0, no known failures added. It does not replace the game's full build.
`scripts/2_compilar.cmd`, CI of the final HEAD and functional control of 107
remain pending before merging. **The GPU haze and
its fidelity against the original software remain open**.

### 2026-10-14 — Full build of the CPU reference 107

The mandatory full `scripts/2_compilar.cmd` finished with code 0 in
1,110.174 s, source `f76bc46327ca646a1eb5fc6103b4b484d1d9be8b`, 107 patches,
VU1 compiled and 501 private micro-memories. The 13 files `programa0..12`
were compiled and linked. Executable of 66,302,464 bytes, SHA-256
`c19f1d31ab52d26d3cdd09ca68310c74d62595435d912e9ba30f122aff1af250`;
runtime library
`49c3458c2acb8ff45f0c6d5126403b1c4d19944a2dd098e779987ba49b88acb9`.
Manifest and binaries were kept in a private folder; runner/runtime
106 and its library `5c3787…67bc` remain untouched.

The first attempt ended with code 1 when exclusively its FFmpeg
download was interrupted after 9,412.85 s, before building the runner. Its logs
and partial file were kept. CMake had removed the local copy because
the project does not define URL_HASH. The retry verified the existing private file
by SHA-256 and extracted it normally through a guard in its
generated CMake script; neither the dependency nor the C++ sources were changed.

The four CI checks of the source HEAD passed in `38487502682`.
This establishes build and tests; **the functional control 107 is still
in progress** and PR 76 remains a draft. The OpenGL haze, normal shutdown
and prolonged stability are not declared fixed.

### 2026-10-14 — Closed functional controls of runner 107

The following three controls use the full executable 107 above,
with a copied private card, whose SHA-256 remained identical before/after
and to the original. Logs and captures were reviewed. The searched-for
signatures of exception, assertion or unknown opcode were not found; that search
does not rule out other failures. The processes were closed by the control's limit,
**without establishing normal exit or prolonged stability**.

`scripts/probar_menu.ps1 -Segundos 115` finished in 115.343 s, controller 0.
Nine captures show title, new game, difficulty, Kratos's introduction
and the start of the ship. The report reaches state 11 at 91.68 s. This
script did not record the minimization state and does not measure presented FPS.

Synchronous shared control with compiled VU1, VU1/GS-front threads off
and original DX11 Maximum mirror `9f0130…79bb7`: 420.390 s, process 1 by
limit/controller 0. First state 11 at 50.24 s and last at 410.74 s;
window without recorded minimization. The 16 acquired and 16 DX11 frames
4000..4015 correlate with their records, are distinct and are
512×448. The contact sheets and two full pairs were reviewed: HUD,
Kratos and enemies appear; OpenGL keeps the excessive haze and there are also
line/pose differences. The same tick does not demonstrate the same command
prefix. 520 recorded acquisitions without sequence regressions,
inconsistent repetitions, A-B-A returns or size changes; maximum
hostTick−frameTick distance 0 in this record, not equivalent to FPS.

Combined shared control, asynchronous FINISH and VU1/GS-front threads
actually enabled according to the log: 420.046 s, process 1 by
limit/controller 0, no recorded minimization. First state 11 at
35.06 s; the last report is state 14 at 416.41 s. **420 s of sustained
gameplay are not established**. The 16 distinct, correlated acquired frames
512×448, frameTicks 3990..4039, show HUD, Kratos and enemies in the
sampled scene. The 4,096 acquisitions have no sequence regressions,
inconsistent repetitions or size changes. There are 32 A-B-A returns:
30 with the same parity and two alternating, all with recorded field
mode. They are not attributed to corruption or stale image without investigating
state and pixels. The distance between ticks is between 0 and 22; they are not
milliseconds, unique frames or a latency measurement.

The bounded functional validation of the CPU COLCLAMP change is closed. The
final documentation and its CI must still be incorporated into PR 76 before
merging it. These controls do not resolve the haze, the framing,
real presented performance or a prolonged combined session.

### 2026-10-14 — TEXA in depth textures: external negative and candidate 108

`GSLocalMemory` of the original software was reviewed: `ReadTexel24Z`,
`ReadTexel16Z` and `ReadTexel16SZ` call the same TEXA expansions as their
color formats. The runtime's CPU and GLSL only applied TA0/TA1/AEM to
CT24/CT16/CT16S and omitted Z24/Z16/Z16S. In the real block 75983..76076 of
the earlier backend capture, TEXA has **TA0=0, TA1=0, AEM=false**;
32 sprites sample Z16 with DECAL/TCC=1 towards CT16 and FBMSK `0x3fff`.
The initial assumption TA1=128 does not correspond to that input and is discarded.

Procedural control without the game, 48 full 8×8 cells in a 64×64 image:
six color/depth formats and eight TA0/TA1/AEM patterns, zero RGB and the
high 16-bit bit. Alpha is written and observed through a later blend
that uses Ad. Original GSRendererSW and DX11 Maximum pass 48/48. CPU 106 and
GPU 106 pass 29/48: the 19 failures are from the depth aliases, while
the 24 color cases pass. The GPU is really enabled; this fixture
mixes hardware/compute and does not certify hardware exclusively. The
Z16 high-bit case with TA0=TA1=0 returns 128 in the earlier runtime and 0 in both
original references.

Candidate 108, separated in `ps2recomp-gs-texa-depth.patch`, adds only
the three aliases to `applyTexa` CPU/GLSL. It keeps RGB, blending, FOG, depth,
fences and presentation. Independent regression: CPU 107 without the change fails
the three tests, code 3, with 19 wrong patterns; CPU 108 passes 3/3 and
OpenGL 108 passes 5/5, including compute and hardware observed without CPU
fallback. It also checks the RGBA and the uncovered neighbor. Full
incremental suite with CPU/GLSL/main/regression objects 108, full runtime library
107 and earlier test libraries: 620/620 normal in 11.821 s and
662/662 GPU in 209.116 s, codes 0, no known failures added.
**It does not yet replace the mandatory full build nor the control of runner 108**.

The same prefixes 76076/76158/76223 of the field recorded with
106 were repeated, changing only the CPU/GLSL objects to 108. First a complete
procedural record was validated, code 0 and exact End state/VRAM/RGB.
In the sky and actor regions, CPU and GPU 108 produce identical RGBA and
the Z24 remains the same. After 76076, the sky's mean alpha changes
from 206.7415 with corrected CPU 107 to 85.9133; after 76158 and 76223,
from 102.2364 to 43.1870. The RGB after the late blend 76223 drops from
85.2845/95.5252/82.4820 to 44.6819/47.2167/40.0719. This attributes part
of the brightness to the TEXA expansion of that same input, without comparing ticks
from different runs. The partial replays still return 1 due to
other VRAM/transfer-progress differences: there is no global parity.

The reading above uses a **synthetic probe of freshly drawn FBP0**;
the real PCRTC of that record copies inherited FBP208 at the start of the field.
It does not establish the presented image of runner 108 nor its final fidelity.
Next: isolated full build with 108 patches and compiled VU1, mandatory menu,
new capture with CPU/GPU 108 and DX11 mirror within the same run,
original-software repetition at the same boundary, and combined control.
Remaining haze, framing, unique presented frames and prolonged stability
remain open.

### 2026-10-14 — Full 108 finished; functional control still pending

`scripts/2_compilar.cmd` finished with code 0 in 1,171.305 s, source
`084908442f9640535cbd94bb9dcc216c9e46738d`, 108 patches and VU1 compiled with
501 private micro-memories. The 13 files `programa0..12` were compiled
and linked. Executable of 66,302,976 bytes, SHA-256
`a147193bcf80eb5cdf1c5c68a3cefb201f9f1dcc9ba80eb5f3f509c849e3fd3a`;
runtime library
`116b54c428b5f9d9c85fd7f8c04a3ff4d6dbfdee09634340f0160ea44eff6645`.
Manifest/binaries in a separate private folder, without modifying the
libraries or executables 106 and 107. Original FFmpeg cache verified by
the same SHA-256 as the full 107; normal extraction, without changing sources.

The four CI checks of source 0849084 passed in `38493899926`.
main was then integrated by merge, keeping the identity of the built
source separate. PR 76 for CPU COLCLAMP was merged as
`4caab4e630b4089e60b884cc3ea782a074249506`, after local review, full build,
functional controls and four CI SUCCESS of the final documentation HEAD
`60aa5249ad345145a8283d01b197683fda816a0e`, run `38493430447`.

Extension of the limit of combined control 107: the **first** state 14
report already appears at 100.75 s, in addition to the last at 416.41 s. The
cause is not assigned without a capture of that transition. The full
interval must not be treated as sustained gameplay. The future control 108 may
deliver attacks with an explicit script, but delivering buttons by itself
does not prove acceptance by the game nor survival.

PR 77 for TEXA remains a draft. Menu 115, private reference
relinked with runtime 108, new scene against DX11/software at the same
boundary and combined configuration remain pending. The full build and its CI
do not by themselves establish visual fidelity or prolonged stability.

### 2026-10-14 — Menu 108 and relinked reference: procedural controls closed

The mandatory menu 108 finished in 115.294 s, controller 0 by limit.
The nine captures were reviewed: first one black during startup,
title/new game, difficulty, Kratos's introduction and the start of the ship
with the character visible. The 90.87 s report shows state 11.
Private card intact before/after/against the original, without the searched-for signatures
of exception/assertion/unknown opcode. There is no minimization
monitoring in this script, normal exit or proof of prolonged gameplay.
These images from another run are not used to compare ticks with 107.

A new private DLL was built with the same original nativeCore/Maximum API and
trace, but frontend/shadow and **full 108** runtime library
`116b54…6645`, without overwriting the 106 reference. Module SHA-256:
`1879c86e9c05189e8d8bc0d9e91c718bd17151a00d1a063def4fde3390d88488`.
The first control could not create the reference because it omitted the mandatory
trace folder; the records were kept and the helper's configuration was
fixed, without changing the renderer/DLL nor hiding a pixel
difference. The retry uses new folders.

The 48 full TEXA patterns pass on CPU, requested hardware and requested compute
of the full runtime 108, and 48/48 in the original DX11 reference.
The hardware mode of this fixture records 96 primitives and 12 tiles: it is a
mixed path, keeping the scope of the separate effective tests.
Three 64×64 FOG fields, six full halves, of the GPU shadow match
byte for byte in RGB with freshly initialized original software. Two fields
restored from Freeze and the same GIF/VSync match exactly
that fresh software reference. A record without End is rejected before
creating the device or output directory. The known FOG limit
of the second half of the original hardware is kept.

These checks validate the tool before using it with the game;
they are not yet the scene contrast 108. PR 77 stays a draft:
new scene with the same boundaries, combined control and CI of the final
documentation HEAD are missing before ready/merge.

### 2026-10-14 — Scene 108 with common boundaries and host separation

Synchronous shared control 108, compiled VU1, VU1/GS-front threads off
and private DLL 1879: finished in 464.471 s through its own STOP after
completing 16 acquired frames, 16 DX11 frames, 16 GPU shadow frames and End4015. Process 1,
controller 0; **it is not a full 600 s control nor a normal exit**.
Card intact, no recorded minimization nor searched-for failure signatures;
first state 11 at 55.17 s and last at 457.72 s. The 251 recorded
acquisitions show no regressions, inconsistent repetitions, A-B-A
returns or size changes; maximum distance between ticks 0. The 16 acquired
captures 512×448, 4000..4015, are distinct and correlate with the record.

Native burst with Freeze3999 and the same GIF/VSync until End4015:
113,538,293 bytes, 94,829 records, SHA-256
`995df20376de22b04678ed4156c55449b48fd8ece1e8d1a1677364c69df13b51`.
Original software restores that same input and produces 17 fields
3999..4015, code 0. The 16 triples of DX11 merge/restored
software/shadow108 and the full frames 4004/4015 were reviewed. HUD,
Kratos and enemies appear; the shadow 108 background is close to the original
references. At 4015, fixed background region x=200..339, y=0..79, mean RGB
shadow 35.6946/35.7850/31.2411 and software 35.7638/35.8478/31.3343.
The region includes mast/ropes and does not establish global equality.

Line, edge and pose differences persist. Over all of 4015, mean absolute
difference shadow−SW 3.8922/3.7271/3.2203 RGB; signed mean
−0.2818/−0.2830/−0.2386, absolute maximum 157 and 195,092 distinct pixels.
DX11−SW has absolute mean 0.6009/0.5978/0.5453. These are descriptive
statistics, with no accepted global tolerance nor state/VRAM equivalence.
The field history before the Freeze is not kept; the 16 later fields
are inspected without presenting that limitation as resolved.

The texture acquired by the host **is not identical to the shadow at any of
the 16 ticks**. At 4015, 118,710 RGB pixels differ, absolute mean
3.9683/3.5600/3.0705 against the shadow. The full quartet
DX11/SW/shadow/acquired was also reviewed. The acquired background remains close, but that tick
does not establish its same command boundary: the EE runs on another thread,
notifies VSync before waking callbacks and the host takes/enqueues Present
separately. This offers a possible explanation of the difference,
**without yet attributing it to order, slots, raster or presentation**.
The common shadow/DX11/SW comparison must not be turned into established
parity of the host's texture.

The TEXA expansion has external negatives/positives, full build and a bounded
visual control; the earlier separation and the image details remain open.
The combined control 108 with attack inputs is in progress. PR 77
remains a draft until its closure/review and CI of the final documentation HEAD.

### 2026-10-14 — Combined 108 with attacks: 420 s control closed

Shared control with asynchronous FINISH, VU1/GS-front on their own threads
actually enabled: 420.059 s, process 1 by limit/controller 0. Private
card intact, no recorded minimization nor searched-for failure signatures.
First state 11 at 35.06 s and last at 416.35 s; no state 14 appears in
the reports. The Start/X startup was kept and square presses were added
from 40 s, every 0.75 s for 0.35 s. The 128 recorded packet
changes include `ff7f`/neutral in state 11. The 16 late captures
11998..12032, distinct and correlated, show HUD and Kratos
performing attacks with the blade arcs. That establishes delivery and
visible action in that portion, without claiming to complete a section of the game.

The 4,096 recorded acquisitions have no sequence regressions,
inconsistent repetitions, A-B-A returns or size changes; images
512×448 and recorded field mode. Distance between ticks 0..4, without
turning it into milliseconds, latency or unique FPS. That figure is not compared
with combined 107 as a performance improvement: the scripts/scenes are
different. The startup is part of the 420 s; the observed stay
in state 11 spans reports 35.06..416.35. **There is no normal exit,
prolonged stability nor coverage of the whole game**.

Closed: full build, menu, external negatives/positives, procedural
reference and bounded functional controls of TEXA 108. The final code/scope
review is local, without external approval. PR 77 still requires
green CI of the final documentation HEAD before ready/merge. Still open:
the acquired/shadow difference, the details against the original software,
framing, unique presentation, HostWait breakdown and long stability.

### 2026-10-14 — TEXA merged; PCRTC composition 109 under validation

PR 77 was merged as `80f42145d2e9373d02c23685294de40236deed97`.
The four checks of the final HEAD `14a70b3` ended in SUCCESS,
run [38498133684](https://github.com/KIexster/god-of-war-recomp/actions/runs/38498133684).
The final review is local and bounded; the earlier full build, menu and controls 108
are closed within the scope described. The detail differences and those between
the acquired image and the shadow, framing and long stability persist.

The next probe uses independent uniform CT32 sources, pages 0/32,
64×64 progressive output and 32 EN/MMOD/SLBG/ALP/alpha combinations. CPU and
OpenGL 108 match the original software in 16/32 RGB results.
When only RC1 remains, both omit its blend with BGCOLOR; there are also
one-level errors in the blend arithmetic. The primary source
PCSX2 `2954ebe`, `GSDevice11::DoMerge` and `merge.fx`, keeps the blend of
RC1 even with RC2 off: MMOD selects ALP/255 or RC1 alpha×2/255.
This belongs to the output compositor, separate from the raster ALPHA.

Candidate 109 also blends RC1 with BGCOLOR and adds the products before
UNORM rounding to the nearest integer, on both CPU and GLSL.
The three private modes CPU/compute/hardware produce 31/32 exact RGB
against the original software. At ALP201, red is 232 versus 231; green 61
and blue 120 match. That difference is kept on record: the ideal
UNORM model gives 232 and the [D3D11 specification, section 17.5](https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm)
allows blending with precision equal to that of the output format. It is compatible
with a numeric limit of the reference, without demonstrating its particular cause
nor declaring exact 32/32 parity. The original hardware mirror differs from the
software in four patterns with framebuffer alpha and is not the sole
authority either. The new test uses 32 expected values from the model, with case 201 explained.

Negatives against the full LIB 108: CPU 0/2, exit 2, GPU 0/4, exit 4. Candidate
CPU 2/2 and GPU 4/4, exit 0, effective OpenGL verified without fallback. The normal
incremental suite ends 622/622, exit 0, 13.871 s. The first suite found
six failures in controls that intended to copy RGB with low alpha and MMOD 0;
seven copy/stride/latch fixtures now explicitly request MMOD 1/ALP 255,
keeping their expectations. The opaque-copy GPU control
also requires that configuration: modifying a black pixel to give it
color with alpha 0 leaves it black when blended with the background. The new matrix
covers the blend separately. No known failures are added. GPU suite,
mandatory full 109, menu and functional contrast of the executable pending.

Another probe of 450 rows with observed PCRTC 108 matches HW/SW 6/6 and differs
on CPU/OpenGL with both parities. The 17 records of the same burst 108 have
SMODE1=0 and SYNCV=0; the reference `isReallyInterlaced()` requires CMOD and
odd VFP, while the port duplicates rows based on SMODE2. The runtime's `GsSetCrt`
configures SMODE2 and does not yet model those timing
registers. The difference is not attributed to a wrong parity nor
is interlacing changed in 109: the effective configuration of the reference
and the appropriate port timing remain to be established. These probes do not
prove a single cause of the game's image, FPS or stability.

The later closure of the suites of candidate 109 records **622/622
normal** (13.523 s) and **666/666 GPU** (46.452 s), exit 0, no known failures
nor new failures. Incremental exe SHA-256
`17e8efbd9a101d171da0f5c55d3792c8e4424286de8528921d1db509e868f0cc`:
CPU/GLSL objects and tests 109, tests 107/108, full runtime LIB 108 and earlier
tests LIB. It does not yet establish the full build 109.
The first GPU run ended 664/666: its two failures were the copy control
mentioned; the explicit adjustment to opaque copy keeps all earlier
VRAM, source and field controls. The failed results are kept.

The new public probe reproduced the 32 RGBA of the original software from the
private probes, module SHA-256
`3ad27ad874ec7e8bcba35396bb2134f158156261d392965978cc43085587db55`, exit 0.
Valid config (four historical warnings, zero errors), syntax of 25 PowerShell
scripts, pad2 test and whitespace review green. Still pending:
full 109, menu and functional contrast of the new runner; the PR will remain a
draft until that validation and the CI of the final HEAD are closed.

### 2026-10-14 — Full 109 closed and title contrasted with the acquired image

The mandatory build through `scripts/2_compilar.cmd` finished with
code 0 in 1,050.312 s. Source `3fb71484935a1b6f373eb4f6fa62912250627915`,
109 patches, VU1 compiled, the 501 identified private micro-memories and
the 13 files `programa0..12` compiled and linked. Executable of
66,302,976 bytes, SHA-256
`6af0e4c12f4cf5d8061ed478b41ea48c28d93aa52a560456aa499e0cdd02c552`;
runtime LIB
`4b46443ce6d1f93e006d216b75ebcd554e93437aedc764042063b84e348f361d`.
Manifest and private results in `transition109_pcrtc_blend_vu1c_full`.
The four checks of that source finished in SUCCESS,
[run 38552301551](https://github.com/KIexster/god-of-war-recomp/actions/runs/38552301551).
This replaces the earlier pending build status, without yet establishing
the CI of the final documentation HEAD nor all the game's behavior.

The mandatory menu ended by limit in 115.314 s, PowerShell controller
0. Private card intact, nine 512×448 captures and no searched-for failure
signature. Difficulty, introduction and ship/Kratos appear in the samples;
first report 11 at 70.19 s and last at 90.19 s. Captures 1..3 showed
fire/face without options, and 0/7 were black. No cause is attributed
to those images. This script did not record the window state and its
closure by limit does not demonstrate normal exit nor prolonged stability.

To review the title, a separate control was run with only Start at 5 s,
but **the four references of that control receive the same run**:
original DX11 merge, OpenGL shadow bound to the full LIB 109, original software
restored from its Freeze/GIF/VSync and texture acquired by the host.
Duration 180.172 s by limit, process 1/controller 0, card intact,
window visible without recorded minimization and state 3 until 170.81 s.
The full quartets 900/904/908/912 and the acquired 900 were reviewed:
all show the title, "New Game" and "Select". The lack of options in
the captures of the menu script does not demonstrate a compositor regression.

The `GowPadTest` capture calls `copyLatchedHostPresentationFrame`: in shared
mode it downloads **current** VRAM with the latched CRTC request. It does not copy
the pixels of the texture acquired by the window. This limits its use as
evidence of what was presented, without by itself demonstrating the cause of the background
without options in the earlier samples. That path has not been modified.

Title burst Freeze899..End915, 41,187,493 bytes, 23,084 records,
SHA-256 `5a83dee1de5422f044dcca690167ab1b690985f005fbb5a40cd2f4bc0b94e88a`.
Restored original software: 17 fields 899..915, code 0, no initial
deinterlacing history serialized. The 16 acquired frames are distinct,
correlate exactly with their records, size 512×448 and SMODE2=1.
In 3,305 recorded acquisitions there are no sequence regressions,
inconsistent repetitions nor size changes; tick distance 0..1.
Those figures do not measure latency nor unique frames per second.

Acquired and shadow are still not identical at the same tick: the shared
run does not establish their same GIF boundary. There is also no global
shadow/software equality: at 915 the mean absolute RGB difference is
2.7159/1.5433/0.6734, with 194,045 distinct pixels; DX11/software gives
0.7117/0.5857/0.3457. These are descriptive statistics, with no global tolerance.
The full 109 capture module was first validated with TEXA48, FOG64, SW
restoration against a fresh reference and rejection of a truncated End before creating GS.
CPU and original references are kept; there is no global `glFinish` nor
removed fences. PR 80 stays a draft until closing the scene, combined run
with threads, final local review and CI of the final HEAD.

### 2026-10-14 — Scene 109: same prefix and separate comparison of the host

Synchronous shared control 109, compiled VU1 and both threads off:
433.235 s, own STOP after End4015 and the 16 HW/shadow/acquired frames.
Process 1/controller 0, card intact, window without recorded minimization
and no searched-for failure signature. First state 11 at 55.22 s and last at 426.94 s.
These are not a full 600 s, normal exit nor proof of prolonged stability.

Freeze3999..End4015: 113,832,837 bytes, 94,405 records, SHA-256
`c04ee2bd36a0a907942c8728ba6f79bbf0c75e9e7572ea793562affb1828190f`.
Original software restores that input and repeats 17 fields 3999..4015, code 0.
The initial deinterlacing history is not kept. The 16 full
triples of DX11 merge/software/shadow109 were reviewed in contact sheets, plus the
full quartets 4004/4015 with acquired. HUD, Kratos and enemies appear.
The background is close to the original references; line and pose differences
persist. PMODE constant 0x8023, SMODE2=0x21fed1 and sources 208,
without changing interlacing in 109.

At 4015, fixed region x200..339, y0..79: mean RGB shadow
35.4516/35.3573/30.6859 and software 35.2632/35.1795/30.5835. It includes mast
and ropes; it does not establish global equality. Over the whole field, mean
absolute difference shadow−SW 4.0995/3.9323/3.4149 RGB, signed mean
−0.2999/−0.2906/−0.2419, maximum 171 and 208,847 distinct pixels.
DX11−SW has absolute mean 0.6197/0.6157/0.5630. There is no accepted global
tolerance nor causal comparison with another pass because they share the tick.

The 16 acquired frames 4000..4015, 512×448, are distinct and correlate
exactly with their records. In 90 recorded acquisitions there are no
regressions, inconsistent repetitions, A-B-A returns nor size changes;
tick distance 0. None of the 16 acquired frames is identical to the
shadow of the same tick. At 4015 there are 216,932 distinct pixels and absolute mean
11.8596/11.3732/9.6050 RGB. **The host's GIF boundary is still not established**:
that disagreement does not by itself demonstrate a rasterization or slot failure.
These passes with mirror and readbacks do not measure unique FPS.

The scene closes a bounded functional contrast of executable 109. The combined
mode with attack inputs is still in validation; PR 80 remains a
draft until its closure, final review and CI of the final documentation HEAD.

### 2026-10-14 — Combined 109 with attacks closed and local review

Shared presentation, asynchronous FINISH and VU1/GS-front on their own threads,
confirmed in the startup log: 420.056 s by limit, process 1 and
controller 0. Private card intact, no recorded minimization nor searched-for
failure signatures. First state 11 report at 35.09 s and last at 416.33 s;
no state 14 appears in the reports. The startup is part of the 420 s,
so these are not 420 s of full gameplay nor prolonged stability.

Start/X script and square from 40 s every 0.75 s for 0.35 s. The 128 recorded packet
changes include attack/neutral in state 11; its quota limits
the reads kept. The 16 late acquired frames 11999..12040 were reviewed
in contact sheets and the first/last full ones: HUD and Kratos performing attacks
with the blade arcs. They are 16 distinct RGBA, 512×448, SMODE2=0x21fed1,
exactly correlated with the record. Completing a game
section is not claimed, nor equivalence against another run because they share a tick.

The 4,096 recorded acquisitions show no regressions, inconsistent
repetitions, A-B-A returns nor size changes. Distance between ticks
0..4, without turning it into time, latency or unique FPS. The logger omits
iterations that reuse the same sequence; zero repeated rows does not
rule out reuse by the host. The process was stopped on reaching the
limit: **normal shutdown is not yet established**.

Closed: the mandatory full 109, menu, negatives/positives,
procedural reference, title/scene at common boundaries and this bounded
combined control. The final source and scope review is local, without
external approval: factor 0..255, weighted sum bounded before dividing by 255,
alpha preserved during blending and normalized afterwards. The copy
tests request explicit opacity and keep their expectations; no
known failures are added. CPU/DX11/SW references and fences preserved.
PR 80 needs the CI of the final documentation HEAD before ready/merge.
Still open: acquired GIF boundary, lines/pose, timing,
framing, HostWait breakdown, distinct frames and prolonged stability.

### 2026-10-14 — PCRTC 109 merged and timing control without captures

PR 80 merged as `ca6bace6eec3f33432229d357d8f6b2bbffe38ae` after
the four SUCCESS of the final HEAD `286267264027b181997e1438a7fd48874d8996ea`,
[run 38559090776](https://github.com/KIexster/god-of-war-recomp/actions/runs/38559090776).
The source and evidence review is local, without external approval.

Another control uses the same identified runner 109, shared presentation,
asynchronous FINISH and both threads, but without mirror, hash, readback nor acquisition
diagnostics. `GOW_PERF_DIAG=1`, Start/X script and attacks, copied card.
It ends by limit at 600.164 s, process/controller 0. The controller sends
WM_CLOSE only to the window of the child PID: the process exits with code 0
in 0.147 s, without resorting to forced termination. **Requested closure
of that window** is established, not the end of the game nor a spontaneous exit. Card intact,
no recorded minimization nor searched-for signatures; state 11 in the reports
35.06..596.22 s. The foreground changes during the control; it was not constant.

119 timing reports; 111 have state 11 observed in two consecutive
reports, without demonstrating a continuous state between samples. In them,
Flip 25.32..49.07/s and host 9.11..60/s. Ten windows t50.17..95.67 record
host 9.11..19.64/s and Flip 25.32..41.68/s; one hundred later ones t100.69..595.73
record host 55.66..60/s and Flip 41..46.6/s. **These are operation counters,
not unique frames displayed**. There are no captures of this pass to align
its camera/scene with another control nor to declare a performance improvement.

HostWait has a median of 4,979.41 ms in windows of about 5 s, while Upload
has a median of 5.20 ms. The code measures HostWait around the whole
`EndDrawing`: GL batch, swap, limiter and events. That scope also dominates the
60/s host windows; it does not by itself prove GPU wait, fences or swap.
The EE/VU/GS/IOP scopes span distinct threads and are not summed as global
exclusive time or CPU percentage. The components of
EndDrawing remain to be separated and new/reused submissions counted without
hash/readback. This ten-minute control does not establish prolonged stability nor the whole game.

### 2026-10-14 — Aspect-ratio reference and limits of the original processing

New private wrapper with the original `SaveSnapshotToMemory` and mode query:
build 0, 16 aspect/window patterns and three correct rejections.
It repeats the same Freeze/GIF/VSync of scene 109: the 17 raw SW fields
are identical to the earlier SW module. At 4015, Stretch 512×448 keeps exact
RGB; Auto/4:3 produce 597×448 and 16:9 produces 796×448. The full
Stretch and Auto with a 640×448 window were reviewed. This separates texture
aspect from the presentation configuration of the original calculator, without
yet establishing the physical PS2 framing nor changing the port's camera.

The original's effective configuration at that input is VESA, Automatic,
PCRTCAntiBlur enabled and `isReallyInterlaced=false`: SMODE1=0, SYNCV=0,
SMODE2=0x21fed1. Another synthetic matrix uses four CMOD/VFP conditions and
four INT/FFMD, six fields per fresh instance. Its 96 HW/SW fields are
identical RGB. CPU/SW have equal size 84/96 and exact RGB 0/96; the two
GPU modes have equal size 60/96 and exact RGB 0/96. The dimensions change
according to configuration; a 512×448 equality is not imposed on all cases.
With CMOD 2 NTSC is recognized; only CMOD 2+VFP 1 activates reallyInterlaced.
The INT 1/FFMD 0 differences persist with those synthetic registers.

PCRTCAntiBlur ON/OFF was also contrasted in independent SW instances
of the same row pattern. ON keeps its original colors; OFF blends
adjacent rows. GPU blends and duplicates row pairs. In the observed control,
the five original merges before deinterlacing are RGB-identical to
GetCurrent afterwards; both differ from the shadow. In field 6, absolute mean
GPU−ON 2.6161/6.7411/10.2009 RGB and GPU−OFF 2.9174/6.5938/10.0112. They are not
scene tolerances nor proof of a single cause. The first trace request
starting at 1 was rejected by its limit start>=2; corrected to Freeze 1,
merge 2..6/End 6, it ended 0. That rejection was not a failure of the game's renderer.
Bob, parity, timing or fences are not modified to match the oracle.

### 2026-10-14 — Snapshot and effective mode as an optional extension of the module

The isolated module now offers `gow_gs_read_video_info` and
`gow_gs_read_snapshot`. It keeps ABI 1 and the earlier structs/calls; an old DLL
may lack the new exports. Snapshot calls the original calculator
with Stretch/Auto/4:3/16:9, restores the aspect configuration and
keeps the raw output. Query and read use the same capture; VSync,
reset and close invalidate the cache. It does not change the game's renderer nor require
another build of its generated files: it is an isolated tool.

Local build over the pinned original Core: 0; contracts without a device and
two-cycle GPU control: 0. Proportions, bands, insufficient buffers,
canaries, owner thread, output preservation and reset with repeated
sequence verified. When omitting only VSync/reset invalidation, exactly the
stale-cache-after-reset control fails, code 1; intact positive 0.
The public probe `probe_snapshot_reference.py` obtains 16/16 RGBA identical
to the private SW aspect/window reference. Old DLL: explicit error
of missing function before creating GS. Private results/binaries, no assets
published. CI of the final HEAD and final review of this extension are missing before
merging; it is not presented as an already validated fix of the game's framing.

### 2026-10-14 — Reference merged; public profile options and closure

PR 81 merged as `ec7cd43882d8f58c1208ad5828b1e744bc674a8c` after
the four SUCCESS of HEAD `e71ad9c32ac5634ee1062b98247488e3368944ba`,
[run 38562439264](https://github.com/KIexster/god-of-war-recomp/actions/runs/38562439264).
Isolated build, contracts, GPU, cache negative and earlier probe
close that reference extension; local review, without external approval.

The launcher `run_transition_control.py` now exposes `--gpu-profile`,
`--gpu-stats` and `--request-window-close`, recorded in measurement/result.
The first two enable already-existing flags; they add no timers to the
runtime. The third sends WM_CLOSE only to a visible window of the PID of the
child created by Popen, without activating windows. If there is no window, the
send fails or the child does not terminate in 15 s, it records the fallback and uses the handle of
that same child to stop it. An already-closed child keeps its code and does not
query windows. The earlier defaults are kept.

26 own Windows tests and 91 full Python tests pass 0: they include selection
of the own HWND, exclusion of foreign windows, preservation of error 17,
timeout/no window, sanitizing of inherited flags and metadata. Real control of
75.323 s with the three options, runner 109 without rebuilding: process/controller 0,
WM_CLOSE 0 in 0.303 s without fallback, card intact, no minimization nor searched-for
signatures. State 11 at 35.08..70.23; there are no images of that pass nor proof of
prolonged stability or displayed FPS. CI of the launcher's final HEAD is missing.

### 2026-10-14 — GPU 109 timestamps: raster and denominator checked

Earlier private control of 240.172 s, same executable 109, without mirror/hash/
readbacks, with CPU and GPU profile and attack inputs: process/controller 0,
requested window closure 0 in 0.159 s without forcing. Card intact, no
recorded minimization nor searched-for signatures; state 11 at 35.09..235.62.
39 CPU windows have state 11 observed in consecutive reports, with
Flip 27.44..46.97/s and host 10.72..60/s. Do not compare its speed with another
run because the script or tick coincide; there is no aligned visual reference.

The GPU profile generates 2,613 windows: 2,612 of four attempts and one at close.
There are eight warnings of omitted samples. In 2,083 windows of four without those
warnings, without an interleaved timing line and with last observed state 11,
raster records 12.93..103.88 ms, median 19.56; present 0.02..0.24 ms, median 0.02.
CLUT has a median of 0.03 ms. These are times of the scopes instrumented by
timestamps, not covering the whole GPU nor representing utilization or CPU time.

The denominator was checked in the source: `profFrame/endFrame` is called after
the Present DispatchCompute and **before** PublishShared. It does not count Flip,
VSync, acquisitions or EndDrawing; the windows may contain work
accumulated between attempts. Closing may collect pending queries with
fewer attempts. The GPU and CPU windows lack a recorded common time
boundary: raster stands out among the measured scopes, but the whole
EndDrawing wait is not yet attributed to it nor are physical FPS derived.
The results support continuing with the breakdown of GL batch/swap/limiter/
events and with counters of submitted/reused sequences. Fences, synchronization,
bob, parity or raster are not modified to hide the difference.

### 2026-10-14 — Candidate 110: inclusive EndDrawing detail and actual submissions

New patch `ps2recomp-gs-host-timing.patch`, at the end of the chain 110.
With `GOW_PERF_DIAG=1`, raylib calls callbacks around the first GL batch,
swap, conditional `WaitTime` and events. CMake checks the fingerprint of the
raylib 5.5 source and builds an instrumented `rcore.c` in its binary directory;
it does not write to the FetchContent source. The private copy 110 and the
shared source 106..109 keep their original SHA. The calls, conditions and
order of EndDrawing remain; manual frame control is not used.

`[gow-perf:host]` shares t/window with `[gow-perf]`. It reports end/batch/swap/
limiter/events/other_ms and calls. **HostWait keeps its inclusive
meaning**; the four phases are mutually exclusive and are included in
EndDrawing/HostWait, they are not summed again as global time nor CPU%.
`other_ms` keeps what is unattributed. Without the diagnostic the callback is null;
it is removed when the consumer is closed. `GOW_PERF_DIAG=frames` does not enable phases.

It counts the View returned after EndDrawing: shared_texture/blank/fallback and RAM
are disjoint categories; ram_blank is a subset of RAM. shared_changed/
reused count first/changed or same sequence in effective Acquire,
also if blank. Mode change/reset separates epochs. An absence of
Acquire does not use old metadata as proof of reuse. **A changed
sequence does not establish distinct RGB nor scanout**, and no hash/readback is added.

New build of suite 0/127.219 s; normal 626/626 and GPU 671/671 both OFF
and ON, codes 0. First normal 625/626 was launched from the binary directory:
the VU0 mappings test did not find its relative header. Only the
launcher directory was fixed; the failed attempt is kept and no known
failures are added. Chain 110 reapplied from the pin, ten files of the topic equal.

Isolated control 5/5 positive; raylib 109 without callbacks fails only the
real-hooks case, 4/5/code 1. Real consumer 4/4 positive; omitting only the
View registration fails the three scales, 1/4/code 3. Images, fences and
CPU/DX11 references are kept. Local review, without external approval.
**Full 110, menu 115, functional control and game measurement remain pending**;
there is still no timing result for 110 nor a declared performance improvement.

### 2026-10-14 — Full 110 and functional control of the diagnostic

`scripts/2_compilar.cmd` finished 0 in 1,079.539 s: 110 patches, VU1 compiled,
private copy of 501 micro-memories and 13 programs 0..12 compiled and linked. Source
`7d3461c2d42694bbc12dceb437e6a1812c55269a`; executable 66,307,584 bytes,
SHA256 `533c9cd7e841b7343c34e6cc3ff86ae5615a35969efcd5cec8a4bef6705852cc`.
Private manifest `transition110_host_timing_vu1c_full/build.json`.
Libraries 106..109 and the shared raylib source intact after the full build;
the instrumented copy of rcore is identical between successive configurations.

Mandatory menu 115: 115.348 s/control 0/copied card intact, nine 512×448
captures reviewed. Difficulty 4, introduction 5..6 and ship 8; 0 and 7 black and 1..3
background without options. They are GowPadTest reads of current VRAM/latched CRTC,
not the acquired texture: no title regression is declared from those captures.
No searched-for failure signatures nor reports of the new profile with diagnostic OFF.
The script's stop by limit does not establish normal closure of the game.

Another combined control lasts 240.186 s: asynchronous FINISH configured, VU1 and
GS-front on their own threads confirmed in the log, shared presentation,
Start/X and square inputs. State 11 in reports 35.05..235.65; no state 14.
Process/controller 0; WM_CLOSE of its own window ends 0 in 0.168 s,
without fallback. Card intact, no recorded minimization nor searched-for signatures.
There is no line that counts each FINISH; the configuration of
that option is distinguished from the explicit confirmation of the threads.

The 16 acquired frames 3999..4031 are distinct RGBA 512×448, SMODE2=0x21fed1,
exactly correlated with their record. Contact sheet and first/last
full ones reviewed: HUD, Kratos, enemies and pose variation; attack
arcs and completing a section are not claimed. The 4,096 recorded
acquisitions show no regressions, inconsistent repetitions, A-B-A
returns nor size changes. Tick distance 0..9, not translated to latency.
The old logger omits reuses; the new counter does record them.
This pass with hashes/captures is not used as a benchmark nor as a visual
reference for another game because their ticks coincide.

### 2026-10-14 — Swap wait, limiter and reuse measured without captures

Separate control with the same identified runner 110, both threads,
asynchronous FINISH configured, without mirror, hashes, captures, acquisition
diagnostics nor GPU profile. It lasts 600.150 s, process/controller 0. WM_CLOSE
requested only to child 11444: exit 0 in 0.141 s without forcing. Card intact,
no recorded minimization nor searched-for failure signatures. The foreground
changes; it was not constant. State 11 in reports 35.07..596.32, no 14 observed.
These are not 600 s of full gameplay nor proof of prolonged/final stability of the game.

119 pairs of CPU/detail reports with equal t/window, zero contract
errors. Each EndDrawing/submission has one batch/swap/events call;
WaitTime only counts if executed. The phases plus residual sum to end_ms
within printf rounding; that total remains included in HostWait.

111 windows have state 11 observed in consecutive reports, without proving
a continuous state between samples. Host 8.51..60/s and Flip 18.93..47.60/s.
In 21 windows with host<20, located at 45.16..100.73 and 341.01..381.75,
swap records 4,553.40..5,047.23 ms, median 4,917.07; limiter median 109.31 ms.
In 87 windows with host≥50, swap 12.21..1,938.29 ms, median 154.53;
limiter 3,045.12..4,967.29 ms, median 4,819.00. The windows are about 5 s.
The profile locates the wait inside swap in the slow group and in the limiter
in the fast one; it does not by itself demonstrate a fence, GPU work or driver
policy as the cause. Batch measures the first batch inside EndDrawing, not all
the drawing nor the batches the overlay may have sent earlier.

In the 111 windows: 27,519 texture submissions, 19,432 sequence changes and 8,087
reuses, with no blank/fallback/RAM in that subset. They do not represent
27,519 distinct RGB nor physical scanouts. Median HostWait 4,980.18 ms keeps
its earlier scope; the phases are not summed again into it nor into the scopes
of other threads as CPU%. There is no aligned visual reference in this pass.

The CI of source HEAD 7d3461c ended with four SUCCESS,
[run 38603697064](https://github.com/KIexster/god-of-war-recomp/actions/runs/38603697064).
Source/evidence review local, without external approval. CPU/DX11/SW, fences
and the renderer are kept; **no FPS improvement is declared**.
CI of the final documentation HEAD is missing before taking PR 83 out of draft/merging.
Still pending: identify the common command prefix acquired/mirror,
remaining haze, lines/pose, framing and prolonged stability.

### 2026-10-14 — PR 83 merged and boundary of the reference module

PR 83 merged by merge at `96b164f143dc62917779d42fbdac32c4a2bfa11c`.
The final HEAD `d0afe0b6062bc5fb240a5efc4038846b572eb6ba` finished the four
jobs with SUCCESS,
[run 38609264065](https://github.com/KIexster/god-of-war-recomp/actions/runs/38609264065).
The earlier validation of 110 is closed within its scope; haze,
framing, cause of the swap wait and prolonged stability remain pending.

The source audit detects two limits for comparing acquired/mirror:
the CRTC request is built under stateMutex but Present is enqueued after
releasing it, and the observer receives the full GIF span before its
processing in the frontend finishes. The publication sequence does not establish a
common original prefix. The CRTC bank also has host readers and MMIO/syscalls/DispEnv
writes without a visible common exclusion. A concrete native
overlap is not demonstrated here, nor that this risk causes the haze; making each
field atomic would not establish a multi-register transaction either. Locks,
fences, synchronization, the observers' C++ ABI nor the game's renderer are not changed.
As a bounded step, the isolated module adds `gow_gs_read_stream_info`, an
optional ABI1 export with a struct64, without changing the earlier contracts. It counts
accepted calls and the GIF bytes accepted by the transport; it keeps both cursors of the last
VSync, its field and sequence; a reset separates epochs even if the sequence repeats.
Queries/rejections do not advance cursors. The alignment refers only to the
16-byte transport: a tag may still be pending. A GetCurrent being available does not
prove a new composition, and later input is not attributed to the last VSync.
They are not fingerprints nor a certificate of alignment with the host image.

Isolated build and device-less contracts: 0. GPU control with two cycles: 0,
exactly 2,048 RGBA pixels per cycle. It checks prefixes before/after VSync,
fragments across VSync, a tag with a pending payload but QWORD aligned,
empty submit, repeated queries, rejections/owner thread and pending reset.
Omitting only the VSync byte record produces three boundary failures, code 1;
not advancing the epoch produces only the reset-separation failure, code 1.
Positive intact 0; 16/16 RGBA snapshots equal to the previous module. Previous DLL,
original Core, runtime and runner 110 preserved. The game does not need to be
recompiled: no patch/runtime/override was modified. Final review/CI of
this extension is still missing before merging it. The next step is to correlate these
cursors with complete host FIFO events and the composed image,
without equating captures by tick alone or draining the shared path.

### 2026-10-14 — Reference boundary merged and probe with provenance

PR84 merged at `9aa3423fb1a3e23670bbb78344bd7626ce2180c8`, local review
without external approval and four SUCCESS on HEAD `0d34424765ac95b278ca16aeab48bf25ae6c4614`,
[run38612566788](https://github.com/KIexster/god-of-war-recomp/actions/runs/38612566788).
The snapshot probe now adds `--stream-info`: it saves the cursors before
the pattern, after submit, after VSync and after the captures. It only resolves the export
if requested; errors propagate and the created handle is closed in a finally.

96 full Python tests: 0, including layout64, counters/handles above
32 bits, ctypes ABI, DLL without export and query error. Real GPU controls:
new DLL with option 0/0.809 s; old one without option 0/0.818 s; old one with option 1/
0.085 s, explicit error before creating the GS. The 16 snapshots are equal RGBA on
both DLLs; cursors 0→1→2, 192 bytes accepted, no advance from the captures. No
runtime/patch/override changes or game recompilation. Final CI is still missing
before merging the probe option.

An additional private control linked to the real frontend and GSThreadedBackend
reproduces the interleaving with explicit barriers, without sleeps or running the
game. The host finishes its snapshot, another thread enters the observer with an
80-byte span and stops before the parser. Present is queued and executed with zero
Submits; when the parser is released, one Submit is processed. Repeated with compact 1 and 0,
codes 0/0.069 s and 0/0.079 s. The observer and final backend of that control are
test ones: it shows the possible ordering of the implementation, not its frequency in
the game, visual divergence or the cause of the haze. The future regression must
mark that Present as an open event/different prefix; counting received spans
is not enough. Present is not moved under stateMutex and the shared path is not drained.

### 2026-10-14 — ResetGraph: ALPHA corruption reproduced and candidate 111

The snapshot-provenance PR85 was merged at
`4709806ad0594a507f9e311368f420442d55c03c`, after local review and
four SUCCESS on HEAD `ae43949304f8d2dd72b3496fdb85f4c2f14e87e9`,
[run38613982328](https://github.com/KIexster/god-of-war-recomp/actions/runs/38613982328).

A private probe of the real stub 110, with runtime RAM and without running the
game, calls `sceGsResetGraph(mode0,interlace1,omode2,ffmode1)`: it returns 0 and
emits one DMA; PMODE stays 0 and SMODE2 keeps the sentinel 0x12345678. At the same time,
ALPHA_1 changes from 0x8000000064 to 3. The cause in the source is the A+D packet
that tries to configure the CRTC using 0x41/0x42: 0x42 corresponds to ALPHA_1. The haze
observed in the game is not yet attributed to this failure.

The separate candidate 111 `ps2recomp-gs-reset-crtc.patch` changes only that mode 0
path to an update of the privileged bank of PMODE, SMODE2, both
DISPFB/DISPLAY and BGCOLOR under the frontend mutex, shared with its snapshot. It keeps the calculated values, including CRTMD bit 2 of
PMODE. It does not inject GIF commands nor touch ALPHA; it does not invent SMODE1/SYNCV nor decide
the effective mode from empty registers. The complete mode selection
is still pending: bob/parity is not modified to match the oracle.

New regression in ps2xTest: four INT/FFMD combinations, CRTC registers,
ALPHA_1/2 preservation and absence of drawing DMA. Against library 110
it fails 0/1, code 1, with four checks per combination; against 111 it passes
1/1, code 0. The first MMIO variant passes 627/627 normal and 672/672 GPU OFF/ON,
codes 0, but it is kept as historical: before full, that path was adjusted
to keep the snapshot lock and its final sources are validated again.
Initial fresh suite build 0/121.297 s. When reviewing the expected
PMODE, 0x8001 was corrected to 0x8005 because of CRTMD bit 2 and it was rebuilt before running
the regression. **Full suites, full 13/501, menu, functional control and final CI
are still pending**: there is no validated runner 111 nor a declared visual improvement.
The runtime 110, cards, CPU/DX11/SW and earlier diagnostics are preserved.

The final sources under stateMutex pass 627/627 normal 0/11.858 s and 672/672
GPU both OFF 0/38.039 s and ON 0/37.706 s. Final suite SHA
`b82957d494261cb28a6902c0ca1acd019f6cd3089f8c3371253bd96566e2ff67`.
Chain 111 is reapplied from the pin and its four files match the
candidate. Configuration/handlers 0 and 25 PS1 scripts without errors. The full game run
starts after freezing the source commit; these tests do not replace it yet.

### 2026-10-14/15 — Complete runner 111 and bounded ResetGraph validation

The full build `scripts/2_compilar.cmd` of source
`8c5cefe2dfb297187970da037463731fd54d33de` finished with code 0 in 1,067.821 s:
111 patches, VU1 compiled, 13 program units 0..12 linked and 501 private
micro-memories. The final manifest is at
`E:/gowgpuprof/transition111_reset_graph_vu1c_full/build.json` and replaces the
historical activity notes. EXE SHA-256
`63c3bae7f275e8638a83618f2f8864f4230436f65f2153ff54c3414fb42b62e6`,
66,307,584 bytes; library
`b94efacbfa991f246a47443c31d69a7dd4413abd065b34c61153636c489e015b`.
Both identities were verified after finishing. The previous
runtimes, CPU/DX11/SW, source cards and micro-memories were preserved.

The final sources under `stateMutex` pass 627/627 normal tests and 672/672
with GPU, both with `GOW_PERF_DIAG` disabled and enabled, all with code 0.
The new case includes four INT/FFMD combinations. The regression against 110
fails 0/1, code 1; the case passes on the final sources within 627/627.
The previous MMIO variant also passed 1/1 in isolation, without replacing the final suite
under mutex. Chain 111 from the pin, configuration, handlers and PowerShell syntax
correct. CI of source 8c: four SUCCESS,
[run38616693562](https://github.com/KIexster/god-of-war-recomp/actions/runs/38616693562).

Mandatory menu `scripts/probar_menu.ps1 -Segundos 115`: script code 0,
115.375 s and nine 512×448 captures. Review of the contact sheet and full capture:
face/fire, Hero difficulty, scene with Kratos and ship with character. Samples
0 and 7 are black at start/transition; the log reaches state 11
without errors of the reviewed pattern. Private card and source keep SHA-256
`47ebe237a3987f843fc19b0f801ce1edc1690768ef6b18e4b03a12ca6b298358`.
The script stops at the limit: its code 0 does not prove a normal exit. These
captures are GowPadTest (current VRAM/latched CRTC), not an acquired texture.

Private combined control `visual_reset111_a`: 240.170 s, code 0, VU1 and GS
front on threads, asynchronous FINISH and shared presentation enabled. State 11
sampled between 35.06 and 236.73 s, real reads of the pad script and intact card.
No minimization recorded; the foreground varied. The 16 acquired
512×448 captures are distinct RGBA and correlate with the host log:
ticks 3999..4030 and SMODE2=0x21fed1. The full contact sheet and the
last frame were reviewed: HUD, Kratos, enemies, pose changes and attack effect
on the ship. There is no aligned DX11 reference in this pass.

The 4,096-record inspector with quota finds no sequence regression
nor inconsistent repetition; it does not certify unlogged iterations nor the
global absence of reuse. No errors of the reviewed pattern. WM_CLOSE
to the HWND of the child PID closes with code 0 in 0.163 s, without forced termination.
The 240 s limit is still the controller's reason, not the end of the game.
The pass contains hash, readback and profile: it is not a benchmark.
Private artifacts in `transition111_reset_graph_vu1c_full/runs/`:
`menu115_reset111` and `visual_reset111_a`, with results, logs and captures.

Scope contrasted with the commercial ELF: the original ResetGraph also
orders CSR.RESET/FLUSH and has mode paths that the stub still approximates.
This PR only fixes the CRTC programming of mode 0 that emitted an improper
ALPHA_1 write through GIF. Keeping ALPHA in its test characterizes that bounded
operation, not the hardware state after RESET. It does not validate the complete ResetGraph,
all the CRTC/MMIO writes nor the commercial GParam ABI.
Bob/parity/SMODE1/SYNCV are not modified to force a visual reference.

Still pending are the command boundary between acquired and original mirror,
the remaining haze, the PS2 framing and prolonged stability. These
controls do not measure physical frames nor unique FPS, nor prove end of level.
Other runs were not compared by tick equality.

Local review of code, regression, original scope and functional evidence
completed, without external approval. The merge requires CI of the final
documentation HEAD; there were no source changes after the full.

## Intermittent stall after the menu load: re-reading and `GOW_STALL_DIAG` diagnostic (2026-10-14)

**Re-reading of the blocked attempt of runner 105** (private logs
`profile_fog105_review_20261013` and its repetition `_repeat_`, same
configuration except the card path; line-by-line comparison without the
shader caches). Observed facts:

- It was not a boot stall: both logs are identical up to t≈20 s.
  The eight initial IRXs were loaded, 989snd answered 113 commands and the
  game was in state 3 at ~47 `vid::Flip` entries per second.
- The divergence appears after the script's X press at t=20 s. In the correct
  run, `[gow-fmv] skipped Semo01` arrives at t≈22 s, then state 4
  (`levelReady=1`) and state 11 at t≈35 s. In the blocked one that line does not appear,
  the game stops reading the pad and emitting `[gow-pad2:state]`, and
  `guest_flip_hz`, `vu_ms` and `gs_ms` drop to zero from the window t=25..30 s.
- During the remaining ~90 s, each 5 s window splits the EE thread into
  `ee_ms≈3360` and `iop_ms≈1640` (sum ≈5000 ms), with `guest_wait_ms=0`. The
  host kept refreshing at 60 Hz.

Inference: the EE is not blocked in a kernel wait (there is no `GuestWait` time),
but running game code while the IOP advances in slices; it is
compatible with polling that waits for something that does not arrive before the
call to the video load (0x188CA0). Hypothesis not yet verified: an asynchronous
request to the IOP (load or stream) that does not complete. The pair does not
prove a relation with `ResetGraph`, the profile or the script.

**New diagnostic** (`patches/ps2recomp-stall-diag.patch` and
`src/gow_overrides.cpp`), enabled with `GOW_STALL_DIAG=1`, label
`[gow-stall]`, `steady_clock` times common to all threads:

- `hito` (milestone): first time of `ee_run`, `sif_init_rpc`, each `sif_bind_rpc` (by
  SID), first `sif_call_rpc`, first `sif_dma`, each `irx`/`irx_buffer`
  (id and boot result), first VIF1 data, `primer_flip`,
  `fmv_saltado` and each new game state observed in `vid::Flip`
  (`estado_juego`) or by the watchdog (`estado_juego_vigia`). Maximum 512 milestones.
- `latido` (heartbeat) every 5 s from its own watchdog thread: increments of flips, VBlank,
  alarms, RPC calls and binds, SIF DMA, IOP slices, VIF1
  blocks, semaphore signals/waits/polls and EE wakeups, the PC/RA of the last
  EE dispatch and the game state words.
- `volcado` (dump) when there are no flips for 3 s after the first (at 3, 10, 30
  s and then every 60 s, maximum 8): EE threads with state, reason and wait id;
  semaphores and flags with waits; PC/RA histogram of dispatch sampled
  over 200 ms; the last 12 SIF RPC operations with their time; and IOP threads,
  semaphores and flags. The IOP is described in the EE thread, in the next
  IOP slice, at the watchdog's request: no IOP structures are read from another
  thread.

Limits: the PC is that of the last dispatch (function entry or loop header),
not the exact instruction; an inner loop without dispatches appears as
its function. The watchdog does not change waits, deadlines nor the scheduler order;
without the variable, the counters are not touched (regression in `ps2xTest`).

Controls with the game (local full build of 114 patches, VU1
compiled with 501 micro-memories, exe SHA-256 `3e375c2d…f301`, 66,339,328 B),
same configuration as the blocked attempt (VU1 thread, GS frontend, asynchronous
FINISH, direct presentation, `GOW_SKIP_FMV=1`, same script, intact card
copied per attempt) plus `GOW_STALL_DIAG=1`:

- First attempt discarded as a comparison: empty shader cache; the GPU
  backend compiled during the game (`gs_ms≈ee_ms≈6 s` per 5 s window,
  `host_hz<1`). The watchdog dumped at 3 s with no flips and then recorded the
  resumption; the request to the IOP expired because the EE thread was inside the
  GS. It serves as proof that the dump fires and recovers.
- Eleven attempts with a warm cache (one of 120 s and ten of 60 s), all correct:
  state 4 at 22.03..22.16 s, `fmv_saltado` at 23.77..23.93 s and
  state 11 at 35.36..35.68 s; ~47 entries to `vid::Flip`/s in state 3, same
  as the original log. Closed by `WM_CLOSE`, code 0, intact card.
- **The stall was not reproduced** (0 of 11). There is no correct/blocked comparison
  with the diagnostic; the cause is still unidentified.

Next step: leave `GOW_STALL_DIAG=1` on in the usual long controls.
If the stall reappears, the dump will say which EE thread runs or waits, the
dispatch PC, the last RPC and the state of the IOP threads.

## SPU2: `GOW_SPU2_PERF` profile and measured cost on the ship (2026-10-15)

`patches/ps2recomp-spu2-perf.patch` (only `spu2.cpp` and its test):

- `GOW_SPU2_PERF=1`: one `[gow-spu2-perf]` line every 5 s with the elapsed
  time of `advanceTo` (samples), the active voices per sample, the
  ADPCM blocks, DMA (ms and KB), the audio thread drain (ms, mutex wait,
  frames requested, delivered and missing) and the discards.
- `GOW_SPU2_PERF=2`: adds the TSC cycles per section (envelope,
  decoding, pitch/interpolation/mixing, output and wait on its mutex),
  calibrated with the `advanceTo` time of the same window. It has its own
  per-voice overhead: it serves to split, not to measure the total.
- Regression `multi-voice mix keeps its reference output hash`: 12 voices on two
  cores with pitches, ADSR, loops and mid-way KON/KOFF. The FNV-1a hash
  `0xa97415b49fd7d37c` matches the non-instrumented `spu2.cpp`. It pins the
  observable output for future optimizations.

Measurement (local exe of 115 patches, SHA-256 `1b8d2112…07a5`, VU1 compiled,
same configuration and script as the stall controls, 150 s per round, 20 s
pause, machine without builds or other games; rounds 0/1/0/1/2/2).
5 s windows with t=50..145 s, all in state 11 (ship with script
attacks); medians [min..max], 19-20 windows per round:

| Round | `step_ms` | % of the window | µs/sample | samples/s | active voices |
|---|---|---|---|---|---|
| 2 (level 1) | 146.7 [77.0..176.9] | 2.93 [1.54..3.54] | 0.83 | 34,696 | 37.4 |
| 4 (level 1) | 150.6 [77.7..174.6] | 3.01 [1.55..3.49] | 0.87 | 34,698 | 38.9 |
| 5 (level 2) | 166.3 [108.2..187.4] | 3.33 | 1.21 | 26,528 | 39.5 |
| 6 (level 2) | 169.5 [103.1..185.0] | 3.39 | 1.30 | 26,189 | 42.0 |

- Fact: with level 1, the SPU2 takes ≈3 % of the elapsed time of the EE thread
  (which also runs the IOP). DMA ≈0.37 ms and drain ≈0.17 ms per window.
  There are no discards due to latency or buffer.
- Fact (level 2, rounds 5 and 6): of the voice time, the envelope ≈39 %, the
  pitch/interpolation/mixing ≈54 % and the ADPCM decoding ≈7 %. The output
  (master mix and tail) 4.1-4.3 ms per window, with 2.3 ms of mutex wait.
- Fact: only ~34,700 samples/s of 48,000 are produced (level 1). The SPU2
  clock follows the IOP cycles, which follow the EE, and the latter runs below
  real time. The audio thread requests 48 kHz and receives less: ~66,500 missing
  frames per window (~28 %), which `ps2_runtime.cpp` fills with silence.
  Inference: the audio dropouts on the ship come from the global speed of
  the emulation, not from the cost of the SPU2.
- The median flips vary a lot between rounds unrelated to the level
  (level 0: 37.4 and 28.7; level 1: 41.0 and 40.1; level 2: 29.8 and 27.7). With this
  dispersion the overhead of level 1 cannot be quantified. `guest_flip_hz`
  are not physical FPS.
- The old 5 % estimate is replaced by these measurements. The SPU2
  is not a bottleneck: optimizing the envelope would save at most ~1 %
  of the thread. No optimization has been done.

Pending: decide how to handle the sample deficit (time stretching or
audio pacing) when the emulation does not reach real time; it is an audio
output decision, not a matter of SPU2 cost.

## `GOW_SAMPLER` sampling profile: EE thread breakdown on the ship (2026-10-15)

`patches/ps2recomp-sampler.patch` (Windows x64 only). `GOW_SAMPLER=start:end` in seconds, or `1` for
the whole run. A dedicated thread suspends the EE, VU1 and GS frontend threads about 1000 times per second,
copies their stack (RIP plus `RtlVirtualUnwind`) into a preallocated buffer, without allocating memory while the thread
is suspended, and resumes it. On close it symbolizes with DbgHelp (`ps2EntryRunner.pdb` next to the exe) and
prints `[gow-sampler]` with the 40 functions with the most self and inclusive samples per thread. They are
samples of the thread's wall-clock time, including waits, not exclusive CPU use.

First measurement: `main` `ed181a8` plus the sampler, exe `20e87cea…`, VU1 compiled, script and
configuration of the previous controls, `GOW_PERF_DIAG=frames` (no per-subsystem clocks),
sampling from 50 to 145 s in state 11. Result: 51,059 samples per thread, actual interval 1.86 ms,
none failed. EE thread, percentage of samples:

| Inclusive | % | Reading |
|---|---|---|
| `GS::notifyExternalVSync` → `RtlSleepConditionVariableSRW` | 28.5 | the EE waits for the GS at every VBlank |
| `PS2Runtime::advanceIopEeCycles` | 31.9 | IOP emulation; `runCycles` 27.1, `serviceSpu2` 9.7 |
| `PS2Memory::advanceEeTimers` | 9.4 | self: walks the 4 timers at every checkpoint |
| `ps2_stall::enabled` + `ps2_perf::enabled` | 2.9 | self: guard of non-inlined local statics |
| Game code (`sub_…`) and rest | ~27 | e.g. `sub_00162F18` 6.9 incl., `sub_0017A1D0` 6.6 |

- Fact: more than 40 % of the EE thread goes into advancing the IOP and the timers from every
  checkpoint (`checkpointDue`, 43 % inclusive), and almost all of it is checking that there is nothing to do.
  The IOP's `executeInstruction` only adds 2.4 % self.
- Fact: 28.5 % of the EE thread is blocked waiting for the GS inside `notifyExternalVSync` (GS/presentation
  area). It is documented for whoever owns that area; it is not touched here.
- `ps2_stall::enabled` (1.6 %) was introduced by the stall diagnostic (#87): it is fixed in the following patch,
  together with the IOP and timers fast path.
## Cheaper EE checkpoint: exact idle IOP and lazy timers (2026-10-15)

`patches/ps2recomp-checkpoint-fast.patch`, based on the breakdown measured with `GOW_SAMPLER` (previous section):

- **Idle IOP:** `IopEmulator::runEeCycles` only adds cycles while the IOP has no ready threads and the
  target stays below the first possible event: a thread wakeup, end of DMA, callback,
  IOP timer event or next SPU2 sample. It is exactly what `runCycles` would do in
  that stretch. The limit is invalidated by any external input (RPC, SIF, module loading, memory
  writes) and by a change of the IOP core version.
- **Lazy EE timers:** `advanceEeTimers` accumulates cycles up to the next possible interrupt
  (`cyclesUntilNextEeTimerInterrupt`) and applies them before any read or write of their
  registers. Applying them at once or in pieces gives the same count and the same clock remainder.
- `ps2_stall::enabled` and `ps2_perf::enabled/countFrames` read `inline const` globals instead of
  local statics with a guard (2.9 % of the EE thread in the sampling).
- Regressions: an idle IOP advanced in 200,000 irregular steps keeps cycles and samples after each
  step; lazy timers versus immediate application in 300,000 steps (same interrupts,
  counts and deadline). Both fail with a mutation of the limit (verified).

Measurement on the ship (exe A `20e87cea…` = `main` plus the sampler; exe B `9e61941e…` = A plus this
patch; 3 rounds of 150 s per side alternating A/B, 5 s windows with t=50..145, `GOW_PERF_DIAG=frames`,
`GOW_SPU2_PERF=1`, `GOW_DELTA_DIAG=1`):

| Metric (median [min..max]) | A | B |
|---|---|---|
| game speed (`[gow-delta]`, 1.00 = real time) | 0.91 [0.60..1.76] | 1.00 [0.84..1.10] |
| SPU2 samples per second | 44,365 [34,295..83,716] | 49,436 [48,295..50,331] |
| entries to `vid::Flip` per second | 30.1 [16.3..101.6] | 30.3 [17.5..60.2] |

- Fact: with the patch the game keeps real speed and the SPU2 produces real-time
  samples. The ~28 % silence deficit measured before disappears. The samples stay ~3 % above
  48 kHz; this is being watched.
- Fact: the median flips do not change (~30, two VBlanks per frame). The improvement is in regularity and
  speed, not FPS. `guest_flip_hz` is not physical FPS. `host_hz` was bimodal (17 in two B rounds,
  60 in one) and is not attributed.
- Sampling of B (`sampler_cpfast`): the EE thread waits 57 % of the time (before 28 %); `checkpointDue`
  goes from 43 to 21.7 % inclusive, the IOP from 31.9 to 14.1 %, the wait in `notifyExternalVSync` from 28.5 to
  10.1 %, and `advanceEeTimers` stays at 5.9 % self. The loop `0x17A2A0` reads T0 on every iteration and forces
  the application; the next step would be a native clock for the timers without events.
- Anomaly (presentation area): in one A round the host thread stopped iterating around t≈5..10 s
  (only one `[gow-perf]` line, the window did not answer `WM_CLOSE` and had to be terminated), while the
  game was still in state 11. Its FPS are not used; its audio and speed are.

## Waffle565 ports: SPU2 NAX and EE fast accesses (2026-10-15)

[Waffle565/God-Of-War-Native-Port](https://github.com/Waffle565/God-Of-War-Native-Port) forked from this repository's
patch stack on 2026-10-09. The following are ported, with attribution in the patches and in the commits:

- `ps2recomp-spu2-nax.patch` (runtime@65e1d79): the NAX register is read inside the block that is playing, like
  `NextA` in PCSX2. Our NAX pointed to the next block; on the last block of one half of the streaming
  ring it ended up outside both halves and 989snd (989NOMID.IRX 0x13258) aborted the stream (error
  0x35): the music restarted every few seconds. Regression: NAX inside the block in a two-block
  ring; it fails with the previous code (verified). The SPU2 reference hash does not change.
- `ps2recomp-ee-fast-access.patch` (runtime@96f61ab and the macros part of runtime@e96ee58): the
  `READ*`/`WRITE*` macros access the scratchpad directly when the access is aligned, and `SET_GPR_*` write
  the low 64 bits with a single store. Regressions for the scratchpad (and its alias `0xF0000000`) and
  for GPR semantics (sign extension, high 64 bits intact, `$zero`).

Validation: `ps2x_tests` 640/640 with the two patches and the native VU1 on top. Full local build
(exe `ad179aa4…`): the ship reaches state 11 and closes with `WM_CLOSE`, code 0, with the native VU1
disabled. The music fix has not been verified by ear; the effect described is that of the
originating project.

## Waffle565's native VU1, optional with `GOW_VU1_NATIVE=1` (2026-10-15)

`patches/ps2recomp-vu1-native.patch` gathers, via `cherry-pick` onto the current series, the commits of its
`runtime` branch 61052ee, 5cea74e, af18417, 0055349, 994a514, 6358428 (VU1 part only), 71fb632, ef2692f
and 1d9d563, plus two build adjustments (`<vector>` and `m_verifySilent`, from runtime@8af9676).
`tools/vu1/vu1n_gen.py` (from its `main`) generates, from the captured micro-memories,
C++ blocks with immediate semantics and flag latency between blocks. The exact engine
stays as a fallback for any missing block and as an oracle: `GOW_VU1N_VERIFY=<n>` compares n
executions (state, data memory and GIF packets; exact integers, floats with relative tolerance
2e-4). `GOW_VU1N_RECORD/REPLAY` records and replays to compare generator versions. Here it is
**disabled by default**; in the originating project it is active.

- Generation with the 501 micro-memories of this repository: 1302 distinct blocks, 1302 generated, 0
  unsupported.
- Verification with the game (ship, 120 s, `GOW_VU1N_VERIFY=3000`): **2000 executions compared, 0
  discrepancies** against the exact engine. State 11 reached and closed with `WM_CLOSE`, code 0.
- Performance: same exe (`ad179aa4…`) alternating `GOW_VU1_NATIVE=0/1`, 3+3 rounds of 150 s,
  `GOW_PERF_DIAG=1`. `vu_ms` per 5 s window: 4066 and 3630 (exact) versus 1474, 1477 and 1647 (native),
  a −60 %. Game speed does not improve (0.76 and 0.66 versus 0.58, 0.57 and 0.73), and with
  `GOW_PERF_DIAG=1` neither side reaches 1.00. This profile mode has a noticeable cost of its own; with
  `frames`, the `checkpoint-fast` branch gives 1.00.
- Why it does not improve (sampling `sampler_vu1n`, native active, `GOW_PERF_DIAG=frames`): EE, VU1 and GS
  frontend wait 52, 66 and 87 % of the time. The 52 % of the EE is entirely inside `GS::notifyExternalVSync`,
  waiting for `GS::m_stateMutex` (`std::recursive_mutex`) to call the VSync observer; in the base
  measured earlier it was 28.5 %. Inference: another thread, probably the presentation/GPU one, holds that
  mutex for a long time, and the earlier the EE reaches the VBlank, the more it waits. It is a
  GS/presentation area: it is left documented for whoever owns it. Until it is resolved, speeding up EE, IOP or VU1 does not
  translate into game speed.
- The intermittent stall appeared again in a round with the exact VU1 (`vu1ab_1A`): state 4 at ~22
  s, no flips since t≈36..40 s, right before the move to state 11; EE ≈3800 ms and IOP ≈1200 ms per
  window, with no VU or GS. It is the same signature as on runner 105, but at a different load transition. That
  round had `GOW_STALL_DIAG=0`; a series with the diagnostic is launched to capture it.

## Integration of #91 and #97 (2026-10-15)

- #91 (fewer wait checks in VU1 blocks): merged. With the game's 501 micro-memories only 1
  of 1294 blocks meets the fast path conditions; the effect in the game is negligible. 60 s run
  on the ship: state 11, closed with `WM_CLOSE`.
- #97 (P4 uploads by rows): order conflict in `compilar.ps1` resolved (the patch goes last). The series
  of 123 patches applies cleanly. Full local build (exe `0cddf7cf…`) and visual comparison with an exe
  without #97 (`02e81c90…`): 10 captures at the same instants (4..110 s) of the title, the difficulty
  choice, the Kratos close-up and the combat on the ship, with menu text, HUD and correct-hit
  counter. No texture differences are seen; the combat differs due to the normal variation between
  runs. Performance was not measured.

## The EE VBlank no longer waits for the GS mutex (2026-10-15)

With `GOW_SAMPLER` also recording the host thread and the GPU worker
(`ps2recomp-sampler-threads.patch`), and the native VU1 active (`sampler_gs_n`):

- The GPU worker is busy 87 % of the time; 73 % is `GSGpuBackend::Impl::prepareTarget`, and
  inside it, ~62 % is the wait for the upload ring barriers (`GSGpuUpload::Ring::put`,
  `WaitOnAddress` in the driver). The host spends 91 % in `SwapBuffers`. Inference: the GPU is
  saturated with this renderer.
- The GS frontend waits for a slot in that queue (`GSThreadedBackend::PublishLocked`, 65 %) **inside
  `processGIFPacket`, with `GS::m_stateMutex` held**. The EE waits for that mutex in
  `GS::notifyExternalVSync` (58 %) when processing each VBlank, so the VBlanks arrive late and the
  game speed drops (0.58).

`ps2recomp-gs-vsync-unlocked.patch`: `notifyExternalVSync` only takes the mutex if there is an external observer
(the optional PCSX2 mirror); without it, it neither reads nor writes GS state. Regression: a backend that blocks
`Submit` with the mutex held; the notification must return. It fails without the change (verified).

Measurement (exe A `a075fcc7…` without the change, exe B `02e81c90…` with it; both with `GOW_VU1_NATIVE=1`, 3+3
alternating rounds of 150 s on the ship, windows of t=50..145 s, `GOW_PERF_DIAG=frames`):

| median [min..max] | A | B |
|---|---|---|
| game speed | 0.63 [0.36..0.96] | 1.00 [0.33..3.33] (rounds: 1.00 / 0.99 / 1.00) |
| SPU2 samples per second | 29,272 | 49,160 |
| entries to `vid::Flip` per second | 33.2 | 31.8 |

When the GPU cannot keep up, the game no longer slows down: it keeps the real speed and the audio, and drops
frames. One B round had a recovery burst (maximum 3.33) that may have coincided with a test build
launched in parallel. The GPU saturation remains: it is the next target (renderer).

## Migration to Waffle565's base (2026-10-15)

User decision: adopt the runtime of **Waffle565/God-Of-War-Native-Port** as the base
to run the game as its port. Details of the patches in [`architecture-details.md`](architecture-details.md).

**Done (verified):**
- `ps2x_tests` suite 439/439 on Windows (MSVC) and on Linux (GCC, WSL Ubuntu 24.04), with 89 cases removed for pieces
  replaced by design (list in `patches/ps2recomp-waffle-tests.patch`).
- Two defects of Waffle's runtime fixed in our own patches: it did not link with GCC (`inline` on
  PCSX2 functions called from another unit) and the native VU1 lost its `NativeState` with each `VU1Interpreter`
  (`gow_vu1_fmac_test` went over 7.6 GB; now 47 MB).
- Full build on Windows and run with the extracted disc (`tools/iso_extract.py --layout`), values from
  `play.cmd` (`PS2X_GS_WORKER=1`, `GOW_GS_FINISH_ASINCRONO=1`) and new-game script (`logs/tools/correr_w.py`,
  private): difficulty menu, ship, combat, HUD and blood correct in the captures (1024×894, 2x internal
  resolution). The window responds to WM_CLOSE.
- Native IOP: a run with `PS2X_IOP_DUMP_MODULES` dumps the 8 IRXs; with `GOW_IOP_MODULOS` and recompilation
  the 8 run as native code. Game start (`[gow-pad2:test] gameplay start`): 33.6 s with the
  interpreter, 21.1 s with the native IOP and `GOW_FAST_BOOT=1` (Waffle documents ~20 s).
- VU1: `GOW_VU1_STATS=1` gives 0 interpreted steps (every block native), ~2.7 s of VU1 per 5 s window.

**Measurement (ship scene with combat, 150 s, final windows, `guest_flip_hz` = calls to `vid::Flip`, not physical
FPS; game speed with `GOW_DELTA_DIAG`):**

| Executable | Rounds | `guest_flip_hz` median (min–max per round) | speed |
|---|---|---|---|
| PR #101 (`bin\gsn`, previous base, native GS and VU1, `GOW_PERF_DIAG=frames`) | 3 | 59.98 / 60.00 / 60.00 (59.79–60.20) | 1.00 |
| Waffle base (`bin\waffle2`, native IOP, `GOW_PERF_DIAG=frames`) | 2 | 44.17 / 48.53 (42.75–60.16) | 1.00 |
| Waffle base (`GOW_PERF_DIAG=1`, more expensive) | 3 | 47.54 / 44.34 / 44.80 | 1.00 |

Fact: in this scene Waffle's base gives fewer flips per second than PR #101, without losing game speed.
Breakdown of Waffle's base (`GOW_PERF_DIAG=1`, 5 s window): EE 2.6 s, EE VBlank wait 2.1 s, VU1
2.8 s (worker thread), GS 1.9 s (stage thread); the EE barely waits for the worker (`PS2X_GS_WORKER_DIAG=1`:
~15 ms per window in `mmio 0x12001000`). Inference: per frame, EE (~12 ms) + VU1 (~13 ms) exceeds 16.7 ms
and some frames miss the VBlank. Hypothesis: the EE improvements made after Waffle's fork are missing
(checkpoint-fast #94, mutex-free VBlank #100), which do not apply as-is on its runtime.
Separate observation: the PR #101 executable with `GOW_PERF_DIAG=1` hung at ~60 s
(`runs\abw_perfA`), another appearance of the intermittent stall of the previous base.

**Next steps:** port checkpoint-fast and the lock-free VBlank to Waffle's base and measure A/B; the `[mmio]` table
of the video player (13 entries from Waffle, private); diagnostics `GOW_SAMPLER`, `GOW_STALL_DIAG`,
`GOW_SPU2_PERF`.

### VIF1 UNPACK fast paths on Waffle565's base (2026-10-16)

- Sampling (`muestrear`, 30 s, ship with a still camera, `bin\waffle2`): in the worker thread (VIF1 + VU1)
  `PS2Memory::processVIF1Data` was 18.5 % of the samples, more than the native VU1 (`runNative` 11.3 %). Waffle's
  runtime unpacks each vector through the generic path.
- `patches/ps2recomp-vif1-unpack-rapido.patch` ports the fast paths of the previous base (one loop per unmasked
  format and the SSE path with mask or STMOD 1-3). Difference from the previous version: STMOD 3 also stores the
  data in ROW, like Waffle's generic path (and PCSX2), so without a mask only STMOD 0 goes through the simple loop.
- Test `VIF1 UNPACK fast paths match the generic path`: compares the two paths (switch
  `ps2_vif1::setUnpackFastPaths`, for tests only) in VU1 memory and ROW for all formats, mask,
  STMOD 0-3, five CL/WL cycles and sign extension. It fails if the STMOD 3 case is removed (verified).
- Alternating A/B, 3 rounds of 130 s, same scene, `GOW_PERF_DIAG=frames` (`guest_flip_hz` of the last 12
  windows, not physical FPS):

| Round | A `waffle2` (no change) median (min–max) | B `waffle3` (with the patch) median (min–max) |
|---|---|---|
| 1 | 47.35 (43.53–59.96) | 50.94 (49.56–52.76) |
| 2 | 44.75 (42.55–60.16) | 53.76 (48.08–60.00) |
| 3 | 46.55 (43.55–59.98) | 54.00 (51.00–59.80) |

  Game speed 1.00 in all. It is still below 60: next are the worker thread's memory allocations
  (`RtlAllocateHeap` ~3.9 % of its samples) and the native VU1.

### Reusable DMA buffers (2026-10-16)

- Worker trace (`PS2X_GS_WORKER_TRACE`, private `logs/tools/gap.py`), ship with a still camera, `bin\waffle3`:
  period per frame 17.75 ms = flip→kick of the DMA chain 1.66 ms + VU1/GS work 13.01 ms + end→flip 3.12 ms.
  60 Hz asks for 16.67 ms.
- The EE flattened each chain (~2.6 MB per frame) into a new vector that grew by reallocating; the worker
  freed it when done. `patches/ps2recomp-dma-buffers.patch` reuses those buffers (up to 4). Test
  `DMA sends reuse buffers without replaying earlier data` (fails if the reused buffer is not emptied).
- Trace with the change (`bin\waffle5`): flip→kick 0.22 ms (before 1.66–1.78), work 10.63 ms, period 16.55 ms in that
  2 s window (a single window; `waffle3`'s work varied between 13.0 and 14.9 ms in two windows).
- Alternating A/B of 7 rounds, 130 s, `guest_flip_hz` (not physical FPS), median of the last 12 windows:
  A `waffle3` 49.39 / 55.55 / 51.15 / 53.20 / 56.15 / 50.16 / 53.79 (median 53.20);
  B `waffle5` 56.96 / 52.94 / 52.17 / 54.57 / 55.75 / 56.36 / 56.96 (median 55.75). B wins in 5 of 7; the
  dispersion between rounds (±4) is comparable to the difference. Game speed 1.00 in all.
- Discarded (no measurable improvement): reusing the GIF arbiter vectors and not sorting its already sorted queue
  (`waffle4`: A 48.60–58.98, B 53.98–55.37 in 5 valid rounds).
- Presentation hang: a run of `waffle4` (`runs\abg_2B`) kept running 148 s without any `[gow-perf]`
  line and did not answer WM_CLOSE; earlier, `w1_dump` (`waffle1`, with no changes of our own) did not answer WM_CLOSE either.
  The harness now dumps the stacks of all threads (`pilas.exe`, private) if there is no `[gow-perf]` at 40 s;
  0 appearances in the following 14 runs.

### Rumble off the game thread; 16/8-bit SSE UNPACK discarded (2026-10-16)

- Sampling profile (`muestrear4`, 150 s, ship with a still camera, `bin\waffle5`): in the EE thread 1.9 % of
  the samples was in `openSonyPads ← sonyRumble ← ps2PadWindowsRumble`. Without a Sony pad connected, each motor change
  from the game re-enumerated the HID devices (SetupDi + `CreateFile` on each one) at most every
  2 s, in the game thread. In two worker traces an isolated 73-74 ms frame appeared.
- `patches/ps2recomp-pad-rumble-scan.patch` does that scan in a separate thread; rumble uses the pads already
  open. With the change (`bin\waffle7b`, 120 s profile) `openSonyPads` does not appear in the EE thread. No test
  in `ps2xTest`: it is Windows code with real HID devices.
- Three-way alternating A/B, 4 rounds of 130 s (`guest_flip_hz`, not physical FPS), `waffle5` = `main`:
  `waffle5` 59.15 / 56.15 / 57.54 / 54.97; `waffle7b` (rumble) 56.56 / 55.17 / 58.54 / 58.57: neutral on average;
  `waffle8b` (16- and 8-bit V4/V3 UNPACK with SSE4.1) 51.56 / 51.95 / 58.74 / 52.16: worse in 3 of 4, discarded
  (the differential test passed; it remains to be understood why it is slower than the scalar loop).
- Procedure error corrected: `waffle6/7/8` were built without `ps2recomp-dma-buffers` (working copy
  reverted), so their first comparisons are not valid; those of this section use `waffle7b/8b`, with the `main` base.
- Presentation hang: it reappeared once in `waffle6` (`runs\ab6_3B`: 4 `[gow-perf]` lines and then nothing,
  the game kept going 148 s). The harness watchdog now detects 15 s without new lines and dumps the stacks. 0 appearances
  in the following 38 runs (`caza5_*`, `caza6_*`, `sep_*`, `sepb_*`); 4 in total since the migration.

### Video player `[mmio]` table (2026-10-16)

- `GOW_IO_HIST=80` during the opening video (`Semo01`, new game with `GOW_SKIP_FMV=0`, `bin\waffle5`):
  13 player instructions were still accessing hardware through the generic path (~1360 times each per
  channel): `0x26ee18/24/34/54` (QWC/MADR/D_STAT/CHCR of VIF1 and GIF), `0x26eda0/ac/bc/d0` (toIPU channel),
  `0x26ed54` (D_ENABLEW), `0x26e844/60/68` and `0x26cc74` (GS display registers, 64 bits). They are the 13
  private entries that Waffle565 describes in the functions 0x26CB90, 0x26E798, 0x26ED20, 0x26ED68 and 0x26EDE0.
- Added to `[mmio]` of `config/recomp.template.toml`. When regenerating, exactly those 5 files change; the emitted
  code goes through the native DMA service (`eeDmaStore`) or the native display registers.
- With the change (`bin\waffle9`): `GOW_IO_HIST` no longer lists any access during the video; `Semo01` looks the same
  (49 `[MPEG:sync]` marks, correct captures).
- The failure of a video requested from the extras menu (`tools/pruebas/videos.py` of PR #107, `GOW_BONUS_MOVIE`):
  virtual call to `0x0` at `0x161c68` (method `+0xB4` of the table of a global object at `-0x3D48($s0)`, not yet
  constructed) and the main thread asleep. **The `[mmio]` table does not fix it** (a first correct run with
  it turned out to be chance): it is intermittent, 3 of 9 attempts with `D01MP03`; then 3/3 correct without the table
  (`waffle5`) and 3/3 with it (`waffle9`). It happens when the harness forces the request (`GOW_BONUS_MOVIE_DELAY` seconds
  after the menu starts updating) before the title has constructed that object. Correct run:
  270 images at 30.00/s, 8.01 s of image and 8.00 s of audio, A/V drift 0.01 s.

### Validation of the 67 videos and NTSC VBlank (2026-10-16)

- `tools/pruebas/videos.py` (PR #107) with the `main` executable + `[mmio]` table, one session per video (`--batch 1`):
  25/67 correct on the first try; 41 failures were the harness's null virtual call when forcing the request from the extras
  menu (`missing-target` at `0x161c68`; the video is not even loaded). Retrying those (up to 3 sessions,
  `logs/tools/reintentar_videos.py`, private): **61/67 correct**. In batches the 2nd forced request almost
  always fails; with `GOW_BONUS_MOVIE_DELAY=20` instead of 8, 5 of 7 sessions failed.
- Real failures: BONUS03 and BONUS06 (A/V drift 0.80 and 0.44 s), SEMO10 (drift 0.46 s and missing audio), SEMO08
  (214.6 s of audio for 210.2 s of image, same as in Waffle565), P04MP05 (stops, also open in Waffle565)
  and BONUS20 (correct image, RMS 0 for 208 s: to check whether the video has audio).
- Cause of the BONUS03/06 drifts: the runtime's VBlank was 16,667 µs (59.9988 Hz) and the NTSC PS2 gives
  60/1.001 Hz (59.94). Videos were presented at 30.00 images/s instead of 29.97 and the audio fell behind by
  0.1 %: 436 s × 0.001 = 0.44 s (BONUS06), 812 s → 0.81 s (BONUS03).
- `patches/ps2recomp-vblank-ntsc.patch`: VBlank period = 16,683,350 ns and kEeClockHz × 1001 / 60000 cycles.
  Test `VBlank field period is the NTSC 60/1.001 Hz field` (fails with the previous value; verified).
- With the change (`bin\waffle10`): BONUS06 correct (29.97 images/s, drift 0.01 s), BONUS03 correct (drift
  0.08 s), SEMO10 correct (drift 0.01 s, no missing audio). SEMO08, P04MP05 and BONUS20 stay the same (other causes).
  Ship with a still camera: `guest_flip_hz` median 56.15 (54.16–59.98), speed 1.00; the ceiling becomes 59.94.

### Anatomy of a frame on the ship and extended trace (2026-10-16)

- `patches/ps2recomp-gs-worker-trace.patch` extends the `PS2X_GS_WORKER_TRACE=<s>` diagnostic: configurable window
  (`PS2X_GS_WORKER_TRACE_SECS`, default 2 s), extra game functions (`PS2X_GS_WORKER_TRACE_PCS=hex,hex,...`) and
  events `stage-wake` (the GS stage raises FINISH and wakes the EE), `ee-gs-irq` (the EE dispatches the GS
  interrupt), `vblank` and `thread <id>` (EE thread that starts running). Disabled by default.
- 30 s trace on the ship with a still camera (`bin\wtrace`, 1640 frames, private `logs/tools/gap2.py`):
  - Per frame: flip → kick of the DMA chain (~2.6 MB) 0.3 ms; the game logic on the EE (`sub_00162F18`…) lasts
    8.5 ms median (p90 9.6) and runs in parallel with the work of the VU1/VIF worker + GS stage (median
    14.6 ms, p90 15.9, max 19.6); the stage finishes at the same time as the worker (`stage-wake` = `job-done`).
  - After the work: `ee-gs-irq` 10–20 µs later; from there to the next kick median 0.86 ms (p90 2.48; the slow
    cases have a VBlank in between); from `WaitForDMAComplete` to the flip median 2.15 ms (p10 1.00, p90 3.05) of serial
    EE work (it is not VBlank wait: the flips land at a median of 6.85 ms from the last VBlank, spread out).
  - Frame period ≈ work + 3.5 ms: work 12–14 ms → 17.12 ms; 14–16 ms → 18.32 ms; 16–18 ms → 20.18 ms.
    For stable 60 Hz the VU1+GS work would have to drop below ~13 ms.
  - There are no EE thread switches in that stretch (a single active thread). `DelayThread` is not called.
- The EE thread spends ~46 % of the time sleeping in `processDueDeadlines` (pacing against real time, 16 steps per
  field), mostly from `advanceIopEeCycles`.
- Discarded: VF/ACC register cache in the native VU1 blocks (`vu1n_gen.py --regcache`, not pushed): fewer
  generated reads (ACC 3052 → 1636) but the same cost, ~3.8 ns per VU1 cycle (the compiler was already forwarding the
  values); `GOW_VU1N_VERIFY=20000` gave the same single mismatch as without the change (run 15759, already existing).

### Images lost in the presentation (2026-10-16, user's game)

- User's game with the meter (`jugar.cmd`, 274 s of play): the game gave ~60 frames/s median, but over 28 seconds
  noticeably fewer images reached the window (e.g. 60 game frames and 44 images). It is the drop
  seen "with many enemies" that the game frame meter did not register. In dense combat the
  game also drops to 44–56 (EE ~3.8 s and VU1 ~3.7 s per 5 s window).
- Cause: the game's pacing is irregular (frames of 10 to 22 ms; the VBlanks it receives arrive every 10.8–23.3 ms) and
  `GSSharedPresent::Acquire` always took the most recent frame: if two frames fell within the same window
  refresh, the first one was not seen.
- `patches/ps2recomp-present-orden.patch`: the next frame not yet shown is displayed; it only jumps to the most
  recent one with 3 or more pending. `PS2X_GS_PRESENT_LATEST=1` restores the previous behavior.
  `patches/ps2recomp-fps-imagenes.patch`: the meter (F2) and the `[gow-fps]` line also count the images.
- Alternating A/B, 6 rounds of 130 s with continuous combat (the default script), seconds 40-130:
  images per second (median) 55.0 / 55.9 / 58.0 / 54.9 / 56.0 / 54.9 before, 59.9 / 59.4 / 58.9 / 59.6 / 59.9 /
  59.9 with the change; lost images 413 / 293 / 277 / 359 / 208 / 455 → 102 / 34 / 58 / 169 / 58 / 166.
  Game frames (median) 58.9 / 58.9 / 59.9 / 59.0 / 58.9 / 59.0 before and 59.9 / 55.0 / 55.9 / 58.1 / 56.0 /
  59.9 with the change: a possible small drop, unconfirmed (game speed stays at 1.00–1.01 in both).

### GIF packets in batches to the GS stage (2026-10-16)

Per-phase timers of the worker thread (temporary diagnostic, not pushed) in combat on the ship: two jobs per
frame of ~7.5 ms; the VU1 takes ~88 % (~930 calls per job) and passing the packets to the GS stage ~13 % (~2850
`push` per job, each with a lock, a copy and often a wakeup of the stage thread). The "slow mode" that
was seen between games is scene load: the slow games make up to 50 % more VU1 calls with the
same cost per cycle (3.8-4.0 ns).

`ps2recomp-gs-stage-lotes.patch`: the worker accumulates the packets (16-byte header with route and size, data
aligned to 16) and delivers them to the stage every `PS2X_GS_STAGE_BATCH` bytes (16384 by default; 0 = one by one), at the
end of each job and before waiting for the stage from the producer thread itself. Test: "GS stage batches packets
and delivers them in order with exact sizes".

A/B in combat, 5 alternating rounds (work per frame, median / frames with work > 15 ms), before → after:
13.15/9 % → 12.98/6 %; 14.04/22 % → 13.58/10 %; 14.47/30 % → 11.39/1 %; 13.65/12 % → 12.82/2 %; 14.48/30 % →
13.24/4 %. All 5 in favor; median of medians 14.04 → 12.98 ms, median frame period 17.3 → 16.9 ms.

### IOP cycles accumulated on the EE side (2026-10-16)

Sampling profile (with symbols) of a game in combat with the GS stage batches: the worker thread
waits ~44 % of the time; the EE thread is busy ~88 %, and ~30 % of it is checkpoint bookkeeping
(every 8 EE cycles, tens of millions per second): `IopEmulator::accrueEeCycles` 15 %, `checkpointDue` 6 %,
`advanceEeTimers` 2.5 %, `advanceIopEeCycles` 2.2 %, `eeCheckpointDue` 2.2 %, `IopSubsystem::accrueEeCycles` 1.7 %.
The IOP only does something every batch of 512 of its own cycles (4096 of the EE).

`ps2recomp-iop-acumulado.patch`: `PS2Runtime::advanceIopEeCycles` (now inline) adds the cycles and calls the IOP only
when its batch is due, which the IOP reports with `eeCyclesUntilBatch()`: same batches at the same checkpoint as
before. Test: "IOP batches are due exactly after eeCyclesUntilBatch EE cycles" (it also compares with
step-by-step accumulation over ~30 batches).

Result: the EE thread goes from ~88 % to ~64 % of samples in the executable (waits ~31 % instead of ~8 %). The
combat frames on the ship do not change (3 rounds: work 12.32/13.28, 10.92/9.67, 12.47/12.83 ms; period
16.70/16.95, 16.83/16.68, 16.68/16.81 ms): there the worker thread (VU1) rules. It is headroom for scenes where
the EE logic rules.

Note: `ps2xTest/src/ps2_spu2_tests.cpp` is not in `ps2xTest/CMakeLists.txt`; its tests do not run.

### EE pacing: 64 points per field (2026-10-16)

Frame trace in combat with the moments when the EE sleeps (local diagnostic): after the GS notice the
EE did not continue right away, but slept in `processDueDeadlines` ~1-2.5 ms per frame, waiting for pacing points
(`ExternalWake` 0xFFFFFFFF events of the VBlank grid). While waiting for the GS, the game polls
(`vid::WaitForDMAComplete`), and each iteration adds EE cycles ~10 times faster than real time; the pacing lets
the EE clock run up to a point ahead of the real one (1/16 of a field, ~1 ms), and when the GS finishes the game
has to sleep that lead before sending the next frame. It does not exist on the PS2: it is an artifact of
the emulation.

`ps2recomp-ritmo-fino.patch`: 64 points per field (maximum lead ~0.26 ms). Test: "EE clock never runs more
than 1/64 field ahead of the host clock" (a guest function that only spends cycles; fails with 16 points).

A/B in combat, 3 rounds (median period / p90 / % of frames <= 17 ms), 16 → 64: 16.91/18.45/55 → 16.73/18.09/59;
17.15/18.97/43 → 16.71/18.02/60; 17.13/19.01/43 → 16.71/17.89/61. 64 versus 256 points: no clear difference
(16.71/16.72/16.67 versus 16.67/16.68/17.06). The game's time step (`[gow-animation] delta`) stays at
~0.01668-0.01679 s (1/59.94) in both cases: speed does not change.

### EE cycle cost halved (2026-10-16)

With 64 pacing points, the serial part of the frame (end of VU1 work -> next flip) was still ~3.7 ms,
of which the EE slept ~3.1 ms and worked ~0.6 ms (local trace with the moments when it sleeps). The recompiler
charges 32 EE cycles per backward jump of the generated code and 8 per dispatch, without looking at how many instructions
there are; since the EE clock is tied to the real one, a high estimate forces the game to sleep PS2 time it never
spent.

Experiment with a temporary divisor (A/B in combat, 3 rounds, median period / p90 / % <= 17 ms): divisor 1 -> 2:
17.23/18.98/39 -> 16.67/17.66/67; 17.18/18.97/42 -> 16.67/17.69/67; 16.74/18.07/59 -> 16.68/17.68/68. By ranges of
VU1 work: 12-14 ms goes from 17.0 to 16.6 ms per frame and 14-16 ms from 18.1 to 17.0. Divisor 2 versus 4: no
difference (16.70/16.68/16.66 versus 16.66/16.75/16.68). Game time step (`[gow-animation] delta`)
~0.01667-0.01669 s in all cases: speed does not change.

`ps2recomp-ciclos-mitad.patch`: `kGeneratedCheckpointCycles` 32 -> 16, `kGuestDispatchCycles` 8 -> 4 (and the default value
of `PS2Runtime::eeCheckpointDue`). Test: "generated checkpoints charge 16 EE cycles each". With the final
build, 2 rounds versus the previous one: 17.03/18.59/49 -> 16.67/17.63/70; 16.98/18.40/52 -> 16.72/18.00/63.

### Native VU1 dispatcher: 64-byte slot (2026-10-17)

Per-address profile (`muestrear4` with `MUESTREO_DIRS`) of `VU1Interpreter::runNative` in combat: the hottest jump is the read of `sl.known` (cache miss: 2048 slots of 128 bytes = 256 KB) and, after each block, the
read of `cyc[pairs - 1]` from its timing table and the history writes.

`ps2recomp-vu1-ranura64.patch`: the per-predecessor memo fields move from the slot to `BlockTiming` (only used by
blocks that read input flags) and the slot stores `idleLast` (= idle[pairs - 1]): it fits in one cache line
(static_assert) and the end of a block with an idle table does not read the table. When replacing an entry of the timing
cache it no longer walks the 2048 slots. Deterministic replay (4000 combat executions x 19): 0 differences;
381.9/392.2/400.4 -> 384.2/379.0/383.6 ms (~2 %). In the game, below the noise (3 rounds: 2 in favor).

Discarded: successor slot prefetch (replay 378-382 -> 383-391 ms; neutral in the game) and not invalidating
the translated code when an MPG uploads identical bytes (the game really does switch microprograms: the invalidation
loop kept appearing in the profile).

### VU rounding with the MXCSR (2026-10-17)

The game calls the VU1 ~110,000 times per second (~1900 per frame), always through three entries (0x0000, 0x0018 and
0x0030), of 5-9 µs each (temporary statistic by start address). Each `VU1Interpreter::run` switched the
rounding with `fegetround` + `fesetround` twice: ~77 ns versus ~8 ns with `_mm_getcsr`/`_mm_setcsr`
(microbenchmark, MSVC /O2).

`ps2recomp-vu-redondeo.patch`: on x86-64 only the MXCSR is changed (all float arithmetic goes through SSE); on other
architectures `fesetround` continues. Test: "VU1 runs round toward zero and restore the host rounding mode".
Replay: 0 differences. Combat, 2 rounds: median work 12.69 -> 12.44 and 13.68 -> 13.36 ms.

Note for playing: `GOW_PERF_DIAG=1` enables the full accounting (reads the clock at every bucket change, thousands of
times per frame); to measure frames `GOW_PERF_DIAG=frames` is enough.

### Native VU1: an MPG only invalidates the blocks it reads (2026-10-17)

Temporary counters in combat: ~550,000 entries to `runNative`, ~4200 changes of VU1 code generation
(the game switches microprogram ~14 times per frame) and ~260,000 slot resolutions (`slotFor`) every 5 s: each
change invalidated the 2048 slots, including those of the resident code (entries 0x0000/0x0018/0x0030 and common
routines).

`ps2recomp-vu1-invalidacion-rango.patch`: `PS2Memory` records the range written by each generation (VIF1 MPG; the
other writes, the whole memory) in a 64-entry log (`vu1CodeWritesSince`), and `runNative` only discards
the slots whose block reads that range ([pc, pc + (pairs + 1) * 8)); if the log does not cover all the generations,
it discards everything as before. Test: "VIF MPG logs the VU1 code range of each generation".

Result: ~134,000 resolutions every 5 s (half; those that remain belong to the freshly loaded microprogram).
Native verification against the exact engine (`GOW_VU1N_VERIFY=200000`, combat): 12 discrepancies, the same 12 as
the base (differences of 1 in the last bit of a result, already known); none new. In the game the gain is
below the noise between games.

### Audio regression of #120 and EE clock catch-up (2026-10-17)

The video validation with the 17th version first gave 0 of 67, for two causes:

1. Harness: the local copy of `videos.py` had gone back to `GOW_BONUS_MOVIE_DELAY` 8; the request arrived before the
   menu built its object (null call at 0x161c68). With 20 s it works; with 30 s it arrives when the title has already moved
   on to the automatic idle demo and the null call returns (the game is left frozen after the request).
2. Real, from #120 (16 cycles per checkpoint): ~6,300-6,700 samples without audio (~0.13 s) at the end of each video.
   Bisection with A01MP01 and P01MP01 on the day's builds: up to the 64-point pacing, correct; from
   the halved cycles on, all fail. In long stretches of EE work (leaving a video) the EE clock
   ran behind the real one, the IOP (which advances with the EE cycles) too, and the audio buffer ran empty.

`ps2recomp-ee-ponerse-al-dia.patch`: every 2048 checkpoints, `checkpointDue` calls `catchUpToHost` with a margin
of one field (`slack`): if the EE clock is more than one field behind the real one, it catches up. Without a margin
the audio problem disappeared but the combat frame period went up to 17.2-17.5 ms; with one field (and with
50 ms) the videos A01MP01, SEMO01, P01MP01 and BONUS06 pass and combat stays at 16.66-16.70 ms (2 rounds).
Test: "a slow guest still reaches the first VBlank on host time" (fails without the change).

### Frozen video tests: the player's pad (2026-10-17)

The video validations froze from a different point in each batch (null call from 0x161C68
right after the forced request). The only difference between the good and bad logs was
`[pad] gamepad slot 0: Xbox Controller`: the user was playing another game with their pad while the tests ran, and
raylib reads pads even when the window does not have focus. The input moved the title menu and the video request
fell into a state without the +0xB4 method of the object `*0x29C2B8`. Without a pad, 14 of 14 correct; with a pad, 6 of 10
frozen. The waits of 8, 20 and 30 s (`GOW_BONUS_MOVIE_DELAY`) only changed the luck.

`ps2recomp-prueba-sin-mando.patch`: with `GOW_PAD_TEST=1`, `ps2_pad.cpp` uses no physical pad; only the script
controls the game. Note: in a normal game the game also receives the pad without having focus.

### Menu flicker in the middle of videos (2026-10-17)

The user saw, for a few milliseconds, the main menu background in the middle of the cutscenes. Log of each
presentation (local diagnostic) in BONUS14: almost all show the video buffer (FBP 0x68), but every ~1000
presentations (~17 s) 2-3 show FBP 0xD0, whose render target had not been drawn since before the video (the menu).
Log of the display register writes: the player sets `DISPFB2` = 0xD0 and returns it to 0x68
~130 µs later, every 66.7 ms. The console never shows it (the CRTC does not see a value that lasts only a fraction of a
line); the port took the snapshot of the registers from the window thread at any moment and sometimes landed inside.

`ps2recomp-pantalla-latch.patch`: `GS::latchDisplayField()` captures the display registers at the start of each VBlank
(called by the EE scheduler before publishing `vsyncTick`) and the presentation uses that snapshot. Test: "presentation
uses the display state latched at VBlank, not a transient write". Result in A01MP01: 1579 presentations of the
video, all of FBP 0x68 and none with old content.

### Native VU1: dispatch and region measurements (discarded, 2026-10-17)

Measurement with `rdtsc` (1 in 16 blocks) in combat: ~105 M native blocks every 5 s (~194 per VU1
execution, ~137 CPU cycles per block); the VU1 time splits into blocks ~73 %, dispatch and timing
accounting ~26 %, fixed cost per execution ~1 %. The time of the blocks is spread across the whole code memory
(0x0000-0x03FF 19 %, 0x2800-0x2BFF 14 %, 0x0C00-0x0FFF 14 %, the rest 1-9 % per zone): hand-rewriting a few
microprograms (HLE) would not give a large improvement.

Experiment: regions (local branch `vu1-regiones` of the clone and `stash@{0}` of the repository): the generator grouped the
blocks of each image joined by static jumps (426 regions) into one function with `goto` between blocks, same
per-block accounting inline; the dispatcher entered the region if all its blocks matched the loaded code.
Correct (replay: 0 differences; ~97 % of the blocks inside regions, 11.6 per call), but no
measurable gain: replay 377-381 versus 382-397 ms; in the game, VU1 time per cycle 3.4-3.5 versus
3.6-3.7 ns in one round and 3.6 versus 3.5 in another. The dispatch cost is memory stalls when reading the state of
each block, which the accounting needs anyway. Discarded because of the complexity it adds.
### sceCdStop in the native IOP (2026-10-17)

When testing the videos by starting a new game and replacing the intro (Semo01) with another video
(`GOW_MOVIE_OVERRIDE`), the IOP logged `unhandled import cdvdman:15` and a call that exhausted its budget of
400 M instructions: `sceCdStop` was not implemented and the thread waiting for it was left looping; the video did not
start. `ps2recomp-cd-stop.patch`: with no reader there is nothing to stop, it finishes immediately (and calls the
notification function with SCECdFuncStop, like `sceCdSeek`). With the change, A01MP02 plays in full in that case (998 images).
Test: "IOP sceCdStop completes at once". It had not appeared in the user's games.

Other videos reviewed: SEMO08 runs at 29.32 images/s (4.7 s of offset over 210 s; the player waits an extra image
cycle in ~40 % of the 30-image stretches; neither the disc, which responds immediately, nor the decoding,
~1 ms per image, is the cause; pending). BONUS20: its audio track on the disc is ~15 s of very low PCM (RMS
~540) for 208 s of image; the port leaves it silent. The five ship cutscenes (A01MP01-05), with the sound
through the real device: offset <= 0.2 s and no gaps.

### DelayThread outside a thread in the native IOP (2026-10-17)

With the same test (new game and replaced intro) and the sound muted, the RPC call "Stopping sound system"
of 989snd exhausted its instruction budget: the loop at 0x2D49C waits for its alarm handler (0x2D664) to
set the counter at 0x44360 to 2, with `DelayThread(33 ms)` between polls. The RPC server runs with no current thread and
`DelayThread` returned immediately without the IOP clock advancing, so the alarm never arrived.
`ps2recomp-iop-delay-fuera.patch`: outside a thread, `DelayThread` uses the same wait as `WaitSema` and
`WaitEventFlag` (the emulator lets the rest of the IOP run) until the delay has passed. Test: "DelayThread outside a
thread lets the IOP run for the delay". In combat on the ship none of these waits occurs; the replaced intro
no longer exhausts the budget.

### End of P04MP05: the demultiplexing stops at 0x1B9 (2026-10-18)

With the intro replaced by P04MP05 (the game loads the widescreen version, `P04MP05.PSW`), the video played
to the end and the game got stuck: 0 game frames until the end of the test. The EE thread went
round in circles at 0x18AC20 → 0x188848. The player reads the PSS in blocks of 0x4000 into a ring of 16 (0x188848); the last
block carries only 4 valid bytes (the program end code 0x1B9) and the rest is old ring data. The game's
`sceMpegCbNodata` callback (0x18AAA8) calls 0x18AC20 in blocking mode until it has 0x2000 bytes of
video pending, and only sends the rest and returns when the demultiplexing returns 0. The original
`sceMpegDemuxPssRing` (0x273CF0) stops at 0x1B9 and returns the preceding bytes, and then 0. The HLE counted the
whole block as consumed, so the game read again, received 0 bytes and repeated forever. In other videos the end
fell with more than 0x2000 bytes pending and it went unnoticed. P04MP05.PSW has 741 images; before, 739 were served.

`ps2recomp-mpeg-fin-programa.patch`: neither 0x1B9 nor what follows it count as consumed, and an input that starts
with it returns 0. Test: "sceMpegDemuxPssRing stops at the program end code". Verified with the replaced intro:
P04MP05 serves the 741 images, ends (`ended=1`) and the game starts at 60.2 s. A01MP02 still ends
the same way (998 images, game at 66.9 s).

### Correction: 989snd's "Stopping sound system" was the game's shutdown (2026-10-18)

The entry "DelayThread outside a thread" attributed the RPC call "Stopping sound system" to the test of the replaced
intro. The trace of a run in which it appears (A01MP02 instead of Semo01, with the fix already applied)
shows something else: the main loop 0x17AA18 ends because the flag 0x29C4D8 stops being 0, `main` calls the
shutdown 0x17A9B0 (which stops the sound with the command 0x1 of 989snd) and returns to crt0, which calls `Exit()`. Before the
fix, that shutdown was left hanging in the IOP; now it finishes and the main thread is left asleep. There is no static
writer of 0x29C4D8 in the ELF. It occurred in 1 of 9 runs (8 without failure, 6 of them with the watcher
`PS2X_EE_WATCH=29C4D8:4` recording no write). It may depend on the harness's video substitution
(`GOW_MOVIE_OVERRIDE`). Pending: catch the write with the watcher in a run that fails.

### Optional enhanced widescreen (2026-10-18)

The user proposed the PCSX2 pnach `SCUS-97399_CBE116C1.pnach` ("Widescreen 16:9", nemesis2000 and CRASHARKI). The
port already applied its data part (flag 0x29CC90 and aspect floats); the "enhanced" part rewrites the projection
function 0x169238 and in a recompiled port it cannot be patched at runtime. Comparing instruction by
instruction, its only substantive change is multiplying the horizontal aperture (field 0x37C) by 0.75 × aspect
(0x32F1B0). It is done with `[patches] instructions` of `config/recomp.template.toml` (0x169298-0x1692F4, without shifting the
rest: an integer comparison with `slt`/`movn` replaces the floating-point one and the 1.0 comes from aspect/aspect). The
factor is read from 0xFFFF0 (a watcher `PS2X_EE_WATCH=FFF00:100` saw no write by the game in a game) and
is set by the override every frame: 0.75 with `GOW_PANORAMICO=ampliado`, 9/16 otherwise (total factor 1, same as before).
Verified with GS captures at 3 s into the game: without the variable, the framing is the usual one; with it, the view
widens without distortion. Cost in combat on the ship: median from 59.9 to 54.9 game frames per second.
Requires `scripts\2_compilar.cmd` (regenerates the C++ of 0x169238).

### EE thread: checkpoint fast path (2026-10-18)

Combat profile on the ship (sampler, 35 s, `main` binary): the EE thread was busy ~85–90 % of the
frame and more than a third was per-checkpoint bookkeeping: `EeScheduler::accountCycles` 18.9 %,
`checkpointDue` 10.4 %, `PS2Memory::advanceEeTimers` 4.9 %, `PS2Runtime::eeCheckpointDue` 2.9 %. The generated code
calls `eeCheckpointDue` every 16 EE cycles and each call delivered the cycles to the timers and the IOP and
checked deadline, time slice and catch-up with the real clock. The worker thread (VIF1/VU1) and the GS ones
waited ~50 % of the time.

`ps2recomp-ee-via-rapida.patch`: `checkpointDue` (inline) only adds the cycles as long as `m_fastLimitCycle` is not reached
(the minimum of: next event of a timer, next IOP batch, end of the time slice and next catch-up with the real clock, now every
2048 × 16 cycles instead of every 2048 calls) nor the next
deadline (`m_nextDeadlineCycle`, which other threads can bring forward) and nothing is pending. On that cycle
(`checkpointDueSlow`) the timers and the IOP receive the cycles all at once: same events at the same cycles.
An access to a timer register (hook `PS2Memory::setEeCycleSync`, only in the EE thread) and the idle wait
(`waitForEvent`) deliver the pending cycles first. Test: "an EE timer read sees the cycles of the
checkpoint fast path" (fails if the hook is removed).

Result: in the same profile the EE thread is busy ~46 % (`eeCheckpointDue` 4.6 %); the rest is waiting for the
60 Hz pacing. At 60 Hz the frame period does not change (alternating A/B of 3 rounds, `ab_traza.sh`: median
16.68/16.71/16.70 versus 16.70/16.69/16.68 ms; % ≤17 ms 72/65/71 versus 71/67/68), because the EE was not the limit;
it is headroom for more frames per second. Suite 454/454.

Game time step (0x17D860, guard 0x29C64C): `delta = max(VBlanks since the previous frame, frames measured
with a timer and clamped to [1, 4]) / 60`. It never goes below 1/60 s: for more than 60 frames per second a
more frequent guest VBlank and another calculation of the step will be needed.

### Presentation: the GS stage yields the lock (2026-10-18)

With the game above 60 frames per second (120 Hz experiment, see the next entry) the window
would show 2-8 images per second in stretches of several seconds. The main thread stacks during the
drop: `GSHostPresentation::prepare` → `GS::latchHostPresentationFrame`, waiting for `m_stateMutex`. The GS stage takes
and releases it once per packet, thousands of times per frame; the mutex is not fair and the thread that releases it takes
it again before the one that is waiting. `ps2recomp-gs-prioridad-presentacion.patch`: the presentation registers a priority
wait (`ps2_gs_stage::priorityWaitBegin/End`) while it takes the lock, and the stage, between packets and without any
lock, yields while there is one. With 120 Hz, the images shown go to 59.8-60.6 per second throughout the combat.
Test: "GS stage yields between packets while a priority waiter is registered". Suite 455/455.

Pending: with `PS2X_GS_HW_SCALE=4` (and at 60 Hz) the window still drops to 0.5-1.7 images per second; it is another
cause (not investigated).

### Experiment: game logic at 120 Hz (2026-10-18, not pushed)

Local tree, `GOW_HZ=120`: the EE VBlank (not the IOP one) every 8.34 ms, and an override of 0x17D778 that replaces the
time step with the real elapsed time, clamped to [1/120, 4/60] s (with the game's flag 0x29C660, "VBlanks only", its value halved).
The first version, which only divided the result by 2, ran in slow motion
(speed 0.57): the timer term is already in sixtieths and clamped to a minimum of 1. With the corrected
version, the game speed (`GOW_DELTA_DIAG`) is 1.00. The game loop gives ~120 frames per second in scenes
light and 63-72 in the ship combat: there the VIF1/VU1/GS pipeline is the limit. The host presentation is still limited to
60 Hz. Not yet reviewed: videos (they count VBlanks), cutscenes, physics and sound at 120.

Correction about the game shutdown in the video tests (entry "the Stopping sound system was the game's
shutdown"): the death screen and the pause menu have the "Quit Game" option, and the harness's button script presses X at fixed
times. It is very likely that the shutdown was requested by the game's own menu (it writes the flag through a pointer, which is
why there is no direct writer in the ELF). It is not a port failure.

### Distance fog: the Z buffer read as color on the GPU (2026-10-18)

Profile of the GS backend thread at 120 Hz: `GSMem::ReadColorRun` 10.6 % and `decodeDirect` 8.9 % (almost all on the
per-texel line). With `GOW_GS_HW_STATS` and a temporary counter: ~300 decodings per 5 s of a PSMCT24 texture of
1024×1024 at `tbp 0xD00`: about 63 million texels per second, one million per frame, plus its upload to the GPU.
`0xD00` is page 104, the game's Z buffer (Z24, `zbp 104` in all targets). They are the 32-pixel strips
of the fog/DOF that copy the depth as PSMCT24 to `fbp 320`. `overwrittenByDepth` rightly discarded the color
target of that page (an old video), but then GS memory that never held the
GPU's depth was decoded on the CPU, and any upload in the half VRAM covering the texture invalidated it again.

`ps2recomp-gs-z-como-color.patch`: if a texture falls in the Z buffer of a target and that Z is the last thing written
there, it is read with the reinterpretation on the GPU (`reinterpretTexel`). The owner is the depth texture, its
Z format (inverse tables of 0x30/0x31/0x32/0x3A) and the word is the Z value (`zpsm` of the target).
`GOW_GS_HW_ZCOLOR=0` goes back to CPU decoding, for comparison.

Result: 0 texels decoded on the CPU (before ~310 million every 5 s). The GS captures at 3 and 8 s into the
game show the distance fog (washed-out background and mountains) that was missing and that is seen in the
PCSX2 capture of the ship combat (`logs/vif_pcsx2_inicio2/Screenshot.png`). Menus, in-engine intro and ship correct. At
120 Hz (experiment), the game loop in combat goes from 67.4 to 72.3 frames per second on average. No test in
`ps2xTest`: the OpenGL backend does not run in CI (no GPU); suite 455/455.

GPU usage ("GPU Engine" counter, 3D engine, of the process): 80 % at 2x and 62 % at 1x at 60 Hz on the ship; ~88 % at 120 Hz
with or without this change. Still high for what is drawn; pending investigation.

## Linux: GS OpenGL context with EGL (2026-10-18)

On Linux the GPU GS did not start (`[gs-hw] GL unavailable: GPU GS backend is only implemented for Windows`): the
context only existed with WGL, there is no other renderer and the window showed the magenta marker of the RAM
presentation with the game running behind. `ps2recomp-gs-egl-linux.patch` creates the context on Linux with EGL (`libEGL.so.1`
loaded at runtime, Mesa surfaceless display and, if not, the default display; core 4.6, with 4.5
and 4.3 as fallback) and the contexts of the workers shared with it. The list of GL functions goes into a common
function for WGL and EGL; on Windows the behavior does not change. On Linux the context is not shared with the window: the
presentation goes through RAM (readback and upload), the path that already existed.

Verified on Linux Mint (Ubuntu 24.04), Ryzen with integrated Radeon (radeonsi, Mesa 25.2.8), NTSC-U disc
(`SCUS_973.99`, single layer) read with `GOW_ISO`: `[gs-gl] EGL: AMD Radeon Graphics ... 4.6 (Core Profile)`, difficulty
menu and game with correct image. No test in `ps2xTest/`: creating the context needs a GPU and the CI does not
have one. The game build on Linux was done by hand following `compilar.ps1` (there is no script for Linux). Two
differences from Windows: the IRXs in `IOP_MOD/` must also exist in lowercase (the game asks for
`IOP_MOD/sio2man.irx` and the file system is case-sensitive), and GCC's LTO link takes ~20 min on a
single partition of the generated code.

Speed measured with `GOW_FPS=1` in the menu: ~6 game frames/s with the VU1 and IOP interpreter; 40-50 with the
native VU1 (1,156 micro-memories) and the native IOP. After a hand-played session the capture rose to 6,448
micro-memories; that build has not been measured yet.

`ps2recomp-vu1-captura-nativa.patch`: `GOW_VU1_CAPTURA` only saved micro-memories when the VU1 ran on the exact
engine, that is, with `GOW_VU1_NATIVE_OFF=1` and the game at ~6 frames/s. Now it also saves with the native VU1 active,
so what is still missing can be captured by playing at normal speed. It is a diagnostic enabled by the variable; without
it nothing changes.

## GS: conservative grouping of shadow volumes (2026-10-18)

Volume passes with modular blending (`COLCLAMP=0`) read the destination in the shader. The backend split them into one
call per triangle and placed a barrier between all the calls, some 3,000 per frame on the ship. The patch
`ps2recomp-gs-volumenes-agrupados.patch` keeps together only consecutive triangles whose areas do not overlap;
when two triangles may touch the same pixel, it keeps their order and the preceding barrier. The analysis is limited to
groups of 64 to keep its cost bounded. `GOW_GS_HW_VOLGROUP=0` restores the one-call-per-triangle path.

The independent suite covers adjacent, separate and overlapping triangles and the order between groups. The effect on FPS
is pending an alternating in-game measurement; a performance improvement is not yet attributed.

### Measurement of shadow volume grouping (2026-10-23)

Pending from the previous entry. Full build of `main` (`bin\wmain`), ship at 60 Hz, "GPU Engine" counter
(3D engine) of the process for 8 s, two alternating rounds: `GOW_GS_HW_VOLGROUP=1` 52.2 % and 51.2 %; `=0` 78.6 % and
77.2 %. The game, at 59.9-60.0 frames per second in all four cases. Before grouping: ~180,000 texture barriers
and draw calls per second, 99 % of them volumes (temporary counter).

### Game logic at 120 Hz: `GOW_HZ=120` (2026-10-23)

`ps2recomp-ee-120hz.patch` (last of the stack): `EeScheduler::configuredVBlankDivisor()` reads `GOW_HZ` (2 with 120,
otherwise 1). The EE VBlank and the pacing points use the NTSC field divided by it; `eeCycle()` gives the EE clock.
The MPEG HLE counts the video time in NTSC fields (`mpegFieldTickQ32`) and converts its waits to EE VBlanks.
The host presentation uses `SetTargetFPS(60 × divisor)`. In `src/gow_overrides.cpp`, `gowFrameStep120`
replaces the time step of 0x17D778 with the elapsed guest time (see "Experiment: game logic at
120 Hz"). Test: "GOW_HZ=120 halves the EE VBlank period". Suite 457/457.

Measured with `bin\w120` (full build of `main` plus this change), ship combat: game speed
(`GOW_DELTA_DIAG`) 0.995-1.003, game 65-73 frames per second, presentation 119.6 per second with 78-112 distinct
images, GPU 65 %. A01MP02 instead of the intro: between images 270 and 870, 20.02 s of video and 20.02 s
real pass, 998 images, and the game starts at 66.7 s (66.98 s at 60 Hz).

### Correction: the game shutdown in the video tests was a harness failure (2026-10-23)

With `GOW_HZ=120` the shutdown (main loop ended, `Exit()`) occurred in 2 of 3 tests with
`GOW_MOVIE_OVERRIDE`, so the "Quit Game" menu hypothesis does not hold. The cause was `gowMovieOverrideLoad`:
it put the video name under the stack pointer, lowered the SP for the call to 0x188CA0 and restored it afterwards, and
did not check for resumptions (`ctx->pc` different from the entry). If 0x188CA0 stopped at a checkpoint, the
SP was restored with the function half done, the resumption substituted the name again and the main loop frame
ended up shifted by 32 bytes. Now the name goes in its own buffer (`guestMalloc`), the SP is not touched and
resumptions call the original. 4 of 4 tests correct at 120 Hz. It only affected `GOW_MOVIE_OVERRIDE`.
### CI on ubuntu-26.04: DIV.S/SQRT.S outside the rounding change (2026-10-23)

GitHub's `ubuntu-latest` image moved to ubuntu-26.04 and the test "EE FPU div/sqrt round to nearest under a
round-toward-zero MXCSR" started failing on `main` too (re-run of #138: fails the same). Locally
(WSL, earlier GCC) and on Windows it passes. `ps2FpuDivideNearest`/`ps2FpuSqrtNearest` set the MXCSR to round to
nearest, operate and restore it; without `-frounding-math`, GCC and Clang assume the default rounding and may move the
operation out of that stretch (the game on Linux would round toward zero). `ps2recomp-fpu-barrera.patch`:
`PS2_FP_PIN` (an empty `asm volatile` with the value in an SSE register) pins operands and result between the two
`_mm_setcsr`; on MSVC it does nothing. The test uses the same for its control division.

### 3x and 4x internal resolution after offloading the GPU; frames in flight (2026-10-23)

Full build of `main` with native VU1 and IOP (`bin\wbase`), ship at 60 Hz, GPU counter of the process:
with `PS2X_GS_HW_SCALE=3` (≈1440p) the game gives 60.0 frames per second and the window 58.7 images per second (GPU
88 %). On 2026-10-18, before the fog on the GPU (#136) and the volume grouping (#138), it gave ~33. With
`PS2X_GS_HW_SCALE=4` the game gave 59.7 but the window only 2.4 images per second. The main thread stacks:
`EndDrawing` → `SwapBuffers`, waiting inside the driver. The backend kept sending frames to a GPU slower
than the game, the driver queue grew and the window waited behind it.

`ps2recomp-gs-cuadros-en-vuelo.patch`: when presenting, the backend waits (100 ms at most) for the GPU to finish the
frame presented two frames earlier (`PS2X_GS_FRAMES_IN_FLIGHT`, 2 by default, 0 = no limit). With 4x: game 49.9
and window 48.5 images per second (GPU 95 %). With 2x: 59.9 and 59.2, same as before. With `GOW_HZ=120`: 69.9
frames per second with the limit and 70.4 without it (within the noise). No test in `ps2xTest` (OpenGL backend);
suite 457/457.

Profile at 120 Hz (combat, `GOW_HZ=120`, ~70 frames per second), for the next phase: the bottleneck is the
VU1 worker thread. In 16 stacks taken during the game, 14 show it working (native blocks,
`runNative` dispatch, `XGKICK`/delivery to the stage) and 2 waiting for work. The frame work lasts ~13 ms
(`ab_env.sh`, 3 rounds). The GS stage processes ~8 ms per frame and the GS backend is busy ~24 %. In
`runNative`, 28 % of its samples are in the indirect call to the block and 22.5 % in the slot read
(`sl.known`): dispatch branch-prediction and cache misses. More queue in the backend (`PS2X_GS_QUEUE_CHUNKS=64`)
does not change the work duration (13.1 versus 13.0 ms); stage batches of 2 KB or 64 KB are worse than the current
16 KB.

### VU1 in parallel by microprograms: not viable (2026-10-23)

Starting data (combat, `GOW_VU1_STATS=1`, 60 Hz): ~1,650 microprograms per frame, of ~1,730 cycles on average,
~2.85 M VU1 cycles per frame at 3.4 ns per cycle (~10 ms). Breakdown of the worker thread at 120 Hz (sampler,
busy time): native blocks 44 %, dispatch 21 %, exact timing 15 %, VIF1 unpacking 11 %,
XGKICK/GIF 4 %.

To split the microprograms across threads, each `MSCAL` would have to depend only on constants and on its input
buffer. Local diagnostic (interpreted VU1, `GOW_VU1_NATIVE_OFF=1 GOW_VU1_SIN_COMPILAR=1`; registers read
before being written according to `decodeUpperUsage`/`decodeLowerUsage`; memory read that another microprogram wrote and that
the VIF has not overwritten), 840,000 microprograms: 99.9 % read registers written by the immediately preceding one
(`vf5`, `vf4`, `vf29`, `vf15`, `vf16`, at the three entries 0x0000/0x0018/0x0030), and ~78 % read memory of the
previous one (quadwords 656, 315, 269, 587). The register value received from the previous one differs from the one that was there before
in 87 % of cases (in memory, 21 %), so speculating that it does not change does not work either. The microprograms
form a data chain: the VU1 must execute in order. For more than ~75 frames per second in combat what is left is
to speed up the execution itself (blocks, dispatch, timing).

### Native VU1: CLIP without branches (2026-10-23)

Line profile of the hottest blocks in combat: in `b0d00_53ba0530`, `clipVal` was 15 % of the
samples. It dropped the two vectors to memory and made six scalar comparisons with a branch; with clipping data the
processor mispredicts a lot. `ps2recomp-vu1-clip-sinsaltos.patch`: `vu1n::clipBits` gives the six judgements with
two SSE comparisons (`v > |w|`, `v < -|w|`), `movemask` and a table that interleaves the bits. With NaN the ordered SSE
comparisons give false like the scalar ones, and `-|w|` as a sign change gives the same with ±0. Test: "VU1 native CLIP
without branches matches the scalar judgements" (1,331 combinations of ±0, ±1, ±2.5, ±FLT_MAX, ±inf and NaN).

Measured: VU1 replay (`replay_vu1.sh`, 76,000 executions, 3 alternating rounds) 398.4/392.6/404.4 ms before,
403.4/386.3/389.6 ms after, and 0 bit-for-bit differences with what was recorded. In the game (combat, `GOW_VU1_STATS`,
median of ns per VU1 cycle; a metric that does not depend on how much is drawn): 3.476/3.450 before and 3.448/3.432/3.415
after, ~1 %. The replay repeats the same data and the branch predictor learns them, so it underestimates
exactly what this change fixes. The work duration per frame (`ab_traza.sh`) varies ±1 ms between runs
depending on the scene: it is no use for changes of this size.

### VU1: two discarded experiments (local ACC, parallel VIF1) (2026-10-23)

Breakdown of the hottest native blocks in combat (line profile of 40 blocks, grouped by helper
function): `madd` with its loads (`ldAcc`, `ldn`, `bc`) ~41 %, `divOp` 8 %, `ftoi` 8 %, `itof` 6 %, function
entry and exit ~12 % (on Windows x64 `xmm6`-`xmm15` must be saved; the blocks are already compiled with `/GS-`,
`/arch:AVX2` and `/fp:fast`).

- ACC in a local variable of the block (generator `tools/vu1/vu1n_gen.py`: load on entry, store before
  `callUpper`/`callLower`/`xgkick` and each exit, reload after `callUpper`): bit-for-bit identical (0 differences in
  the replay), but no gain. Replay 392.0/388.9/383.3 versus 388.4/395.1/391.4 ms; game 3.46 versus
  3.40 ns per cycle. The processor was already hiding the latency of the pass through memory. Not pushed.
- VIF1 in parallel with the VU1 (`PS2X_VU1_HILO`, local): the VIF's own work is ~1.6 ms per frame at 60 Hz
  (`processVIF1Data` ~3.97 s of every 5 s, of which ~3.5 s is the VU1); 97 % of the unpacked bytes carry
  `FLG` (double buffer). With the VU1 programs in their own thread, handoff by busy-wait, and the VIF waiting
  before `MSCAL`/`MSCNT`, `FLUSH*`, `MPG`, `DIRECT*`, `MSKPATH3` and the `UNPACK`s that touch the buffer of the running
  program, the game works and looks the same, but runs slower: work per frame at 120 Hz 13.59 and 13.70 ms with the
  thread versus 12.96 and 13.07 ms without it (two rounds, reversed order). Most likely: each `MSCAL` changes core
  and the unpacked data (~2.6 MB per frame) and the VU1 state travel between the caches of the two cores.
  Not pushed.

### Ship hold, thread priority and UNPACK with SSE4.1 (2026-10-24)

- Ship hold (the zone where a user game from 17-10 dropped to 40-46 FPS): it is `ATHN01B`, reached with
  `GOW_WARP=ATHN01B` (the `ATHN01*` zones are the ship; 35 s tour per zone with captures). With
  `main` (`bin\wfin`) and 190 s in the zone: at 60 Hz, average 59.9 per second according to `[gow-fps]` (10th percentile: 59.8;
  one-second minimum: 56.0); with `GOW_HZ=120`, 73.4 (minimum 63.6). The drop from that game no longer reproduces.
- `GOW_HZ=120`: burst of 8 GS captures every 20 ms in combat: no half-drawn frame.
- `AboveNormal` priority for the VU1 worker (`gsWorkerLoop`) and the GS stage, like the backend thread:
  A/B at 120 Hz, 3 alternating rounds (`GOW_PRIO_OFF` as the switch, same binary), work per frame of 13.76,
  12.97 and 12.80 ms without the change versus 12.73, 14.04 and 10.33 ms with it. No clear difference; not pushed.
- 8- and 16-bit UNPACK without mask with SSE4.1 (`pmovzx`/`pmovsx` of all the components at once, instead of
  the scalar component-by-component version): same output (test "VIF1 UNPACK fast paths match the generic path",
  full suite in WSL 458/458), but slower. Sampling profile (`muestrear4`, 95 s in `ATHN01B` at 120 Hz, two
  runs of each version): `processVIF1Data` with its lambdas is 9.0 and 9.1 % of the VU1 thread samples
  without the change, and 13.0 and 12.9 % with it (MSVC does not inline the per-format function and the scalar version
  was already well compiled). The work per frame (`ab_traza.sh`, 4 rounds) does not distinguish it: it varies ±1 ms between
  runs. Not pushed. Even if the vector version were twice as fast, the 8- and 16-bit UNPACK is less
  than 4 % of that thread (~0.25 ms per frame).
- Local tests with the game are launched with `GOW_AUDIO=0` (no sound; recording with `GOW_AUDIO_PCM` still
  works).

### Native VU1: no clampv after the FMACs (2026-10-24)

Each `add`/`sub`/`mul`/`madd`/`msub` result of the native blocks went through `vu1n::clampv` (a `max` and a
`min`: about 8 more cycles in the dependency chain, which on the VU1 usually runs through ACC). It changed nothing: the
operands are already finite (`ldn` normalizes Inf/NaN to +-FLT_MAX, and the registers of the `clean` set are FMAC results
of the block itself) and the blocks run with round-toward-zero, so a sum, difference or product of
finite values gives neither Inf nor NaN (overflow stays at FLT_MAX). The only exception was the slow path of `madd`
(`maddWide`, in double precision), which returned +-inf on purpose.

- `tools/vu1/vu1n_gen.py`: only emits `clampv` in `add`/`sub`/`mul` with I or Q as an operand (they are read without normalization).
- `patches/ps2recomp-vu1-madd-saturado.patch`: `maddWide` returns its result already passed through `clampv`. `macVal`
  counts 0x7F7FFFFF as overflow, so the MAC flags are the same as with infinity. Test: "VU1
  native madd returns overflows clamped with the same MAC flags".
- Counters in combat at 120 Hz (`GOW_VU1N_DIAG`, temporary): 22.5 M native blocks per second, 8.5 pairs on
  average; 15 % are loops over themselves, 9.7 % go through `blockTiming` and 48 % leave a flag tail.
  ~33 ns per block, of which the dispatch in `runNative` is ~7.
- Measured: VU1 replay (`replay_vu1.sh`, 76,000 executions, 3 alternating rounds) 396.6/395.7/392.6 ms
  before and 386.3/384.6/383.7 ms after (-2.6 %), 0 bit-for-bit differences in the 4,000 records. In the game
  (combat, `GOW_VU1_STATS`, median of ns per VU1 cycle): 3.466 and 3.427 before, 3.374 and 3.380 after (-2 %).

### Native VU1: dispatch, three discarded attempts (2026-10-25)

Per-address profile of `runNative` in combat at 120 Hz (`muestrear4` with `MUESTREO_DIRS`, `bin\wsat`): 13 % of
its samples fall on the read of `sl.known` of the next block's slot and another ~17 % on the history writes
right after the call to the block. It is the chain result -> `pc` -> slot -> function -> indirect call, which the processor
cannot run ahead on. Breakdown of the VU1 thread (profile of `ATHN01B`): blocks ~40 %
(counting the tail that does not appear in the top 70), dispatch and exact timing ~27 %, VIF 9 %, wait ~22 %.

- Cache of normalized operands in the generator (each `ldn` of a register is reused until it is written;
  MSVC reused the load but repeated the normalization: 8 `vpblendvb` for 3 registers in `b0d00_53ba0530`):
  replay 382.7/378.5/386.5 ms before and 378.9/379.3/386.7 ms after. No gain: the processor was already hiding
  those instructions.
- Prefetch of the successor slot (inside the slot itself, written only if it changes; already tried on
  17-10 with a separate table): in the game 3.413 and 3.382 ns per VU1 cycle without it, 3.422 and 3.364 with it. Neutral.
- Single-block loops repeated inside the block itself (187 blocks whose jump returns to their start, 15 % of
  executions; `VU1NativeAccess::loopAgain` did the accounting of one `runNative` iteration): 0 bit-for-bit
  differences, but replay 386.9/382.8/379.8 ms before and 385.3/386.7/392.7 ms after. They are short loops, the
  accounting continues and the indirect call to the same target was already well predicted.
- 16 indirect call sites according to the previous block (so the predictor learns the successors of each one
  separately), same binary with `GOW_VU1N_SITES_OFF`: 399.9/402.5/396.4 ms without them and 424.8/419.2/421.2 ms with
  them (+6 %). The predictor was already right; the extra call layer only adds cost.

- VIF1 UNPACK, second attempt with SSE4.1 (line profile of `processVIF1Data` in combat: 8-bit V4 19.7 %,
  signed 16-bit V2 12.8 %, 16-bit V4 7.9 %, 8-bit V3 7.4 % of its samples). This time it only changes the body of
  those lambdas within the same `unpackAll`, reading exactly the bytes of the vector and with the signed or unsigned extension
  outside the loop. VU1 thread profile in `ATHN01B` at 120 Hz (two alternating runs of each):
  `processVIF1Data` 9.14 and 9.19 % without the change, 9.02 and 9.11 % with it. No difference: that time is memory
  (the ~2.6 MB per frame of source data), not instructions.

With this architecture (one block per function and exact timing in the dispatcher) the dispatch is at its floor.
What remains is reducing the timing machinery itself (so that blocks that do not read input flags
do not need history) or redoing the backend with static per-program flag analysis, like PCSX2's microVU.

### State of combat at 60 and 120 Hz (2026-10-25)

- 60 Hz, ship combat (`ab_traza.sh`, `bin\wsat` = `main` with #147): 2396 frames; period between flips from 13 to
  19 ms (median 16.67) and none above 25 ms, that is, no lost frames. Median VU1+VIF+GS work
  8.9 ms (p90 12.0, max 15.8). The 31 % of periods between 17 and 19 ms is variation around the VBlank, not lost
  frames. VIF1/VU1 note in `docs/estado/datos.toml` updated.
- 120 Hz (`GOW_HZ=120`), tour by zones with `GOW_WARP`: ATHN04B 112.4 on average, SEWR02 118.3, DEST00 117.0
  (game frames per second); ship combat ~75. With the monitor at 120 Hz ~6 fewer images per second than frames are
  shown: temporary counters in `PublishSharedTexture`/`Acquire` (113 publications per second, no
  publication failure nor jump when acquiring) indicate that two frames sometimes fall in the same guest VBlank and the
  screen captures the last one, as the hardware would.
- EE thread in combat at 120 Hz: ~23 % sleeping in `EeScheduler::processDueDeadlines` (VU1 and VBlank
  waits), the game logic in parallel with the VU1 (8.5 ms per frame) and ~1.7 ms per frame in series between the end
  of the work and the next launch.

### Linux: render scale and window GPU (2026-10-31)

Hybrid laptop (Intel + RTX 5050), scripted tour through the ship zones (`ATHN01B;ATHN04B`, `GOW_WARP`), native VU1,
84 samples of 1 s after the first 30 s, fullscreen window. `PS2X_GS_HW_SCALE` sets the GS internal scale in OpenGL.

| Scale | Lines | Game FPS (average) | Minimum | gs_ms / 5 s | upload_ms / 5 s |
|---|---|---|---|---|---|
| 2 (default) | 896 | 56.0 | 44.0 | 1242 | 606 |
| 2.41 | 1080 | 56.0 | 46.0 | 1308 | 766 |
| 3 | 1344 | 55.2 | 43.5 | 1382 | 1043 |
| 4 | 1792 | 53.9 | 39.4 | 1638 | 1694 |

Drawing at exactly 1080 lines costs nothing measurable. Image quality: the author played with all four scales and they all look good, including 4.

**Finding (corrects a previous measurement):** with `__NV_PRIME_RENDER_OFFLOAD=1` and `__GLX_VENDOR_LIBRARY_NAME=nvidia` the log says
`[gs-hw] GL unavailable: OpenGL 4.x core context unavailable (EGL error 12288)` and the runtime silently falls back to the CPU renderer, so
a "window on NVIDIA" comparison was measuring two different renderers (51 versus 56 FPS is not valid). `DRI_PRIME=1` keeps the GS on
OpenGL but did not reduce the upload cost (977 versus 625 ms per 5 s, one run each). With the window on the Intel the OpenGL GS
(on the NVIDIA) returns each image through RAM: `upload_ms` from 600 to 1700 depending on the scale. Real cost of that trip, not measured in isolation.
Always check that the log shows `[gs-hw] render-target renderer ready` before trusting a measurement.

## Waffle565 sync review (2026-11-01)

KIexster's tip (2d3c91d) was already in our tree; Waffle565's repository had newer commits (10-16 and 10-18) we lacked.
Checked against our patched tree by distinctive identifiers:

| Waffle565 commit | Status here |
|---|---|
| `615b046` pooled DMA buffers, no per-packet heap copies | the DMA buffer pool was already ours (KIexster); `deque`→`vector` is MSVC-only; the in-place GIF submit was missing and is now `patches/ps2recomp-gif-inplace.patch` |
| `ecd6cb5` VIF1 UNPACK fast path, native slots invalidated only where micro memory changed | not ported yet (next candidate) |
| `d6de6e6`, `664d93e` MPEG pacing and audio buzz | not ported (movie sync, not FPS) |
| `906b684`, `ba16c8d` language and text disc overlays | not ported (could unblock PAL languages) |
| `c8a2c59` Windows release polish | not needed on Linux |

**In-place GIF submit, measured** (4-zone scripted run `ATHN01B;ATHN04B;SEWR02;DEST00`, 280 s per run, `[gow-fps]` game average
from t=40 s, RTX 5050, same microcode and build tree, runs alternated, `[gs-hw] render-target renderer ready` confirmed in each log):

| | run 1 | run 2 | run 3 | run 4 | mean |
|---|---|---|---|---|---|
| baseline | 56.4 | 57.5 | 58.0 | 58.1 | 57.5 |
| in-place submit | 57.6 | 58.3 | 58.8 | 58.3 | 58.3 |

The patched build is ahead in all four pairs, by +0.75 FPS on average (about 1%). Run-to-run spread is about 1.5 FPS, so this is
small and not statistically conclusive with four runs; it is kept because the change removes a copy per XGKICK, is covered by a
test and has no downside seen. The first run of a series also pays a cold-cache cost.

## Grid lines in the desert haze (2026-11-01)

**Symptom.** Thin orange vertical and horizontal hairlines in the far sand and sky of `DEST00` (also seen in the last playtest).
Reproduced muted (`GOW_AUDIO=0`) with the scripted warp (`GOW_PAD_TEST=1 GOW_WARP=DEST00`) and the presented-frame captures.

**Narrowing.** Absent at render scale 1, present at 2 and 3, so the GL render-target backend adds them. Not the haze triangle fans
or the textured haze (skipping them with `GOW_GS_HW_SKIPVERTS` / `GOW_GS_HW_SKIPTBP` left the lines), not sliver triangles (a cull
removed about 4 million triangles and the lines stayed). Per-draw render-target dumps (`GOW_GS_HW_RTDUMPAT`, `RTDUMPRANGE`) show
the scene target clean, then lines after the game's full-screen glow/haze passes: 16 sprites of 32 px at x = 32k + 0.25 that copy
the screen onto itself with alpha. The observed lines sit on those seams (host x about 385 and 510 = 2 * 192.25 and 2 * 256.25).
`GOW_GS_HW_SEAMMODE=1` (never open seams) removed them; opening every clamp did not.

**Cause and fix.** `openSharedSide` leaves the clamp open on the side two consecutive strips share, so a picture drawn as strips
continues across the seam. For a pass whose texture is a render target (a 1:1 copy at the internal scale) that left the seam
columns different from their neighbours. `patches/ps2recomp-gs-seam-targets.patch` skips the opening when the sprite's `TBP0`
equals a render target's `FBP * 32`. `GOW_GS_HW_SEAMFEEDBACK=1` restores the old behaviour.

**Verified.** Capture comparison in `DEST00` at scale 2: the sky and sand lines are gone; `SEWR02` and `ATHN04B` look unchanged.
**Not verified:** scale 3, menu and logo screens, a real fullscreen 1080p view; no unit test (the backend needs a GL context).
A faint horizontal hairline across the dark ground at the shadow edge predates the fix and is still open.

**Update: remaining horizontal hairlines (not fixed).** At scale 2 and 3 a few very faint horizontal lines remain, in the sand
(three at scale 3) and across the dark ground at the shadow edge (two, about 6 host pixels apart, host y 654 and 660 at scale 2,
x about 640 to 950). They are absent at scale 1. They do **not** change with `GOW_GS_HW_SEAMMODE=1` or `2`, nor when the haze
fans (`GOW_GS_HW_SKIPVERTS=1488,1560,1752`) or the textured haze (`GOW_GS_HW_SKIPTBP=36f0`) are skipped, so they are not the strip
seams, those fans or that texture. Per-draw render-target dumps were stale across batches in this build and could not isolate the
draw. Next: bisect by draw signature with a vertex dump of the full-screen and shadow passes. Also checked with the fix: scale 3 has
no vertical lines, menu and logo screens are visually unchanged (flame animation aside).

### Grid lines through the whole game: what is ruled out (2026-11-02)

Report: faint grid lines in every zone, a "plane that follows the character", clearly visible in fog, at night and with
particles / sword glow. Reproduced without playing: `GOW_PAD_GUION='8:x,16:x,24:x,32:x,40:x,48:x'` with `GOW_PAD_TEST=1
GOW_PAD_SOLO_GUION=1 GOW_SKIP_FMV=1` reaches the rainy deck fight (steady scene after ~35 s). Window grabs
(`import -window`) are lossless; `GOW_GS_HW_DISPDUMP=<n>` dumps the internal render target.

Measured: the lines are already in the internal render target (not the window scaling). In the dump (scale 4, 512x447)
the column / row energy has a periodic peak at a 128 px pitch = 32 game px: columns at x = 128k + (127..3), rows at
y = 128k + (4..5), i.e. on the 32 px tile borders of the post passes (tiles at x = 32k + 0.25). Score = max residue of
the mean second difference over the median, about 1.6-1.9 for columns and 2.0-2.3 for rows in the deck scene.

Ruled out (peak unchanged, ~1.8): `GOW_GS_HW_SEAMMODE=1`, the render-target and depth-target seam rules (PR 34 fixed only the
desert haze; PR 35 closed), `GOW_GS_HW_SKIPTBP` of the post-pass sources 0xD00 / 0x1A00 / 0x2800, the window scaling,
render scale 1 vs 2, and dropping the UV clamp of every sprite that samples a render target (the band only moves a few
pixels: columns 2/127 -> 125/126). Next: dump the vertex data (positions, UVs, alpha, blend) of the strip draws by
signature and look for a per-tile offset or an overlap/gap at the borders; check the blend of the alpha-76 passes.

Vertex dumps of the post passes (`GOW_GS_HW_VERTDUMPSIG=<verts>:<fbp>:<tme>:<tbp hex>:<seconds>:<count>`, deck scene, scale 4):

- Fog/DOF pass: 16 pairs of draws into fbp 320 (256 px wide). The textured ones are two 32 px sprites each (x = 0.125..32.125 and
  32.125..64.125 in game px at scale 4, `u` = 0.5..32.5 and 32.5..64.5), reading the Z buffer (tbp `d00`, PSMCT24) 64 columns
  further right on every draw; each sprite's UV clamp is `[first sample, last sample]` = `0.5..31.5` / `32.5..63.5`.
  At scale 4 the last two host pixels of every 32 px tile have `u` = 32.0 and 32.25, are clamped to 31.5 and so read Z texel 31
  instead of texel 32: a 2 host-pixel band at every tile border in a map whose value (depth) drives the fog. That fits "worse in
  fog, at the 32 px tile borders". The unclamped read (`GOW_GS_HW_NOCLAMPRT=1`, experiment only) moves the band
  (columns 125/126 instead of 2/127) but does not remove the periodic peak: more than one pass contributes.
- Copy passes: 16 strips of 32 px each (fbp 208 and fbp 0 both sample tbp 0, the main buffer, as a 1:1 copy with colour 128;
  clamps `0..31`, `32..63`, ...).

Next: find which of the remaining passes still produces a peak with the clamp dropped (dump fbp 320 and 208 per pass and score each),
then fix the sampling in `reinterpretTexel` / the clamp range for the Z read.
