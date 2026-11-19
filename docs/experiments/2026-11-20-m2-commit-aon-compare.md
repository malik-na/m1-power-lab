# Which always-on words differ from macOS's at Linux's commit? (milestone 2, lead 1)

```
Question      Just before core 0's final write (cores 1-7 down), which of 24 always-on words read
              differently from macOS's value at its commit?
Known         macOS at the commit: 0x23d2c4000 0, 0x23d2b8028 0x1000000, 0x23d2b8040 0x20, WD2
              bite 0x7270e00 control 4, 0x23d0d9378 0 [spec 4.1c, lines 2684-2700];
              AOP cfg 0x23d2c0000-3c: 0 except +0x10 0x880ff04, +0x14 7, +0x18 1, +0x1c 0xff0
              [var/commit-state/macos135-det8-real-commit.json, det11 the same];
              ps-aon 0x23d280058-c0 [macos135-det9-awake-vs-commit-new.tsv]. Linux: the AOP cfg
              words equal macOS's awake and at the entry's start (ds13, live-wide); MSG, ATC1_USB_AON,
              ATC1_USB on (0x2ff) at the entry's start where macOS has them off (ds14 prepare; C9
              turns them off when on). Linux at the commit: never read (ds10-ds12 lost the snapshot).
Prior art     None for Linux at the commit; the macOS side as above.
Outcomes      A  mask 0 (bits 0-23)          -> these always-on words are as macOS's at the commit;
                 lead 1 is out for them.
              B  some bits set               -> each set bit names a word that differs; its raw
                 value is k 146+bit in a later run if needed.
              C  not captured (bit 31 clear) -> inconclusive.
Tell apart    k 144's bits 0-23 (layout in the probe branch notes).
Not covered   Words outside the 24; AOP SRAM; values after core 0's final write.
Safety        Reads only, core 0, at the sampler's place; same kernel and run as the AOP card.
Budget        Shares the AOP card's build and its first run.
Result        B. Run 3 (see the AOP card): k=144 bits 0-23 = 0x028c00: bits 10, 11 (0x23b718000,
              0x23b718004 nonzero), 15 (ATC0_USB_AON 0x23d280088 != 0xff), 17 (ATC0_USB
              0x23d280098 != 0xff). Equal to macOS's: 0x23d2c4000 0, 0x23d2b8028 0x1000000,
              0x23d2b8040 0x20, WD2 bite 0x7270e00 and control 4, AOP cfg 0x23d2c0000-3c (all 16),
              0x23d0d9378 0, MSG, NUB_GPIO, ATC1_USB_AON, ATC1_USB, NUB_SPMI/AON/FABRIC and the
              0x23d2800b0-c0, 060/068 words. Caveat for bits 10-11: macOS's value at its commit was
              never read (it writes both 0 in R22; 0x23b718004 reads 0 at the wake) [spec 2022,
              3739-3749]; raw values: k 156/157.
```
