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
