---
name: verify-m1
description: Drive the real M1 MacBook Air (t8103, Omarchy Linux) from the M3 Max and prove hardware, power and sleep behavior with evidence. Use before claiming any change to the M1's kernel, sleep (s2idle or suspend-to-RAM), power domains, registers or tooling works; for "verify on the M1", "run a sleep test", "read the M1's registers", "snapshot the M1".
---

# Verify on the M1 Air

The "app" is a physical machine: an M1 MacBook Air (`m1-air-omarchy`, lab name `naeems-m1-air-r25`) running Omarchy's stock kernel, driven from the M3 Max this repo lives on. You prove behavior by running it on that machine and capturing what the machine itself reports, plus what the M3 Max sees from outside. There is exactly one M1: never drive it while something else is.

**Primary standing rule (Naeem): never assume, always validate.** Every statement about cables, ports, power, firmware or kernel comes from a reading you just took, quoted with its source. A type-C partner is not proof of a far-end device (an unconnected active Thunderbolt cable registers as one). If you cannot read it, say it is unknown and ask.

## Launch

There is no server. "Launch" is making the channels and recorders ready:

1. Channel. Cable in: `tools/tb/m1tb '<cmd>'` (root over IPv6 link-local on `thunderbolt0`; the M3 Max end must be in **USB-C Left Back**: on the M3 Max's Linux only that port has Thunderbolt). Cable out: `ssh m1ts '<cmd>'` (same key over Tailscale/Wi-Fi). Both use `~/.ssh/m1_tb_ed25519`; after an M1 reinstall run `tools/tb/authorize-m3-max.sh` on the M1 (its header has the one-liner).
2. M3 Max flight recorder, whenever the cable is in: `tools/tb/m3-blackbox &` (fsync'd kernel messages and a 1 s port/power heartbeat in `var/m3-blackbox/<boot id>.log`). The M3 Max has reset itself silently after Thunderbolt/USB-C link events (memory `m3-silent-resets-tb-link`); the recorder keeps the last seconds.
3. Outside observer for anything that sleeps or resets the M1: `tools/tb/m1-observe <label> &` (cable link, peer found/lost, Wi-Fi ping, port power roles, on the M3 Max's clock) into `var/m1-observe/`.
4. Ready = `doctor.sh` prints `VERDICT: drivable`.

Teardown: stop the observer and recorder you started with `kill -TERM <pid>` of the process you launched (it stops its children). SIGINT does not work for them when backgrounded.

## Doctor

```bash
.claude/skills/verify-m1/doctor.sh
```

Read-only, ~3 s. Checks the cable link and which channel to use, the flight recorder, both Macs' power, the M1's host, kernel, boot id, test-boot flags on its cmdline, system firmware (13.5 since the 2026-11-14 macOS reinstall), battery and `charge_behaviour`, type-C ports, the power chip's start byte `0x0201` (04 after a power-button start, 01 after a sleep restart), `m1power.ko`, Wi-Fi power save and gateway latency, and the lab's view. Exit 0 drivable, 1 not (a `FAIL:` line says why), 2 unreachable. Run it first, and again whenever anything looks off.

## Drive

Use the recipe in `features/` for the feature you are proving; read `features/README.md` first. All entry points:

- `tools/tb/m1tb` / `ssh m1ts`: commands as root on the M1.
- `tools/tb/m1-collect [label]`: run records, kernel logs (this boot and the previous one), power-chip bytes into `var/m1-state/<stamp>-<label>/` (set `M1TB_VIA=m1ts` for Wi-Fi).
- `tools/tb/m1-s2idle-cal [secs] [label]`: one s2idle cycle with the wake timer, observed from outside.
- `tools/regmap/collect-inventory.sh` + `tools/regmap/hwdb.py`: a hardware snapshot into `var/hwdb/m1-hw.db`.
- `tools/regmap/scan.sh <list> <label>`: crash-tolerant read-only register reads (Wi-Fi only, see Gotchas in its feature file).
- `lab run` / `lab retry` / `lab job`: one-shot test-kernel boots with a script; `lab mcp` (tool `lab_job`, argument `job_id`) for a job's JSON. Never read the maclab token from `~/.config/maclab/client.json`.
- `.venv/bin/m1power --target m1tb <cmd>`: the live power CLI (`doctor`, `knobs`, `watch`, ...).

## Evidence

- Raw evidence (private, gitignored): `var/m1-state/`, `var/m1-cal/`, `var/m1-observe/`, `var/regmap/`, `var/hwdb/m1-hw.db`, `var/m3-blackbox/`. Register values, decoded firmware programs and Apple-derived material stay there.
- Public summaries: `docs/evidence/<date>-<name>/README.md` (what ran, deviations named, timeline, what it establishes, what it does not), committed and pushed on `omarchy-live-power`.
- Proof standards: run the real path on the M1 (a lab boot of the real kernel, a real suspend), not a dry-run or a host test; capture the action and the resulting state; for sleep, both the M1's own records (postmortem, power-chip scratch, boot ids) and the M3 Max's outside timeline; a deviation from a recorded run is named in the script and the write-up; "it entered" is not "it slept", and a restart through a boot is not a wake (boot id changes).

## Cleanup

- Kill only the observer/recorder processes you started (by PID). Never `pkill -f` a pattern that matches your own command line.
- Put back what you changed on the M1: `charge_behaviour` to `auto` (the restart resets it, check anyway), DPMS on. Never change its network config or idle/lock/brightness defaults to stabilize a test.
- A lab job returns the M1 to its known-good kernel by itself; wait for `lab job <id>` to finish before the next run.
- Cleanup never deletes `var/` evidence.

## Rules that bind every run

- With the cable in, do not deliberately crash or reset the M1 (unknown-register reads, suspend-to-RAM entries) unless Naeem accepts the risk for that run; the M3 Max may reset. Prefer Wi-Fi with the cable out for those.
- No full-load builds on the M3 Max while the M1 is being driven (`docker run --cpus 12`).
- Downloads get a written security check first; nothing is pulled from Asahi repositories.
- Commit and push as you go (`omarchy-live-power`, identity Naeem Malik).
