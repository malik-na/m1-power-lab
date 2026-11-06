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
