# Aurora Silicon prior art for sleep and wake

Aurora has a working suspend-to-RAM driver for other Apple chips and a t8103 `pmp` protocol module; nothing of theirs sleeps an M1.
2026-11-20. Aurora is a partner: its code may be used as it is or modified (lab `ef280da`). `tools/prior-art.sh <word>` finds more.

## Established

**Kernel sleep driver**: `~/Work/aurora-ref/linux-integration` (branch `integration/aurora`, `1f38ff8f4`, 2026-11-17), `drivers/soc/apple/sleep.c` (5,816 lines).
- Matches `apple,t8140-sleep`, `apple,t8132-sleep`, `apple,t6050-sleep`; no t8103. [sleep.c 5798-5800]
- "Only SoCs measured and tested that way are matched": elsewhere s2idle stays the only sleep. [sleep.c 24-27]
- Method: replay macOS's last 14 ms in macOS's order, measured under aura's hypervisor (the lab's method). [sleep.c 21-25]
- s2r mailbox: does nothing unless the boot object publishes `/chosen/aurora,s2r-mailbox`. [sleep.c 10-19]
- Mailbox layout `magic` "AURAS2R1", `boot_mpidr`, `resume_pa`, `resumes`; must match aura's struct. [sleep.c 92-100]
- `resume_pa` is written just before the commit; the boot core takes `cpu_resume` from it at EL2, MMU off. [sleep.c 18, 3486-3487]
- `resumes` before and after are compared and logged ("back from sleep, boot object resumes"). [sleep.c 3780, 4543-4544]
- Refuses unless one CPU is online and it is the mailbox's `boot_mpidr`. [sleep.c 2315-2318]
- Refuses with no wake source enabled ("the sleep ends only at the watchdog"). [sleep.c 2327-2334]
- Masks every wake source but `apple,wake-enable`: "These words read all zero until something writes them, which leaves every source enabled". [sleep.c 2276-2291]
- Clears AMCC error enables (word0 bit 25, word1 bit 8) before every commit: a pending enabled error "turns the sleep around within 20 ms". [sleep.c 231-244, 3560-3571]
- Zeroes the PMC voter agents, then waits for DCS state 4: "The engine's first step polls for DCS at this state". [sleep.c 3390-3403]
- "under 33 ms from the complex words to the WFI (the engine's bound for the cores to go idle)". [sleep.c 3443-3445]
- Every core writes `SYS_APL_DEEP_SLEEP` (s3_5_c15_c6_2) bits 0, 63 before its last WFI: T8140 only. [sleep.c 333-337, 1617-1620]
- The RTC alarm is left to `rtcwake`, armed long before the commit (macOS arms it after). [sleep.c 3448-3450]

**aura** (`~/Work/aurora-ref/aura.git`, branch `main`, `03d120dc`):
- `docs/boot-options.md` "Sleep and CPU power-off for an OS at EL2": the 32-byte s2r mailbox; boot core jumps to `resume_pa` with MMU off. [boot-options.md 35-55]
- Same file: "On A7 to M3 RVBAR isn't locked, so nothing is published". [boot-options.md 54]
- `src/smp.c`: the mailbox (`smp_s2r_publish`), and `smp_s2r_return_to_os` takes `resume_pa` on the boot core and counts `resumes`. [smp.c 460-530]
- `src/kboot.c` `dt_set_s2r_mailbox`: publishes the mailbox, or `aurora,s2r-unavailable` with the reason. [kboot.c 690-722]
- `docs/pmp-boot-data.md`: stage 2 copies the ADT's PMP inputs on T6000 and T8112 only; "after ASC RUN, failure recovery requires a reboot". [pmp-boot-data.md 1-27]
- `docs/m1-m3-handoff-sources.md`: source and licence record of an m1n1 handoff series (T6031 display/PMP facts, T6030 SIO records); no sleep content. [that file, lines 1-30]
- `src/sptm_virt_s2r*.c`, `src/s2r_dcp_pkt.c`: s2r support for the SPTM virtualisation path; not read for this card. [aura `main` tree]

**m1n1** (`~/Work/aurora-ref/m1n1.git`, branch `aurora-wip`, `cd714cd2`):
- `proxyclient/m1n1/fw/pmp.py`: the t8103 (v1) protocol: Startup, Configure (64 KiB region), Init1, Init2, DevPwr `0x20e`. [fw/pmp.py 9-66]
- Its set-up: whole `energy_model_dram_configs` at +`0x2000`, reg 3+ mapped at IOVAs packed from `0xc0000000`, table at +`0xe000`. macOS uses its own IOVAs and bytes `0x80`-`0xff` only. [fw/pmp.py 89-111; R76]
- `proxyclient/experiments/pmp_init.py`: the v2 protocol (IOVA table, Malloc, Advertise); exits on t8103: "you have a pmp v1, this script is for v2 only". [pmp_init.py 256-257]
- `proxyclient/hv/trace_pmp.py`: hypervisor tracer for the v2 messages and `CPU_CONTROL` writes. [trace_pmp.py 14-120]
- `proxyclient/tools/pmp_assist.py`: reads `/arm-io/pmp/iop-pmp-nub` `ptd-range` from an ADT. [pmp_assist.py 1-20]

**Lab's reference**: `docs/reference/asahi-aurora-sleep-deep-dive.md` (2026-11-18, reference not observation). [its status line]
- Section 2.2 lists what the engine waits on; 2.3 ranks them for the M1 (inference); 3.4 PMP; 3.6 coprocessors; 3.13 earlier attempts. [its headings]
- Spec 4.4a sets 2.2's conditions C1-C17 against M1 readings; C10, C11, C14 have no Linux reading. [spec 4.4a]

## Decided

- Aurora code is reference for the observation and spec stages; it may be used as it is or modified; stages stay separate. [lab `ef280da`; AGENTS.md]

## Open

- Is RVBAR locked on this M1 (aura says not on A7-M3; the lab's hypervisor notes say a wake enters m1n1 at its locked RVBAR)? Settled by reading a core's RVBAR register from the proxy. [boot-options.md 54; handoff-2026-11-19 "Next step"]
- The AP wake-source masks `0x23d004008`-`018` under Linux before the commit. Settled by one read in the entry. [spec 4.1c, R63; sleep.c 2276-2291]
- Which t8103 words are AMCC error enables and PMC voters. Settled by naming them from the ADT and reading them at both commits. [spec 4.4a C10, C11]

## Read more
- `linux-integration/drivers/soc/apple/sleep.c` lines 1-33 (header), 2276-2340 (masks, refusals), 3390-3460 (DCS, commit).
- `aura.git` `main:docs/boot-options.md` lines 35-55.
- `m1n1.git` `aurora-wip:proxyclient/m1n1/fw/pmp.py` lines 80-146.
- `docs/reference/asahi-aurora-sleep-deep-dive.md` sections 2.2 and 2.3.
- Spec `docs/spec/macos-13.5-sleep-wake-observed.md` 4.4a (lines 3203-3285).
