# State of the deep-sleep work (read this first)

Linux reaches macOS's commit conditions, but no wake has ever reached the boot CPU.
2026-11-20, after milestone 1: the always-on program never starts its power-down (sequence 0) after our commit.

## Established

- With `cand=0xffffe` (C1-C18) the entry reaches its commit with the C3 words at macOS's `0x333/0x444/0x222` (record `44 56 43 32 24 43 f2 00 00 00`). [evidence 2026-11-17, ds28]
- `pmp` runs under Linux once its translator holds macOS's 34 MMIO windows and the opening region at IOVA `0x3c000` holds macOS's bytes. [evidence 2026-11-17, ds27p; spec R76, D17]
- No run comes back by itself: ds28, ds29 and the breadcrumb run all end at the `wdt` bite (165 s with `wdt=150`). [evidence 2026-11-17, ds28, ds29]
- No kernel wake marker (`'Dr'`, `'DA'`) and no loader breadcrumb (`0x9f0b` = 0): no wake reached the boot CPU. [evidence 2026-11-17, ds29 and breadcrumb sections]
- macOS on the same machine and firmware sleeps and wakes (hypervisor, wake status `+0x20=0x400000`). [evidence 2026-11-16-hv-macos135-s2r]

## The one open question

- After Linux's commit the always-on engine accepts the cores going idle, stops watchdog 2, and never enters sequence 0 (AWAKE->AOP_DDR). What does it wait on between the cores going idle and sequence 0's first write? [docs/experiments/2026-11-20-m1-engine-sampler.md; 2026-11-20-m1-sequence1.md]

## Milestone 1 readings (2026-11-20, 5 runs)

- Watchdog 2 armed (control 4) and `0x23d2b8028` = `0x01000000` (sequence 12) just before Linux's first `0x23d2c4000` write, as macOS [2026-11-20-m1-engine-start.md; R62].
- Sequence 0 never starts after Linux's commit: it arms watchdog 2 for 5 s first and only sequence 1 disarms it after writing `0x0201` = 01; no clean-room run has reset at 5 s or left `0x0201` = 01 (04 -> 04 read before and after) [2026-11-20-m1-sequence1.md; var/recfg/t8103-recfg-brief.txt; records.md].
- Core 0 held 3 s after cores 1-7 go down: nothing moves (sequence 12, progress `0x20`, watchdog 2 counting) and watchdog 2 resets the SoC about 5 s after the commit, as macOS with a core up. All cores down within 1.65 ms: no watchdog-2 reset [2026-11-20-m1-engine-sampler.md; 2026-11-20-m1-commit-timing.md].
- Aurora's leads, each read on the M1: wake masks at macOS's values change nothing; AMCC error enables already off at the commit; gate records `0x23b71c090`/`360` as at macOS's commit; DCS state 4 reached (C3 words); cpu0 RVBAR locked to the loader (`0x00100008025dc001`); PMC voters not nameable on t8103 [cards/aurora-sleep-driver.md, "Read on the M1"].

## Tried and ruled out (each alone did not bring a wake)

- 2026-11-07/08 driver: stage-2 reset path, RVBAR page, cable, SMC handshake, AOP, MCC flush, alarm programming, nub-spmi IRQ setup, PMP idle, macOS's wake masks. [evidence 2026-11-07-linux-s2r, "Where this leaves it", "The last three Linux runs"]
- Clean-room driver: each candidate C1-C17 alone, all but C3/C5, all C1-C17, then + C18 (`pmp` client): commit reached, no wake. [evidence 2026-11-17, ds20, ds21, ds28]
- Kernel wake markers (ds29) and the loader breadcrumb (2026-11-20). [wake-path.md]
- Aurora's wake masks and AMCC enable clearing before the commit (run 3, 2026-11-20). [2026-11-20-m1-masks-amcc.md]

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
| Milestone 1 probes | `~/Work/dsk-probe-m1-leads` `probe/m1-leads` `6fe52a780` (k 76-143, `m1fix`, sampler) | probe lane, not reviewed, never merged | [docs/agents/milestone-1-report.md] |
| Loader | `boot.bin` `0a1e47f3` (mb2 + SIO alias); breadcrumb `91d54c2` not installed | | [boot-chain.md] |

## Read more

- `docs/cards/INDEX.md`, `wake-path.md`, `run-recipes.md`, `boot-chain.md`
- `docs/agents/handoff-2026-11-19.md`
- `docs/experiments/2026-11-20-boot-loader-breadcrumb.md`
