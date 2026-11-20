# Does the live USB-C link hold the debug domains active at Linux's commit? (milestone 4, item 1)

```
Question      Aurora cuts a live USB-C debug link before its commit (HPM cold reset, then SSPS S3,
              sleep.c 2528-2650, 1f38ff8f4) because it "holds the debug domains active, which macOS
              has idle". With the Thunderbolt cable in, are t8103's debug domains active at Linux's
              commit, and does the cable matter?
Known         Aurora cuts only if ps-aon "debug_switch" (T8140 +0xb0) reads a nonzero state
              (sleep.c 2597-2601, 2620). t8103's ADT has no debug_switch; its ps-aon words DEBUG
              0x23d280058, DEBUG_USB 0x23d2800b8, DEBUG_AUTH 0x23d2800c0 read 0x2ff, 0x1000030f,
              0x1000030f at Linux's commit with the cable in, each equal to macOS's at its commit
              (DEBUG_USB/AUTH state 0, idle) [2026-11-20-m2-commit-aon-compare.md; probe.rs
              AON_WORDS; pmgr-devices.json]. So Aurora's own test would not cut here (inference:
              DEBUG_USB as t8103's counterpart of debug_switch). The M1 sources power to the M3 on
              port 0 over the cable [memory m1-thunderbolt-direct-access]. The old driver's cable-
              out runs (2026-11-07/08) never reached macOS's commit conditions.
Prior art     Aurora as above; tools/prior-art.sh hpm: nothing of ours.
Outcomes      A  run 1: k 173 bit 15 clear (k 184 state 0) -> debug domains idle as macOS's with
                 the cable in: Aurora's condition is met, no cut is called for.
              B  bit 15 set -> the link holds DEBUG_USB on: the cut (or the cable out) is the next
                 run, by Naeem's pick.
              Cable out (only by Naeem's pick: he pulls it after a delayed start, or the software
              cut if the safety check calls it safe for the M3): 0x0201 01 -> the cable is the
              gate; 04 -> ruled out.
Tell apart    k 173 bit 15 / k 184; for a cable-out run 0x0201 and the reset time.
Not covered   Anything the cable holds other than the debug domains (port 0 sourcing power).
Safety        Run 1 reads only for this item. A cable-out run needs Naeem's hands or a software
              cut judged safe for the M3; the run would be driven over Tailscale (m1ts).
Budget        Reads in run 1; a cable-out run would be one of the 4.
Result        (after the run)
```
