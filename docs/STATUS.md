# Qualification status

This file distinguishes implemented behavior from physical qualification.

Owner-selected coordination uses the installed Agents Orchestrator on
`gpt-6-astra` with `xhigh` reasoning. All other development and review agents use
`gpt-6-sol` with medium reasoning. One integration owner controls commits and
physical dispatch; the orchestrator assigns bounded tasks against the existing plan.

The seventh attended attempt again returned automatically to the caught proxy,
with no native samples. Its log/video are retained and the original unknown is
reconciled as failed. Independent Linux source inspection identified a concrete
gadget bug: configfs resolves symlink targets from process cwd, while the target
used a path relative to the link's parent. The function link now uses its absolute
path. A regression reproduced the old `ENOENT`; all eight native boot tests pass.
The next delivery step is rebuilding this fix and verifying capture/return on M1.
See [seventh-attempt evidence](evidence/2026-09-26-native-seventh-attempt.json).

The sixth separately approved attended attempt booted Linux and returned to
proxy; the watcher caught it and the owner confirmed no manual reboot. No native
samples were captured. Its 23,960-byte boot log and 30.937-second private webcam
video are retained. The video shows diagnostic lines, but the exact failure stage
and type remain too blurred to transcribe reliably. The original unknown result
is retained and reconciled as failed. The spent helper correctly withdrew launch
capability after this attempt while retaining proxy observation. All six test
approvals are consumed. See [sixth-attempt evidence](evidence/2026-09-26-native-sixth-attempt.json).

The exact candidate kernel includes `TER16x32`. Fixed boot arguments now select
that font to address the unreadable console evidence; 30 backend/launcher checks
passed. The target image is unchanged. Prior font selection and actual readability
remain unverified; the changed helper configuration needs fresh exact review and
attended approval. See [font evidence](evidence/2026-09-26-native-console-font.json).

Fresh exact review has now accepted font proposal `8acb0a44…e50ad30c`, with a
fresh owned helper and unchanged target image. Its subsequent attended approval
was consumed by the seventh attempt above. Earlier clock/recording-sequence review issues
are retained as history. See [review evidence](evidence/2026-09-26-native-font-review.json).

The fifth approved attended attempt stopped at the host helper before any boot
log was created. The helper from the fourth attempt had spent its one launch,
but still advertised the launch capability; its refusal surfaced as a transport
EOF. The 168 ms dispatch, unchanged proxy connection and private webcam recording
support this diagnosis. Zero native samples were captured. The original unknown
outcome is retained and reconciled as failed. The camera armed before dispatch
and stopped cleanly. All five approvals are consumed. See
[fifth-attempt evidence](evidence/2026-09-26-native-fifth-attempt.json).

Spent helpers now stop advertising native execution while keeping the returned
proxy available for observation. The one-launch guard is unchanged. A regression
reproduced the defect before the fix; 35 focused host checks passed afterward,
including refusal before adapter execution or approval consumption. The next
test requires a fresh helper and newly reviewed attended approval.

Before the sixth attempt, the spent helper stopped normally and a fresh proxy was acquired.
Exact review accepted `6b077c88…c9a9d4d` for the unchanged target candidate and
webcam scripts. The owner then approved the sixth test and confirmed attendance;
its outcome is above. See [review evidence](evidence/2026-09-26-native-fresh-helper-review.json).

The fourth attended test failed to capture native samples, but the continuous
watcher caught and held the returning proxy at 18:05:39 UTC. The owner confirmed
it returned by itself, without a manual reboot, and reported Linux penguins/logs
with M1Lab errors that passed too quickly to read. The full 23,960-byte boot log
survived and was published privately. The original `unknown_effect` is retained
and the attempt is reconciled as failed. Kernel handoff and USB disconnect are
logged; the exact native failure stage remains unknown. Bounded image/runtime
inspection identified no concrete packaging defect. The next useful evidence is
a recording of the existing target diagnostics during a separately approved run.
See [fourth-attempt evidence](evidence/2026-09-26-native-fourth-attempt.json).

The owner requested the ThinkPad webcam for the next diagnostic observation.
Its preview now contains the full console. The same candidate has a freshly
accepted exact proposal `d16b1906…e21ccef`: host camera frames must be captured
before dispatch, recording is bounded to 510 seconds/1 GiB, and explicit host
cleanup stops/reaps it. Two rejected preparation reviews remain recorded;
the corrected script bytes and procedure matched. The owner subsequently approved
one test and confirmed attendance; its fifth-attempt outcome is recorded above. See
[webcam preparation](evidence/2026-09-26-native-webcam-preparation.json).

The next candidate adds diagnostics for the demonstrated missing-evidence gap:
private boot logs survive helper death, and target startup emits fixed stage
markers with a five-second failure-only hold before its existing reboot request.
Thirty host backend/launcher checks and 31 target boot/capture/identity checks
passed; both independent crossreviews are clear. Console visibility on the Mac
is still unverified. Clean source `350819d` produced diagnostic candidate
`build_7307a7fbd37d412681afe9a3a4259fbb`; independent package review passed all
36 checks. Fresh exact review accepted procedure `056724af…0f3546` with 90,606
reported tokens in the isolated harness session, without usage uncertainty.
Its single attended approval was consumed by the fourth attempt above.
See [diagnostic evidence](evidence/2026-09-26-native-diagnostics.json)
and [candidate evidence](evidence/2026-09-26-native-diagnostics-build.json).

