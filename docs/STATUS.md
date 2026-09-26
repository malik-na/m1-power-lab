# Qualification status

This file distinguishes implemented behavior from physical qualification.

| Area | State | Evidence or next gate |
|---|---|---|
| Durable coordinator | Host implemented | SQLite journal, revisions, budgets, exact approvals, reconciliation |
| Replay experiment cycle | Host demonstrated | `m1lab replay-demo` records target, review, dispatch and immutable results |
| Scientific records | Host implemented | Versioned immutable records and frozen paired 10% / 95% decision rule |
| Codex runtime | Implemented, opt in | Read only app-server adapter and budgeted job supervisor; authenticated live call still needs host qualification |
| Owner CLI | Host implemented | Lifecycle, budgets, approvals, events, artifacts, jobs, operation and usage recovery, export, backup, replay and diagnostics |
| Owner web UI | Host rendered | Four responsive views, revisioned commands, SSE and local/Tailscale identity modes |
| Tailscale on ThinkPad | Pending physical setup | Configure Serve, exact owner login and tailnet policy; verify no Funnel |
| iPhone 12 mini | Pending physical check | Verify all views, Home Screen install, reconnect and approval handling |
| ThinkPad-to-Mac transport | Unqualified | Identify cable/ports, m1n1 versions, target identity, boot epoch and exclusive helper ownership |
| Live m1n1 adapter | Disabled | Implement only after transport and recovery qualification |
| Native result channel | Unqualified | Demonstrate finite harness result and return/re-identification |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.
