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
| ThinkPad lab availability | AC, thermal, disk, and explicitly requested inhibitor state gate and supervise Codex jobs; opt-in systemd sleep/lid inhibitor and status reporting implemented | Five-second readiness supervision pauses active phases and interrupts live Codex jobs while preserving review/approval waits; inhibitor acquisition/release, actual sensor, AC-loss, thermal-pressure, and shutdown behavior still need T480 qualification |
| Tailscale on ThinkPad | Pending physical setup | Configure Serve, exact owner login and tailnet policy; verify no Funnel |
| iPhone 12 mini | Pending physical check | Verify all views, Home Screen install, reconnect and approval handling |
| ThinkPad-to-Mac transport | Unqualified | Identify cable/ports, m1n1 versions, target identity, boot epoch and exclusive helper ownership |
| Hardware-helper boundary | Versioned bounded codec, deadline-bound Unix IPC, same-UID peer checks, exclusive owner lock, and pre-dispatch identity/configuration/capability validation implemented | No fixed physical backend or service wiring yet; device selection, helper ownership, and recovery await T480 inventory and qualification |
| Live m1n1 adapter | Disabled | Implement only after transport and recovery qualification |
| Native run manifests and result channel | Host contract implemented | Immutable image/launch manifests, bounded checksummed frames, target identity binding, and unknown/partial capture handling are implemented; image build, live harness run, return/re-identification, and recovery remain physical gates |
| Reproducible target builds | Host runner implemented | Typed recipes, detached worktrees, exact source diffs, tool versions, configuration/input/output hashes, session-linked immutable artifacts, and active-time/disk bounds are implemented; an M1-specific recipe and T480 cross-toolchain inventory remain pending |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.
