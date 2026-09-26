# Qualification status

This file distinguishes implemented behavior from physical qualification.

| Area | State | Evidence or next gate |
|---|---|---|
| Durable coordinator | Host implemented | SQLite journal, revisions, budgets, exact approvals, reconciliation |
| Replay experiment cycle | Host demonstrated | `m1lab replay-demo` records read-only and approved mutating paths, immutable scientific evidence and matching operator readback |
| Scientific records | Host implemented | Versioned immutable records and frozen paired 10% / 95% decision rule |
| Codex scientific decision loop | Advisory brief, cost comparison, typed decision publication, draft/review boundary, and redesign checkpoint gates implemented | Live model turn and evidence-to-next-decision cycle remain unqualified until a bounded authenticated turn runs on the ThinkPad |
| Codex runtime | Implemented, opt in | SHA-256 pinned, read only app-server adapter and budgeted job supervisor; authenticated live turn still needs host qualification |
| Owner CLI | Host implemented | Lifecycle, budgets, approvals, events, artifacts, jobs, operation and usage recovery, export, backup, replay and diagnostics |
| Owner web UI | Host rendered | Four responsive views, revisioned commands, SSE and local/Tailscale identity modes |
| Owner push notifications | Explicit subscription management and generic deduplicated delivery implemented | VAPID configuration and actual iPhone delivery remain unqualified |
| ThinkPad service deployment | Guarded immutable release install and rollback implemented; host deployment pending | [Operations guide](OPERATIONS.md); install, service readiness, release rollback, restore, and uninstall are not yet qualified on the T480 |
| ThinkPad lab availability | AC, thermal, and disk blockers gate and supervise Codex jobs; opt-in systemd sleep/lid inhibitor and status reporting implemented | Five-second readiness supervision pauses and interrupts active Codex work; inhibitor acquisition/release, actual sensor, AC-loss, thermal-pressure, and shutdown behavior still need T480 qualification |
| Tailscale on ThinkPad | Pending physical setup | Configure Serve, exact owner login and tailnet policy; verify no Funnel |
| iPhone 12 mini | Pending physical check | Verify all views, Home Screen install, reconnect and approval handling |
| ThinkPad-to-Mac transport | Unqualified | Identify cable/ports, m1n1 versions, target identity, boot epoch and exclusive helper ownership |
| Hardware-helper wire protocol | Versioned bounded request/result codec, strict length-prefixed framing, and blocking short-read/write handling implemented | Transport deadlines remain caller-owned; no helper server owns a device yet; physical interface selection and exclusivity await T480 inventory |
| Live m1n1 adapter | Disabled | Implement only after transport and recovery qualification |
| Native result channel | Unqualified | Demonstrate finite harness result and return/re-identification |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.
