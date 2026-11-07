# macOS 27 under the m1n1 hypervisor on the M1 Air, and its first sleep trace (2026-11-06)

## Result

macOS 27.0.1 (26A434, Darwin 27.0.0, xnu-13432.1.9 RELEASE_ARM64_T8103) booted to the
desktop as a guest of m1n1 on the M1 Air (J313, t8103). The user logged in, and
"Apple menu > Sleep" ran with `hv_s2r_trace.py` armed (18 zones).

macOS went most of the way into sleep:
- `powerd` answered;
- tasks were suspended;
- NVMe, USB-C accessory power and the display were powered down.

The tracer logged 284,456 events (223,896 MMIO writes). The run stopped while the CPU cores
were powering down. CPU 1 took an SError (ESR 0xbe000000) at the `wfi` after
`cbz x30` / `retab` in its final idle path. Its last traced write was PMGR `0x23b738004 = 0`
(pc 0xfffffe003b2bad7c). Resuming re-raised the same SError, so wake was impossible.
The screen stayed off.

The raw files are local only (`var/mac27-trace-20261106/`, gitignored):
- `s2r-trace-20261106-172437.jsonl.zst`
- `run-try13.out`
- `vuart-all-runs.log.zst`

## How the guest got there (m1n1 branch `m1power/m1-sptm-native` in `~/m1n1`)

macOS 27 is the first macOS that uses SPTM/TXM on M1; macOS 13 used PPL. SPTM expects to
be entered at EL2 and uses EL2 registers (`TPIDR_EL2`) whenever it is not in guarded mode.

Upstream m1n1 (70757dc7) has two ways to run an SPTM guest, and neither works on M1:
- **nested mode:** needs FEAT_NV2;
- **SPRR/GXF emulation mode:** traps ERET with HFGITR_EL2, which needs FEAT_FGT. Neither
  feature exists on M1.

Run natively (unpatched), SPTM hits `msr tpidr_el2` at EL1, which is UNDEF. Its own vector then
spins in `mov x0,#0xdead; wfe` with DAIF masked. Confirmed by trapping WFE: guest ELR_EL1
pointed at `msr tpidr_el2, x8`.

| Commit | Change |
|---|---|
| 6ee155e4 | Virtual AMCC for M1's single CTRR region A. Skip the AMCC IRQ hook when T8103 has no error-handler metadata. |
| 9e6b6603 | On t8103, patch guest ERET to `hvc #0x1403` and emulate it. Skip HFGITR_EL2 without FEAT_FGT. Run 4K-granule TTBR0 (Rosetta) unshadowed instead of panicking the hypervisor. |
| b93d084e | Pass the guest's AMX enable (AMX_CONFIG_EL1/EL12 vregs) through to hardware. Without it, XNU panics after login with "thread already has AMX saved state". |

How the guest was run:
- **Command:** `run_guest.py --sptm-mode emulation -p sptm.t8103.release -t txm.macosx.release kernelcache`.
- **Boot args:** `debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0 -v`.
- **Boot path:** Macintosh HD's boot object is m1n1 70757dc (Permissive, set in 1TR). The
  patched build was chainloaded over USB.
- **Hangs:** a hardware watchdog armed before start (150 s) turns a hang into a reboot. It was
  disarmed from the hypervisor shell once macOS was up.

## Next

1. Find the SError at core power-down. Candidates:
   - the hypervisor emulating the PMGR CPU word `0x23b738004/8` from EL2;
   - the CPU's deep-sleep WFI while m1n1 still owns the core.

   aurora-silicon/aura `feat/sptm-hv` met the same stage on the A18 Pro: core power-down via
   `S3_5_C15_C6_2` bits 63 and 0, then WFI. See `docs/evidence/2026-11-06-aurora-silicon-survey.md`.
2. Narrow the armed zones. aura saw whole-block PMGR trapping slow the power-down past a 5 s
   AON watchdog.
3. Drop m1n1's USB link at the sleep commit. In aura's run, the PMU never powered the chip off
   while the hypervisor's USB device stayed up.
4. Decode the captured entry sequence:
   - PMGR `0x23b7003c8`, `0x23b700470`, `0x23b700258`, `0x23b70c000..28`, `0x23b74a000`;
   - AON `0x23d2dc100`;
   - SPMI `0x23d0d93xx`;
   - SMC keys;
   - PMP mailbox.

   Compare it with aura's 10-step T8140 sequence.

## Update, evening: the full sleep entry is captured (try23)

Tests 13 to 23 moved the guest from "faults at sleep" to a complete sleep entry. What each wall was:

| Wall | What it was | Fix |
|---|---|---|
| E-core SError at sleep (try13-15) | Apple's error handler names it a DPC (instruction-side) error, S3_5_C15_C0_5 = 0xcb00000000000000 (code 37, "multiple"). Idle E-cores exiting retention WFI, woken ~1000/s by m1n1's 1 ms EL2 tick (no ECV on M1). | Guest cores run with CYC_OVRD WFI_MODE 2 (clock-gate, never retain), m1n1 86d6ddf7. The E-cluster idle hold (a8d2885c) turned out to be unneeded (try21). |
| "Sleep transition timed out ... calling power state change callbacks" (try16-21) | Read from the guest's panic stackshot, dumped from /pram (0x9e6730000) through the hypervisor and decoded with xnu's kcdata.py: IOPMrootDomain's thread waited on a kernel mutex held since boot by a bluetoothd thread stuck in com.apple.driver.AppleBluetoothModule. The m1n1-docs boot-arg `apcie=0xfffffffe` set the Wi-Fi/Bluetooth PCIe port's debug flags to 0xfffffffe, which left the chip unusable (also no Wi-Fi in the guest). | Drop `apcie=0xfffffffe` from the guest boot-args. |

