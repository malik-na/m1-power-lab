# What do the cluster words read at macOS's commit, with its cores down? (milestone 4, hypervisor reading)

```
Question      At macOS's commit, on core 0 after its own final write and the other seven cores'
              real ones: what do P 0x23b718004, E 0x23b718000, 0x23d2b8008 and watchdog 1's
              control 0x23d2b001c read? (Linux at its commit: P 0x10, then 0x50 50 ms later; E
              state 1; 0x23d2b8008 0 after a write of 0.)
Known         macOS reads both cluster words 0xf and writes them 0 at R22 (det36 log 454.9288);
              at the wake E reads 0xf, P 0 (det36 544.6152) [spec 2022, 3739-3749]. At its commit:
              not read (no commit list holds them: var/recfg/commit-snap-list*.json checked).
              0x23d2b8008: macOS writes it 0 at T-18 ms (det36 454.9108, cpu 0); reads 0 awake
              (135snap1). Watchdog 1 control at macOS's commit: 0 (K, spec 4.1c). Cores 1-7 and 0
              at the commit: ISR 0, IPI_SR 0, guest virtual timer fired and unmasked on 4 cores
              (det18 core-state, var/commit-state/r7-det18-core-state.txt): already read.
Prior art     tools/prior-art.sh cluster; the det runs as above.
Outcomes      A  P reads 0 (state 0) at the commit -> macOS's P cluster is off when its last core
                 goes down; Linux's 0x10/0x50 differ: tell Naeem, with the Linux probe to match.
              B  P reads 0x10 (or 0x50, any state 1/5) -> as Linux: not a difference.
              C  the words read with an error flag, or no commit snapshot -> inconclusive.
              Each word is read twice: first and last of the 1,336-word list (the list's read
              time apart); E and 0x23d2b8008 judged the same way.
Tell apart    The "snap" record (tag "commit") in detached-det40.jsonl.
Not covered   Values after core 0's own power-down (no CPU runs then).
Safety        macOS under the hypervisor by the recipe that ran unattended (det33, det11):
              claim `observation`; hv_preflight (go135.sh); one console reader; nothing else on
              the M3's USB (read 2026-11-20 07:2x: only the Thunderbolt cable). No-hands way out:
              the hypervisor's alarm at commit + 90 s (ALARM=90) and watchdog 1 at commit + 150 s
              (WD1=150); a hang before the commit leaves the proxy reachable over USB
              (detach_readout.py --reboot); hv-reboot.sh at the end. Linux is not slept. No build:
              m1n1-next as built (c2d99a4e), list var/recfg/commit-snap-list-m4.json.
Budget        1 hypervisor run (2 if the first fails), Naeem's "Yes, read it" (2026-11-20).
Result        (after the run)
```
