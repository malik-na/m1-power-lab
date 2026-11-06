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
