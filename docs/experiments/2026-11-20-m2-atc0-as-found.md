# Does sequence 0 start when the first USB-C port's always-on domains are left as found? (milestone 2)

```
Question      If the entry's R54 leaves ATC0_USB_AON 0x23d280088, ATC0_USB 0x23d280098 and
              ATC0_COMMON as it finds them (on, 0x2ff, with the Thunderbolt cable in), does sequence
              0 start after the commit?
Known         Readings: at Linux's commit both words differ from macOS's 0xff [run 3 of this
              milestone, k 144 bits 15, 17; docs/experiments/2026-11-20-m2-commit-aon-compare.md].
              Linux awake / before an entry: 0x2ff [spec 4.2a line 2880; var/commit-state/
              linux-ds14-bare-ps-words.json]. macOS under the hypervisor: requests them off from boot
              but they read on (0xff) until after core 0's trapped final write [spec 2159-2165,
              2927-2935]; macOS bare metal with the port in use: not observed.
              Code reading (allowed tree): the clean-room R54 requests all three off at the entry's
              start, before R22 [~/Work/dsk-probe-m1-leads drivers/soc/apple/deepsleep/logic/lib.rs
              346-352; logic/pmgr/domains.rs 571-573].
              Old driver: no reading of these words at its commit exists. That they were on there is
              an inference: the old runs' evidence lists only atc0_common among the domains it turned
              off (runs 37-41 `mac_off`) and runs 27b/32/36 without it
              [docs/evidence/2026-11-16-run36-38-restart/README.md 36-38]; nothing says it wrote the
              always-on words. Source: lab evidence files only; the off-limits trees were not opened.
Prior art     Aurora T6050 reference: a USB-side domain on at the commit reset the machine 5 s later
              (the opposite direction) [spec C9 "Why a candidate", reference 2.2].
Outcomes      A  0x0201 04 -> 01 or a 5-7 s reset -> the port's domains being off at the trigger
                 stops sequence 0; build lane next.
              B  04 -> 04, 165 s, k 144 bits 15/17 clear -> words now as macOS's, not enough.
              C  bits 15/17 still set -> the switch did not take; inconclusive.
              D  wakes or powers down by itself -> stop, tell Naeem at once.
Tell apart    0x0201; the reset time; k 144 bits 15, 17.
Not covered   The port's other domains; the cable-out case.
Safety        m1fix bit 3, off by default: fewer writes than now (R54 skips three words). wdt=150,
              boot-once.
Budget        Shares the cache card's build; 1 run (and 1 with both switches if both are B/C).
Result        B. Run 6, 2026-11-20 04:19:28 (probe/m2-cache e1442a487, m1fix=8, m1aop=0,
              probe_k=144): k 144 = 0xf0028c00, bits 15/17 still set (the words differ from 0xff
              because left on they read 0x2ff, not because the switch failed: run 7); stock kernel
              04:22:14 = 166 s; 0x0201 04 -> 04. Run 7, 04:23:49, all three together (m1fix=24:
              this switch and the L1 clean; m1aop=3: the AOP's full sequence), probe_k=161: k 161 =
              ATC0_USB_AON = 0x2ff (on, as found); stock kernel 04:26:34 = 165 s; 0x0201 04 -> 04.
              Neither the port's domains on at the trigger, nor these together with the L1 clean and
              the AOP's sequence, start sequence 0.
              Raw: var/milestone2/run6-*.txt, run7-*.txt, runs.tsv.
```
