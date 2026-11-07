# Linux suspend-to-RAM on the M1 Air (t8103): first runs

Kernel: malik-na/linux-aurora `m1power/s2r-mem` (base omacom/linux-aurora b798f2b = 7.2.11-14,
plus the m1power CPU-hotplug and PMU-RTC branches). New: `drivers/soc/apple/apple-s2r.c`, an opt-in
(`apple_s2r=1 apple_cpu_hotplug=park`) `platform_suspend_ops` for "mem" whose `cpu_suspend()` finisher
runs the sleep commit macOS 27 performs on this SoC (traced under the m1n1 hypervisor, see
../2026-11-06-mac27-hv/), and an S2R deep-stop mode for the secondaries in `smp_apple.c`. Built on the
maclab builder against the M1's own config; run as one-shot maclab jobs (`target/lab/m1power-s2r-mem.sh`,
read back with `target/lab/s2r-mem-readback.sh`), USB-C cable unplugged, on battery.

Stage 1 has no resume: the wake enters the resident m1n1 at the locked RVBAR, which does not know how to
hand back to Linux; a watchdog-1 dead-man (170 s) resets the SoC so the lab gets the Mac back.

Progress markers in PMU scratch 0x9f0a: P (prepare), N (noirq done), E (enter, secondaries offline),
then a..g through the finisher (g = the last commit written, next is the deep WFI); 0x9f04 = 'P' or 'L'
+ the RTC second at prepare / at the commit.

## Before any run: review

A review workflow caught a blocker: the SoC windows were mapped with `ioremap()` (posted, nGnRE); t8103
MMIO must be non-posted (`ioremap_np()`), otherwise every write in the finisher is rejected while
`cpu_suspend()` has SError masked — no alarm, no commit, no markers, a machine that sleeps forever.

## Run 1 (job j1107-140441-7775, build 13a1aa29): hung before the finisher

Entered "mem" at 19:38:27; dark; no reboot (no dead-man yet, it was armed only in the finisher); long
press at 19:43. Next boot: 0x9f0a = 0, no note, boot_stage 0x30, alarm untouched — the finisher never
ran. Cause: the secondaries each armed ACC_OVRD's deep-sleep bits, which are per cluster, while CPU0 (E
cluster) and other P cores were still running; the next idle WFI could power a cluster off under a live
core. Fix: only the last core of a cluster CPU0 is not in arms them; CPU0 arms its own in the finisher.
Also: the dead-man is now armed at the end of `.prepare` and given back to apple_wdt in `.finish`.

## Run 2 (job j1107-142600-37b7, build aca68b69): the SoC entered S2R and the alarm fired

Entered "mem" at 19:59:27 (camera: the M1's screen went dark at 19:59:30). Next boot (by itself, at
about 20:02:40), PMU:

| Field | Value | Meaning |
|---|---|---|
| 0x9f0a | `g` | every finisher step ran, through the third S2R-timer commit |
| 0x9f04 | `L` + 0x2bae33 | the commit's RTC second |
| 0x9f01 boot_stage | 0x50 | written by the finisher |
| RTC alarm | 0x2bae6f = commit + 60 s | programmed by the finisher |
| alarm_ctrl 0xd000 | 0x41 → 0x01 | the alarm fired (as in every macOS alarm wake) |
| boot − commit | 181 s | = dead-man (170 s) + boot, **not** commit + 5 s |

The last row is the key: when an S2R entry does not complete, the AON engine's WD2 (armed at the
commit, 5 s) resets the SoC — that is how every failed macOS entry under the hypervisor ended. Here WD2
did not fire, so the hand-off completed and the SoC went into suspend-to-RAM from Linux. The alarm then
fired; the wake entered the resident m1n1, which has no Linux resume, and watchdog 1 reset the SoC 170 s
after the commit.

Not measured yet: the power during the sleep (the window is short, and the reboot follows a hung wake).

## Next

Stage 2, the resume: Linux writes the m1n1 wake note ('W' + the physical address of a resume stub that
calls `cpu_resume`) before the commit, and the resident m1n1 at the locked RVBAR must be one that
honours it (our trampoline build) — on this Mac that means installing it as the Omarchy volume's boot
object, a Recovery step for the owner. Then: devices back, the long sleep for the power number.
