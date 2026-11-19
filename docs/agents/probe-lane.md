# The probe lane

For finding out what the hardware does. The code is thrown away. Nothing from this lane ships.
(Naeem, 2026-11-20: "Two speeds"; probe checks: "Safety check only".)

## Steps

1. **Prior art.** `tools/prior-art.sh <component>` and read what it finds: our evidence, the
   reference deep-dive, Aurora Silicon's repositories (usable as they are or modified). If the
   answer or the code exists, use it and stop here.
2. **Experiment card.** Fill `docs/agents/experiment-card.md` and save it as
   `docs/experiments/<date>-<name>.md`. A probe whose outcomes cannot be told apart in what we can
   read is not run.
3. **Probe.** One agent writes the smallest change that answers the question, on a `probe/<name>`
   branch (kernel tree, boot loader tree, or a script). Off by default where it is a switch. No
   spec, no tests.
4. **Safety check.** A second agent, about five minutes, two questions only:
   - can any path leave the M1 dark with no watchdog armed?
   - does anything write outside the allowed places (power chip `0x9f04`-`0x9f0d` and the alarm
     register; nothing on the M3)?
5. **Run.** `tools/tb/m1-claim take`, a boot-once kernel, the run, the read-out, release. The card
   gets the outcome and the raw file paths.
6. **Fact card.** The finding goes on the component's card in `docs/cards/` with its source. One
   line to Naeem.

## Rules

- Probe branches are never merged. What a probe taught reaches kept code only through the build
  lane (`docs/agents/cleanroom-cycle.md`).
- One question per card; several cards may share one build and one boot.
- A change to what the M1 boots by default (its boot loader, its default entry), anything that
  needs Naeem's hands, and anything that cannot be undone are asked first, with a pick.
- Everything else reversible: act, then say what was chosen and why in one line.
- The AGENTS.md rules on the M1 still hold: the claim, the watchdog, boot-once kernels, reading
  the state before stating it.
