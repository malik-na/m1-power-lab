# Qualification gates

## Host-only gate

- Latest T480 regression run: **90 passed**, with no reported warnings.
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

- Physical inventory is partial: T480 host facts have been observed, but the
  cable, USB identity, target mode, m1n1 revisions, and recovery remain
  unqualified. See [lab inventory](LAB-INVENTORY.md).
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