try23 (lid closed, auto sleep, tracer armed) then ran the whole entry in about 0.7 s after MBSE='slpw':
- device power-down: PMGR domains to 0 (spi, display, etc.), PMP DevPwr messages, DCP/DCPEXT RTKit SET_AP/IOP_POWER 0x201 acked;
- AON AP watchdog disabled (0x23d2b0000/+0x10 = 0); PMU boot_stage (0x9f01) <- 0x50 and scratchpad reads;
- PMP and SMC RTKit SET_AP_POWER/SET_IOP_POWER 0x201 acked; SMC MBSE = 'slpa';
- secondary cores' CPUSTART bits written; AON watchdog-extra registers cleared;
- clkgen muxes parked (0x23b040140..154 = 0x80100000); cluster controls 0x23b734000/77c000/778000/748x00 = 0; CPM power gating 0x23b71c080/088 = 0x80000000; cluster PS 0x23b718000/4 = 0; PS 0x1c0/0x1c8 (m1n1's own UART/USB domains, refused by m1n1 as "dangerous") and 0x1d0;
- **S2R-timer commit 0x23d2c4000 = 1** (the address the static analysis predicted);
- PMU RTC wake alarm over SPMI: read 0xd00c, write 0xd008 = 0x2a6f80, 0xd00e = 0, 0xd000 = 0x41, then the commit written twice more;
- every core: ACC_OVRD <- 0x1800101526076207 (deep sleep), CYC_OVRD <- 0x3000001, WFI. m1n1 skipped those writes and took each core back ("Guest is shutting down CPU"), so the SoC did not actually power down.

Raw files (local, gitignored): `var/mac27-trace-20261106/try23/` (JSONL trace, hv log, console, `sleep-entry-timeline.txt`), `try22/` (panic stackshot).

Next: let the hardware really sleep under the hypervisor (pass the final ACC_OVRD/CYC_OVRD through, drop m1n1's USB link at the commit, as aura did) and see whether the RTC alarm wakes it; and turn this sequence into the Linux suspend-to-RAM checklist.

## Update, late evening: first real hardware sleep attempts (try24-26)

m1n1 gained an experimental "real S2R pass-through" (local branch, commits b2c8453d, e4a5fdfe): the
guest's final ACC_OVRD and CYC_OVRD(DISABLE_WFI_RET) writes reach the hardware, each core stops
its EL2/guest timers, the last core shuts m1n1's USB gadget down, and the guest's CPU self-disable
bits are passed through.

| Try | What happened | Evidence |
|---|---|---|
| 24 | Never slept: macOS held sleep with `kPMDKNotReady` after a 6-min pause I caused. | console |
| 25 | Cores 1-3 powered off for real; m1n1 then panicked trying to rendezvous the off cores; the other cores stayed stuck in m1n1 and the SoC never powered down (needed a power-button hold). Fixed: powered-off cores leave the rendezvous. | hv log; PMU: boot_error_count 2, btn reset |
| 26 | Whole entry ran; all 8 cores went down with USB off; **about 4 s later the SoC was reset by the watchdog** (PMU fault_shadow `wdog,reset_in_1`, boot_error_stage 0x50, RTC far before the alarm, alarm_event 0). The PMU never cut power. | `runs/.../try26/postmortem-after-try26-*.txt`, trace in `var/mac27-trace-20261106/try26/` |

Also learned: with the lid closed, macOS sometimes never sleeps on its own after boot
(`kPMDKNotReady`, a DriverKit driver not reporting ready); Apple menu > Sleep works. The
`pmu_postmortem.py` Sera read was broken (raw ADT slave id) and is fixed (6966dcd).

Next: find what kept the SoC awake inside the ~5 s window after the commit (m1n1 residue such as
its watchdog core or idle loop, a refused PS write, or a missing step such as the PMU go-hib
setting), then retry. Analysis running.

### try27 and the diagnosis

try27 applied macOS's requested power states for m1n1's protected USB/UART/SIO domains at the
commit (m1n1 b4dc39c7): same result as try26, all 8 cores down at 22:30:38, m1n1 back on USB
at 22:30:45 after a watchdog reset (PMU `wdog,reset_in_1`, boot_error_stage 0x50).

What the trace comparison and Aura's history say:
- The entry sequence is complete and identical to try23; J313 arms no "reconfig" watchdog
  (no WD2 writes), so the ~4 s reset is not a macOS-armed timer.
- m1n1 has nothing left running: no HV watchdog core, no idle m1n1 cores (all 8 were guest
  cores), timers cleared per core, USB gadget shut down, the guest's PS values applied.
- Aura's stage after the same signature was the **wake path**: the SoC does go down, then a wake
  source (a pending SPMI/PMU or AIC wake bit, or a USB-AON wake) brings the boot core back at the
  locked RVBAR, where only the hypervisor's own reset entry can resume the guest; anything else
  hangs and the watchdog resets. We have no such entry: the locked RVBAR points at the unpatched
  m1n1 70757dc image that Macintosh HD boots, not at the chainloaded patched one.
- Not yet proven: whether the SoC actually powered off before the reset. Aura answered that with a
  breadcrumb byte poked into PMU scratch from the RVBAR entry.

Next (a real piece of work, Aura took ~15 commits): install the patched m1n1 as Macintosh HD's
boot object so the locked RVBAR lands in it; run the guest from that image without chainloading;
add an S2R wake entry (breadcrumb first, then restore the hypervisor state and re-enter SPTM's
resume under emulation); then chase the wake bounces (pending AIC/SPMI wake bits, USB AON wake).

### try28: the patched m1n1 installed as the boot object; the wake path was never taken

The trampoline build (m1n1 f5fecc0b, sha256 `08a8b8c8...`) was installed as Macintosh HD's boot
object (one more Recovery trip: `kmutil configure-boot -c .../s2r/m1n1-s2r-wake.bin`), so the
locked boot-CPU RVBAR (`0x210050000` = `0x1000080578c001`, bit 48 is a flag) points at the image
that runs the hypervisor. The guest ran from that image without chainloading; at arm time the
hypervisor wrote `'W'` + the handler address into PMU scratch `0x9f04..0x9f09`.

Lid-closed sleep at 23:44:00, USB gone at 23:44:18-21, m1n1 back on USB at 23:44:24. After that:
- PMU scratch `0x9f04..0x9f0d` = `57 40 29 5f 01 02 00 00 00 00`: the `'W'` note is **unconsumed**
  and the breadcrumb bytes are zero. `_cpu_reset_c` of the installed image never ran.
- m1n1 came up at a **new base** (`0x805f10000`, was `0x80578c000`): iBoot reloaded it. This was
  a full reset through the boot ROM, not a warm wake at the RVBAR.
- PMU fault log: bit 11 `wdog,reset_in_1` again; `boot_stage 0x30`, `boot_error_stage 0x50`;
  RTC far before the alarm (`0x2a9268` vs `0x2a94d5`), `alarm_event 0`.
- The AON block after the reboot: WD0/WD1/WD2 CTRL all 0 (WD1 alarm 120 s and WD2 alarm 90 s are
  iBoot leftovers), `0x23d2c4000` (S2R timer commit) still reads 1.

So the "bounce wake into an image without a handler" theory is wrong for the M1: the boot core
never came back at the reset vector. Something pulls the PMU's reset input within about a second
of the cores going down (`reset_in_1`), and the PMU performs a full reset.

Candidates: the SMC (it was told `slpw`/`slpa` and `SET_AP_POWER 0x201`; a Mac SMC may reset an AP
that does not reach the sleep state in time), an AON watchdog macOS leaves armed across the entry
(WD1 CTRL is not written in the captured sequence; WD0 is disabled at +0x0c = 0), or the SoC's own
sleep logic asserting reset_in because the PMU was not prepared for sleep.

### try29: spin test (m1n1 e4cb5e3c)

Diagnostic build: the last core does the whole tail (other cores powered off, USB off, deferred PS
words applied) and then **spins instead of sleeping**, writing `'S'`, a tenths-of-a-second counter
and the AON WDT CTRL nibbles into PMU scratch `0x9f0a..0x9f0d`, and reboots itself through WD1
after 25 s (`'R'`). An external timer shows up as a counter that stopped early; surviving the 25 s
means the sleep step itself causes the reset.

Result (23:55): same reset. Last traced write (RTC alarm) at 23:55:27.2, m1n1 back on USB at
23:55:39.2, a gap of 12.0 s; try28's gap was 11.7 s. A plain `p.reboot()` through WD1 measures
6.3 s from USB-gone to m1n1-back, so in both tries the SoC lived **about 5.5 s after the commit**,
whether the last core slept or spun. The scratch bytes came back all zero ('W' at 0x9f04 still
unconsumed), so either the spin loop was never reached, its SPMI writes failed, or iBoot clears
those bytes (tested next). At arm time macOS had no AON watchdog armed (WD0/WD1/WD2 CTRL = 0,
boot-arg `wdt=-1`), so the ~5 s timer is outside the AON WDT block: SMC, PMU, or the S2R engine.
The deferred PS list is harmless: 0x23d280088/098 are AOP_MCA1/3 (ADT), not the SPMI link.

The private watchdog analysis notes that Aura's A18 Pro resets also "came 5 s after the commit";
Aura later reached a real 0.109 W suspend. What they changed is the next thing to read.

### try30: stage markers — the last core hangs in m1n1's own USB teardown

A plain `p.reboot()` showed iBoot clears PMU scratch byte 0x9f0d at every boot but leaves
0x9f0a..0x9f0c alone, so the scratch layout became: 0x9f0a a stage letter, 0x9f0b/0x9f0c data
(m1n1 5b051e91). The last core writes 'L' when it enters the commit tail, 'U' after
`usb_iodev_shutdown()`, 'P' after the deferred PS words; the UART console is muted at 'L'
(`uart_putbyte()` spins forever on a gated UART).

Result (00:09): **'L' only.** The SPMI write worked, then `usb_iodev_shutdown()` never came back
(its dwc3 stop, DART unmap and frees), so the last core never reached its final WFI, the SoC never
slept, and the ~5 s external timer reset it — the same signature as try26-29. The spin test
(try29) never started for the same reason. So the "5 s reset" is a consequence of our own hang,
not a hardware mystery; which timer it is (SMC most likely) only matters if the real sleep still
fails once the core gets there.

Fix (m1n1 38266673): at the commit the gadget is only detached — iodevs unregistered,
`DCTL.RUN_STOP` cleared with one write — no DART, no heap; sub-stage byte at 0x9f0b. try31 runs it.

### try31: the hang is the first dwc3 register access

With the minimal detach (m1n1 38266673) the bytes read **'L' + sub-stage 1**: the last core got
to `usb_iodev_detach_all()` and never past its first MMIO write to the USB device controller
(`DEVTEN`). Same reset, same timing. Also checked: on J313 macOS writes no WD2/reconfig alarm
during the entry (only WD0/WD1 counters and the reconfig words to 0), so unlike Aura's phone the
~5 s reset is not the AON reconfig watchdog; its owner is still unknown but moot if the core
reaches its WFI.

Why the controller is unreachable: on t8103 the guest parks the clkgen muxes (0x23b040140..154)
*before* the commit, so by the time the last core runs, the dwc3 has no clock even though its
PMGR domains (ATC0_USB 0x23d280098, ATC0_USB_AON 0x23d280088, ATC0_COMMON 0x23b700420 — hooked
by m1n1 and held on; the guest asked for all three off) are still powered. Domain names were
checked against the ADT; the earlier "AOP_MCA1/3" label for 0x23d280088/098 was wrong.

try32 (m1n1 c7ee1e2f): no dwc3 access at all at the commit — drop the iodevs, apply the guest's
PS words (which power the three ATC0 domains off), WFI.

### try32: first real sleep — no reset, and the first entry at the reset vector after it

m1n1 c7ee1e2f (no dwc3 access at the commit). Commit at 00:20:11.9, "last core (8 of 8) going
down", and **no reset**: the M1 stayed down. The M3 Max never saw a USB disconnect (the controller
was gated without a detach). macOS's RTC alarm was ~15 min out (0x2a9d4f).

- Opening the lid (00:4x), a key, a short power-button press: no visible reaction.
- A ~10 s power-button hold restarted it. Post-mortem: fault bit 10 `btn_rst,btn_seq_reset`;
  `alarm_ctrl` 0x41 -> **0x01** (the alarm's enable bit self-cleared: the alarm fired; RTC was
  907 s past it); PMU scratch `0x9f04` = 0 (**note consumed**) and `0x9f0a` = **'Z'**.
- 'Z' is written only by `hv_s2r_wake_entry()`, which is called only from `_cpu_reset_c` on the
  boot CPU (startup.c:242), i.e. an entry at the locked RVBAR, never from a normal iBoot boot
  (`_start_c`). So the SoC came back from the S2R state into the installed trampoline; the most
  likely trigger is the 00:35 RTC alarm (enable bit cleared). The trampoline then jumped to the
  chainloaded image's handler, whose `m1n1_main()` most likely hung on clocks macOS had parked —
  hence no screen, no USB, and no reaction until the button reset.

Also: macOS reads the u32 at PMU scratch 0x9f08 during boot and sleep entry (5 reads in try32),
which overlapped the arm-time note. try33 (m1n1 6be234a0) writes the note only on the last core
after the PS words, reprograms the RTC alarm to now+60 s at the commit, and the handler records
the RTC second ('H' at 0x9f0c, second at 0x9f0b) and resets cleanly through WD1.

### try33: full round trip — real sleep, RTC-alarm wake, trampoline, handler in the surviving image

m1n1 6be234a0: the note is written by the last core after its PS words; the RTC alarm is
reprogrammed at the commit to now+60 s; the handler reached through the trampoline writes the RTC
second and 'H' and resets through WD1.

Commit 00:56:43 ("last core (8 of 8) going down"), host saw the USB device go at 00:57:20.7,
m1n1 back on USB at 00:57:27.0 (a 6.4 s WD1 boot, i.e. our own reset). PMU afterwards:
- `0x9f04` = 0 (note consumed), `0x9f0a` = **'Z'** (installed image's trampoline ran),
  `0x9f0c` = **'H'** (the chainloaded hypervisor image, still in DRAM, ran its handler),
  `0x9f0b` = 0x82 = the RTC second at the wake, **equal to the alarm's low byte** (0x2aa282);
  `alarm_ctrl` 0x41 -> 0x01 (alarm consumed); fault log `wdog,reset_in_1` = the handler's WD1 reset.

So on the M1 Air under m1n1: the SoC enters suspend-to-RAM, DRAM contents survive, the PMU RTC
alarm wakes it, the boot CPU comes up at the locked RVBAR in the installed image, the trampoline
hands over to the image that ran the hypervisor, and that image executes. The whole entry is the
captured macOS sequence plus three things m1n1 had to do: clear its per-core EL2 timers and vFIQ,
drop its USB iodevs without touching the dwc3 (clockless by then), and apply the guest's deferred
PS words for the domains it had protected.

Open: the wake came ~37 s after the commit, not 60 (the RTC read at the commit or the alarm
granularity; the handler overwrote the trampoline's AON wake-status bytes, so the wake source is
inferred from the cleared alarm enable); resuming the guest (restore the hypervisor state and
re-enter SPTM's resume path) is not started; sleep power not yet measured.

### try34-35: wake sources and a first power bracket

try34 (m1n1 f8d9c788, alarm now+3600 s): commit 01:04:28, back at 01:08:08 — the user had
opened the lid; 'Z'+'H', alarm still armed. **Lid open is a working wake source** through the
same path.

try35 (m1n1 0c8a821b: the handler keeps the trampoline's AON bytes and adds the RTC second and
nub-wake+0x1c in the note slot; alarm now+3600 s): commit 01:16:39, lid closed throughout, back at
**01:46:30 — 1791 s after the commit, 1788 s before the alarm**. An unknown source wakes the SoC
~30 min into the sleep; the AON words recorded (+0x1c, +0x20>>16, +0x24) were all zero, so they
are not the wake-reason registers (better pick needed).

Gauge (SMC B0RM via m1n1, cable in: DC-in 0.04 W, so the M3 Max does not feed the M1):
2847 mAh at 01:08:18, 2716 mAh at 01:46:40 — 131 mAh over 38 min, of which ~7 min were m1n1 idle
(2.2 W) and the guest boot/login phase. First rough bracket for the 30 min of sleep: 40-70 mAh,
i.e. **about 1-2 W** — far above a real suspend (not measured on this M1 under macOS; the only measured low-power state here is Linux s2idle at 0.440 W, so this is ~5x that and about m1n1 idle). try36 is the control cycle (same
phases, 2-min alarm) to subtract the boot/login cost properly.

### try36-37: control cycle, the gauge is not a clean coulomb counter

try36 (alarm now+120 s) never slept: macOS panicked at the entry, `RTBuddy(SMC): No response
received in 20s, SMC not started? (4)`. Cause: the gauge reader run from m1n1 (`fw/smc.py`
client) between cycles had left the SMC's RTKit session started; a WD1 reboot of the AP does not
reset the SMC. Fixed by ending the session (`smc.stop()`), as m1n1's own smccli does.

try37 (alarm now+120 s): commit 01:56:32, back 01:58:08 — the alarm (RTC second = alarm's,
`alarm_ctrl` 0x41 -> 0x01). The trampoline's AON byte `nub-wake+0x20 >> 16` = **0x40** for the
alarm wake; it was 0x00 for try35's ~30-min wake, so that word does carry the source (different
bit, not yet decoded).

Gauge readings (B0RM, mAh): 2847 @01:08:18, 2716 @01:46:40, 2726 @01:48:03 (+10 while
discharging at 178 mA), 2714 @01:58:18 (only -12 across two guest boots and a panic). B0RM is
the gauge's compensated "remaining capacity" and moves by +-10-15 mAh on its own, which is the
size of the signal for a 30-min sleep. So tonight's 1-2 W bracket is **not reliable**; a defensible
sleep-power number needs a sleep of hours (which needs the ~30-min wake source masked, or a
handler that goes straight back to sleep) and possibly a raw-charge key instead of B0RM.

### Correction (side-session review, verified): try35's sleep drew about 2.5 W

The tracer caught macOS's own gauge poll just before the try35 commit: `READ_KEY <B0RM>` =
0xb03 = **2819 mAh** at trace t=364.56 s (01:16:24; `s2r-trace-20261107-011020.jsonl`). After the
wake m1n1 read **2716 mAh** at 01:46:40. That is 103 mAh across an interval that contains nothing
but the sleep (1812 s by the PMU RTC: commit 0x2aa6f3, wake 0x2aae07): **~204 mA ≈ 2.5 W at
12.24 V** — the same rate as m1n1 idle (2.2 W), as the 01:08→01:16 boot phase (207 mA), and about 5x Linux s2idle on this M1 (0.440 W). Correcting for the gauge's +16 mAh load-compensation jump at display-off gives 173 mA ≈ 2.1 W, so 2.1–2.5 W. Even
with ±15 mAh of gauge noise that is 1.7–2.4 W. So with the cores off and the clocks parked the
SoC is **not** in a suspend-power state: the PMU never dropped the rails. (Review correction: Aura's HEAD code comment says only that a powered
ATC0 USB AON domain is an armed *wake source*; "the PMU never finishes the SoC off" is the
inference in Aura's commit 1820814 message, J700, not a measured mechanism. In try35 the M3 Max
kept the M1's gadget enumerated for the whole 30 min — the first USB loss was the WD1 reset at
the wake — so the gadget was never disconnected, only its domains were written off.)

Also from the review: the "last core (8 of 8) going down" line reaches the host ~20 s after the
real commit (RTC-based commit-to-wake is 1812 s in try35 and exactly 60 s in try33), so
commit-to-wake must be measured by the PMU RTC, not host timestamps. The try33 "37 s" oddity
was that latency, not the alarm.

### try38 (aborted: lid closed at boot) and the WD2 answer

try38 booted with the lid still closed, so macOS slept before the harness armed; the old
"Skip: msr ACC_OVRD" path ran and the hypervisor exited. Its last-cpu snapshot settles the
5-second question: at the commit **WD2 is armed — alarm 0x07270e00 (5.000 s @ 24 MHz), CTRL 4**
(`run-try38.out`), exactly Aura's "reconfig watchdog" on the J700. It only looked unarmed before
because every earlier read of that block was after a reboot or at arm time. try26-31 reset at
~5.5 s because the last core hung before the entry completed; try32-37 slept for minutes, so
after a completed entry WD2 is stopped or cleared by the hardware hand-off.

### try39: E-cluster idle hold off (m1n1 99b4ef37 / 21fc1d5a)

Review found a suspect that had been compiled in all night: `HV_HOLD_ECLUSTER_IDLE` (added for
the retention-WFI SError that WFI_MODE 2 later fixed) drops every E-cluster idle report the
guest writes to 0x23b738004, so PMP never sees both clusters idle — a plausible reason for a
completed S2R entry that still draws ~2 W (cluster rail and fabric left in idle, not off). try39
runs with the hold off (`M1N1_NO_ECL_HOLD=1`, default 0 in C), 25-min alarm, cable in, lid closed.
The handler now records at the wake: nub-wake+0x2c (AON wake sources 128-135: 131 ATC0 CIO,
133 ATC0 USB), the ACTUAL nibbles of ATC0_USB / ATC0_USB_AON / ATC0_COMMON, and WD2 CTRL. Mask
for the port's wake sources, if needed later: set32(0x23d004018, 0x28) (ATC0 CIO+USB; 1 = masked,
from AppleT8103PMGR::setAPWakeupSources, valid & ~enabled).

**try39 result (02:24:40 → 02:49:15, hold off):** the 25-min sleep ran to the alarm with no early
wake (RTC second 0xbd = alarm, `alarm_ctrl` 0x41→0x01, trampoline +0x20>>16 = 0x40, +0x2c = 0:
no USB/CIO wake bits). Readback at the wake: ATC0_USB actual 0, ATC0_USB_AON actual 0,
ATC0_COMMON actual 4, WD2 CTRL 0 (stopped by the hardware after a completed entry).

Gauge: macOS's last B0RM poll before the entry = **2632 mAh** (t=153.8 s, awake at −205 mA);
m1n1 read **2639 mAh** 10 s after the wake. −7 mAh over 1500 s — i.e. within the gauge's
±15 mAh noise, **at most ~20 mAh / 25 min ≈ 50 mA ≈ 0.6 W, consistent with much less**. try35
(hold on, same entry otherwise, line for line) drained 87–103 mAh in 30 min. So the E-cluster
idle hold was the ~2 W: with it, PMP never saw the E cluster idle and left its rail and the
fabric in idle inside a completed S2R; without it the SoC goes genuinely down.

A precise number needs a multi-hour sleep (the gauge resolves ~1 mAh; an hour at 0.3 W is
~25 mAh) or an inline USB-C meter with the battery parked at its 80 % charge limit (CHLS 0x5005).

### try40-42: sleeping from the login screen does not hold

try40/41/42 were launched with the lid closed so macOS sleeps by itself from the login screen
(the harness now arms 25 s after the kernel jump, no console dependency; `ARM_DELAY`).
- try40: slept before the arm (old Skip path) — nothing learned.
- try41 (hold off, light trace: SMC+SPMI zones only, `S2R_AON=0 S2R_PMGR=0 S2R_CLKGEN=0 S2R_DCP=0`,
  alarm 10800 s): commit 03:02:15, m1n1 back 03:02:26 — the **5-second WD2 reset** (fault
  `wdog,reset_in_1`, note unconsumed, stage 'P', new base). Our side completed; the SoC did not
  reach the state that stops WD2.
- try42 (hold off, try39's full trace, alarm 10800 s): commit 03:06:14, slept, then a **real wake
  ~40 s later** ('Z'+'H', WD2 CTRL 0, ATC0_USB/AON actual 0, COMMON 4) with the alarm still armed
  and no USB/CIO bits (+0x2c = 0, +0x20>>16 = 0): an unidentified wake source, like try35's.

try39 — same build, same trace, but asleep from a **logged-in desktop** — ran 25 min to the alarm.
So the login-screen sleep behaves differently (different wake policy or sleep type, not yet
identified); the long measurement goes back to the logged-in desktop. The handler's RTC byte is
not reliable at 1-s granularity (reads can return a value ~20 s stale), so commit-to-wake by RTC
needs the full counter read twice, not the low byte.

Side-session findings on the login-screen sleep (from the try39/try42 traces, for the next
build): (a) the loginwindow entry skips the DCP/DCPEXT SET_AP_POWER 0x20 (display-off) step
and goes straight to 0x201, and runs slpw→slpa in 0.56 s vs 12.6 s from a user session (so the
12 s was session quiesce, not trace overhead); (b) our wake record never reads nub-wake+0x28
(sources 96-127) — the trampoline takes +0x1c/+0x20/+0x24 and the handler +0x2c — so a wake in
96-127 is invisible by construction; read all five words first thing; (c) the PMU RTC appears to
latch 0xd002..0xd007 on a read starting at 0xd002, and our 4-byte read at 0xd004 returns the
latched copy (fresh in try39 where macOS never read 0xd002, stale in try42 where it read it 14
times): read 6 bytes from 0xd002 and take bytes 2..5. (d) WD2 is loaded by the AON engine at the
S2R-timer commit (count 0.10 s at the last-cpu snapshot), not by an AP write; a WD2 reset means
the engine's completion condition went unmet with all AP steps done (try41, light trace: entry
timing).

### try43: 30-minute sleep from the desktop — drain within noise; the ~30-min wake is a fixed timer

try43 (try39's recipe: logged-in desktop, full trace, hold off; alarm 10800 s): commit 03:13:06,
woke at **03:42:57 = 1791 s later — the same 1791 s as try35**, alarm still armed, 'Z'+'H', WD2
CTRL 0, ATC0_USB/AON actual 0, COMMON 4, and +0x1c/+0x20/+0x24/+0x2c all zero. So an exact
~29.85-min timer wakes the SoC regardless of the E-cluster hold, and its source is in wake
sources 96-127 (nub-wake+0x28), the one word we never read. The next build (m1n1 f3354310)
records +0x28 and reads the PMU RTC as 6 bytes from 0xd002.

Gauge: macOS's last poll before the entry **2556 mAh** (t=74 s, B0AC −218 mA awake); m1n1 read
**2554 mAh** 10 s after the wake. **2 mAh over 1791 s ≈ 4 mA ≈ 0.05 W** — with the gauge's ±15 mAh
that is 0.05 ± 0.36 W. Together with try39 (−7 mAh / 1500 s) the two independent sleeps give a
drain indistinguishable from zero at this resolution, with an upper bound of roughly 0.3–0.4 W —
at or below Linux s2idle on this M1 (0.440 W, the only other measured low-power state here).
A tighter number needs the 30-min timer masked first (then a multi-hour sleep).

Status at 03:45: the M1 Air does suspend-to-RAM under m1n1 with the captured macOS sequence
plus m1n1's three additions (per-core EL2 timer/vFIQ clear, iodev drop without touching the
clockless dwc3, deferred PS words for its protected domains) and **without** the E-cluster idle
hold; it wakes on the RTC alarm, the lid, or the 30-min timer, lands in the installed trampoline
and the surviving hypervisor image. Not done: resuming the guest, the 30-min wake source, the
login-screen entry, and the light-trace WD2 reset (entry timing).

**Wake-source table (read from the live ADT, `ap-wake-sources-j313.txt`):** the J313 names only
16 AP wake sources, none in 96-127 — so the 1791-s waker is one of the 16, and our record
simply missed it: the trampoline keeps `+0x20` bits 16-23 (NUB.APWatchdog 49, NUB.APWakeupTime
50, NUB.SPMI0Sw3IRQ 54 — the RTC-alarm wakes showed as 0x40 = bit 22 = **NUB.SPMI0Sw3IRQ**, the
PMU's interrupt) and `+0x24` bits 0-7 (AOP.SPMI0Sw3IRQ 64). Unrecorded until now: AOP.GPIO.IRQ4/6,
AOP.OutboxNotEmpty, AOP.CPUWakeupAP, NUB.WakeupAP, NUB.GPIO.IRQ6, SMC.CPUWakeupAP,
SMC.OutboxNotEmpty. The next build (m1n1 1aaf4e54) re-reads all five words in the handler and
stores a 16-bit map in ADT order. Masks: word i at 0x23d004008 + 4*i, 1 = masked.

### try44: 40-minute sleep from the login screen — no 30-min wake; the timer belongs to the logged-in session

try44 (2026-11-07, build fb4802c4, alarm 2400 s, hold off, full trace): the lid stayed closed from
boot, nobody logged in, so macOS slept from the login screen at 10:14. That sleep **held for the
whole 2400 s** and woke on our RTC alarm (PMU RTC: commit 0x2b2503, handler read 0x2b2e6c =
2409 s; `alarm_ctrl` 0x41→0x01, RTC−alarm = 9 s). Handler record: wake sources **set** =
NUB.SPMI0Sw3IRQ only (map 0x0100); **enabled** = all 16 (0xffff); ATC0_COMMON actual 4; WD2 CTRL 0;
trampoline +0x20>>16 = 0x40. So the **1791-s waker did not fire** from a login-screen sleep. try35
and try43, the two sleeps that woke at 1791 s, were both desktop (logged-in) sleeps: the timer is
armed by the user session, not by the sleep entry. With try43's recorded zeros (+0x1c, +0x20 bits
16-23, +0x24 bits 0-7, +0x2c) the candidates are NUB.WakeupAP (40), NUB.GPIO.IRQ6 (47),
SMC.CPUWakeupAP (76) and SMC.OutboxNotEmpty (81).

Two practical consequences: (1) the login-screen sleep is now a working recipe — lid closed from
boot, hold off, full trace, no user action — and it is the one to use for long measurements
(try36/38/40 from the login screen did not hold; the difference to today is unexplained — those
runs had the light trace or the E-cluster hold); (2) the multi-hour measurement no longer waits on
masking the timer.

Gauge: macOS's last B0RM poll before the entry **2480 mAh** (t=49 s, 32 s before slpw, lid
closed so no display-off jump); m1n1 read **2463 mAh** at 10:54:18, 10 s after the wake. 17 mAh
over 2409 s, of which ~2 mAh is the awake tail and m1n1's 10 s: **~15 mAh / 40 min ≈ 22 mA ≈
0.27 W, ± 0.27 W** (gauge ±15 mAh). Three sleeps now: −7 mAh/25 min, +2 mAh/30 min, +15 mAh/40 min
— all within the gauge's noise of zero, upper bound still ~0.3–0.4 W.

