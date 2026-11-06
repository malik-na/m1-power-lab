# Overnight run, 2026-11-05 22:33 to 2026-11-06 05:21 (M1 Air, Omarchy, on battery)

Batch `batch-223328-2126`, unattended, panel off, Wi-Fi associated, on battery
throughout (DC-in 0 W). Raw data: [`batch-223328-2126.json`](batch-223328-2126.json),
spec: [`batch-223328-2126-spec.json`](batch-223328-2126-spec.json), HTML:
[`report.html`](report.html).

## Results

| What | Result |
|---|---|
| Idle, panel off, tuned (30 min record) | **0.625 W** system, 0.523 W SoC; E-cores 88.6% deep idle, P-cores 98.8% |
| Whole tuning vs stock (`tuneset`, 6 randomized pairs, 4 min each) | tuned **0.617 W**, stock **1.096 W**: the tuning saves **479 mW (-44%)**, 95% CI 404..554 mW. Every pair agrees (tuned 0.60-0.64 W, stock 0.98-1.14 W; per-pair savings 342-546 mW) |
| Wi-Fi PS-Poll (`wifi_pm` 1 vs 2, 6 pairs, 2 min each) | PS-Poll 0.609 W, PM 2 0.599 W: PS-Poll costs 10 mW, 95% CI -32..+52, not significant. In four of six pairs PS-Poll saves 15-17 mW; in the other two (both with PS-Poll measured first) the SoC rail was 93 and 115 mW higher during the PS-Poll arm, so those pairs show PS-Poll costing 56-67 mW |
| Sleep (s2idle), 6 x 45 min | **0.440 W** every time (0.4395-0.4405), 1.22 %/h of battery, about 3.4 days of standby. 6/6 woken by the wake timer, all CPUs in power-down 100% of the sleep |

## What the numbers mean

- The tuning deployed on the M1 (PCIe ASPM `powersupersave`, L1 substates,
  LTR, Wi-Fi power save with a 50 ms tail, PS-Poll) is worth about half a watt
  at idle with the panel off: the Mac idles at 0.62 W instead of 1.10 W. This
  is the first same-night, randomized measurement of the whole stack, and it
  confirms the gain from the separate knob tests.
- Sleep is flat at 0.44 W and fully reliable. Nothing in Linux s2idle is left
  to cut at that level that is large: the remaining draw is the SoC staying
  powered (CPUs are already in power-down 100% of the time). The next real
  step is SoC sleep (suspend-to-RAM), see [STATUS](../../STATUS.md).
- PS-Poll stays deployed, on weak evidence. Tonight's test alone shows no
  saving. Pooled with the earlier 6-pair test (saving 20 mW, CI 6..35) by
  inverse variance, PS-Poll saves about 17 mW (roughly 6..27 mW); weighting
  all 12 pairs equally gives only about 5 mW. A longer, cleaner A/B would
  settle it.

## Problems found and fixed

1. **The tuned arm of the stack A/B ran without PS-Poll.** Applying the tune
   spec in its listed order set `wifi_pm=1` and then `wifi_ps=on`, and turning
   power save on puts the firmware back in PM_FAST (2). The first sleep logged
   this as drift (`wifi_pm` want 1, now 2), and the resume hook corrected it.
   Fixed: `tuneset` and `tune run` now re-check and re-apply until every knob
   holds (`settle_knobs`, commit on `omarchy-live-power`). Checked on the M1:
   stock -> tuned now ends at `wifi_pm=1`. The true whole-stack saving is
   therefore somewhere between about 0 and 17 mW larger than measured.
2. **The run was cut short at 05:21 by maclab, not by the M1.** From 05:06 the
   lab agent's calls to the maclab server timed out waiting for a response
   (TCP connected; Tailscale on the M1 stayed connected and no Wi-Fi
   disconnect was logged, though at 05:18:58 one read failed with "network is
   unreachable"). At 05:19 the server re-sent job `j1105-221851-ca63`, which
   had already finished (pass) at 22:18, and the agent rebooted the Mac
   into that lab kernel, then back. Lost: the final 30 min idle record
   (`night-idle-end`, 17 min in). Everything before it completed. This looks
   like a maclab server-side fault (stale job re-dispatch after an outage).
3. Seen on every resume, harmless so far: `PS fpwm1: Failed to reach power
   state 0xf` (a PMGR domain that does not fully turn back on at resume).
   Not investigated tonight.

## S2R groundwork prepared overnight (not run on hardware yet)

- PMU RTC wake alarm kernel (`m1power/s2r-pmu-rtc` `7e874c1`, build
  `b1105-175339-6471`): checker rated ready. Lab test:
  `target/lab/m1power-s2r-rtcwake.sh`.
- CPU hotplug kernel (`m1power/s2r-cpu-hotplug` `fffde00`, build
  `b1105-191712-d6ee`): two rounds of fixes, final checker rated ready. Power
  down only on a clean m1n1 <= v1.6.1 with `powerdown-legacy`; otherwise park.
- macOS 13.5 hypervisor trace kit and owner runbook:
  [`tools/hv-trace-kit/RUNBOOK.md`](../../../tools/hv-trace-kit/RUNBOOK.md).
- Static S2R entry/wake sequence from Apple's public macOS 13.5 kernelcache
  for j313 (kept local, not in the public repo).
