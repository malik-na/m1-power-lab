# Linux under the hypervisor with real S2R: it restarts too, so the fault is in the state Linux leaves, not in its commit path (run lx11, 2026-11-16)

Linux 7.2.11-run40 (run 40's command line, `wake_path=0`) as the m1n1 hypervisor guest, eight
cores, real S2R pass-through armed 30 s after the guest start (`harness/golinux.sh`,
`harness/drivelinux.sh`), the entry made by the guest's own unit. One console reader, checked
with `fuser` before the start: the guest booted (lx5-lx10, with three to five stale readers on the
console port, all froze; see `docs/evidence/2026-11-16-run40-mac-order/`).

| M3 clock | Event |
|---|---|
| 23:00:44 | real S2R armed (stage two, wake handler written at the commit) |
| 23:02:32.99 | guest: `echo mem > /sys/power/state` |
| 23:02:33.89 | the M1's USB device leaves the M3: the commit (m1n1 turns USB off as the last core goes down) |
| 23:03:04.00 | Thunderbolt: `new host found ... Linux m1-air-omarchy`: the M1 has restarted into Omarchy |

No wake into m1n1's handler. Commit to Omarchy's Thunderbolt host: 30.1 s; in bare-metal run 40 the
same interval was 29.7 s with the restart at 5.0 s, so the restart here was about 5 s after the
commit as well (inferred from that interval; the moment itself was not observed). Power chip
afterwards: 0x0201 = 01, as in every bare-metal run.

macOS 13.5 through the same hypervisor commit path woke three times out of three (135r2, 135r5,
135r6). **So the ~5 s restart follows the state Linux leaves the machine in, not Linux's own last
stage or the stage-1 wake vector.**

## Register writes between MBSE slpw and the commit, both under the same tracer

(macOS 135r6 against Linux lx11; mailboxes, SPMI and SMC SRAM left out. Linux's last stage, the
carry words, cluster state and the S2R timer write, comes after m1n1 has cut USB and is not in its
trace; `s2r_seq.rs` does write them.)

Same in both: watchdog words, the five clock-generator words, PMGR 0x48000-0x48c00, power gates
0x1c080/0x1c088, 0x18000/0x18004.

| Register | macOS 13.5 | Linux run40 |
|---|---|---|
| DISP0_FE, DISPEXT_FE (0x360, 0x368) | written 0x23f0 (target off) | not written |
| DISP0_CPU0, DISPEXT_CPU0 (0x10018, 0x378) | 0xf0403f0 (target off) | not written |
| RMX (0x350) | 0x300 (target off) | not written |
| APCIE_ST (0x418) | 0xf0003f0 (target off) | not written |
| SPI2 (0x250) | 0x3f0 | not written |
| aon-pmgr 0x23d2dc100 | 0x100 | not written |
| SIO_CPU (0x1d0) | 0x0400024f | 0x0f0002ff |
| GFX (0x3f8) | 0x0f0023f0 | 0x0f002b00 |
| I2C0, I2C3 (0x1f0, 0x208) | 0x3f0 | 0x200 |
| GPIO (0x130) | not written (stays on) | **0xf0 (target off)** |
| MCA2, I2C1, SIO_ADMA, DPA1 | not written | 0xf0 (target off) |
| wake enable words 0x23d004008-18 | not written | written (wake_mask=2) |
| watchdog 1 | control 0 | armed 170 s (the driver's net) |

"Not written" in this window does not say what state the domain is in: a read-back of each word
right before the commit, on both systems, is the next reading. The engine's wake sequence 10 polls
ps_gpio for fully on and the i2c/uart/spi words for state 4.

## Next

One Linux run that leaves these words as macOS does (GPIO left on; display, RMX and APCIE_ST
targets off; SIO_CPU, GFX, I2C0/I2C3 values as macOS writes them; MCA2, I2C1, SIO_ADMA and DPA1 left
alone), with each word's value read back before the commit and kept in the trace.
