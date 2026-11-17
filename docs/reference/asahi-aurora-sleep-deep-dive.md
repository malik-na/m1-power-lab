# Asahi and Aurora on deep sleep and SoC power-down: a reference

**Status: reference material, not observation.** This document collects what the Asahi Linux documentation and the Aurora Silicon repositories say, show or imply about suspend-to-RAM (s2r) and SoC power-down on Apple silicon. It contains no macOS 13.5 reading and no M1 measurement. Every statement is a source's claim or a marked inference. The clean-room spec agent should use it to interpret observations and to choose the next macOS readings. It must not be cited as evidence of what the M1 does.

Compiled 2026-11-18 from read-only reading of the Asahi docs clone and the Aurora clones and GitHub API. Nothing was built, run or flashed. No hardware was touched.

## How to read this document

Short names for sources:

- **AD** = Asahi docs repo @e8bcfea, `docs/<path>`. The matching URL is `https://asahilinux.org/docs/<path without .md>/`. URLs were mapped from the repo path and not fetched.
- **LI** = aurora-silicon/linux `integration/aurora`. Read two ways: a local sparse clone @1f38ff8 (2026-11-17) and the GitHub API at later tips (432f1758 and earlier). Line numbers cite the clone or the named commit.
- **L:`<branch>`** = an aurora-silicon/linux branch, usually with a short commit hash.
- **AU** = aurora-silicon/aura (the boot object and macOS-under-hypervisor tracer). **M1N1** = aurora-silicon/m1n1 (branches aurora-wip cd714cd, main cf57aeb, j873 e8a1720b). **UB** = u-boot, **MU** = mu (UEFI), **FA/AA/NA** = fedora-/alarm-/nixos-aurora packaging.

Kinds, on every statement:

- **documented**: prose in a doc or binding.
- **implemented**: code or a device-tree property.
- **measured**: a number or observation in a commit message or PR body. No raw logs were seen by anyone. Treat "measured" as the author's claim.
- **comment**: a code or DT comment.
- **inference**: reading drawn by the compilers of this document, not stated by the source.

Verifier tags: **[C]** = the verifier corrected the original claim and the text here is the corrected version. **[O]** = the verifier judged the original overstated and the text here is the weaker reading.

Chip names as the sources use them: t8103 = M1 (J313 Air). T8112 = M2. T6000/t600x = M1 Pro/Max/Ultra. T6020/t602x = M2 Pro/Max/Ultra. T8132 = M4 (J713 Air). T8140 = A18 Pro (J700, MacBook Neo). T6040/T6041 = M4 Pro/Max family (J616s). T6050 = M5-generation (J714s, J716c). T8142/T8152 = later M5/M6 parts.

---

## 1. Summary

1. Asahi documents no deep sleep. Its docs give the sleep-adjacent facts that exist: the AON watchdog block, SPMI standard sleep/shutdown/wakeup command classes, ACC_OVRD/CYC_OVRD field names, the RVBAR resume remark, and a feature-table cell "Suspend/sleep: linux-asahi" for M1 with no depth stated.
2. Neither Asahi nor Aurora ships working suspend-to-RAM on t8103. On M1 the only sleep in both trees is s2idle, which keeps the SoC powered (AIC, SPMI, PMGR domains and coprocessors stay up).
3. Aurora has a complete EL2 suspend-to-RAM driver (`drivers/soc/apple/sleep.c`, formerly `t8140-sleep.c`) that reports real power-down and wake on T8140 (J700) and T8132 (J713), and in-progress T6040/T6050. Its match table holds no t8103. It uses the same method as this lab: replay macOS's last ~14 ms in macOS's order, traced under Aurora's hypervisor.
4. In that model Linux does not power the SoC off. It writes ordered PMGR/PMU/MCC state, then one 4-byte "commit" word in the always-on block, masks AIC, and puts every core in deep WFI. An on-chip sleep engine then powers the SoC down.
5. The engine has untimed waits. Aurora recorded these causes of "commit reached, SoC stays up": a core not powered down in WFI, a boot core whose per-cluster PMGR WFI power-gate enable is clear, PMP/SIO/SEP/DCP firmware still running, DCS not at sleep state 4 with PMC voters non-zero, a domain left on or BUSY-latched, a serialized cluster power-down queue, and a USB/ATC/AUSS domain left on.
6. The recorded failure signature is a watchdog reset at a fixed time after the commit (5 s, 5.5 s, a configured 13 s). It is not a silent hang.
7. The PMU needs little from the AP. On T8140 only a boot-stage byte (0x50) and SPMI notify enables are written before the commit and nothing after it. One T8132 trace shows PMU writes after the commit ("go hib"), but Linux's later head sleeps and wakes without them.
8. The SMC is told slpw, then slpa, then an RTKit AP-idle notice last. A live USB-C debug cable can look like a cable pull to the SMC and wake the AP, or keep a commit from returning.
9. No source has t8103 data for the engine, PMGR power-gate words, the AON commit word, or the PMU sleep program. The M1 address correspondences below are arithmetic inferences.
10. Largest unknown: what the hardware engine checks between the last core's write and power-down. Nothing in these sources observed that gap.

---

## 2. After the last core stops

This is the section that matters. Everything is for non-M1 SoCs unless said. M1 transfer is inference.

### 2.1 The sequence Aurora runs, in order

Source for the T8140 order: LI `drivers/soc/apple/sleep.c` header lines 1-33 and `apple_sleep_commit` (L:fix/t8140-slpddr-coproc-crash 53bfa1914a, about L2604-2700; L:j713/dock-s2r-thunderbolt@903277c6 `t8140_sleep_commit` L2741-2825, `t8132_sleep_commit` L3370-3456), commit d43118bcb4. Kind: implemented. The header says "what the kernel does in suspend-to-RAM is what macOS does in its last 14 ms, with the order kept", with offsets "measured from a macOS sleep under aura".

Before the commit window (`.enter`): refusal checks; one CPU online; coprocessors quiesced; wake source enabled; parked CPUs "hold" handshake (100 ms); display off; coprocessor last checks; SEP request; first-pass coprocessor stops (GPU, withdrawing its PMP request first); wake masks; the macOS power-word match step; second-pass stops (ANS, SIO early, then PMP and the rest); USB/debug-link down; `cpu_suspend(commit)`.

The commit itself (T8140):

1. Other cores write their stop bit (cpu-start block +0x0) and park coherent.
2. Lower I/O domains (ATC0 USB, ATC0_COMMON, ATC0_USB_AON unless USB sleeps in place, PCIe/ANS block last).
3. Arm WD2 (5 s), clear WD0 control, write 0 to AON-misc +0x08 ("AP deadline").
4. Poll ten domains XNU polls off (ATC0_COMMON, DISP_SYS, DISPEXT0_SYS, ANS, AVD, VENC0/1, GFX, JPG, APCIE_SYS_GP). The sleep proceeds whatever they read.
5. SoC perf word (clk-perf word 0) to state 3. State is bits [11:8], busy is bit 31.
6. Write 0 to every PMC voter agent (4 agents, stride 0x4000), then DCS to state 4 via state 6. [C: the voters are zeroed in `t8140_sleep_dcs_down`, before the gates, not in the commit body.]
7. MCC channel step-down: enables cleared one bit at a time from fresh reads, then four lanes strobed (bit 16+4n) and cleared, two lanes per channel before the next two.
8. Power-gate CPM pair (T8140 0x60/0x68, T8132 0xa0/0xa8) written 0x80000000 twice around PTD words zeroed and PMC voter 0 zeroed twice.
9. Cluster complex words AVE (+8), E (+0), P (+4) written 0. SIO_CPU AUTO_ENABLE cleared.
10. Three clock-mux words parked with 0x80100000 ("the SoC refuses the first, on macOS too").
11. CLLT bits cleared. DVFM parked. All PMGR power words saved. AMCC error enables cleared (word0 bit 25, word1 bit 8).
12. Resume physical address written to the boot-object mailbox and cache-cleaned.
13. `writel(1, commit)`. T8140 commit = 0x3082d4000 (DT reg-name `commit`, 4 bytes). T8132 = 0x3882d4000.
14. Mask every AIC line. Release stopped cores into deep WFI. Boot core takes its deep WFI last, looping WFI, AIC ack and IPI_SR clear if an event ends it.

Comments in the source: "No printing, and under 33 ms from the complex words to the WFI (the engine's bound for the cores to go idle). A hang from here ends at the watchdog." [C: the source says "under 33 ms", not "about 33 ms".]

T8132 differs [C]: AMCC plane enables cleared bit by bit in the order 8,0,1,2,3,4,9,5,6,7; the plane stage words are stepped down by clearing bits 0,1,2; MCC lane words are stepped for the first channel. The T8132 commit still runs the DCS step and the SoC perf wait, although its header comment says DCS and perf are left out (see section 4). T8132 leaves out DVFM, CLLT, PTD and AVE because the trace shows macOS does not write them in that window.

T6050 (J714s, J716c) is time-anchored instead (L:j716c/dts-deep-sleep t6050-j716c-sleep-full.dtsi lines 21-27; LI `sleep-t6050.h`). Kind: implemented. Each commit step runs at a DT-given time before a "sleep timer": `apple,commit-runway-us` 48000 and 20 steps (41700 40900 39800 24700 23300 22300 20300 18010 18000 2491 2296 2202 1552 1468 1382 950 730 650 550 500 us). The steps are: MCC release x2, storage PHY park, storage words, watchdogs (WD0 off, WD2 13 s, aux +0x8), memory-floor voter 0, MCC stop, clkgen +0x78000 zero, clock words bit 0 cleared, three PTD drops, three pwrgate rounds (+0x120/+0x128/+0x130 = 0x80000000), perf words 0, AP voter 0, AFR, cluster words (boot 0, others 0x10), complex request at cluster +0xc polled to 0, SIO and clock muxes, tables. The SMC policy (pmVC 0x101 then 42000/35000/10000/60000/58000 us) anchors the timer to the SMC AP-IDLE ack. The schedule and spacings are stated to be the J714s's own measurements "not in any ADT" (header lines 11-14).

T6040 (J616s, `sleep-t6040.c`, L:j6s2r/deep-default 58e1028dcb): the commit is a write of 1 to MasterMini +0x4000 = 0x508904000, "the S2R timer: it arms the SoC sleep engine, and macOS makes exactly this write". Before it: other cores off (PMGR power word ACTUAL=0 polled), PMGR quiesce (ACC APSC disable with BIT7 busy poll, PLL relock bit 42, 8 TVMs disabled), five cluster-ctl words, clkgen mux park, 64 keep-alive enable bits cleared, 13 fabric power words raised to target 0xf with auto. An entry counter at 0x508370970 (bits 31:3) is a read-only discriminator for "engine entered S2R" versus "engine never finished".

### 2.2 What the engine waits on (preconditions)

Each entry gives the source, the symptom, and the kind. The common symptom is a watchdog reset.

