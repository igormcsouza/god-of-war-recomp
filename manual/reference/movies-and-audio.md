# FMV and audio (2026-10-07)

## FMV

Without `GOW_SKIP_FMV`, the game stayed in state 4 (`movie=10`) waiting in
`sceMpegGetPicture`: the decoder received valid PSS data (`00 00 01 BA`) but produced no
frames. God of War demultiplexes the first block of the video (which carries the MPEG-2
sequence header, `00 00 01 B3`) **before** calling `sceMpegCreate`, and the runtime
implementation reset the playback state there. Since the video does not repeat the header, the decoder
waited for one that never arrived.

`patches/ps2recomp-mpeg-create.patch` keeps the already-demultiplexed input of the stream in progress when
the decoder is created (if no picture has been served yet and the stream has not ended). The
regression `sceMpegCreate keeps a sequence header demuxed before it` fails without the change; the suite passes
**548/548**. In the game, without `GOW_SKIP_FMV`, the intro video (Kratos on the cliff) is
decoded and presented.

Separately: the inherited `sceMpegCreate`/`sceMpegReset` implementation writes to fixed addresses
(`0x1717BC`, `0x171800`..., `0x171904`) that belong to another game. In SCUS-97399 they fall in code,
so they do not seem to affect the recompiled program, but they should be removed.

## Audio

`patches/ps2recomp-audio-pcm.patch` adds `GOW_AUDIO_PCM=<file>`: it saves the emulated SPU2 samples
(s16le, stereo, 48 kHz) without the padding silences, to check the audio even when the
emulation runs slower than real time.

Before the fixes below, in 23 s of emulated audio (menu, intro and gameplay) the output was
absolute silence: no sound bank ever reached SPU2 RAM.

`patches/ps2recomp-iop-sound.patch` fixes two bugs in the IOP emulator:

1. **`sceSifGetOtherData` (sifcmd, ordinal 23) copied nothing.** smpd and 989snd use it to fetch
   from EE RAM the banks the game already has loaded (`GENERAL`, `Title01`, `AthnA01`,
   `SKS_Skel1`..., `SMPD` command of type `0xD`). It now copies `size` bytes from the EE to IOP RAM and
   fills in the `SifRpcReceiveData_t` (source, destination and size from `+0x10`). With this, the
   first seconds (the menu sound) play.
2. **`WaitSema` without a current thread faked success.** RPC servers run as standalone calls
   (without a thread), and if the semaphore was at zero it returned 0 without taking it. 989snd protects its tick with a
   lock (`gLockMasterTick`, semaphore and owner = `GetThreadId()`): the RPC server "took" it
   while the tick thread held it, thread 0 was left as the owner and the tick could no longer release it
   (error `0x7B`). From then on the IOP printed `Sound System Tick locked out for 2 seconds` every 2 s and
   the sound stopped. Now, without a current thread, `WaitSema` lets the other IOP threads run until
   the semaphore is released (at most ~1 s of IOP clock; if it times out it returns `KE_SEMA_ZERO`).

Result with `GOW_SKIP_FMV=1` and 240 s of execution: 19.7 s of emulated audio with continuous sound
(previously 5 s of sound and then silence) and no blocked-tick warnings. New regressions in
`ps2xTest/src/ps2_iop_tests.cpp`: `WaitSema outside a thread waits for the semaphore instead of
faking success` and `sceSifGetOtherData copies EE memory into IOP RAM`; the suite passes **550/550**
(run from `ps2xTest`, which is where the VU0 test finds `instructions.h`).

The audio follows the emulated clock: with gameplay at ~2 fps it sounds choppy. It will reach real time
when VU1 stops being the bottleneck (see `performance-research.md`).
