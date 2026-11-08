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

## Runs 3–12 (2026-11-07/08): the wake never reaches the boot CPU

Stage 2 work replaced the ESP stage-2 m1n1 with a build whose reset path handles the wake (omacom
bc79acc4 + m1power commits, local tree `~/Work/m1n1-omacom-s2r`), installed with
`target/lab/install-stage2-wake.sh`. Every Linux run below entered S2R cleanly (stage `g`, no WD2
reset, alarm fired) and rebooted at **commit + ~181 s** (the WD1 dead-man):

| Test | Change | Result |
|---|---|---|
| 3 | wake note in `_cpu_reset_c` | no wake mark — the note check ran after UART output |
| 4–6 | note before any UART output; then `cpu_reset` without `debug_putc`; then cable out | no `v` mark |
| 7 | dead-man off | the M1 stayed down until a long press: nothing restarts it without WD1 |
| 8 | WD1 "progress meter" at each reset-path stage | 181.0 s: **not even the first instruction at the RVBAR ran**; the final `wfi` did not return |
| 9 | macOS SMC sleep handshake (MBSE slpw, WKTP=2, slpa, AP 0x201 — all acked) + MCC M1–M4 flush | 181.2 s |
| 10 | + `pd_ignore_unused` (pms_sram etc. stay on) | 181.2 s |
| 11 | + DRAM retention probe | inconclusive: the probe page is lost in a plain WD1 reset too |
| 12 | nub-spmi IRQ words as macOS leaves them; RVBAR pre-check | 181.4 s; the RVBAR page is reserved and byte-identical to the stage-2 image |

## Bisection from the working macOS case (macOS 27 under the m1n1 hypervisor)

Each run blocks one group of macOS's sleep messages in the hypervisor (the message is swapped for a
harmless RTKit PING / SMC READ_KEY and the real reply relabelled, so macOS still completes the sleep);
`tools/hv-trace-kit/hv_s2r_trace.py`, `S2R_BLOCK=aop,pmp,smc,mcc`. Each valid run's log shows the swap
and the faked reply before `slpa`.

| Run | Blocked | Result |
|---|---|---|
| try56 | nothing (baseline) | slept, woke at the alarm (wake source 54), resumed |
| try57 | nothing; AOP mailbox traced | woke; the AOP's only sleep message is ep0 SET_AP_POWER 0x201 (between slpw and slpa) |
| try58 | AOP | invalid: hook bug (128-bit data list), nothing blocked |
| try59 | AOP SET_AP_POWER 0x201 | **woke** — AOP ruled out |
| try60 | AOP + PMP + SMC + MCC | invalid: macOS panicked (MBSE `panb`) before `slpa` |
| try61 | AOP + PMP + SMC | invalid: macOS panicked right after the PMP 0x201 pair was swapped — the PMP block is detected |
| try62 | SMC: MBSE slpw/slpa, WKTP, SET_AP_POWER 0x201 | **woke** — the SMC handshake ruled out |

## The reconfig engine's wake sequences

The AON reconfig SRAM (0x23df00000, 128 KiB, locked by iBoot) was dumped read-only from the m1n1 proxy
and decoded (12 sequences; layout as PongoOS's A11 recfg, table at SRAM + 0, entries PA >> 4). No
sequence touches the CPU implementation registers, IORVBAR, CPU_START or the cluster power states, so
the boot CPU is **not** released by the reconfig engine. The progress registers (0x23d2b8028/8040) are
cleared by a WD1 reset, so they cannot be read after a failed wake. The dump and decode stay private
(`var/recfg/`).

## Where this leaves it

Ruled out: the stage-2 reset path, the RVBAR page, the cable, the dead-man, the SMC handshake (both
ways), the AOP, the MCC flush, the PMU alarm programming and the nub-spmi IRQ setup. The one candidate
that neither side has tested is the **PMP**: Linux never starts it (pms_sram is off from boot), macOS
runs it and idles it at sleep, and macOS will not complete a sleep with the PMP idle pair blocked. The
next test would be Linux with the PMP running (m1power/pmp-v1-overlay) and idled as macOS does, plus a
no-sleep diff of the registers the wake sequences poll, Linux vs macOS at the commit.

## The last three Linux runs (budget 10/10)

| Run | Change | Result |
|---|---|---|
| 9 (test 2) | PMP started (pmp_v1) and idled (AP 0x201 + IOP 0x201) between slpw and slpa | 180.9 s, no wake. A no-sleep self-test later confirmed the idle path itself works (idle → 0; the following wake → -62, a warm restart is needed) |
| — | PMP idle self-test (no sleep) | idle acked |
| 10 | AON wake masks copied from the macOS run that woke (only 26/27/38/81 masked) | 181.2 s, no wake; the results byte now survives: slpw/WKTP/slpa/SMC 0x201 acked, MCC flushed |

A commit-time register comparison (Linux vs the try55/try62 traces, over every register the reconfig
engine's wake sequences poll) found most differences rewritten by the entry sequences right after the
commit. Remaining untested differences: ps_atc0_common (Linux target 0xf, always-on in the DT; macOS
target 0) and ps_gfx (Linux target 0xf + auto-enable; macOS 0). Neither register is read by the
macOS trace at the moment that matters, so they are candidates, not findings.

The Wi-Fi watchdog (target/wifi-heal) now also cycles power save when the gateway answers slowly.

## Run 11 (2026-11-08): XNU core order (global sleep), past the budget

Approved by the user through a side session ("Tell the agent to go for it."). The macOS traces
(second sleep in try54, also try57/try62) show every secondary core writing its own CPU-start stop bit
about 40 ms before the commit but staying up, and all eight cores setting ACC_OVRD deep and entering
WFI together only after it. Linux before this put each secondary into deep WFI at cpu_die, long before
the commit, so the P cluster was already down. Kernel m1power/s2r-pmp b6b2ea1d1 (7.2.11-labgs2): the
stop argument's bit 30 holds a core in WFE on a release word read with the MMU off; CPU0 releases them
(clean to PoC, dsb, sev) after the final commit and the cluster writes, and each released core then sets
ACC_OVRD deep (bit 31).

| Run | Change | Result |
|---|---|---|
| 11 (job j1108-140158-cfb1) | secondaries held in WFE until after the commit, then all cores deep-WFI together | entry ~19:32:55 IST, next boot 19:35:55 (watchdog reset, ~3 min), no wake. 0x9f0a = 'h' (the release ran: last mark before deep WFI), 0x9f0b = 00 (m1n1 never reached on a wake), 0x9f0c = 0x9f (slpw, WKTP, slpa, SMC 0x201 acked, MCC flushed; PMP not idled in this run) |

So the core order is not what keeps the boot CPU from restarting. The lab reported the job as HUNG
only because the M1's Wi-Fi stayed stuck after the reset; the desktop was up at 19:36, and the PMU
bytes were read from its screen with the camera.