try45 (started 11:00): the same login-screen recipe with alarm 10800 s, for a ±0.07 W number.

### try45: the login-screen early wake has a name — SMC.OutboxNotEmpty at 41 s

try45 (same login-screen recipe as try44, alarm 10800 s): commit 10:58:19, USB down 10:59:00
= **41 s later**, handler record: wake sources set = **SMC.OutboxNotEmpty (81)** only (map 0x0800),
enabled = all 16, WD2 CTRL 0, trampoline +0x20>>16 = 0, alarm still armed (RTC−alarm −10748 s).
This is the "login-screen sleep wakes after ~40 s" seen in try36/38/40 — the SMC put a message
in its outbox to the AP and that is an enabled wake source. try44 (same recipe) held 2400 s, so
whatever the SMC wants to say is not deterministic. Note for the desktop timer: SMC.OutboxNotEmpty
is one of its four candidates too.

The post-wake m1n1 cannot read that message: by the time the WD1 reset has run and m1n1 is back,
iBoot has talked to the SMC and the outbox is empty (an unfiltered batt.py run showed a clean
RTKit start). Reading it means the wake handler draining the SMC mailbox before the reset.

Next: m1n1 330cba51 adds `hv_s2r_wake_mask_or[5]`, ORed into the mask words at the last core
(after macOS's own setAPWakeupSources); `real_s2r_on(mask=[81])`. try46 = login-screen recipe,
alarm 10800 s, SMC.OutboxNotEmpty masked.

### What arms the desktop 1791-s timer: nothing the tracer sees (trace diff, 2026-11-07 11:00)

Two independent diffs of try43 (desktop, woke at 1791 s) against try44 (login screen, held
2400 s) — the peer session's and an 11-agent workflow over the three JSONL traces, the run logs
and the serial console — found no arming act: the SMC WRITE_KEY set at sleep entry is identical
(MBSE, WKTP=02, NTAP, UB0C, gP0d, CHLS, the tG*/zE* telemetry; NTAP/UB0C/gP0d are written at SMC
bring-up in both runs), no SMC key or SRAM/MMIO write in 0x23d000000–0x23d3fffff carries a value
near 1791/1800 s in any unit, the SPMI command list at the commit (boot_stage 0x50, alarm,
irq_mask, alarm_ctrl 0x41) and the PMP/SMC SET_AP_POWER messages are the same, and the console
log for try35 shows only macOS's own MaintenanceWakeCalendarDate (+942 s, through the RTC alarm
we overwrite). Desktop-only differences: READ_KEY DICT, and slpw→slpa 9.8–12.5 s vs 0.8 s. What
the tracer cannot see: AOP traffic and the DCP side. So the timer is either the SMC's own
(SMC.CPUWakeupAP 76, or an SMC message = SMC.OutboxNotEmpty 81) or NUB-side (40/47), and one
desktop cycle with the current build names it directly from the status map. (NTAP = the SMC
notification enable, written at probe; with it on, source 81 was live in every sleep so far.)

