# Diagnosis of the transition with shared presentation

Current status, 2026-10-12: #51 merged at
`05421940617e5ce69889600d9eb727b3c36c0b3b` after its validation and the CI of the final HEAD.
The later chain 102 includes the EE PMULTH fix from #67: full native
build, 602/602 normal, 638/638 GPU and four correct contracts.
The first synchronous/shared control without threads completes five minutes; its
16 acquired introduction images are favourable, within the limits
described in research-log.md. The asynchronous combination with threads and the broad
animation/NPC control are still pending; not all failures are declared resolved.

The independent PCSX2 adaptation from #68 is connected as an optional mirror
in chain 103. Two six-minute shared controls verify reception
of GIF/VSync and introduction/NPC outputs; the asynchronous one shows the HUD. It keeps
the usual renderer and uses generic DMA paths, without VU1/GS-front threads. It does not
certify animation, scene parity, performance or prolonged stability.
The four-variant seven-minute matrix of e5e040e completes,
but its mirror used the inverted field with respect to MTGS. Fixed in 89ffb57, with
a client/queue/DLL regression and two additional complete shared controls.
Introduction favourable within its window; with HUD/NPCs OpenGL shows much more
fog than DX11. No visual equivalence is validated. See pcsx2-gs.md and the
latest entries of research-log.md for identity, quantities and limits.
The historical results below keep the identity of their chains.

Count #59 and framebuffer units #58 are merged into main. The isolated
four-control matrix of 98 and the three six-minute passes
of 99 are kept; they do not vouch for the new SMODE2 field of 100. The aligned visual
comparison, the framing and prolonged stability remain open. The sections
below keep the results and the limitations of each executable.

The old frame alternating with asynchronous FINISH and the incorrect framing already
present before the final framebuffer copy require separate controls.
This diagnosis observes the texture that the host acquires; it does not reconstruct a
later VRAM capture as if it were that same image.

## Optional logging

Before starting the game, enable `PS2X_GS_PRESENT_DIAG=1` together with
`PS2X_GS_DIRECT_PRESENT=1`, the OpenGL renderer and `PS2X_FRAME_HASH=1`.
The existing hash is computed on the GPU; the diagnostic does not force readback,
`glFinish` or an additional acquisition. The hash and the logging have a cost:
this run is a functional control, not a performance measurement.

`[gs-present:shared]` logs only acquisitions of new sequences,
up to 4,096 per host instance. It keeps the published sequence, the render
sequence, the image and host ticks, framebuffer/source, dimensions,
hash and validity, and blank state. The host tick can advance while
it retains the same texture. The ticks do not vouch for alignment with PCSX2 or
with a matrix observed at another moment of the game.

The 2026-10-11 extension adds `preferred=0/1`, taken from the
`usedPreferred` of that same acquired texture. On the shared GPU path,
`displayFbp` is in pages of 8,192 bytes; `sourceFbp` is in those pages
with `preferred=0`, or in 256-byte TEX0 blocks with `preferred=1`.
Comparing both raw numbers does not vouch for address equality.
The indicator adds no readback, acquisition or synchronization.

For the automatic sequence, use `GOW_PAD_TEST=1` and
`GOW_PAD_TEST_NO_CAPTURE=1`: it keeps the pad and the status logs without
introducing the periodic captures that force readback. Keep GS replay capture
and the camera/model probes disabled during this control.

```powershell
python tools/render/inspect_shared_frames.py logs/control_compartido_err.log
```

The inspector reports sequence regressions, content changes associated
with a repeated sequence, and A–B–A hash returns with increasing sequences.
It discards pattern continuity when the hash is missing, the
dimensions change or the host mode changes. It rejects truncated or
interleaved logs and files without samples. A hash return can correspond
to legitimate animation or to a collision: it does not prove pixel equality,
corruption or FPS. The absence of patterns only covers the captured samples.

## Control still to be performed

Use the same binary, ELF, ISO and pad sequence for synchronous and
asynchronous FINISH, with RAM/shared presentation. Keep the new VU1/GS-front
threads off when isolating this problem; check them in a later run.
Relate the game state to the log without assuming that captures
with readback preserve the timing of the shared path. If the sequences
advance but old content returns, follow the GS framebuffer; if the sequences
go backwards, follow the host's selection/synchronization.

Tests without the game: texture retention, change under the same sequence,
regression and mode change, hash return, unknown hash, different
dimensions and rejection of corrupt logs. Six Python tests pass.
The patch applies in check mode on the own runtime; full build
with the new chain and game playback pending. The transition is not declared
fixed and no performance options are enabled by default.

FPS measurements must wait until the shared PC is free of
builds and of other runs of the game.

## Integration of #55 and light controls (2026-10-10)

`main` is integrated at `7800bc27c27ab5ddb0dd19338b834e0e2eff3829`, by
merge. The two insertion conflicts in `scripts/compilar.ps1` are resolved
by keeping event-driven PATH1, lazy decoding and GIF buffers, followed
by the host diagnostic. The chain contains 90 unique patches.

Local controls of this integration, without building or running the game:

- The six Python tests of the inspector pass with Python 3.14.7.
- Configuration: 0 errors and the 4 existing warnings.
- PowerShell syntax: 20 scripts, 0 errors; includes the private controls.
- The 90 patches pass `git apply --check --ignore-whitespace` and are applied
  in order in a new private worktree on
  `c5a9d02573410a2085a4b4b831b0b68ba3515440`.
- The diff of the existing runtime sources matches before and after the
  control. Its executable is not rebuilt and does not vouch for the integrated changes.

The PC remains reserved for Opus's measurements. The full Windows build
and the functional control are still pending; #51 remains a draft.
The patch check does not replace the build, the native suite or the
verification of the acquired images.

## Matrix for the next functional control

Once the user confirms that the PC is available, build the full chain
with a private `GOW_WORK` and record the commit and SHA-256 of the executable.
Prepare a private run folder and an independent copy of the
same initial card for each pass; set `GOW_MC0` to that copy and
`GOW_MC1=0`. Do not write over the original card.

| Pass | `GOW_GS_FINISH_ASINCRONO` | `PS2X_GS_DIRECT_PRESENT` |
|---|---|---|
| Synchronous FINISH, RAM | `0` | `0` |
| Synchronous FINISH, shared | `0` | `1` |
| Asynchronous FINISH, RAM | `1` | `0` |
| Asynchronous FINISH, shared | `1` | `1` |

Explicitly set `PS2X_VU1_HILO=0` and `PS2X_GS_FRENTE=0` in all four
passes. Keep the same binary, ELF, ISO, scene and pad script, with
`PS2X_GS_GPU=1`, `PS2X_GS_PRESENT_DIAG=1`, `PS2X_FRAME_HASH=1`,
`GOW_PAD_TEST=1`, `GOW_PAD_TEST_NO_CAPTURE=1`, `GOW_FAST_BOOT=0` and
`GOW_SKIP_FMV=1`. Disable other diagnostics, GS replay and automatic captures
before starting. Check the sequence of states and the VU1/GIF errors before
interpreting the differences. None of these passes measures FPS.

Analyse the shared logs with the inspector and keep the investigation of
the framing inside the GS framebuffer separate. Then evaluate
the VU1 and GS-front threads, separately, if the initial control is stable.

## Metadata of reappearing sequences (2026-10-10)

A synthetic `1 → 2 → 1` control with different metadata on the second
appearance of `1` showed an omission: the inspector reported the regression,
but only compared metadata of consecutively repeated sequences.
It now keeps the first metadata of each sequence until a host
mode change; it excludes `hostTick`, which can advance. An inconsistent row
breaks continuity and does not start a new content-return pattern.