**Cores**
- Every core must reach deep WFI after the commit. A core left awake: "the sleep engine waits on the awake core until WD2 resets the SoC" (932de6dc2b, measured with a test switch that made one CPU miss its stop, J700). "A sleep committed with a core that missed its stop doesn't come back at all" (fa4e8a93d6). Measured.
- A secondary that takes its deep WFI at hotplug stops the machine within seconds on T8140. macOS takes it only after the commit (fa4e8a93d6). Measured.
- Boot core power-gate enable. Each CPU cluster has a PMGR word whose top bit (BIT 31) lets its cores power down in WFI. PMGR-started cores come up allowed. The boot CPU was started by the boot ROM and "only follows the word", which iBoot leaves clear (T8140 P cluster; T8132: "iBoot sets E's only"). With it clear "the boot CPU only clock-gates in WFI, and a system sleep's engine, which waits for every core to power down, never starts: measured on a J700, the watchdog reset the machine 5 s into every sleep until this bit was set" (3bd4bd1bf8; `drivers/soc/apple/apple-cluster-pwrgate.c`; early_initcall sets it before secondaries start). Words: T8140 `/arm-io/pmgr` reg[22] E +0x0, P +0x40 (0x300724000, 0x300724040). T8132 reg[34] E +0x0, P +0x60 (0x380724000, 0x380724060). T6050: one word per core at pmgr reg[0]+0x2c000 (J714s core 0 and core 12 left clear by the loader; J716c 0x28062c000 and 0x28062c0c0). Message for J716c: "Without them the boot cluster never powers down, and the sleep never gets past its first sequence" (873fb29b, 4783b9f7). [C: the J714s comment does not mention the 5 s reset.] Measured on three SoCs.
- Cluster ordering (J716c, 438de391). T6050 cluster power-down programs run one at a time on one engine. With all three cluster requests dropped together the P cluster's program queued behind the boot cluster's, which cannot finish while the boot core runs the commit. Fix: at the start of the commit, release clusters 1 and 2's cores to their last WFI, wait up to 2 ms for them to be counted, drop their PTD bit and request, poll each cluster's sequencer (cluster +0x18 = 0x1a, +0x1c = 0x1c01a, 5 ms), boot cluster last. Failure ends at the engine watchdog. [C: the commit message says 5 s; the code arms WD2 at 13 s. Unresolved.] Measured.
- Pending interrupts: a raised AIC line ends the final WFI and "the engine waits for it", so all lines are masked right after the commit (`aic_sleep_mask_all`, 67e70ac476). A timer left running also ends WFI (CNTP/CNTV masked). Implemented.
- WFI-retention note: on T8140/T6050/T8142 a plain WFI can return with registers cleared. Aurora wraps WFI to save x18-x30 and FP state (e994fc36; `idle-apple.S`). Cause unknown; may be the boot chain leaving a non-retentive WFI mode. Measured.

**Coprocessors**
- PMP and SIO: "a commit with the PMP and SIO still running reset the SoC 5.5 s later" (d43118bcb4). Measured. The sleep refuses unless DCP, DCPEXT, PMP and SIO have the ASC RUN bit (CPU_CONTROL +0x44 bit 4) clear or their domain off. [C: GPU is a first-pass stop on T8140, not in the must-stop list.]
- SEP: "a commit with it running never returned" (d43118bcb4). The SEP self-gates after a control message (tag 8, type 0x0c, param 2, answered ~18 ms later); the driver then waits up to 5 s for DEV_DISABLE (f559a3fcfd). Measured.
- Display coprocessors: "the sleep engine waits on DISP_CPU with no timeout", so DCP firmware must be stopped and its CPU/FE/SYS domains lowered first (c922a676a1). Measured/comment.
- AVE complex: macOS has it off already; turning it off at the commit "puts that sequence, with its untimed wait, right before the CPU complexes" (sleep.c comment ~4196-4204). Comment.
- ANS: idled but with its PCIe block/domains not lowered stalls the engine (9d13f7b130, 1cc0c96930). On T6040 the ANS fabric bridge bit 0 (+0x104/+0x108), set by a wake, must be cleared before entry or the second sleep stalls in the engine storage power-down until the AP watchdog resets (05312c21cf). Measured.
- GPU: on T6050 the GPU firmware is stopped by the commit stop; reading its mailboxes while GFX reads "off" under automatic power took a synchronous external abort inside the sleep's last steps (541d9be9). Measured.
- A coprocessor idled for sleep does not come back with power kept; so these stops run after every refusal (f7edd90a82, 4f7e92c1fb). Measured.

**Power domains and words**
- Ten XNU-polled domains: XNU polls them off just before its complex words and panics if on (sleep.c t8140_ps_still_on). The driver lowers any still on and refuses if one will not go. Implemented.
- A domain off with BUSY (bit 11) latched holds the wake's per-switch poll (171 us per switch per the comment; the driver itself uses 1 ms settle and 5 ms) until WD2 resets the SoC. Fix: UNLATCH (bit 12) pulse (sleep.c ~3180-3213; pmgr-pwrstate.c:124-142). [C: the 171 us figure is a comment only.] This is a wake-side stall on T8140.
- T6050 stray domains: AUSS on at the commit: "the machine resets five seconds after the commit; macOS never sleeps with AUSS on" (sleep-t6050.h 2151-2165). VENC0_SYS (PS_MEDIA +0x1c0) reads 0x0f0003ff at the commit, unused but on: "the entry's last phase waits for its power gate" (949b24a8). Lowered at entry, sleep refused if it will not go off. Measured.
- Memory-side words (J716c, dc3fe15c; 8246bb49): iBoot leaves AMCC0-15, AMCC16-31 and AFR/AFC fabric words on with automatic power off. AMCC16-31 read 0x0f0003ff and "a real attempt never got through the sleep engine's entry". Fix: put them under AUTO_ENABLE in `apple,seq-boot` (block 20 words `<0x0 20 0x418 0xf0000ff>` then `0x1f0000ff` pairs [C]). FAB3_SOC (a no-PS fabric word) was lowered by genpd and "never reached 0 (requested 0xf0000f0, read 0x1f0003ff)"; it is marked firmware-owned.
- T6040 DCS: the engine does not write DCS power words. It expects each DCS to gate itself after self-refresh, which needs DCS +0x20 bits 12 and 8 (dynamic power gate) plus the DCS power word in automatic mode. macOS sets both at boot and after each wake. Linux did not, and the engine waited for good on the first DCS pair power gate (16 ps_dcs words applied in each `.begin`). Measured.
- T6040 ATC: the engine writes ATCPHY_CFG +0x2c and waits for AHB clock ack at +0x04 bit 8. It needs three S2R entry writes (+0x2c bit 0, +0x08 bit 0, +0x28 bit 0). A display in DP alt mode on any port stalled it (08c935fbcf). ATC commons must be on at the commit or the engine waits on raising ATC0_COMMON whose parent FAB2_SOC is off. Measured.
- ISP (T8140, 671928ed): resident-firmware domains are syscore devices; `isp_sys` stayed held by the ISP's own runtime-PM link, and the sleep controller found "isp_sys is on: 0x23ff" at the commit. Fix: `dev_pm_genpd_suspend(pd_dev[0])` in `suspend_noirq`. Measured.
- Domains held by a DART's clock protection or by an "awake path" device are not powered down by genpd in noirq (apple,sleep-driver-owned, GENPD_FLAG_ACTIVE_WAKEUP). J713 ATC2_CIO "held on by its DART" is taken down explicitly before the PHY shutdown (1d2639d2). Implemented.

**Memory side**
- DCS and voters: "The engine's first step polls for DCS at this state and has no way to get it there. macOS has every voter at 0 by now, which is how it lands there" (sleep.c `apple_sleep_dcs_down` comment). Implemented/comment. On T8132 macOS's firmware reaches DCS 4 and perf state 3 with no CPU write.
- AMCC error enables: any enabled and pending error "turns the sleep around within 20 ms", so word0 bit 25 (DSID_AGE_OUT) and word1 bit 8 (UNEXP_RT_HIT) are cleared on every plane before every commit. A deep sleep sets them again. Measured (6 of 6 sleeps held with both off; bit 25 alone still bounced). AU independently: "With macOS's platform error handler hidden (as with Linux), an enabled and pending memory-controller error at the commit wakes the SoC within 20 ms" (AU docs/sptm-nv2-virt.md; `AURA_S2R_QUIESCE=24`; `S2R_AMCC_ERR 0x25000`).
- SLC: write-back and invalidate every plane in noirq, allocation off (113be2304f). On T8132 "dirty lines were lost, so resume died at random points" (669e8db10c). Wake-side.

**Wake and SMC/PMU events (bounces, not stalls)**
- A wake source left unmasked: mask words "read all zero until something writes them, which leaves every source enabled". iBoot leaves all enabled and a pending source turns the entry round at once. The driver masks all except `apple,wake-enable`. Refuses a sleep with no wake source enabled ("ends only at the watchdog"). Implemented.
- A latched PMU interrupt in nub-spmi0 status (T6050 0x600 bit 2) "holds the controller's interrupt output up: an AP wake source". Unacknowledged, every sleep after the first RTC alarm woke right after its commit. The SPMI response-vector enable is cleared pre-commit because the wake logic watches that queue's line for the RTC alarm (c8e03faac4). Implemented/measured.
- SMC.OutboxNotEmpty is a wake source: any queued SMC event wakes at once. A debug-link cut after the SMC AP-idle notice "committed and never returned" (d6158d07a0). Measured.

### 2.3 What these sources imply for a SoC that stays up (all inference for M1)

Ranked by how directly the Aurora records match "commit reached, no wake, watchdog resets later". Each lists the reading it suggests.

1. **Boot core or any core not actually power-gating in WFI.** Match is the strongest: 3bd4bd1bf8, 4783b9f7, 873fb29b. M1 differs: M1-M3 take core power-down through CYC_OVRD_EL1 bits 25:24 and WFI (LI `cpuidle-apple.c`; M1N1 `cpu_sleep`), and T8140 has no such register. Whether t8103 has a per-cluster/per-core PMGR WFI power-gate enable word is not stated anywhere. Reading to take: the PMGR CPU block (M1: PMGR +0x54000 = 0x23b754000 by arithmetic from AD smp.md) and whatever per-cluster word macOS sets at boot, for each core, at the macOS commit.
2. **A core, or its cluster program, not idle.** Reading: each core's last write and state at the macOS commit, plus the order across clusters (M1 has E and P clusters).
3. **PMP, SIO, DCP, SEP, ANS, GPU run bits and domains.** Reading: ASC CPU_CONTROL (+0x44) and PMGR words for each coprocessor at the macOS commit. PMP is at 0x23bc00000 on M1.
4. **DCS/SoC perf state and PMC votes.** The user's own lead ("what keeps the DRAM controllers busy at Linux's commit") matches the Aurora comment above. Reading: DCS0-7 words, the SoC perf word, and any voter words at the macOS commit.
5. **Domains left on, BUSY-latched, or in forced instead of automatic mode** (VENC0_SYS 0x0f0003ff pattern, AMCC/AFR auto power, AUSS, isp_sys, ATC commons/USB). Reading: every PMGR power word at the macOS commit against Linux's.
6. **Pending wake or error state at the commit**: AIC line, wake-block mask/status words, PMU/SPMI latch, SMC outbox, AMCC error enables.
7. **Cable and debug link.** The lab's M1 has a Thunderbolt/USB-C cable to the M3. Aurora records the SMC treating the debug link's cold reset as a cable pull (section 3.5), and ATC/AUSS/CIO domains as blockers (section 3.3). INFERENCE only for M1.

