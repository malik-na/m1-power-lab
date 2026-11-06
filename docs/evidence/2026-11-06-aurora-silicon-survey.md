# aurora-silicon survey (2026-11-06)

Five-agent survey of every aurora-silicon repository: final synthesis first, then the per-area reports. Repository content was read as data; nothing from it was run.

## Synthesis

**aurora-silicon org survey: what the M1 power lab can use (verified 2026-11-06)**

Nothing in the org runs macOS 27 on an M1 under a hypervisor. Nothing in it does suspend-to-RAM on M1 either. What it does have:
- a way to reboot the M1 from the M3 Max over the USB-C cable, with no button presses;
- a macOS sleep trace from another Apple chip (the A18 Pro in the MacBook Neo), which shows two ways our trace kit will probably get the M1 reset;
- a few kernel patches worth 0 to about 175 mW each.

I checked the main claims of the four surveys against the clones, `/home/naeem/m1n1` and this host. Two survey claims were wrong:
- This host's USB-C power controllers are not on i2c. `0-0038..003a` are speaker amps (tas2764). All four controllers are SN201202x on SPMI.
- aura's PMU reset-reason reader adds little. Our `tools/hv-trace-kit/pmu_postmortem.py` already reads the same registers (`leg_scrpad`, `fault_log`, `fault_shadow`).

I ran no code from these repos.

## 1. What we can use, ranked by expected value

**1. tuxvdmtool: reboot the M1 from the host (unblocks every hypervisor run)**
- **Where:** aurora-silicon/tuxvdmtool `main` 187d73a. The other branches are merged into it.
- **What it does:** sends Apple's USB-C vendor commands to the M1's power controller: `reboot`, `reboot serial`, `dfu`, `debugusb`. These reach the controller, not the CPU, so they should still work when m1n1 hangs. That last part is my inference, not tested.
- **The catch on this host:** with SPMI controllers it needs `/sys/kernel/debug/usb/tipd/<dev>/command`. That file only exists with `CONFIG_TYPEC_TPS6598X_DEBUG_COMMANDS`, which is off here (checked in `/proc/config.gz`).
- **How we'd use it:**
  1. Rebuild only `tps6598x_core.ko` from aurora-silicon/linux 2661d71e (the commit our kernel is built from) with the option on. Kernel headers are installed and module signing is not enforced.
  2. Reload `tps6598x_core` and `sn201202x`. The host's USB-C ports drop out for a moment.
  3. Plug the cable into the M1's rear (DFU) port. Host port labels are `USB-C Left Back`, `USB-C Left Front` and `USB-C Right`. They are in `/sys/bus/spmi/devices/*/of_node/connector/label`; the i2c grep in the README finds nothing on this host.
  4. Test with `sudo tuxvdmtool --connector "Left Back" nop`, then `reboot`. The M1 comes back into m1n1 70757dc in proxy mode.
  5. `reboot serial` gives a UART on `/dev/ttySAC0`, which exists here. For that the cable must carry the SBU lines.
- **Effort:** half a day. **Confidence:** high that reboot works, medium for serial.

