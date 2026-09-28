# Qualification gates

## Current gate: native USB configuration and capture

On September 28, the twelfth bounded attempt ran candidate
`build_a522bd6a10a44159bf38da9c5229d9d5` after fresh independent accepted
review and one-use attended authorization. Host logs show native enumeration
at 17:03:22.271519 UTC and SET_CONFIGURATION timeout (`-110`) at
17:03:27.487533 UTC. No native tty, payload bytes or samples were obtained.
The original `unknown_effect` outcome is retained and reconciled as failed.

Two readers independently decoded private no-audio screen snapshots.
`VAGP 2 / 3 / 2 / 2` at 65 and 149 seconds reports both ACM interface calls and
serial connection returned zero and the DWC3 EP0 status command was accepted.
`VRES 2 / 2 / 0 / 0` at 67 and 145 seconds reports the selected status wrapper
returned, with no post-command EP0 event observed in those snapshots. The
target displayed `10 / 1 / 8` at 174 and 176 seconds: `launch_wait`,
`TimeoutError` and UDC state `configured`. These are target-side observations,
not evidence that host configuration completed. Wrapper return makes a stall
in its MMIO/PHY-restoration tail unsupported; the next diagnostic must separate
controller status-TRB ownership/progress and device/link event state from
missing EP0 completion. No role, FIFO or module fix is established.

The same checked proxy identity returned on a new owned connection at
17:05:50.672948 UTC, without independent reboot attestation. The camera
stopped; footage remains private. The qualification session is paused with no
automatic repeat or unattended native dispatch. Native capture and power
measurement remain unqualified. The frozen source passed 500 host tests before
launch, and the expanded 90-test tracer suite passed after its review
regression. See
[twelfth-attempt evidence](evidence/2026-09-28-native-twelfth-attempt.json) and
[service handoff](evidence/2026-09-28-twelfth-service-handoff.json).

On September 28, the eleventh bounded attempt ran candidate
`build_91cbf0b92ef6404b8483bfdd5269c77f` after AC returned, a fresh
independent accepted review and one-use attended authorization. Host logs show
native enumeration at 16:11:58.268470 UTC and SET_CONFIGURATION timeout
(`-110`) at 16:12:03.711495 UTC. No native tty, payload bytes or samples were
obtained. The original `unknown_effect` outcome is retained and reconciled as
failed.

In the private no-audio recording, two readers independently decoded trace
`2 / 3 / 2 / 2` at 37, 145 and 146 seconds. The target trace reports both ACM
interface calls and serial connection returning zero, with the DWC3 EP0
status Start Transfer command reaching its acceptance tracepoint. The console
later showed `10 / 1 / 8` at 167 seconds: `launch_wait`, `TimeoutError` and UDC
state `configured`. These are target-side, timing-perturbed observations, not
host completion. The `P2` tracepoint occurs before the command helper returns,
reads its resource index and restores PHY bits; the retained snapshots do not
show a matching status-completion callback. The next diagnostic should
separate helper return from controller EP0 event and callback completion. This
trace establishes no role, FIFO, module or endpoint fix.

The watcher caught the same checked proxy identity on a new owned connection
at 16:14:26.749184 UTC. That USB return does not independently attest reboot.
The camera stopped cleanly and its footage remains private. The qualification
session is paused, with no automatic repeat or unattended native dispatch.
Native power measurement remains unqualified. See
[eleventh-attempt evidence](evidence/2026-09-28-native-eleventh-attempt.json).

On September 28, the tenth bounded attempt ran candidate
`build_7885d048ed074cf2bded9b757c5bd9a7` under exact independent review and
single-use authorization selected under the owner's delegation. Operation
`operation_f7fbabeda7064d71ae5c13de612e9e5c` ran at 15:27:19–15:30:13 UTC.
Host logs show native enumeration at 15:27:45 UTC and SET_CONFIGURATION timeout
(`-110`) at 15:27:50 UTC. No native tty, payload or samples were obtained.

After prior USB-only diagnostics failed, the owner-authorized bounded camera
recording supplied the missing target stage. Two readers decoded the large
console marker as `10 / 0 / 8` at 35 seconds and `10 / 1 / 8` at 169 seconds:
`launch_wait`, initially no reported error, then `TimeoutError`, with UDC state
`configured`. Lower kernel lines were not reliably transcribed. The image was
unchanged after the independent review and its 52 published artifacts matched
their stored hashes and sizes. All 407 host tests passed before packaging.

