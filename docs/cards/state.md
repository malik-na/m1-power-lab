# State of the deep-sleep work (read this first)

Linux reaches macOS's commit conditions, but no wake has ever reached the boot CPU.
2026-11-20, after milestone 4: Aurora's pre-commit steps our entry lacked, all on together, do not start sequence 0 either (5 runs, 04 -> 04; the fifth with no device access after R38's third write). After milestone 3: the SEP gated as macOS's does not start sequence 0 either; by the stop condition the deep-sleep work stops. After milestone 2: the always-on program never starts its power-down (sequence 0) after our commit; every lead of milestones 1-2 is ruled out.

## Established

- With `cand=0xffffe` (C1-C18) the entry reaches its commit with the C3 words at macOS's `0x333/0x444/0x222` (record `44 56 43 32 24 43 f2 00 00 00`). [evidence 2026-11-17, ds28]
- `pmp` runs under Linux once its translator holds macOS's 34 MMIO windows and the opening region at IOVA `0x3c000` holds macOS's bytes. [evidence 2026-11-17, ds27p; spec R76, D17]
- No run comes back by itself: ds28, ds29 and the breadcrumb run all end at the `wdt` bite (165 s with `wdt=150`). [evidence 2026-11-17, ds28, ds29]
- No kernel wake marker (`'Dr'`, `'DA'`) and no loader breadcrumb (`0x9f0b` = 0): no wake reached the boot CPU. [evidence 2026-11-17, ds29 and breadcrumb sections]
- macOS on the same machine and firmware sleeps and wakes (hypervisor, wake status `+0x20=0x400000`). [evidence 2026-11-16-hv-macos135-s2r]

## The one open question

