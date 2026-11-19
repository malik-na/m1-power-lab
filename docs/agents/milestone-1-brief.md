# Milestone 1 brief: probes from Aurora's sleep driver

Written 2026-11-20. For a fresh session (or this one), in the probe lane (`probe-lane.md`).

## Read first, in this order, and nothing bigger

`AGENTS.md`, `docs/cards/INDEX.md`, `docs/cards/state.md`, `docs/agents/probe-lane.md`,
`docs/agents/experiment-card.md`, `docs/agents/handoff-2026-11-19.md` (its 2026-11-20 update),
`docs/cards/aurora-prior-art.md`, `docs/cards/wake-path.md`, `docs/cards/run-recipes.md`.
Open the spec and the evidence file only by section, through the cards' pointers.

## The question

After the Linux sleep entry's commit, why does no wake reach the M1's boot CPU?

Aurora Silicon's kernel sleep driver, `~/Work/aurora-ref/linux-integration/drivers/soc/apple/sleep.c`
(`1f38ff8f4`; matched for T8140 and T8132; measured from macOS the way this lab measures), names
conditions never checked on the M1. Leads, most likely first:

1. **Wake-source masks** (`sleep.c` 2276-2291, 2327-2334). It unmasks only the enabled wake
   sources, because the words read zero until something writes them. Our logic never writes them,
   and they have never been read at Linux's commit. Fits "powers down and is never woken".
2. **PMC voters and DCS state 4** (3390-3403). The always-on engine's first step polls for it.
3. **Memory-controller (AMCC) error enables** (231-244, 3560-3571). An enabled pending error
   turns the sleep around within 20 ms.
4. **Power-gate records** `0x23b71c090` and `0x23b71c360` after the commit (`docs/cards/power-domains.md`,
   the Nov 16 "stuck islands"), untested on the current driver.
5. **Is the boot CPU's RVBAR locked on this M1?** aura's docs say not on A7-M3; the lab's notes
   say it is. One read at the m1n1 proxy.

Also open: the boot-loader breadcrumb has never been seen to write
(`docs/experiments/2026-11-20-boot-loader-breadcrumb.md`).

## Steps

1. Prior art: `tools/prior-art.sh wake`, `tools/prior-art.sh amcc`; read the parts of `sleep.c`
   named above, how it arms a wake source, and what it does at the wake. Write what the M1 would
   need (the t8103 address of each word, and which are unknown) to
   `docs/cards/aurora-sleep-driver.md`, at most 80 lines, each with its source.
2. One experiment card per lead in `docs/experiments/` before any run. Combine cards that can
   share one build and one boot. No probe whose outcomes cannot be told apart.
3. Probes on `probe/*` branches (kernel tree `~/Work/deepsleep-kernel`, current code `52669b5bb`
   = ds29; loader tree `~/Work/m1n1-mb2-breadcrumb`); a 5-minute safety check by a second agent;
   then the runs (`tools/tb/m1-claim take`, `tools/kbuild-clean.sh <tag> <commit>`, boot once,
   read out, release). Where macOS's value of a word is not recorded, a hypervisor reading of
   macOS comes first, with every needed reading in one run.
4. After each run: the outcome on its card, the finding on the component's fact card, one line
   to Naeem if it is a finding.

## Budget

At most 12 sub-agents, 150M sub-agent tokens, 8 M1 runs. No build-lane work. Tell Naeem at half.

## Done

For each lead: a reading on the M1 that rules it in or out, or a line saying why it could not be
read. `docs/cards/state.md` updated. A short recommendation for what the build lane should build
(likely Aurora's driver structure with t8103 tables). If a probe makes the M1 wake by itself,
stop and tell Naeem at once.
