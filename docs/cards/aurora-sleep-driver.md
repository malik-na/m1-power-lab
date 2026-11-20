# Card: Aurora's sleep driver, condition by condition, on t8103

What each condition Aurora Silicon's kernel sleep driver (T8140/T8132) enforces would need on the M1, with the t8103 address where one can be named.
Reference, not an observation: "sleep.c N" = `~/Work/aurora-ref/linux-integration` `1f38ff8f4` `drivers/soc/apple/sleep.c` line N. 2026-11-20. Derivations: side-session notes `aurora-sleep-driver-notes.md`.

## Established: the address map (Aurora's reg-names, T8140 -> t8103)
- Aurora's DT takes them from the ADT: pmgr reg[21], [22], [24]+0x4000, [27], [28], [31]+0x4000, wdt reg[0], pmgr reg[29], reg[4] = ps .. wake [t8140.dtsi 893-935].
- wake `0x308004000` -> `0x23d004000` = t8103 ADT `/arm-io/pmgr` reg[4], the same index [t8140.dtsi 894-898; var/map-20261117/adt/things.json].
- ps `0x300700000` -> `0x23b700000`; ps-aon `0x308280000` -> `0x23d280000` (ADT pmgr reg[0], reg[1]) [things.json].
- wdt `0x3082b0000` -> `0x23d2b0000`; aon-misc `0x3082b8000` -> `0x23d2b8000` (ADT `/arm-io/wdt` regs) [things.json; watchdogs.md].
- commit `0x3082d4000` -> `0x23d2c4000` ("Starting S2R timer") [R24; var/notes/aura-wake-reentry-2026-11-07.md 110].
- cpu-start `0x300734000` -> `0x23b754000` [m1n1-mb2-breadcrumb src/smp.c 19 `CPU_START_OFF_T8103`; R11].
- cluster +0x0/+0x4 (0 at commit, 0xf at wake) -> `0x23b718000`/`004`, same writes [sleep.c 3545-3546, 3795; R22; R30].
- pwrgate `0x300724000` -> `0x23b71c000`: wake pair +0x000/+0x040 and CPM pair (T8140 +0x060/+0x068) = t8103 +0x080/+0x088, all written `0x80000000` as macOS does [sleep.c 3526-3539, 3802; R67].
- clk-mux parked `0x80100000` = R18's five muxes `0x23b040140`.. ; mcc enables bit by bit (+0x584) = `0x200200584`+n x `0x40000` [sleep.c 3362-3373, 5554; spec 1985; R18].
- dvfm-e/-p `0x210e70000`/`0x211e70000`: the same addresses are in t8103's pmgr reg list; words not checked [things.json].
- Not named on t8103: pmc-voters, pmc-dcp, ptd, cllt, cluster-dcs, spmi-a0 [notes, map table].