m1n1 ecac044f: the wake handler drains the SMC outbox before the WD1 reset and records the first
message's endpoint, command byte and event code (msg0 >> 32) in the note; with no message pending
the note carries the enabled map instead (the proof that a requested mask reached the hardware).
Note layout now: 'H', status map lo/hi, count<<6 | ep, cmd (0xff = no message), 4 bytes event code
or enabled map. `crumb.py` decodes both layouts.

### try46: 3-hour sleep from the login screen, SMC.OutboxNotEmpty masked — held to the alarm

try46 (2026-11-07, build 330cba51, login-screen recipe, `real_s2r_on(alarm=10800, mask=[81])`):
commit 11:03:23 host (PMU RTC 0x2b308e), woke on the alarm at 14:03:23 — **10810 s by the RTC**
(alarm 0x2b5abe, handler read 0x2b5ac8). Handler record: set = NUB.SPMI0Sw3IRQ only; **enabled =
0xf7ff, i.e. bit 11 (SMC.OutboxNotEmpty) clear — the proxyclient's mask reached the hardware and
survived macOS's own setAPWakeupSources**; WD2 CTRL 0; ATC0_COMMON actual 4. The user opened the
lid at ~11:13 and the SoC did not wake (the lid path on this Mac goes through the SMC's message,
the masked source). The host-side guest process hit its 1-hour timeout at 12:02; the M1 was
unaffected (the harness now allows 4 h).

