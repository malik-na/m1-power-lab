# Milestone 4 brief: one batch run of what Aurora's driver does before its commit and ours does not

Written 2026-11-20 after milestone 3. For a fresh session, in the probe lane (`probe-lane.md`).
Naeem asked for it on 2026-11-20: "do that one batch run in a new session".

## Read first, in this order, and nothing bigger

`AGENTS.md`, `docs/cards/INDEX.md`, `docs/cards/state.md`, `docs/agents/milestone-3-report.md`,
`docs/agents/probe-lane.md`, `docs/agents/experiment-card.md`,
`docs/cards/aurora-sleep-driver.md` (section 6 above all), `docs/cards/sleep-entry.md`,
`docs/cards/power-domains.md`, `docs/cards/watchdogs.md`, `docs/cards/run-recipes.md`. Open the
spec and the evidence files only by section (grep, then read the range).

## Where milestone 3 left it

After Linux's commit the always-on engine never enters sequence 0: power-chip `0x0201` reads 04
before and after every run (01 would mean sequence 1 ran), and each run ends at watchdog 1,
165 s after the start with `wdt=150`. Milestone 3's run 5 had the SEP gated as macOS's
(`apple_sep.xart_guard=0`; `0x23b700c00` = `0x1000230f` at the commit): still 04 -> 04.

`state.md` says "No known difference from macOS remains". That is too strong; correct it. The
cards themselves list things never read or tried on the M1.

## The question

Does any of the steps Aurora's sleep driver takes before its commit, and our entry does not,
let the always-on engine start sequence 0?

## The items

From `docs/cards/aurora-sleep-driver.md` section 6 (`sleep.c` at `1f38ff8f4`, line numbers there):

1. A live USB-C debug link is cut before the commit (HPM cold reset, then SSPS S3): it "holds
   the debug domains active, which macOS has idle". Every clean-room run had the Thunderbolt
   cable in. The old driver tried cable-out on 2026-11-07/08 (`state.md`, "Tried and ruled out").
2. The boot core's last WFI: timers masked, every event acked at the AIC, the WFI retaken. What
   our glue does after core 0's final write is not read.
3. BUSY-latched PS words the wake polls are unlatched. The t8103 list is not named.
4. AON_AP_DEADLINE (`0x23d2b8008`) = 0 and watchdog 2 from the AP. On t8103 the always-on side
   arms watchdog 2 (R62); the deadline word at Linux's commit is not read.
5. The AIC is masked right after the commit write; ours masks in R36, before R37.
6. PMC voter words to 0. Not located on t8103 (aura's rule does not apply; card section 3).

Never compared at all, to read in the same runs where a word is known: the P cluster word
`0x23b718004` (`0x10` then `0x50` at Linux's commit; macOS's value at its commit never read),
the E cluster word `0x23b718000`, the wake masks and AMCC enables at the commit (card sections
1 and 2, "not read").

## The run

Several changes per run (AGENTS.md): one probe kernel with every item that can be built behind
its own switch, all on in the first run, together with everything milestone 3's run 5 had
(cand `0xffffe`, the SEP gated). The deciding reading is `0x0201` after the run, with the words
above and the reset time beside it. If it reads 01, find which switch by halving. If 04, each
item that was on is ruled out together.

Item 1: the M1 is driven over the cable, and the M3 is not to be put at risk (memory
`m3-silent-resets-tb-link`). Aurora's software cut is one way; Naeem pulling the cable after a
delayed start is another. The safety check says whether the software cut is safe for the M3;
if it is not clearly safe, put both to Naeem with a pick before that run.

Prior art first: `tools/prior-art.sh wake`, `tools/prior-art.sh aic`, `tools/prior-art.sh hpm`,
and the `sleep.c` ranges the card names. Aurora's code may be used as it is or modified. Where
macOS's value of a word is not recorded and nothing else gives it, say so on the card; a
hypervisor reading of macOS is allowed, with every needed reading in one run and a no-hands
way out.

One experiment card per item in `docs/experiments/` (they share the build and the boot). Probe
code on a new `probe/m4-batch` branch in `~/Work/dsk-probe-m1-leads`, from `probe/m3-sep`
`ecbbcc4aa`; never merged. A 5-minute safety check by a second agent before the first run.
Runs with `tools/tb/probe-run/m3run.sh` or `onerun.sh`, claim taken, `apple_wdt` unbound, `wdt`
armed, and a watchdog held from before any trigger (milestone 3's safety gap).

## Budget

2 probe builds, 4 M1 runs, 5 sub-agents. No build-lane work. Tell Naeem at half.

## Done

- `0x0201` = 01 after a run: tell Naeem at once, in one line.
- 04 with every buildable item on: those items are ruled out together; say which items could
  not be built or read, and why.
- Either way: outcomes on the cards, findings on `docs/cards/aurora-sleep-driver.md` and
  `docs/cards/state.md` (with the corrected sentence), `docs/agents/milestone-4-report.md` (at
  most 40 lines), the M1 back on its default kernel with the claim released, the lab repo
  committed and pushed. Kernel repos stay local.
