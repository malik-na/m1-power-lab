# Milestone 2 brief: what the always-on engine waits on after Linux's cores go idle

Written 2026-11-20 at the end of milestone 1. For a fresh session, in the probe lane (`probe-lane.md`).

## Read first, in this order, and nothing bigger

`AGENTS.md`, `docs/cards/INDEX.md`, `docs/cards/state.md`, `docs/agents/milestone-1-report.md`,
`docs/agents/probe-lane.md`, `docs/agents/experiment-card.md`, `docs/cards/aurora-sleep-driver.md`,
`docs/cards/watchdogs.md`, `docs/cards/run-recipes.md`, and the five cards
`docs/experiments/2026-11-20-m1-*.md`. Open the spec, the evidence files and `var/recfg/` only by
section (grep, then read the range).

## Where milestone 1 left it

After Linux's commit the SoC never begins to power down. At the commit the always-on engine is in
sequence 12 (`0x23d2b8028` = `0x01000000`), with watchdog 2 armed for 5 s, the same as macOS. It takes
Linux's cores going idle (all down within 1.65 ms of the first `0x23d2c4000` write) and stops
watchdog 2, but never enters sequence 0 (AWAKE->AOP_DDR). There is no 5 s reset, and power-chip
`0x0201` is never 01. The run ends at watchdog 1. With core 0 held 3 s, the engine waits in sequence
12 and watchdog 2 resets the SoC about 5 s after the commit, the same as macOS with a core up.
Aurora's leads were each read and ruled out: wake masks, AMCC enables, gate records, DCS state,
timing. RVBAR is locked to the loader.

## The question

Between the engine's cores-idle check and sequence 0's first write (`0x23d2b8028` = 1, then
watchdog 2 armed), what does the engine wait on, and what stops watchdog 2 there?

## Leads (from milestone 1's recommendation; most likely first is judgment)

1. **Always-on control words at the commit, macOS against Linux:** the S2R timer block
   `0x23d2c4000`-`0ff`, the AON misc block `0x23d2b8000`-`0ff`, the AOP config `0x23d2c0000`-`0ff`
   (sequence 0 hands off to the AOP at `0x23d2c001c`), and the CPU cluster power-state words.
   macOS's side may already be in `var/recfg/commit-snap-list*.json` and the hypervisor captures.
   Linux's side needs one probe run (k table) or the `snap=1` path. Read-only first.
2. **The 11 SMC shared-memory writes** macOS makes after its third `0x23d2c4000` write
   (`0x23fe5f1f8`-`220`, spec around line 2086; the earlier 22 writes at `0x23fe5f098`, around
   line 2030). They carry kernel text addresses and differ between captures, so they look like a
   log. Linux makes none. Settle what they are before ruling them out.
3. **The engine's cores-idle window:** the sampler (`m1fix` bit 2) at 20 ms and 50 ms instead of
   3 s. If 20 ms gives no 5 s reset and 50 ms does, the window lies between them.
4. Anything the AOP must have done before sequence 0 starts (the AOP is running under Linux?
   `docs/cards/coprocessors.md`).

## Tools and state

- Probe branch: `~/Work/dsk-probe-m1-leads`, `probe/m1-leads` at `6fe52a780` (based on ds29
  `52669b5bb`). It has k 76-143 (masks, status, gate records, AMCC, timing, sampler), `m1fix` bits
  0-2 and `m1samp_ms`. The k table is in `probe.rs` and in the milestone-1 notes
  (`~/.config/Claude/side-session-notes/local_c530a88a-baf4-4edd-9e3d-d6fabe7bdf08/probe-m1-leads.md`).
  New probes go on this branch or a new `probe/*` branch. Never merge them.
- Packages: `var/kernels/m1leads/` (a18064d55), `var/kernels/m1samp/` (6fe52a780). Command lines:
  `var/deepsleep/m1l-*.cmdline`, `m1s-*.cmdline`.
- One run: `tools/tb/m1-claim take <who> "<why>"`, then
  `M1_CLAIM=<who> tools/tb/probe-run/onerun.sh <pkg> <tag> <cmdline> var/<dir>/<runN>`, then release.
  It reads `0x0201` before the sleep (`spmi_nvmem3` on test kernels) and the record after the reset.
  `tools/tb/m1-cand-runs`' start step failed twice on probe kernels; use `onerun.sh`.
- The record shows one 32-bit value (`probe_k`) per run. Pack what you need into one k.
- Decoded always-on program: `var/recfg/t8103-recfg-brief.txt`. Sequence i marks bit 2i on
  entry and 2i+1 on exit in `0x23d2b8028`. A boot overwrites that word with 2, so it can't be read
  after a reset.

## Steps

As in `probe-lane.md`: prior art (`tools/prior-art.sh`), an experiment card per question before
any run, the smallest probe, a 5-minute safety check by a second agent, the run, the outcome on its
card, the finding on its fact card, one line to Naeem. A macOS reading comes first wherever macOS's
value is not recorded, with every needed reading in one hypervisor run (`run-recipes.md`).

## Budget

At most 12 sub-agents, 150M sub-agent tokens, 8 M1 runs, 1 hypervisor run. No build-lane work.
Tell Naeem at half.

## Done

Either sequence 0 starts after a Linux commit (`0x0201` = 01 after a run, or a 5 s reset with
every core down), or every lead above is ruled in or out by a reading (or a line saying why it
could not be read). `docs/cards/state.md` is updated, with a short recommendation. If a probe makes
the M1 wake by itself, stop and tell Naeem at once. Stop condition (memory, 2026-11-19): if this
milestone gives no solid next step, say so plainly and stop the deep-sleep work.
