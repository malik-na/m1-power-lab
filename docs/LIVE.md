# Live measurement from an Omarchy host (`m1power`)

`m1power` measures and reduces idle and sleep power on an Apple-silicon Mac
running Asahi/Omarchy Linux, driven from a second Mac (or any Linux machine)
running Omarchy. It replaces the ThinkPad + m1n1 proxy path for day-to-day
power work: the target runs a real Linux system, so it is instrumented from the
inside instead of being booted into a bare-metal harness.

```
Omarchy host (M3 Max)                       Target (M1 Air, Omarchy)
  m1power CLI ── SSH over Tailscale ──▶  agent.py (stdlib Python, root)
  results in ~/.local/share/                 m1power.ko  ── SMC keys, wake timer
    m1-power-lab/live/*.json                 systemd-sleep hook ── ledger.jsonl
  report.html                                m1power-tune.service (optional)
```

The USB-C cable between the two Macs carries power only: the target kernel has
no USB gadget support (`CONFIG_USB_DWC3_GADGET` is off), so all control goes
over the network. The host can power the target through the cable; the SMC's
DC-in counters then measure the whole target, asleep or awake.

On battery the DC-in counters read about 0 W, so a sleep's power (`sleep_w`
in every ledger entry) is the DC-in average when the target is on AC and the
battery's energy drop otherwise. For a standby (days-on-battery) figure,
unplug the cable before the sleep: a DC-in figure includes charger loss and
says nothing about the battery. The two sources are never paired against
each other in `sleep-ab`. Ledger entries written before `sleep_w` existed get
the same rule from their `dcin_w`/`battery_w` fields.

## Setup

