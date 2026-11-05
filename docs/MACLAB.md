# m1power and maclab

[maclab](https://github.com/chriskearney/maclab) is a test lab for Linux
kernels on Apple-silicon Macs: labd queues jobs, lab-agent runs them as root on
each enrolled Mac, every test kernel boots exactly once and falls back to the
Mac's Known-good kernel, and `lab` (CLI) and `lab mcp` (23 MCP tools) drive it.
The M1 Air used here is enrolled as a **Lab-owned** Mac (`naeems-m1-airr` at
`https://maclab.chonkbase.net`): Maintainers may boot it into a test kernel or
run a job at any time, with no availability window and no suspend inhibitor.

This page records how the two fit together, from a read of maclab at
`a5d8134` (2026-11-05). File references are to that tree.

## What already lines up

- **No watchdog conflict.** maclab and its boot chain use only Apple watchdog
  channel 1 (`/dev/watchdog0`, `apple_wdt`): systemd holds it on normal boots,
  lab-agent holds it with a 60 s timeout on Lab boots
  (`internal/agent/watchdog.go`, `setup.go`, `stage.go`). m1power's wake timer
  uses channel 0's BARK interrupt (offsets 0x00-0x0c); the register sets do not
  overlap. Nothing in maclab touches channel 0, installs a systemd-sleep hook,
  or really suspends a Mac.
- **The wake timer fills a documented gap.** maclab's only suspend test,
  `suspend-devices`, runs `pm_test=devices` because "Apple Silicon's RTC
  (macsmc-rtc) has no wakealarm, so a real suspend stays asleep until someone
  presses a key" (`internal/agent/suspend.go`). With `m1power.ko` loaded, a
  real s2idle cycle wakes itself.
- **Owner-side tools are outside maclab's policy.** Its rules govern labd and
  Maintainer actions, not software the owner installs over SSH.

## Coexistence (implemented)

m1power treats the lab as busy when any of these holds (`lab_activity()` in
`src/m1lab/live/agent.py`):

| Signal | Meaning |
|---|---|
| `maclab.lab_boot=1` or `maclab.job=` on `/proc/cmdline` | a Lab boot (test kernel or job boot) |
| `/sys/power/pm_test` not `[none]` | maclab's `suspend-devices` cycle |
| files in `/var/lib/maclab/out` or `/var/lib/maclab/jobs` newer than this boot | job output being produced (older ones are left by interrupted commands, which maclab never prunes; its own busy check ignores them too) |
| a `lab-agent.service` child older than 2 s that is not one of its idle helpers (`busctl monitor`, the `--mode=delay` sleep lock and its `sleep`) | an exec, test script or other command in flight; brief probes such as `systemctl is-system-running` on every check-in are ignored |
| a lab-agent `--mode=block` sleep inhibitor | a job holding the Mac awake |

While it is busy:

- the sleep hook only records (entries tagged `lab_boot` and `pm_test`): no
  sleep knobs, no wake timer, no tuning, no standby decision;
- the standby guard chooses `stay` at a dark wake instead of going back to
  sleep, and its 8 s watch window doubles as time for lab-agent to reconnect
  and pick up work; at or below the poweroff threshold it still powers off,
  because a flat battery would end any lab job anyway, without a clean log;
- `m1power sleep`, `sleep-ab`, `ab` and `sweep` refuse unless `--force`, and
  re-check before every A/B block and right before suspending: if the lab
  arrives mid-run they put the knob back, keep the completed pairs and stop
  the rest of the batch;
- `m1power install` rewrites the tune unit, and `tune run` itself returns on a
  Lab boot, so older tune units cannot apply tuning there either;
- `m1power-kmod.service` builds and loads nothing on a Lab boot (lab kernels
  ship no headers, and a compile would land inside boot-health and
  omarchy-m-test); it still restores radios m1power switched off for sleep;
- `m1power-tune.service` has `ConditionKernelCommandLine=!maclab.lab_boot=1`,
  so Lab boots, including the job boots of the Known-good kernel the lab
  baselines against, run untuned;
- `pm_test` cycles are excluded from sleep statistics.

`m1power doctor` shows the enrollment and whether the lab is busy now.

## Running m1power through the lab (`m1power lab-run`)

With `lab login` done (maclab's CLI, built from its repo with `go build
./cmd/lab`):

```bash
m1power lab-run naeems-m1-airr                       # its known-good kernel
m1power lab-run naeems-m1-airr --kernel <build-id>   # a lab kernel
m1power lab-run naeems-m1-airr --no-wait             # then: m1power lab-collect <job>
```

It submits a `--script` test, `target/lab/m1power-probe.sh`, with the agent,
the module source and a plan as payload. On the Lab boot the script builds and
loads `m1power.ko` against that boot's headers (macsmc-hwmon only when there
are none), runs `agent.py probe` (settle, idle capture with the display off,
one self-waking sleep, watchdog channel snapshots), and leaves `result.json`
for labd. The host waits for the job, fetches the file, saves it with the
other results and prints it. The probe is the lab's own work, so it does not
defer to the lab; m1power's installed services stay passive on that boot.

First run, 2026-11-05, job `j1105-075658-7770` on `naeems-m1-airr`
(7.2.11-14-1-ARCH, battery): pass. Idle 1.18 W with the display off (SoC
0.57 W, untuned on the Lab boot). The Mac slept 85.6 s and resumed on the same
boot, woken by the m1power timer, with lab-agent's 60 s watchdog on channel 1
armed: `apple_wdt` stops across s2idle on Lab boots as on normal ones. labd
logged its usual "the lab can't wake it" note, then "back on the same boot
after 1m30s". The passing job became the Mac's omarchy-m-test reference, with
`m1power` taint among its new kernel lines; the lab's after-tests screenshot
timed out, possibly because the probe turned the display off.

Keep `--sleep` under 120 s: longer sleeps in a job page a person.

## Using the lab for power work (needs a Maintainer login)

None of this works without a Maintainer token for the labd instance
(`lab login <labd-url> <token>`, written to `~/.config/maclab/client.json`).
The deployed labd was started with `--maintainer=chris`; tokens come from its
operator.

1. **m1power as lab jobs, fleet-wide.** A `--script` test runs as root with up
   to 16 `--payload` files in `$MACLAB_IN`, and everything written to
   `$MACLAB_OUT` comes back as job files (`lab logs <job> <file>`,
   `GET /api/jobs/{id}/files/...`, MCP `lab_log`). An `m1power-probe.sh` would
   insmod a payload `m1power.ko`, run the agent's `record` / `ab` / short
   `sleep`, and write the JSON results to `$MACLAB_OUT`. Every job reboots
   twice and appends omarchy-m-test, so measure after a fixed settle time and
   compare Lab boot with Lab boot only.
2. **A lab transport for the CLI.** `lab exec` (`POST
   /api/devices/{name}/exec`) runs `bash -c` as root without a reboot, 120 s
   default timeout, 1 MiB per stream, no lease check. A `--via maclab:<device>`
   transport in `remote.py` would replace Tailscale SSH (no re-auth prompts) and
   put every action in the lab's audit log. Take `lab lease` first: exec does
   not respect leases.
3. **Kernel fixes, crash-safe.** The two bugs found here need patched kernels:
   the BCM4378 firmware wedge under ASPM L1.1/L1.2 (`brcmfmac`), and the NULL
   dereference in `dwc3_apple_remove` on a never-connected port. `lab build
   <fork/branch>` (or `lab pack --build <dir>` for a local tree, or `lab
   package` with a `.patch`) builds against the Mac's own config, and `lab run
   --kernel` boots it once; an oops, panic or hang falls back to Known-good
   with logs collected. `m1power.ko` for a lab kernel can be built from the
   build's `module-build.tar.zst` (`lab build-get`), or carried as a built-in
   driver on a lab-only branch, as `tools/chaos` does for its test driver.
   `brcmfmac` can be reproduced without real sleep: enable the substates in the
   script, then run `suspend-devices` repeatedly.

## Upstream proposals

maclab takes requests as GitHub issues, not unsolicited pull requests
(`docs/agents/issue-tracker.md`). Worth proposing:

- a real-suspend builtin next to `suspend-devices`, using the m1power wake
  timer, with lab-agent's Quiet announcements so labd does not page a person
  after 2 minutes asleep (`realSleepNote`) or fail commands after an hour
  (`maxSleep`);
- a `WakeTimer` device fact, so labd expects a self-waking Mac;
- a power result beside omarchy-m-test (idle W, sleep W, %/h, s2idle entries)
  that the release gate can treat as a regression check, judged on paired,
  seeded known-good/candidate boots rather than a single run.

## Cautions

- A real sleep longer than about 2 minutes inside a job pages a person, and
  over an hour fails the command. Long standby measurements stay owner-side.
- Artifacts no job references are deleted after a day; re-upload payloads.
- labd serves job files with a sandboxing CSP, so the HTML report does not run
  from there; rebuild it with `m1power report`.
- Re-running lab-agent setup with a Tailscale key can move the Mac to the lab
  tailnet and break `root@naeems-m1-air`; point `--target` at the new name.
