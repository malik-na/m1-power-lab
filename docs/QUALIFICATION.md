# Qualification gates

## Host-only gate

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
  `session_6419f91cb6c943af80b4f3ad9ad1c067` is paused, with the prior
  remaining token and time allowances carried forward conservatively. No
  physical M1 observation was made.
- The configured Codex executable SHA-256 is verified before app-server startup.
- Live app-server startup, authenticated completion, and terminal usage are
  demonstrated on the T480. Cancellation, sandbox escape checks, and recovery
  from interrupted live turns remain unqualified.
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
