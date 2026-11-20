# PMC voter words to 0 before the commit (milestone 4, item 6): not buildable

```
Question      Aurora zeroes 4 PMC voter words (stride 0x4000) before its DCS wait (sleep.c 215-224,
              3389-3416, 1f38ff8f4). Does doing so on t8103 let sequence 0 start?
Known         No t8103 voter word is named: aura's rule (the PMGR's only 16 MiB entry + 0x800000)
              does not apply, t8103's pmgr lists 16 such entries [aurora-sleep-driver.md section 3].
              The goal of the voters, DCS state 4, is reached already: the C3 words read
              0x333/0x444/0x222 at Linux's commit, as macOS's [c3-words.md; ds28].
Prior art     Aurora sleep.c as above; aura sptm_virt_s2r_soc.c 270-279.
Outcomes      None: no run. Writing unnamed PMGR words to 0 is not a probe whose outcome can be
              read; the condition the voters serve is met.
Tell apart    -
Not covered   Whether t8103 has voter words at all.
Safety        -
Budget        None.
Result        Not built, not run: no t8103 address (see Known).
```
