# Calibration: one stock s2idle cycle on the M1 Air, watched over Thunderbolt (2026-11-16)

First run with the M3 Max and the M1 Air joined by a Thunderbolt 4 cable. Purpose: learn
what an ordinary sleep and wake look like **from the M3 Max's side** (an observer that does
not depend on anything the M1 records), before any suspend-to-RAM claim is re-tested.

Setup: M1 on Omarchy's stock kernel 7.3.0-0test5-1-ARCH, stage-2 m1n1 26844aaf, charger on
the M1's port1; the Thunderbolt cable on the M1's port0 (the M1 is power source and USB
host on that cable; the M3 Max had its own charger by the time of the run). `m1power.ko`
built on the M1 (gcc against the clang kernel: no kCFI, SCS or randstruct in its config)
and loaded for its watchdog-BARK wake timer. No tuning of any kind; Wi-Fi only measured.
Script: `tools/tb/m1-s2idle-cal 60 stock-s2idle`; observer: `tools/tb/m1-observe`.

## What was seen

| M3 Max clock | Source | Event |
|---|---|---|
| 02:01:17.466 | ssh | wake timer armed (60 s), `systemctl suspend` queued 3 s ahead |
| 02:01:20.940 | M3 `ip monitor` | thunderbolt0 NO-CARRIER: the M1 took the link down |
| 02:01:21.336 | M3 ping (5 Hz) | the M1's link-local address stops answering |
| 02:01:21.388 | M3 kernel | Apple ACIO firmware: rx/tx path tear-down (no "host disconnected") |
| ~02:02:17.5 | M1 timer | BARK fired 35 ms after its deadline (BOOTTIME 5428.836 vs 5428.801) |
| 02:02:18.972 | M3 `ip monitor` | thunderbolt0 carrier back |
| 02:02:21.546 | M3 ping | first answer (2049 ms: the probe queued during link training) |
| 02:02:24 | ssh | logs in; same boot id: a resume, not a reboot |

Link down for 58.0 s of the 60 s timer; carrier back about 1.5 s after the timer fired.

## What this establishes

1. **The timed wake works on the reinstalled M1**: the watchdog-channel-0 BARK woke s2idle
   on time (fired_total 1, no spurious fires), suspend_stats.success 2 -> 3, no failures.
2. **The cable gives an external entry and exit marker**: carrier drop about 3.5 s after the
   request (device suspend), carrier back about 1.5 s after the wake. A resume shows only a
   carrier change and an ACIO path set-up; the M3 Max's kernel logs no "host disconnected" /
   "new host found". A reboot of the M1 would show those (seen at 683-817 s of the M1's
   previous boot, when the link was re-established), and only after Linux has started the
   thunderbolt driver again, so a resume and a reboot can be told apart from the M3 Max.
3. **The M1's own kernel log cannot time a sleep**: its monotonic stamps show 0.85 s between
   "suspend entry" and "suspend exit" for a 58 s sleep (CLOCK_MONOTONIC stops in s2idle).
   Durations must come from BOOTTIME (the wake timer's clock) or from the M3 Max.
4. **Wi-Fi unaffected**: power save off before and after; gateway RTT 3.33 ms avg before,
   3.20 ms after, 0 % loss both times.
5. The M1's and M3 Max's wall clocks agreed within about 10 ms at the request.

## Not established

- Sleep power: the M1 was on its charger. Earlier s2idle figures (0.44 W tuned, 0.61 W
  untuned) remain unverified on this install.
- Whether the M1 keeps sourcing power on port0 while asleep: the M3 Max was on its own
  charger, so its view of the port did not change. Worth one run with the M3 Max's charger out.

Files: `host.txt` (script), `observer.txt` (M3 Max side), `pre.txt` / `post.txt` (M1 state),
`kernel-sleep.txt` (M1 kernel lines), `arm.txt` (M1 clock at the request).
