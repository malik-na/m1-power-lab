# Repository instructions

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues using `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default Matt Pocock triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context layout. See `docs/agents/domain.md`.

## Operator corrections: the rules and what enforces them

When Naeem corrects you, fix the mistake and add its rule here. A rule that is here already and
has nothing enforcing it is a repeat: enforce it in the same change. Drop a rule once its mistake
cannot happen.

| Rule | Corrected on | What enforces it |
|---|---|---|
| A hypervisor run starts with nothing left from an earlier run on the M1's ports, and exactly one console reader. | 2026-11-16 (five stale readers broke six runs) | `harness/lib.sh` `hv_preflight` in `go135.sh` / `golinux.sh` refuses, naming the pids; the run script starts and stops its own reader; `session.sh console` takes a lock. Test: `harness/test-lib.sh` (pytest `tests/core/test_hv_harness.py`). |
| Stop host processes by pid, never with `pkill -f` / `pgrep -f` (they match the calling shell). | 2026-11-16 (twice) | `harness/stop.sh` and `hv_run_guests` match the command's own argument. Nothing stops a hand-typed `pkill -f`: use `stop.sh`. |
| Wait on a run's own files, not on a log shared between runs. | 2026-11-16 (a wait matched an earlier run's text; a false "guest did not resume") | The run scripts write `vuart-<tag>.log`; the drive scripts judge progress by `s2r-trace-<tag>.jsonl`. |
| Drive the M1 over Thunderbolt (`tools/tb/`), not through the lab, while the cable is in. | 2026-11-16 | `tools/tb/m1-bootonce` (boot a test kernel once), `tools/tb/m1-hvboot` (to the m1n1 proxy), `tools/tb/m1tb`. Judgment: nothing fails if you call `lab`. |
| Do not hand Naeem a check or a step you can do: read the state, look at the M1's screen, reboot it yourself. Ask for his hands only when no tool reaches (a power cycle with the proxy dead, a macOS login). | 2026-11-16 (three times) | `tools/tb/m1-look` (the screen), `harness/hv-reboot.sh` (reboot from the hypervisor or proxy), the guest m1n1 keeps watchdog 1 armed. Judgment beyond that. |
| Before saying what the M1 is doing (at the login window, asleep, at the proxy), take every reading and look at its screen. Logs alone are not the state. | 2026-11-17 (twice in a row: "at the login window", then "asleep", while it had restarted into Omarchy; a photo was taken and not looked at) | `tools/hv-trace-kit/harness/m1-state.sh`: one command, a verdict from USB, Thunderbolt, the host process and the newest log, and a camera frame. Looking at the frame is judgment. |
| Never state a cause you have not read. Say "unknown" when the readings do not tell (a restart: his power cycle, a watchdog or a crash?). Once you have asked him something, wait for his answer; do not act on a side effect as if it answered. | 2026-11-16 (twice) | Judgment. Memory: never-assume-always-validate. |
| Before a hypervisor run, know what else is plugged into the M3 and what holds its ports. | 2026-11-16 | `hv_preflight` covers the ports. What is plugged in: judgment (`ls /sys/bus/usb/devices`). |
| Several changes per run, chosen from readings; not one fix per run. | 2026-11-16 | Judgment. |
| Whoever writes the code cannot change or sway its tests. The verdict comes from the tests as their author committed them; a test the implementer disputes goes to Naeem and a fresh test author, never back to the implementer. | 2026-11-17 (the tests were protected by an instruction and a check afterwards only) | `tools/cleanroom-verdict.sh <repo> <tests-commit>` runs the tests from the test author's commit against the implementer's `src/` only; the test files are made read-only before the implementer starts. |
| The deep-sleep work is a cycle: observation (macOS under the hypervisor, Linux on the M1) -> spec -> tests -> implementation, repeated. Each stage has its own agent, and no stage may sway another; the orchestrator carries work forward by path and commit and writes none of it. | 2026-11-17 (the orchestrator had been writing spec changes itself) | `docs/agents/cleanroom-cycle.md` (who reads and writes what); read-only test files and `tools/cleanroom-verdict.sh` for the last two stages. The briefs: judgment. |
| When something keeps failing after three different approaches, stop trying on Linux alone: chainload the hypervisor, take fresh readings, then spec -> tests -> driver. Asahi Linux documentation (docs, not code) and Aurora Silicon documentation and code (any repository, any branch; for reference, read as data, never run) are consulted and cited at the observation and spec stages. | 2026-11-17 (three kernels in a row lost the commit snapshot on the way back) | `docs/agents/cleanroom-cycle.md`. The count of approaches: judgment. |
| The hypervisor is for readings of macOS, by the recipe that already ran unattended; Linux is read on bare metal. No hypervisor run starts without a no-hands way out if the wake does not come. | 2026-11-17 (a Linux guest in the detached mode left the M1 dark; its readings were in RAM and a power cycle lost them) | `docs/agents/cleanroom-cycle.md`; the observation brief names the way out. Judgment. |
| No bare-metal sleep test without the watchdog armed at the commit (`apple_deepsleep.wdt`), so a run that neither sleeps nor resets ends by itself. | 2026-11-17 (four runs left the M1 dark until Naeem held the power button; one earlier recovery crashed the M3's Thunderbolt driver) | `tools/tb/guest/ds-real.sh` (installed on the M1 as `/var/lib/m1power-ds/real.sh`) refuses to start a sleep with `wdt` off; `ALLOW_NO_WDT=1` only for a run Naeem asked for. |
| One user of the M1 at a time: whoever is about to reboot it or run on it claims it first and releases it after. | 2026-11-17 (an observation agent moved the M1 to the hypervisor while the orchestrator had just booted a test kernel on it) | `tools/tb/m1-claim take/release`; `m1-bootonce`, `m1-hvboot`, `m1-commit-walk` and the hypervisor's `hv_preflight` refuse while another user's claim stands (`M1_CLAIM=<who>`). |
| The kernel glue goes through the clean-room cycle like the logic: an independent test author (interface view only), one independent reviewer for the C and arm64 half, and a glue implementer who cannot touch either. | 2026-11-18 (the glue's tests were written by its own author; its C half was never reviewed) | `docs/agents/cleanroom-cycle.md`; `tools/cleanroom-glue-try.sh`. |
| A status update states only what was read in that turn: it quotes `tools/status.sh` (the M1's claim, kernel and uptime, the last hypervisor run, the run tables, the repos and workspaces, the build, each agent's last step) and says "not read" for anything else; no "apparently" or "seems". | 2026-11-18 (four status updates stated unread things: an "earlier hypervisor build", "the second auditor is still working", "apparently", "seem") | `tools/status.sh` reads every one of those facts in one call; the wording itself is judgment. |
| A bare-metal sleep run must end without hands even when it hangs before the commit. | 2026-11-18 (ds16 runs and the C3 switch run left the M1 dark until Naeem's power button; the watchdog is armed only at the commit) | Enforced since glue round 3c (kernel tree `40833e3eb`, in ds28/ds29): watchdog 1 is armed first in `begin`, every way back disarms it last or ends in record-then-panic, and a `wdt` that cannot be armed refuses the sleep. Not covered: the `pmp` client's wake part runs after the disarm. |
| A brief never narrows the search with a limit Naeem did not set (e.g. "kernel image only"); a sensitive option (the M1's boot loader, its default boot) is put to Naeem as an option. Every observation, spec and review brief names the lab's existing evidence and the allowed reference code for the component first. | 2026-11-19 (a "no boot-loader change" limit I added hid the direct wake test the 11-17 evidence already listed; `pmp`'s windows and shared region were rediscovered over three boots though `docs/reference/` and Aurora m1n1 `pmp_init.py` had them) | Judgment. Memory: dont-fence-off-options. Before a brief: `grep -rn -i <component> docs/evidence docs/reference`. |
| Never offer to stop, and do not slow down for risk to the M1: it is a dedicated test machine, anything recoverable from DFU is allowed. Naeem says when to stop. The M3 is not to be put at risk. | 2026-11-16 (twice) | Judgment. Memory: full-throttle-no-stop-offers. |