Mismatch to keep in mind: Aurora's stalls reset at 5-13 s. The M1 run resets at about 120 s, which is the value the lab's own driver arms (and the Asahi docs' initial WDT value). A 120 s reset therefore says only that no shorter timer fired.

### 2.4 What nobody documents

- The engine's own program, order and timeouts. Aurora infers it from comments ("the engine's bound for the cores to go idle", "the engine waits for X") and from stalls.
- Why a commit-word write starts the engine. No source describes the engine hardware.
- The t8103 AON commit word. See 3.2.

---

## 3. By topic

### 3.1 PMU / power chip (Dialog/SPMI)

**Asahi docs**
- AD `hw/soc/spmi.md` lines 80-82, 118-161 (documented): SPMI master gen1 on M1, gen2 M2, gen3 M3/M4; the page is written from gen3. STATUS +0x00, TX_PUSH +0x04, RX_PULL +0x08, IRQ mask/ack areas, CONFIG1 +0xA0, ACTION1 +0xA4 (bit 0 flushes FIFOs), command word opcode/slave/NOTIFY/PARAM, 64-word FIFOs. "Power state management commands (reset, sleep, shutdown, wakeup)" are simple commands with no PARAM and no data. Opcode numbers are not given and "other commands" is a TODO. [O: bit 27 FAIL is level-triggered; the author "can't find" a way to clear it short of a PMGR reset, not that only a PMGR reset clears it.]
- AD `hw/peripherals/ace3.md` 27-59 (documented): the M3 USB-PD controller supports SPMI sleep/wakeup, sleeps at boot, ACKs but ignores writes while asleep, raises interrupts while asleep. Not the M1 (M1 uses CD3217 over I2C, `hw/soc/usb-pd.md`).
- No Asahi page describes the PMU's registers (0x0201, 0x9f00.., 0xd008, 0xa47b not mentioned).
- AD `hw/soc/memmap.md` 205-340: SPMI at 0x23c280000/0x23c290000/0x23c2a0000 (SOC) and AOP_SPMI 0x24a824000/0x24a828000. The 0x23d0d9300 PMU SPMI is not listed there.
- AD `platform/introduction.md` lines 42, 215-255 (documented): the PMU is an external chip whose firmware is embedded in iBoot1 and started by it; the OS has a small I/O surface to it.

**SPMI command opcodes** (M1N1 `proxyclient/m1n1/hw/spmi.py` 8-30, 78-88; `trace/spmi.py`; implemented): RESET 0x10, SLEEP 0x11, SHUTDOWN 0x12, WAKEUP 0x13, SLAVE_DESC 0x1c, EXT_WRITE 0x00, EXT_READ 0x20, EXT_WRITEL 0x30, EXT_READL 0x38, WRITE 0x40, READ 0x60, ZERO_WRITE 0x80. M1N1 sends SPMI WAKEUP/SHUTDOWN only to the TPS6598x (`src/tps6598x.c` 85, 100). Nothing in the fork sends SLEEP/SHUTDOWN to the PMU. [C]
- Aurora Linux uses SLEEP 0x11 / WAKEUP 0x13 only on USB-C port controllers (SN201202x: `tipd/spmi.c sn201202x_suspend`; LI `sleep.c` HPM code). [C: this half of the original claim was right; "no PMU sleep program" was wrong.]

**What Linux writes to the PMU before the commit** (T8140; `t8140_sleep_match`, `t8140_pmu_write`; implemented):
- WD0/WD1 counts zeroed, then boot-stage register 0xf701 (T8132 and T6050 0xf801) written 0x50 over SPMI (USID 0xe, extended write, command word `(reg<<16)|BIT15|0xe<<8|0x30`, then the data byte), "the PMU's boot stage as macOS leaves it" / "the AP sleeps". The reply notify enable (+0x40 bit 0) is masked around the write and acked (+0x80). [C]
- SPMI NOTIFY_ENABLE words (main SPMI +0x40 and `spmi-a0`) set to 0x2000001 for the sleep, restored on undo.
- No SPMI traffic after the commit (T8140; comment in `sleep.c` near L3501). The RTC alarm is not armed after the commit: "macOS arms it after the commit. rtcwake has armed it long before this, with no SPMI traffic near the engine" (sleep.c 3446-3450).
- T6050: after ANS's stop, boot-stage write (0xf801 = 0x50), then PMU extended reads (J714s `apple,pmu-sleep-reads`: 0xf801 1, 0xf808 4, 0xf802 1, 0xf818 1, 0xf819 2, 0xf800 1, 0xa7dc 4 as address/length pairs), SPMI buses masked in order `<1 0 4 2 3>` (J716c `<1 0 4 2 3 5 6>`) with a 480 us gap, `apple,spmi-runtime-mask 0x3f833ff1` restored at wake, PMU source acknowledge at nub-spmi0 +0x600 bit 2 at entry and every wake, `apple,pmu-wake-stage <0xfe>`, `apple,pmu-alarm-rearm <0x43 0x41>`. The J716c's seven buses add nub-spmi1 and nub-spmi4; the mask 0x2000001 for them is "Unverified ... assumed right" (66fcb224) [C].

**What macOS sends after the commit (traces under Aurora)**
- AU `docs/sptm-nv2-virt.md`, 'What it found for a Linux port' (documented): after the commit, macOS arms the PMU RTC alarm over SPMI (T8140: 0xf80c, 0xf808, 0xf80e, then 0xf800 <- 0x41, "go hib"), then each core takes deep WFI.
- T8132: about 3 ms after the commit, four commands to the PMU on nub-spmi0 slave 0xe: read 0x2000, 4-byte write at 0x2008, 0x200e <- 0, 0x2000 <- 0x41 (commits 5990e777, a216c948; measured).
- AU `src/sptm_virt_s2r.c` comment above `s2r_stop_before_timer` (~577-580, comment): the S2R timer start "is where the hardware takes over: XNU's go hib to the PMU follows it, and the PMU does not wait for the last core". AU never sends 'go hib' itself.
- Linux T8132 replays them: default before the commit (`bringup_wake_early` true, `t8140_sleep_enter` 3568-3571), after the commit with a 3 ms delay when it is false [C]. PR #1314 item 6 (head 04f43c7f): "The T8132 commit no longer adds the PMU commands macOS sends after the commit; sleep and wake work without them". Those lines are for the PR head; the 903277c6 branch still sends them. [Mixed.]
- INFERENCE: 0x41 equals ENABLE (bit 6) plus MONITOR (bit 0) in the Abbey RTC control byte, so 'go hib' may be the alarm arm itself and not a distinct power-down command.

**PMU RTC register maps** (implemented unless stated). No t8103 PMU RTC layout exists in any source.
- Baku (J700): control 0xf800 (arm bit 6), counter 0xf802 (6 bytes, 65536 Hz, >>16 = s), compare 0xf808 (4 bytes), event 0xf80c, mask 0xf80e (bit 0); alarm limited to 3600 s for s2idle, unrestricted for deep sleep ("macOS's own deep-sleep wakes use it", LI `rtc-apple-pmu.c`). Stowe (t8112) uses the same Baku block, offset in 1/32768 s.
- Abbey (T6041/T6050): control 0x2000 (event bit 1, monitor bit 0, enable bit 6), counter 0x2002, compare 0x2008, mask 0x200e.
- Maverick (t6000 M1 Pro/Max): control 0x1401, counter 0x1406, compare 0x140c, event 0x14c0, mask 0x14c2; a second fired latch in control bit 1 so the armed value is 0x41 not 0x43 (rtc/t600x-pmu-alarm-int3 0dd76c9db6).
- Alarm programming order: mask, disarm/ack event (W1C), write compare, arm with monitor, unmask. A stale event raises the wake line as soon as the alarm is armed, so it is acked first.
- Firmware arms the alarm at every boot with the comparator near 2^32-1 seconds (early 2106) (864149fc00) [C: seconds, not days]. The driver disarms or takes over unless due in range.
- T6050 sleep refuses if alarm compare is not at least counter + delay + 2 s ahead (`-ETIME` in the schedule routine, sleep-t6050.h ~2623-2630) [C: `t6050_sleep_check_alarm` returns -EBUSY].
- The alarm is an interrupt (peripheral interrupt 2) through the always-on SPMI controller and AIC. The rtc driver rejects non-s2idle unless a firmware-driven suspend (`apple_pmu_rtc_prepare`); "retained SPMI/AIC power is required" (4fa8b7d8db). J700 measured: alarms 30 and 90 s ahead ended s2idle at 29.8-30.5 s and 90.3 s (50a3d01721).

**t8103 PMU data present in Aurora DT** (LI `t8103.dtsi` 1207-1265; implemented): `nub_spmi` 0x23d0d9300, pmic1 USID 0xf `apple,sera-pmic`; nvmem cells boot_stage 0x9f01, boot_error_count 0x9f02 bits 0-3, panic_count 0x9f02 bits 4-7, boot_error_stage 0x9f03, shutdown_flag 0x9f0f bit 3, **fault_shadow 0xa67b** (16 bytes), socd 0xab00 (0x400), pm_setting 0xd001, rtc_offset 0xd100 (6 bytes). `nub_spmi1` 0x23d0e1300 (simetra PMIC, disabled), primary_spmi_monitor 0x23d0d8e00 IRQ 343. No PMU alarm node for t8103. The lab notes say 0xa47b for the fault shadow, the source says 0xa67b. Verify. `macsmc-reboot.c` consumers: shutdown_flag, boot_stage (0x00 clean, 0x2f iBoot done, 0x30 kernel started), boot_error_count, panic_count, pm_setting (bit 0 no-restore, bit 5 no-power-on-at-connect).

**PMU scratch / failed-boot counter** (M1N1 `hw/pmu.py` 25-40; `src/pmu_counter.c`; implemented): m1n1 writes 0 to byte `info-leg_scrpad`+2 on SPMI PMUs, or register 0x5002/0x4002 on I2C PMUs, because iBoot drops to recovery once the failed-boot count is high. INFERENCE: repeated watchdog resets may raise that count. [C: the C version is generic; T6040-only is the call in `main.c` 314.]

**macsmc-reboot keys** (LI `macsmc-reboot.c` 104-198; documented comment): MBSE actions offw, slpw, rest, off1 (shutdown; PMU bit needed to stay off), susp, phra, panb, pane. 'susp' is listed but nothing writes it. Power off writes off1 atomically then waits 100 ms. Before reboot/poweroff the notifier sets boot_stage 0 and writes PMU shutdown_flag (1 = power off, 0 = restart): "without this the device will just reboot". INFERENCE: the PMU owns the off decision for shutdown. Nothing says it owns the sleep decision.

### 3.2 AON block and wake sources

**Asahi docs**
- AD `hw/soc/memmap.md` (documented): pmgr[1] gates 0x23d280000-0x23d2f4000 (WDT 0x23d2b0000, the 0x23d2bc000 apcie/atc-phy block, aes[1] 0x23d2d0000, aop[3]/admac 0x23d2a8000). pmgr[3] gates 0x23d200000/0x23d240000/0x23d27c000. pmgr[23] gates 0x23d100000-0x23d188000. nub-gpio 0x23d1f0000. No register is named at 0x23d2b8028/40 or 0x23d2c4000. INFERENCE: the 0x23d2xxxxx 'AON' space is a PMGR-gated region that macOS can leave off.

**Aurora T8140/T8132 AON block map** (LI `t8140.dtsi` sleep node ~889-935; implemented): wdt 0x3082b0000, aon-misc 0x3082b8000 (size 0x44; +0x08 AON_AP_DEADLINE, written 0 at WD2 arm), commit 0x3082d4000, wake 0x308004000 (size 0x48), ps 0x300700000, pwrgate 0x300724000, cpu-start 0x300734000, cllt 0x300768000, cluster 0x300780000, ps-aon 0x308280000, spmi 0x308714000, pmc-voters 0x302800000, dcs 0x30005c000, AMCC planes 0x220025000/0x220065000/0x2200a5000/0x2200e5000. T8132 is +0x80000000 on the wdt/aon/commit/spmi bases.
- INFERENCE for M1: wdt 0x23d2b0000 and the progress words 0x23d2b8028/0x23d2b8040 sit at the same +0xb0000/+0xb8000 offsets inside an aon-misc-like block. The commit word on T8140 is the aon_pst block (AON area +0x50000, +0x4000 = 0x3082d4000 per AU `s2r_places`). The same arithmetic on t8103 (pmgr_mini 0x23d280000) would give 0x23d2d4000, and wdt+0x24000 also gives 0x23d2d4000. The lab's S2R timer word is 0x23d2c4000. The two do not agree. The AU place table is M4-class. Check the macOS 13.5 trace.
- AU `s2r_places`/`s2r_timer_only` (implemented): T6050 commit = PMGR reg[11] +0x4000 (J714s 0x288f04000). T6041 commit = master mini-PMGR reg[54] +0x4000 (only on L:ctl/t-6353-t6040-s2r) [C]. T6040 = 0x508904000.
- t8103 side in Aurora DT: `wdt` 0x23d2b0000 (0x4000, IRQ 338), `pmgr_mini` 0x23d280000 (syscon, no children), `pmgr` 0x23b700000 (0x14000). None of 0x23d2c4000, 0x23d2b8028, 0x23d2b8040 is described (LI `t8103.dtsi` 1107-1112, 1276-1344).

**Wake block layout** (T8140/T8132; implemented): +0x00 WAKE_SLP_DDR word (bit 0 is the USB host's DRAM-keep vote); 8 mask words at +0x08+4n (1 = masked); sticky status words at +0x28+4n. Word 7 has 21 sources; the driver writes GENMASK(20,0) there, while macOS reads 0x001fef77 [C]. The driver masks everything except `apple,wake-enable`.
- T8140 list `<131 70 145 165 80 99>`: NUB.SPMI0.SW3 (PMU RTC alarm), ATC0_PMGR_USB_WAKEUP, SMC.CPUWakeupAP, SMC.OutboxNotEmpty (power button, lid, AC, Wi-Fi, Bluetooth), MTP dock channel and outbox. Other names: NUB.APWakeupTime 109, NUB.APWatchdog 110, NUB.GPIO.IRQ6 125, NUB.WakeupAP 140, AOP.AICWakeupAP 0, AOP.CPUWakeupAP 5.
- T8132 `<145 69 161 183 85 104>` (NUB.SPMI0.SW3, ATC0.USBWakeup, SMC.CPUWakeupAP, SMC.OutboxNotEmpty, MTP). T8132 names: 122 NUB.APWakeupTime, 123 PMGR_AON.APWatchdog.
- T6050: 10 AP words at wake +0x0c enable, +0x34 status, plus one GFX-die word (+0x0c enable, +0x10 status); J714s/J716c list `<16 18 28 30 38 39 62 65 69 71 72 73 74 76 122 127 147-154 171 183 290>`, GFX `<1>`. T6040 has 9 mask words (0x508000000 window; status +0x30; a S2R control word at +0x0 cleared on wake) [C].
- T6050 wake-status snapshot is read first at wake and logged as `wake status set: AP <id> <name>`; the messages relabel it "latched status, not proof of cause" (7e634372, e56e48b5). Names are a compiled-in table, not read from the ADT [C].
- A macOS write observed in the AP wake block: zero to the control word at wake base +0x0 at boot and early resume. L:j714s-wake-control0-test b06156ae makes it an opt-in experiment (no result stated).
- Wake after power-off needs an AON/SMC/PMU source. s2idle wake is the AIC alone (3.11).
- PR #2137 (T6050 wake-controller snapshots) and #2135 (T8142 S2R) exist as open PRs and were not read.

### 3.3 PMGR power domains and states

**Asahi docs**: the PMGR register layout, power-state encodings (state 4, bit 28), PS/clock-gate bits and dependencies are not documented under `hw/soc` [C: the sweep did hit spmi.md sleep text, smc.md CLSP, agx.md MCC mapping]. `hw/soc/clocks.md` 10-21 (documented): clock-gates/power-gates index the pmgr node's `devices` array, must generally be on before a device's MMIO works, topology is unknown (SIO and UART_P are needed for UART0); iBoot presets clock-ids. `hw/cpu/smp.md`: PMGR CPU block offset 0x54000 on M1 series.

**PS word layout** (Aurora, M1N1 `pmgr.c` 10-20, U-Boot `apple-pmgr.c` 15-25; implemented): [3:0] TARGET, [7:4] ACTUAL, bit 8 WAS_PWRGATED, bit 9 WAS_CLKGATED, bit 10 DEV_DISABLE, bit 11 BUSY/PARENT_OFF (hardware-owned), bit 12 UNLATCH (reset pulse), [19:16] MIN floor, [27:24] auto state, bit 28 AUTO_ENABLE, bit 31 RESET. 0xf = on, 0x4 = clock-gated (reads as "on" for sleep checks), 0 = power-gated. M1N1 and U-Boot only use the endpoint states.
- Lowering recipe (macOS order, measured values ANS 0x1f0020ff, 0x0f0020ff, 0x0f0023f0): clear AUTO_ENABLE and flags first, then target 0 with flags written; raise = target f then AUTO_ENABLE once ACTUAL is f. Never write DEV_DISABLE on a raise.
- Flags (binding `apple,pmgr-pwrstate.yaml` 116-222): always-on, sleep-retained, sleep-driver-owned, firmware-owned (read only; a write to DISP_CPU raised an SError, 22b90b8d), consumer-switched, retention-workaround, bridge-link (bit 0 of link words cleared before power-off), apple,min-state (0 power-gated, 4 clock-gated, 15 on).
- BUSY is masked from whole-word writes (5079db85); the poll is 100 us and slow domains time out in noirq resume (gfx on M1 Pro) then reach ACTIVE; genpd ignores noirq power-on errors (cd8b4487). [C: M1 Pro gfx claim is not in cd8b4487 or the driver comments.] After a transition fails genpd undoes it except inside the suspend_late/resume_early window.
- T8140 ANE_SYS: after a system sleep a power-on can stop at 0x2b4f (target 0xf, actual 4, bit 11 latched). Only a PS reset while off clears it (a8874062 / PR #1255, later reverted on L:nhang2 9f9a0611; reason not stated). Process-context recovery only; running it in noirq resume hung the Neo (70b1c8bc).
- T8140 resume parent wait: ANE_SYS 0x0b4f (parent fabric not ready); bounded 10 ms wait for bit 11 (93a8fdc3).
- Wake replay: the sleep driver saves every power word and rewrites them in macOS's wake order; macOS's wake record on T8140 shows AUTO_ENABLE gone from 22 domains, 30 lowered within 5 ms of wake (73600d2dd0). The replay can lose floor bits: GFX word 0x1404034f replayed with floor [19:16]=0 until `apple,sleep-ps-min <4>` (L:djdev/t6050-gpu-sleep-ps-floor, merged; the hex value is not in source [C]). SEP's auto-power word is replayed without its ACTUAL field (795d6225).
- t8103 always-on domains in DT (LI `t8103-pmgr.dtsi`): mcc 0x2f8, dcs0-7 ("LPDDR4 interface"), apcie_gp 0x3e8 ("Breaks things if shut down"), atc0/1_pcie, sep 0xc00 ("Locked on"), and AON words 0x58-0xc0 (debug, nub_spmi0 0x60, nub_spmi1 0x68, nub_aon 0x70, msg 0x78, nub_gpio 0x80, nub_fabric 0xa8, nub_sram 0xb0, atc0/1_usb_aon 0x88/0x90). ps_pmp 0x3d8 and ps_pms_sram 0x3e0 are NOT always-on. Source: `docs/alt/boot-process-guide.md` 55-56 (documented): some domains are always-on in the DT "because they break something badly if turned off", and missing power or MCC init in m1n1 could cause "a hard SoC wedge".
- Domains genpd powers off in noirq once all devices in them suspended: Aurora used syscore virtual devices, awake path, and GENPD_FLAG_ACTIVE_WAKEUP to stop this under running firmware (GPU gfx 96d8a4b8; ANS link domains 161d8dcb; SEP needs the GPIO state on dd2a90a2). These record hangs "until the watchdog resets it" on resume (T8140, 30/90 s s2idle). Measured. [C: three of the four cases name the J700 watchdog hang; the SEP case does not.]

**Cluster/CPU PMGR blocks**: AD smp.md block offsets M1 0x54000, M2/M3 0x34000, M2 Pro/Max 0x28000, M3 Pro/Max 0x88000; die stride 0x2000000000. +0x4 system alive mask, +0x8 cluster 0 core start, +0xc cluster 1. M1N1 `smp_stop_cpu` writes the core's bit (BIT(4*cluster+core)) to block +0x0 before `cpu_sleep`, so "the PMGR powers the core off when it enters deep WFI". The same block is the CPU stop register in Aurora's `CPU_START_STOP`.

### 3.4 PMP (power management processor)

**Asahi** (documented): `hw/soc/accelerators.md`: "Power Management Processor?" with the invented-name marker, "handles power functionality" [C: entries have descriptions]. `platform/introduction.md` firmware table calls it "Power Measurement Processor", ~400-920 KB, loaded by iBoot2, started by the OS. Glossary: "Power Management Processor". `memmap.md`: PMP windows pmp[0] 0x23bc00000 (+0x23bc2c000-0x23bc6c000 gated by pmgr[22]), pmp[1] 0x23b850000-0x23ba00000, pmp[N] tags on GPIO (pmp[37]) and 0x23d1xxxxx (pmp[30]/[31]). No protocol, vote or sleep description.

**Aurora PMP protocol**
- RTKit app endpoint 0x20. Messages (M1N1 `fw/pmp.py`; implemented) [C]: Startup 0x00, Configure 0x10 (64 KiB shared region), Init1 0x200/0x201, Init2 0x202/0x203, Unk 0x100/0x110, DevPwr 0x20e / DevPwr_Sync 0x208 / DevPwr_Ack 0x209 (DEV 31:16, STATE 15:0). Linux PM command form: marker bit 53, opcode shift 44, power opcodes 0x0e/0x0f with replies 0x0f/0x10; T8112 device-constraint opcode 0x0f with completion 0x10, domain at shift 40, device 32, level 16; replies untagged. [C]
- Report apertures (T8112): request read 0xa00, request write 0x10500, update 0x10000 (8 bytes/entry), ack 0xa40, status 0x10 (bit 0 = running), range-ready state at 0x80 (entry 8), achieved-state words at 16*entry (0x90, 0xa0). T6000: 0xf80/0x107c0/0x1000. Never read a DVFS request entry back (it can retire the pending update). The T8112 PMP never acknowledges PS request bits 2 and 3 on J413 (71f25e67; measured: 9.3 GB/s memcpy, glmark2 ~1800, 4.45 W idle with PMP on). T8112 is M2, J413 a T8112 board [C]. The constraint command path was later judged not to transport device constraints (95319c93, on r7 only).
- Boot inputs (`Documentation/arch/arm64/apple-pmp.rst`; documented): Linux loads no PMP firmware. The bootloader preserves the resident image, prepares the PMP DART filter, passes BDID, DVID, DCAP, DCHD, PMC_, PMCX, CVAR, PMCV/PMCB. Once ASC RUN is set the firmware "can own fabric, memory and thermal controllers"; a failure is not permission to unbind or clear RUN; recover by reboot. 'running' is retained state. PMP is disabled in default DTs; `APPLE_USE_PMP` is opt-in.
- T6050 PMP registry-v2 stop handshake (L:t6050/pmp 3c25583a5e; implemented): on stop the driver reads save counter 0x7bcc4 and wake counter 0x7bcc0, calls RTKit idle, then requires 0x7bcd8 == 0xcafe4b0b (cold 0xfeed1b00), 0x7bce0 == 0x10024a8, 0x7bcc8 != 0, save counter advanced, wake counter unchanged, then clears RUN. Offsets are T6050. [C: the delta is not required to be one.]
- PMP stop at sleep (T8140; 4f7e92c1fb; measured): 13 mailbox messages. About 61 ms before the commit AP state then IOP state to 0x201 (each acked). About 37 ms after wake HELLO unasked, endpoint map, IOP 0x20, AP 0x20. SRAM 0x3c000-0x98000 (T8140) copied out and back before the run bit (T8132 sram_backup 0x3c000, 0x68000 with __DATA kept, 3eceeaf3; T6050 `apple,sram-keep` <0x58000 0x9b000>; T6041 __DATA 0x500761000, 0x7d000 kept). Requests withdrawn before the stop; the GPU withdraws first. Idle is a point of no return.
- Report sleep/wake hooks (`pmp-report.c apple_pmp_report_sleep/wake`; implemented): withdraw requests except `commit_owned` bits at the commit, set defer, poll the ack up to 50 ms; wake rewrites the request word, re-primes the DVFS range if power was lost, republishes pending words. `apple,release-for-sleep` entries (external display, ~0.25 W in s2idle on J514S) withdraw in noirq. PTD drops at the commit (T6050 `apple,ptd-sleep` <0x1e0 12 13 14 36>); when no PMP runs on J716c the sleep takes the PTD entries itself (4ea82386).
- PMC (T8140; `pmc.c`; implemented): voter agents PMP, CLPC, GFX, AP; per-agent floor words (stride 0x4000) honoured only if the rail's enable bit is set; macOS enables static agents (PMP, CLPC, AP) and dynamic ones (GPU) only while powered. CLPC releases its floor before system sleep (5caea343). T6050: five agents (PMP, CLPC, GFX, AP, PMP1), DCS states 0-6, fabric 0-3.
- PMP memory/fabric votes on T8112: DCS state 0..4 (class 0x21 bits 35:32), fabric 0..2 (class 0x25 bits 51:48); cluster/ANE entries 0xa8/0xa9/0xab, AVD 0xb0 (VMAX floor 2), JPEG 0xb2. With the PMP running, DRAM and fabric stay at idle unless votes raise them (6d9096e6). [C: class 0x21 vs DCS and 0x25 attributions differ between sources.] A sleep that stops the PMP drops the floors; the next vote republishes (43362509).
- No source describes a PMP "SoC state" sleep vote. The nearest is the stop/withdraw handshake above.

### 3.5 SMC

**Asahi** (AD `hw/soc/smc.md`; documented): SMC keys CLSP ("possibly the time the SMC last went to sleep"), CLWK, CLBT, CLKU, MSLD lid, bHLD, MBSe (read-to-clear), gP0d (Wi-Fi/BT chips), PSTR, NTAP notifications (lid, power button, power connect, 64-bit payload). No sleep-entry key.

**Aurora SMC sleep protocol** (T8140, measured; `macsmc.c` 755-880): MBSE='slpw' (sleep warning) before any other coprocessor is told (about 800 ms before the rest); MBSE='slpa' (6 ms), then an RTKit AP-idle notice (AP state 0x201) after all others, then 30 ms quiet; wake: AP-on notice 0x20, read MBSE and MBSW (8-byte wake record), write MBSE='waka'. Between the two notices the SMC takes no commands (-EAGAIN). [C: slpw is written in `.prepare`, slpa in a noirq callback.] MBSW bits: pwrbtn, lid, charger, USB-C plug, USB2_wake, wifibt, acattach/acdetach, rtc (T8140: 0 pwrbtn, 9 ipd_touch, 10 lid, 16 ipd_kbd, 18 charger, 23 wifibt, 40 acattach, 41 acdetach, 42 USB-C_plug, 43 USB2_plug, 44 USB2_wake, 45 aupo, 48 rtc; T8132 differs) [C: no "Neo" label in the source]. MBSW is zero when only the PMU's RTC woke the AP.
- T6050: policy `apple,smc-sleep-policy` and the pmVC key (value 0x101): written after slpw, after ANS's stop, after each USB_AON power-down, before slpa; spacings warning to pmVC 42000, pmVC to SLPA 35000, SLPA to idle 10000, idle to timer 60000, wake to pmVC 58000 (us). "Without it there is no deep sleep" (binding). Saved-context SMC RTKit transport so SMC SRAM and message IDs survive the irreversible stops (30f95ffe, unmerged for J716c). pmVC and SLPA are message names, not SMC keys [C].
- Debug cable (measured): the debug port controller is cold-reset ('Gaid' 0x64696147) and told SSPS S3 (0x53505353) before sleep. The SMC reads the cut as a cable pull and queues events (acattach, acdetach, USB-C_plug) into its outbox; SMC.OutboxNotEmpty then wakes the AP. On J700 with the reset 223 of 223 retained sleeps woke 0.15-0.27 s after the commit with the alarm 10-19 s away, although the outbox had been quiet 500 ms before the AP idle notice; 154 of 154 without the reset ran to their alarm (6de229f824). Fix: warn the SMC only after the cut, with a gap (770 ms as macOS's shortest gap in 6de229f824; later 200 ms in 567a28f1d9). macOS never resets a port controller around a sleep.
- PD controllers: tipd sends SSPS S3 to controllers with `apple,sleep-ssps` about a second before the commit, S0 after. A failed S3 on J714s ended with "the SMC did not answer the sleep notice: a reset instead of a sleep" (tipd `core.c` sleep_s3_refuse comment). SMC port reasons (acattach/acdetach/USB-C_plug) trigger a debug-link-cut wake handler. M1's Type-C controllers are CD3217 over I2C (cd321x); whether `apple,sleep-ssps` exists in an M1 DT is not shown.
- SMC wake path: SMC.OutboxNotEmpty and SMC.CPUWakeupAP are the lid/button/AC/Wi-Fi/Bluetooth wake sources; "nothing in-band can wake the SoC from S2R" (mt7932 `wow.c` header); Wi-Fi uses radio GPIO13 to the SMC wifibt wake (6c752dd6; J700 magic packet woke 2 of 2). A spurious SMC lid-open event ended a J716s suspend ~230 ms after the close (L:diagnostic-t6373 macsmc-input; fixed with a settle time). Measured.
- SMC wake events on s2idle: only IRQF_NO_SUSPEND mailbox interrupts carry lid/power button (a48ca155bf).
- T6050 SMC cells: only macsmc-input and macsmc-hwmon (plus pcIO GPIO); power, reboot, RTC deliberately not instantiated: "Do not instantiate unqualified T6050 power, reboot or RTC functions" (639eea96) [C]. pcIO key (0x7063494f) writes power the radio and a bpli key (0x62706c69) is N1's warm reset.
- Asahi: the "T6050/t8103 SMC" sleep keys are not in any M1 source. The t8103 SMC has the same `apple,t8103-smc` path and guard (`pm_suspend_via_firmware`, macsmc.c:748) [C] but no recorded exercise.

### 3.6 Coprocessors' sleep messages

- **RTKit power states** (LI `rtkit.c` 25-58, 1355-1372, 3107-3340; implemented): OFF 0x00 (cannot restart), SLEEP 0x01 (restartable), IDLE 0x201 (sleeping, retain state), QUIESCED 0x10, ON 0x20, INIT 0x220. Management messages SET_IOP_PWR_STATE 6 (ack 7), SET_AP_PWR_STATE 0xb, IDLE_NOTIFY 0xc. Stop recipe: AP IDLE then IOP IDLE, each acked, wait CPU_STATUS (+0x48) idle and stopped, clear mailbox I2A control bit 0, clear CPU_CONTROL (+0x44) RUN (bit 4) twice reading back. After a stop the firmware restarts only from its reset vector; warm restart keeps the endpoint map; HELLO comes unasked. OSLOG counters must be echoed or later sleeps fail (AP idle refused). [C: 'AP idle notice missing after about eight sleeps' is MTP and SMC; the DCP case is the warm restart.]
- **Who is told what** (measured, T8140): AOP, MTP, SMC get AP-only notices (0x201 before, 0x20 after) and keep running. AOP also stops five AFK endpoints with 0xa4 (answer 0x87), AP idle after, restart with 0xa3 (0x86) (978e9b2409). MTP AP idle 280 ms before the commit, on 73 ms after wake; HID report 0xc1 (087adb4fc3). PMP idle pair ~61 ms, SIO ~64 ms before the commit (SIO loses SRAM, restarts ~300 us after run bit). ANS shutdown CC 0x46c001, CSTS 0x9, then idle and run bit; PCIe block lowered. GPU: GFX then GFX1 idle, mailbox off, run bit 5 us later, PMP request withdrawn. DCP: A484 and A500 sleep steps, sessions closed, DART streams off, GAPF slice released; a firmware stopped for sleep but then refused needs a restart. SEP as in 2.2.
- Non-restartable: post-M4 ANS cannot be restarted once RUN is cleared and a PMGR reset raises an SError (b8aec88e79; U-Boot `nvme_apple.c` 84-96). Pre-M4 ANS can be stopped (nvme_shutdown, RTKit SLEEP, clear RUN). Documented in U-Boot: T8140 MTP is stopped with an RTKit SLEEP at OS entry and restarts from its reset vector (6b418c00ef). ISP firmware cannot be started a second time after CISP_CMD_SUSPEND (026b206e78). Aurora's design for these is to leave them running and keep their domains on.
- ANE (ane/sleep-cycle series; measured): SUSPEND 0x24 never completed on J700/J616s even after EXCLAVE_MODE_STOP 0x31 and SET_SNE_PMU_BASE2 0x29 (the PMGR/PMU aperture base passed to firmware: J700 0x300700000). The shipping path is a cold cycle (power off, cold boot, program replay). [C: the cold path is the default only on `ane/sleep-cycle-14l`.] omarchy-ane's desk study (documented): ANE firmware POWER_DOWN 0x0b ends in WFI forever; macOS polls the ASC idle status (240 ms timeout on M1 Max) then writes 0 to the PS words. INFERENCE: firmware WFI does not remove power; the host's PMGR writes do.
- AD `hw/soc/asc.md` (documented) [O]: CPU_CTRL bit 4 CPU_START, CPU_STATUS bits (IDLE bit 0, STOPPED bit 1 etc.). Mailbox A_CLR bits 1/2 "trigger IRQ/FIQ IPI?" with question marks. RTKit is "not covered here". `platform/introduction.md` 126: iBoot2 "puts some coprocessors to sleep", without detail. `hw/soc/sep.md` 43-46: endpoints 0x10 xars ("involved in startup/shutdown") and 0x14 hibe ("hibernation related"), no messages. SEP "put to sleep before the kernel boots" (introduction.md 151).
- Per-subsystem state lost at a real power-off (measured, T8140): all DARTs (DAPF ranges, GAPF slices; DART TCR/TTBR compare tells whether power was lost, 84bb6582), SART entries 0-7 (rewritten before ANS RUN), AP pins (all 216 reset, macOS restores 212 except 49-51 and 134 after writing 1 at 0xc48, 113 of 212 differed over three sleeps) [C], AIC, PMC enables/floors, USB host core registers, ATC PHY lane banks ("Lane register banks disappear in deep sleep", M1N1 `atc_phy.c`), PCIe PHY PLL/lane tables, QSPI, MCA audio, cpufreq cluster pstate (comes back 2). DART/SART are only relevant to the wake side.

### 3.7 CPU core/cluster power-down and resume

- **M1-M3 core power-down uses CYC_OVRD_EL1** (documented): AD `hw/cpu/system-registers.md` 124-127, 357-385: ACC_OVRD_EL1 (S3_5_C15_C6_0): [14:13] OK To Power Down SRM (3 = deepsleep), [16:15] Disable L2 Flush For ACC Sleep (2), [18:17] OK To Train Down Link (3), [26:25] OK To Power Down CPM (2 deny, 3 deepsleep), [28:27] CPM Wakeup (3 = force), [29] Disable Clock Dtr, [32] Disable PIO On WFI CPU, [34] Enable Deep Sleep. CYC_OVRD_EL1 (S3_5_C15_C5_0): [0] Disable WFI Return, [25:24] OK To Power Down (2 force up, 3 force down), [21:20]/[23:22] FIQ/IRQ mode. ACC_CFG [3:2] BP Sleep. Names are guesses ("Some of these are guesses").
- Register dumps (AD `hw/cpu/system-register-dumps.md` 234-239, 605-613, 374-376; measured) [C]: under m1n1 ACC_CFG 0xd, CYC_OVRD 0x2000000 (bits 25:24 = 2, force up), ACC_OVRD 0x180010102001c207. Under Darwin (version 20.3.0 XNU 7195.81.3) ACC_CFG 0xd, CYC_OVRD 0x0, same ACC_OVRD. Bit 34 is NOT set in that ACC_OVRD value (set bits 0,1,2,9,14,15,16,29,36,44,59,60); m1n1 and Darwin ACC_OVRD are identical at rest.
- M1N1 `cpu_sleep(deep)` for SLEEP_GLOBAL SoCs (A10, A11, M1, M2, M3 only; M4+ SLEEP_NONE) [C] (`src/utils.c` 249-310; `cpu_regs.h` 527-599; implemented): ACC_OVRD read-modify-write sets PWR_DN_SRM=3, DIS_L2_FLUSH_ACC_SLEEP=2, TRAIN_DOWN_LINK=3, POWER_DOWN_CPM=3, DISABLE_PIO_ON_WFI_CPU, DEEP_SLEEP (bit 34), then CYC_OVRD WFI_MODE=3 with DISABLE_WFI_RET "to allow deepest sleep states", then WFI loop. The reg_mask only clears the DIS_L2_FLUSH field first. Non-deep: FIQ_MODE=IRQ_MODE=2. `deep_wfi()` brackets a retention WFI. Chickens set WFI_MODE=2, DISABLE_WFI_RET clear, ACC_CFG BP_SLEEP=3 at boot (`chickens.c` 257-267) [C].
- Under m1n1's stock hypervisor: guest ACC_CFG_EL1 and ACC_OVRD_EL1 writes are skipped (the 'ro' set in `hv/__init__.py` 661-664), and CYC_OVRD writes with DISABLE_WFI_RET or FIQ_MODE are returned to Python, logged, and "Guest is shutting down CPU" calls `hv_exit_cpu` (`hv_exc.c` 324-338; commits 5a4e30a, a75afff). So the stock HV never executes macOS's real core power-down. [C: comment text and handler details.] INFERENCE: the lab's capture code presumably does something different; check.
- Aurora LI cpuidle (`cpuidle-apple.c` 21-215; implemented): CPU PD sets bits 25:24 of s3_5_c15_c5_0, WFI until ISR_EL1 non-zero, clear bit 24, bracket with `cpu_pm_enter/exit`; WFI-only on machines not in `apple_cyc_ovrd_machines` (M1-M3: t8103, t6000-2, t8112, t6020-2, t8122, t6030-2, t6034 [C]). On T8140 CYC_OVRD reads 0 and an MSR raises ESR 0x02000000 (1af04ca4); hardware power-gates idle cores on plain WFI (94-99.9% of 1 kHz PMGR samples; the boot P core never) (measured, J700). A guarded CPU PD opt-in once lost wired reachability and needed a VDM reset (15aa0e41). s2idle on M1 uses these same states.
- **Resume vector** (documented): AD `fw/macho-boot-protocol.md` 79-90 [documented]: iBoot enters with MMU off and x0 = boot_args; it sets and locks the boot CPU's RVBAR to the top of the page containing the entry point; "presumably after a resume from deep sleep, the boot CPU will start executing code here"; secondary RVBARs not locked. `platform/introduction.md` 207: the CPU0 reset vector is locked at a computed offset within the image, so resume needs code there. `sw/m1n1-dev-guide.md` 9-11: the m1n1 image has RVBAR at offset 0, entry at 0x800, "only relevant for resuming from sleep mode" [O: not the only place]. AD `hw/cpu/smp.md` 45-54: RVBAR at cpu-impl-reg +0x00; locked for CPU0 by iBoot, free for others.
- Aurora's contradicting claim: AU `src/smp.c` 37, 393-438, `docs/boot-options.md`: on A7-M3 RVBAR "isn't locked" (so M1), and `smp_point_rvbar_here` writes each running core's RVBAR with aura's vector (18ba01e2, d1301ea7). From M4, iBoot locks every core's RVBAR to the boot object. The sleep driver's header repeats "iBoot locks every core's reset vector". Contradiction; see section 4.
- Aurora's mailbox/boot object (AU `src/smp.c` 473-530; LI `sleep.c` 82-100): `/chosen/aurora,s2r-mailbox` (magic `AURAS2R1`, boot_mpidr, resume_pa, resumes). A secondary returns through its spin-table release address into `secondary_holding_pen`; the boot core takes `cpu_resume` at EL2, MMU off, DAIF masked. Under a different boot chain (m1n1) the analogue is m1n1's resume handling (inference). `__cpu_suspend_exit` restores ACTLR and AMX under `pm_resume_via_firmware()` (b90ca804) [C: suspend.c 90-95, not sleep.S]. Nothing else of the Apple impdef state (CYC_OVRD, ACC_OVRD, HID) is saved or restored in common code.
- Spin table (LI `smp_spin_table.c` 131-448; implemented): non-boot cores park (wfe loop) coherent; `spin_table_hold_parked` (100 ms), `spin_table_stop_parked`, `spin_table_release_stopped`, `spin_table_release_cpus(mask)` (early release, d127243a), `spin_table_stop_finished`, `spin_table_cpus_stuck`; boot CPU cannot be offlined (`cpu != 0`); `cpu_disable` needs power ops. The sleep refuses unless exactly one CPU is online and it is the boot core.
- Start sequence after wake (AD smp.md 45-54; M1N1 `smp.c` 340-372): write RVBAR, set (1<<cpu) in block +0x4, set core bit in block +0x8+4*cluster. Core start addresses lost at power-off.
- T6050 per-core stop: timers masked, S3_4_C15_C10_4 low 2 bits cleared (SIQ), S3_7_C15_C5_0 <- 1, DEEP_SLEEP set, WFI loop (`t6050_cpu_down`). T8140 deep WFI = S3_5_C15_C6_2 bits 0 and 63 (`SYS_APL_DEEP_SLEEP`). Boot core T6050 also sets S3_5_C15_C1_6 bits 28:26 (comment says boot core; code not restricted to it) [C].
- PSCI: none on Apple. AD `platform/feature-support/m1.md` 117-127: cpuidle note: "Some power management functionality on ARM machines is controlled via the PSCI interface"; Asahi's cpuidle is a hacked WFI/WFE driver "never upstreamable" [O]. M1N1 j873 emulates PSCI for Windows guests (`hv_psci.c`): CPU_ON/OFF/SUSPEND; power-down states "not supported, pending an understanding of how to trigger this power state"; SYSTEM_OFF = reboot; cpu_sleep(true) commented out in suspend [documented/implemented]. MU DSDT comments: "suspend to ram not implemented yet"; a staged PSCI retention state 0x11 has "never run on hardware".
- T8140/T6040 per-cluster notes: T6050 boot core power-gate words (see 2.2). t8132 `cpu_p_first_bit` 6.

### 3.8 DRAM / MCC / DCS

- Aurora's OS-side step-down is in 2.1 (SoC perf state 3, voters 0, DCS 4 via 6, MCC enables and lanes, AMCC error enables, AMCC planes and stage words). The engine does the self-refresh itself; no explicit self-refresh register write exists in any source (inference from absence).
- DRAM-kept vs deep wake (measured, T8140): wake word 0 bit 0 (`WAKE_SLP_DDR`) is a USB-host vote that keeps DRAM, MCC and the host's always-on side powered ("SLP_DDR"). After a Linux boot an SLP_DDR wake stalls in the engine and the watchdog resets about 5 s after the alarm; after one deep sleep five SLP_DDR sleeps each returned 0.4 s after the alarm (6d31ecef). Only the deep path runs C2S and turns AP_TMM (0x1a0) on, so the driver clears the vote until the first deep wake. AOP crash (60425f5f) and camera use (93b53f4d, 6 of 6 vs 70 of 70 without) also stalled the next SLP_DDR wake. "Which boot-time state the deep sleep rebuilds isn't known yet." [C: AOP crash text is in 60425f5f.] The wake stall is not an entry stall.
- Cache: apple-mcc stops SLC allocation and writes back every plane before a deep sleep (113be230); T8132 left allocation off (669e8db10c). T8112 PMP start changes DCS DRAM configuration per channel (offsets 0xdc4/0xdbc, stride 0x40000, resource 2; `restore_dram_config`) and can re-establish MCC cache mode; cache-mode restore commits were reverted (62d644c1 and others, reason not stated) [C].
- DCS floors in s2idle (measured, t6000/t600x): `apple-pmgr-misc` suspend_noirq lowers the fabric (and DCS where no PMP) p-state. "Lowering DCS under PMP leaves s2idle unable to resume"; the fabric alone is safe and saves about 0.35 W on t6000 (2.62 W to 2.27 W at 5 V input) (e9d616b9). M1 Pro: "every M1 Pro suspend we have logged ran at DCS 7" and the first suspend with a 7.2 DT that set DCS 1 hung the machine (919904e81a) [C: the 7.2 tree dropped the property; the default moved DCS to 1]. `apple-pmgr-misc.c` is in Aurora trees but matches only t6000/t602x, not t8103.
- t8103 DT: mcc node 0x200100000 disabled; dcs0-7 always-on (`t8103-pmgr.dtsi`; `t8103-peripherals.dtsi` 5-10).

### 3.9 Clocks

- AD `hw/soc/clocks.md` only (3.3). Aurora's commit sequence parks clocks: three clock-mux words with 0x80100000 (T8140; T8132 four muxes 0x10/0x14/0x00/0x04), clkgen +0x78000 zeroed and clock words bit 0 cleared (T6050), 26 `entry-clk-words` and 7 `entry-perf-words` (J714s). 'The SoC refuses the first mux write, on macOS too.' Purpose of the pwrgate page write (0x80000000, "reads back this value already") is "unknown", CLLT is "names from nothing", the two DVFM/CLLT orderings were never hooked in one run (sleep.c 121-122, 3558-3568, 3641-3645) [C].
- The ISP and display have their own clock-protection slices (GAPF block at 0x2803f0000 on T6050; live 0x12, off 0x2; the PIPE clock gate on the USB4 tunnel producer).

### 3.10 Watchdog

- AD `hw/soc/wdt.md` (documented): block at 0x23d2b0000; 24 MHz 32-bit counter +0x10, compare +0x14 (initially 120 s), control +0x1c bit 0x04. Disable by writing 0, enable by writing 4. Maximum just under three minutes. First macho (m1n1) is booted with the WDT enabled. Banks +0x0/+0x4/+0xc and +0x20/+0x24/+0x2c "seem to work like" the main set but reboot into recovery mode. The page says nothing about the WDT across sleep.
- Linux `apple_wdt.c` 21-135 (implemented): WD0 (+0x00 CUR, +0x04 BITE, +0x08 BARK, +0x0c CTRL) resets to recovery; WD1 (+0x10, +0x14, +0x1c) and WD2 (+0x20, +0x24, +0x2c) cause a normal reset. CTRL bits IRQ_EN 0, IRQ_STATUS 1 (W1C), RESET_EN 2. The driver uses WD1 only. Restart: RESET_EN, BITE 0, CUR 0, wait 150 ms ("up to ~120-125 ms until the SoC is actually reset"). Suspend stops it, resume restarts it. Compatibles `apple,t8103-wdt`, `apple,wdt`. [Contradicts AD on +0x20 bank; section 4.]
- M1N1 `wdt.c` 8-84 (implemented): `wdt_disable` CTL 0 (and secondary word at reg[2] when wdt-version 2 or 3), `wdt_reboot` ALARM 0x100000, COUNT 0, CTL 4, `wdt_arm_seconds` (T8140/T6040 only, max 178 s). m1n1 hypervisor boot-args `wdt=-1` in the examples (AD `sw/m1n1-hypervisor.md` 124-230) [O: what wdt=-1 does is not stated]. Systemd reboot watchdog set to 2 min for the 178 s limit (AA `90-aurora-reboot-watchdog.conf`).
- Aurora sleep (implemented): WD2 (+0x20 count, +0x28 alarm, +0x2c ctl, 24 MHz) is the safety net. ctl 0, count 0, alarm secs*24e6, ctl 1. 5 s at the commit (ADT `simple-reconfig-wdog-icc-time`, a comment; the driver hard-codes 5), 13 s on T6050, 30 s default on T6040, 120 s over device suspend and resume, cleared at `.end`. WD0 control cleared at the commit (not at the match step) and WD0/WD1 counts zeroed in the match step [C]. Aux watchdog +0x8 cleared. T8132's resume stub (MMU off) rewrites WD2 for 60 s before `cpu_resume` [C].
- macOS arms a ~5 s reconfig watchdog (WD2) during sleep entry and stops it last on wake (AU docs). AU console silence from the first core's self-disable to wake so output does not delay the boot core past it [C: output resumes after WD2 stops].
- T8142 "hibernation watchdog", "secure watchdog" (`hib_exclave_watchdog` 0x5d82b0000) are disabled bindings with no behaviour. 'NUB.APWatchdog' and 'PMGR_AON.APWatchdog' are wake-source names.
- An SMC AP watchdog is separate: a T6040 wake that sat in a DockChannel write reset about a minute later (a1db45bc). [Documented in a commit message.]

### 3.11 s2idle versus s2r

- Asahi: `platform/feature-support/m1.md` line 41 (documented): Suspend/sleep = "linux-asahi" for T8103 and T600x, m2.md and m3.md the same. [C: the M1 legend reads "(mostly) stable and available for use in Fedora Asahi Remix"; "not upstream" is inference.] M4-M6 are "TBA". The table does not say s2idle versus deep. `sw/kernel-config.md` 82-83: CONFIG_SUSPEND=y, HIBERNATION not set, CPU idle, PMGR_PWRSTATE, SPMI_APPLE, MFD_APPLE_SPMI_PMU, APPLE_SMC, POWER_RESET_MACSMC, RTC_DRV_MACSMC, APPLE_WATCHDOG, WATCHDOG_HANDLE_BOOT_ENABLED; no Apple s2r driver option. INFERENCE: the Asahi cell most plausibly means s2idle. `project/faq.md` 94-97: Wake on LAN does not work; WoWLAN untested; no reason or state given.
- Aurora (implemented/documented): AIC commit a48ca155bf (also d1319d0d on unified/7.2.11): "suspend-to-idle is the only system sleep state on these SoCs. The AIC stays powered in it and delivers unmasked interrupts to the CPUs idling in WFI as usual, so there is no wake logic to program." `IRQCHIP_SKIP_SET_WAKE` on aic_chip and aic2_chip; before it only IRQF_NO_SUSPEND mailbox interrupts woke. [C: no separate AIC3 chip.] DockChannel, PCIe MSI and xHCI got wake flags. Many drivers refuse non-s2idle (`rtc-apple-pmu`, pcie-apple adopt_link and managed radios, apple-dart live MTP, rtkit-helper adopted MTP, mt7932 hibernation) [C: details differ per driver]. The PCI T8140 doc: "Hibernation, deeper suspend and kexec are refused while admission or retained DMA ownership is active."
- s2idle leaves AIC, SPMI, PMGR domains (unless genpd gates them in noirq), the SLC, DARTs and coprocessors as they are. Only `pm_suspend_via_firmware()` paths save/restore. On M1 the CPU PD cpuidle state is the deepest s2idle state; T8140 copies WFI over the PD slot so the generic s2idle selector reaches `tick_freeze()` (43e5c465fe; Neo 3 x 20 s RTC sleeps accounted 20.198/19.808/20.419 s). `PM_SUSPEND_MEM` on Aurora kernels maps to s2idle unless the sleep driver binds.
- The Aurora sleep driver registers platform ops (`suspend_valid_only_mem`) and "Deep becomes the default sleep state, unless mem_sleep_default= chose another"; binds only where match data was measured: T8140, T8132, T6050 (and J716c) (LI `Kconfig:103-118`, `sleep.c:5797-5800`) [C: three entries, not two]. Everything else "the driver doesn't bind, and s2idle stays the only system sleep". No t8103 entry (the only t8103 string in sleep.c is a PMGR lookup at line 4290). The boot object must publish `aurora,s2r-mailbox`.
- Packaging: FA/AA/NA say "This policy does not add a deep-sleep provider. The consolidated Linux sleep provider currently matches T8140 only; M5 experimental sleep is separate." They set `SuspendState=mem` with no fallback and order suspend after `aurora-sep` (the kernel refuses deep sleep until `apple_sep` is bound). FA changelogs: 7.3.0-34 "MacBook Neo (T8140): suspend-to-RAM at EL2 with the DRAM-kept wake (#1445, carries #1208-#1443)"; 7.3.0-36 faster DRAM-kept wake with PHY set up again after a deep sleep (#1658), AVE complex as parent of the encoders (#1663) [C] so "the first wake from S2R no longer resets the Mac" with encoder 0 enabled; 7.3.0-37 "M4 Air (J713): suspend-to-RAM (#1314) with the CIO default (#1855)", G17 refuses a sleep its commit cannot stop (#1839). No M1 S2R claim anywhere in these changelogs. omarchy-mac-pkgs: Suspend and resume "works" on M1/M2, wake by lid or power button only, keyboard and trackpad not wake sources; BCM Wi-Fi/Bluetooth can wedge across s2idle.
- Hibernation: `tools/aurora-sep/HIBERNATION.md`: Aurora has no supported hibernation on Apple silicon; spin-table CPUs have no `cpu_die`; one s2idle cycle (J413) recorded [O]. hibernate.c refuses `apple,arm-platform`.

### 3.12 Measured power

All "measured" per commit message. No suspend-to-RAM power exists for M1.

- T8140 J700 deep sleep (PR #1208): SMC charge counter on battery averaged 11.3 mA (0.049 W at 4.375 V) over a 300 s sleep including entry and wake; about 8.6 mA asleep from a four-sleep fit. macOS under aura on the same counter: 0.109 W. Entry 0.25 s median, wake to "PM: suspend exit" 1.02 s median (test kernels).
- s2idle: J514S (T6030) 2.69 W to 1.60 W when the panel hardware is stopped and PMP floors withdrawn; idle with panel off ~5.9 W to ~4.3 W (2faa6ef0). t6000 s2idle 2.62 W to 2.27 W (fabric p-state, e9d616b9); an ACIO-teardown option saves 1.3 W of 4.0 W (2.7 W) (5637681a). A held external-display PMP request costs about 0.25 W.
- Idle (not sleep): M1 MacBookPro17,1 (j293) SMC Total System Power 3536 mW stock, 3529 mW at GPU base pstate 6; 1 request/s ~7.6 W; saturated ~17.3 W (omarchy-mlx `docs/gpu-base-pstate.md`; rail not separately metered). J316s P clusters at 3036 MHz 6-48% of the time; 3.29 W to 2.98 W with `sched_util_clamp_min_rt_default` 0 (6b72af7a8c). J716s/J714s WFI instead of spin idle 16.4 W to 9.8 W and 15.3 W to 5.6 W (c6224a20). J413 with PMP on: 4.45 W idle.
- ANE autosuspend: suspended equals module removed within 33 mW on T8103 (ae4f177).

### 3.13 Prior suspend attempts and how far they got

- **t8103/M1**: none found in any source. Aurora J313 (M1 Air): s2idle worked with a Touch ID capture fixed (05abcba5, "tested on a J313: it suspended with a verify waiting for a finger and woke on a key press"); a capture that polled the sensor over SPI during suspend stopped the wake before the fix. M1 j293 Thunderbolt: router sleep request leaves the link failing exactly 40.8 s after "PM: suspend entry" in ten cycles on four kernels (0b53a3cc); `QUIRK_NO_SYSTEM_SLEEP` fixes it for s2idle; "the initiating xHCI resume fault remains unresolved" (3524c924). This is s2idle with SoC on.
- **t6000 (M1 Pro)**: s2idle hangs from a DCS floor write; MCA register restore hung the J316 at the first s2idle cycle with a speaker PCM held open (94bc74b0, WIP, cause stated as writing a powered-down MCA, inference).
- **T8112 (M2)**: PMP work only; s2idle "never entered" because ANE restart counted seven domains instead of eight (b68a64cf11, measured).
- **T8140 (J700)**: complete. "Sleep holds, the RTC wakes it, and resume completes" (d43118bcb4). PR #1208: 30 of 30 deep sleeps over two boots; 16 of 16 battery suspends; wakes from RTC, power button, internal keyboard and trackpad, USB keyboard, Bluetooth keyboard, lid, Wi-Fi magic packet [the list is spread over cad6fce0, 6c752dd6, 1864a509, bc9540d8 [C]]. Failures recorded: SLP_DDR wake stalls (5 s reset), debug-link wakes (223/223), DART restore into an off VENC0 domain reset the SoC at wake (263989e0; 21 of 21 with DARTs disabled), about one sleep in 25 lost the debug-link PD contract.
- **T8132 (J713 Air)**: PR #1314: 8 plain `systemctl suspend` sleeps (40 s, 3 min) each woken by its RTC alarm; 22 earlier sleeps; 37 attempts and 35 wakes (two refused). Needed SLC allocation off and radio workarounds earlier. Dock/Thunderbolt series: one real deep sleep with RTC wake on a CalDigit TS5 (first version only). [C: the "radio PRs" do not carry the 'tested by Claude' sentence.]
- **T6040 (J616s)**: real S2R end to end, wake with all 14 CPUs; six suspends with radio WAKE# armed; `a1db45bc`: the wake's DockChannel write reset the SoC about a minute later via the SMC AP watchdog until fixed.
- **T6050 (J714s)**: wakes reached; early-wake unresolved. PR #2073 validation correction: runs returned 22-23 s before the alarm; a 24-cycle run held about 0-1 s; 30 s, 5 min and 30 min holds pending [O: "SoC powers down at the commit" is the compilers' reading]. Dock PR #2057: 8 deep sleeps and 2 refused all trained in place (0 of 10 before). Dell hub SuperSpeed missing in 12 of 41 wakes. J716c: before dc3fe15c "a real attempt never got through the entry"; before 4783b9f7 reset 5 s after the commit; before d404515d the P cluster program queued behind the boot cluster; the tip enables the full sleep (no completed cycle reported in these commit messages) [C].
- **Other**: aura macOS-under-hypervisor traces on T8140, T8132, T6050 (J714s 26A428). No Aurora record of a SoC that was powered down but "did not complete" with nothing wrong in the domain state; every recorded failure was a precondition.
- ANE SUSPEND/cold-cycle (J700, J616s) is coprocessor-level only (section 3.6).

---

## 4. Contradictions between sources, and sources contradicting themselves

1. **Watchdog banks.** AD `wdt.md`: banks +0x0 and +0x20 both reboot into recovery mode (the page says they "seem to work like" the main one). LI `apple_wdt.c` 21-52: WD0 resets to recovery, WD1 and WD2 do a normal machine reset. Aurora arms WD2 for the sleep net, so on Aurora's reading a WD2 timeout is a normal reset.
2. **RVBAR on M1.** AD `macho-boot-protocol.md` 79-90 and `smp.md`: iBoot sets and locks the boot CPU's RVBAR. AU `smp.c` 37 and `boot-options.md`: on A7-M3 (so M1) RVBAR is not locked, and aura rewrites each core's RVBAR. The Linux sleep driver comment says iBoot locks every core's reset vector (true for M4+ per AU). Not reconcilable from these sources; the M1 case needs a reading.
3. **S2R timer word address.** LI/AU M4-class layout implies commit = AON area +0x50000 +0x4000 (0x23d2d4000 by arithmetic on `pmgr_mini` 0x23d280000, also wdt +0x24000). The lab's S2R timer word is 0x23d2c4000. No source covers t8103.
3a. **Fault shadow address.** `t8103.dtsi` lists 0xa67b; the lab's notes say 0xa47b. Verify.
4. **PMP name.** AD `accelerators.md` writes "Power Management Processor?" (a flagged invention); `platform/introduction.md` says "Power Measurement Processor"; the glossary says "Power Management Processor".
5. **Aura's 'go hib' versus Linux.** AU comment: XNU's go-hib PMU command follows the commit and "the PMU does not wait for the last core". Linux T8140 sends no SPMI after the commit and the RTC is armed long before; the T8132 driver moved the post-commit commands before the commit by default and PR #1314 drops them. macOS's order and what Linux needs differ.
6. **Boot-core stall time.** 873fb29b / 438de391 messages say the engine watchdog resets "five seconds after the commit". The T6050 code arms WD2 at 13 s (`T6050_WDT_COMMIT_SECS`). Not resolved.
7. **T8132 DCS.** `t8132_last_mile` header comment says DCS and the SoC perf word are left out (macOS firmware reaches them with no CPU write). `t8132_sleep_commit` calls `t8140_sleep_dcs_down` and the perf-wait anyway.
8. **AMCC on T8132.** Summaries say T8132's AMCC error enables are "left out". The code clears AMCC plane enables bit by bit (bits 8,0,1,2,3,4,9,5,6,7) and stage words, which are different bits from T8140's bits 25 and 8 (sleep.c 3189-3212, 3697-3712).
9. **J716c inheritance.** t6050-j716c-sleep.dtsi header says no J714s commit schedule, clock programming, MCC stop masks or SMC timings are inherited and the profile "must be qualified". Later commits (e7c9be1c, 894d9d36) take "the J714s's SoC data as it is".
10. **ACIO links.** An earlier commit said ACIO links remain trained across sleep; 3c5d350b retracts it ("Replace the inaccurate claim...").
11. **Router sleep.** 0b53a3cc/5637681a: asking routers to sleep starts a 40.8 s failure on M1/t6000; on T6050 the router sleeps in place by design (691d249a, d2fde906). Different chips and modes.
12. **PMP stop versus never clear RUN.** `apple-pmp.rst`: do not clear RUN or unbind a failed PMP; T8140 sleep stops the PMP and clears RUN at the commit. Context differs (failure recovery versus sanctioned stop).
13. **Suspend/sleep status.** AD feature tables say "linux-asahi" (available) for M1; Aurora's driver and packaging say deep sleep matches T8140 only. Consistent only if the Asahi cell means s2idle (inference).
14. **Deep-sleep register on newer SoCs.** M1N1 cpu_sleep uses ACC_OVRD and CYC_OVRD; Aurora's T8140 comment says "This is not CYC_OVRD, which is undefined on this SoC" and AU `macho-boot-object.md` says CYC_OVRD is undefined from M4 on. A consistent split by chip; the M1 side is untested here.
15. **Asahi `cpuidle` note versus register docs.** The cpuidle note says the Asahi idle driver only does WFI/WFE and doesn't mention CYC_OVRD; AD `system-registers.md` documents CYC_OVRD/ACC_OVRD; Aurora's cpuidle for M1-M3 writes CYC_OVRD. Not a contradiction in fact, but the Asahi note understates the idle driver as Aurora has it.
16. **Aurora PMU RTC claims.** The rtc driver says no off-domain wake claim (s2idle with retained SPMI/AIC) while the integration table comment says macOS's deep-sleep wakes use the comparator.

---

## 5. Gaps, and what was not read

**What the sources do not cover (relevant to this lab)**
- Any t8103 sleep data: engine, PMGR power-gate words, commit word, PMU sleep program, cluster ordering. No source has an M1 trace.
- The hardware sleep engine itself: its steps, timeouts, and bounds beyond the 33 ms comment.
- Which t8103 PMGR words correspond to Aurora's cluster power-gate enable, the cluster complex words (E/P/AVE), CLLT, PTD, DVFM, clk-mux, CPM pwrgate, voters and DCS dynamic-gate bits. Aurora's own comments call several "purpose unknown".
- A macOS record of M1 (13.5) between the last core's write and power-down: nothing, not even under aura (stop mode halts before the commit; go mode is silent from the first self-disable).
- The M1 PMU's sleep program, alarm (0xd008), and scratch map. The only M1 PMU data is the t8103.dtsi nvmem layout.
- SMC sleep keys for t8103, and whether `slpw/slpa` apply to M1.
- PMP "SoC state" votes.
- Measured s2r power for any chip other than T8140; no M1 s2idle power.
- The Asahi docs' meaning of "Suspend/sleep: linux-asahi" (s2idle versus deep).

**Not read or read only in part**
- Asahi: only the docs repo @e8bcfea; no asahilinux.org page fetched; no linux-asahi code, issues or blog posts; `agx.md` and `serial-debug.md` read selectively; `memmap.md` probe list read around PMGR/AON/PMP/SMC/SPMI; `docs/hw/soc` pages for pmgr do not exist.
- Aurora Linux: of 754 branches, about 200 were read from the triage list (the groups cited above); the rest were not read. Large driver patches (DCP, mt7932, g17 Rust, thunderbolt, DART) were read through commit messages. The API compare lists omit patches past ~300 files. The full `drivers/soc/apple/sleep.c`, `sleep-t6050.h`, `sleep-t6050-tables.h`, `sleep-v27-late.inc` and KUnit tests were not read end to end. t8132.dtsi and the j714s sleep DT were read selectively. Merge-commit messages mostly not read. PR threads and review comments not read (except bodies of #1208, #1314, #1152, #1378-1384, #1414-1420, #2046, #2057, #2066, #2073, #1217, #1266, #1374, #1398, #1437, #1443); #2135 and #2137 not read.
- AU: only sleep-related source and docs; `docs/j616s-bringup.md` and `j616s-driver-contracts.md` searched by term. The three J700 S2R docs named in the task do not exist on any of 75 branches; a full-history pickaxe for deletions was abandoned.
- M1N1: keyword grep over all 38 non-main branches; j873's 1647-line `hv_psci.c` read in the init, state, CPU_OFF, suspend, reset paths only.
- Others: mu, omarchy-mac-pkgs, aurora-installer, speakerguardd, omarchy-ane, omarchy-mlx, u-boot, FA/AA/NA read only for sleep content. No other Aurora repository was opened.
- Unverified: every "measured" item above is a commit-message claim. No logs (including aura's `wakerec-20261105-154137Z`) were available. The GitHub API quota ran out during parts of verification; findings where verifiers could not confirm are marked above. Branch heads move; hashes quoted are as read.
- M1 transfer: every M1 statement above that is not from `t8103.dtsi`, `t8103-pmgr.dtsi`, an AD page, `cpuidle-apple.c` (M1-M3 CYC_OVRD) or an M1 hardware commit is inference.

---

## Completeness check (added after the document was written)

A separate critic agent read this document against the sources. Its points, most important first;
the document text above was not changed for them:

1. Fault shadow: Aurora's `t8103.dtsi:1245` names `fault-shadow@a67b`; the lab's own ADT reading
   (`docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, Observation round 4) puts the
   fault shadow at `0xa47b`-`0xa47e` and records `0xa67b` as changing at each read. The lab's
   reading of the ADT is the observation; Aurora's DT cell is probably a different register.
   (`docs/hardware/m1-air-j313.md:69` repeats `0xa67b`.)
2. The commit word: the formula from Aurora's M4-class table gives `0x23d2d4000` on t8103; the
   macOS 13.5 captures show macOS writing `0x23d2c4000` (spec R24). The captures are the
   observation; the formula is an inference from another chip.
3. Section 2.3's first reading (boot-core power-gate enable) rests on one developer's
   measurements on J700 (commits 3bd4bd1bf8, 4783b9f7, 873fb29b); no source says whether t8103
   has that per-cluster power-manager word. It ranks first by match to the symptom, not by
   evidence about the M1.
4. No source shows how the lab's own hypervisor handles the cores' final writes at the commit.
5. Asahi pages `hw/soc/aop.md`, `aic.md`, `apcie.md` were not read line by line (a grep found
   nothing on sleep); `serial-debug.md` and `usb-debug.md` were skimmed.
6. Of the smaller Aurora repositories, `aurora-diag` and `aurora-sep-userspace` have hits worth
   one read for the ordering of the Secure Enclave before suspend; the others had none or only
   packaging.
7. About 550 of the 754 Aurora Linux branches were not opened (triage judged them not relevant);
   the three J700 S2R documents named in the 2026-11-06 survey were not found; `aura` branch
   `auractl/selftrace` is not reported here. The count of three match-table entries comes from a
   later API tip than the local clone (which shows two).

Coverage counts: 808 items triaged, 207 high-relevance Linux branches read, 45 readers, 806
findings, 785 kept after verification, 21 dropped as not found at their citation.
