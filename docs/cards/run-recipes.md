# Run recipes: the commands for each kind of run, in order

Bare-metal Linux sleep runs, unattended switch runs, macOS under the hypervisor, and the reads around them.
2026-11-20. Every tool that reboots the M1 refuses while another user's claim stands.

## Before anything

- `tools/status.sh`: claim, kernel, uptime, last hypervisor run, repos, build, agents; quote it, say "not read" for the rest. [tools/status.sh header; AGENTS.md]
- `tools/prior-art.sh <word>...`: our evidence, the reference deep-dive, Aurora's repos, most hits first; before any probe or build. [tools/prior-art.sh header; docs/agents/probe-lane.md step 1]
- `tools/hv-trace-kit/harness/m1-state.sh [label]`: one VERDICT from USB, Thunderbolt, host process, newest log, plus a camera frame you must look at. [m1-state.sh header; AGENTS.md]

## Bare-metal sleep run (one sleep)

| # | Command | Refuses / notes | Source |
|---|---|---|---|
| 1 | `tools/tb/m1-claim take <who> "<why>"`; then `export M1_CLAIM=<who>` | fails if someone else holds it | [m1-claim header] |
| 2 | `tools/kbuild-clean.sh <tag> [commit]` | builds the committed HEAD (or commit) of `~/Work/deepsleep-kernel` only; out `~/.cache/m1-s2r-kb/io-clean/out/kernel.tar.zst` | [kbuild-clean.sh header] |
| 3 | write `var/deepsleep/<tag>.cmdline` (one word per line) | e.g. ds29's: `apple_deepsleep.enable=1 alarm_secs=20 wdt=150 wakemark=3 cand=0xc0000` | [var/deepsleep/ds29.cmdline] |
| 4 | `tools/tb/m1-bootonce <kernel.tar.zst> <tag> <cmdline-file>` | runs `m1-claim check`; deletes older `/boot/efi/s2r/*/`; needs 80 MB free on the ESP; one-shot Limine entry `m1tb-<tag>`; default untouched | [tools/tb/m1-bootonce] |
| 5 | unbind `apple_wdt` on the M1 | a `wdt` sleep with Linux's watchdog driver bound is refused (-EBUSY, D7 (e)); how ds28 unbound it is not recorded | [evidence 2026-11-17, ds28 "refused sleep"; glue.c `wdt` parameter] |
| 6 | set runtime parameters in `/sys/module/apple_deepsleep/parameters/` (`cand` etc.) | `cand` is read at each entry | [glue.c `cand` parameter] |
| 7 | `systemd-run /bin/bash /var/lib/m1power-ds/real.sh` | refuses with `wdt` 0 unless `snap=4` or `ALLOW_NO_WDT=1` (Naeem's named run only); writes `real.out`, dmesg before/after | [tools/tb/guest/ds-real.sh] |
| 8 | note the commit time on the M3; wait for the reset | | [read-breadcrumb.sh header] |
| 9 | `tools/m1n1/read-breadcrumb.sh --commit "<time>" --alarm 20 --wdt 150`; `tools/tb/m1-pmu-dump [label]` | both read-only; read before the next sleep overwrites `0x9f04`-`0x9f0d` | [their headers] |
| 10 | `tools/tb/m1-claim release <who>` | | [m1-claim header] |

## `apple_deepsleep` parameters

| Parameter | What it does | Source |
|---|---|---|
| `enable` | offer `mem_sleep` "deep" through the tested logic; without it nothing runs | [glue.c 77-78, header] |
| `alarm_secs` | seconds from the sleep's start to the power chip's alarm | [glue.c 81-82] |
| `wdt` | arm watchdog 1 first in `begin` and again at the commit point; N s, max 178; unarmable N refuses the sleep; disarmed last on every way back | [glue.c 101-102] |
| `cand` | bits 1-17 = candidates C1-C17; bit 18 = C18, the `pmp` client | [glue.c 135-136] |
| `snap` | 0 off; 1 snapshot 792 words, 'C' record, back without power-down; 2 same then commit; 4 before the entry only, logic not called | [glue.c 89-90] |
| `probe` (`probe_k`) | read open-question values (spec 56, 64, 65); record 'Q'/'q' | [glue.c 118-123] |
| `trace` | progress marks into `0x9f04`-`0x9f0d` during the entry | [glue.c 126-127] |
| `dump` | log the domain words in `prepare_late` and at the start of wake | [glue.c 85-86] |
| `wakemark` | diagnostic: bit 0 stub bite 60 s + `'Dr'` before `leave_early` (90 s); bit 1 `'DA'` if core 0's WFI returns late | [glue.c 114-115] |

## Unattended switch runs

- `tools/tb/m1-cand-runs <kernel.tar.zst> <tag> <cmdline> <out.tsv> <mask>...`: per mask: boot once, set `cand`, `real.sh`; outcome WOKE / RESET / DARK (DARK stops the series); a camera frame after each non-wake. [m1-cand-runs header]
- It runs `m1-claim check`; `wdt` must be on the command line. It does not unbind `apple_wdt`. [m1-cand-runs 16, 27]

## macOS under the hypervisor (readings of macOS only)

1. Claim as `observation`. [evidence 2026-11-17, Hypervisor round 6 recipe]
2. `WD1=150 ALARM=90 FULL_SKIP=<det8's four pages> [S2R_ARGS='...'] harness/macos-up.sh detNN` (proxy, chainload `~/m1n1-next`, go135, drive135; prints READY). [macos-up.sh header; evidence round 5 "Commands"]
3. `harness/detach135.sh detNN` (cable may come out after "detached"). [detach135.sh header]
4. `nohup harness/detached-wake-readout.sh detNN &` (reads the log before macOS sleeps again). [its header]
5. `harness/hv-reboot.sh`, then `tools/tb/m1-pmu-dump` once Linux answers; release. [evidence round 6 recipe]
- No run without a no-hands way out: the alarm (commit + 90 s) and watchdog 1 (commit + 150 s). [AGENTS.md; evidence round 6]
- About 14 min a run (det11 22:57-23:11); the idle sleep comes 434-438 s (about 7 min) after the detach. [evidence round 5 heading; evidence round 2 "Run B"]
- Under the hypervisor, Linux is not slept: Linux is read on bare metal. [AGENTS.md]

## Safe USB-C restart

- `M1_CLAIM=<who> tools/m1-reboot/m1-reboot.sh [reboot|nop|dfu|which]`: Apple VDM via tipd debugfs; never loads/unloads drivers; refuses without the command file. [m1-reboot.sh header]

## Durations

- Build about 2 min (ds29: 06:14:55-06:16:39). [~/.cache/m1-s2r-kb/io-clean/build-ds29.log times]
- Sleep start to the stock kernel's answer with `wdt=150`: 165 s. [evidence 2026-11-17, ds29]

## Read more

- `docs/agents/probe-lane.md`
- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, "Hypervisor round 5" and "ds29"
- `tools/hv-trace-kit/harness/README.md`
- `~/Work/deepsleep-kernel` `drivers/soc/apple/deepsleep/glue.c` 75-140
- `AGENTS.md`, operator corrections
