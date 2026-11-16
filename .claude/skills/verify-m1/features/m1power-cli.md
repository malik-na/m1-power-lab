# m1power CLI

`m1power` is the repo's live power tool (see docs/LIVE.md): it inventories the target, reads every SMC key, lists and changes tunables, and runs measured sleeps and A/B tests. On the reinstalled M1 only its read-only commands are verified; its agent is not installed.

## Sub-features

- `cli-doctor` inventories the target and what is set up.
- `cli-knobs` lists every tunable and its current value.
- `cli-smc` reads named SMC keys.

## How to get to it (user POV)

- Run `.venv/bin/m1power --target m1tb <command>` (or `M1POWER_TARGET=m1tb .venv/bin/m1power <command>`).

## Driving it with .venv/bin/m1power

Preconditions:

- Doctor reports `drivable` via the cable (the `m1tb` ssh alias), and `M1 m1power_ko loaded` for `smc`.

- **Doctor.** Run `M1POWER_TARGET=m1tb .venv/bin/m1power doctor`. Exit 0 and a knob table ending with lines such as `wifi on`, `backlight <n>`, `pmgrgate:atc1 on`.
- **Knobs.** Run `M1POWER_TARGET=m1tb .venv/bin/m1power knobs`. One line per tunable with its value; nothing changes.
- **SMC.** Run `M1POWER_TARGET=m1tb .venv/bin/m1power smc PSTR zSPa`. Two key lines with values.

## Gotchas

- The default target is `root@naeems-m1-air`, a host key from before the reinstall: always pass `--target m1tb` (cable) or `m1ts` (Wi-Fi).
- `m1power install`, `tune apply`, `knob`, `ab`, `sweep` and `sleep` change the M1 (agent, systemd units, Wi-Fi and PCIe link settings). An earlier tuning left Wi-Fi in a high-latency power-save state: do not run them without Naeem's go for that change.
- The `m1power` helper agent (`/var/lib/m1power`) is not installed on the reinstalled M1; commands that need it fail until `m1power install`.