Root SSH to the target must work without a password (Tailscale SSH does this).
The default target is `root@naeems-m1-air`; override with `--target`,
`M1POWER_TARGET`, or `~/.config/m1-power-lab/target`.

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
.venv/bin/m1power install
.venv/bin/m1power doctor
```

`install` puts these on the target:

| Path | Purpose |
|---|---|
| `/usr/local/lib/m1power/agent.py` | the agent every command runs; replaced in place (atomically, checked by sha256) whenever the host's copy differs, so the sleep hook, boot units and experiments always run the same version |
| `/usr/local/src/m1power/` | source of `m1power.ko` |
| `m1power-kmod.service` | builds the module for the running kernel at boot (needs that kernel's headers) and loads it |
| `/usr/lib/systemd/system-sleep/m1power` | brackets every suspend in `/var/lib/m1power/ledger.jsonl` |

Without an install, commands upload the agent to `/run/m1power/agent-<digest>.py`
the same way. If the module source changed but the loaded module is busy (a
capture holds its debugfs files), `install` fails instead of leaving the old
module running: stop the job and rerun it, or reboot the target.

`m1power uninstall` removes all of it, reverts any tuning and keeps the ledger.

Results are saved as JSON in `~/.local/share/m1-power-lab/live/` (or
`$M1POWER_RESULTS`). The owner web UI (`m1lab serve`) serves the same report at
`/api/live-report.html`, linked from the Evidence view; when it runs as the
`m1lab` system service, point both at one directory with `M1POWER_RESULTS`
(for example in `/etc/m1-power-lab.env`) and make it readable by the service.

## The kernel module

`target/kmod/m1power.c` adds two things the stock kernel lacks:

- **All SMC keys, read-only.** `macsmc-hwmon` exposes ten sensors; the SMC has
  ~1640 keys. The useful power keys on the M1 Air: `PSTR` system total,
  `PDTR` DC-in, `PHPC` SoC ("heatpipe"), `PMVC`, per-PMU-rail `PPxx`/`PRxx`
  with matching `I`/`V` keys, and the accumulators `zSPa` (DC-in energy in mJ,
  1 Hz, keeps counting while the CPU sleeps) and `zSPc` (its sample count).
  Function keys are never read and nothing is ever written.
- **An s2idle wake timer.** The SMC RTC has no alarm, so `rtcwake` cannot end a
  suspend. The Apple watchdog block's channel 0 has a BARK (interrupt)
  threshold separate from its BITE (reset); the module programs BARK with only
  the interrupt enabled, chains 170 s chunks inside s2idle without waking the
  system, and raises a hard wakeup event at the deadline. The reset-enable bit
  is never set. Channel 1 belongs to `apple-wdt` (systemd's 30 s watchdog);
  channel 2 ignores the interrupt-enable bit.

Files under `/sys/kernel/debug/m1power/`: `smc_keys`, `smc_watch`,
`smc_sensors`, `waketimer` (write seconds, read status), `wdt_regs`.

`smc_watch` keeps its key list per open file: write the keys on an fd, then
`lseek(fd, 0, SEEK_SET)` and read to EOF for `BOOT <ns>`, `MONO <ns>` and one
`KEY type size flags hex` line per key. Each reader (a capture, the sleep
hook, a one-off `m1power smc`) has its own list and never changes another's.

## Measuring

```bash
m1power watch                         # live: W, idle residency, MHz, IRQ/s
m1power record --duration 120         # detached capture + top wakers/IRQs
m1power knobs                         # every tunable and its value
m1power ab wifi_ps on                 # randomized paired A/B of one knob
m1power sweep --preset idle           # A/B every knob in a preset, ranked
m1power sleep --seconds 600 --repeat 3            # unattended sleep tests
m1power sleep --seconds 600 --set wifi=off        # sleep with a knob changed
m1power ledger                        # every suspend ever recorded
m1power collect batch-123456-789     # reattach to a detached job and save it
m1power report                        # HTML report of everything saved
m1power domains | smc PSTR zSPa       # SoC power domains, raw SMC keys
```

Experiments run **detached on the target** under `systemd-run` and the host
stays off the network until they finish, so SSH traffic does not wake the
Wi-Fi radio mid-measurement. A/B runs alternate the two settings in random
order within each pair, settle before measuring, and report the paired
difference with a 95% t-interval (and the repository's frozen 10% rule from
`science/power.py`). Every knob change is journaled in `/run/m1power` and a
transient systemd failsafe timer restores it (and unblocks all radios) if the
agent dies; `m1power restore` does the same by hand.

Each detached job prints its id when it starts. If the host stops waiting
(Ctrl-C, a Tailscale SSH re-authentication prompt, or the grace timeout) the
job keeps running on the target and its result stays in
`/var/lib/m1power/results/<job>.json`; `m1power collect <job>` waits for it,
saves it and prints it as the original command would. A job whose unit dies
(reboot, crash) without a complete result fails at once with its journal
tail. `sleep --manual-wake` waits up to 24 h for you to wake the Mac. If a
`sweep --display` wait is interrupted the display is left held, so run
`collect` and then `restore` once the batch ends.

Knobs that can cut the network (`wifi`) are guarded: `m1power knob wifi off`
refuses unless given `--force`, and then the agent arms a 300 s failsafe that
restores the knob. A/B runs and sweeps arm their own failsafe.

The sampler itself costs a little: each SMC key read is a mailbox round trip
that interrupts the target. It reads four keys per second and battery
attributes every ten seconds; both A/B arms pay the same cost.

## Making changes stick

```bash
m1power tune apply wifi_ps=on --sleep wifi=off
m1power tune show
m1power tune revert
```

`wq_power_efficient` is read-only at runtime on the target kernel and is
reported as unsupported; the power profile showed no measurable effect.

`tune apply` refuses knobs that can cut the network or that are not
persistable: re-applied at every boot and resume they would strand the target
offline. It records each knob's previous value, writes
`/etc/m1power/tune.json` and enables `m1power-tune.service`, which re-applies
the knobs at boot. The sleep hook re-applies them after every resume, because
some (Wi-Fi power save) reset across suspend.

`--sleep KNOB=VALUE` adds a value applied just before every suspend and undone
on resume, sleep tests included. A network radio may only be switched off this
way: the hook records it in `/var/lib/m1power/sleep-radios-off.json`, and both
the resume hook and the next boot (`m1power-kmod.service`) turn it back on, so
a crash or power loss while asleep cannot leave the Mac offline. A radio you
switched off yourself is never touched.

Do not persist `aspm=powersupersave`: with L1.1/L1.2 on, the BCM4378 Wi-Fi
firmware wedges and `brcmfmac` then times out entering D3, aborting suspends,
even when the radio is blocked for sleep (see [STATUS](STATUS.md)).

Hyprland 0.56 evaluates `hyprctl dispatch` arguments as Lua; the `display`
knob tries `dispatch dpms off` and falls back to `dispatch 'hl.dsp.dpms("off")'`.

## Standby guard

```bash
m1power standby set --check-every 2h --poweroff-below 10 --poweroff-after 24h
m1power standby show
m1power standby off
```

While the guard is on, each suspend arms a dark wake every `--check-every`
(a unit is required, minimum 5 min, so a typo cannot loop suspend and
resume); on battery the target powers off below `--poweroff-below` percent or
after `--poweroff-after` (must be positive) asleep. Each decision is a
`standby` ledger record, never shown as a sleep. The settings are kept in
`/etc/m1power/standby.json`; the per-sleep state (when the current sleep began)
lives in `/run/m1power`, so a reboot starts it fresh instead of acting on a
stale sleep.

`--max-dark-wakes N` is a testing aid: after N dark wakes the Mac stays awake
instead of going back to sleep, so the host can reach it again.

## Hibernation

The target kernel is built without `CONFIG_HIBERNATION`, and enabling it would
not be enough. See the hibernation section of [STATUS](STATUS.md) for what
blocks it on Apple silicon and what `m1power` does instead.
