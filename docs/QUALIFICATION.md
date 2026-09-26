# Qualification gates

## Host-only gate

- On 2026-09-26 the T480 ran 36 host tests and the replay demo. The installed
  `e6fc7ba` and `f58395f` loopback releases each served `/overview` as `m1lab`
  with HTTP 200 and zero restarts during their observed windows. The update,
  rollback, and return to `f58395f` passed the stopped-service maintenance
  check. The original session survived the update with its budget unchanged.
  The pre-update bundle restored into isolated `/tmp` state on the T480 and
  its CLI reported the same session with the full 3-hour / 100-million-token
  budget. Replacing the live data root and running the authenticated Codex
  runtime remain unqualified.
- The configured Codex executable SHA-256 is verified before app-server startup.
- Live app-server startup, authenticated job lifecycle, cancellation and usage remain unqualified until a bounded turn completes on the deployment host.
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
