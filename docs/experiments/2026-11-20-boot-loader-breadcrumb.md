# Boot-loader wake breadcrumb (run 2026-11-20 01:36 IST)

```
Question      Does a wake reach the boot CPU after our sleep entry?
Known         No kernel-side wake marker fired in two ds29 runs (evidence: ds29 section).
Prior art     Hypervisor m1n1 bd6a43d4 leaves 'W' in power-chip scratch at its wake entry
              (evidence 2026-11-06-mac27-hv); lab loader patches 16456a0..7ea6fde.
Outcomes      A  breadcrumb 'Z', kernel up about 65-110 s after the commit -> woke; hand-off failed
              B  no breadcrumb, kernel up about 165 s after the commit      -> no wake reached the CPU
Tell apart    A and B differ by at least 55 s and by bytes 0x9f0b-0c.
Not covered   "Woke but DRAM lost" looks like B. The breadcrumb code has never been seen to write.
Safety        wdt 150 s armed at begin; boot-once kernel; old boot.bin kept with a restore script.
Budget        1 loader build, 1 run.
Result        B: no breadcrumb, 165 s. Raw: var/commit-state/breadcrumb-run1-20261120.txt.
              Loader restored to 0a1e47f3. Open: prove the breadcrumb can write (start the loader's
              reset path on purpose).
```
