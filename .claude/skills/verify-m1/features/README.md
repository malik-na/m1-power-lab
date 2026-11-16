# M1 Air verification map

The maintained source for proving the M1 Air's hardware, power and sleep behavior from the M3 Max. Read this index, then use the matching feature file as the recipe.

## Baseline preconditions

- `.claude/skills/verify-m1/doctor.sh` prints `VERDICT: drivable` (run from the repo root).
- No lab job or test boot is running on `naeems-m1-air-r25` (doctor checks the cmdline and `lab status`).
- The M1 runs the stock kernel `7.3.0-0test5-1-ARCH` unless the feature itself boots a test kernel.
- Cable in: the M3 Max end is in USB-C Left Back, and `tools/tb/m3-blackbox` is running.
- Charger state is read, not assumed: doctor's `M1 ac` and `M1 battery` lines.

## Driving conventions

- Commands on the M1 go through `tools/tb/m1tb '<cmd>'` (cable) or `ssh m1ts '<cmd>'` (Wi-Fi), as root.
- Every command runs from the repo root on the M3 Max.
- One run at a time on the M1. If doctor says something else is driving it, stop.
- A step that sleeps or resets the M1 runs with `tools/tb/m1-observe <label>` in the background, started first.

## Proof and skip reporting

- Proof is the M1's own record plus, for sleep and resets, the M3 Max's outside timeline with times on its clock.
- Quote the reading behind every statement (file, command and value).
- A restart through a boot (new boot id) is never reported as a wake or a resume.
- Report an unreachable path with the attempted command and the unmet precondition. Never report a skipped entry point as verified through another.
- Raw values stay in `var/`; the summary goes in `docs/evidence/`.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the behavior. It then uses exactly four H2 sections in this order: `Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>`, `Gotchas`.

## Features

- [Hardware snapshot](./hardware-snapshot.md): inventory of devices, drivers, power domains and SMC keys into the hardware database.
- [Register read](./register-read.md): crash-tolerant read-only reads of named registers or whole blocks.
- [s2idle cycle](./s2idle-cycle.md): one ordinary sleep and timed wake, observed from outside.
- [Suspend-to-RAM entry](./s2r-entry.md): one deep-sleep attempt on a lab test kernel and its postmortem.
- [m1power CLI](./m1power-cli.md): the live power tool's read-only commands against the M1.