Eight Python tests pass. The new regression fails with the previous version
in four cases: hash, hash validity, dimensions and render sequence.
It is also checked that advancing the host tick is valid and that a mode
change allows the numbering to restart with other metadata. These are
procedural inputs, with no game data. This change to the inspector does not prove that the
runtime produces such inconsistencies nor does it fix the game's presentation.

## Build and first Windows matrix (2026-10-10)

With the PC freed by the user, `scripts\2_compilar.cmd` completes with code 0
in the private runtime `GOW_WORK=E:\gowgpuprof`, keeping its previous sources
in a snapshot and verifying the junction's target. Port code:
`76a25bedac7842e0a35cbd5eb56ca5941ebae429`, 90 patches, Release, VU1 interpreter.
SHA-256 of the new executable:
`36e632cd39dfd73e3de3573c38b8c87715f9ef65b1eb6b2bba3ef776ed457c9f`.
Opus's checkout is not modified. The Windows suite passes 591/591 in normal mode
and 625/625 with real GPU; libpad2 also passes. The GPU run of the diagnostic
logs six procedural acquisitions, with no anomalies detected.

The four passes use that binary, the same ELF/ISO and pad script,
initially identical private cards and the variables of the previous matrix.
Other optional diagnostics are removed; there is no replay or periodic captures.
`GOW_FAST_BOOT=0` keeps the wrappers installed by presence, without enabling
the shortcut. The debug panel is expanded in the four passes.

| FINISH / presentation | Actual duration | First state 11 of the script | Acquisitions | A–B–A returns | Greatest host/frame tick distance |
|---|---|---|---|---|---|
| Synchronous / RAM | 360.06 s | 146.64 s | — | — | — |
| Synchronous / shared | 360.04 s | 121.16 s | 2,186 | 105 | 3 |
| Asynchronous / RAM | 360.05 s | 116.32 s | — | — | — |
| Asynchronous / shared | 233.22 s | 111.31 s | 1,247 | 109 | 417 |

The three complete passes are terminated at the limit; the user asks to recover the
PC during the fourth and only our identified process is terminated.
It is not a spontaneous shutdown nor a complete 360 s control. The last reports
of the four keep state 11; the sought signatures of
VU1/GIF error/exception are not found and no card changes. This does not prove playability,
visual equivalence, normal shutdown or prolonged stability.

The shared logs show no sequence/render regressions,
unknown hashes or inconsistent metadata. All A–B–A returns
appear before the first state 3 report. They do not appear after the first
state 11 report: 1,094 synchronous samples and 342 asynchronous ones. Classifying
by the last state report only delimits approximate stretches. Since the
runtime logs only new acquisitions, zero retained rows does not
mean zero retentions in the run.

Asynchronous sequence 906 has `hostTick=1365`, `frameTick=948` and distance
417; later acquisitions return to nearby ticks. It is a lead for
following host waits and pending GS work, without assuming slot corruption,
pixel equivalence or sustained delay. A tick distance does not
turn this run with diagnostics into an FPS measurement.

The visual review remains incomplete: an external RAM capture lets us see
HUD/scene/Kratos, but the panel covers much of the image. `copyLatchedHostPresentationFrame`
is not used as proof of the shared texture.
Resume with separate visual controls and the panel collapsed, repeat the
asynchronous combination and then evaluate VU1/GS front separately. Keep the
framing inside the framebuffer as an independent investigation.

The user reserves the computer again. #51 remains a draft until the
functional control is completed and the CI of the final HEAD is checked. The game
data, logs and captures remain private; this description of the
results and their limits is published.

## Chain update (2026-10-11)

`main` is integrated with #56/#57 by merge, keeping the six new
VU1 patches before the GS diagnostic. The 96 unique patches pass check
and application in a clean private worktree. Configuration: 0 errors,
4 existing warnings; syntax of 21 PowerShell scripts: 0 errors.

The executable and the four previous passes correspond to 90 patches,
not to this integration. Rebuild completely with the private workspace
when the user confirms that the PC is available and record the new
commit/hash before repeating the control. Do not carry the previous native results
over to the new VU1 code or to the threads that were not tested.

The inspector adds `tick_distance` to obtain directly the signed
host/image distance and the metadata of its maximum. Eleven tests pass;
the three new ones fail with the previous version. It includes consistent
retained rows and unknown hash, excludes contradictory metadata and allows a
negative distance when the request reads the counter after the host.
The summary reproduces the 3/417 maxima in the previous logs without
running the game. It does not demonstrate sustained latency or old content.

## Reproducible launcher and host window (2026-10-11)

`tools/render/run_transition_control.py` prepares a new folder per pass,
checks the executable and ELF against a build manifest and copies the
ELF/IOP to that private folder. The ISO is consumed from its origin. Each pass
creates the same unformatted procedural card or copies the one given with
`--initial-card`; it never uses the original file as a writable card.
It rejects existing folders and output inside the source modules to
avoid a recursive copy. It does not copy or publish the executable or the data to Git.

The output must be outside this checkout or inside `logs/`. The launcher
resolves the path and rejects other repository folders before writing
the pass, keeping card copies and results under the private area.

The JSON manifest requires the full `commit`, `exe_sha256` and `elf_sha256`.
Record these data **after checking that the build finished**,
using the commit of that build, not another later HEAD. It is recommended
to also keep the patch chain, VU1 mode and private build log.
The ELF hash must match SCUS_973.99. The manifest verifies
the identity of the binary; by itself it is not proof of a correct build.

Example for a **new 96-patch build**, when the PC is free
and the corresponding private manifest has been created:

```powershell
$controlArgs = @(
    '--runner', 'E:\gowgpuprof\PS2Recomp\out\build\ps2xRuntime\ps2EntryRunner.exe',
    '--elf', 'E:\gowgpuprof\SCUS_973.99',
    '--iso', 'E:\gowport\God of War.iso',
    '--iop-mod', 'E:\gowgpuprof\IOP_MOD',
    '--build-manifest', 'E:\gowgpuprof\transition96\build.json',
    '--output-root', 'E:\gowgpuprof\transition96',
    '--seconds', '360',
    '--collapsed-ui'
)
python tools/render/run_transition_control.py sync_ram @controlArgs
python tools/render/run_transition_control.py sync_shared @controlArgs
python tools/render/run_transition_control.py async_ram @controlArgs
python tools/render/run_transition_control.py async_shared @controlArgs
```