The third attended native attempt exposed a return-watching gap: proxy USB
appeared for about five seconds while the helper was still waiting for the
native channel. No samples were captured. The host wait was stopped; a bounded
catcher connected after the owner's manual reboot. The attempt is reconciled
as failed with its original unknown outcome retained. Continuous proxy-return
observation during native startup/capture is now implemented; 23 focused backend
checks pass and independent review found no blocking issue. The next gate is
fresh exact review and a separately approved physical test. See
[third-attempt evidence](evidence/2026-09-26-native-third-attempt.json).
The [watcher evidence](evidence/2026-09-26-native-return-watcher.json) remains host-only.

The first attended native attempt remains reconciled as failed. The owner-approved
single retry used the corrected device environment, a fresh exact review,
attendance approval and proxy check. It ended `unknown_effect`: zero captured
samples and no observed proxy return. The boot client reached kernel handoff
preparation, then failed initializing terminal I/O; target execution and stop
remain unverified for that attempt. The helper stopped normally. The owner's
subsequent manual reboot restored a responsive identity-bound proxy at 16:59:12 UTC;
the retry is now reconciled as failed with its original unknown result retained.
No further native boot was dispatched.
See [first-attempt evidence](evidence/2026-09-26-native-first-attempt.json) and
[retry evidence](evidence/2026-09-26-native-retry.json). The terminal integration
fix now passes 19 focused host checks, including real pySerial Miniterm over a
local loopback port. It supplies a private PTY and requests graceful console exit
after capture; fresh review and approval are required for its changed configuration.
The subsequent third-attempt outcome is recorded above. See
[fix evidence](evidence/2026-09-26-native-terminal-fix.json).

Current owner scope: build and verify the harness end to end using the m1n1
connection. Scientific investigation remains stopped. Source `520d05b` produced
a pinned J313 candidate through the session-linked builder; an independent
assembly matched all seven output digests. Eight focused native CLI/launch
checks passed. The identity-enabled candidate at `3f75558` also completed
ARM64 emulated collection through artifact publication; 54 combined native
checks passed at that checkpoint. The integrated attended path now passes
313 host tests; see qualification records for the command and scope.
The attended coordinator/helper native path is implemented, with explicit
CLI commands, immutable artifact staging, bounded boot/capture, raw retention
and observed proxy-return checks. It remains opt-in and unqualified pending
the real Mac round trip. Persistent physical helper inspection passed
on earlier source `b5b420d`. Separate helper service packaging is prepared;
installed service `f560929` and the paused lab usage hold are unchanged.