- After Linux's commit the always-on engine accepts the cores going idle, stops watchdog 2, and never enters sequence 0 (AWAKE->AOP_DDR). What does it wait on between the cores going idle and sequence 0's first write? Not any of milestone 2's leads (below). [docs/experiments/2026-11-20-m1-engine-sampler.md; docs/agents/milestone-2-report.md]
- The Secure Enclave is ruled out (milestone 3): gated as macOS's (`0x1000230f`) before the entry and at Linux's commit, `0x0201` 04 -> 04, back at 165 s. Differences from macOS remain (corrected after milestone 4): watchdog 1 is armed at the commit (macOS: control 0, though armed it still slept, R61) (the glue's SPMI record and re-arm after R38's third write were left out in milestone 4's run 5: no change); the cable is in with the M1 sourcing power on port 0. Not read: macOS's cluster words and `0x23d2b8008` at its commit; cores 1-7's pending state. [docs/agents/milestone-4-report.md]

## Milestone 4 readings (2026-11-20, 4 runs, none started sequence 0: `0x0201` 04 -> 04, back at 165 s)

- Aurora's last WFI on every core (timers masked, IPI_SR cleared), core 0's AIC ack, PS unlatch and `0x23d2b8008` = 0 before R22, every AIC line masked again after the commit write, all on together with the SEP gated and macOS's wake masks: no sequence 0 [2026-11-20-m4-deep-wfi.md, -ps-unlatch.md, -ap-deadline.md, -aic-after-commit.md].
- At core 0's last write: nothing pending on core 0 (FIQ, IRQ, timers, IPI); no BUSY-latched power-state word before R22; DEBUG_USB idle as macOS's with the cable in [run 1, k 173].
- Wake sources: pending and unmasked at core 0's last write in run 1 only; none in runs 3-4 (C14 met), no sequence 0 [2026-11-20-m4-pending-wake-source.md].
- With no device access from R38's third `0x23d2c4000` write to the cores' WFIs (no SPMI record, no watchdog-1 re-arm, no probe reads; m4fix bit 6), still 04 -> 04, back at 166 s: our write after the commit is ruled out [2026-11-20-m4-quiet-commit.md, run 5].
- macOS (existing captures): writes `0x23d2b8008` = 0 at T-18 ms (det36), as Linux with m4fix bit 3; cores 0-7 ISR 0, IPI_SR 0 at its commit (det18). Its cluster words at the commit: not read; on 2026-11-20 the macOS volume booted macOS natively, no m1n1 proxy, so no hypervisor run [2026-11-20-m4-macos-cluster-words.md].
- Not built: PMC voters (no t8103 word). Not run: the cable out (the software cut is not clearly safe for the M3; a pulled cable needs Naeem) [2026-11-20-m4-debug-link.md, -pmc-voters.md].

## Milestone 2 readings (2026-11-20, 8 runs, none started sequence 0: `0x0201` 04 -> 04, back at 165 s)

- The AOP told "AP power `0x201`" (echoed), alone or after the old driver's sensor and queue stops, with the SMC handshake succeeding: no sequence 0 [2026-11-20-m2-aop-ap-power.md, runs 3-4].
- At the commit 20 always-on words equal macOS's (AOP config, S2R timer, `0x23d2b8028`/`040`, watchdog 2, MSG, ATC1, NUB words); ATC0_USB_AON/ATC0_USB differ (off; macOS `0xff`) [2026-11-20-m2-commit-aon-compare.md, run 3].
- First USB-C port's domains left on as found; an L1 clean with the cache off before every core's WFI; both with the AOP's sequence: no sequence 0 [2026-11-20-m2-atc0-as-found.md, 2026-11-20-m2-core-cache-clean.md, runs 5-7].
- Core 0 held 20 or 50 ms: no watchdog-2 reset; 3 s: reset at 5 s. The engine's wait for the cores is between 50 ms and 3 s; Linux's 1.65 ms is inside it [2026-11-20-m2-engine-window.md, runs 1-2].
- P cluster `0x23b718004`: `0x10` at once, `0x50` 50 ms after cores 4-7 go down; the old driver's run 26 recorded P `0x50` too [2026-11-20-m2-p-cluster-50ms.md, run 8; power-domains.md].
- macOS's 11 SMC shared-memory writes after its last `0x23d2c4000` write are one slot of a 17-slot log ring, with no doorbell after: not a sleep step [coprocessors.md].

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
- Aurora's last WFI, AIC ack, PS unlatch, AP deadline 0, AIC mask after the commit, all together (milestone 4). [docs/agents/milestone-4-report.md]

## Decided

- Two lanes: probe (throw-away, experiment card, safety check) and build (clean-room, once per milestone, spec frozen). [docs/agents/probe-lane.md; docs/agents/cleanroom-cycle.md]
- Stop condition: if the next kernel build gives no solid next step, stop the deep-sleep work. [memory deepsleep-stop-condition, 2026-11-19]

## Decision (after milestone 3)

The last known difference, the SEP, is ruled out (run 5). By Naeem's stop condition (memory, 2026-11-19) the deep-sleep work stops here. [docs/agents/milestone-3-report.md]

## Where the code is

| Piece | Commit | Tests | Source |
|---|---|---|---|
| Logic | `~/Work/deepsleep-clean` `1b01552` | 333/333 on locked `45f1897` (round 10e) | [handoff-2026-11-19, State] |
| Logic tests r10f | `~/Work/deepsleep-tests-r10f` `80ec294` | not reviewed, not locked | [handoff] |
| Kernel (glue + logic + `pmp` client + wakemark) | `~/Work/deepsleep-kernel` main `52669b5bb` (ds29) | glue 147/148, one known stale test; round 3d and the merge not C-reviewed | [handoff; evidence ds29] |
| Client tests r4d | `~/Work/deepsleep-glue-tests-r4` `21cbbe9` | not reconciled with the client's interface | [handoff] |
| Spec | `docs/spec/macos-13.5-sleep-wake-observed.md` round 15f `9444f02` | ds27p-ds29 and the breadcrumb run not in it | [handoff] |
| Milestone 1 probes | `~/Work/dsk-probe-m1-leads` `probe/m1-leads` `6fe52a780` (k 76-143, `m1fix`, sampler) | probe lane, not reviewed, never merged | [docs/agents/milestone-1-report.md] |
| Milestone 2 probes | same worktree, `probe/m2-aop` `a9680e86b` (`m1aop`, k 144-169), `probe/m2-cache` `e1442a487` (`m1fix` bits 3-4); packages `var/kernels/m2aop/`, `var/kernels/m2cache/` | probe lane, safety-checked, never merged | [docs/agents/milestone-2-report.md] |
| Milestone 3 probe | same worktree, `probe/m3-sep` `ecbbcc4aa` (k 170-172 SEP words; `apple_sep.probe_sleep`); package `var/kernels/m3sep/` | probe lane, safety-checked, never merged | [docs/agents/milestone-3-report.md] |
| Milestone 4 probe | same worktree, `probe/m4-batch` `59394c943` (m4fix bits 0-4, k 173-184), `0ac81077f` (bit 5, k 185-189); packages `var/kernels/m4batch/`, `var/kernels/m4batch2/` | probe lane, safety-checked, never merged | [docs/agents/milestone-4-report.md] |
| Loader | `boot.bin` `0a1e47f3` (mb2 + SIO alias); breadcrumb `91d54c2` not installed | | [boot-chain.md] |

## Read more

- `docs/cards/INDEX.md`, `wake-path.md`, `run-recipes.md`, `boot-chain.md`
- `docs/agents/handoff-2026-11-19.md`
- `docs/experiments/2026-11-20-boot-loader-breadcrumb.md`
