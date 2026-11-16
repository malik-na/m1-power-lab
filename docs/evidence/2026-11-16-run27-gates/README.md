# Run 27b: the two stuck power islands reproduce on 13.5 firmware, cable in (2026-11-16)

Kernel 7.2.11-run26 (linux-aurora m1power/s2r-rs1-135 a56c1c110 = run 22 + sep_target), run 22's
command line + `sep_target=1`, no watch (the sequence runs normally; `gate_record=1` records which
of the sleep sequence's 49 wait conditions are open). Lab job j1116-004112-67ab after a cold start
(0x0201 = 04). Thunderbolt cable in (M3 Max USB-C Left Back, M1 left back).

**Run 27 (j1116-002751-9d10) did not enter**: the power roles on the cable are renegotiated at
every M1 boot. Validated before the submit: the M1 sourced the M3 Max (ac 0, discharging). After
the lab's reboot into the test kernel the M3 Max sourced and the M1 charged (ac_online=1), and the
gate (charger offline required) timed out. Run 27b's gate requires discharging and no USB device;
the battery was set to `force-discharge` from outside at 06:12:15.99 and read back: Discharging,
-0.34 A, ac 1. The restart put it back to `auto`.

## Result

| | |
|---|---|
| stage 0x9f0a | 'R': the boot core reached the release |
| record 0x9f10-17 | 84 05 00 02 2d 2f ff 2f: cache flush done, window 80 us; **slow part's gates: 2 open, #45 #47** |
| 0x9f1a, 0x9f1c-1e | 02, 2d 2f ff: **at the release: 2 open, #45 #47** |
| 0x0201 | 04 -> 01 |
| postmortem | next boot 25 s after the recorded entry, alarm not reached, new boot id |

Outside (M3 Max clock, from the script's ENTRY 06:12:20.111): Thunderbolt paths torn down and
Wi-Fi silent +2.5 s; the M1's USB4 port dies ("host disconnected") +5.8 s; **the M1's type-C
detaches (SoC reset) +11.1 s = 5.3 s after the port died** (run 25 cable test: 5.4 s);
Thunderbolt connected again +29.8 s. GPU coprocessor running at the entry (0x10 / 0x2c).

## What it establishes

The same two wait conditions as run 22 on 2026-11-13 (macOS-27-era firmware) stay open on the
13.5 firmware, with the cable in: **#45 (power-gate record 0, after the SIO island)** and **#47
(record 30, after the PCIe and NVMe domains)**, both at the end of the slow part and at the
release. The reset follows ~5.3 s after the commit: the sleep sequence's own watchdog 2
(run 26 watch). The cable does not change which islands block.

Next: release the SIO-island domain Linux holds (`pmgr_pwrstate.always_on=fpwm1`) and read #45.
