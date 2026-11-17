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