| Area | State | Evidence or next gate |
|---|---|---|
| Durable coordinator | Host implemented | SQLite journal, revisions, phase-aware budget exhaustion, exact approvals, reconciliation, and exclusive lease for standalone Codex turns |
| Replay experiment cycle | Host demonstrated | `m1lab replay-demo` records read-only and approved mutating paths, immutable scientific evidence and matching operator readback |
| Scientific records and reports | Host implemented | Versioned immutable records, frozen paired 10% / 95% decision rule, and Markdown report generation from validated records with provenance and explicit qualification limits |
| Codex scientific decision loop | Advisory brief, cost comparison, typed hypothesis/decision publication, draft/review boundary, redesign checkpoint gates, bounded/redacted evidence imports, one primary plus up to two budgeted helper jobs, and linked Markdown research reports implemented | Five synthetic science cases passed on the T480, covering decision lineage, durable briefs, redesign, a scripted change of leading explanation with recorded closure, and a scripted lower-cost discriminating proposal that persists but cannot dispatch without review. M3 remains partial: live Codex experiment selection/cost comparison and live provider resume are not demonstrated; synthetic reopen/resume preserves evidence, accounting, and read-only authority; live scientific decisions remain unqualified |
| Codex runtime | Standalone authenticated host-only turn qualified; approved service startup fix and live cancellation demonstrated | Release `10934e9` completed job `job_c4b06fe7f5f44710926be4d698c0f8b7` using pinned Codex 0.156 and `gpt-6-sol` medium, reporting 19,816 tokens. Later service chat exposed a Bubblewrap conflict with `RestrictSUIDSGID`; the controlled startup probe passed, exact owner approval was received, and release `f560929` is active and its controlled job reached `interrupted`. The session is paused with released reservations; missing provider usage correctly blocks new work. Synthetic transport cleanup, cancelled shutdown, reopen/resume, and failed-profile refusal now pass; the standalone OS sandbox passed synthetic canaries. Live interrupted-turn usage reconciliation, provider resume, and complete enabled-tool qualification remain pending |
| Owner CLI | Host implemented | Lifecycle, budgets, approvals, events, artifacts, jobs, operation and usage recovery, export, backup, replay and diagnostics |
| Owner web UI | Host rendered | Four responsive views, revisioned commands, SSE and local/Tailscale identity modes; real temporary HTTP tests cover owner/CSRF/origin checks, uncached views, duplicate/stale commands, cursor replay, reconnect, and snapshot recovery. Sampler failure now renders unavailable readiness. Approval cards expose recovery steps and risk rationale |
| Owner push notifications | Stable service-owned VAPID key configured on the T480; owner reported iPhone enrollment and HTTPS push config confirmed `enabled=true`, `enrolled=true` | Seven stubbed delivery cases cover generic payloads, deduplication, expiry/revocation, and workflow preservation; actual phone delivery, revocation, and offline behavior remain unqualified |
| ThinkPad service deployment | Release `f560929` installed on the T480 after exact owner approval and a verified backup; service active with zero observed restarts, HTTPS 200, and iPhone enrollment retained. Controlled cancellation ended with the session paused and a usage hold. Earlier update/rollback and isolated/live backup restore passed | [Operations guide](OPERATIONS.md); interrupted-turn usage reconciliation/recovery, uninstall, and longer availability checks remain pending |
| ThinkPad host inventory | T480 hardware, firmware, OS, CPU, memory, and available build tools observed on 2026-09-26; latest full suite: 313 passed, including native collector/acquisition/import, synthetic science, interruption accounting, maintenance, host-readiness faults, notification contracts, and HTTP owner controls; replay demo previously passed | These are host checks; USB enumeration and protocol version were separately observed, while exact cable/port mapping, target binary provenance, and recovery remain pending; [inventory](LAB-INVENTORY.md) |
| ThinkPad lab availability | T480 diagnostics observed AC, 62–63 °C, and about 7.7 GiB free. With release `3c49b9e`, opt-in logind `sleep:idle:handle-lid-switch` block inhibition was held while the service ran, released on stop, and absent after lab mode was turned off; `/overview` returned HTTP 200 before and after | Seven injected-readiness cases verify admission refusal, durable pause, interruption requests, reservation release, and no auto resume. Actual lid behavior, AC-loss, thermal-pressure, low-disk, shutdown, and longer availability still need T480 qualification |
| Tailscale on ThinkPad | Serve configured on the T480 on 2026-09-26 with exact owner login; HTTPS `/overview` returned HTTP 200, missing/wrong identity headers returned 403 on loopback, service remained active, and no public Funnel entry was enabled; iPhone enrollment subsequently confirmed | Tailnet policy and full iPhone workflows remain unqualified |
| iPhone 12 mini | Owner reported enrollment; server confirmed an active subscription | Verify all views, Home Screen behavior, reconnect and approval handling |
| ThinkPad-to-Mac transport | Direct setup and bounded helper/IPC inspection passed; full transport unqualified | USB-A to USB-C at topology `1-1`, USB `1209:316d`, interface `00`, hashed serial binding, chip `0x8103`. One-shot and persistent helper checks completed fixed read-only requests and exited cleanly, with socket removal and owner-lock release verified for the persistent path. Target version banner previously matched host release tag `v1.6.1`; exact target binary, boot epoch, reviewed coordinator dispatch, failure/recovery and native channel remain pending; see [probe evidence](evidence/2026-09-26-proxy-helper.json) |
| Hardware-helper boundary | Typed bounded IPC now includes inspect-only snapshots; fixed physical observer and one-shot supervised probe implemented | 42 socket/deny-guard cases, 11 PTY transport cases, 13 observer cases, 14 supervisor cases and 4 coordinator/IPC cases pass. Durable intent refusal survives actual process death; startup/request/cleanup stalls are bounded. Physical persistent inspections and normal shutdown passed, retaining no capabilities, no boot epoch and `qualified=false`. Separate service packaging is prepared with coordinator process binding and source maintenance guards; actual unit permissions/lifecycle, qualified dispatch and recovery remain pending; see [harness contract](PROXY-HARNESS.md) |
| Live m1n1 adapter | Autonomous selection disabled; explicit attended native qualification implemented | Exact reviewed artifacts and single-use attendance approval required. Physical native channel, return and recovery remain pending |
| Native run manifests and result channel | Host acquisition CLI and RAM-only J313 candidate implemented | Synthetic collector/acquisition/import checks cover complete/partial/unknown results, deadlines and retained bytes; 54 combined native checks pass. Actual packaged ARM64 collector streamed complete synthetic data plus observed Linux self-report into artifact storage. One-shot ACM ownership/exchange passes synthetic PTY checks. Physical source/timing, independent boot identity, reviewed dispatch and return/recovery remain pending. Explicit `native-run` now supplies the attended qualification route; normal startup remains disabled |
| Reproducible target builds | Actual pinned candidate assembled and session-linked at `520d05b` | Independent assembly matched all seven output hashes. Kernel/DTB/modules and 37 userspace packages are pinned; input bytes, provider metadata, source/recipe/tool and output digests are recorded. This reproduces assembly from signed binaries, not the provider kernel compilation. No qualified known-good image or physical return yet; see [build evidence](evidence/2026-09-26-native-build.json) |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.
