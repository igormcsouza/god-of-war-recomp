# Memory card (2026-10-07)

## Status

With a copy of a PCSX2 card (`Mcd001.ps2`, 8 MB with ECC) that holds a God of War save:

- the **Load** menu lists the saves with their thumbnail, zone, date, difficulty and time;
- **loading** the save ends in "Load Complete" and the game appears at the save point on the
  Athens docks;
- **saving** at the altar ("Zeus has given you the opportunity...", overwrite) ends in "Save
  Complete"; the card's file system remains valid and the port loads the
  saved game again (with the new play time).

The card is chosen with `GOW_MC0=<path>` (by default `Mcd001.ps2` next to the ELF). To test without
risk it is best to use a copy: the game writes to the file.

## Fixed bugs (`patches/ps2recomp-memcard.patch`)

God of War uses `MC2_D.IRX` on top of `DBCMAN.IRX`/`SIO2D.IRX`: the EE's libmc2 sends each command with
`sceDbcSendData3` (RPC to dbcman's server `0x8000131c`), mc2_d runs it with SIO2 transfers
and replies to the EE with DMA. Previously the game said "No MEMORY CARD found in MEMORY CARD Slot 1". There were
four bugs in the IOP emulator:

1. **`sceSifSetDmaIntr` (sifman 32) did nothing.** dbcman replies to the EE with that function and waits for its
   end-of-DMA callback (which releases a semaphore) before sending the next reply. It now copies
   like `sceSifSetDma` and schedules `func(data)` as an interrupt callback. smpd also
   uses it: its callbacks now run (sound and videos keep working).
2. **`WaitEventFlag` without a current thread failed immediately** (`KE_EVF_COND`). mc2_d performs the SIO2
   transfers from dbcman's RPC server, and sio2man waits for the end of each one with `WaitEventFlag`:
   it read the reply before it arrived (`GetSpecs` failed). Now, like `WaitSema`
   (`ps2recomp-iop-sound.patch`), the other IOP threads run until the condition is met.
3. **Consecutive LWL/LWR on the same register.** On the R3000 the second one combines with the value still
   in the load delay slot of the first; the interpreter used the previous value. mc2_d
   copies the card specifications (page, block and card size) this way, and they reached
   the EE as garbage.
4. **The IOP `sceCdReadClock` (cdvdman 24) did not exist.** mc2_d uses it for the saves' date
   ("??? 95, 2000 12:00:00"). It now returns the time in BCD and, like the PS2 clock, in
   Japan time (UTC+9): the game subtracts 9 hours and adds the time zone from the system configuration, which
   the runtime takes from the host, so the save shows local time. (The runtime's EE `sceCdReadClock`
   returns local time; God of War does not use it for saves.)

New regression tests in `ps2xTest/src/ps2_iop_tests.cpp` (one per bug); the suite passes
**555/555**.

## How it was tested

`GOW_PAD_GUION` (see [scripted pad](controls-and-menu-tests.md)) drives the menu without a controller. With
`GOW_SKIP_FMV=1`, load and save in the same run:

```sh
GOW_MC0=/path/to/copy_of_Mcd001.ps2 GOW_SKIP_FMV=1 GOW_PAD_TEST=1 \
GOW_PAD_GUION='5:start,13:abajo,20:x,62:x,75:x,90:x,230:r2,250:x,270:x,295:arriba,310:x' \
python3 tools/linux/gow_launcher.py --no-gui
```

The timings depend on the machine's speed. Still to be checked: creating a save on an empty card (formatting).
