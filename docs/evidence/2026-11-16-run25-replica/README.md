# Run 25 replicated, with an outside observer (2026-11-16)

Purpose: test the record of the last real suspend-to-RAM entry (lab job j1115-101250-868e,
2026-11-15 15:44: "this boot started 23 s after the recorded entry", no wake at the 60 s
alarm) by running it again unchanged while the M3 Max watched the M1 on its own clock.

## What was run

`lab retry j1115-101250-868e` -> job **j1115-205114-6163**: same Mac (naeems-m1-air-r25), same
kernel (lab kernel 05754414 = 7.2.11-labsep14 #77, built 2026-11-14 11:40 UTC; source not
reachable from this machine), same test script (run25: acceptance.sh, params.sh sha256
27d46856...), same command line (`apple_s2r_rs.enable=1 dry=0 alarm_secs=60 net_wd1_secs=170
disp_park=1 apple_cpu_hotplug=park pmgr_pwrstate.always_on=fpwm1,gfx,sio_busif,sio`).
Preconditions as the script demands: a power-button cold start first (0x0201 = 04, read over
the cable before the submit), then charger and Thunderbolt cable out at the script's gate
(both ports empty, on battery, 64 %). Observer: `tools/tb/m1-observe` on the M3 Max (cable
signals while the cable was in, the M1's Wi-Fi address from the M3 Max over the LAN while it
was out).

## Timeline

| Clock | Source | Event |
|---|---|---|
| 02:19:47.7 | ssh (cable) | shutdown queued |
| 02:19:56.5 | M3 kernel | "host disconnected": the M1 is off; M3 port2 turns **source** (the M3 Max powers the switched-off M1) |
| 02:20:53.7 | M3 kernel | "new host found": the M1 booted after the power button; 0x0201 = 04 |
| 02:21:32 / 02:21:57 | M3 kernel | host gone / back: the lab's one-shot reboot into the test kernel |
| 02:22:17.3 | M1 log | GATE: waiting for the charger out and both ports empty |
| 02:22:30.9 | M3 kernel | host disconnected: the cable pulled |
| 02:22:46.2 | M1 log | GATE PASSED (ac 0, no type-C partners, no USB devices) |
| 02:22:51.6 | M1 log | ENTRY: acceptance cycle 60 |
| 02:22:53.9 | M1 log | rmmod apple-sep rc=0 (last line of the run's log) |
| 02:22:53 | M1 postmortem | recorded entry second 1794775973; alarm 1794776033 (entry + 60 s) |
| 02:22:54.3 | M3 ping (Wi-Fi, 5 Hz) | the M1 stops answering |
| 02:23:14 | M1 postmortem | next boot's kernel start, 1794775994 = **entry + 21 s** (journal's first line of that boot: 02:23:19) |
| 02:23:22.9 | M3 ping (Wi-Fi) | the M1 answers again: stock kernel 7.3.0-0test5, new boot id |
| 02:25:18 | M3 kernel | cable back in, "new host found" |

## Result

**The record replicates.** Entry, then a restart through a boot about 21 s after the entry
(2026-11-15: 23 s), 39 s before the alarm; 0x0201 04 -> 01; the script's postmortem gives the
same classification as before ("wake-restart", A3 FAIL woken by something else, A4 FAIL new
boot, A5 FAIL RAM marker lost; A6 PASS). The M3 Max's view agrees on the outside of the window
independently of the M1's records: silent from 02:22:54.3 to 02:23:22.9 (28.6 s, which
includes boot to Wi-Fi); the M1 was not reachable at any time near the 60 s alarm.

What the outside view adds: the entry really took the machine off the network within 0.4 s
of the driver's last logged step; the restart is not a late artefact of the M1's clock or
records, it happened well inside the first 21 s.

## Not settled by this run

- What restarts the chip ~10-20 s after the entry (the 2026-11-13 notes: the chip's own wake
  sequence starts by itself and stalls at its display step, then a 5 s chip reset). This run
  cannot see inside that window: the cable had to be out.
- The two clocks for the next boot's start differ by 5 s (postmortem 02:23:14 vs journal
  02:23:19); either way it is before the alarm.
- The test kernel's persisted journal ends at 70.6 s of uptime (apple_sep hwrng EIO x5, then
  "trusted_key ... unregistered"); the entry's final kernel lines were not persisted.

## Side observations

- While the M1 is powered off, the M3 Max sources power to it over the cable (port2 role
  flips to source); while the M1 runs, the M1 sources power to the M3 Max.
- The M3 Max's own charger (port0) dropped at 02:22:31.3, the same second the cable was
  pulled, and came back at 02:25:01: either it was unplugged too, or something on the M3
  Max's side reacted to the cable pull. Not explained yet.

Files: `observer.log` (M3 Max), `run25-log.txt` / `run25-result.txt` (the M1's script),
`postmortem.txt` (acceptance.sh postmortem), `boots.txt`, `state-after.txt` (PMU bytes after).
