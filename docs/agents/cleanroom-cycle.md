# The clean-room cycle (the build lane)

Since 2026-11-20 the work has two lanes (Naeem: "Two speeds"). Finding out what the hardware does
is the probe lane: `docs/agents/probe-lane.md`. This file is the build lane, for code we keep.

Observation -> spec -> tests -> implementation. Each stage is done by its own agent.
No stage's agent may change or sway another stage's work. The orchestrator (the session Naeem
talks to) only carries finished work forward by path and commit.

**Once per milestone, with the spec frozen.** On 2026-11-19, 10 of 14 test rounds and 8 of 12
implementation rounds were redone only because the spec changed after the tests were locked.
So:

- The build lane starts only when the probe lane has settled what the behaviour is.
- The spec is frozen when the test authors start. Gaps and review points found after that go on
  one list (`docs/spec/gaps-<milestone>.md`) and are answered in a single spec pass at the end of
  the milestone, followed by one delta round. A gap that makes a test impossible to write is the
  only reason to stop early.
- Tests for the logic, the glue and any client are written in one wave, in parallel.
- A new reading from the M1 does not reopen the spec mid-milestone; it goes on a fact card
  (`docs/cards/`) and into the next milestone.
- Every brief names the fact cards to read. The spec and the evidence file are opened by section,
  through the cards' pointers, never whole.
- An agent's report back to the orchestrator is at most 15 lines; details go in a file it names.
- Models follow `~/.claude/rules/pstack-models.md`: Haiku for mechanical work, Opus medium by
  default, Opus high for design and review only.

| Stage | Agent | Reads | Writes | Must not |
|---|---|---|---|---|
| Observation | a fresh agent per round (or the orchestrator running a tool whose output is the record) | the machines: macOS under the hypervisor, Linux on the M1 | readings in `var/` (private) and `docs/evidence/` | state causes, propose fixes, edit spec, tests or driver |
| Spec | a fresh agent per round | observations only | `docs/spec/` | read the driver, the glue or the tests; write anything not in an observation |
| Tests | a fresh Fable 5.2 agent, effort medium | the spec only | `tests/`, `TESTS.md` (with its list of spec gaps) in `~/Work/deepsleep-clean` | read the driver or the glue; implement |
| Implementation | a fresh Opus 5.5 agent, effort high, red-green-refactor, one commit per cycle | the tests (read-only files) and the spec copy beside them | `src/` only | change, skip or argue with a test; read the old driver branches |

Rules for the orchestrator:

- A brief names the input by path and commit and says what done looks like. It carries no
  hypothesis, no preferred fix and no summary of what a later or earlier stage "wants".
- Work goes forward only. Going back is one thing: a list of gaps or disputed points, handed to a
  fresh agent of the earlier stage, answered from that stage's own input.
- The orchestrator does not write spec text, tests or driver code itself.
- The verdict on the driver is `tools/cleanroom-verdict.sh <repo> <tests-commit>`.
- The kernel glue (`drivers/soc/apple/deepsleep/` outside `logic/`) wires the tested logic in and
  takes readings. It never changes what the logic does; `logic/` is a copy made by
  `sync-logic.sh`.

Two more rules (Naeem, 2026-11-17):

- **Three strikes.** When something keeps failing and three different approaches have been tried,
  the next step is an observation round under the hypervisor (`tools/tb/m1-hvboot`,
  `tools/hv-trace-kit/harness/`): fresh readings, then spec, tests and driver in that order. No
  fourth workaround on Linux alone.
- **Documentation.** The observation and spec agents consult the Asahi Linux documentation
  (asahilinux.org/docs) and the Aurora Silicon documentation (the aurora-silicon repositories'
  docs; survey in `docs/evidence/2026-11-06-aurora-silicon-survey.md`) and cite the page for
  anything taken from them. Documentation explains readings; it is marked as documentation, not
  as an observation. Asahi code is not pulled.
- **Aurora Silicon code** (Naeem, 2026-11-17: "any repository/any branch ... for reference";
  widened 2026-11-20: "We're okay to use any code from Aurora Silicon as it is or modified. They
  are in partnership with us."). Any stage may read, build, run, use or modify aurora-silicon code
  (any repository, any branch), citing repository, branch and commit; tools and infrastructure
  (the M1's boot loader `aura`, m1n1, scripts) may be taken from it directly. The clean-room
  separation between stages still holds: the driver logic's author works from the tests alone, and
  no stage hands another its conclusions.
- **What the hypervisor is for** (Naeem, 2026-11-17, after a Linux guest left the M1 dark). The
  hypervisor stage reads macOS, the system whose sleep and wake work, by the recipe that has
  already run unattended (det8). Linux is read on bare metal. Before any hypervisor run the
  observation agent names the step that ends the run without hands if the wake does not come.

- **The kernel glue is in the cycle too** (Naeem, 2026-11-18: "Include the kernel glue in the clean
  room cycle."). The glue (`drivers/soc/apple/deepsleep/` outside `logic/`, and the arch hooks)
  gets its own independent test author, who reads the spec and the glue's interface view (doc
  comments and signatures, no bodies) and never the glue's code; the tests run against the
  committed glue with `tools/cleanroom-glue-try.sh`. What cannot run on the host (the C and arm64
  half) gets one independent reviewer against the spec. Fixes go to a glue implementer who reads
  the locked tests and the review and cannot change either. The glue's earlier host tests were
  written by its own author and do not count as the verdict.

- **Faster cycles** (Naeem, 2026-11-18: "All three", to the proposal of that day).
  (1) A round may carry several candidate behaviours at once: the spec names each candidate
  requirement as such, the tests hold the driver to each behind its own switch (a module
  parameter, off by default), recorded as decision D5. (2) The M1 then tests the switches one by
  one or in combination, unattended, each run ended by the watchdog (`apple_deepsleep.wdt`); a
  run that stays dark stops the series and pings Naeem. (3) The stages overlap: while agents
  write spec, tests and driver for the next round, the M1 may run the current round's switch
  tests or observation runs. This replaces the rule of 2026-11-18 04:35 ("no more runs until the
  spec, tests, driver and kernel test are done").
