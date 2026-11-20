# Are BUSY-latched power-state words left at Linux's commit, and does unlatching them let sequence 0 start? (milestone 4, item 3)

```
Question      Just before R22 (the logic's first write of 0 to 0x23b718000), does any power-state
              word read BUSY (bit 11) with request and state 0 and stay so for 1 ms; with Aurora's
              unlatch (sleep.c 3180-3213, 1f38ff8f4) done, does sequence 0 start?
Known         Aurora: "A domain that went off with BUSY latched holds that poll until WD2 resets the
              SoC" (T8140's list of 41 polled words). t8103's polled list is not named; the probe
              scans every ADT pmgr power-state word (var/map-20261117/adt/pmgr-devices.json).
              Bit 11 was read set only while macOS waited for a turn-on [power-domains.md].
              A stuck poll in the always-on program would end in watchdog 2's 5 s reset; no clean-
              room run has ended so [watchdogs.md].
Prior art     Aurora sleep.c 3180-3213, 3460-3480 (the place: after lower_io, before the last mile).
Outcomes      A  0x0201 04 -> 01 or a 5-7 s reset -> batch positive: halve.
              B  04 -> 04, ~165 s, k 173 bits 0-7 = 0 -> no latched word at Linux's commit: the
                 condition is met already; ruled out.
              C  04 -> 04, ~165 s, latched words found and unlatched (bits 8-11 = 0) -> unlatching
                 does not start sequence 0 (with the rest of the batch).
              D  no record / other time -> inconclusive.
Tell apart    k 173 bits 0-11 (k 177/178 the first word), 0x0201, the reset time.
Not covered   Words outside the ADT list; latches arising after R22.
Safety        Probe kernel probe/m4-batch (boot once, m1-bootonce), safety-checked by a second
              agent before run 1; claim taken; watchdog 1 held at 120 s through /dev/watchdog0 from
              before any trigger (m3run.sh idle mode), apple_wdt unbound by start.sh, wdt=150
              armed in begin and at the commit point; the M1 comes back on stock by the watchdog.
              Nothing needs Naeem.
Budget        Shares milestone 4's build (2 at most) and run 1 (4 runs at most); 1 agent writes the
              probe, 1 checks it.
Result        (after the run)
```
