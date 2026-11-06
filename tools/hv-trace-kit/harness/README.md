# Real-S2R harness (macOS 27 guest under m1n1 on the M1 Air)

Scripts used for try28-37 on 2026-11-06/07; paths inside are absolute (this machine).
Build: ~/m1n1 branch m1power/m1-sptm-native (local). The M1 boots the installed trampoline image
(08a8b8c8) from Macintosh HD; each run chainloads the current ~/m1n1/build/m1n1.bin.

One cycle (the M1 at a fresh m1n1 proxy, cable in):
    go27c.sh tryNN -m real_s2r.py          # FRESH=0 CHAIN=1 BOOTARGS=... EXTRA_M=hv_s2r_trace.py
    drive.sh tryNN                         # ARM_EXTRA='real_s2r_on(alarm=120)\n'
    wake_watch4.sh tryNN                   # start after "S2R: last core" appears in run-tryNN.out
The user logs in and closes the lid; macOS sleeps ~1 min later; the alarm wakes the SoC; the
handler records markers in PMU scratch and reboots; the watcher reads the markers (crumb.py),
the PMU records (pmu_postmortem.py) and the battery gauge (batt.py, which must stop its SMC
session). Reboot the M1 (p.reboot()) before the next cycle.