Gauge: macOS's last B0RM poll before the entry **2465 mAh** (t=17 s, 39 s before slpw, awake at
~−180 mA ≈ 2 mAh); m1n1 read **2450 mAh** at 14:03:33 and again 2450 at +30 s and +74 s.
**15 mAh over 10810 s, ~13 mAh after the awake tail ≈ 4.3 mA ≈ 0.05 W; gauge ±15 mAh → ±0.06 W.**

**Caveat on the source of that current.** Every earlier post-wake read showed the M1 on its
battery with the M3 Max link feeding nothing (B0AC −178 mA, PDTR 0.04 W; last confirmed 11:00:24).
At this wake the M1 reported B0AC 0 and **PDTR 2.33 W** (the M3 Max's port3 is now `[source]`,
`usb_power_delivery`, feeding m1n1's whole idle draw). The host journal has no record of when
port3 took the source role. So for an unknown part of these 3 hours the M1 may have been fed by
the M3 Max, and the battery drop is then a lower bound on the SoC's draw. The number above holds
if the role changed at the wake (the SMC renegotiates when the AP comes back); it is not proven.
For the next long run the M3 Max side must be pinned to sink (`/sys/class/typec/port3/power_role`)
or the cable unplugged after the commit, and the gauge read before the first USB enumeration.

Pooled, battery-only cycles (try39 −7 / 1500 s, try43 +2 / 1791 s, try44 +15 / 2409 s): 10 mAh over
5700 s ≈ 6 mA ≈ 0.08 W ± 0.11 W. With try46 taken at face value: 25 mAh over 16510 s ≈ 5.5 mA ≈
**0.07 W ± 0.04 W**. Either way the SoC's suspend-to-RAM draw on this M1 Air is well under Linux's
s2idle (0.440 W) and in the range Aura measured on the J700 (0.109 W, by its battery gauge).

(try46 addendum: the status map at the wake was 0x0100, so no SMC message was latched for source 81
during the sleep. A host power-role swap during the sleep would most likely have posted one, so this
favours the swap having happened at the wake — suggestive only, since whether a masked source still
latches its status bit is untested. The host journal has no typec/tps6598x line for port3 at all.)

### try47: first stage-one wake (hypervisor image kept alive, USB re-taken) — stalls in the gadget bring-up

Goal of stage one: at the wake, instead of the WD1 reset, the handler keeps the hypervisor image,
turns its MMU back on over the surviving page tables, restores the five clkgen mux words recorded at
arm time (0x23b040140..154: 0x85100000 ×3, 0x86100000 ×2; macOS parks them at 0x80100000), powers
the ATC0 USB path back up (`usb_phy_bringup(0)`), brings the dwc3 gadget back (`usb_iodev_init`) and
runs the proxy, so the host can talk to the live image (guest memory, SPTM state, Python hooks).
m1n1 93ec2724 + a 60-s WD1 fallback (1b60e585); `real_s2r_on(alarm=300, mask=[81], wake="proxy")`.

try47 (login-screen recipe): commit 15:18:02, woke on the alarm at 15:23:01 (the host saw the old
device disconnect then). **The PHY came up and the controller connected within 0.5 s** (host:
"new high-speed USB device" at 15:23:02.24), but it never answered: "device descriptor read/64,
error -110", then "not responding to setup address" through 15:23:20. The SoC reset ~20 s after the
wake (WD1's 60-s fallback had not expired; 20 s is `wdt_reboot()`'s alarm while `hv_s2r_down` is
set, i.e. some path called reboot — most likely an exception or assertion inside the gadget
bring-up, whose message went to a console with no output) and came back as a normal boot through
the installed image at 15:23:28. Note: stage 'D' (inside `usb_iodev_init`), sub 1 (PHY bring-up
returned OK); wake set = NUB.SPMI0Sw3IRQ; SMC outbox not drained (mode 1).

Also learned: in every cycle so far the host kept the M1's gadget enumerated through the whole sleep
and saw the disconnect only at the wake. m1n1 0a10540d adds a fault note (kind, ESR, image offset
of ELR into 0x9f05..09 / 0x9f0b..0c on the first exception, SError, assertion or reboot call while
the wake path runs) and sub-stage bytes inside the gadget bring-up; the harness now reads CNTPCT at
arm time and twice after the wake. try48 = the same cycle with that build.

### try48: the stall is a synchronous abort in dart_init — on USB port 1, which is off at the wake

try48 (m1n1 0a10540d, same cycle; commit 15:27:19, wake 15:32:18) left the new fault note: kind 1
(synchronous exception), **ESR 0x96000018** (data abort at the same EL, DFSC 0x18 = synchronous
external abort, read), ELR at image offset 0x16bb0 = `dart_init` dart.c:227, the first DART access
(`read32(regs + DART_T8020_CONFIG)`). So on t8103 a read of a gated block comes back as a catchable
synchronous abort (exc_sync → "Unhandled exception" → `wdt_reboot()`, whose 20-s alarm explains
try47's +20 s), not a hang. The peer session found which DART: `usb_iodev_init()` loops over every
port, and port 0 had come up (the host saw the high-speed device at +0.5 s in both runs); the abort
is port 1's `dart-usb1`, whose ATC1 domains are off at the wake (at boot, `usb_init()` powers every
port before `usb_iodev_init()`). The PMGR words macOS writes in its last 3 s besides the clkgen muxes
(0x23b71c080/88 = 0x80000000; 0x23b734000, 0x23b748000..c00, 0x23b778000, 0x23b77c000 = 0;
0x23d2dc100 = 0x100) all equal their fresh-boot values. CNTPCT at arm read 214.5 s, i.e. counting
from try47's WD reset: a watchdog reset restarts the system counter.

### try49: stage one works — the live hypervisor image is back on USB 0.6 s after the wake

m1n1 21fcf0ec: at the wake only port 0 is brought up (`usb_iodev_init_count = 1`), and guarded
probes of `dart-usb0` +0x60 and `usb-drd0` +0xc120 run with the clkgen muxes still parked (after
`usb_phy_bringup(0)`) and again after the restore. Login-screen recipe, mask=[81], alarm 300 s.
macOS sat at the login screen for 14 min without sleeping (lid closed from boot); one lid
open/close and it slept at once (commit 15:51:23) — the login-screen recipe can miss its clamshell
trigger at boot.

**Wake 15:56:22.7 (old device disconnects); 15:56:23.3 the host enumerates `m1n1 uartproxy
v2.0.0-125-gf33` — the chainloaded hypervisor build that went to sleep, not the installed image
(-105-gf4c) a reset would boot.** Stage letter 'Q' (proxy running), sub 0x50 (gadget bring-up
complete), probe byte 0 (dart-usb0 and dwc3 read cleanly both with the muxes parked and after the
restore), PMU 0x9f01 = 0x50 (macOS's boot_stage, untouched — no iBoot ran), set = NUB.SPMI0Sw3IRQ,
enabled 0x..ff with bit 11 masked. Through the live proxy: clkgen 0x85100000 ×3, 0x87100000 ×2;
ATC0_USB/AON 0x3ff, ATC0_COMMON 0x23ff, UART0 0x3ff; WD1/WD2 CTRL 0.

**The system counter runs through the suspend.** CNTPCT at arm 303.391 s (host time 1794046063.128),
at the wake 1427.285 s: 1123.894 s of counter against 1123.863 s of host time across the arm, the
14-min wait, the 5-min sleep and the wake — equal within 31 ms. So the 24 MHz timebase keeps
counting while the SoC is off in S2R (it restarts only on a watchdog reset), which is what xnu's
`cpu_timebase_init` assumes and what a Linux S2R implementation can rely on.

What stage one does not do yet: the host-side Python session dies with the USB link
(`SerialException` in run_guest.py), so the hooks, the PMGR shadow and the tracer state are lost;
the guest is not re-entered. Stage two: keep the host session across the link drop, bring the
seven secondaries back into m1n1's spin loop, re-arm EL2 on cpu0 without re-seeding the SPTM's
per-CPU SPRR/GXF state, and enter the guest at the SPTM reset page (entry & ~0xfff).

### try50–52: stage two — macOS re-entered after a real S2R, runs its restore, then panics

Stage two (m1n1 ffb206f7 → bd6a43d4): the host session survives the USB drop (run_guest catches
the SerialException only when `real_s2r_on(wake="resume")` expected it, reopens 1209:316d, `nop()`
first, resumes only if a 64-bit nonce written at arm time is still in the image), then calls
`hv_s2r_resume_guest(pc, flags)`: hv/S2R/exception bookkeeping reset, every core's SPTM-emulation
state re-seeded with the boot-time seed plus the boot CPU's CTRR/CTXR values, the secondaries'
alive flags forgotten, EL2 re-armed on cpu0 like a secondary, entry at the SPTM reset page (the
address every secondary got). Secondaries are started lazily, when the guest's CPUSTART comes.

- **try50** never slept: the chainload silently did not take (the M3 Max's xHCI re-enumerated at
  that moment) and the old installed image ran; calling our ELF's addresses into it crashed. The
  launcher now checks the running version against the uploaded build and retries.
- **try51**: reconnect, nonce check and the resume call worked; starting the secondaries at the
  wake raised an SError on core 4 (L2C_ERR_ADR 0x211050000 = its impl register): **the P cluster
  is unpowered at the wake** until macOS's restoreHW powers it. A review also found that
  restarting the secondaries overwrote their RVBARs with m1n1's vectors, which the CPUSTART hook
  reads back on M1. Both fixed (lazy start, recorded reset page).
- **try52** (bd6a43d4; slept 16:34:21 after a lid cycle, alarm wake 16:39:21): host back at
  16:39:22, nonce matched, **cpu0 re-entered macOS at 0x81f030000**. macOS then ran its own wake
  restore on cpu0: HID/EHID/ACC sysregs, **`enableCPUComplex` (0x23b718000/004 = 0xf, both
  clusters on)**, 0x23b71c000/040 = 0x80000000, the AON PMGR, PMGR PS read/writes for UART0/SIO/
  ATC0 (served by the Python hooks), 0x23b71c080/88, **PMU boot_stage 0x40**, the AON watchdog
  disarm (WD1 CTRL 0, 8008 = 0) — then **SMC MBSE = 'panb' (panic begin)**, NESN, boot_stage
  0x46. cpu0 now sits in xnu's halt loop (`wfe` at _start+0xc). The panic text was not captured:
  the macOS serial console (second CDC channel) was not being logged, and a memory scan found no
  runtime panic string. Next cycle: log the console channel across the drop.

So the S2R round trip now goes sleep → hardware wake → live hypervisor on USB → macOS's own wake
code running and restoring hardware; what is left is whatever its restore trips over.