## 1. Wake block: masks and status
- Aurora: every word all ones, last word `wake_last_word`, then unmasks `apple,wake-enable`; refuses with none enabled [sleep.c 2276-2292, 2327-2334, 2369-2381].
- T8140: masks +0x08, status +0x28, 8 words, last word GENMASK(20,0); enable `<131 70 145 165 80 99>`, 131 = NUB.SPMI0.SW3 "the PMU's RTC alarm" [sleep.c 5556-5558, 5601; t8140.dtsi 940-947].
- t8103: 5 words, masks `0x23d004008`-`018`, status `0x23d00401c`-`02c`, 1 = masked, valid `ffffffff` x4 + `0x03ffffff` (154 sources): t8103's `wake_last_word` = GENMASK(25,0) (inference) [var/s2r-static/SEQUENCE.md 275-291].
- macOS's masks `f3ffafff ffb97eff fffdeffe ffffffff 03ffff87` enable exactly the ADT's 16 `ap-wake-sources` (decoded) [R63; docs/evidence/2026-11-06-mac27-hv/ap-wake-sources-j313.txt].
- Source 54 = word 1 bit 22 = `NUB.SPMI0Sw3IRQ`: status `0x23d004020` = `0x400000` on the alarm wake and on the space-bar wake [spec 3288-3300; R33].
- Aurora's rule by name on t8103 (54, 133 ATC0.USB, 76 + 81 SMC; no MTP): `ffffffff ffbfffff fffdefff ffffffff 03ffffdf` (computed, not run) [notes].
- macOS writes the masks at boot (`initAON`) and at every restore; none in any logged entry [SEQUENCE.md 288; R63].
- The clean-room logic writes none (R63's test) [spec 6353].
- Linux awake: `0 / 0x40 / 0 / 0 / 0`: 153 of 154 sources enabled, source 38 (unnamed) masked [run25-20261115-163933.txt 379-383 (dry=1); run22-20261116-061738.txt 356-360].
- At Linux's commit and at a Linux wake: not read.

## 2. AMCC error enables
- Aurora: per plane clear word0 bit 25 (DSID age-out) and word1 bit 8 (unexpected RT hit) last before the commit; an enabled pending error "turns the sleep around within 20 ms" [sleep.c 232-244, 3564-3572].
- aura: word = ADT mcc reg[amcc-reg-idx] + `0x25000` + plane<<18 + word x 8; macOS's error handler makes these writes [aura src/sptm_virt_s2r.c 76-83; sptm_virt_s2r_soc.c 283-291].
- t8103: word0 = P+`0x21000`, word1 = P+`0x21008`, P = `0x200000000` + n x `0x40000`, n = 0-3 (by layout and bits; inference) [spec 1990-1992; ADT `/arm-io/mcc` reg[1]].
- macOS's error handler zeroes both whole words in the entry (R17) and writes `0xfffffc3f` / `0x700` at the wake: bit 25 and bit 8 set [R17; R31].
- Linux awake: planes 0-2 word0 `0xffedfc3d`, word1 `0x700`: both bits set; plane 3 not checked [run25a-20261114-075631.txt 67-98].
- The clean-room entry does R17, so the condition is met in it (inference); values at Linux's commit: not read [sleep-entry.md R17].

## 3. PMC voters and DCS state
- Aurora: 4 voter words (stride `0x4000`) to 0, wait 5 ms for DCS [11:8] = 4, else write 6 then 4; SoC perf word to 3 first [sleep.c 215-224, 3389-3416, 3518-3523].
- T8140 dcs `0x30005c000`, clk-perf `0x300058000` -> t8103 `0x23b05c000`, `0x23b058000`, the C3 words (same offset from clkgen; macOS's values say perf 3, DCS 4) [t8140.dtsi 920, 928; c3-words.md].
- Readings: macOS awake and at commit `0x333/0x444/0x222`; Linux no `pmp` `0x444/0x666/0x333` (DCS at Aurora's step state 6); ds28/ds29 commit `0x333/0x444/0x222` [c3-words.md].
- Linux's write of them hung (ds20); Aurora zeroes the voters before any write [c3-words.md; sleep.c 3400-3402].
- PMC voters on t8103: unknown; aura's rule (PMGR's only 16 MiB entry + `0x800000`) does not apply: t8103's pmgr lists 16 such entries [aura sptm_virt_s2r_soc.c 270-279; things.json].

## 4. Power-gate records `0x23b71c090`, `0x23b71c360`
- Aurora never reads or polls a record bit 30 (no `BIT(30)` in sleep.c); it writes the CPM pair `0x80000000` and display pairs (T8140 +0xc8c = 3, +0xcd0 = 0) [sleep.c 2440-2446, 3526-3539].
- Its nearest check: PS words the wake polls, left BUSY-latched, are unlatched; such a word "holds that poll until WD2 resets the SoC" [sleep.c 3180-3213].
- t8103: the records are pwrgate +0x090 and +0x360; which Aurora word they match: unknown [power-domains.md 43-46].

## 5. RVBAR (boot CPU)
- Register `0x210050000` (cpu0 `cpu-impl-reg`), bit 0 lock, bits 47:12 address [breadcrumb src/smp.c 30-31; var/notes/resume-design-2026-11-07.md 77].
- Read under the hypervisor: `0x10000804828001`, `0x10000805ccc001`, `0x1000080578c001`: locked to the m1n1 image base (bit 52 also set, meaning unknown) [resume-design 79, 138; docs/evidence/2026-11-06-mac27-hv/README.md 145].
- So "On A7 to M3 RVBAR isn't locked" does not hold on this M1 under that chain [aura docs/boot-options.md 54].
- From Linux: never read (no row in `var/hwdb/m1-hw.db`; the faults were ACC `0x210e00000`, `0x211e00000`) [hwdb read_fault].
- Method: `mrd-stream` (`/dev/mem`, one read of the given width) via `tools/regmap/scan.sh` [tools/regmap/mrd-stream.c; scan.sh 1-10].
- Command: `tools/tb/m1-claim take rvbar "cpu0 RVBAR" && printf '0x210050000 8 # cpu0 RVBAR\n' > var/regmap/lists/rvbar-cpu0.list && M1TB_VIA=m1ts tools/regmap/scan.sh var/regmap/lists/rvbar-cpu0.list rvbar-cpu0; tools/tb/m1-claim release rvbar`.
- Safety: m1n1 reads it at EL2 at every boot; from Linux: unknown [breadcrumb src/smp.c 776-781].

## 6. Done by Aurora before its commit, absent from sleep-entry.md (most likely to matter first; ranking is judgment)
- Wake masks set: ours leave 153 sources enabled; status at a Linux wake never read [item 1].
- BUSY-latched PS words the wake polls are unlatched; t8103's list of them: not named [sleep.c 3180-3213].
- A live USB-C debug link is cut (HPM cold reset, then SSPS S3): it "holds the debug domains active, which macOS has idle"; ours runs with the cable in: not read [sleep.c 2528-2560, 2603-2650].
- Boot core's last WFI: timers masked, every event acked at the AIC and the WFI retaken; our glue after core 0's final write: not read [sleep.c 1622-1628, 3418-3430].
- AIC masked right after the commit write; ours masks in R36, before R37 [sleep.c 3493-3496; R36].
- WD2 5 s and AON_AP_DEADLINE (`aon-misc`+0x08 = `0x23d2b8008`) = 0 from the AP; on t8103 the always-on side arms WD2 [sleep.c 3335-3340; R62].
- `SYS_APL_DEEP_SLEEP` bits 0, 63: t8103's counterpart is R43's `ACC_OVRD_EL1`/`CYC_OVRD_EL1` writes (inference) [sleep.c 336-337, 1617-1620; R43].
- RTC alarm left to `rtcwake` "with no SPMI traffic near the engine"; ours sends R38's SPMI alarm after the commit write, as macOS [sleep.c 3449-3450; R38].

## Read on the M1, milestone 1 (2026-11-20)
- Wake masks set to macOS's values before the entry (read back f3ffafff ffb97eff fffdeffe ffffffff 03ffff87, 16 sources unmasked), no wake status pending at the commit: the always-on program still does not start sequence 0 (0x0201 04 -> 04, reset at the watchdog-1 time) [docs/experiments/2026-11-20-m1-masks-amcc.md, run 3].
- AMCC word0 bit 25 and word1 bit 8, planes 0-3: already clear at Linux's commit, before any fix (R17 zeroes them) [same card, summary bits 4-5].
- Gate records at Linux's commit: `0x23b71c090` bit 30 clear, `0x23b71c360` bit 30 set, as at macOS's commit [same card, bits 2-3; power-domains.md 46].
- DCS: the C3 words reach `0x333/0x444/0x222` at the commit (state 4) [c3-words.md; evidence ds28]. PMC voters: no t8103 word named, not read.
- cpu0 RVBAR read from Linux: `0x00100008025dc001`, locked (bit 0) to `0x8025dc000`, the loader's reserved image [var/regmap/scan-rvbar-cpu0/reads.txt, 2026-11-20 02:29].
- First `0x23d2c4000` write to core 0's last power-down write: 1.65 ms (39,566 ticks); Aurora's bound is 33 ms [docs/experiments/2026-11-20-m1-commit-timing.md, run 4].

## Read on the M1, milestone 4 (2026-11-20, 4 runs, each `0x0201` 04 -> 04, back at 165 s)
- All on together, with cand `0xffffe`, the SEP gated (`xart_guard=0`), m1fix 11 (macOS's wake masks, AMCC clear, ATC0 as found): Aurora's last WFI on every core (timers masked, IPI_SR cleared, retaken), core 0's AIC event ack, PS unlatch before R22, `0x23d2b8008` = 0 before R22, every AIC line masked again after R38's third write: no sequence 0 [docs/experiments/2026-11-20-m4-*.md; var/milestone4/runs.tsv].
- Core 0 at its last write: no FIQ, IRQ, firing timer or IPI pending (k 173 bits 16-20) [run 1].
- No power-state word of the 137 ADT words BUSY-latched just before R22 [run 1, k 173 bits 0-11].
- DEBUG_USB `0x23d2800b8` state 0 at the commit with the cable in, as macOS's: Aurora's link cut (it cuts only an active debug switch) would not run here [run 1, bit 15; 2026-11-20-m4-debug-link.md]. No cable-out run made.
- Wake sources: one bit pending and unmasked at core 0's last write in run 1, none in run 4 with the same switches, none at the commit-point step in run 3: no source both unmasked and pending in runs 3-4 (C14 met), still no sequence 0 [2026-11-20-m4-pending-wake-source.md].
- Not built: PMC voters (no t8103 word named). Not read: `0x23d2b8008` before the write (k 174).

## Open
- Wake status at a Linux wake (none has happened). `0x23d2b8008` at Linux's commit before any write. A cable-out run with the clean-room entry.
