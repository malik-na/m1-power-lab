# Run 26 (watch): what the chip's sleep sequence waits on (2026-11-16)

## Setup

- **Firmware**: the M1's macOS was reinstalled as 13.5 on 2026-11-14, so its system firmware is
  13.5 (iBoot-8422.141.2, os-fw 13.5, read from /chosen). Runs 1-22 ran on macOS-27-era firmware;
  run 25 and every run tonight on 13.5. A rebuilt run 22 on 13.5 is therefore not a replica.
- **Kernel** 7.2.11-run26: malik-na/linux-aurora `m1power/s2r-rs1-135` a56c1c110 = run 22's
  ed5e15e8d + `apple_s2r_rs.sep_target` (the Secure Enclave counts as on by its target nibble:
  under 13.5 it gates itself ~1.4 s after its driver's last exchange, power word 1000230f, and
  run 22's rule then never claimed its mailbox). Host tests 18/18. Built offline in maclab's
  builder image (gcc 14.2 Debian, rustc 1.93.1, the test kernel's own config; download check in
  var/kernels/run22-rebuild/SECURITY-CHECK.md).
- **Command line**: run 22's exactly, plus `sep_target=1 watch_ms=2500` (the driver's own
  diagnostic: after the release the boot core stays up 2.5 s and records, every 10 ms, the
  engine's progress word, the wake sources set and watchdog 2, into the power chip's scratch).
- **Script**: run 22's, with three named deviations: the kernel stamp; the gate allows a stale
  type-C partner (port0 kept one, no PD, no power, after the Thunderbolt cable was removed; it
  cleared on the next boot); the enclave bring-up ends at its driver's last line whether that is
  "hwrng: registered" or, as on every boot since the 13.5 reinstall, "hwrng: survey failed after
  5 attempts (EIO)"; and the pre-entry enclave check reads the target nibble (run 25's rule).
  Plus one record-only line: the GPU coprocessor's run control / status before the entry.
- Lab job j1115-235453-4495, after a power-button cold start (0x0201 = 04), on battery, cable out.

## Result

Entry 05:26:08.7 (GPU coprocessor at the entry: run control 0x10, status 0x2c: **running**).
Next boot 20 s after the entry (postmortem), ending "5 s" by the chip's clock, no wake at the
alarm. Watch record (PMU scratch):

| Byte | Value | Meaning |
|---|---|---|
| stage 0x9f0a | 0x53 'S' | the boot core watched the full 2.5 s |
| ticks 0x9f1a | 0xfa | 250 x 10 ms |
| record 0x9f10-17 | c0 00 10 50 01 00 ff 45 | last change at tick 0; clusters E 0x10 / P 0x50; engine progress 0x01; 0 wake sources; **watchdog 2 control 4, 5 s** |
| 0x0201 | 04 (stays) | the sequence did not get past its first step (expected: the watching core keeps its cluster up) |

So **watchdog 2 is armed for 5 s when the always-on engine's sleep sequence starts at the
release**, and no wake source fires. The "5 s ending" of every Linux run is that watchdog:
the sleep sequence does not finish within 5 s.

## What it waits on

Run 22's `gate_record` bytes `02 2d 2f` (earlier read as "wake sources 45, 47": that was the
old after-script's label for a different layout) say 2 of the sequence's 49 wait conditions
were open at the release: **#45 = 0x23b71c090** and **#47 = 0x23b71c360**, bit 30 of each must
read 1. That page lies outside the device tree's PMGR window; m1n1 (proxyclient/m1n1/hw/pmgr.py)
names it `PG1` (power gates at +0x1c010) and `PG1CFG` (69 power-gate records of 24 bytes from
+0x1c090). Read awake on the stock kernel: #44 0xc0040301, **#45 0x8004030c**, #46 0x?004030e
(bit 30 toggles with activity), **#47 0x8004030b**, #48 0x80040317. A display on / off test did
not move #45 or #47.

The sleep sequence (decoded earlier from the always-on engine's memory, kept private) polls
#45 right after switching off the **SIO island** (SIO processor and bus interface, audio DMA,
PWM incl. the keyboard backlight's fpwm1, I2C, SPI, UARTs, MCA, DPA, AES), and #47 right after
switching off **PCIe (incl. the Wi-Fi link) and the NVMe controller (ans2)**. The earlier
reading "stalls at its display step" is superseded: no display domain is in either group.

So on Linux the SIO island and the PCIe/NVMe island never report ready. Leads to test one at a
time (gate_record without watch says which gates stay open):
1. run 22 holds `pmgr_pwrstate.always_on=fpwm1` (run 25 held fpwm1, gfx, sio_busif, sio): drop it;
2. the Wi-Fi PCIe link and the NVMe controller at the commit.

Files: none copied: the run's log and the PMU bytes are in var/m1-state/<stamp>-run26 (private).
