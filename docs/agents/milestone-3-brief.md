# Milestone 3 brief: the Secure Enclave at Linux's commit

Written 2026-11-20 after milestone 2. For a fresh session, in the probe lane (`probe-lane.md`).
Naeem chose this test on 2026-11-20 ("Okay, let's do it.") knowing the stop condition: it is the
last known difference from macOS.

## Read first, in this order, and nothing bigger

`AGENTS.md`, `docs/cards/INDEX.md`, `docs/cards/state.md`, `docs/agents/milestone-2-report.md`,
`docs/agents/probe-lane.md`, `docs/agents/experiment-card.md`, `docs/cards/coprocessors.md`,
`docs/cards/power-domains.md`, `docs/cards/candidates.md` (C1), `docs/cards/watchdogs.md`,
`docs/cards/run-recipes.md`. Open the spec and the evidence files only by section (grep, then
read the range).

## Where milestone 2 left it

After Linux's commit the always-on engine never enters sequence 0; power-chip `0x0201` reads 04
before and after every run (01 would mean sequence 1 ran) and every run ends at watchdog 1,
165 s after the start with `wdt=150`. Every other lead is ruled out (milestone 1 and 2 reports).

What the cards record about the SEP:

- macOS sends `sep` no message; its domain `0x23b700c00` reads `0x1000230f` (power-gated by
  automatic power) awake and at the commit (`coprocessors.md` line 20, `power-domains.md` line 33).
- Under Linux before the entry it reads `0x1f0020ff` (fully on). Candidate C1 writes the domain
  to state 0 before R16, without a message (`candidates.md`).
- Milestone 2's report: the old driver sent the SEP a sleep message and waited for `0x23b700c00`
  to read gated before every entry, and some of its runs reached sequence 1. This is known
  second-hand only (`var/catchup/PLAN.md`, `var/catchup/hv-STATUS.md`). The report names side
  notes `old-vs-clean-entry.md`; no file of that name was found on 2026-11-20.
- Not read: `0x23b700c00` at Linux's commit, and PMGR `0x23b74c200` bit 2 (an unverified "wait
  for the SEP's power gate").
- Aurora (T8140): "a commit with it running never returned" (`coprocessors.md` line 47).

## The question

Is the Secure Enclave what keeps the always-on engine from starting the power-down after
Linux's commit?

## Prior art to read before the card

`tools/prior-art.sh sep` first. It lists, among others: Aurora's
`~/Work/aurora-ref/linux-integration/Documentation/devicetree/bindings/soc/apple/apple,sep.yaml`
and the SEP driver that binding belongs to, how `drivers/soc/apple/sleep.c` (`1f38ff8f4`) treats
the SEP before its commit, `~/Work/aurora-ref/asahi-docs/docs/hw/soc/sep.md`, the reference
deep-dive `docs/reference/asahi-aurora-sleep-deep-dive.md`, and the spec's 67 lines naming it.
Aurora's code may be used as it is or modified. The sleep message itself (endpoint, opcode,
reply) is to come from these sources or from a reading; this brief does not know it. The old
driver branches (`~/Work/s2r-rs1-135`, `~/Work/linux-aurora-s2r`) stay off limits.

## Runs

1. Read `0x23b700c00` and `0x23b74c200` at the commit, with the entry as milestone 2 ran it.
2. Tell the SEP to sleep by message before the entry, wait for its domain to read gated, then
   the same entry; read the same two words at the commit.

One experiment card per run in `docs/experiments/` before any run (they may share one build and
one boot each). The reading that decides: `0x0201` after the run (01 or 04), with the two words
and the reset time beside it. If a run's outcomes cannot be told apart, change the run, not the
question.

Probe code on a new `probe/m3-sep` branch in `~/Work/dsk-probe-m1-leads` (from `probe/m2-cache`
`e1442a487` or from ds29 `52669b5bb`, whichever the card needs); never merged. A 5-minute safety
check by a second agent before the first run. Runs with `tools/tb/probe-run/onerun.sh`, claim
taken, `apple_wdt` unbound, `wdt` armed.

## Budget

2 M1 runs; up to 4 if a run fails to start or a repeat is needed to tell outcomes apart. At most
4 sub-agents and 2 probe builds. No build-lane work. No hypervisor run unless the message cannot
be found any other way; say so to Naeem first.

## Done

- `0x0201` = 01 after a run: tell Naeem at once, in one line, and stop running.
- 04 in both: the SEP is ruled out. By the stop condition the deep-sleep work stops; say so.
- Either way: outcomes on the cards, the finding on `docs/cards/coprocessors.md` and
  `docs/cards/state.md`, `docs/agents/milestone-3-report.md` (at most 40 lines), the M1 back on
  its default kernel with the claim released, the lab repo committed and pushed. Kernel repos
  stay local.
