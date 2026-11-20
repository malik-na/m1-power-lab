# Does masking every AIC line again after the commit write let sequence 0 start? (milestone 4, item 5)

```
Question      Aurora masks every AIC line right after its commit write (sleep.c 3493-3496;
              irq-apple-aic.c 454-470, 1f38ff8f4). With the 28 MASK_SET words written 0xffffffff
              again right after R38's third 0x23d2c4000 write, does sequence 0 start?
Known         R36 (logic/aic.rs quiesce) already sets all 28 mask words and the 11 block masks,
              before R37; nothing in the logic unmasks after it (probe tree logic/aic.rs). So this
              repeats a mask already set: expected to change nothing (inference).
Prior art     Aurora as above.
Outcomes      A  0x0201 04 -> 01 or a 5-7 s reset -> batch positive: halve.
              B  04 -> 04, ~165 s, k 173 bit 27 set -> ruled out with the batch.
              C  bit 27 clear -> the step did not run; inconclusive for this item.
Tell apart    k 173 bit 27, 0x0201, the reset time.
Not covered   AIC events already latched before R36 (item 2's ack covers those on core 0).
Safety        Probe kernel probe/m4-batch (boot once, m1-bootonce), safety-checked by a second
              agent before run 1; claim taken; watchdog 1 held at 120 s through /dev/watchdog0 from
              before any trigger (m3run.sh idle mode), apple_wdt unbound by start.sh, wdt=150
              armed in begin and at the commit point; the M1 comes back on stock by the watchdog.
              Nothing needs Naeem.
Budget        Shares milestone 4's build (2 at most) and run 1 (4 runs at most); 1 agent writes the
              probe, 1 checks it.
Result        (after the run)
```
