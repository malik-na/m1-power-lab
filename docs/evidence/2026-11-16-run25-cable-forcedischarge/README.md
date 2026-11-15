# Run 25 with the Thunderbolt cable in: the first look inside the restart window (2026-11-16)

Purpose: the replica (../2026-11-16-run25-replica/) confirmed the record (restart through a boot
~21 s after the entry, before the 60 s alarm) but had to run with the cable out, so nothing could
be seen inside the window. This run keeps the cable in and watches the window from the M3 Max.

## What differs from run 25 (two named deviations)

1. **Cable in.** The script's gate (`gate()` in run25.sh 3b90a8a4) no longer requires the charger
   offline, no type-C partner and no port supply; it still requires the battery discharging and
   no USB device, and still records everything (`gate-variant.diff`: only the condition line and
   the waiting message change).
2. **Force-discharge.** With the M1's charger out, the M3 Max (on its own charger) sources power
   over the cable and the M1 charges from it, which the gate refuses. The M1's battery was set to
   `charge_behaviour = force-discharge` over the cable at 02:53:25.1, three seconds after the gate
   started waiting: the M1 runs on its battery (tested awake beforehand: about -0.37 A) while the
   cable still carries 5 V (`ac_online` stays 1). The setting was back to `auto` after the restart.

Everything else as run 25: lab kernel 05754414583e96fd... (7.2.11-labsep14 #77), the same seven
S2R arguments (lab job **j1115-212222-b733**, cmdline identical apart from maclab.job), tests
boot-health then the script only, the same cold start (0x0201 = 04 before the entry).

An earlier try with deviation 1 alone (job j1115-210748-d02e) timed out at its gate without an
entry, because the M1 was charging from the cable (`gate-variant-cablein-unused.diff`).
A try before that (j1115-210531-b66d) was cancelled at its gate: listing omarchy-m-test
explicitly made the lab run it (GPU and display work) before the S2R script.

## Timeline (M3 Max clock; M1 log lines on the M1's clock, which agreed within ~10 ms)

| Clock | rel. s | Source | Event |
|---|---|---|---|
| 02:53:30.479 | -2.35 | M1 log | GATE PASSED (ac_online 1, Discharging, 1 partner, 1 port supply), battery 77 % |
| 02:53:30.570 | -2.25 | M1 log | ENTRY: acceptance cycle 60 |
| 02:53:32.824 | 0 | M1 log | rmmod apple-sep rc=0, the last line the M1 wrote |
| 02:53:33.112 | +0.29 | M3 ping (Wi-Fi) | the M1 stops answering |
| 02:53:33.138 | +0.31 | M3 (ACIO fw) | the M1's side tears down the Thunderbolt paths (device suspend) |
| 02:53:36.390 | +3.57 | M3 (ACIO fw) | Gen2/3 link errors on both lanes |
| 02:53:36.414 | +3.59 | M3 kernel | retimer disconnected, **host disconnected**: the M1's USB4 port stops |
| 02:53:37.3-02:54:00.1 | | M3 (ACIO fw) | 107 x "Timeout reading AT register": nothing answers on the M1's side |
| 02:53:41.158 | +8.33 | M3 (ACIO fw) | SBX disconnected |
| 02:53:41.809 | +8.98 | M3 type-C | **the M1 detaches**: partner gone on the M3 Max's port2 |
| 02:53:43.828 | +11.00 | M3 type-C | partner back, the M3 Max sourcing |
| 02:53:52.632 | +19.81 | M1 uptime | next kernel's start (uptime 43.26 at 02:54:35.892; postmortem: 1794777832, entry + 20 s) |
| 02:54:00.146 | +27.32 | M3 (ACIO fw) | USB4 link "Entering Connected" |
| 02:54:02.429 | +29.61 | M3 ping (Wi-Fi) | the M1 answers again (stock kernel, new boot id) |
| 02:54:06.388 | +33.56 | M3 kernel | new host found |

## What this establishes

1. **Same ending as run 25 and its replica**: back through a boot 20 s after the recorded entry,
   40 s before the alarm; 0x0201 04 -> 01; postmortem classes unchanged (wake-restart, A3/A4/A5
   FAIL, A6 PASS). The cable and force-discharge did not change the outcome.
2. **The SoC reset is pinned from outside at 02:53:41.8.** The M1's type-C controller detached
   from the cable then. The M1's own boot timing (systemd-analyze on the same kernel: firmware
   9.474 s + loader 1.368 s = 10.842 s) put forward from that instant gives 02:53:52.651; the
   next kernel started at 02:53:52.632 by its own uptime, **19 ms apart**. So the detach is the
   reset (or within milliseconds of it), not a later event.
3. **The reset comes 5.4 s after the M1's USB4 port died** (02:53:36.41 -> 02:53:41.81), and 9.0 s
   after the last line the M1 wrote. The postmortem's own reading of the chip's clock says
   "ENDING 5 s". A fixed ~5 s from the moment the port powers down to the reset fits the 5 s
   watchdog the earliest notes describe (an always-on engine's WD2, armed at the commit, resets
   the SoC when the entry does not complete), and it also fits the 2026-11-13 reading (the chip's
   own wake sequence starts at once and stalls, then a 5 s reset). This run does not separate them.
4. **What the port death is, is an inference**: the USB4 port dropping 3.6 s after the last log
   line fits the SoC powering down at the commit; nothing on the M1 logged that moment.

## Not settled / next

- Whether the 5 s runs from the commit (entry never completes) or from a wake that starts by
  itself: this needs a signal inside those 5 s. The M1's port is dead for all of it, so the
  cable cannot show it; a second, independent timing of the commit itself would (for example a
  driver mark written to the PMU at the commit and read back, compared with the port's death).
- The pre-commit stretch (0 -> +3.6 s) is longer than the driver's measured release time
  (112 us): the rest of the suspend path (devices, CPUs) happens in it. Device suspend on the
  Thunderbolt side began at +0.31 s.

Files: `observer.log` (M3 Max, includes the timed-out first try from 02:35), `run25-log.txt`,
`run25-result.txt`, `postmortem.txt`, `boots.txt`, `state-after.txt`, `gate-variant.diff`,
`gate-variant-cablein-unused.diff`. The run25.sh script itself stays out of git (it cites
private reverse-engineering notes); its sha256 is 3b90a8a46d5d1ce3....
