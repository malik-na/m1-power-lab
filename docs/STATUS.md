# Qualification status

This file distinguishes implemented behavior from physical qualification.

| Area | State | Evidence or next gate |
|---|---|---|
| Durable coordinator | Host implemented | SQLite journal, revisions, phase-aware budget exhaustion, exact approvals, reconciliation, and exclusive lease for standalone Codex turns |
| Replay experiment cycle | Host demonstrated | `m1lab replay-demo` records read-only and approved mutating paths, immutable scientific evidence and matching operator readback |
| Scientific records and reports | Host implemented | Versioned immutable records, frozen paired 10% / 95% decision rule, and Markdown report generation from validated records with provenance and explicit qualification limits |
| Codex scientific decision loop | Advisory brief, cost comparison, typed hypothesis/decision publication, draft/review boundary, redesign checkpoint gates, bounded/redacted evidence imports, one primary plus up to two budgeted helper jobs, and linked Markdown research reports implemented | One bounded authenticated host-only turn completed on the T480 as a proposal with recorded usage; a full evidence-to-next-decision cycle remains unqualified |
| Codex runtime | Authenticated host-only turn qualified | Release `10934e9` completed job `job_c4b06fe7f5f44710926be4d698c0f8b7` using pinned Codex 0.156 and `gpt-6-sol` medium; provider reported 19,816 tokens with no usage uncertainty. SHA-256 pinning, restricted permission profile, and budgeted supervisor are implemented; host sandbox escape and interruption behavior still need T480 qualification |
| Owner CLI | Host implemented | Lifecycle, budgets, approvals, events, artifacts, jobs, operation and usage recovery, export, backup, replay and diagnostics |
| Owner web UI | Host rendered | Four responsive views, revisioned commands, SSE and local/Tailscale identity modes; approval cards expose recovery steps and risk rationale |
| Owner push notifications | Explicit subscription management and generic deduplicated delivery implemented | VAPID configuration and actual iPhone delivery remain unqualified |
| ThinkPad service deployment | Release `3c49b9e` installed on the T480; after the authenticated host-only turn and inhibitor check the service was active with `/overview` returning HTTP 200. Earlier update/rollback and isolated/live backup restore passed; the owner-matched replacement investigation session is paused | [Operations guide](OPERATIONS.md); uninstall and longer availability checks remain pending |
| ThinkPad host inventory | T480 hardware, firmware, OS, CPU, memory, and available build tools observed on 2026-09-26; 36 host tests and replay demo passed there | USB enumeration, cable/port mapping, m1n1 revisions, and physical recovery remain pending; [inventory](LAB-INVENTORY.md) |
| ThinkPad lab availability | T480 diagnostics observed AC, 62–63 °C, and about 7.7 GiB free. With release `3c49b9e`, opt-in logind `sleep:idle:handle-lid-switch` block inhibition was held while the service ran, released on stop, and absent after lab mode was turned off; `/overview` returned HTTP 200 before and after | Five-second readiness supervision is implemented; actual lid behavior, AC-loss, thermal-pressure, low-disk, shutdown, and longer availability still need T480 qualification |
| Tailscale on ThinkPad | Serve configured on the T480 on 2026-09-26 with exact owner login; HTTPS `/overview` returned HTTP 200, missing/wrong identity headers returned 403 on loopback, service remained active, and no public Funnel entry was enabled | Tailnet policy and access from the iPhone remain unqualified |
| iPhone 12 mini | Pending physical check | Verify all views, Home Screen install, reconnect and approval handling |
| ThinkPad-to-Mac transport | Unqualified | Identify cable/ports, m1n1 versions, target identity, boot epoch and exclusive helper ownership |
| Hardware-helper boundary | Versioned bounded codec, deadline-bound Unix IPC, same-UID peer checks, exclusive owner lock, pre-dispatch identity/configuration/capability validation, and a stoppable connection loop implemented | No fixed physical backend or production service wiring yet; device selection, helper ownership, and recovery await T480 inventory and qualification |
| Live m1n1 adapter | Disabled | Implement only after transport and recovery qualification |
| Native run manifests and result channel | Host launch preparation/import and standalone target collector source implemented | Immutable image/launch manifests, bounded checksummed frames, launch artifact creation, offline raw-stream preservation, strict schema-checked and canonicalized collector-record views with requested sample-count reconciliation, and a read-only raw-sysfs producer are available; frame echoes verify launch binding only, while offline imports mark target identity, physical source, and capture timing unverified and keep raw frames out of model context; M1-specific image integration, independent live identity, live channel, return/re-identification, sensor qualification, and recovery remain pending |
| Reproducible target builds | Host runner implemented | Typed recipes, detached worktrees, exact source diffs, tool versions, configuration/input/output hashes, session-linked immutable artifacts, and active-time/disk bounds are implemented; an M1-specific recipe and T480 cross-toolchain inventory remain pending |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.
