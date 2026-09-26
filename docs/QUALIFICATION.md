# Qualification gates

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
  No physical native boot has occurred, and no live service was deployed or
  resumed. The candidate's sample window now permits longer approval
  headroom without extending its finite sample duration; this target change
  is now built from `8b9ae1d` as `build_a790a2c29c0a4151b62b45862fd5a908`.
  Payload SHA-256 is
  `21f0fdbbea097af66b2b3310c85c80400329fb32880fe9e382277bb23194d686`.
  Independent exact-image review verified packaged source/configuration and
  boot-file digests with no blocking finding; this does not replace exact
  procedure review or physical approval. See [dispatch evidence](evidence/2026-09-26-native-dispatch.json).
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
- The standalone target collector source emits framed raw sysfs observations; it has not been integrated into or run from an M1 image.
- Offline `m1lab native-import` validates framing and lineage but leaves physical source and capture timing unverified; it does not satisfy the live-result gate.
- Return or physical recovery is demonstrated for the selected mode.
- Sensor provenance, cadence, energy boundary and observer effect are known.
- The native desktop fixture can resolve the intended improvement with a predeclared method.

The application must continue to label these gates unqualified until evidence from the actual ThinkPad and Mac is committed.
