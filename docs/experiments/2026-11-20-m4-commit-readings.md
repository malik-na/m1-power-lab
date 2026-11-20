# What do the cluster words and the wake block read at Linux's commit? (milestone 4, readings)

```
Question      At core 0's last write: the P and E cluster words 0x23b718004/000, the wake masks
              0x23d004008-018 and any unmasked pending status 0x23d00401c-02c.
Known         P 0x10 at once, 0x50 50 ms later; E nonzero (k 156) [2026-11-20-m2-p-cluster-50ms.md;
              m2-commit-aon-compare.md]. macOS's cluster words at its commit: not read (it writes
              both 0 in R22; 0 at the wake) [spec 2022, 3739-3749]. Wake masks and status at
              Linux's commit: not read [aurora-sleep-driver.md, Open]. AMCC enables at the commit:
              already clear [2026-11-20-m1-masks-amcc.md], not read again.
Prior art     As the cards named.
Outcomes      Reads only. k 173 bits 21-26 the cluster states; bit 14 masks = macOS's (m1fix bit 0
              writes them, so expected set); bit 13 an unmasked wake source pending (would end the
              sleep at once if the engine ran: compare 0x0201). Raw: k 179-183.
Tell apart    The k value in the record.
Not covered   macOS's cluster values at its commit: no capture has them; a hypervisor reading
              would be needed.
Safety        Reads only, in run 1 (see 2026-11-20-m4-deep-wfi.md).
Budget        No extra run.
Result        (after the run)
```
