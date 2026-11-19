# State of the deep-sleep work (read this first)

Linux reaches macOS's commit conditions, but no wake has ever reached the boot CPU.
2026-11-20. One open question: does the SoC power down at all after our commit?

## Established

- With `cand=0xffffe` (C1-C18) the entry reaches its commit with the C3 words at macOS's `0x333/0x444/0x222` (record `44 56 43 32 24 43 f2 00 00 00`). [evidence 2026-11-17, ds28]
- `pmp` runs under Linux once its translator holds macOS's 34 MMIO windows and the opening region at IOVA `0x3c000` holds macOS's bytes. [evidence 2026-11-17, ds27p; spec R76, D17]
- No run comes back by itself: ds28, ds29 and the breadcrumb run all end at the `wdt` bite (165 s with `wdt=150`). [evidence 2026-11-17, ds28, ds29]
- No kernel wake marker (`'Dr'`, `'DA'`) and no loader breadcrumb (`0x9f0b` = 0): no wake reached the boot CPU. [evidence 2026-11-17, ds29 and breadcrumb sections]
- macOS on the same machine and firmware sleeps and wakes (hypervisor, wake status `+0x20=0x400000`). [evidence 2026-11-16-hv-macos135-s2r]

## The one open question

- Never powers down, or powers down and is never woken (or woke with memory lost)? The M3's flat 8.1 W cannot tell. Settling read: a power-down signature in one sleep (`0x0201` after the reset, or the M1's own draw), and a positive control that the breadcrumb can write. [docs/experiments/2026-11-20-boot-loader-breadcrumb.md; evidence 2026-11-17, Observation round 4 table]

## Tried and ruled out (each alone did not bring a wake)

- 2026-11-07/08 driver: stage-2 reset path, RVBAR page, cable, SMC handshake, AOP, MCC flush, alarm programming, nub-spmi IRQ setup, PMP idle, macOS's wake masks. [evidence 2026-11-07-linux-s2r, "Where this leaves it", "The last three Linux runs"]
- Clean-room driver: each candidate C1-C17 alone, all but C3/C5, all C1-C17, then + C18 (`pmp` client): commit reached, no wake. [evidence 2026-11-17, ds20, ds21, ds28]
- Kernel wake markers (ds29) and the loader breadcrumb (2026-11-20). [wake-path.md]

## Decided

- Two lanes: probe (throw-away, experiment card, safety check) and build (clean-room, once per milestone, spec frozen). [docs/agents/probe-lane.md; docs/agents/cleanroom-cycle.md]
- Stop condition: if the next kernel build gives no solid next step, stop the deep-sleep work. [memory deepsleep-stop-condition, 2026-11-19]

## Where the code is

| Piece | Commit | Tests | Source |
|---|---|---|---|
| Logic | `~/Work/deepsleep-clean` `1b01552` | 333/333 on locked `45f1897` (round 10e) | [handoff-2026-11-19, State] |
| Logic tests r10f | `~/Work/deepsleep-tests-r10f` `80ec294` | not reviewed, not locked | [handoff] |
| Kernel (glue + logic + `pmp` client + wakemark) | `~/Work/deepsleep-kernel` main `52669b5bb` (ds29) | glue 147/148, one known stale test; round 3d and the merge not C-reviewed | [handoff; evidence ds29] |
| Client tests r4d | `~/Work/deepsleep-glue-tests-r4` `21cbbe9` | not reconciled with the client's interface | [handoff] |
| Spec | `docs/spec/macos-13.5-sleep-wake-observed.md` round 15f `9444f02` | ds27p-ds29 and the breadcrumb run not in it | [handoff] |
| Loader | `boot.bin` `0a1e47f3` (mb2 + SIO alias); breadcrumb `91d54c2` not installed | | [boot-chain.md] |

## Read more

- `docs/cards/INDEX.md`, `wake-path.md`, `run-recipes.md`, `boot-chain.md`
- `docs/agents/handoff-2026-11-19.md`
- `docs/experiments/2026-11-20-boot-loader-breadcrumb.md`