Do not run those paths on the old binary as if it incorporated the new
chain. Use `--label` for a repetition in a different folder. Keep the same
panel option in the four passes. The launcher removes all inherited
`GOW_*`/`PS2X_*` variables and sets the matrix; it enables `GOW_PAD_SOLO_GUION=1`
(added in #56) to ignore physical inputs. It does not enable readback, replay or
captures. The threads are initially off; the arguments
`--vu1-thread 1` / `--gs-front 1` allow separate later controls.
The GS front requires VU1 on a thread.

`window_state.jsonl` records changes of the state queried every second:
visible window of the own PID, minimization and whether the foreground belongs
to that PID. It does not read titles of other applications, activate windows or capture
images. Win32 visibility does not guarantee that the window is uncovered,
and losing focus does not imply being minimized:
[IsWindowVisible](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-iswindowvisible),
[IsIconic](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-isiconic).
Window not found means unknown minimization state; the
sampling interval may miss changes shorter than one second.

The raylib version of the built runtime
[`c1ab645`](https://github.com/raysan5/raylib/blob/c1ab645ca298a2801097931d1079b10ff7eb9df8/src/platforms/rcore_desktop_glfw.c#L1258)
waits for events while minimized without `FLAG_WINDOW_ALWAYS_RUN`.
The runtime configures only `FLAG_WINDOW_RESIZABLE`, while the EE runs
on another thread. That host pause is a possible explanation of an image
with an old tick when the window is restored. No minimization was recorded in the
previous passes: losing the foreground does not demonstrate that it happened and
does not allow attributing the 417 ticks to it or considering the alternation resolved.

Creating the `STOP` file inside the pass folder or pressing Ctrl+C
stops only the process started by the launcher. `result.json`
distinguishes limit, stop request, interruption and spontaneous exit;
it keeps the exit code, time and card hashes. A shutdown by limit
or by the user is not proof of a crash or of a normal shutdown of the game.

Twelve local Windows tests pass, including a run of Python as a
procedural child that terminates without game or window. The other eleven test
environment, matrix, window ownership, card copying, rejections before
writing and stopping the child. The control is added to CI; the full Win32
rehearsal is skipped on Linux. The real Win32 query is also checked on
our Python process without a window. This validates the tool, not the scene.
Its new matrix with the game and the 96-patch chain is still pending.

The manifest hashes accept upper and lower case, including the
usual output of `Get-FileHash`; they reject values that are not 64 hexadecimal digits.
A regression checks that an equivalent uppercase manifest is accepted
without relaxing the comparison of the executable or the ELF.

## Units of the acquired source (2026-10-11)

The initial diagnostic omitted `usedPreferred`, although the renderer and
the shared slots already kept it. It is now logged as `preferred`.
This distinguishes the units of the selected source; it does not change which source
the renderer chooses, the texture contents or the CPU renderer.

The inspector accepts both the eleven old fields and the twelve new ones.
`source_units` counts consistent rows in `unknown`, `pages_8192` and
`blocks_256`, including logged retentions. An old row does not allow
deducing the units by numeric equality between framebuffer and source.
The maxima and A–B–A returns keep `preferred` when it is present.
Contradicting a known flag under the same sequence is an inconsistency;
omitting it in an old row does not erase the previously known value.
It rejects flags outside 0/1, unknown additional fields and duplicates.

Fifteen Python tests pass. Three regressions fail with the inspector of
`60ce933`: known/unknown units, metadata preservation across
formats and source evidence in a hash return. The 96 patches are
checked and applied in a new private worktree on the pinned upstream.
The review of the two old Windows logs reproduces the 3/417 maxima
and classifies their 2,186/1,247 rows as unknown units.

The CI of `60ce9338f9c27d312a474cab40498f1cf6fdcdd7` finished correctly
before this extension. It does not validate its new format: check the CI of the
final HEAD and rebuild completely on Windows before running the game.
There is no native build or visual control of `preferred` yet;
#51 remains a draft. The source selection and the framing remain pending.

## Dimension changes in the summary (2026-10-11)

Until now a size change interrupted the A–B–A pattern, but was not
identified in the JSON. `dimension_changes` reports line, sequence/render
and previous/new size for consistent rows, even without a valid hash.
It excludes contradictory metadata of a single sequence and resets the
reference when the host mode changes.

Seventeen Python tests pass; the two new ones fail with `715e216`.
The two private 90-patch Windows logs show a single change,
from 1×1 to 512×448 at sequence 2, at the start. No other change is observed in
the logged samples; this does not verify the appearance or framing of the scene.

The CI of `715e216fa72cec85e4112eb20b3fdcbba090a910` passes both controls
([run 38114877209](https://github.com/KIexster/god-of-war-recomp/actions/runs/38114877209)).
It builds the `preferred` extension and validates the integrated chain without the game.
The Windows build and the functional check of the current code are still
pending. This adjustment to the Python summary does not change the runtime patch.

## Private control directory (2026-10-11)

The same directory criterion as for the PCSX2 reference is applied to the launcher:
outside the checkout or inside `logs/`. Thirteen Windows tests pass;
the new one checks rejection before any write and acceptance of
`logs/` or an external directory. It fails with the launcher of `2930666`;
the negative control intercepts `mkdir` to prevent creating that output.
Only a procedural Python child is run, without game or local build.

The CI of `2930666cddd7d907a6576b2410ebed1a8695a61c` had passed both
controls before this adjustment. Check the CI of the final HEAD. The tool
keeps an explicit manifest and private cards; it does not alter the runtime.

The source investigation produces the independent
[PR #58](https://github.com/KIexster/god-of-war-recomp/pull/58):
it normalizes three comparisons of FRAME/DISPFB pages versus TEX0 blocks.
Its negative control `5f3d7de` compiles and fails only the two new regressions;
the fix `e52527d` passes 593/593 and full CI. Both rehearsals are remote,
without the game. The Windows GPU control and the real scene are still pending;
it does not demonstrate the cause of the alternation or camera. Both PRs remain drafts.

## Windows 96-patch reference and next integration (2026-10-11)

The user frees the PC. Full build finished with code 0 in 886.33 s:
`de5a89ad437c952a6ae384025ed602e4e62a9c1b`, Release, VU1 interpreter, three tasks.
Runner SHA-256: `e5aae46440de86b0eeb97da91f742330ce0e95d22bbf70b368e83c44f082f0bd`.
591/591 normal Windows tests and libpad2 pass. Copy of the executable, DLLs,
manifest and log in the private folder `E:\gowgpuprof\transition96`.
GPU and the new matrix are still pending; the #58 fix is not attributed to this binary.

The branch then integrates #58 by merge and moves to 97 patches, with a source
fix before the host diagnostic. It requires a second full build
and a different manifest to compare against the previous reference. The
results will be published with the commit/hash of each binary, keeping
the two visual problems and the unlogged retentions as open limits.

## Full 96-patch reference matrix (2026-10-11)

Binary `de5a89a` and SHA-256 `e5aae46440de86b0eeb97da91f742330ce0e95d22bbf70b368e83c44f082f0bd`,
without the #58 fix. Same exclusive inputs, private procedural cards,
collapsed panel, hash/diagnostic active, VU1/GS front off:

| FINISH / presentation | Actual duration | First report 11 | Last pad state | Acquisitions | A–B–A returns | Maximum tick distance |
|---|---|---|---|---|---|---|
| Synchronous / RAM | 360.06 s | 149.78 s | 11 | — | — | — |
| Synchronous / shared | 360.05 s | not logged | 4 at 25.36 s | 4,096 (quota) | 3,895 | 3 |
| Asynchronous / RAM | 360.05 s | 116.44 s | 11 | — | — | — |
| Asynchronous / shared | 360.04 s | 116.39 s | 11 | 2,310 | 113 | 3 |

All four end deliberately at the limit, with process code 1 and
launcher 0. Cards intact, none of the sought error signatures. The
synchronous shared pass stops reporting the pad in state 4 and does not log
entry into gameplay; host responsive and ticks/acquisitions continue until
the quota at ~116 real seconds. Its state 4 stretch contains two alternating hashes,
possibly static-image fields: it does not prove corruption. Only
our PID is sampled after several minutes of waiting, 5 s with a
brief thread suspension; without PDB, it does not identify a function or measure performance.

The asynchronous shared pass has zero sequence/render regressions, contradictory
metadata and unknown hashes. Its 113 returns occur before the
first state 3; none in the 1,205 acquisitions of the stretch of the last
report 11. Classification by reports spaced ~5 s apart: it does not align frames.
Both shared passes use `preferred=0` in all rows and change 1×1 → 512×448
only at the start. In them, the selection corrected by #58 is not observed nor
is the old 417-tick distance reproduced; that does not prove a global solution.

Windows visible, never observed minimized. Only synchronous/RAM gains
foreground and allows two private external captures; the others have no valid
visual review in this control. Therefore camera equivalence, absence of visible
alternation, playability and prolonged stability are not declared.
The internal framing failure remains separate.

The full build of the 97 integrated patches is prepared, with private
symbols to locate the wait if it repeats. Keep Release optimized:
`CMAKE_CXX_FLAGS_RELEASE=/O2 /Ob2 /DNDEBUG /Zi` and
`CMAKE_EXE_LINKER_FLAGS_RELEASE=/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`.
Record these settings in the manifest; that build is not a benchmark
nor the same reference binary. Do not publish PDB or game code/data.

## Build and integrated procedural controls (2026-10-11)

Full chain of 97, code `f51cc2cb7ee981c1cb6419926d46acc217de1f86`,
finished with code 0. Runner SHA-256
`ba80364535c22d728058ad98bf8182937f36c2db9ada5a11063f684c1a57add0`.
Release/VU1 interpreter/three tasks, with the optimized flags and private
symbols indicated above. Manifest and frozen copy in `transition97`.
Approximate log duration: 902 s; the manifest is recovered after an
error of the post-build helper, explained in `research-log.md`.

593/593 normal and 627/627 real GPU pass on Windows. The
`gow_gs_finish_async_test default|async` controls pass both contracts separately.
The new `gow_gs_shared_finish_test default|async` acquires and downloads
16 new textures in each mode; it compares all their rows and metadata with
CPU, checks an independent known pixel, alternates preferred/CRTC source
and changes 64×64 → 64×96 when reusing the eight slots. It requires real GPU and sharing;
it admits no fallback nor a retained sequence as validation.

The first rehearsal with height 48 was not comparable with the CPU, which considers
dimensions smaller than 64 invalid. Its failure is kept and the control
is corrected, without touching the reference. This target needs Windows/WGL and
does not run in Linux CI; it does not replace the game matrix nor prove the absence
of old images, correct camera or prolonged stability. Nor does it
add readback to the host diagnostic or compute FPS.

## Runner with COP0.Count per cycles (2026-10-11)

Full chain of 98: code `f36936e067aa283e4567e3b16700cfe4e546b629`,
898.79 s, exit 0, VU1 interpreter/three tasks and private symbols.
SHA-256 of the frozen runner:
`4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`.
CI passes 597/597. The Count reads of the EE loop have been regenerated;
the 97 runner does not contain that fix.

Repeat first synchronous/shared, which waited after state 4 in the two
previous chains, and then asynchronous/shared. Keep script,
initial card, threads off and protocol diagnostics. Only one
game at a time and no build; also record minimization and captures.
The native suite and both FINISH controls must complete first. Do not carry
the CI/build success over to the transition, camera, game pixels or FPS.

## Full isolated matrix with Count (2026-10-11)

Same 98 runner, code `f36936e067aa283e4567e3b16700cfe4e546b629`,
SHA-256 `4693c62c14919c5bd400aa55b8da50a0ab5f5d281d3d20e7b02624aeaa5c6663`.
Exclusive script, equal private procedural cards, VU1 interpreter,
VU1/GS-front threads off and protocol hash/diagnostic. No
simultaneous build, other game or emulator during these four passes.

| FINISH / presentation | Actual duration | First report 11 | Last state | Acquisitions | A–B–A |
|---|---|---|---|---|---|
| Synchronous / shared | 360.08 s | 145.14 s | 11 | 1,910 | 25 |
| Asynchronous / shared | 360.04 s | 116.40 s | 11 | 2,325 | 140 |
| Synchronous / RAM | 360.04 s | 126.41 s | 11 | — | — |
| Asynchronous / RAM | 360.05 s | 121.31 s | 11 | — | — |

All end deliberately at the limit (process 1/launcher 0), cards
intact, without sought error signatures. Windows visible and never observed
minimized. Synchronous RAM gains foreground from ~21 s; asynchronous RAM from
~41 s. One own capture of each RAM lets us review enemies or HUD/Kratos;
by itself it does not identify a GS frame nor align it with PCSX2, and it perturbs
the captured instant. Do not use the times as FPS.

In the two shared passes, zero sequence/render regressions, contradictory
metadata or unknown hashes; none of the A–B–A in the stretches
of the last state 4/11. All sources are CRTC, `preferred=0`, and only
the initial dimension changes 1×1 → 512×448. Maximum tick distance 34
(synchronous, before the first pad report) and 3 (asynchronous); maximum 1
in their 11 stretches. The log omits retentions and has a quota; absence of
patterns does not certify absence of an old image or pixel equality.

#59 is merged at `cee659a` after the [correct CI of the final HEAD `ab89804`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38139636066).
#51 integrates main by merge, keeping the runner code: an empty diff
of patches/script/src/config versus `f36936e` was verified. The specific wait
of 96/97 is overcome; camera, visible alternation and stability with threads remain
open. An isolated asynchronous/shared pass with only VU1 on a thread is started afterwards;
the GS front requires VU1 on a thread and is evaluated in another later pass.

## Quota with threads and deferred window (2026-10-11)

With the validated 98 runner, asynchronous/shared and VU1 on a thread only:
360.04 s by limit, report 11 from 80.90 s and last 11, card intact,
no sought error signatures nor minimization. A private own capture shows
HUD/Kratos/enemies, without frame alignment. The diagnostic exhausts 4,096
acquisitions in state 4, the last at `hostTick=4136`; it covers none under
the last report 11. Its 3,064 A–B–A and zero regressions/inconsistencies/unknown hash
only describe that initial stretch.

The later VU1+GS front combination reports 11 from 80.83 s, but ends
at 228.17 s with `process_exit`, exit 0, before the 360 s limit. The log
does not determine the cause of the shutdown. Card intact, no sought error
signature nor minimization; no own capture of that pass. It is not a complete
control nor proof of stability. It also exhausts the quota in state 4, 3,045
A–B–A and no acquisition record under the last report 11. Repeat.

New per-topic patch `ps2recomp-gs-host-diag-window.patch`, applied after
the diagnostic: `PS2X_GS_PRESENT_DIAG_FROM_TICK=<uint64 decimal>` allows
logging from that `hostTick`, inclusive. Absent/invalid keeps start at
0. It keeps the maximum of 4,096 records per instance, only new acquisitions,
the same metadata and existing hash; it does not change Acquire, render, FINISH,
fences or readback. The ticks are those of the log, not seconds nor alignment.
The launcher accepts `--diag-from-tick 6000`, records the variable in the
manifest and rejects invalid ranges before creating the pass. Shifting
the window explicitly omits the startup; keep both runs.

New regressions without the game: do not spend quota before the inclusive tick,
same 4,096 limit from zero or deferred, decimal parse/uint64 limits.
The three pass with MiniTest/MSVC in a reduced executable. The negative
control uses APIs compatible with the previous semantics (no window):
1/3 passes and exactly the two for deferral/parser fail; it is not the full
native suite. 14 launcher tests and 17 inspector tests pass; configuration
0 errors/4 warnings, syntax 23 scripts/0 errors including the private ones,
chain 98 applied in order and new patch applied in an independent tree.
Chain 99 requires a full build, suite/CI and functional repetition.

## Native validation of 99 and probe isolation (2026-10-11)

Full build from `3dbac1a442add16518b0504975bfa715f1b32dc4`,
99 patches, exit 0, 1,005.59 s. VU1 interpreter, Release optimized with
private symbols and three tasks. Frozen runner SHA-256:
`cf063d2f03a1a78f455a9ff57a1378cd4a1ddaf71e6d279d305b34663b96fa07`.
[Correct CI of the same code](https://github.com/KIexster/god-of-war-recomp/actions/runs/38152876084).
Windows: 600/600 normal and 634/634 real GPU; comparator without known failures.
FINISH/read and FINISH/acquired texture pass `default` and `async`, each
mode in a new process. The latter compares 16 textures per mode, all their
rows and metadata against CPU, including reuse of the eight slots.
These tests do not vouch for the pixels or the stability of the game.

It is also detected that the install condition of the animation
overrides checked presence of `GOW_FAST_BOOT`, although the shortcut itself
already required the value `1`. Therefore the previous passes with value `0`
included `[gow-animation]` and `[gow-flash-ready]`, even without enabling the shortcut.
This limitation is kept in their results. The change in `src/` requires the
exact value `1` to install those probes through fast boot; the explicit
diagnostics `GOW_PATH_DIAG`/`GOW_ANM_DIAG` keep their existing activation.
It does not change the original functions when the probes are disabled.

The previous frozen runner does not contain this last overrides adjustment.
Rebuild only `src/` on top of the full 99 chain, record another identity,
and verify the absence of those labels with `GOW_FAST_BOOT=0` during the
functional repetition. Keep #51 as a draft until the required controls are
completed and the CI of the final HEAD is checked; camera and alternation remain open.

## First functional control of 99 without animation probes (2026-10-11)

On top of the previous full runtime only the overrides are rebuilt from
`a37cd856ccc884c03b7a8260957d56d9d7ac49cd`, exit 0 in 19.05 s, without
regenerating the C++ nor changing patches. New runner SHA-256:
`a4ec4365273903d525ce19ecade3fb423fb871c5628a84e695b33ac777ca3598`.
[Correct CI of the same HEAD](https://github.com/KIexster/god-of-war-recomp/actions/runs/38154314459).

Asynchronous/shared, threads off, default window (tick 0), same exclusive
script/hash and private procedural card: 360.06 s by limit
(process 1/launcher 0), first report 11 at 154.02 s, last 11. Card
intact, none of the sought error signatures nor animation/flash-ready labels.
Window visible, never minimized nor in the foreground during this pass.
No own capture; window control through Computer Use is not available.

2,046 acquisitions, 27 A–B–A only before report 3; zero regressions,
contradictory metadata or unknown hashes. There are 983 acquisitions under
the last report 11, none A–B–A there; CRTC/`preferred=0` source in all.
Only the initial dimension changes 1×1 → 512×448. Maximum tick distance 37
at startup under report 0; maximum 5 in stretch 4 and 1 in 11. The pad
reports are spaced samples, not a frame alignment. No old
image nor performance is diagnosed from those distances or times.

VU1 on a thread only is repeated next with `--diag-from-tick 6000` in another
private folder; then VU1+GS front. Do not overlap games, emulator or builds.
The absence of patterns in these samples does not certify correct visual
presentation, pixel equivalence, camera or prolonged stability.

## Gameplay window with VU1 on a thread (2026-10-11)

Same runner `a37cd85`/SHA-256
`a4ec4365273903d525ce19ecade3fb423fb871c5628a84e695b33ac777ca3598`,
asynchronous/shared, VU1 on a thread and GS front off, window from 6000.
Completes 360.06 s by limit; report 11 from 81.05 s, last 11. Card
intact, none of the sought error signatures nor animation/flash-ready probe,
window visible/never minimized, no foreground nor own capture. It is not
overlapped with another game, emulator or build.

The first record has `hostTick=6000`, `frameTick=5999`, sequence/render
5880. Exactly 4,096 acquisitions are logged, all under the last report
11: the filter keeps the quota through startup. CRTC/`preferred=0` source,
512×448, valid hash in all; zero sequence/render regressions, contradictory
metadata or dimension changes. Tick distance 0..2.

There are 3,009 A–B–A in this stretch. The inspector now keeps the three ticks
per return and quantifies their parity without suppressing any: all 3,009 are
0–1–0 or 1–0–1 in `frameTick`; zero with constant or different parity.
Its 20 tests include equal host ticks with different texture
parities, retentions and separations by mode/unknown hash.
The previous control without threads also has its 27 startup returns
with alternating parity, none during gameplay.

The procedural GPU suite already checks two different fields with invariant VRAM
and GoW timing against CPU. This result is compatible with field
alternation, but the game log does not include SMODE2: it does not prove that mode,
its cause nor the absence of old content. Equal pixels, correct
camera or FPS are not declared. The quota is still finite and leaves the
rest of the pass unlogged. The VU1+GS front repetition from 6000 is started next.

## Full repetition with VU1 and GS front (2026-10-11)

Same runner `a37cd85`/SHA-256
`a4ec4365273903d525ce19ecade3fb423fb871c5628a84e695b33ac777ca3598`,
asynchronous/shared, VU1+GS front on threads, window from 6000: completes
360.04 s by limit (process 1/launcher 0), report 11 from 80.97 s, last
11. Card intact, none of the sought error signatures nor animation/
flash-ready probes; window visible/never minimized, no foreground nor own
capture, no overlaps. This pass does not reproduce the early exit of
98 at 228.17 s: its cause remains unknown, it is not declared fixed because of it.

First record hostTick=6000, frameTick=5999, seq/render=5933. The 4,096
acquisitions are under the last report 11, 512×448/CRTC source/valid hash,
without sequence/render regressions nor contradictory metadata or dimension
changes. Tick distance 0..1. 3,506 A–B–A, all with alternating parity
of frameTick; they do not demonstrate old images nor interlacing by themselves.

Chain 99 thus passes three finite controls: without threads/window 0, VU1
only/window 6000 and VU1+GS front/window 6000. The full RAM/synchronous matrix
of 98 is not repeated here nor are its results carried over to the new runner.
[Correct CI of the inspector and documentation `6f30f5c`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38155362566);
check the new documentation HEAD after publishing this result.
Keep #51 as a draft because of the pending visual comparison. To distinguish
fields from other returns, the next diagnostic must keep SMODE2
of the request used to produce the texture, not read the current CRTC afterwards.
The new tests and acquisitions do not resolve the framing inside the GS.

## Mode of the request actually composed: chain 100 in preparation (2026-10-11)

New separate patch `ps2recomp-gs-acquired-mode-diag.patch`, after the
window one: it keeps the complete `request.smode2` in the slot when publishing, together
with its tick. The host logs `smode2=<uint64 decimal>` of the same Frame
returned by Acquire. It does not read the current CRTC, acquire another texture, download
pixels, compute another hash or change FINISH/fences/filtering/composition.

Windows/WGL regression with a real texture: fixed VRAM, even/odd fields, frame
mode and progressive, compare rows against CPU and check the complete SMODE2
in each new and retained sequence. Changing the caller's request afterwards
does not alter the mode of the previous texture. The pattern height is 128 to
keep at least 64 logical rows even in the mode that splits the buffer.
Do not consider this new regression correct before running it; it requires a real
GPU on Windows, it does not run as an empty success in Linux CI.

The inspector accepts 11..13 fields, including the two optional `preferred`
and `smode2`; uint64 range, per-sequence coherence and old logs.
It keeps all A–B–A: `smode2_values` stores the three modes when any
is known; `content_return_modes` counts `unknown` if any is missing,
`all_field` if in all three `(SMODE2 & 3) == 1`, and `other` for the rest.
A logged mode and compatible parity do not prove the cause of the return,
equal pixels nor the absence of an old image. The logs of 99 still lack
SMODE2 and must be classified as unknown, without inventing it from parity.

24 Python tests of the inspector correct, syntax 23 scripts/0 errors,
independent application of the new patch on a correct 99 base.
Pending: CI of the final HEAD, full Windows build of 100, new native
test/meaningful negative and another gameplay window. The 99 runner
does not contain the field. Keep its identity and previous results.

## Initial control of 100 and scope of the mode regression (2026-10-11)

The full build of `4a000c48e2d111637a77318eb509dd88f35d653d` finishes
with exit 0 in 943.29 s; 100 patches, Release `/O2 /Ob2 /DNDEBUG /Zi`, link
`/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`, VU1 interpreter and private symbols.
Runner of 54,542,848 bytes, SHA-256
`fb46a87ac6d80a600f8662ae3ee6b74bbb5b37b84f1cc10fa0eb0b0f3d4367b5`.
[Correct CI of that code](https://github.com/KIexster/god-of-war-recomp/actions/runs/38156407391).
After freezing it, the objects of the private procedural controls are also
rebuilt: the new field changes the layout of Frame.

Windows suite: 600/600 normal in 13.42 s; real GPU 634/635 in 31.35 s. Only
"SMODE2 of acquired and retained texture" fails, with reasons "logical height" and
"Real composition compared against CPU". The following contracts are left
unexecuted by that exit; no game uses this runner. Keep the failure
as a result, without confusing a correct build with functional validation.

For `SMODE2=0x403` and DISPLAY of 64×128, the GPU formula divides the height by
two and the CPU does not divide it. The diagnostic did not modify those formulas. Investigate
separately which interpretation is correct and whether that mode actually appears
in the game; the difference does not prove the cause of the framing nor of the alternation.

The new test is adjusted to the purpose of preserving the metadata: it keeps
even/odd fields, frame and progressive with high bits, all new
and retained acquisitions. Fields/progressive still compare all rows against
CPU. In frame mode a real non-empty texture is acquired and the
dimensions of both renderers are printed through `[gs-test:mode-frame]`, without claiming
equivalence there. The mode is not suppressed nor is composition, FINISH or
fences changed. This decision expressly reduces the scope of the CPU comparison
of the new test; it does not change the previous tests nor cover up the first failure.

Pending: another full build, normal/GPU suite, compatible negative
control forcing the metadata to zero and positive restoration, independent
contracts and the game window. Do not use the previous runner to vouch for
the adjusted test. PR #51 remains a draft and the framing remains separate.

## Revised native validation of 100 and metadata negative (2026-10-11)

New full build from `383c6b65986ffe2cddebaed987d9132ea791d100`,
100 patches, exit 0 in 928.11 s. Release optimized with private symbols,
VU1 interpreter and flags equal to the previous one. Runner of 54,542,848 bytes,
SHA-256 `5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`.
[Correct CI of that code](https://github.com/KIexster/god-of-war-recomp/actions/runs/38157988334).
Runner/symbols are frozen before including the private controls and
their objects are rebuilt because of the Frame layout change.

Windows: 600/600 normal in 13.39 s and 635/635 real GPU in 30.87 s; both
comparators return 0, without known failures. The four controls pass in
new processes: FINISH/CSR/order/read and FINISH/acquired texture, each one
with `default` and `async`. The second compares 16 textures per mode, all
rows against CPU, sources, dimensions and reuse of eight slots.

The new case confirms the complete SMODE2 in new and retained textures for
fields/frame/progressive; fields/progressive compare pixels against CPU. In
frame mode it actually logs `smode2=1027 cpu=64x128 shared=64x64`. That case
only validates texture/metadata: composition equivalence remains pending
and it is not declared fixed because of the success of the adjusted suite.

API-compatible private negative: change only the storage
of `slot.frame.smode2` to zero and rebuild **only the tests**, without altering
or running the runner. It compiles and runs 635 cases: 634 pass, exactly
"SMODE2 of acquired and retained texture" fails. The comparator reports that regression;
it is neither a build failure nor an exception in `fallos_conocidos.txt`.
Afterwards the complete positive file is restored, the tests are rebuilt
and GPU returns to 635/635 in 31.33 s. Restored source and frozen runner verified.

Pending isolated functional controls of this runner: first threads 0 and
window from 0, then VU1 and VU1+GS front separately from 6000. The diagnostic
introduces no readback, additional Acquire, additional hash computation or glFinish.
The game patterns and the visual comparison are not yet validated for 100.

## First functional control of 100: mode acquired during gameplay (2026-10-11)

Full runner `383c6b6`, SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared, threads 0, logging from 0 and same private procedural
script/card. Completes 360.06 s by limit (process 1/launcher 0), first
report 11 at 133.85 s, last 11. Card intact; none of the sought error
signatures nor animation/flash-ready probes. Window visible/never minimized,
in the foreground only between 17.12 and 41.29 s according to the monitor; no own capture.
The foreground change was not an automated Computer Use input.

1,955 acquisitions, without sequence/render regressions, contradictory metadata
or unknown hashes; CRTC/`preferred=0` source. Initial dimension 1×1 →
512×448. Six A–B–A, all before stretches 4/11, with alternating parity and
three field modes logged. Maximum tick distance 37 at startup,
6 in stretch 4 and 1 in 11; it does not measure time nor demonstrate sustained latency.

There are 1,063 acquisitions under the last report 11: `smode2=2227921`, whose
low value is `(SMODE2 & 3) == 1`, field mode. None A–B–A there. The
frame case with different CPU/GPU height (`&3 == 3`) does not correspond to these samples;
it does not rule out other composition problems nor demonstrate the cause of the camera.
The pad reports are spaced, not a frame alignment with PCSX2.

[Correct CI of the native validation/documentation `6a53774`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38159575279).
VU1 on a thread only, window from 6000, is started next, in another folder;
VU1+GS front will be repeated after closing that pass. Do not overlap games, emulator
or build, nor use these times/hash/diagnostic/interpreter as FPS.
Without a visual comparison, alternation, framing or hangs are not declared resolved.

## Control of 100 with VU1 only: returns in field mode (2026-10-11)

Same full runner `383c6b6`/SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared, VU1 on a thread and GS front disabled, window from 6000.
Completes 360.04 s by limit (process 1/launcher 0), first report 11 at
80.98 s and last 11 at 357.24 s. Procedural card intact, none of the sought
error signatures nor animation/flash-ready probes. Window visible, never
minimized and not in the foreground according to the monitor; no own capture nor overlaps.

4,096 acquisitions under the last report 11, all `smode2=2227921` (`&3=1`),
512×448, CRTC/`preferred=0` source, valid hash. First sequence/render
5877, hostTick=6000/frameTick=5999; last 9973, hostTick=10153/frameTick=10152.
Tick distance 0..1, without sequence/render regressions, metadata inconsistencies
or dimension changes. The 3,562 A–B–A returns alternate
parity and keep field mode in the three samples; there are no returns
of equal parity, unknown modes or other modes in this window.

This reinforces compatibility with field composition, but does not prove
what produced the visual symptom, pixel equality or absence of old
content. The quota ends before the end of the game; it does not cover the whole
six-minute interval. It is not used as a benchmark nor a comparison with Opus.
[Correct CI of the documentation HEAD `e3678cb`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38160245742).
Another isolated VU1+GS front pass, window from 6000, is started next;
its result is pending. Framing and visual comparison remain open.

## Control of 100 with both threads and closing of the diagnostic (2026-10-11)

Same runner `383c6b6`/SHA-256
`5f3b9c29dad7797e7edaa17585254eccaadd14238a834d15b69101c28895c74f`,
asynchronous/shared, VU1 and GS front on a thread, window from 6000. Completes
360.05 s by limit (process 1/launcher 0), first report 11 at 80.92 s and
last 11 at 357.49 s. Card intact; none of the sought error signatures nor
animation/flash-ready probes. Window visible, never minimized/not in the first
foreground according to the monitor. There is no own capture nor overlaps.

4,096 acquisitions under the last report 11, all SMODE2=2227921 (`&3=1`),
512×448, CRTC source/valid hash. First sequence/render 5958,
hostTick=6000/frameTick=5999; last 10053, hostTick=10119/frameTick=10118.
Tick distance 0..1; zero regressions/inconsistencies/dimension changes.
3,542 A–B–A: all alternate parity and log fields in the three samples.
The early exit of 98 is not reproduced, but its cause remains open;
two six-minute repetitions do not prove prolonged stability.

The three passes of 100 complete the functional control **of the diagnostic**:
without threads/window 0, VU1 only/window 6000 and both/window 6000. The log
stays bounded, keeps the metadata of the acquired texture and works in gameplay.
The full build and native suite/negative/contracts are recorded above.
[Correct CI of the VU1 result `bae5d74`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38160854972).
Also review the CI of the final HEAD before publishing #51 as ready/merging it.

The closing criterion is clarified: #51 incorporates optional instrumentation,
not a visual fix. The previous entries that kept it as a draft because of the
visual comparison described the work pending at the time; the absence of
that comparison still limits the conclusions about the game and does not invalidate
the metadata proven with real GPU. Framing, old content and equivalence
with PCSX2 remain pending, without declaring them resolved by this closing.
The next check requires a few pixels of the texture actually
acquired, with metadata of that reservation, in a separate explicit capture:
the latched VRAM is not enough and adding it must not silently change the cost
of the #51 diagnostic. Do not turn these passes into FPS measurements.

## Explicit capture of the acquired reservation: preparation of 101 (2026-10-11)

#51 was merged at `05421940617e5ce69889600d9eb727b3c36c0b3b` after reviewing
the change, closing the previous validations and checking the [green CI of the final HEAD
`10edb76`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38161351218).
Framing, visual cause of the returns and prolonged stability remain open.

New separate topic `ps2recomp-gs-host-acquired-capture.patch`, applied after
the 100 previous ones. `GSHostPresentation` can save a few textures
from the same reservation it has just acquired, with RGBA PNG and JSON of their metadata.
The option is disabled by default and is independent of PRESENT_DIAG.
It does not query VRAM, re-acquire nor introduce a global glFinish or changes
in FINISH/fences/composition. **Enabling it does download pixels and write files**:
use another diagnostic pass, never a benchmark or proof of absence of hangs.

Variables read when building the host: `PS2X_GS_ACQUIRED_CAPTURE_DIR` points
to an existing private folder, `PS2X_GS_ACQUIRED_CAPTURE_FROM_TICK` sets
the first inclusive hostTick (absent/invalid: 0), and
`PS2X_GS_ACQUIRED_CAPTURE_COUNT` limits attempts (default 6, range 1..16;
invalid disables). It does not capture retained sequences, regressions, empty textures
or PMODE off; failures also consume the quota. It rejects existing files
and keeps the Unicode path on Windows. A complete JSON accompanies each correct
PNG; failures are logged as `[gs-present:capture] status=failed`.

The launcher adds `--capture-acquired 6` only for shared cases, creates
`acquired/` inside the new folder of the pass and uses `--diag-from-tick`
also for that window. With value 0 it does not install the capture variables,
including inherited ones. Keep manifest/hash/script/cards and close
one pass before starting another. The game's PNGs and JSONs remain private.

Windows/WGL procedural regression pending execution: publish A,
acquire it, modify VRAM to B and export reservation A. Compare all
the pixels of the PNG with A and then publish/export B; verify metadata, window,
retention, quota and rejection of overwriting. Do not accept CPU fallback nor an empty
success on Linux. C++20 syntax correct, application on an independent base
of 100 correct, 17 launcher tests correct, configuration 0 errors/
4 existing warnings and PowerShell syntax 0 errors. Pending: full build
of 101, normal/GPU suite, meaningful negative/restoration, CI
and game control before attributing captures or visual conclusions to it.

## Native validation of the acquired capture of 101 (2026-10-11)

Full Windows build of `394779a6dca0fd8dcaf7415e06ad048fdd9ad7f8`,
101 patches, exit 0 in 916.19 s; Release optimized with private symbols,
VU1 interpreter and three build processes. Runner of 54,552,576 bytes,
SHA-256 `63e6a576307675f34b70e4671a5b34de30219627a2ca2a3a362c182effd27040`.
Flags `/O2 /Ob2 /DNDEBUG /Zi` and `/INCREMENTAL:NO /DEBUG /OPT:REF /OPT:ICF`;
runner/symbols frozen before including the private controls.
[Correct CI of the same code](https://github.com/KIexster/god-of-war-recomp/actions/runs/38161970774).
[CI of the #51 merge into main also correct](https://github.com/KIexster/god-of-war-recomp/actions/runs/38161755251).

Windows: 600/600 normal in 12.41 s, 636/636 real GPU in 30.98 s, without known
failures. The four FINISH/read/acquired-texture contracts pass in
new `default`/`async` processes; the second compares 16 textures per mode,
all rows and slot reuse. The new regression verifies the complete RGBA
PNG of A after changing VRAM to B, metadata of that reservation and
the later PNG of B, plus window/quota/retentions/no overwriting.
The CPU/GPU difference in frame mode described in 100 remains open.

Compatible private negative: replace only LoadImageFromTexture with
a synthetic magenta image of the same size in the exporter. Rebuild
only the tests; runner unchanged and no game. It compiles and runs
636 cases: **635 pass and exactly "Capture of acquired reservation
after changing VRAM" fails**, because of different pixels. Restore the complete positive file
and rebuild: GPU returns to 636/636 in 31.84 s. Restored source
identical to the backup; current runner and frozen copy keep the same hash.

An isolated asynchronous/shared game pass without threads is started next,
window from 1500 and six captures; there is still no functional result nor
visual conclusion of 101. That window differs from the previous one from 0 in
reserving the captures for gameplay. Then compare another window with VU1
on a thread from 6000, without overlapping games/build/emulator. PNG/JSON and
pixel analysis remain private; do not use the times as FPS.

## First captures of 101: provenance and window limitation (2026-10-11)

Runner `394779a`/SHA-256
`63e6a576307675f34b70e4671a5b34de30219627a2ca2a3a362c182effd27040`,
asynchronous/shared without threads, six captures from hostTick=1500. Completes
360.07 s by limit (process 1/launcher 0), first report 11 at 131.78 s,
last 11; card intact, none of the sought error signatures nor old probes.
**The monitor records minimization between 44.22 and 156.01 s**, with foreground
before/after; its cause is not known and there was no automated Computer
Use input. Do not present the pass as a constant window condition. The captures
are after the restoration, under the last report 11; the case will be repeated.

643 acquisitions from 1500, all SMODE2=2227921 (`&3=1`), 512×448/CRTC
source/valid hash, without regressions/inconsistencies/A–B–A/dimension changes,
tick distance 0. Six RGBA PNGs and six JSONs are saved, of sequences
486..491/ticks 1500..1505; each field matches its acquisition in the log.
The six RGBA contents are different from each other; the 224 adjacent row
pairs are identical within each image, in line with the field compositor.
The review of the first two samples shows Kratos/deck/rain, without alternating
menu and gameplay in those samples. It does not demonstrate absence of old content
in other windows, correct scene, PCSX2 equivalence or resolved framing.

## VU1 of 101: A–B–A confirmed in acquired pixels (2026-10-11)

Same runner, asynchronous/shared, VU1 on a thread and GS front 0, six captures
from hostTick=6000. Completes 360.05 s by limit, first report 11 at 80.83 s
and last 11 at 358.22 s; card intact, without sought error signatures nor old
probes. Window visible/not minimized/not in the foreground according to the monitor.
4,096 acquisitions under the last report 11, all SMODE2=2227921 (`&3=1`),
512×448/CRTC source/valid hash; without regressions/inconsistencies/dimension
changes, tick distance 0..2. The 3,204 A–B–A alternate parity and have
field mode in the three samples. The quota does not cover the whole interval.

Six complete PNGs/JSONs of sequences 5806..5811, texture ticks
5999, 6000, 6001, 6003, 6005, 6006. Metadata correlated exactly
against the records of those acquisitions; 224/224 duplicated row pairs
in each PNG. Textures 5806 and 5808, of odd parity, are **identical in
all their RGBA bytes**, and 5807 (even) is different: a real A–B–A in this triple,
not just a coincidence of the GPU hash. Also 5809 and 5810 are identical to each other,
both odd. The other pairs are different; do not extrapolate that equality
to other textures or to the game's CPU renderer.

The visual review of 5806/5807 shows the same scene/camera of Kratos on
deck, with different fields. This supports the compatibility of the return
with field composition, **without demonstrating VRAM freshness nor the cause
of the original symptom**. No alternating menu is observed in these images;
it is not ruled out outside the six captures. The framing is not compared with an
aligned reference. The 1500 and 6000 windows of the two passes also
do not automatically represent the same pose/instant: do not compare their cameras
as evidence of a difference caused by the threads.

[Correct CI of the native result `ce23d73`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38163566080).
Another pass without threads is started to repeat the window condition. #60
remains a draft during that control and review of the CI of the final HEAD.
All pixels, JSON and analysis remain private; the camera
math is not modified nor published as a benchmark or solution of the failure.

## Repetition without threads and closing of the capture control (2026-10-11)

Same runner `394779a` and previous hash, asynchronous/shared, VU1/GS front
disabled, six captures from 1500. Completes 360.04 s by limit (process
1/launcher 0), first report 11 at 116.48 s and last 11. Card intact,
none of the sought error signatures nor old probes. The monitor records no
minimization; it moves to the foreground at the end. This does not erase the minimization
of the previous pass nor identify its cause.

870 acquisitions under the last report 11, all SMODE2=2227921 (`&3=1`),
512×448/CRTC source/valid hash, tick distance 0. Zero regressions,
inconsistencies, A–B–A or dimension changes in that window. Six RGBA PNGs
and six JSONs of sequences 1462..1467/ticks 1500..1505, all their metadata
match the acquired log. The six contents are different from each
other and each image duplicates 224/224 adjacent row pairs. The first two
reviewed images show Kratos on deck and the same view within the pair.
Do not compare them with poses/cameras of another pass for sharing tick 1500:
the script uses host time and that tick does not align the game state.

The three passes of 101, full build, normal/GPU suite, restored negative
and contracts close the functional validation of this **optional
capture**. Manual review: the call uses the Acquire Frame while
its reservation is still valid; without the option there is no readback nor capture I/O.
[Correct CI of `9332c1b`](https://github.com/KIexster/god-of-war-recomp/actions/runs/38164770068).
Before merging #60, also check the CI of the HEAD that incorporates this
result. Framing, content freshness, frame-mode discrepancy and
prolonged stability remain open; no math is changed nor is the original
symptom declared solved. PNG/JSON/analysis remain private.

## Controls of runner 105 and separation of counters (2026-10-13)

Runner 105 with compiled VU1 is built and identified in research-log.md;
the previous historical passes do not vouch for it. The later manual test
confirms shared presentation and both threads, but does not record scene,
window nor exit code. Flip/s and host/s count different operations and
do not measure unique frames displayed. Their zero times correspond to the
`frames` mode, which disables timers.

The reproducible control now allows `--perf frames` or `--perf timing` and
`--presentation-diagnostics sequence` or `off`, besides the default hash.
Without `--capture-acquired` no pixels are exported. To follow waits without
readbacks nor hash use `--perf timing --presentation-diagnostics off`,
without DX11 mirror and with capture disabled. Keep window monitor,
shutdown result, identity and private card. The times are elapsed times
of instrumented scopes; they are not CPU percentages. For a visual reference
use another explicit pass with mirror/captures and both threads off.

## Diagnostic capture and acquired texture (2026-10-14)

`GowPadTest` uses `GS::copyLatchedHostPresentationFrame`. With shared
presentation, that function requests a readback of current VRAM with the latched
CRTC request; its pixels do not come from the texture acquired by the host.
The `--capture-acquired` option, in contrast, reads the acquired `Frame` while
its reservation is still valid. The two captures have different limits and
must not be interchanged as proof of what the window presented.

In the mandatory menu 109 several diagnostic captures did not contain
options. A dedicated title control with the same runner, only Start,
obtained 16 acquired and the HW/shadow/SW references of its own run.
The complete quartets 900/904/908/912 were reviewed: title, "New Game" and
"Select" appear in all four sources. This vouches for those samples,
without demonstrating why options were missing in the capture of the menu script.
There is no fix of that path nor a confirmed visual regression.

The control closed by limit at 180.172 s, card intact and no minimization
recorded. Acquired distinct, 512×448 and correlated metadata.
Shadow and acquired are not identical for sharing a tick: it remains pending
to record their command boundary. None of these controls measures unique frames
displayed nor vouches for normal exit or prolonged stability.

In addition, the host's `[gs-present:shared]` log is emitted when the
acquired sequence changes, with threshold and quota. The iterations that reuse
the same sequence do not generate another row. Zero repetitions in the inspector
does not prove that the window never reuses a texture. `host_hz` does count
each completed `renderFrame/EndDrawing`, even if it reuses content;
`guest_flip_hz` counts entries to `vid::Flip`. Counters and times
specific to reuse/presentation are missing to turn that disagreement
into a measure of distinct frames sent, and even that measure would not be
proof of physical frames displayed by the monitor.

## Times 109 and requested window close (2026-10-14)

Combined pass 600.164 s without mirror/hash/readbacks/GS diagnostic, with copied card:
state 11 observed 35.06..596.22, no minimization recorded. WM_CLOSE was sent
only to the HWND of the child PID and the process closed with 0 in 0.147 s, without forced termination.
This validates that requested close; not the end of the game nor prolonged stability.
The foreground varied; do not attribute speed differences to a single condition.

Within the same pass there are gameplay windows with host 9.11..19.64/s and
later ones 55.66..60/s. Flip and host count different operations.
There is no visual reference of that pass to align cameras with others by tick.
HostWait has a median of 4,979.41 ms per window of about 5 s, even with host 60/s:
it includes GL batch/swap/limiter/events of EndDrawing. Before attributing waits,
separate those components keeping calls/order/fences. The scopes of
distinct threads do not represent a CPU percentage nor are they summed as global time.

## Reproducible profile and close options

To repeat the controls without private scripts, add to the usual command:

```text
--perf timing --presentation-diagnostics off --capture-acquired 0 --gpu-profile --gpu-stats --request-window-close
```

`--gpu-profile` enables existing timestamps and `--gpu-stats` backend
statistics; both are optional and are recorded in measurement.
The GPU profile queries AVAILABLE before reading during render and may
omit samples because of its quota. Its "per frame" label divides by attempts
of the compositor after DispatchCompute/before PublishShared: **it is not
time per Flip nor per displayed frame**. The last close window
can pick up pending work with few attempts. Do not mix its windows
with the CPU ones as if they shared exact time limits.

`--request-window-close` requests close only from the HWND of the child PID created by
the control. It waits up to 15 s; if it does not achieve close it records forced_fallback and
stops only that child with Popen. The result includes sending, fallback,
code, duration and query error, if any. Review those fields before
vouching for a close without forcing. The limit or STOP remain recorded as
the controller's reason; they are not equivalent to the end of the game. Without that option
the previous stop method is kept. Real 75 s control and procedural tests
closed in research-log.md; CI of the new HEAD pending confirmation.
