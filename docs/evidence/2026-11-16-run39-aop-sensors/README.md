# Run 39: AOP sensors off and ordered, acknowledged AOP stops: the restart stays at 5.0 s (2026-11-16)

Job j1116-143547-0578, kernel 7.2.11-run39 (s2r-rs1-135 c403d79c1, package sha256 551cf71f84d2…),
run 37's set (watchdog 2 moved to 100 s, PMP idled, mac_off) plus:

- `aop_sensors_off=1`: before the AOP queue stops, the light sensor's properties 0x16, 0x5c and
  the report interval 0x00 set to 0, and the lid angle sensor's interval, as macOS 13.5 does
  (hv runs 135r5/135r6, `docs/evidence/2026-11-16-hv-macos135-wake/`).
- `aop_stop_acked=1`: the eight queue stops in macOS 13.5's order, each answer (0x87) waited for.

## Before the entry (run script, read only)

- `aop_als` bound (`als.0.auto` -> `iio_aop_als`), calibration file present, reading 43.49 lux:
  **in every earlier Linux run the AOP was sampling the light sensor every 200 ms through the
  sleep.** No lid angle driver bound (no `las` service device).
- Run 35's log (j1116-063331-8519) already shows eight `0x87` answers to Linux's unordered stops
  (logged then as "unknown message"): the AOP did answer them.

## Result

| M3 clock | Event |
|---|---|
| 20:07:56.30 | rmmod apple-sep, suspend |
| 20:07:59.51 | USB4 host disconnected on the M3 (the release) |
| **20:08:04.51** | **SBX disconnected: the M1 restarts, 5.0 s after the release** |

Power chip after the restart: 0x0201 = 01 (no wake sequence reached its power-chip write, as
before), 0x9f02 unchanged. Record 0x9f10-17 `d2 01 04 05 64 01 01 31`: watchdog 2 seen armed and
moved to 100 s, PMP idle acked, byte 7 = 0x31: moved, **8 of 8 queue stops answered**, **1 of 3
sensor property writes accepted** (status 0). Which one is not recorded; on this ALS part
(CT720) Linux's own driver writes only the calibration and the interval, so 0x16/0x5c may be
refused here.

**The restart is unchanged.** Ordered, acknowledged stops make no difference. Sensors off is not
fully excluded: if the accepted write was not the interval, the light sensor kept reporting.

## Next

- Record which sensor writes the AOP refused (dmesg does not survive the restart: put each status
  in the record).
- The other differences from macOS's last second still open: NVMe (ANS) AP power 0x201 + IOP power
  0x201 (Linux shuts the controller down instead), SIO AP power 0x201, SMC AP power 0x201.
- Or run Linux itself as the hypervisor guest with the same tracer, to diff its entry against
  macOS's message by message.
