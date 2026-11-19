# Experiment card (template)

Copy to `docs/experiments/<yyyy-mm-dd>-<name>.md` and fill every line before the run.

```
Question      One sentence. What do we not know?
Known         What the readings already say, with card or evidence pointers.
Prior art     What `tools/prior-art.sh` found (Aurora file and commit, evidence section), or "none".
Outcomes      A  <what we would read>  -> <what it means>
              B  <what we would read>  -> <what it means>
              (every outcome the run can have, including "inconclusive")
Tell apart    Why A and B look different in what we can read (a byte, a time, a log line).
Not covered   What this run cannot show.
Safety        Watchdog, boot-once, what is kept to restore, what needs Naeem.
Budget        Builds, runs, agents.
Result        (after the run) the outcome letter, the raw files, the card line added.
```

Example: `docs/experiments/2026-11-20-boot-loader-breadcrumb.md`.
