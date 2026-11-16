# Linux's sleep entry under the m1n1 hypervisor, against macOS 13.5's (run lx4, 2026-11-16)

Linux (kernel 7.2.11-run39, run 39's command line with `wake_path=0`) booted as the hypervisor guest
with the same tracer as the macOS runs (`tools/hv-trace-kit/hv_s2r_trace.py`, AFK ring decoding on).
Guest image: our m1n1 (bd6a43d4 with a 4 KiB variable limit, `~/m1n1-guest`) + bootargs + J313 DTB
with the proxy port (atc0: dwc3, DARTs, PHY, ACIO, usb-pd@38) disabled + run39 initramfs + kernel
(`var/hvlinux/`, private). No network or console in the guest: the entry is made by
`m1hv-autos2r.service` (`tools/hv-trace-kit/guest/`), which runs only with `m1hv.autos2r=1` on the
command line; it loads and unloads `apple-sep` as run39.sh does (`modprobe.blacklist=apple_sep`).
Run lx3 stopped in prepare (SepSleep: the enclave answered 0x100 with its driver still bound);
lx4 went to the commit. The hypervisor ran without real S2R pass-through: the CPUs exit to m1n1 at
the commit, so everything up to the commit is real and nothing after it is.

Traces (private): `tools/hv-trace-kit/runs/20261116-linux/s2r-trace-lx4.jsonl`, extracted windows
`lx4-entry.txt` and `mac135r6-entry.txt`.

## Side by side (t in s from MBSE slpw)

| | macOS 13.5 (135r6) | Linux run39 (lx4) |
|---|---|---|
| NVMe (ANS) | +0.49: syslog acks, **AP power 0x201, IOP power 0x201** (idle) | -0.01, before slpw (device suspend): **AP power 0x10, IOP power 0x1** (quiesced / sleep) |
| SIO | +0.04: DMA channel stops on ep 0x20 (channels 4-8, then 0x0d); **+0.72, after slpa and 0x9f01**: AP 0x201, IOP 0x201 | no channel messages; +0.12, before slpa: AP 0x201, IOP 0x201 |
| PMP | +0.20: 0x20e display notifications (devs 0x54/0x55 on, then off), +0.23: **0x208 dev 0x63 (GFX) off**; **+0.72, last**: AP 0x201, IOP 0x201 | **+0.001, first**: AP 0x201, IOP 0x201; no 0x20e/0x208 messages |
| Secure Enclave | +0.46, after the AOP: sleep message, answered | +0.003: sleep message, answered (same message, other tag) |
| AOP | ALS and **LAS (ep 0x25)** interval 0; stops in three batches; AP 0x201 at +0.41 | ALS 0x16, 0x5c, interval 0 (all answered); **nothing to ep 0x25**; stops one by one; AP 0x201 at +0.12 |
| SMC | WKTP 02 at +0.23; slpa at +0.68; AP 0x201 | WKTP 02, slpa at +0.13; AP 0x201 |
| power chip 0x9f01 = 0x50 | +0.69, right after the SMC's AP power | +0.19, after the CPU_START writes |
| CPU_START, PS words, RTC alarm | +0.77 on | +0.16 on |

The Secure Enclave, SMC and AOP steps now match apart from order and the lid angle write. The
NVMe controller is left in a different power state (Linux: IOP sleep 0x1, AP quiesced 0x10; macOS:
idle 0x201 both), the PMP and SIO go down in a different order, and Linux never sends the PMP the
GFX power-down (0x208 dev 0x63) or the display notifications.

## Next (one Linux run, all together)

1. NVMe: idle the controller (AP 0x201, IOP 0x201) instead of shutting it down, at macOS's point
   (after the AOP, before slpa).
2. SIO and PMP: their AP/IOP 0x201 after slpa and 0x9f01, SIO then PMP; PMP gets 0x208 dev 0x63.
3. Lid angle sensor: interval 0 on ep 0x25 (no Linux service registers it).
4. 0x9f01 = 0x50 right after the SMC's AP power, before SIO and PMP.