**2. aura's macOS sleep trace: two fixes for our trace kit before the first run**
- **Where:** aurora-silicon/aura `feat/sptm-hv` (PR #70, head eae9afc).
  - Docs: `docs/j700-s2r-measured.md`, `docs/j700-s2r-linux-sequence.md` (0.109 W asleep, measured), `docs/j700-s2r-entry-trace-20261105.txt`.
  - Code: `src/sptm_virt_s2r.c`.
  - Commit 1820814 (the debug USB link).
- **What it shows:**
  - (a) Trapping whole PMGR blocks slowed the power-down past macOS's 5-second AON watchdog, which then reset the machine. Our `hv_s2r_trace.py` arms whole zones, including AON PMGR `0x23d280000+0x74000` and `0x23d200000+0x80000`. That is the same setup.
  - (b) While the hypervisor's own USB device stays connected, the PMU never finishes powering the chip off, and the watchdog resets. Their fix shuts their USB gadget down at the sleep commit (1820814). m1n1's USB proxy is in the same position.
  - (c) They never trap WFI, print nothing after the commit, and log to a buffer in RAM.
- **How we'd use it:**
  - Narrow the zones to the commit page plus a few small pages.
  - Add an option that drops m1n1's USB link at the commit; reconnect after wake with `tuxvdmtool`.
  - Use their 10-step entry sequence (PMGR CPU word, AON watchdog arm, cluster words, CLLT, S2R timer, AIC mask, PMU RTC alarm, `pmu go hib`, `S3_5_C15_C6_2` bits 63 and 0, WFI) as the checklist for our Linux S2R path. Their T8140 addresses line up with our M1 addresses `0x23d2c4000` and `0x23d004008..`.
- **Effort:** 1 to 2 days. **Confidence:** high that the method carries over to M1, medium that M1 has the same 5-second watchdog. The prize is going from 0.44 W toward about 0.1 W.

**3. Wi-Fi: make the ASPM L1.1/L1.2 saving stable (171 to 175 mW)**
- **Where:** aurora-silicon/linux `integration/aurora` 43d03538d38 ("quiesce TX and defer country updates across suspend"), which includes 229031640b7.
- **What it does:** stops and drains Wi-Fi transmit before the D3 handshake, and restarts it only after interrupts and HOSTREADY are back.
- **How we'd use it:** it is a different race on the same D3 path as our `fix/brcmfmac-d3-recovery-v2`. It needs a hand merge in `pcie.c`; drop `tools/asahi/run-host-tests.py`. Then rerun the 15-cycle suspend stress with `powersupersave` on.
- **Backup:** omarchy-mac-pkgs `main`, `omarchy-mac/bin/omarchy-wifi-resume-fix` (plus its service). After resume it spots the `ASSOC-REJECT status_code=16` wedge and reloads `brcmfmac`. It only heals after resume; it does not fix the failure at suspend entry.
- **Effort:** half a day. **Confidence:** medium.

**4. ANE power: check it is not held on (107 to 173 mW)**
- **Where:** omarchy-ane `main`, `ane/src/ane_drv.c:81` (`autosuspend_ms=1500`), and CHANGELOG.md around lines 705-711. Those are the repo's own M1 (T8103) measurements.
- **How we'd use it:** on the M1, check `lsmod | grep ane` and `power/control`. If it reads `on`, set `auto` or blacklist the module.
- **Effort:** minutes. **Confidence:** high for the numbers, unknown whether ours is held on.

**5. Put empty USB-C ports' power controllers to sleep, as macOS does**
- **Where:** aurora-silicon/linux open PR #425, commit 840c4ba04ca, `drivers/usb/typec/tipd/core.c`. Not merged.
- **How we'd use it:** the survey says it cherry-picks cleanly onto our kernel base b798f2b; I did not re-run that check. Build it, run the idle and sleep A/B, then replug-test both ports including DisplayPort.
- **Effort:** small. **Confidence:** high it is safe; the M1 saving is unknown (the 190 mW to 1 mW figure is for a different chip).

**6. macOS 27 under the hypervisor:** our own patch idea, see section 2. Medium confidence it removes the FEAT_FGT blocker, low that macOS then boots.

**7. Remote boot switching without touching the M1**
- **aurora-bless** (`master` 903a630): `asahi-nvram` and `asahi-bless` read and write NVRAM from Linux. `asahi-bless --set-boot-macos --next -y` followed by `reboot` boots macOS once.
- **recovery-ssh** (`j813`, 44f4453 adds Linux controllers): a shell into macOS Recovery from the M3, for `bputil`, `kmutil configure-boot` and `csrutil`. Its `ptywrap` helper has to be built on macOS.
- **Effort:** 30 minutes and 2 to 3 hours. **Confidence:** medium-high and medium.

**8. Idle power for the second USB-C port (`atc1_*`)**
- **Where:** `integration/aurora` c8372a0ec63, 1c79b032094 and cf4eb7c2e35 (runtime PM for the dwc3 controller and the ATC PHY on newer chips).
- **How we'd use it:** port to t8103 by adding `apple,t8103-dwc3` to `idle_rpm`, adding PHY runtime PM that respects DisplayPort, and fixing the DT power-domain placement.
- **Effort:** medium-large. **Confidence:** about 30 to 60 mW, low to medium.

**9. Correctness fixes**
- 8c2ba08c751: 10 ms PMGR power-on wait instead of 100 µs. A 3-line hand port. Likely cause of our "fpwm1 failed to reach 0xf" message.
- 7f12ac1acdd: NVMe late completion; it delayed suspend entry by 19 s on M4 Pro.
- 3543be41e12: drm/apple, no VT switch on suspend.
- df65571d77c: CD321x refreshes power status on resume.
- 0c633c982c3: ATC skips stopped PIPE locks on M1/M2.
- No watts from any of these. Small effort each.

**10. Hibernation, for near-zero standby**
- **Where:** aurora-silicon/linux PR #906 plus aura PR #66, working on M4 Pro.
- **What it needs:** CPU off/on through PSCI and restore code for each coprocessor. The M1 parts (DCP, GPU, NVMe, Wi-Fi) would be new.
- **Effort:** weeks. **Confidence:** medium.

**11. Small items**
- aurora-diag `main` cd861d7: snapshot and diff of power state as a regression guard.
- Omarchy `quattro` ships `wifi.powersave = 2` in `etc/NetworkManager/conf.d/omarchy-wifi-powersave.conf`. Make sure our power-save-on file sorts after it.
- USB autosuspend is off by default (`etc/modprobe.d/omarchy-usb-autosuspend.conf`, `autosuspend=-1`).

## 2. Can anything here run macOS 27 on M1 under a hypervisor?

No.
- aura's SPTM virtualization only runs when `chip_id == T8140` (`src/sptm_virt.c:210`), and it needs nested virtualization (FEAT_NV2), which M1 lacks.
- The SPRR/GXF emulation in the org's m1n1 forks is an older copy of upstream m1n1's.

Confirmed in m1n1 at 70757dc7: emulation mode needs FGT only for the ERET trap, in exactly two places, `src/hv/hv_sprr.c:872` and `:905`. An ERET handler already exists (`hv_exc.c:555`, `hv_sprr_handle_eret`), and `proxyclient/m1n1/hv/sprr.py` already rewrites instructions into HVC calls. So our own attempt would be:
1. Skip both `HFGITR_EL2` writes when the CPU has no FEAT_FGT. On M1 that `msr` is probably UNDEF.
2. In `patch_text_sprr_emu`, also rewrite `ERET` (0xd69f03e0) as HVC with a new number, in the SPTM, TXM and kernelcache code segments.
3. In the HVC handler, set the exception code to ERET with ISS 0, back the return address up to the patched instruction, and call `hv_sprr_handle_eret`.
4. Count ERETAA/ERETAB (0xd69f0bff, 0xd69f0fff) first. Those would need emulating with pointer authentication.
5. Use aura's boot arguments: `-noprogress disable-uart-irq=1 -vm_compressor_wk_sw CAEnableMedina=0 wdt=-1` (`run_guest_sptm.py:45-54`).
6. Check our SPTM memory layout against aura's rules (`docs/sptm-nv2-virt.md`): boot_args revision 2, 0x480 bytes plus 8 zero bytes; TXM not exactly at physBase, or SPTM panics with `PHYS_SLIDE`.

Effort is 2 to 4 days.

For the silent hang in native mode, aura's §3.1 explains it: a GL-only register accessed at real EL1 is UNDEF, the exception goes to the guest's own vector, and SPTM spins without the hypervisor seeing anything. To find the faulting instruction, stop the guest and read `ELR/ESR_EL12` and `ELR/ESR/SPSR/ASPSR_GL12`.

macOS 13.5 (from before SPTM, already in our RUNBOOK) is still the more likely route to a trace.

## 3. Doing without button presses

- **Hard reset or reboot into m1n1, even from a hang:** tuxvdmtool `reboot` or `reboot serial`, once `tps6598x_core.ko` is rebuilt (item 1).
- **Switch the next boot between Linux and macOS:** `asahi-bless --set-boot-macos --next` on the M1. I did not check that it is installed there.
- **Recovery work (bputil, kmutil, csrutil):** recovery-ssh. Getting into Recovery (1TR) still needs the power-button hold, unless an NVRAM boot-into-Recovery trick works; that idea is mine and untested.
- **Read NVRAM first** (`asahi-nvram read`), and only write it with a DFU restore path ready; the aurora-bless README warns a write may force one.

## 4. Not useful
- **aura:** NV2, PSCI, CTXR and Mach-O boot work, and the other boards' branches.
- **m1n1 forks:**
  - aurora-silicon/m1n1 and omacom/m1n1 `j873` (Windows guest on M5).
  - The display, GPU and other device handoff branches for M2 to M4.
  - The small hypervisor fixes (`hv_join_cpus`, 7bcb53b): low value.
- **aurora-silicon/linux:** `aurora/bits/*` (already in our kernel), cpuidle and PMP code for other chips, the fabric p-state code (no t8103 node), the mailbox hold (7c5a1efc5f0, likely nil on M1), ANE/AVD/ISP/GPU branches.
- **Mac-side and boot tools:** macvdmtool (macOS only), aurora-installer, u-boot, mu and the other Mu and Windows repos.
- **Packaging and images:** alarm-aurora (config reference only), aurora-platform, aurora-distributions, aurora-neo-platform-config, aurora-sep-userspace, upower, kbd-light, speakerguardd, .github.
- **Userspace and apps:** mesa, avd-fw, camera-denoise, capture-ns, asahi-audio, alsa-ucm-conf-asahi, splash, gpubench, xserver, omarchy-mac, omarchy-mac-installer, omarchy-pkgs, fedora-aurora, nixos-aurora, fatfs, aurorairc, the website, aurora-steam-native.

Clones and notes are in `/tmp/claude-1000/-home-naeem--config-Claude-scratch-workspaces-1f07808c-2360-478e-a95f-ba9bd83341fb-6e170f00-d2a2-46d6-a9e8-f35600666f81-scratch-2026-11-05-4bcc96/f10f5b89-ddc4-474d-be69-a9a9989967a2/scratchpad/aura/` and `/tmp/claude-1000/-home-naeem--config-Claude-scratch-workspaces-1f07808c-2360-478e-a95f-ba9bd83341fb-6e170f00-d2a2-46d6-a9e8-f35600666f81-scratch-2026-11-05-4bcc96/f10f5b89-ddc4-474d-be69-a9a9989967a2/scratchpad/aura2/`.

## Per-area reports

### bootloaders
**aurora-silicon repos: what we can use for M1 sleep and the macOS 27 hypervisor trace**

None of the three repos (aurora-silicon/aura, aurora-silicon/m1n1, omacom/m1n1) lets an M1 run macOS 27 with SPTM/TXM as a guest. What they do give us: the clearest way past the missing FEAT_FGT (patch ERET instead of trapping it), a measured macOS suspend-to-RAM sequence from another Apple chip, and some PMU tools for figuring out why a sleep attempt reset the machine. I read code and docs only and ran nothing. Every branch was checked, plus open PRs, issues and docs/.

## A. Running macOS 27 under the hypervisor on M1

**A1. aura's SPTM virtualization does not work on M1** (high confidence)
- **Where:** aurora-silicon/aura, branch `feat/sptm-hv` (PR #70, 79 commits, 2026-11-02 to 11-05, head eae9afc). Files: `src/sptm_virt.c` (3739 lines), `src/sptm_virt_s2r.c`, `docs/sptm-nv2-virt.md`, `proxyclient/tools/run_guest_sptm.py`, `proxyclient/aura/sptm_virt_plan.py`.
- **What it does:** runs the real SPTM, TXM, secure kernel and exclaves on the A18 Pro (T8140, J700). They run as a FEAT_NV2 guest at virtual EL2, aura runs at GL2, and macOS 26.6.2 boots to the login window on all 6 cores.
- **Why not M1:** it only runs when `chip_id == T8140` (`src/sptm_virt.c:210`). It also requires FEAT_NV2 (`ID_AA64MMFR2.NV >= 2`, `src/nv2.c:258-272`), which M1 lacks.
- **Effort to port:** not feasible.

**A2. The SPRR/GXF emulation in all three repos is an older copy of upstream m1n1's** (high confidence)
- **Where:** aura `main` and `feat/sptm-hv` (`src/hv/hv_sprr.c`, `proxyclient/aura/hv/sprr.py`); aurora-silicon/m1n1 `main` and `aurora-wip`; omacom/m1n1 `integration/aurora`.
- **What it is:** Sven Peter's MIT version from b9c200eb, b2962b59 and 3dac58d5 (2026-07-28). The binary patcher turns GENTER/GEXIT and the GL/SPRR register accesses into HVC. The hypervisor then swaps the EL1 and guarded register sets (vector base, SPSR, ELR, ESR, FAR, AFSR1, SP_EL1) on each GENTER/GEXIT, with no FGT anywhere.
- **Why it isn't enough for SPTM:** it predates upstream 10e3be6d, 740bd84b and cfa7af64. The cfa7af64 message explains why the swap model breaks SPTM: ASPSR.GUARDED must be clear on EL-to-GL GENTER and set on exceptions taken into GL2. SPTM also checks the EL1 exception registers before returning to XNU.
- **Bearing on M1:** upstream 42934570 says "Running SPRR/GXF on M1 was useful for bringup", so this emulation path was brought up on M1 before.
- **Use:** none directly; it is already in `/home/naeem/m1n1` history.

**A3. Proposed fix: patch ERET instead of trapping it with FGT** (my own proposal, built from upstream code rather than taken from any of these repos)
- **The only FGT dependency:** at 70757dc7, emulation mode touches HFGITR_EL2 in exactly two places, `src/hv/hv_sprr.c:872` (activate) and `:905` (deactivate). Exception entry already reaches EL2 without FGT through the injected vector page (740bd84b). MTE handling is already conditional (`hv.c:166-170`).
- **What we would change:**
  - In `proxyclient/m1n1/hv/sprr.py`, also rewrite `ERET` (0xd69f03e0) in the SPTM, TXM and kernelcache `__TEXT_EXEC` segments to an HVC with a new immediate.
  - In the HVC dispatch, call `hv_sprr_handle_eret()` (upstream line 1420) with an ESR whose ISS is 0.
  - Skip both HFGITR_EL2 writes when FEAT_FGT is absent; that `msr` is likely UNDEF at EL2 on M1.
  - Count ERETAA/ERETAB (0xd69f0bff / 0xd69f0fff) first. `handle_eret` rejects ISS != 0, so they would need emulating (PAC on ELR).
  - Check whether the auxiliary kernelcache (or any other code loaded outside the patcher) contains an ERET.
  - Expect a cost: every exception return traps, on top of the entries that already trap.
- **Effort:** 2–4 days.
- **Confidence:** medium that this removes the FGT blocker; low to medium that macOS 27 then boots fully on M1.

**A4. Hardware lessons that may explain the silent native-mode hang** (medium confidence; from `docs/sptm-nv2-virt.md` §3.1 and `src/sptm_virt.c` ~757-776, 1440-1450, 2260-2275, 2845-2855)
- **Silent spin:** a GL-only register accessed at real EL1 is UNDEF. The exception goes to the guest's own vector, so the hypervisor sees nothing and SPTM spins (they saw `x0=0xdead`). HACR trap bits cannot catch an access that is already UNDEF.
  - That matches "hangs silently right after SPTM's HID writes".
  - **Use:** when it hangs, stop the guest and read `ELR/ESR_EL12` plus `ELR/ESR/SPSR/ASPSR_GL12` (s3_6_c15_c9_x, already in our `cpu_regs.h:731-736`) to get the faulting PC.
  - Their spin detector and single-step tracer are a ready model for this. Effort: hours.
- **Write-once lock bits:** under a hypervisor, SPTM's own writes to GXF_CONFIG (lock bit 5), VMSA_LOCK and APCTL land on the same EL1/GL1 copies that later code depends on. After that, `msr VBAR_GL1` and `msr TTBR1` UNDEF. **Use:** watch for this once XNU starts.
- **CTRR/CTXR:** return the real bounds on read (a zero shadow made SPTM reset) and swallow writes. Our 6ee155e4 virtualizes the AMCC CTRR; the CTRR system registers need the same treatment.

**A5. The iBoot-to-SPTM handoff contract, measured on T8140's SPTM** (medium confidence; `proxyclient/aura/sptm_virt_plan.py` header, `docs/sptm-nv2-virt.md` §1.4 and §2.1)
- x0 points to an XNU-style boot_args: revision 2 / version 2, 0x480 bytes, and the 8 bytes at [0x480] must be readable and zero.
- SPTM is entered with the MMU off and a clean EL1&0 regime.
- SPTM maps its window from the next 32 MiB boundary above physBase. TXM placed exactly at physBase panics with `PHYS_SLIDE`.
- The pieces sit in a fixed blob order and are listed as `/chosen/memory-map` properties (TXM-*, TrustCache, BootKC-*, DeviceTree, SPTM-*).
- The entry point is `sptm_pa + (LC_UNIXTHREAD pc - lowest vmaddr)`.
- **Use:** check m1n1's `run_guest --sptm` layout against these rules. Effort: hours.

**A6. XNU boot-args for an SPTM guest** (medium confidence; `run_guest_sptm.py:45-54`)
- `-noprogress` stops an endless loop when the boot_args video block is zero.
- Also: `wdt=-1`, `-vm_compressor_wk_sw`, `CAEnableMedina=0`, `disable-uart-irq=1`.
- Upstream already adds `sprr_tpro=0` and similar. **Use:** add the missing ones. Effort: minutes.

**A7. Recovering from a failed hypervisor session** (low value)
- aurora-silicon/m1n1 and omacom/m1n1 commits 7bcb53b, 8b6cba9 and 7faeb0a add `hv_join_cpus` to `src/hv/hv.c`, so a session whose secondary CPUs failed can be cleaned up without a reboot.

## B. Power and suspend-to-RAM

**B1. macOS suspend-to-RAM traced on T8140 under a hypervisor** (high confidence the structure carries over to M1; addresses and values must come from M1)
- **Where:** aura `feat/sptm-hv`, docs `j700-s2r-measured.md`, `j700-s2r-linux-sequence.md`, `j700-s2r-entry-trace-20261105.txt` (the 46 final writes with guest PCs) and `j700-sptm-virt-s2r-plan.md`; code `src/sptm_virt_s2r.c`.
- **Result:** macOS 26.6.2 slept at 0.109 W on battery, woke on the RTC alarm and answered ssh (6cac53d).
- **Entry sequence, in order:**
  1. Each secondary core sets its bit in the PMGR misc CPU word.
  2. The AON reconfig watchdog is armed for 5 s with reset enabled.
  3. The cluster control words are written to 0.
  4. SIO_CPU auto-enable is cleared and the clock muxes are parked.
  5. CLLT config is written.
  6. The S2R timer is started (the commit).
  7. AIC mask-all.
  8. The PMU RTC alarm is set over SPMI.
  9. `pmu go hib`.
  10. Each core sets bit 63 and bit 0 of `S3_5_C15_C6_2`, then executes `wfi`.
- **Wake:** the boot core comes back at the locked RVBAR.
- **Handshakes seen:** the PMP acks IDLE 0x201, the SMC receives `MBSE`, and the secondary PMIC gets SPMI SLEEP.
- **Use:** template for `tools/hv-trace-kit` and the Linux S2R path. The T8140 addresses 0x3082d4000 and 0x308004008.. line up with our static 13.5 results (0x23d2c4000 and 0x23d004008..18). Effort: 1–2 h to read and map.

**B2. How to trace sleep without breaking it** (high confidence; `j700-s2r-measured.md` §2.1 and §5, `sptm_virt_s2r.c`)
- Trapping whole PMGR/SPMI blocks slowed the quiesce past macOS's ~5 s reconfig watchdog, which then reset the machine. Hook only the commit page and a few small pages.
- Never arm WFI trapping (TWI).
- Do not strip the watchdog's reset-enable bit.
- Print nothing after the commit; write records to a ring in reserved RAM instead.
- A reset loses DRAM because iBoot zeroes it, so evidence has to come from the PMU.
- The USB debug link (ATC0) loses power during sleep.
- On J700, with exclaves off, DCP could not reach power state 0 and XNU panicked during sleep. Check whether that applies to M1.
- **Use:** configure the trace-kit tracers this way. m1n1's Python tracers send each access to the host, which is much slower. An in-C ring hook would take 1–2 days.

**B3. PMU post-mortem tools for failed sleep attempts** (medium-high confidence)
- `proxyclient/tools/reset_reason.py` (`feat/sptm-hv`): reads, read-only and driven by the ADT, the PMU `info-fault_log` / `fault_shadow` with bit names such as `wdog,reset_in_1`, plus `leg_scrpad`.
- `src/pmu_counter.c` (main): iBoot counts unclean boots at `leg_scrpad+2` and drops to recoveryOS when the count gets too high. Repeated failed S2R attempts could put the M1 into the recovery error screen.
- The `feat/sptm-hv` version adds a wake breadcrumb in a spare PMU scratch byte (0x8208 on J700), read and cleared at stage 1.
- **Use:** port the reader to m1n1's proxyclient and run it after every failed attempt. Clear the counter. Pick an M1 scratch byte only after confirming nothing uses it. Effort: about half a day.

**B4. PMP tunables** (low-medium confidence; M2 Pro has PMP v2, the M1 has v1)
- **Where:** aurora-silicon/m1n1 PR #63 (`pmp-tunables-fit`), aura PR #88 (`pmp/t6000-t8112-boot-data`, a0201cd), and aura's `dt_set_pmp`/`dt_fill_pmp` in `src/kboot.c`.
- **Measurement:** enabling the PMP on an M2 Pro took awake idle from 3.485 W to 2.566 W (SoC 1.99 to 1.34 W). The PMP node received the ADT `apple,tunable-*` properties plus board-id, dram-vendor-id and capacity, and `APPLE_USE_PMP` also selects which devices report power to the PMP.
- **Use:** check whether our pmp-v1 overlay passes those tunables (from `/arm-io/pmp/iop-pmp-nub`) and reports power for the right devices. Ours measured only 0–50 mW. Effort: hours.

**B5. Hibernation (S4) is working on M4 Pro** (medium confidence as a route to near-zero standby; high effort)
- **Where:** aura PR #66 (fbalazsy, branch `j616s/hibernation-layout`, not in our clones, so I read only the PR body) and aurora-silicon/linux#906.
- **How it works:**
  - With `hib=1`, the boot loader gives the kernel a fixed memory layout and publishes it as `/chosen/aura,hibernate-layout` and `/chosen/aura,hibernate-dt`.
  - Secondary CPUs go down and come back through PSCI CPU_OFF/CPU_ON.
  - SYSTEM_OFF halts with the watchdog stopped.
  - The Linux series restores NVMe/ANS, DCP, SMC, Type-C and MTP.
  - Two shutdown cycles came back fully.
- **Bearing on us:** this addresses the blockers our STATUS lists as "not possible": CPU offline and coprocessor restore.
- **Use:** port it to M1 with m1n1 as the boot loader. It needs our CPU hotplug work. Effort: weeks.

## C. Checked and not relevant (one line each)
- aura `src/nv2.c`, `pv_kvm.c`, `monitor.c`, `psci.c`: need FEAT_NV2, or apply only to chips that confine secondary CPUs (CTXR); M1–M3 keep the OS at EL2. PSCI only parks CPUs; no powerdown-legacy equivalent.
- aura `feat/ctxr-exec-window` (PR #77): CTXR-confined chips only (T8140 and later).
- aura `feat/macho-boot-object`, `docs/macho-boot-object.md`: kcbz=0 Mach-O wrapper for M4/A18.
- aura `j873-afk-handoff` (#89), `satchlj/j613-native26-external` (#86), `fix/audio-acoustic-identity`, `work/t3784-sio` (#34), `j713/dcpext-handoff`, `fix/debug-uart-stdout-path`, `fix/monitor-probe-*`, `cdc-boot-uploads`, `j873-public-boot`, `release/*`, `backup/*`: other SoCs or release plumbing.
- aura `m1pro/aura24-heap-20261031`: Stage 1 heap changes; its M1–M3 ANS sleep timing applies at chainload only.
- aura open PRs #82 (aura-try), #15 (CTRR_D on M4+), #12/#9 (J873g), #11 (T8152 NVMe), #10 (cpufreq proxy): not M1 power.
- aura docs j616s-*, j713, j813, j873*, t8142-*, t8122-gpu-diagnostics, m5-m6, cdc-boot, stage2-dtbs, j700-install, j700-nv2-pmu, m1-m3-handoff-sources, boot-options, licensing, RELEASING, validation/, releases/: other boards, install steps or provenance.
- aurora-silicon/m1n1 and omacom/m1n1 `j873` branch: Windows-on-Apple-Silicon hypervisor (vGIC, PSCI, TPM, hv_xfer bulk channel) for M5/T8142, not macOS/SPTM.
- aurora-silicon/m1n1 `main`, `aurora-wip`, `work/*`, `satchlj/*`, `j613/*`: display, GPU, ISP, AOP, SIO and DART handoffs for M2–M4. Hypervisor changes are only A2 and A7; no M1 SPTM loader, no T8103 power code.
- omacom/m1n1 `integration/aurora` and the feat/fix/chris/max/neo branches: handoffs for other SoCs. omacom `main` is an older m1n1 (Sept 2026).
- Open PRs omacom #16 and #21–#25, aurora-silicon/m1n1 #9, #62 and #64: display, GPU or SEP on other SoCs.
- Issues: none open on aura or omacom/m1n1; aurora-silicon/m1n1 has issues disabled.
- Searched for powerdown-legacy, cpu-release and spin-table power-down: nothing relevant to M1.
- The macOS sleep-program and reconfig docs that the S2R docs cite (`work/aura-macho/...`, `RECONFIG-RVBAR-WAKE.md`) are not in any public repo.

Files are in /tmp/claude-1000/-home-naeem--config-Claude-scratch-workspaces-1f07808c-2360-478e-a95f-ba9bd83341fb-6e170f00-d2a2-46d6-a9e8-f35600666f81-scratch-2026-11-05-4bcc96/f10f5b89-ddc4-474d-be69-a9a9989967a2/scratchpad:
- aura_hv_sprr.c
- aura_sptm_virt.c
- aura_s2r.c
- aura_hv_init.py
- m1n1_70757/ (src/hv and proxyclient/m1n1/hv at 70757dc7)

### kernel
I checked aurora-silicon/linux: all 381 branches, all 941 PRs (open, merged and closed) and the docs. Issues are turned off on that repo. To compare with what the M1 runs, I matched commit subjects against `omacom/linux-aurora@b798f2b` (the base of `7.2.11-14`) and test-merged each candidate with `git merge-tree` onto b798f2b. No code from the repos was run.

Nothing in aurora-silicon/linux adds suspend-to-RAM or SoC power collapse for any SoC. The only real-sleep work is a hibernation series for M4 Pro. Everything else listed below improves s2idle or idle power.

## Useful findings, ranked

**1. Ten-millisecond power-on wait in PMGR (likely the fix for "PS fpwm1: Failed to reach power state 0xf")**
- **Where:** `integration/aurora`, commit `8c2ba08c751`, `drivers/pmdomain/apple/pmgr-pwrstate.c`.
- **What it does:** our kernel waits 100 µs for a domain to report "on", and genpd ignores the error and marks it on anyway. Aurora's commit message says the T6000 GPU domain needed more than 100 µs after resume. This commit waits up to 10 ms on power-on, the same as m1n1, and leaves power-off timing alone.
- **How we'd use it:** it does not apply cleanly to b798f2b (our version of `apple_pmgr_ps_set()` is older). Port it by hand, about 3 lines:
  - add `#define APPLE_PMGR_PS_ACTIVE_TIMEOUT 10000`;
  - use that timeout when `pstate == APPLE_PMGR_PS_ACTIVE`, in both poll loops.

  Then check the "now: 0x…" value in the log after resume. If fpwm1 still reads 0x4 (clock-gated) after 10 ms, the fix is to mark `ps_fpwm1` `apple,externally-clocked` in the DT instead.
- **Effort:** small, about 1 h plus one lab suspend run. **Confidence:** medium-high that this is the cause of the message. No power saving is expected; the gain is correct power-domain state after resume.

**2. Put empty CD321x Type-C ports to sleep, as macOS does**
- **Where:** open PR #425 (nekolyanich/`pr/cd321x-unplug-sleep-73`), also branch `review/pr425-fixtures-t3094-v3`, commit `840c4ba04ca`. Files: `drivers/usb/typec/tipd/core.c`, `tps6598x.h`. Not merged to `integration/aurora`.
- **What it does:** when a port is empty at probe or after an unplug, it writes 0x2000 to the undocumented register 0x50, sends SSPS 2 (the "unplugged" power state), then clears 0x50. It sends SSPS 0 as soon as STATUS shows a plug. The author traced this sequence from macOS. It is enabled through `tipd_cd321x_data`, which is the I2C CD321x driver data the M1 uses.
- **Why it matters for us:** today the M1's PD controllers stay in S0 forever (`tipd_suspend` only disables the IRQ). On M4, aurora measured 190 mW awake against about 1 mW asleep for the SN201202x controllers (`8e656b0b697`). That is a different chip, so the M1 figure is unknown. It may also stop the tps6598x early wakes we saw.
- **How we'd use it:** it cherry-picks cleanly onto b798f2b. Build a lab kernel, then run the idle A/B and a plug/unplug/DP-alt replug test on both ports.
- **Effort:** small. **Confidence:** high that it applies and is safe (tested on M2 Pro under the m1n1 hypervisor and natively). Low to medium on how much it saves.

**3. Stop network TX before the Wi-Fi D3 handshake (brcmfmac)**
- **Where:** `integration/aurora`, commit `43d03538d38`; it includes the earlier `229031640b7`, which is on branch `fix/t4151-brcmfmac-suspend-regulatory`. Files: brcmfmac `cfg80211.c/h`, `core.c/h`, `msgbuf.c/h`, `pcie.c`.
- **What it does:** stops and drains network TX before the PCIe D3 handshake and fences the msgbuf TX and flowring workers. It restarts them only after interrupts and HOSTREADY are back, and restores TX if D3 fails. It also caches country (regulatory) changes made while suspended and replays them on resume.
- **How we'd use it:** it is complementary to our `fix/brcmfmac-irq-ready-v2` and `fix/brcmfmac-d3-recovery-v2`; it addresses a different race on the same D3 path.
  - Onto b798f2b the kernel code merges cleanly; only `tools/asahi/run-host-tests.py` conflicts, so drop that file.
  - On top of our d3-recovery-v2 it conflicts in `pcie.c` and needs a hand merge.

  Then re-run the 15-cycle suspend stress test with the L1.1/L1.2 sleep hook turned off, to see whether TX quiescing removes the every-fourth-suspend D3 failure.
- **Effort:** medium (half a day). **Confidence:** medium that it helps the D3 problem, high that it is harmless.

**4. Hibernation framework (zero-watt standby)**
- **Where:** open PR #906 (fbalazsy/linux `j616s/s4-hibernation`): 24 commits on `integration/aurora@21f7ffcf`, +6373 lines. It needs a rebase and depends on aurora-silicon/aura#66.
- **What it covers:**
  - `soc: apple: aura-hibernate` (`5016c6c3f551`): leaves the boot's reserved memory out of the image, keyed on `/chosen/aura,hibernate-layout`.
  - Durable image signature handling (`d4f9eb5ceb15`).
  - arm64 cache cleaning to the PoC on hibernation and resume (`d7201a452d3a`, `eff3cf582304`).
  - Restore after resume for AIC masks (`69446324bf09`), SPMI masks (`a9aad40e3038`), PMGR domains (`bff385039a27`) and locked DART roots (`81d6dc9e429f`).
  - Re-adoption by rtkit-helper (`02e934802ed7`), SMC session restart (`9eab0af16b6e`) and `macsmc-reboot` (`3c78e6d0bff1`).
- **How it parks CPUs:** through PSCI CPU_OFF/CPU_ON provided by aura (aura#66), not spin-table. That is the same blocker STATUS lists for hibernation, and the answer to it.
- **How we'd use it:** the generic commits listed above apply to t8103. The M1-specific parts would have to be new:
  - DCP restart for M1 firmware 13.5;
  - AGX G13 republish;
  - NVMe restore for the pre-M4 ANS (the PR only does post-M4);
  - CD321x/ATC restore;
  - brcmfmac reload.

  It also needs the aura PSCI (a separate thread) or our `m1power/s2r-cpu-hotplug` work. It doesn't give S2R, but it gives the real "power off with session saved" option.
- **Effort:** large (weeks). **Confidence:** medium. It only works on M4 Pro under aura so far.

**5. Runtime PM so idle USB-C ports power down (for `atc1_*`)**
- **Where:** all on `integration/aurora`:
  - `c8372a0ec63` (dwc3-apple idle runtime suspend for T6040);
  - `4cacc48c78a` (T8132 version; the glue owns runtime PM before the first cable);
  - `dcb1f4fa244` (never-plugged T6041 port);
  - `1c79b032094` (`phy: apple: atc` idle runtime-suspend for T8132);
  - `cf4eb7c2e35` (DT: move controllers, DARTs and PHYs into the ATCn_USB domains).
- **What it does:** exactly what STATUS says the `atc1_*` complex needs ("runtime PM across the ATC block, not an unbind"). On J713 aurora measured 90-130 mW for two idle ports.
- **How we'd use it:**
  - Add `apple,t8103-dwc3` to `idle_rpm` in `dwc3_apple_probe`.
  - Port the ATC PHY `idle_power_off` behaviour to t8103. Aurora limits it to PHYs without DisplayPort, and the M1 port has DP-alt, so the DP PHY ops also need runtime-PM references.
  - Fix up the t8103 DT domain placement.
  - Note: `ps_atc0_common` is `apple,always-on` in `t8103-jxxx.dtsi` (a DP-alt workaround), but `atc1` is not.
- **Effort:** medium-large. **Confidence:** medium on the method, low to medium on saving more than about 30-60 mW on M1.

**6. Fabric p-state while idle (pmgr-misc), a lead only**
- **Where:** `drivers/soc/apple/apple-pmgr-misc.c`, commits `b461cd56032`, `cfdcdd6ed4b`, `ce32dd57ffe`. These are already in our kernel, but only for t6000/t6020.
- **What it does:** aurora reports lowering the fabric p-state while idle saves about 0.5 W on t6000, and about 0.35 W in s2idle. The commit message says there is "no change on Macs without pmgr-misc (M1, M2, M3)". t8103 has no `fabric-ps`/`dcs-ps` node.
- **How we'd use it:** find the t8103 equivalent of the CLKGEN p-state registers from the ADT, read and write them with `m1power.ko`, and if one exists add a `t8103-pmgr-misc` match.
- **Effort:** research. **Confidence:** low. On t8103 iBoot or hardware may already handle this; DRAM gating is already about 92% with the panel off.

**7. Small correctness fixes that apply cleanly to b798f2b**
- `7f12ac1acdd` nvme-apple: polls up to 100 µs when an interrupt finds both queues empty, instead of waiting out the 30 s timeout. On M4 Pro that late completion delayed suspend entry by 19 s. Worth taking. Small effort, medium confidence for M1.
- `3543be41e12` drm/apple: no VT switch on suspend. Removes the console flash and a little resume latency. Small, high.
- `afd51176986` bcm4377 Bluetooth: aborts suspend if arming the wake IRQ fails. Small, medium.
- `df65571d77c` cd321x: refreshes power status on resume even without a plug; fixes the reported AC state after unplugging during sleep. Small, high.
- `0c633c982c3` atc: skips stopped PIPE locks on M1/M2 (removes the "Pipehandler lock not acked" warning on unplug). Small, high.
- `17ab8faf7da` macsmc-input: sets up wakeup before registering the notifier (lid/power-button wake race). Small.

**8. Hold mailbox messages during sleep (optional)**
- **Where:** `integration/aurora` `7c5a1efc5f0` plus `apple,hold-rx-in-sleep` in DT; applies cleanly.
- **What it does:** masks a coprocessor mailbox's receive IRQ for the duration of s2idle. On J713 it cut 1472 wakeups to 3.
- **For M1:** our ledger shows P-cores enter CPU PD once per sleep and stay there, so the gain is likely nil. Check wakeup counts before using it. Small effort, low confidence.

## Confirmations and rebase hazards
- **dwc3 unbind oops:** aurora fixed the same never-connected `remove()` NULL dereference independently. `3949e3640d9` sets `platform_set_drvdata()` in probe, which matches our omacom/linux-aurora#365.
- **PMU RTC alarm:** our `m1power/s2r-pmu-rtc` is built on aurora's own `rtc: macsmc: Add the PMU alarm` (`3a07515269f`/`0d8a55c70a2`). The generic `drivers/rtc/rtc-apple-pmu.c` (Baku/Abbey) uses the same register layout as Sera at 0xd000, but its `.prepare` returns -EBUSY unless the target is s2idle, so it would need changing for S2R. Nothing new to take there.
- **Wake flags:** the AIC (`a48ca155bf4`), SPMI (`0cc4a061df2`) and PCIe MSI (`0ac2a82b2a8`) wake flags are already in our kernel.
- **Linux 7.3 Wi-Fi hazard:** `f0ba5fd51ff2` (Set DMA direction for msgbuf packet IDs) breaks BCM4378 Wi-Fi on 7.3: DART read fault, then `brcmf_msgbuf_query_dcmd_len` timeouts. The fix is open PR #926 (joske/`brcmfmac-bcm4378-rx-dma`, `666e108eb60c`). Not in 7.2.11; we need it if we rebase to 7.3.

## Checked and irrelevant
- `aurora/bits/*` (000 through 900): every commit is already in our running kernel.
- `aurora-wip`, `-edge`, `-rc`, `-stable`, `unified/7.2.1x`, `rebase-wip/7.2.10`: nothing extra for M1 except `idle=` (already in our kernel).
- cpuidle-apple (`959e9ad0ad1`): t8103 is already on its allow-list; the T6040/T8132/T6050 states and PR #826 are for newer SoCs.
- `34649b455f4`, `apple-idle.h` register-saving WFI: T6040 and later only.
- pmp.rs, pmp-report, pmc, clpc and PR #1020: t6000/t8112/t60xx/t81xx only; no t8103 PMP. Our `m1power/pmp-v1` stays the only route.
- `8fd377b7d93` (sleep-retained domains) and `3db9b1f2bbb` (multi-parent power-on): J713/J616s problems that don't occur on M1.
- `f82267ce117` rtkit resume order: its caller was removed again (`244f347d7de`).
- `9a0926526e8` (`j514s/sleep`, never-started DCPEXT powers off in sleep): only in `dcpext-t6030.c`. Our `dcp.c` calls `device_set_wakeup_path()` for every DCP, which explains why `dispext_*` stays on, but the fix would be our own port.
- M4 DCP `setPowerState` on blank/sleep (`aec96e5158b`, `53899593311`): M1's `iomfb_template.c` already uses setPowerState.
- `j514s/sleep-20261022` (M3 Pro 1.29 W s2idle): T6030 pieces; its SPMI/RTC parts are already in our kernel.
- `j700/dcp-s2idle`: H17P; its AIC/dwc3 wake parts are already in our kernel.
- `apif-*`, `t6050/*`, `j716c/*`, docs `aurora-apif-*.rst`: M5 running as a guest with SPTM resident; not M1.
- `rtc-apple-spmi-pmu.c` (`4832ab22bb9`, `t6050/pmu-rtc`): T6050 only.
- `ane/*` branches, accel/ane H13 commits: perf, timing and recovery only; the t8103 ANE DT is already in our kernel.
- `avd/*`, `ave/*`, prores, isp, `camera/*`: codecs and camera; the t8103 AVD has its own domain, so check `avd_sys` in `pmgr_ps` if in doubt.
- drm/asahi G13 commits: stats, memory accounting, queue lifetime; nothing on idle power for G13.
- thermal power-allocator, macsmc hwmon/fan: thermal policy, not idle power.
- macsmc_power (`b8e84d08eef`, CHLS): charge thresholds only.
- SEP/Touch ID (`fix/sep-*`, `test/sep-*`, `tools/aurora-sep/M1-SUPPORT.md`): unrelated to power.
- `feat/apple-afp`, `-amx`, `-apflg`, `-prsv`, `feat/ctxr-execmem`, KVM/neo: CPU features and virtualisation.
- `fix/apple-dwc3-pending-teardown`, `test/j700-*`, `test/neo-*`: ATC teardown robustness on J700; conflicts with our `atc.c` and has no power effect.
- PCIe-C/Thunderbolt tunnel commits (`2309ea1a14b` and others): tunnels only; nothing on BCM4378 ASPM L1ss.
- PR #915 (uclamp background cap), #932 (t602x energy model): affect awake scheduling only; the t8103 OPPs already carry microwatts.
- `config/aurora-platform-defaults`: a defconfig merge only.
- `tools/aurora-sep/HIBERNATION.md`: lists what's missing, now superseded by PR #906.

Everything is in the scratchpad: `/tmp/claude-1000/-home-naeem--config-Claude-scratch-workspaces-1f07808c-2360-478e-a95f-ba9bd83341fb-6e170f00-d2a2-46d6-a9e8-f35600666f81-scratch-2026-11-05-4bcc96/f10f5b89-ddc4-474d-be69-a9a9989967a2/scratchpad/`
- `aura/aurora-linux.git`: blobless shallow clone of all branches, plus our `malik/m1power/*` and `malik/fix/brcmfmac-d3-recovery-v2`.
- `aura/omacom-linux.git`: the same for omacom/linux-aurora.
- `aura/aurora-new.log`: the 1867 path-filtered commits our running kernel lacks.
- `aura/prs.tsv`: all PRs.
- `trypick.sh`: the merge-tree check script.

### tooling
# aurora-silicon scope review: what the M1 power lab can use

I read the code, docs, branches, open PRs and issues. I ran nothing from these repos. Clones are in `…/scratchpad/aura/as_<repo>` (`as_recovery-ssh`, `as_tuxvdmtool`, and so on). Most useful first.

## Findings that are useful

### 1. tuxvdmtool: the M3 Max reboots, DFUs or serial-consoles the M1 with no button presses
- **Repo/branch:** `aurora-silicon/tuxvdmtool`, `main` (187d73a). Branches `connector-labels`, `reboot-debugusb` and `port-disconnect` are already merged into `main`.
- **What it does:** A Linux-to-Apple-Silicon VDM tool. It sends Apple's USB-C PD vendor messages to the M1's PD controller: `reboot`, `dfu`, `serial`, `debugusb`, `reboot serial`, `reboot debugusb`, `disconnect`, `nop`.
  - These go to the M1's USB-C controller, not to its CPUs. A hung hypervisor run (the native-mode silent hang) can very likely still be reset this way. That is my inference from how macvdmtool is used; I did not test it.
  - The README says to use the M1's DFU port with a SuperSpeed or Thunderbolt cable. For the Air that is "the rear port".
- **How we would use it:**
  - Go to the M3 host's USB-C port connector label with `grep -a 'USB-C ' /sys/class/i2c-dev/i2c-?/device/*/of_node/connector/label`.
  - Then run `sudo tuxvdmtool --connector <label> reboot`. The M1 reboots, iBoot runs the Permissive boot policy, and m1n1 70757dc comes up in proxy mode as `/dev/ttyACM*` (the host already saw `ttyACM0` and `ttyACM1` on the old ThinkPad setup, per `LAB-INVENTORY.md`).
  - The loop becomes: run the hv script, hit the hang, `tuxvdmtool reboot`, repeat. This is the highest-value item.
  - `reboot serial` gives a hardware UART on `/dev/ttySAC0` (`export M1N1DEVICE=/dev/ttySAC0`), which would show m1n1 output when the proxy path is dead.
  - `dfu` and `reboot debugusb` are fallbacks.
- **Host-side checks (this host, 7.2.11-14-1-ARCH):**
  - The tipd modules are present (`tps6598x-core`, `sn201202x`), and the typec ports already show partners.
  - `/proc/config.gz` has `CONFIG_TYPEC_TPS6598X_DEBUG_COMMANDS` not set. The `command` debugfs file needs it (Kconfig in `aurora-silicon/linux` `drivers/usb/typec/tipd/Kconfig`; `regs` is read-only without it). The module still contains debugfs strings, so check `sudo ls /sys/kernel/debug/usb/tipd/*/` for a `command` file.
  - If it is missing, rebuild only `tps6598x-core.ko` from `aurora-silicon/linux` `integration/aurora` with the option on.
  - The host has both i2c cd321x devices (`0-0038..003a`) and SPMI `sn201202x`. Check which controller owns the cable's port.
  - M3 and later hosts don't use i2c, so tuxvdmtool uses the kernel route; that path is new (Oct 2026).
- **Risks:**
  - `/dev/ttySAC0` on an M3 host is unverified. The README shows it only for the `serial` subcommand, not for M3 hosts.
  - `docs/LIVE.md` says the current cable carries power only, so confirm it is a full SuperSpeed cable.
  - `reset-controller` isn't available through the kernel route.
- **Effort:** 1 hour if `command` exists; half a day if the module must be rebuilt.
- **Confidence:** Reboot works: high. Serial on M3 host: low to medium.

### 2. recovery-ssh: shell into the M1's macOS Recovery from the M3 Max
- **Repo/branch:** `aurora-silicon/recovery-ssh`, `j813` (the only branch; 02d9580 adds Linux controller support). No open PRs; issues are not enabled.
- **What it does:** Recovery has no `sshd`. The Recovery Mac makes an outbound SSH connection to the controller, and a PTY helper (`ptywrap`, universal Mach-O) gives an interactive shell on the controller's `127.0.0.1`. It works over the USB-C cable (Recovery exposes CDC-NCM), over LAN, or `auto` (USB first, then Wi-Fi). A launcher and a restricted key are installed on `/Volumes/Data`. The key is restricted to a loopback `nc` listener, with pinned host keys.
- **How we would use it:**
  - **On the M3 (Linux controller):** `sshd` running, and a macOS-built `dist/ptywrap` copied into the tree. The README says to copy it from a macOS release build.
  - **Building ptywrap:** `ptywrap.c` needs `<util.h>` and `openpty`. The simplest build is `make release` on the M1's own macOS with Command Line Tools. Cross-building from Linux is awkward (`zig` and `clang` are not installed here).
  - **Check:** `./recovery-ssh doctor`.
  - **Start:** `./recovery-ssh start --name m1 --transport lan --host <M3 tailscale or LAN IP>`. USB endpoints must be given explicitly on Linux: `--usb-host`, `--lan-host` or `--host`.
  - **The owner's part:** boot the M1 to 1TR once and paste the printed `curl … | sh`. After that, a later 1TR needs only `sh /Volumes/Data/recovery-ssh`. `./recovery-ssh connect --name m1` gives a PTY, so password prompts for `bputil` and `kmutil` work.
  - **What we can then run remotely:** the installer's step-2 commands (`src/step2/step2.sh`):
    - `bputil -d -v <VGID>`
    - `bputil -nc -v <VGID>`
    - `kmutil configure-boot -c m1n1.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v <system_dir>`
    - `csrutil`
  - **Why it matters:** this swaps the Stage-1 m1n1, which `update-m1n1` from Linux cannot change, and it lets us set up the planned separate macOS 13.5 volume and its boot policy.
- **Limits:**
  - Entering 1TR still needs a physical power-button hold, unless item 3 works.
  - The Data volume must be unlocked and mounted in Recovery (FileVault).
  - Linux controller support is recent and lightly tested.
  - The README says USB mode "works with USB 2 or USB 3 cables" and doesn't need `iproxy`, but it only auto-detects macOS controllers.
- **Effort:** 2 to 3 hours the first time (ptywrap build plus owner paste), then minutes per session.
- **Confidence:** Medium-high.

### 3. aurora-bless (asahi-nvram + asahi-bless): NVRAM and boot target from Linux
- **Repo/branch:** `aurora-silicon/aurora-bless`, `master` only (903a630). It is an Asahi Rust workspace (`asahi-nvram`, `asahi-bless`, `apple-nvram`). The Aurora additions are MacBook Neo support, a write-window fix, and v3 record bounds. `/usr/bin/asahi-bless` is already on the host.
- **What it does:** It reads and writes Apple NVRAM from Linux through `/dev/mtd/by-name/nvram`. Commands:
  - `asahi-nvram read|write|delete VAR[=VAL]`
  - `asahi-bless --list-volumes`
  - `asahi-bless --get-boot` (add `--next` to show the next-boot target)
  - `asahi-bless --set-boot <name|index> [--next]`
  - `asahi-bless --set-boot-macos`
  - `asahi-bless --clear-next`
  - `-y` to skip the confirmation
- **How we would use it:**
  - Run it on the M1 (not the M3) over Tailscale SSH. `sudo asahi-bless --set-boot-macos --next -y` followed by `reboot` boots macOS once for the hypervisor run, and the default stays Linux.
  - Combined with tuxvdmtool, the whole Linux/macOS switch is scriptable without touching the machine.
  - It can also set or clear `boot-args` (`asahi-nvram write boot-args=…`).
  - It can set `alt-boot-volume`.
- **Not verified:**
  - I did not confirm that `asahi-bless` is installed on the M1. Check there.
  - One idea from my own background knowledge, not from these repos: `recovery-boot-mode=unused` in NVRAM boots 1TR. It would remove the power-button hold from item 2. It is untested here; `asahi-nvram write` may reach it. Try it on the M1 only when the owner can recover it.
  - **Warning:** the README says NVRAM writes "may or may not result in you having to perform a dfu restore". Read the variable first (`read`), and keep a DFU path ready before any write.
- **Effort:** 30 minutes.
- **Confidence:** Medium-high for next-boot target; low for the recovery-boot idea.

### 4. u-boot, branch `apif/sptm-macho` and aura PR #29: how Aurora boots without SPTM on M4 and later
- **Repo/path:** `aurora-silicon/aura` PR #29 (merged) and `aurora-silicon/aurora-installer` PR #72 (open), `macOS/Recovery/Sources/Account/AuraStage1.swift` and `Tests/MachOBootObjectCheck.swift`. The u-boot branch `apif/sptm-macho` itself is only the M5 APIF guest transport and is not relevant to M1.
- **What it does:** `kmutil configure-boot` without `--raw` records `__TEXT_BOOT_EXEC` size as `kcbz`. The PR says macOS 27.2 iBoot loads TXM, ExclaveOS and SPTM, and enters SPTM, only when `kcbz` is nonzero. With `kcbz` 0 it jumps to the object's entry, as in raw mode. Aurora therefore wraps its Stage 1 in an `MH_FILESET` with no `__TEXT_BOOT_EXEC`.
- **How we would use it:**
  - Treat it as a reference for the validation recipe: `kmutil inspect -z -B <object> --show-mach-boot-properties` must report `kcbz : 0`. The installer Recovery flow then runs `bputil -nc -v <group>` and `kmutil configure-boot -c <object> -v <volume>`.
  - Our M1 isn't affected. The raw route already skips SPTM on M1 (the PR text says "GXF writable as on M1 to M3"). The hang we hit is the macOS guest's own SPTM under the m1n1 hv, which is a different problem.
  - It may still show what iBoot does with `kcbz`, if you want SPTM-less macOS 27 behaviour questions answered.
- **Effort:** reading only.
- **Confidence:** High that it is irrelevant to the M1 hang; low that it helps.

### 5. aurora-diag: a read-only snapshot and diff of power-relevant state
- **Repo/branch:** `aurora-silicon/aurora-diag`, `main` (cd861d7); `gpu/telemetry-util-freq-20261101` (PR #7, open) adds GPU-only changes.
- **What it does:** A Python (stdlib) tool that reads sysfs, the device tree and debugfs. It covers hwmon, thermal, cpuidle states and residency, power supplies, `suspend_stats`, wakeup sources, Type-C, PCIe link speeds, and per-device `runtime_status`. `check`, `snapshot` and `diff` compare two boots. It has one logged and reversible write path (`aurora-diag set ID VALUE`, `restore`), but `/sys/power` stays read-only.
- **How we would use it:**
  - Before and after each kernel or DT change on the M1: `aurora-diag snapshot -o before.json` then `aurora-diag diff before.json after.json`. It would catch a driver that stopped binding or a device that stopped runtime-suspending.
  - `aurora-diag show system --json` gives suspend statistics, and `show power --json` gives the power rails.
  - It is not a measurement source: the SMC accumulators (`zSPa`, `zSLa`) we already read are better. It is a regression guard.
  - Its macOS comparison data is for the J616s, not the M1.
- **Effort:** under 1 hour.
- **Confidence:** Medium.

### 6. alarm-aurora: the shipping kernel config
- **Repo/path:** `aurora-silicon/alarm-aurora`, `packages/linux-aurora/config` (pins `aurora-silicon/linux` commit 2661d71e).
- **What it does:** It holds the exact config of the kernel on the M1. Relevant lines:
  - `CONFIG_SUSPEND=y` and `CONFIG_HIBERNATION` is not set.
  - `CONFIG_CPU_IDLE_GOV_TEO=y`, `CONFIG_ARM_APPLE_CPUIDLE=y`, and PSCI cpuidle as well.
  - `CONFIG_NO_HZ_FULL=y` with `CONFIG_HZ_1000=y`.
  - `CONFIG_PCIEASPM_DEFAULT=y`, with POWERSAVE and SUPERSAVE not set.
  - `CONFIG_USB_AUTOSUSPEND_DELAY=2`.
  - `CONFIG_PM_TEST_SUSPEND` is not set.
  - `CONFIG_MFD_MACSMC=y`.
- **How we would use it:**
  - Use it to check what the stock kernel can already do, and which options our `m1power/*` branches have to add. There are no suspend-related docs or open PRs in this repo.
  - The `linux` repo has open PRs for the cpuidle driver (#826, "cpuidle: apple: add T6050, so M5 suspend-to-idle freezes the tick") and for the J616s hibernation (#906). Those are outside my scope and might be a cross-reference for whoever reviews `linux`.
- **Effort:** reading only.
- **Confidence:** High on what the config says; low on any benefit.

## Checked, not relevant (one line each)

- **macvdmtool (`main`, `j813`):** macOS-only (IOKit). `j813` adds a macOS launch daemon (`macvdmd`) and `macvdmctl`. It only helps if the controller were a Mac; the Linux host should use tuxvdmtool.
- **aurora-installer (54 branches):** a native macOS installer and Recovery app for Aurora installs. Its `src/` is the upstream Asahi installer with the `bputil`/`kmutil` recipe quoted in item 2. The other open PRs are about M3, M4 and M5 hardware admission, Fedora and CTXR windows.
- **aura-related `alarm-aurora` PR #132 (update-m1n1 `boot-ctxr.bin`):** for M4 and later only. The PR text says M1 to M3 run unchanged.
- **alarm-aurora other branches and packages:** Plymouth, mutter VRR, FEX, Touch ID, Bluetooth LE audio, ANE, iwd OWE offload, fprintd. None touches M1 suspend. `aurora-system-fixes` and `aurora-boot` are ordering, DMI and early-KMS fixes.
- **aurora-platform:** first-boot and LUKS conversion for Fedora, ALARM and NixOS images. No power content (grep found none).
- **aurora-installer / aurora-distributions / aurora-platform:** catalogs, signing and image layout. Nothing for power.
- **aurora-neo-platform-config:** J700 (MacBook Neo) NetworkManager and libinput quirks. Not M1.
- **aurora-sep-userspace:** libfprint and fprintd patches for the Touch ID SEP on the Neo. Not M1.
- **kbd-light:** keyboard backlight follows ALS. Its main loop polls every 250 ms (`TICK_MS 250`), about 4 wakeups/s even when idle. Not installed on this host. If it is on the M1, it costs a little at idle, so it is a candidate to stop during power measurements, not a saving.
- **speakerguardd:** speaker-protection daemon; the unit runs `SCHED_FIFO` priority 50 and `mlockall`. The README describes a 250 ms lease while audio plays. I did not find idle polling, and it is not the cause of the measured 55 interrupts/s (that was `lab-agent`). Check `systemctl status` on the M1 only if wakeups remain.
- **upower:** a fork of upstream 1.91.4/1.91.5 with macsmc charge reporting and a keyboard-backlight object. No power policy.
- **mu (Project Mu UEFI, 17 branches):** Windows-on-Apple-Silicon firmware. The `codex/hvaa64-gl2-monitor` branch is Windows hypervisor memory and ACPI work; its only SPRR/GXF text is a comment that a secure monitor is "on hold". It is not M1 suspend and not SPTM.
- **mu_basecore, mu_plus, mu_silicon_arm_tiano, Windows-driver-samples:** upstream or vendor mirrors (Mu pieces, Microsoft samples); not opened beyond their description.
- **u-boot (`aurora-wip` and 18 other branches):** the boot-NOR and ESP U-Boot for newer chips (J713, J613, J700, T6050 APIF). `aurora-wip` has T8103 memory map code, but nothing for suspend or the hv. PRs #21, #26, #30 and #32 are NVMe, ESP and MTP keyboard fixes.
- **.github:** the org README is "New light for Apple Silicon." plus a Discord link; `features.md` has no power, suspend or M1 content.
- **Issue trackers:** the 11 issues across these repos are about M3 Air, M4 and BCM4378 Wi-Fi. Issue search for suspend, s2idle, SPTM, RTC and wake alarm returned none. `recovery-ssh`, `tuxvdmtool`, `macvdmtool` and `aurora-bless` have issues disabled (`mu` also).

## Suggested order
1. Check `ls /sys/kernel/debug/usb/tipd/*/` as root on the M3. If a `command` file exists, try `tuxvdmtool --connector <label> nop`, then `reboot`, on the M1 while it is in a known state.
2. On the M1, check for `asahi-bless` and run `asahi-bless --list-volumes` and `--get-boot` (read-only).
3. Build `ptywrap` on the M1's macOS and set up recovery-ssh when the owner next goes to 1TR.

### userspace
**Result:** the in-scope repos hold no sleep or SoC power-down mechanism for the M1, and nothing that unblocks the m1n1/SPTM hypervisor work. They hold only a few userspace and package-default findings. All of it is data from shallow clones, none of it executed.

**Coverage and limits.** I cloned 14 of the 27 repos at depth 1 with all branches into `.../scratchpad/aura2/`. They are omarchy-ane, camera-denoise, capture-ns, asahi-audio, alsa-ucm-conf-asahi, omarchy-pkgs, omarchy-mac-pkgs, fedora-aurora, nixos-aurora, splash, gpubench, avd-fw, xserver and omarchy-mac, plus omarchy. I read branch names for all 27 and the PR/issue lists. Because the clones are shallow, I only saw each branch's tip commit, not its history.

I did not open individual branches in omarchy (440 branches) or mesa. In omarchy I only inspected the branches whose names mention power or idle. GitHub code search was swamped by the `linux` repo, which is out of scope, and then hit the rate limit.

## Useful findings

**1. Wi-Fi resume wedge recovery**
- Repo: omarchy-mac-pkgs, branch main.
- Path: `omarchy-mac/bin/omarchy-wifi-resume-fix`, with `omarchy-mac/vendor/systemd/system/omarchy-wifi-resume-fix.service` and `wifi-test.sh`.
- What it does: after resume it watches the journal (by cursor, immune to clock jumps) for repeated `ASSOC-REJECT status_code=16`. On a hit it reloads `brcmfmac`, falling back to a 12 s timer. It cites AsahiLinux/linux#439.
- How we use it: this is the same firmware wedge that broke our suspends after the L1.1/L1.2 ASPM test. Copy the script and unit onto the M1 so a wedge after any s2idle heals itself. It also lets us retry the ASPM `powersupersave` experiment, which saved 171 to 290 mW, without needing a reboot.
- Limit: it only recovers after resume. It does not stop the `brcmf_pcie_pm_enter_D3 -5` failure at suspend entry, so we still need a pre-suspend `rmmod brcmfmac` workaround or a driver fix.
- Effort: low (about 1 hour). Confidence: high that the script works as described, medium that it fixes our D3 case.

**2. ANE runtime PM (omarchy-ane)**
- Repo: omarchy-ane, branch main (0.4.2 and later), `ane/src/ane_drv.c`.
- What it does: the driver has `autosuspend_ms=1500`, so the ANE power domains and DARTs go off after the last use. The changelog measured it on an M1 (T8103). With the ANE suspended, idle power equals the level with the module removed (within 33 mW). With it held on (`autosuspend_ms=0` or `power/control=on`), idle power is 107 to 173 mW higher.
- How we use it: on the M1, check `lsmod | grep ane`, `cat /sys/devices/platform/*ane*/power/{control,runtime_status}` and the `ane` lines in `pm_genpd_summary`. If it is bound and `control` is `on`, set `auto`, or blacklist the module.
- Also: it may explain which of the 45 domains that stay powered through sleep are ANE ones. The doc says `ane_cpu` and `ane_sys` stay on even with no driver.
- Effort: trivial. Confidence: high on the numbers, because they are the repo's own M1 measurements.

**3. Speaker amp no-suspend policy**
- Repo: omarchy-mac-pkgs, branch main.
- Path: `omarchy-mac/share/wireplumber/wireplumber.conf.d/asahi-audio-no-suspend.conf`. Its commit message is `f379cce`.
- What it does: it sets `session.suspend-timeout-seconds = 0` on the AppleJ speaker and headphone sinks. Its own comment says PipeWire's idle suspend powers down the speaker amplifiers, so this holds them powered. The commit that added the extra DSP-graph keep-alive measured audio-stack CPU rising from about 0.1% to 1.8-2.0% of one core.
- How we use it: confirm the file is not on our M1 (`/usr/share/wireplumber/wireplumber.conf.d/`, or `wpctl status` for the sink state). If present, remove it for the idle and sleep measurements. Amps are probably gated at s2idle anyway, so the gain is mainly awake idle. The `node.always-process` drop-in from `f379cce` is not in main, so I would not expect it.
- Effort: trivial. Confidence: medium. The mechanism is documented but I have not measured its watts.

**4. Omarchy's default of Wi-Fi power save off**
- Repo: omarchy, branch quattro.
- Path: `etc/NetworkManager/conf.d/omarchy-wifi-powersave.conf` (`wifi.powersave = 2`). Branch `drop-wifi-powersave-toggle`, commit `da157fb9`, explains why.
- What it does: Omarchy's default forces Wi-Fi power save off, because of latency spikes and link drops on Intel firmware. Our measurement says power save on saves 186 mW on the M1.
- How we use it: our persisted setting must sort after `omarchy-wifi-powersave.conf` in `/etc/NetworkManager/conf.d/` (or live in `/etc`, which wins). Check that an `omarchy update` does not rewrite it. A name like `99-m1-powersave.conf` is safe.
- Effort: trivial. Confidence: high.

**5. USB autosuspend disabled by default**
- Repo: omarchy, branch quattro, `etc/modprobe.d/omarchy-usb-autosuspend.conf` (`options usbcore autosuspend=-1`).
- What it does: it turns USB autosuspend off globally.
- How we use it: it is probably worth little on an Air with no internal USB devices. Check `cat /sys/module/usbcore/parameters/autosuspend` and set `2` if it is `-1`. This matters if we later test with a dongle plugged in.
- Effort: trivial. Confidence: low on the watts.

**6. Thunderbolt poll loops (watch-out)**
- Repo: omarchy, branch `thunderbolt-idle-recheck`, commit `4838ef71`.
- What it does: it states the Thunderbolt authorization daemon and watcher forked processes every 2 s even with no controller, about 1,590 launches a minute on an idle M2 Max. The branch changes that to 10 s.
- How we use it: those scripts are not in quattro yet. If they land in an Omarchy update, mask the daemon and watcher on the M1 (it has USB4). Also run `pidstat -w` or `perf trace` for fork rates, because Omarchy's `omarchy-hyprland-monitor-watch` only polls (2 s) while docked.
- Effort: none now. Confidence: medium.

**7. Kernel config comparison**
- Repos: omarchy-pkgs, fedora-aurora and nixos-aurora kernel configs.
- What they show: the three configs match on the power-relevant options. They set `CPU_IDLE`, the `TEO`, `LADDER` and `MENU` governors, `ARM_APPLE_CPUIDLE`, `ARM_APPLE_SOC_CPUFREQ`, `PM_GENERIC_DOMAINS_SLEEP`, `PCIEASPM_DEFAULT`, `HZ_1000`, `NO_HZ_FULL` and `PREEMPT`.
- How we use it: no action. It confirms our kernel's idle path is the shipped one. The only odd choice is `HZ=1000` with full preempt, which costs nothing in NO_HZ_IDLE but is a candidate if idle wakeups show up.
- Effort: none. Confidence: high.

## Seen but out of scope (the `linux` and `aura` repos)

I did not open any of these.
- `linux`: `Documentation/power/apple-s2idle.rst`, `tools/aurora-wake/` (including `s2idle-rtc-regression.sh` and `bt-wake-power.sh`), `tools/aurora-sep/HIBERNATION.md`, `drivers/cpuidle/cpuidle-apple.c`, and `tools/testing/selftests/drivers/apple/dart-s2idle-retention.py`.
- Open `linux` PRs: #972 (retain MTP through s2idle), #365 (panel power-off in DPMS and suspend), #707 (AVD runtime PM), #828 (Wi-Fi host-awake notification).
- `aura`: the aura spec mentions "ANS sleep before hand-off", which I did not open.
- These are the places to look for a real sleep or SoC power-down path.

## Checked and irrelevant

- **mesa:** branches are AGX/M4/M5 GPU userspace bring-up; no power work.
- **avd-fw:** firmware source with no power logic. Only worth noting that the AVD driver PM is `linux#707`, so check `lsmod | grep avd` on the M1.
- **omarchy-ane, M2/M3/M4/M6 material:** PMP, T6021 and H15/H18 branches do not apply to the M1.
- **mil-hwx-compiler:** an ANE compiler.
- **camera-denoise:** on-demand PipeWire filter with nothing running idle.
- **capture-ns:** a capture noise-suppression filter whose only "idle" hit was a benchmark note.
- **pipewire, whisper.cpp, fex, Windows-driver-samples:** upstream mirrors or forks with no relevant branches.
- **splash:** an inference engine; its idle-release setting is for model memory.
- **gpubench:** benchmark with an `idle.wake` test. That is useful only as a GPU power-down latency probe, not as a saving.
- **xserver:** an Xwayland implicit-sync patch.
- **asahi-audio and alsa-ucm-conf-asahi:** speaker and mic DSP graphs, with no idle or suspend settings in them.
- **omarchy-mac and omarchy-mac-installer:** macOS-side installer code.
- **omarchy-mac-pkgs-1:** an older duplicate of omarchy-mac-pkgs.
- **omarchy-pkgs:** `m1n1-aurora` is only a USB4 alias patch on m1n1 v1.6.1. `omarchy-power-profiles-daemon` is a CPPC/NVIDIA patch (N1x), not Apple. `linux-aurora` pins `aurora-silicon/linux` and carries no extra patches.
- **fedora-aurora and nixos-aurora:** these set logind power-key suspend and ship `aurora-kbd-light` (the keyboard backlight is off while the displays sleep), but no tuned, TLP or powertop defaults.
- **fatfs:** m1n1's FAT fork.
- **aurorairc, aurora-silicon.github.io, aurora-steam-native:** an IRC client, the website and Steam packaging.

## Not found

- Nothing on macOS sleep tracing, SPTM, FGT or hypervisor changes in the in-scope repos.
- No open issues or PRs on idle power or suspend for the M1 or t8103 in those repos. The one org-wide `power` hit I saw there was alarm-aurora#48, which concerns BCM4378 Wi-Fi on 7.3.
