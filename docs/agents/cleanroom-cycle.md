# The clean-room cycle

Observation -> spec -> tests -> implementation, then again. Each stage is done by its own agent.
No stage's agent may change or sway another stage's work. The orchestrator (the session Naeem
talks to) only carries finished work forward by path and commit.

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
- **Aurora Silicon code** (Naeem, 2026-11-17: "any repository/any branch ... for reference"). The
  observation and spec agents, and the kernel glue's author, may read aurora-silicon code as a
  reference for what the hardware is and does, citing repository, branch and commit. It is read
  as data and never run or built here. The driver's author still works from the tests alone.
- **What the hypervisor is for** (Naeem, 2026-11-17, after a Linux guest left the M1 dark). The
  hypervisor stage reads macOS, the system whose sleep and wake work, by the recipe that has
  already run unattended (det8). Linux is read on bare metal. Before any hypervisor run the
  observation agent names the step that ends the run without hands if the wake does not come.