The exact [Asahi kernel configuration path](https://github.com/AsahiLinux/linux/blob/asahi-7.1.13-3/drivers/usb/gadget/composite.c)
sets `USB_STATE_CONFIGURED` before the function-interface `set_alt` loop.
The [DWC3 EP0 path](https://github.com/AsahiLinux/linux/blob/asahi-7.1.13-3/drivers/usb/dwc3/ep0.c)
also separates configuration handling from status completion. Thus the visible
UDC state supports entry into configuration handling, but cannot prove ACM
endpoint setup or the host's control transfer completed. The next diagnostic
must distinguish those stages; these observations alone do not identify a fix.

The watcher caught the same checked proxy identity on a new owned connection
at 15:30:13.295398 UTC. The original unknown outcome is retained and reconciled
as failed. Screen blanking and a later Apple logo were visible, but this is not
independent reboot attestation or power qualification. The camera stopped
cleanly with no coverage loss reported and no audio recorded. Footage remains
private. The native qualification session is paused; no automatic repeat or
unattended native dispatch is enabled. See
[tenth-attempt evidence](evidence/2026-09-28-native-tenth-attempt.json) and
[current deployment status](STATUS.md).

The ninth attempt's fresh device-descriptor requests timed out or received
protocol errors after the same host configuration timeout, so no target stage
was available over EP0. The eighth attempt also timed out at configuration.
Both captured zero samples, returned to checked proxy connections and were
reconciled as failed while retaining original unknown results. See
[ninth-attempt evidence](evidence/2026-09-28-native-ninth-attempt.json) and
[eighth-attempt evidence](evidence/2026-09-28-native-eighth-attempt.json).

The sections below retain historical qualification states as recorded at the
time; their pending approvals and installed release versions are historical.

## Expired launch replaced without target dispatch

The owner replied `approved` at approximately 23:57 UTC, after the configfs
launch deadline of 19:57 UTC. The exact reply and an unused approval bounded by
that original deadline are retained. No eighth physical test occurred. The
matching proxy and unused helper capability were freshly observed.

Replacement `2366a423…eb6d2c5` changes only the run ID/deadline, keeping the same
candidate, helper configuration, scripts and test bounds. Exact sol/medium review
accepted it without blockers (95,466 reported tokens; isolated lifetime 1,101,538;
no usage uncertainty). It expires at 00:13:56 UTC on September 27. Authorization
for this new digest is pending; the old approval cannot transfer. Live pause and
usage hold remain intact. See [evidence](evidence/2026-09-27-native-launch-refresh.json).

## Seventh attempt and concrete configfs fix

The separately reviewed and owner-approved font-configured attempt ran once at
19:27:34–19:27:59 UTC. It captured zero native samples; boot client exited zero,
and the watcher caught the returned proxy. The owner confirmed automatic return.
A 24,000-byte boot log and 30.933-second private video are retained. Exact visual
failure text remains unverified. Original `unknown_effect` is preserved and
reconciled as failed; all seven approvals are consumed.

Independent source inspection found the target's configfs link error. Linux
[configfs resolves the target at link creation](https://github.com/torvalds/linux/blob/master/fs/configfs/symlink.c)
using the current working directory. The target ran from `/` but supplied
`../../functions/acm.usb0`, so lookup reached `/functions/acm.usb0`. The absolute
gadget function path fixes this defect without changing USB roles or bounds.
A host regression running the actual gadget setup with configfs lookup semantics
failed before the fix with `FileNotFoundError`; afterward
`.venv/bin/pytest -q tests/integration/test_native_boot.py` passed **8 tests in
0.31 seconds**. Root inspected the minimal patch. This proves the source defect
and host correction; physical capture/return with the rebuilt image remains the
next gate. See [evidence](evidence/2026-09-26-native-seventh-attempt.json).

The fixed candidate is built from clean `4c2855b` as
`build_2c9d5eff9bd947a1ac8c575b8b993a9a`. Stored manifest/artifact hashes and sizes
match; the initramfs contains the exact committed fixed bootstrap. Kernel, DTB
and collector outputs are unchanged. This verifies packaging only. The next
acceptance check is the bounded three-sample native capture plus caught proxy
return. Exact sol/medium review accepted `1b751de3…353c8671` with no blocking
findings; new attended single-use owner approval remains pending. The review
reported 91,900 tokens, with no uncertainty in the isolated harness accounting.
Installed release `f560929` is active with zero restarts; its live session remains
paused with `usage_uncertain=true`. See [build evidence](evidence/2026-09-26-native-configfs-build.json).

## Sixth attended attempt: recorded Linux startup, failure text unreadable

Fresh exact review, explicit owner approval/current attendance, armed webcam
and fixed proxy recheck preceded one dispatch of `6b077c88…c9a9d4d`. Operation
`operation_6fb8df5daf9f45e19e692cd7fa6fd94a` ran from 19:00:56.543277 to
19:01:21.028494 UTC. Boot client exited zero and the continuous watcher caught
a new same-identity proxy connection. The owner confirms automatic return with
no manual reboot. No native result payload or samples were received.

The complete 23,960-byte boot log and 30.937-second private webcam recording are
retained. Visible Linux output and diagnostic lines establish screen activity,
but neither the original frame nor a lossless enlarged crop reliably identifies
the exact failure stage/type. Tentative readings are explicitly unverified and
do not justify a target code fix. The camera stopped cleanly. Follow-up fixed
inspection at 19:04:55 UTC confirmed proxy with no launch capability, validating
the spent-helper reporting fix on this path. The original unknown is retained;
the failed attempt is reconciled from private evidence. All six approvals are
consumed. Readability must improve before another diagnostic test. See
[sixth-attempt evidence](evidence/2026-09-26-native-sixth-attempt.json).

The exact published kernel's embedded configuration includes `CONFIG_FONT_TER16x32=y`
and framebuffer console support. The fixed launcher now appends
`fbcon=font:TER16x32`, a [documented kernel option](https://docs.kernel.org/fb/fbcon.html#c-boot-options).
All existing boot arguments and time/output bounds remain; the configuration
digest changes with this option. Existing backend/launcher tests passed **30 in
1.06 seconds**, including fixed command and digest assertions. No target rebuild
is needed. The previous selected font is unknown and improved camera readability
is not yet proven. Fresh helper, exact review and attended approval precede use.
See [font inventory and host evidence](evidence/2026-09-26-native-console-font.json).

Fresh registered font proposal `8acb0a44…e50ad30c` has accepted exact review and
expires at 19:36:52 UTC. Its review reported 90,367 tokens; isolated harness
lifetime is 914,172 with no usage uncertainty. An earlier review's local-versus-UTC
expiry error is preserved. A subsequent correction was accepted by the model but
could not be recorded because the operator had not re-registered after rejection;
it remains advisory history. The current proposal followed normal registration
and review; its new owner approval/current attendance were consumed by the seventh
attempt above. See [review history](evidence/2026-09-26-native-font-review.json).

## Fifth attended attempt: spent helper refused before launch

The owner approved exact procedure `d16b1906…e21ccef` and confirmed attendance.
The webcam captured fresh frames before dispatch. Operation
`operation_f59e819396ed4ddb87297199a7f43a98` ran from 18:46:15.258959 to
18:46:15.427351 UTC and reported an ambiguous helper EOF. It captured zero
native samples and created no boot log. Fixed proxy observations before and
after retained the same connection generation; follow-up at 18:49:36 confirmed
responsive proxy. The 5.933-second private video shows the existing proxy console.
The camera exited cleanly; no fifth native boot or new return is established.

Code inspection identifies a spent one-shot backend: the fourth execution set
`_used`, while later inspection still advertised `run_native_candidate`. The
fifth call therefore refused before launcher entry; the worker's exception
handling closed the socket without a result. The exact exception was not logged,
so this diagnosis combines source behavior with the observed timing and state.
The original unknown outcome is preserved and reconciled as failed with private
execution, approval, proxy and camera evidence. All five single-use approvals
are consumed. The next run needs a fresh helper, launch, exact review and
attended approval. See [evidence](evidence/2026-09-26-native-fifth-attempt.json).

The minimal host correction removes `run_native_candidate` from spent backend
snapshots while retaining proxy availability and identity for reconciliation.
It does not reset the one-launch guard or clear the denial journal. The backend
regression failed before the change. Afterward,
`.venv/bin/pytest -q tests/integration/test_native_candidate_backend.py tests/integration/test_native_qualification_service.py`
passed **35 tests in 2.95 seconds** on the ThinkPad. The public service regression
confirms that a stale stored snapshot followed by a fresh spent snapshot records
`no_effect` before adapter execution or approval consumption. Root reviewed the
patch; no broader test run or physical retry was needed to verify this fix.

After normal shutdown of the spent helper, a fresh helper acquired proxy without
booting the target and retained the denial journal. Exact review accepted new
procedure `6b077c88…c9a9d4d`, expiring at 19:11:10 UTC, for the unchanged target
image and camera scripts. The completed sol/medium review reported 96,924 tokens;
isolated harness lifetime is 641,473 with no usage uncertainty. Subsequent owner
approval and attendance were consumed by the sixth attempt above. See
[fresh-helper review evidence](evidence/2026-09-26-native-fresh-helper-review.json).

## Fourth attended attempt: proxy return caught, capture absent

The fresh accepted review of `056724af…0f3546`, explicit owner approval/current
attendance and fresh proxy inspection preceded one dispatch at 18:05:14 UTC.
No native ACM channel or samples were observed. Proxy disappeared at 18:05:25
and returned as `ttyACM1` at 18:05:39; the helper's continuous watcher caught it,
completed its fixed identity check and retained the new owned connection.
A follow-up inspection at 18:06:27 confirmed responsive proxy. The owner says
the Mac returned by itself and no manual reboot occurred.

The boot client exited zero. Its 23,960-byte log survives in private evidence;
it records kernel/DTB/initramfs loading and handoff, then USB disconnect and a
Miniterm reader/cancel traceback. The traceback does not establish why native
startup ended. The owner saw Linux penguins/logs and fast M1Lab errors, but the
exact failed stage is unknown. No native frames or Linux self-identity were
captured. This demonstrates the corrected return catcher and retained logs on
this attempt; it does not qualify a complete native round trip or known-good image.

The original `unknown_effect` remains intact; evidence-backed reconciliation
records the attempt as **failed**. Bounded package/runtime inspection identified
no concrete missing interpreter, loader, direct library, kernel initrd support,
mountpoint or matching module index. No speculative USB or pySerial patch is
justified. The next discriminating evidence is a video of the existing target
failure markers under a new exact review and attended approval. This approval
was consumed; the separately approved fifth attempt is recorded above. See
[fourth-attempt evidence](evidence/2026-09-26-native-fourth-attempt.json).

For the next observation the owner requested the ThinkPad webcam. A 720p preview
contains the complete console, though fine text is soft. Exact review accepted
`d16b1906…e21ccef` after camera limits, refusal conditions, cleanup and both host
script digests were bound into the procedure. The wrapper checks fresh captured
frames before any native dispatch, imposes a 510-second/1-GiB recording bound
and stops/reaps the camera on normal/error paths. The two preceding rejected
reviews remain in history. Final review reported 97,999 tokens; isolated harness
lifetime is 544,549 with no usage uncertainty. The launch expires at
2026-09-26 18:49:38 UTC. The owner subsequently approved the fifth attempt above;
its approval is consumed. Camera footage can diagnose startup but cannot
substitute for native result frames. See
[preparation evidence](evidence/2026-09-26-native-webcam-preparation.json).

## Native failure diagnostics

The third attempt lost its unnamed boot log when the helper was stopped.
The host now retains one private, at most 64 KiB log per operation in the
helper state directory. A real synthetic worker-kill regression verifies that
the child's output remains readable; duplicate operations cannot overwrite it.
Explicit post-operation readback can publish the log as private evidence.
Target startup now prints fixed stage markers; an actual `main` path with no
UDC reports `stage=udc_wait` instead of only a generic timeout. Failed startup
holds the display for five seconds before the existing reboot request. The
150-second startup deadline and 180-second userspace watchdog are unchanged.

The host backend/helper-launcher run passed **30 tests in 1.08 seconds**;
the target boot/capture/identity run passed **31 tests in 8.40 seconds**.
Both independent crossreviews found no blocker. These checks use synthetic
devices, not the Mac. Host boot logs stop at the USB handoff; the new target
markers need an available console, whose actual visibility remains unqualified.
This change does not establish why native USB failed or qualify a round trip.
Rebuilding, exact review and fresh attended approval precede physical use.
See [diagnostic evidence](evidence/2026-09-26-native-diagnostics.json).

Clean source `350819d` produced `build_7307a7fbd37d412681afe9a3a4259fbb`.
The 179,701,760-byte payload SHA-256 is
`cf69035ee8f71491210a1d590d1b992ddf060ba2945012e911d51ea04a355936`.
Independent `gpt-6-sol` medium review passed **36 byte/content checks** with
zero mismatches: stored manifest/payload, boot files, exact packaged source,
embedded configuration and diagnostic bounds. The build emitted `created_at`
serializer warnings; stored artifact hashes and contents verified correctly.
This is a candidate, with physical native execution and return still pending.
Fresh exact review accepted procedure `056724af…0f3546`; its completed
`gpt-6-sol` medium job reported 90,606 tokens with no usage uncertainty.
Its fresh owner approval and attendance confirmation were consumed by the
fourth attempt above. All prior single-use test approvals are consumed.
The reviewed launch expires at
2026-09-26 18:12:32 UTC; expiry requires a newly bound reviewed proposal.
See [candidate evidence](evidence/2026-09-26-native-diagnostics-build.json).

## Third attended attempt: missed proxy window

At `083646a`, a fresh exact review accepted procedure `b50f8488…e17e3a`
using `gpt-6-sol` medium (63,665 reported tokens, no usage uncertainty).
The owner approved one new three-sample test and confirmed attendance.
Fresh inspection and formal single-use approval preceded dispatch at 17:11:33 UTC.
No native ACM channel or sample capture was observed. Proxy USB appeared as
`ttyACM1` at 17:13:58 UTC and disappeared about five seconds later, while the
helper was waiting for native capture instead of watching return.

The host wait was stopped to arm a recovery catcher. This produced an honest
`unknown_effect` result. At 17:14:48 UTC the fixed identity-bound five-request
probe confirmed responsive proxy; the owner confirmed manual reboot. The attempt
had reached the normal installed OS before that manual reboot, according to the
owner's screen observation. It is reconciled as **failed** with its original
unknown outcome retained. This
establishes manual recovery only. No third-attempt boot log was retained after
the interrupted extraction and helper cleanup. The host now watches continuously
for a returned same-identity proxy during native startup/capture, including tty
renumbering. It requires fresh fixed observation, leaves proxy-only return unknown,
and ends child/watcher ownership before reporting. The changed configuration
digest requires new approval scope. **23 focused backend checks passed in 0.98s**;
independent code review found no blocking issue. This fix still needs fresh exact
review and a separately approved physical attempt. See
[watcher evidence](evidence/2026-09-26-native-return-watcher.json).
See [evidence](evidence/2026-09-26-native-third-attempt.json).

## First attended native attempt

The owner-approved three-sample attempt reached coordinator/helper dispatch.
The boot client failed opening nonexistent `/dev/m1n1`: the launcher supplied
`PORT`, while the documented m1n1 interface uses `M1N1DEVICE`. No native result
was received. The waiting helper was stopped; the initial `unknown_effect`
record was preserved and reconciled as **failed** using the saved traceback
and a successful same-device, five-request read-only proxy observation.
The corrected launcher binds `M1N1DEVICE` into its configuration digest and
retains a bounded boot-log tail/count/hash. Seventeen focused host tests pass.
This failure does not qualify native USB, reboot or recovery.
See [attempt evidence](evidence/2026-09-26-native-first-attempt.json).

## Single attended retry

The owner-authorized immediate retry used corrected launcher source `b971b9c`,
a fresh exact `gpt-6-sol` medium review, fresh proxy inspection and a single-use
attended approval. Operation `operation_efc39ae30ffd4a67a02aa924c2691759`
ran from 16:36:36 to 16:44:30 UTC on 2026-09-26. It ended **unknown_effect**:
zero captured samples, capture timeout and no observed return snapshot.
The boot client logged kernel handoff preparation, then exited 1 when pyserial
Miniterm tried terminal I/O on non-terminal stdin. This does not establish
whether Linux executed. Proxy USB interfaces disappeared; neither the native
ACM channel nor proxy return was observed. Target stop remains unverified.

The helper stopped normally after the terminal result. Raw diagnostics and the
typed result are retained; the first attempt remains reconciled as failed.
At 16:59:12 UTC, following the owner's manual reboot, the fixed identity-bound
five-request observation confirmed responsive m1n1 proxy. The retry was then
reconciled as **failed**, preserving its original unknown outcome and all evidence.
This is manual recovery evidence; no automatic native return was demonstrated.
No additional native boot is authorized or dispatched. The host fix supplies
private PTY stdin, requests Miniterm exit after capture, and preserves bounded
cleanup and conservative success conditions. Its configuration digest changes.
The regression first reproduced errno 25 with a real subprocess; the corrected
path passed that regression and an actual installed pySerial 3.5 Miniterm test
against `loop://`. The focused backend suite passed **19 tests in 0.46 seconds**;
independent code review found no blocking issue. This is host evidence; a fresh
exact review and owner approval must precede another physical test. See
[terminal-fix evidence](evidence/2026-09-26-native-terminal-fix.json).
The installed `f560929` lab remains paused with its usage hold; science remains
stopped. See [retry evidence](evidence/2026-09-26-native-retry.json).

## Host-only gate

- The attended native path now connects coordinator admission, typed helper
  dispatch, verified bundle staging, the fixed pinned tethered boot client,
  bounded ACM capture and re-observed proxy return. `native-inspect` and
  `native-run` require an explicit session; only the latter enables the
  qualification gate. Exact review, single-use attended approval, durable
  duplicate refusal and unresolved accounting/operation gates remain active.
  The helper reports `qualified=false`; its epoch identifies the owned proxy
  connection, not independently attested boot state. Raw evidence precedes
  interpretation, and absent/mismatched return stays unknown.
  `.venv/bin/python -m pytest -q` passed **313 tests in 38.60 seconds** on the
  ThinkPad using `gpt-6-sol` medium with host socket/process permissions. The
  initial run exposed one test fixture expecting IPC refusal where typed
  construction already refused; that assertion was corrected before this
  passing run. The final focused service/backend/launcher run passed **29 tests in
  2.16 seconds**, including the imported-client tree pin and a complete
  synthetic service round trip through the real helper IPC. The actual `3f75558` published payload also passed bundle staging.
  At this host checkpoint no physical native boot had been attempted; the
  subsequent physical outcomes are recorded above. No live service was deployed
  or resumed. The candidate's sample window now permits longer approval
  headroom without extending its finite sample duration; this target change
  is now built from `8b9ae1d` as `build_a790a2c29c0a4151b62b45862fd5a908`.
  Payload SHA-256 is
  `21f0fdbbea097af66b2b3310c85c80400329fb32880fe9e382277bb23194d686`.
  Independent exact-image review verified packaged source/configuration and
  boot-file digests with no blocking finding; this does not replace exact
  procedure review or physical approval. A separately accounted
  `gpt-6-sol` medium review then accepted the exact three-sample procedure
  `e07bf8af…a797`, with **48,086 reported tokens** and no usage uncertainty
  in the harness session. The installed live session retains its separate
  unresolved hold. That reviewed launch expired without dispatch; the separate
  fresh reviews and attended attempts are recorded above.
  See [dispatch evidence](evidence/2026-09-26-native-dispatch.json).
- The identity-enabled candidate at `3f75558` was rebuilt and session-linked.
  Its packaged configuration SHA matched the image manifest. The actual
  packaged ARM64 Python/collector ran under qemu-user with synthetic sysfs and
  boot UUID, streamed a complete capture through the host receiver and
  published both raw and screened artifacts. Linux kernel release in this
  emulation is the host's, not a Mac observation. The capture retains the
  Linux self-report while physical verification flags remain false.
  The native ACM transport now owns one configured tty, sends exactly one
  bounded launch, and applies one monotonic deadline to send plus receipt.
  Six synthetic PTY cases cover binding, cleanup, complete receipt, truncated
  receipt and ambiguous send without retry. The combined native test command
  recorded in [identity evidence](evidence/2026-09-26-native-identity.json)
  passed **54 tests in 17.43 seconds**. No physical native boot or live dispatch
  was enabled; reviewed coordinator/helper launch wiring and physical
  identity/channel/return qualification remain open.
- At source `520d05b`, the actual J313 RAM-only candidate was built and
  published into the separate `build/harness-state` journal with all package
  inputs and seven output artifacts. A second independent assembly matched
  every output SHA-256. The image uses pinned signed ALARM kernel/DTB/modules
  and 37 userspace packages; this reproduces assembly, not provider kernel
  compilation. ARM64 Python, BusyBox and kmod ran under qemu-user; all five USB
  module dependency trees resolved, and the exact collector emitted a complete
  synthetic framed capture. GNU cpio read the archive and its required files.
  `.venv/bin/python -m pytest -q tests/integration/test_native_boot.py
  tests/integration/test_native_cli.py` passed **8 tests in 3.65 seconds**.
  The latest full-suite result remains the 210-test checkpoint below.
  Native startup source review found no concrete blocker; exact artifact and
  procedure review remains required before dispatch. No Mac image was booted.
  USB ownership/channel, observed target boot/config identity, return and
  recovery remain pending. Both the separate harness build session and the
  existing live session are paused; the live usage hold remains intact.
  See [build evidence](evidence/2026-09-26-native-build.json) and
  [candidate instructions](NATIVE-HARNESS.md).
- At source `a16f31e` on 2026-09-26, the ThinkPad full suite passed
  **210 tests in 29.46 seconds**, no warnings reported, using
  `.venv/bin/python -m pytest -q` with host socket permissions through Codex
  `gpt-6-sol` medium. Sixteen new descriptor cases include a real synthetic
  collector child whose stdout flows into acquisition and coordinator artifact
  storage. They cover fragmented input, terminal completion without EOF,
  retained prefixes/frames on disconnect or timeout, slow input under one
  monotonic deadline, wire bounds, malformed/mismatched/trailing data, retained
  accepted samples before truncation, caller descriptor ownership, and shared
  sample-count screening. File and descriptor acquisition now use the same
  artifact publication boundary. Host receipt metadata leaves physical source,
  target identity, target capture timing and target stop unverified.
  Standards review found no hard violations and one optional named-fixture
  suggestion; independent spec review found no blocker for this increment.
  No device is opened by this library path, and it is not wired to live
  dispatch or a new CLI command. These tests do not demonstrate a physical
  native channel or recovery. A bounded local historical-input inventory found
  no usable native boot bundle; earlier ALARM SSH collection is historical
  evidence, not a standalone image result channel. The live lab was not
  resumed or modified, and its unresolved usage hold was not reconciled.
- At source `dae67b6` on 2026-09-26, the ThinkPad full suite passed
  **194 tests in 23.69 seconds**, no warnings reported, using
  `.venv/bin/python -m pytest -q` with host socket permissions through Codex
  `gpt-6-sol` medium. Fourteen new native capture cases run the standalone
  collector in a child process with synthetic snapshots, receive its actual
  framed stdout through a pipe, and publish/import real coordinator artifacts.
  They cover complete captures, payload-bound partial captures, retained
  damaged streams, mismatched run/boot echoes, missing samples, expired offline
  launches with live deadline refusal, ten-sample scheduling, startup headroom,
  and malformed saved collector parameters. This exposed and fixed the missing
  screening import, historical launch decoding, and a terminal reserve that
  systematically omitted final samples as the requested count grew.
  The first full-suite invocation did not start because automatic approval
  review timed out; the permitted retry produced the result above.
  No target data was collected and no physical channel or image is qualified.
  The installed service remains `f560929`, active with zero observed restarts;
  a read-only SQLite check confirmed the session is paused, lifetime tokens
  remain 0, and usage uncertainty remains set. That zero does not reconcile
  the interrupted provider turn's missing usage.
- At source `2032eee` on 2026-09-26, the ThinkPad full suite passed
  **180 tests in 17.73 seconds**, no warnings reported, using
  `.venv/bin/python -m pytest -q` with host socket permissions through Codex
  `gpt-6-sol` medium. Fourteen supervisor tests now include a kernel process
  handle for the current coordinator generation: dead/invalid handles refuse
  startup, generation changes during lookup refuse startup, and coordinator
  death ends a hung helper without restarting it. Twelve isolated maintenance
  cases retain the usage/unknown-effect gates and verify active-helper and
  owner-lock refusal, history preservation, and symlink/FIFO refusal.
  `bash -n scripts/release.sh` and `systemd-analyze verify
  systemd/m1-power-lab.service systemd/m1-power-lab-helper.service` passed using
  installed systemd 261.2. Standards and independent spec review found no
  blocking findings in this increment. The helper unit/configuration are
  prepare-only: no installation or device-cgroup/systemd lifecycle qualification
  is claimed. Prior physical helper evidence is tied to `b5b420d` below.
- At source `b5b420d` on 2026-09-26, the ThinkPad full suite passed
  **170 tests in 16.77 seconds**, no warnings reported, with
  `.venv/bin/python -m pytest -q` using host socket permissions through Codex
  `gpt-6-sol` medium. Thirteen deny-guard cases cover duplicate IDs/steps,
  restart after an actual child exit during execution, malformed/capacity/write
  failures, deadline expiry during persistence, and cleanup before unlocking.
  Eight supervisor cases cover repeated requests, startup/request/cleanup
  stalls, child crash, parent death both idle and during a hung request, and
  lock release. Four coordinator/IPC cases use a test-only replay fixture;
  the real helper client remains rejected by the experiment service.
  Standards review found no hard violations and one optional typed-event
  suggestion; independent spec review found no blocker for the inspect-only
  increment. These tests do not qualify physical crash/recovery behavior.
- At source `956a617` on 2026-09-26, the ThinkPad full suite passed
  **145 tests in 10.04 seconds**, with no warnings reported, using
  `.venv/bin/python -m pytest -q` with host socket permissions through Codex
  `gpt-6-sol` medium. Added coverage includes strict helper snapshot IPC,
  fixed proxy wire requests and deadlines over PTYs, USB identity refusal and
  probe process cleanup, configuration drift before and during execution, and
  four real temporary-Git build-runner cases. The build cases produce text
  fixtures, not M1 images. Physical evidence is recorded separately below.
  Standards review found no hard violations and one optional duplicated socket
  setup observation; the distinct inspection/dispatch outcome paths were kept.
  Spec review's bounded-inspection concern is resolved for the fixed observer
  and one-shot watchdog, and failed-completion reporting was corrected in
  `956a617`. Persistent helper supervision and real image builds remain gates.
- On 2026-09-26 the ThinkPad full suite passed **102 tests** with
  `.venv/bin/python -m pytest -q` (no warnings reported). Three new runtime
  cases verify the app-server resume request reasserts the read-only profile,
  workspace, model, medium effort, and never-approve policy, and that an absent
  or different active profile closes the adapter before `turn/start`. One new
  scripted scientific case preserves a lower-cost, discriminating proposal and
  its four-dimensional cost rationale across reopening while refusing dispatch
  before exact procedure review. These are synthetic host contracts; they do
  not demonstrate live provider resume, live Codex experiment selection, or
  physical target measurements. The first sandboxed full-suite attempt had
  78 passes and 24 socket-setup errors because that execution sandbox denied
  local listeners; the complete run passed with host socket permissions.
- Preceding full ThinkPad suite: **98 passed**, with no warnings reported; 24
  focused runtime/resume cases passed. The eight new cases cover interrupted
  and reconciled-unknown resume across reopening, actual synthetic subprocess
  EOF/malformed-output cleanup, cancellation of a shutdown caller, and event
  artifact failures with successful, failed, or cancelled cleanup. A historical
  unknown job first reproduced a stuck concurrency slot; three failure cases
  reproduced runtime work remaining active after an unknown outcome.
  Shutdown is now shared and shielded from caller cancellation. Unknown usage
  stays nonterminal and uncertain even when earlier response counts exist.
  Failed cleanup records diagnostics and retains the active job and reservation.
  Historical unknown outcomes remain in the journal after reconciliation but
  do not permanently occupy concurrency slots. Resume retains failed scientific
  evidence, brief, thread identity, read-only authority, and usage accounting.
  The final process check found no synthetic workers remaining. These tests
  do not qualify live provider resume or physical process/device behavior.
  The live service was separately confirmed active with its session paused,
  two historical jobs, and usage uncertainty still set; it remains `f560929`.
- The pinned Codex 0.156.0 standalone OS sandbox passed a no-model canary
  probe on the T480 in a separate transient `m1lab` systemd unit. The unit
  matched the deployed service's filesystem/device protections, including
  `RestrictSUIDSGID=no`, and had a 90-second runtime bound. It used a new
  synthetic HOME/CODEX_HOME, no credentials, and the same `m1lab-read-only`
  profile (`:root=deny`, `:minimal=read`, workspace read, network disabled).
  Workspace reading succeeded; outside and symlink reads were hidden;
  workspace writes returned read-only filesystem; outside writes were denied.
  IPv4, IPv6, filesystem Unix, and abstract Unix connections returned EPERM
  after all four unsandboxed listener controls passed. All synthetic canary
  hashes remained unchanged; the child started and completed successfully.
  The unit exited successfully in 290 ms. The fixture remains at
  `/var/lib/m1-power-lab/qualification-20260926a` on the T480.
  Binary SHA-256: `78a11f06e0a2dda42d13fba1d50dc62e8cbdb2d5f69789722f4d4d99b5cdbe30`.
  This qualifies the selected shared Linux sandbox behavior under these outer
  service restrictions. It does not qualify app-server tool routing, escalation
  handling, inherited descriptors, managed-config equivalence, actual devices,
  or live-model recovery. The probe did not change the production service or
  resume the paused lab session.
- The preceding T480 regression run: **90 passed**, with no reported warnings.
  Twenty new cases cover four SSE replay/reconnect/snapshot cases through a
  real temporary HTTP server and sixteen hardware-helper cases through real
  Unix sockets with a fixed synthetic backend. The SSE cases verify header
  cursor precedence, strictly-after replay, authoritative phase changes after
  reconnect, and malformed/ahead cursor recovery. Helper cases verify typed
  request/result lineage, protocol and capability checks, identity/boot/config
  rejection before backend entry, digest syntax and capture/frame bounds,
  exclusive ownership, and unknown outcome after backend disconnect without
  automatic replay. The focused HTTP/helper run passed all 24 cases.
  These checks do not qualify iPhone browser behavior, physical devices,
  artifact-content verification, or durable duplicate-dispatch prevention.
  The live service remains on `f560929`, paused with its usage hold intact.
- The preceding host regression run on the T480: **70 passed in 4.30 seconds**, with
  no pytest warnings. Eighteen new cases cover seven injected host-readiness
  faults, seven notification contracts with delivery stubbed, and four HTTP
  owner-interface contracts through a real temporary loopback server.
  Sampler failure first reproduced a broken owner view (17 passed, one failed);
  the view now reports unavailable readiness and remains accessible while work
  admission stays blocked. Fault tests verify pause, interruption requests,
  reservation release, and no automatic restart when readings recover.
  Push cases verify generic payloads, deduplication, revocation, expiry, and
  unchanged pending approvals after delivery failure. HTTP cases verify exact
  owner identity, CSRF/origin checks, uncached views, and idempotent/stale command
  handling. They do not qualify physical sensors, process termination, real
  push delivery, Tailscale policy, or the actual iPhone workflow. Published
  source includes these fixes; the deployed service remains `f560929` pending
  reconciliation of its usage hold.
- On 2026-09-26 the T480 ran 36 host tests and the replay demo. The installed
  `e6fc7ba` and `f58395f` loopback releases each served `/overview` as `m1lab`
  with HTTP 200 and zero restarts during their observed windows. The update,
  rollback, and return to `f58395f` passed the stopped-service maintenance
  check. The original session survived the update with its budget unchanged.
  The pre-update bundle restored into isolated `/tmp` state on the T480 and
  its CLI reported the same session with the full 3-hour / 100-million-token
  budget. Release `97363a8` also restored a fresh verified bundle over the
  stopped live data root as `m1lab`; after restart the CLI reported the same
  session and full budget, and the service returned HTTP 200 with zero
  restarts. Release `10934e9` subsequently completed an authenticated,
  host-only Codex turn on the T480 through the `m1lab` coordinator. Job
  `job_c4b06fe7f5f44710926be4d698c0f8b7` ended `completed` in proposal
  mode, with provider-reported usage of 19,816 tokens and no usage uncertainty.
  The replacement session `session_f73011ac092642b88fabdccbaba723ff` was
  stopped after qualification. A new owner-matched session
  `session_6419f91cb6c943af80b4f3ad9ad1c067` was initially paused, with the prior
  remaining token and time allowances carried forward conservatively. No
  physical M1 observation was made.
- The configured Codex executable SHA-256 is verified before app-server startup.
- Live app-server startup, authenticated completion, and terminal usage are
  demonstrated on the T480. A service-hosted turn also accepted cancellation
  and reached `interrupted`; terminal usage, sandbox escape checks, and recovery
  from interrupted live turns remain unqualified.
- A subsequent chat through the deployed `3c49b9e` service failed before a
  model turn: Bubblewrap reported `Can't mkdir parents for /: Function not
  implemented` while loading AGENTS.md. A thread-start-only probe in a
  temporary unit reproduced the same error in 2.497 seconds. Changing only
  `RestrictSUIDSGID` to `no` passed with active profile `m1lab-read-only` in
  1.800 seconds. Exact owner approval of this property change was received;
  release `f560929`, including service fix `193dd7e`, is now installed and
  the service is active with zero observed restarts. HTTPS `/overview` returns
  200 and push remains enabled and enrolled. Effective properties confirm
  `RestrictSUIDSGID=no`, `NoNewPrivileges=yes`, `PrivateDevices=yes`,
  `ProtectSystem=strict`, and `ProtectHome=yes`. A verified pre-update bundle
  was created before installation.
  The failed job `job_b9f0d62514ce4f54bf27a583f8d9c005` remains in history.
  Its usage hold was resolved with a zero additional token bound using the
  [pinned Codex source](https://github.com/openai/codex/blob/rust-v0.156.0/codex-rs/core/src/session/session.rs#L1391): the AGENTS.md refresh failure aborts before model
  client construction, prewarming, or submission-loop creation. This
  evidence applies only to that exact failure; generic internal RPC errors
  remain uncertain. The session was paused after this failure.
- On release `f560929`, one controlled service-hosted `gpt-6-sol` medium
  turn reached running and accepted an HTTPS interruption request (202) after
  ten seconds. Job `job_8d593331ce6f4e2b8e1d6ba95cf58cd2` reached
  `interrupted`; token and active-time reservations were released. The session
  was then confirmed paused. Provider usage was not reported, so usage remains
  uncertain and new model admission remains blocked. No usage bound was
  invented, no retry launched, and the earlier unknown job remains in history.
  This demonstrates cancellation and conservative accounting behavior, not
  complete interrupted-turn usage reconciliation or recovery.
- Read-only follow-up inspected this job's five captured event summaries and
  two runtime artifacts: no `thread/tokenUsage/updated` event or numeric usage
  was present. The matching Codex rollout contained one `token_count` entry
  with `info=null`, followed by an aborted turn. This supports missing upstream
  usage rather than a demonstrated lost-count defect in the adapter.
  The pinned runtime records usage on response completion and may cancel before
  that point ([stream handling](https://github.com/openai/codex/blob/rust-v0.156.0/codex-rs/core/src/session/turn.rs#L2724)); app-server emits usage only when token information exists
  ([event handling](https://github.com/openai/codex/blob/rust-v0.156.0/codex-rs/app-server/src/bespoke_event_handling.rs#L1546)).
  Elapsed time and absent output do not establish a zero or bounded token count;
  the usage hold remains in place.
- On 2026-09-26 the T480 passed three synthetic scientific-cycle integration
  cases, eight maintenance regression cases, and the full suite of 49 tests
  in 2.85 seconds. Science cases cover decision lineage, evidence and brief
  persistence on reopening, and redesign after two valid inconclusive results,
  including an intervening invalid result. They use no model calls or physical
  M1 evidence. M3 remains partial: they do not demonstrate a changed leading
  explanation, selection between experiments by cost, closure of a contradicted
  hypothesis, or job restart without expanded authority. Maintenance cases
  preserve historical unknown jobs, permit maintenance after usage resolution,
  and retain guards for active jobs, operations, reservations, and active time;
  mocked service/account commands do not qualify live process cleanup.
- A follow-up synthetic regression reproduced a separate accounting defect:
  an earlier response count could be accepted as final after interruption of a
  later response. Interrupted counts now remain nonterminal and uncertain while
  retaining the known token total. Both missing-count and earlier-count cases
  verify blocked admission, released reservations, and persisted state after
  reopening. The science suite also demonstrates a scripted A-supporting →
  A-below-target closure decision → B-supporting sequence, with changed brief
  and immutable decision history. Closure is a recorded conclusion, not an
  enforced hypothesis state. The latest T480 run passed 20 focused cases and
  all 52 tests in 3.19 seconds. These changes are published source; the service
  remains on `f560929` until its usage hold is reconciled for maintenance.
- Opt-in lab mode on release `3c49b9e` acquired a logind block inhibitor for
  `sleep:idle:handle-lid-switch` as `m1lab` while the service was active and
  `/overview` returned HTTP 200. The inhibitor disappeared after service stop;
  restoring the original environment and restarting left the service active,
  `/overview` at HTTP 200, and no M1 Power Lab inhibitor. The initial attempt
  without the service-account Polkit rule failed with an interactive
  authorization error. Actual T480 lid behavior remains untested.
- Tailscale Serve on the T480 proxies HTTPS to the loopback-only service.
  On 2026-09-26, local requests with a missing or incorrect
  `Tailscale-User-Login` returned HTTP 403, while the configured owner login
  returned HTTP 200. An HTTPS request to the tailnet Serve address returned
  HTTP 200; the service was active and its environment file had mode 0600.
  Serve status showed the proxy and no public Funnel entry. Full iPhone
  workflows, mobile layout, reconnection, push delivery, and tailnet policy remain
  unqualified.
- The T480 has a stable VAPID key pair in the private service state directory:
  the private key is owned by `m1lab` with mode 0600, and the service
  environment is root-owned with mode 0600. After restart, the HTTPS push
  config endpoint returned HTTP 200 with `enabled=true`, `enrolled=false`,
  and a valid 87-character base64url public key. The service remained active
  and HTTPS `/overview` returned HTTP 200. The owner subsequently reported
  iPhone enrollment, and a fresh HTTPS config request confirmed
  `enabled=true`, `enrolled=true` with the service active. Actual delivery,
  revocation, and offline behavior remain unqualified.
- Replay operations preserve intent, completion and unknown-effect outcomes.
- Stale revisions, revoked approvals and exhausted budgets fail closed.
- Coordinator restart reconciles incomplete jobs, operations and artifacts.
- `m1lab replay-demo` completes read-only and mutating replay procedures through exact review, approval, typed execution, immutable scientific evidence, and matching CLI/web readback.
- `m1lab export`, `m1lab backup`, `m1lab reconcile`, and lifecycle/budget controls remain usable without the web UI.

## Live transport gate

- At 13:04:58 UTC on 2026-09-26, the persistent helper at `b5b420d`
  completed two read-only inspections over the real USB/IPC path. Both matched
  the locally recorded USB identity and retained `qualified=false`, no boot
  epoch and no capabilities. SIGTERM to the supervisor produced normal exit
  0, removed the socket and released the owner lock. Its deny journal stayed
  empty: no dispatch was attempted. The
  [redacted evidence](evidence/2026-09-26-persistent-helper.json) establishes
  persistent inspection and normal shutdown on this connection, not physical
  failure recovery, coordinator dispatch, or native transport. No installed
  service change or scientific investigation occurred.
- At 12:46:06 UTC on 2026-09-26, the inspect-only harness at `956a617`
  completed one physical observation through a separate helper and the real
  Unix-socket client. It checked topology/interface/VID/PID and hashed USB
  serial, held the tty exclusively during the check, completed five fixed
  requests, and exited normally. It returned chip `0x8103`, base `0x805574000`,
  and bootargs address `0x805cac088`; `qualified=false`, no boot epoch and no
  capabilities were retained. No existing serial holders were found before
  opening. This is limited helper-path evidence, not full exclusive-ownership
  failure qualification or reviewed coordinator dispatch. See the
  [recorded output](evidence/2026-09-26-proxy-helper.json) and
  [probe contract](PROXY-HARNESS.md). Current owner scope is harness development
  and end-to-end verification; scientific investigation is not authorized to
  start at this stage. The installed `f560929` service remains separate, active
  with zero observed restarts, and its paused session/usage hold was preserved.
- Physical inventory is partial. An owner-authorized direct setup probe on
  2026-09-26 caught USB `1209:316d` during boot and completed NOP and identity
  queries against m1n1 `v1.6.1` on the M1 MacBook Air. Host checkout tag also
  reports `v1.6.1`; exact target build identity remains unverified. This probe
  bypassed the application path by explicit owner request and does not qualify
  coordinator dispatch, exclusive helper ownership, boot epochs, recovery,
  native results, or measurement. See [lab inventory](LAB-INVENTORY.md).
- The exact target and boot epoch can be identified.
- Host and target m1n1 builds match.
- Only the hardware helper owns the selected USB/serial interfaces.
- Proxy, hypervisor and native capabilities are recorded separately.
- No mutating operation is replayed after an ambiguous disconnect.

## Native measurement gate

- A finite image plus launch manifest returns attributable results.
- The standalone target collector emits framed raw sysfs observations and is
  integrated into the pinned RAM-only candidate. Execution and result capture
  from that image on the physical M1 remain unproven.
- Offline `m1lab native-import` validates framing and lineage but leaves physical source and capture timing unverified; it does not satisfy the live-result gate.
- Return or physical recovery is demonstrated for the selected mode.
- Sensor provenance, cadence, energy boundary and observer effect are known.
- The native desktop fixture can resolve the intended improvement with a predeclared method.

The application must continue to label these gates unqualified until evidence from the actual ThinkPad and Mac is committed.
