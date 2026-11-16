# Run 35b: with SIO idle and its parents fully on, gate #45 still does not report ready (2026-11-16)

Lab job j1116-064811-50af. Kernel 7.2.11-run35b (23c61d2ce = run 35's f30994508 plus `sio_on`
clearing the auto flag, bit 28, on sio_busif, sio and sio_cpu, the way macOS commits them).
Run 35's command line and script, with only the kernel check changed. Cable in, force-discharge
at the gate (12:19:13), no cold start (0x0201 = 01 before).

Question (the agreed stop rule): does gate #45 (the SIO island) report ready once SIO is in
RTKit idle? **No.**

## Record

| | run 27 | run 32 (sio_on, SIO not running) | run 35b (sio_on + auto clear, SIO idle) |
|---|---|---|---|
| record 0x9f10-17 | 84 05 00 02 2d 2f ff 2f | #45 #47 | **84 05 00 02 2d 2f ff 00**: slow part, 2 open, #45 #47 |
| at the release 0x9f1a, 0x9f1c-1e | 02, 2d 2f ff | #45 #47 | **02, 2d 2f ff**: 2 open, #45 #47 |
| 0x0201 | 04 -> 01 | 04 -> 01 | 01 -> 01 (no cold start) |
| ending | ~11 s | ~10.8 s | postmortem reads 5 s, wake-restart |

The release record is written only after `sio_on`'s wait, so this time the wait passed: the
fix took the driver past run 35's refusal. Lab: `crashed_or_hung`, back 33 s after it went silent.
The scratch bytes 0x9f10-0x9f1f were zero after run 35 (no last stage), so these are fresh.

Not seen in this run: the `apple-sio ... RTKit idle` line. The journal lost the suspend's lines
with the reset. That SIO was idle is inferred from the same path acking 0 in runs 33, 34 and 35.

## What it establishes

- The hypothesis "gate #45 waits for the SIO coprocessor to idle through its firmware
  handshake" is not supported. SIO idle, its parents on and the auto flag cleared still leave
  #45 open. Gate #47 (PCIe / NVMe) is open as in every run.
- Per the stop rule agreed on 2026-11-16, the S2R track pauses here. Next: measure s2idle drain.

Raw state: var/m1-state/20261116-122032-run35b/ (private).
