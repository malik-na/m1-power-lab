# s2idle cycle

One ordinary Linux suspend (s2idle) on the stock kernel, woken by m1power's watchdog-BARK wake timer, with the M3 Max timing the sleep from outside. It proves that a sleep and resume happen in the same boot and that nothing (Wi-Fi above all) is left worse.

## Sub-features

- `s2idle-timed` sleeps for N seconds and wakes by the timer.
- `s2idle-outside` times the sleep from the M3 Max (cable carrier down/up, or Wi-Fi ping).
- `s2idle-wifi` compares Wi-Fi power save and gateway latency before and after.

## How to get to it (user POV)

- Run `tools/tb/m1-s2idle-cal [seconds] [label]`.

## Driving it with m1-s2idle-cal

Preconditions:

- Doctor reports `drivable` and `M1 m1power_ko loaded`, with `M1 kernel 7.3.0-0test5-1-ARCH`.
- The wake timer is idle: `tools/tb/m1tb 'grep ^armed /sys/kernel/debug/m1power/waketimer'` prints `armed 0`.
- Nobody is using the M1's desktop (the cycle locks and suspends it).

- **Run.** Run `tools/tb/m1-s2idle-cal 60 <label>`. It starts the observer, arms the timer, suspends 3 s later, waits for SSH, records state and collects. Last lines: `same boot (<id>): resumed` and the observer timeline.
- **Prove the timer woke it.** In `var/m1-cal/<stamp>-<label>/post.txt`, `waketimer.fired_total` is 1 higher than in `pre.txt`, `last_fire_boot_ns` minus `deadline_boot_ns` is tens of ms, and `suspend_stats.success` is 1 higher.
- **Prove from outside.** In `observer.txt`, `LINK ... NO-CARRIER` then carrier back about the timer's length later (cable in), and no `host disconnected` (a reboot would log it).
- **Prove Wi-Fi.** `wifi.Powersave:off` and the `gateway_ping` line in both `pre.txt` and `post.txt`; the averages are within a few ms.

## Gotchas

- The M1's kernel log cannot time a sleep: its monotonic stamps stop in s2idle (0.85 s logged for a 58 s sleep). Use BOOTTIME (the wake timer's numbers) or the observer.
- The cycle is power-measurement-free while a charger or the cable feeds the M1; read doctor's `M1 ac` before quoting any drain.
- If `post.txt` shows Wi-Fi power save on or high latency, report it; do not change Wi-Fi settings to fix it (standing rule).
- The script stops its observer with SIGTERM; a stuck observer is killed by its PID, never by a name pattern.
