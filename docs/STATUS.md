# Qualification status

This file distinguishes implemented behavior from physical qualification.

## 2026-11-05 Omarchy host and live M1 target

The workbench now runs from an Omarchy MacBook Pro (M3 Max, aarch64) against
an M1 MacBook Air that itself runs Omarchy (`linux-aurora` 7.2.11), over
Tailscale SSH. The full host suite passes on the new host (517 passed, 1
skipped, Python 3.14); four tests had stubbed `os.fstat` results without
`st_size`, which Python 3.14 reads. See [LIVE](LIVE.md) for the workflow.

Verified on the physical M1 this session:

- `m1power.ko` builds against the installed headers and reads all 1642 SMC
  keys. `zSPa` is a DC-in energy accumulator in mJ that keeps counting at 1 Hz
  through s2idle (180 samples over a 183 s bracket that included a 163 s sleep).
- The s2idle wake timer works: armed for 45 s at 07:52:07, the Mac suspended at
  07:52:16 and resumed by itself at 07:52:52 through `m1power_waketimer`, with
  no key press. Two failed designs are recorded in the module comments:
  watchdog channel 2 ignores its interrupt enable, and channel 0 interrupts on
  BARK, not BITE.
- Idle sweep, display off, on USB-C power from the host, three randomized
  pairs of 30 s blocks per knob: Wi-Fi power save on saved 186 mW of 1.247 W
  (95% CI 127 to 244 mW). Power profile (performance/balanced/power-saver),
  the teo idle governor, Bluetooth off, runtime PM on every device and pausing
  quickshell showed no effect within about ±30 mW.
- Second round, stacked on Wi-Fi power save, four pairs of 40 s blocks:
  PCIe ASPM `powersupersave` (L1.1/L1.2 substates on the Wi-Fi link) saved
  290 mW on USB power, but that run was unstable (one block's SD was 1.39 W);
  on battery, three pairs gave 175 mW (95% CI 143 to 207 mW), the figure to
  quote; the Wi-Fi radio off saved 484 mW (not usable
  while the host controls the target over Wi-Fi); `lab-agent` costs 7 mW and
  55 interrupts/s; pausing superwhisper had no effect once power save was on.
- ASPM `powersupersave` was persisted, then withdrawn: with L1.1/L1.2 on the
  Wi-Fi link, `brcmfmac` later timed out entering D3 during suspend
  (`brcmf_pcie_pm_enter_D3 ... returns -5`), and the kernel aborted four of
  six suspend attempts in a sleep A/B. Only Wi-Fi power save stays persisted.
  With the substates back off, suspend succeeded again without reloading the
  driver.
- Sleep on USB-C power from the host: 0.47-0.48 W over 295 s sleeps with the
  substates on, 0.70 W over an 86 s sleep without them. The awake part of each
  bracket is about 0.5 s, so the gap is the substates themselves (roughly
  230 mW in sleep too), not resume overhead.
- On battery (cable unplugged), Wi-Fi power save on, display off: 1.136 W
  idle; two 15-minute sleeps at 0.610 W by the SMC load accumulator (0.55 and
  0.60 W by the battery gauge), 1.5-1.6% of this battery per hour. The pack
  holds 36.5 Wh after 759 cycles, so that is about 2.6 days of standby.
- `zSLa` is a system-load energy accumulator (mJ): on battery it advanced at
  1.105 W while the gauge reported 1.116 W, and on USB power it equals DC-in.
  Sleep power now comes from it; the battery gauge did not move at all in 30 s.
- s2idle reaches CPU power-down: each P-core entered `CPU PD` once per sleep
  and stayed. The per-state s2idle *time* counters read near zero because
  sched_clock stops during s2idle, so the ledger counts entries instead.
- Sleep A/B on battery, two pairs of 10-minute sleeps, Wi-Fi radio off while
  asleep: substates on slept at 0.44 W, off at 0.61 W (-171 mW, 1.13 against
  1.70% per hour). But the first suspend after switching the substates back
  off failed: the Wi-Fi firmware had wedged (`brcmf_msgbuf_delete_flowring:
  timed out`, query timeouts, the driver re-registered as a new phy) and its D3
  handshake timed out even with the radio blocked. L1.1/L1.2 on this BCM4378
  link is therefore not persisted; it is a brcmfmac bug worth reporting.
  Blocking the radio during sleep saved nothing measurable (0.608 against
  0.610 W), so the persisted tuning is Wi-Fi power save alone; a suspend
  afterwards worked (0.615 W).
- 45 of the 63 powered SoC domains stayed powered through a sleep. Most must
  (DRAM controllers `dcs*`, `mcc`, `aic`, `pmp`, `pms`, `sep`, `nub_*`); about
  ten are candidates: the external-display coprocessor (`dispext_*`) with no
  display attached, the second USB-C complex (`atc1_*`, nothing plugged in,
  controller without runtime PM), the internal display coprocessor
  (`disp0_*`), and the PCIe root (`apcie*`, `pcie_ref`).
- Unbinding `dwc3-apple` from the never-connected second USB-C port
  (`502280000.usb`, to let `atc1_*` power down) oopsed the kernel: NULL
  dereference in `mutex_lock` from `dwc3_apple_remove+0x1c` at the unbind
  write ([trace](evidence/2026-11-05-dwc3-apple-unbind-oops.txt)). The driver
  never initialised that instance, so its remove path is unsafe. The M1 was
  rebooted (it unlocks itself); the module rebuilt and loaded at boot, tuning
  re-applied, and a suspend afterwards worked (0.69 W). `atc1_*` stays a
  target, but it needs a driver fix first, not an unbind. m1power has no
  unbind knob; the test was a one-off script.
- Standby guard verified on the M1 on battery: an ordinary suspend at
  11:50:26 armed the 5-minute check by itself; the 11:55:26 timer-only wake
  decided `resleep`, watched the input devices for 8 s, and suspended again at
  11:55:50; the second dark wake at 12:00:51 stayed awake as configured
  (`--max-dark-wakes 2`). Each dark wake kept the Mac up about 24 s; sleeps in
  between drew 0.62-0.63 W.
- The guard is now enabled permanently on the M1 at the owner's request:
  `m1power standby set --check-every 2h --poweroff-below 10` (stored in
  `/etc/m1power/standby.json`). Persisted target state: Wi-Fi power save on
  (`m1power tune`), standby guard on, module and sleep ledger installed.
- maclab: m1power now defers to the lab on the enrolled M1 (Lab boots, jobs,
  pm_test cycles; see [MACLAB](MACLAB.md)), and `m1power lab-run` runs the
  probe as a lab job. The first, `j1105-075658-7770`, passed: 1.18 W idle on
  the Lab boot, and a real 85.6 s s2idle sleep that woke itself with the lab's
  60 s watchdog armed, the first unattended real suspend in a maclab job. Two
  dry runs before it found a guard bug (it treated the probe's timer wake as a
  dark wake and re-slept the Mac); the guard now acts only on timers it armed.
  The USB-C PD controllers (`tps6598x`) woke an empty-port sleep early once
  (14.6 of 30 s) and appear as wake sources in others: a lead for sleep work.
- dwc3-apple fix, A/B through the lab: two lab builds from the same commit
  (`omacom/linux-aurora@b798f2b`), with the M1's own config, differing only by
  [a one-line fix](https://github.com/malik-na/linux-aurora/commit/1618cc6d56af4859a22053972dd7e58cc86f5c59)
  that sets the driver data in probe (`dwc3_core_probe()` only sets it at the
  first cable, so `remove()` on a never-connected port dereferenced NULL).
  Stock `7.2.11-labb798f2b0-4585` (job `j1105-082911-4aed`): unbinding the
  unused port oopsed at the same address as on the installed kernel, then the
  Mac rebooted back normally. Patched `7.2.11-lab1618cc6d-1a44` (retry
  `j1105-085239-15ab`): clean unbind, job passed, omarchy-m-test 0 regressed.
  The first patched run lost contact during boot-health because Wi-Fi dropped
  for a couple of minutes (brcmfmac flowring timeouts 76 s after boot, and the
  host lost its network at the same time); nothing from dwc3 in that boot.
  Power: no `atc1_*` domain switched off with controller and PHY unbound (its
  IOMMUs and display crossbar stay active), the awake A/B showed no effect
  (-5 mW, 95% CI -17..+6) and one sleep each way gave 0.649 against 0.631 W.
  Unbinding also left the Type-C controller unable to set its mux
  (`failed to place Type-C mux in safe mode: -19`) until the port was rebound.
  Freeing that complex needs runtime PM across the ATC block, not an unbind.
  The fix is proposed upstream as
  [omacom/linux-aurora#365](https://github.com/omacom/linux-aurora/pull/365)
  (`checkpatch.pl --strict` clean; same tree as the tested commit).
- Two 90 s sleeps back to back in one job read to labd as one 3m14s sleep,
  past its 2-minute notice; keep a job's total sleep under two minutes.
- Wi-Fi link L1 substates, deeper (2026-11-05 afternoon):
  - The per-link sysfs switches (`link/l1_*`, `clkpm`) can only remove states
    from the ASPM policy, and writing 0 is a sticky disable in the ASPM core.
    Two earlier "L1.1 only / L1.2 only" A/Bs measured default against default
    and are void; the knobs now restore by clearing the disable.
  - The Apple root port advertises Port T_POWER_ON and Common_Mode_Restore of
    0, so Linux programs the endpoint's 6 us / 8 us and a 20 us L1.2
    threshold; macOS uses root-port CMRT 25 us and threshold 87 us, writes
    LTR max latency 0x1008 (Linux leaves 0) and never enables Clock PM here.
  - macOS-like configuration (Clock PM off, CMRT 25 us, threshold 87 us,
    T_POWER_ON 50 us, LTR max 0x1008, all four substates on): idle 1.010 ->
    0.807 W, -204 mW (-20.2%, 95% CI -254..-153). The firmware still failed to
    acknowledge D3 on the fifth suspend of a stress run, so timing, Clock PM
    and LTR are not the cause.
  - Cause found in the driver (Asahi-only code, confirmed by two independent
    reviews): since f04be345ad51 brcmfmac's hard IRQ handler clears
    `irq_ready` whenever it catches `mailboxint` still set, and the thread then
    skips the rings for that interrupt. In MSI mode the firmware raises no
    further MSI, so a completion that came with it (an ioctl response, the D3
    ACK) is lost. Fixes on malik-na/linux-aurora: `fix/brcmfmac-irq-ready-v2`
    (the handler masks without touching `irq_ready`; the thread unmasks
    without setting it) and `fix/brcmfmac-d3-recovery-v2` (adds: a missed D3
    ACK no longer aborts suspend without WoWL, and forces a firmware reload on
    resume because the chip stays powered in s2idle).
  - Lab A/B, each a 15-cycle suspend stress with the macOS-like configuration
    on a lab build from the same commit (`b798f2b`):
    | Kernel | Job | Result |
    |---|---|---|
    | stock `7.2.11-labb798f2b0-4585` | `j1105-104309-e433` | D3 timeout on the 4th suspend; omarchy-m-test regressed (failed systemd-suspend.service) |
    | P1 only `7.2.11-lab428772f0-1559` | `j1105-104457-32c5` | the same, on the 4th suspend |
    | P1+P2 `7.2.11-labc0e6d3fa-4ed7` | `j1105-104639-fa1b` | 15/15 suspends; D3 not acknowledged on suspends 4, 8 and 12, each recovered by a firmware reload on resume; omarchy-m-test 0 regressed |
    The lost-completion race is real but is not what stops this firmware: the
    firmware itself fails the D3 handshake on every fourth suspend with L1
    substates on, and P2 turns that into a recovery.
  - Fix without a kernel change, as Broadcom's bcmdhd does around D3: the sleep
    hook turns ASPM L1.1/L1.2 off just before each suspend (the PCI-PM
    substates, used while the chip is in D3, stay on) and back on after
    resume. On the installed `7.2.11-14-1-ARCH`, 15/15 stress suspends with the
    macOS-like configuration live during the run, no D3 failure and no
    firmware reload, where the same kernel failed on the fourth suspend
    without the hook.
  - Persisted on the M1 (`m1power tune`): `wifi_ps=on pcielink:wifi:clkpm=0
    l1ss_profile=apple50 ltr_max_us=0x1008 aspm=powersupersave`, sleep-only
    `pcielink:wifi:l1_1_aspm=0 pcielink:wifi:l1_2_aspm=0`. lspci confirms all
    four substates, CMRT 25 us, threshold 87040 ns, T_PwrOn 50 us and LTR
    0x10081008 on the link.
  - Sleep with that tuning, paired 10-minute sleeps on battery: 0.443 and
    0.441 W, against 0.622 and 0.621 W with the `default` ASPM policy:
    -180 mW asleep (95% CI 177..182 mW), all four sleeps clean. Net for the
    day on battery: idle about 1.25 -> 0.81 W (display off), sleep 0.61 ->
    0.44 W, about 1.2% of this battery per hour, roughly 3.4 days of standby.
- Wi-Fi power save was not staying on (2026-11-05 evening). Omarchy ships
  `/etc/NetworkManager/conf.d/omarchy-wifi-powersave.conf` with
  `wifi.powersave = 2`, and NetworkManager applies it at every connection,
  including the reconnect after each resume; the sleep hook's re-apply ran
  before that reconnect. So the tuned idle figure held only until the first
  sleep. With the rest of the tuning on, power save off cost 140 mW (0.959
  against 0.819 W, 95% CI 49..230 mW). `tune` now writes a later-sorting
  drop-in (`zz-m1power-wifi-powersave.conf`, `wifi.powersave = 3`; Omarchy's
  file is untouched, `tune revert` removes ours); verified on after a suspend.
  `doctor` and every ledger entry now report tuned knobs that have lapsed.
- Wi-Fi awake tail after traffic (`wifi_ps_ret_ms`, brcmfmac `pm2_sleep_ret`):
  cfg80211 passes an unset timeout and brcmfmac clamps it to its 2000 ms
  maximum (`cfg80211.c:3478`; the firmware read 0x7d0), so the chip stayed
  awake 2 s after every packet. Only the wireless-extensions SIOCSIWPOWER
  ioctl sets it; cfg80211 keeps it across reconnects. Paired idle A/Bs, all
  pairs on one access point:
  | A -> B | A W | B W | effect |
  |---|---|---|---|
  | 2000 -> 200 ms (5 pairs) | 0.864 | 0.636 | -229 mW, 95% CI -361..-96 (every pair lower) |
  | 200 -> 50 ms (4 pairs) | 0.633 | 0.609 | -25 mW, 95% CI -44..-6 |
  | 50 -> 10 ms (4 pairs) | 0.602 | 0.658 | no effect (+56, CI -144..+256) |
  Cost at 50 ms: gateway ping at 1 Hz 5.3 ms average (max 7.0) against
  3.3 ms at 2000 ms; a 25 MB download ran at 106-127 Mbit/s at every value.
  Persisted at 50 ms and verified after a suspend and reconnect. Idle with
  display off is now about 0.61 W (from 1.25 W this morning, 0.96 W in real
  use before the power-save fix).
- Display on (2026-11-05, normal boot, battery): a static image costs about
  0.92 W with the backlight at 0 (1.77 against 0.85 W with the panel off),
  of which the SoC rails (PHPC) are about 0.2 W; the rest is the panel's own
  electronics and link. The backlight adds about 0.16 W at level 16, 0.39 W
  at 40, 1.0 W at 100, 3.4 W at 200 and 4.9 W at 394 (nits). With the panel
  on, no DCP or GPU interrupts fire (nothing redraws), but every DRAM
  controller (`dcs0-7`) is ungated 100% of the time, against about 92% gated
  with the panel off: scanout keeps DRAM awake. Hyprland 0.56 answers "ok" to
  `dispatch dpms on|off` but toggles, which had voided an earlier display
  A/B; the knob now checks the state it leaves.
- DCP video power savings: Linux calls
  `enable_disable_video_power_savings(0)` during DCP init
  (`iomfb_template.c:2701, 2786`). A lab kernel with 1
  (`malik-na/linux-aurora@m1power/dcp-video-power-savings`, `0903b4d`)
  against the stock lab build of the same commit, panel on at backlight 16,
  four pairs each: stock 2.29 W on / 0.97 W off (+1.32 W, job
  `j1105-140358-32a4`), patched 2.29 / 0.99 W (+1.29 W, job
  `j1105-140545-aa85`; one off block disturbed by a key press, SD 0.50).
  No effect: DRAM gating with the panel on stayed at 0% and the firmware
  logged nothing about idle savings.
- Wi-Fi DTIM skipping (`wifi_bcn_li_dtim` 0 -> 3, access point DTIM 1 at
  100 TU, on top of the 50 ms tail), five pairs: 0.615 against 0.606 W, no
  effect (-9 mW, 95% CI -21..+3). Not deployed.
- PMP v1 (the power-management coprocessor; nothing starts it on t8103
  today, and Linux powers off `pms_sram`, which holds its firmware, at boot
  as an unused domain): a lab kernel with a port of dd-dreams' v1 driver as
  an on-demand module (`malik-na/linux-aurora@m1power/pmp-v1`, `73f98f1`, job
  `j1105-144905-7bbc`) booted and passed, but the PMP never started: maclab
  stages only the kernel, and the device tree comes from m1n1's payload, so
  the new nodes and always-on flags were not live. Next: the module applies
  its nodes as a runtime overlay (`CONFIG_OF_OVERLAY=y`) on a boot with
  `pd_ignore_unused`.
- A six-lens source review (two adversarial reviewers per lever) ranked the
  remaining levers ([review](evidence/2026-11-05-power-lever-review.md)): the
  small peripheral, domain and waker levers add up to about 30-60 mW idle and
  20 mW asleep; fabric/DCS performance states (PMP) and a real SoC deep sleep
  are the only large ones. CPU idle is healthy (cores in `CPU PD` about 92%
  of awake idle time). tps6598x never woke this boot (wakeup_count 0; 81 of
  90 ledger sleeps ended by the wake timer, 1 by the lid or power button).
- Direction (independent review, 2026-11-05): continue in-OS. m1n1 proxy mode
  cannot measure Linux idle, and neither it nor in-OS tuning reaches macOS's
  tens-of-mW SoC power collapse, which needs firmware-level resume support.
  If m1n1 is revisited, the first step is one attended session that reaches
  proxy mode from the M3 (GET_CHIPID 0x8103) and chainloads back to Omarchy;
  failure ends that path.
- A four-reviewer adversarial review (two skeptics per finding) confirmed 34 of
  35 findings in the new tooling. All were fixed, and the fixes were checked
  independently; the module now tracks a per-fd SMC watch list and re-wakes a
  suspend that a just-expired deadline would otherwise miss.

### Hibernation

Hibernation is not reachable on this hardware by configuration alone. The
target kernel is built without `CONFIG_HIBERNATION`, and enabling it would hit
`swsusp_arch_suspend()` in `arch/arm64/kernel/hibernate.c`, which refuses with
"no mechanism to offline secondary CPUs": Apple silicon starts its CPUs through
spin-table, whose `cpu_operations` have no `cpu_die`, so no CPU can be taken
offline (the target has no `cpuN/online` files). Making it work needs a
kernel-side CPU parking protocol that the restored image can release, plus
restore paths for the RTKit coprocessors (DCP, ANS, SMC) whose firmware state
the freshly booted kernel would not match. Until then `m1power standby`
provides the practical half: periodic dark wakes from s2idle that power the
Mac off cleanly when the battery runs low or it has slept too long.

## 2026-09-28 installed investigation workspace

Release `1212afd` is installed on the ThinkPad as the enabled systemd service.
The private owner interface and Codex jobs run independently of the setup
terminal. Sleep, idle and lid-close inhibition is active while the service runs.
The scoped inspect-only helper is installed and active for USB port `1-2`.
After the twelfth return, the proxy enumerated as `/dev/ttyACM0`; five fixed
read-only requests verified its identity. The helper has no automatic restart
or boot enablement and must be explicitly
reopened after a coordinator restart or USB reconnection. It does not expose
native experiment dispatch.

The prior installed session is stopped. Its old uncertain usage was resolved
with a conservative 300,000-token charge under the owner's delegation, not a
provider measurement. A new session retains the eighth- through twelfth-attempt
technical artifacts and has completed two service-owned analysis turns. The first reported
27,986 tokens; the resumed turn reported 51,192 additional tokens, for a thread
and session total of 79,178 with no usage uncertainty. This verifies bounded
analysis of retained evidence, not a continuous autonomous native experiment loop.

The deployment fixes selected evidence being omitted from bounded prompts,
per-event notification cursor commits contending with the web interface, and
resumed chat reservation checks counting earlier turns. That installed release
passed 368 host tests; the current source including the bounded native USB
trace passed 500 tests before the twelfth launch. The expanded 90-test tracer
suite passed after the regression added for its exact review.
During the installed resumed job, all 90 authenticated and anonymous HTTP probes
returned the expected 200 or 403; the slowest took 3.438 seconds. The private
HTTPS pages also responded successfully. See
[deployment evidence](evidence/2026-09-28-independent-service.json).

The twelfth bounded physical attempt tested candidate
`build_a522bd6a10a44159bf38da9c5229d9d5` after fresh accepted review and
one-use attended authorization. The host saw native USB enumeration at
17:03:22 UTC, then timed out setting configuration 1 (`-110`) at 17:03:27 UTC.
No native tty, payload or samples were obtained. Two readers independently
decoded private screen snapshots: `VAGP 2 / 3 / 2 / 2` at 65 and 149 seconds
records successful ACM setup and acceptance of the DWC3 EP0 status command;
`VRES 2 / 2 / 0 / 0` at 67 and 145 seconds shows the selected status wrapper
returned, with no post-command EP0 event observed in those snapshots. The
target remained at `launch_wait` and later displayed `10 / 1 / 8`
(`TimeoutError`, UDC state `configured`). These target-side markers do not
establish host configuration completion.

The wrapper return no longer supports a stall in its MMIO/PHY-restoration tail.
The next discriminator is controller status-TRB ownership/progress and
device/link event state versus missing EP0 completion; no role, FIFO or module
fix is established. The same checked proxy identity returned on a new owned
connection at 17:05:50 UTC, without independent reboot attestation. The
operation is reconciled as failed with its original unknown outcome retained;
the camera stopped, footage remains private, and the native qualification
session is paused. Native capture, power measurement and unattended target
recovery remain unqualified. See
[twelfth-attempt evidence](evidence/2026-09-28-native-twelfth-attempt.json) and
[service handoff](evidence/2026-09-28-twelfth-service-handoff.json).
Four technical artifacts and the summary were imported into the installed
investigation session; raw video was not. The coordinator and inspect-only
helper are active with zero observed restarts, and both earlier completed jobs
and 79,178 reported tokens were preserved. Authenticated local HTTP and private
HTTPS returned 200; an anonymous local request returned 403.

The eleventh bounded physical attempt tested candidate
`build_91cbf0b92ef6404b8483bfdd5269c77f` after fresh accepted review and
single-use attended authorization. Two readers independently decoded the
private console recording: `2 / 3 / 2 / 2` at 37, 145 and 146 seconds indicates
both ACM interface calls and serial connection returned zero, while the DWC3
EP0 status Start Transfer command reached a tracepoint reporting acceptance.
The target stayed at `launch_wait` and later displayed `10 / 1 / 8`
(`TimeoutError`, UDC state `configured`). The host still timed out setting
configuration 1 (`-110`); no native tty, payload or samples were obtained.
The `P2` tracepoint precedes the helper's return, resource-index MMIO readback
and PHY-bit restoration, and no matching status-completion callback was
observed in the retained snapshots. The twelfth attempt above tested whether
that helper returned.

The same checked proxy returned on a new owned connection at 16:14:26 UTC.
The operation is reconciled as failed with its original unknown result retained;
the native qualification session is paused and the camera stopped. The checked
USB return does not independently attest reboot. Native capture, power
measurement and unattended target recovery remain unqualified. Four technical
artifacts and the summary were imported into the installed investigation
session; raw video remains private. The coordinator and inspect-only helper
were restored with zero observed restarts, two completed jobs and 79,178
reported tokens preserved. Authenticated private HTTPS returned 200 and an
anonymous local request returned 403. See
[eleventh-attempt evidence](evidence/2026-09-28-native-eleventh-attempt.json)
and [service handoff](evidence/2026-09-28-eleventh-service-handoff.json).

The tenth bounded physical attempt used candidate
`build_7885d048ed074cf2bded9b757c5bd9a7` with a large fixed console diagnostic.
After USB observation failed in the earlier attempts, the owner's conditional
camera authorization supplied a readable screen channel. Two readers decoded
`10 / 0 / 8` at 35 seconds and `10 / 1 / 8` at 169 seconds: the target reached
launch waiting, then reported `TimeoutError`, while its UDC state said
`configured`. The host again timed out setting configuration 1 (`-110`) and
never acquired a native tty. No launch or sample payload was recovered.
The exact kernel sets its configured state before all ACM interface setup and
EP0 completion, so the screen does not establish successful USB enumeration.
The next discriminator is completion of ACM endpoint setup versus EP0 status.

The same checked proxy returned on a new owned connection at 15:30:13 UTC.
The operation is reconciled as failed with its original unknown outcome retained,
and the qualification session is paused. The camera stopped cleanly after about
182 seconds; footage remains private, with no audio. Raw video is not imported
into the investigation workspace. Four technical artifacts and the tenth-attempt
summary are retained there, with earlier jobs and accounting preserved. Native
capture, power measurement and unattended target recovery remain unqualified.
See [tenth-attempt evidence](evidence/2026-09-28-native-tenth-attempt.json) and
[service handoff evidence](evidence/2026-09-28-tenth-service-handoff.json).

The trace candidate passed source review and all 454 host tests; 53 published
artifacts and the packaged source bytes matched. An earlier exact-procedure
review was refused before a model job because external power was disconnected.
After AC returned, a new exact procedure received independent acceptance and
was used for the eleventh attempt above. See
[trace candidate evidence](evidence/2026-09-28-native-usb-trace-build.json).

The ninth bounded attempt also timed out configuring native USB. Its separate
read-only descriptor probe timed out or received protocol errors, supplying no
configuration-string stage and no samples. Its checked proxy return was
reconciled as failed while retaining the original unknown outcome. See
[ninth-attempt evidence](evidence/2026-09-28-native-ninth-attempt.json) and
[prior service handoff](evidence/2026-09-28-ninth-service-handoff.json).

The eighth attempt had likewise reached native USB enumeration and timed out
at SET_CONFIGURATION. It captured no samples, and its returned proxy was
reconciled as failed while preserving the original unknown outcome. See
[eighth-attempt evidence](evidence/2026-09-28-native-eighth-attempt.json).

The host also provides read-only USB preflight, capture summaries that recheck
framing and lineage, and explicit artifact selection for investigation turns.
See [native preflight](NATIVE-PREFLIGHT.md) and [native harness](NATIVE-HARNESS.md).
The [initial host-readiness evidence](evidence/2026-09-28-host-readiness.json)
records the earlier state before this deployment and physical attempt.

## Prior qualification history

Owner-selected coordination uses the installed Agents Orchestrator on
`gpt-6-astra` with `xhigh` reasoning. All other development and review agents use
`gpt-6-sol` with medium reasoning. One integration owner controls commits and
physical dispatch; the orchestrator assigns bounded tasks against the existing plan.

The seventh attended attempt again returned automatically to the caught proxy,
with no native samples. Its log/video are retained and the original unknown is
reconciled as failed. Independent Linux source inspection identified a concrete
gadget bug: configfs resolves symlink targets from process cwd, while the target
used a path relative to the link's parent. The function link now uses its absolute
path. A regression reproduced the old `ENOENT`; all eight native boot tests pass.
Clean source `4c2855b` has now produced candidate `build_2c9d5eff9bd947a1ac8c575b8b993a9a`.
Stored artifact hashes/sizes and the packaged fixed bootstrap bytes match; kernel,
DTB and collector are unchanged. The remaining delivery check is a real
three-sample capture and proxy return. The first reviewed launch expired before the owner replied; no dispatch occurred.
Exact review accepted replacement `2366a423…eb6d2c5` with the same image and bounds;
its authorization is pending. See [refresh evidence](evidence/2026-09-27-native-launch-refresh.json). See [build evidence](evidence/2026-09-26-native-configfs-build.json).
See [seventh-attempt evidence](evidence/2026-09-26-native-seventh-attempt.json).

The sixth separately approved attended attempt booted Linux and returned to
proxy; the watcher caught it and the owner confirmed no manual reboot. No native
samples were captured. Its 23,960-byte boot log and 30.937-second private webcam
video are retained. The video shows diagnostic lines, but the exact failure stage
and type remain too blurred to transcribe reliably. The original unknown result
is retained and reconciled as failed. The spent helper correctly withdrew launch
capability after this attempt while retaining proxy observation. All six test
approvals are consumed. See [sixth-attempt evidence](evidence/2026-09-26-native-sixth-attempt.json).

The exact candidate kernel includes `TER16x32`. Fixed boot arguments now select
that font to address the unreadable console evidence; 30 backend/launcher checks
passed. The target image is unchanged. Prior font selection and actual readability
remain unverified; the changed helper configuration needs fresh exact review and
attended approval. See [font evidence](evidence/2026-09-26-native-console-font.json).

Fresh exact review has now accepted font proposal `8acb0a44…e50ad30c`, with a
fresh owned helper and unchanged target image. Its subsequent attended approval
was consumed by the seventh attempt above. Earlier clock/recording-sequence review issues
are retained as history. See [review evidence](evidence/2026-09-26-native-font-review.json).

The fifth approved attended attempt stopped at the host helper before any boot
log was created. The helper from the fourth attempt had spent its one launch,
but still advertised the launch capability; its refusal surfaced as a transport
EOF. The 168 ms dispatch, unchanged proxy connection and private webcam recording
support this diagnosis. Zero native samples were captured. The original unknown
outcome is retained and reconciled as failed. The camera armed before dispatch
and stopped cleanly. All five approvals are consumed. See
[fifth-attempt evidence](evidence/2026-09-26-native-fifth-attempt.json).

Spent helpers now stop advertising native execution while keeping the returned
proxy available for observation. The one-launch guard is unchanged. A regression
reproduced the defect before the fix; 35 focused host checks passed afterward,
including refusal before adapter execution or approval consumption. The next
test requires a fresh helper and newly reviewed attended approval.

Before the sixth attempt, the spent helper stopped normally and a fresh proxy was acquired.
Exact review accepted `6b077c88…c9a9d4d` for the unchanged target candidate and
webcam scripts. The owner then approved the sixth test and confirmed attendance;
its outcome is above. See [review evidence](evidence/2026-09-26-native-fresh-helper-review.json).

The fourth attended test failed to capture native samples, but the continuous
watcher caught and held the returning proxy at 18:05:39 UTC. The owner confirmed
it returned by itself, without a manual reboot, and reported Linux penguins/logs
with M1Lab errors that passed too quickly to read. The full 23,960-byte boot log
survived and was published privately. The original `unknown_effect` is retained
and the attempt is reconciled as failed. Kernel handoff and USB disconnect are
logged; the exact native failure stage remains unknown. Bounded image/runtime
inspection identified no concrete packaging defect. The next useful evidence is
a recording of the existing target diagnostics during a separately approved run.
See [fourth-attempt evidence](evidence/2026-09-26-native-fourth-attempt.json).

The owner requested the ThinkPad webcam for the next diagnostic observation.
Its preview now contains the full console. The same candidate has a freshly
accepted exact proposal `d16b1906…e21ccef`: host camera frames must be captured
before dispatch, recording is bounded to 510 seconds/1 GiB, and explicit host
cleanup stops/reaps it. Two rejected preparation reviews remain recorded;
the corrected script bytes and procedure matched. The owner subsequently approved
one test and confirmed attendance; its fifth-attempt outcome is recorded above. See
[webcam preparation](evidence/2026-09-26-native-webcam-preparation.json).

The next candidate adds diagnostics for the demonstrated missing-evidence gap:
private boot logs survive helper death, and target startup emits fixed stage
markers with a five-second failure-only hold before its existing reboot request.
Thirty host backend/launcher checks and 31 target boot/capture/identity checks
passed; both independent crossreviews are clear. Console visibility on the Mac
is still unverified. Clean source `350819d` produced diagnostic candidate
`build_7307a7fbd37d412681afe9a3a4259fbb`; independent package review passed all
36 checks. Fresh exact review accepted procedure `056724af…0f3546` with 90,606
reported tokens in the isolated harness session, without usage uncertainty.
Its single attended approval was consumed by the fourth attempt above.
See [diagnostic evidence](evidence/2026-09-26-native-diagnostics.json)
and [candidate evidence](evidence/2026-09-26-native-diagnostics-build.json).

The third attended native attempt exposed a return-watching gap: proxy USB
appeared for about five seconds while the helper was still waiting for the
native channel. No samples were captured. The host wait was stopped; a bounded
catcher connected after the owner's manual reboot. The attempt is reconciled
as failed with its original unknown outcome retained. Continuous proxy-return
observation during native startup/capture is now implemented; 23 focused backend
checks pass and independent review found no blocking issue. The next gate is
fresh exact review and a separately approved physical test. See
[third-attempt evidence](evidence/2026-09-26-native-third-attempt.json).
The [watcher evidence](evidence/2026-09-26-native-return-watcher.json) remains host-only.

The first attended native attempt remains reconciled as failed. The owner-approved
single retry used the corrected device environment, a fresh exact review,
attendance approval and proxy check. It ended `unknown_effect`: zero captured
samples and no observed proxy return. The boot client reached kernel handoff
preparation, then failed initializing terminal I/O; target execution and stop
remain unverified for that attempt. The helper stopped normally. The owner's
subsequent manual reboot restored a responsive identity-bound proxy at 16:59:12 UTC;
the retry is now reconciled as failed with its original unknown result retained.
No further native boot was dispatched.
See [first-attempt evidence](evidence/2026-09-26-native-first-attempt.json) and
[retry evidence](evidence/2026-09-26-native-retry.json). The terminal integration
fix now passes 19 focused host checks, including real pySerial Miniterm over a
local loopback port. It supplies a private PTY and requests graceful console exit
after capture; fresh review and approval are required for its changed configuration.
The subsequent third-attempt outcome is recorded above. See
[fix evidence](evidence/2026-09-26-native-terminal-fix.json).

Current owner scope: build and verify the harness end to end using the m1n1
connection. Scientific investigation remains stopped. Source `520d05b` produced
a pinned J313 candidate through the session-linked builder; an independent
assembly matched all seven output digests. Eight focused native CLI/launch
checks passed. The identity-enabled candidate at `3f75558` also completed
ARM64 emulated collection through artifact publication; 54 combined native
checks passed at that checkpoint. The integrated attended path now passes
313 host tests; see qualification records for the command and scope.
The attended coordinator/helper native path is implemented, with explicit
CLI commands, immutable artifact staging, bounded boot/capture, raw retention
and observed proxy-return checks. It remains opt-in and unqualified pending
the real Mac round trip. Persistent physical helper inspection passed
on earlier source `b5b420d`. Separate helper service packaging is prepared;
installed service `f560929` and the paused lab usage hold are unchanged.

| Area | State | Evidence or next gate |
|---|---|---|
| Durable coordinator | Host implemented | SQLite journal, revisions, phase-aware budget exhaustion, exact approvals, reconciliation, and exclusive lease for standalone Codex turns |
| Replay experiment cycle | Host demonstrated | `m1lab replay-demo` records read-only and approved mutating paths, immutable scientific evidence and matching operator readback |
| Scientific records and reports | Host implemented | Versioned immutable records, frozen paired 10% / 95% decision rule, and Markdown report generation from validated records with provenance and explicit qualification limits |
| Codex scientific decision loop | Advisory brief, cost comparison, typed hypothesis/decision publication, draft/review boundary, redesign checkpoint gates, bounded/redacted evidence imports, one primary plus up to two budgeted helper jobs, and linked Markdown research reports implemented | Five synthetic science cases passed on the T480, covering decision lineage, durable briefs, redesign, a scripted change of leading explanation with recorded closure, and a scripted lower-cost discriminating proposal that persists but cannot dispatch without review. M3 remains partial: live Codex experiment selection/cost comparison and live provider resume are not demonstrated; synthetic reopen/resume preserves evidence, accounting, and read-only authority; live scientific decisions remain unqualified |
| Codex runtime | Standalone authenticated host-only turn qualified; approved service startup fix and live cancellation demonstrated | Release `10934e9` completed job `job_c4b06fe7f5f44710926be4d698c0f8b7` using pinned Codex 0.156 and `gpt-6-sol` medium, reporting 19,816 tokens. Later service chat exposed a Bubblewrap conflict with `RestrictSUIDSGID`; the controlled startup probe passed, exact owner approval was received, and release `f560929` is active and its controlled job reached `interrupted`. The session is paused with released reservations; missing provider usage correctly blocks new work. Synthetic transport cleanup, cancelled shutdown, reopen/resume, and failed-profile refusal now pass; the standalone OS sandbox passed synthetic canaries. Live interrupted-turn usage reconciliation, provider resume, and complete enabled-tool qualification remain pending |
| Owner CLI | Host implemented | Lifecycle, budgets, approvals, events, artifacts, jobs, operation and usage recovery, export, backup, replay and diagnostics |
| Owner web UI | Host rendered | Four responsive views, revisioned commands, SSE and local/Tailscale identity modes; real temporary HTTP tests cover owner/CSRF/origin checks, uncached views, duplicate/stale commands, cursor replay, reconnect, and snapshot recovery. Sampler failure now renders unavailable readiness. Approval cards expose recovery steps and risk rationale |
| Owner push notifications | Stable service-owned VAPID key configured on the T480; owner reported iPhone enrollment and HTTPS push config confirmed `enabled=true`, `enrolled=true` | Seven stubbed delivery cases cover generic payloads, deduplication, expiry/revocation, and workflow preservation; actual phone delivery, revocation, and offline behavior remain unqualified |
| ThinkPad service deployment | Release `f560929` installed on the T480 after exact owner approval and a verified backup; service active with zero observed restarts, HTTPS 200, and iPhone enrollment retained. Controlled cancellation ended with the session paused and a usage hold. Earlier update/rollback and isolated/live backup restore passed | [Operations guide](OPERATIONS.md); interrupted-turn usage reconciliation/recovery, uninstall, and longer availability checks remain pending |
| ThinkPad host inventory | T480 hardware, firmware, OS, CPU, memory, and available build tools observed on 2026-09-26; latest full suite: 313 passed, including native collector/acquisition/import, synthetic science, interruption accounting, maintenance, host-readiness faults, notification contracts, and HTTP owner controls; replay demo previously passed | These are host checks; USB enumeration and protocol version were separately observed, while exact cable/port mapping, target binary provenance, and recovery remain pending; [inventory](LAB-INVENTORY.md) |
| ThinkPad lab availability | T480 diagnostics observed AC, 62–63 °C, and about 7.7 GiB free. With release `3c49b9e`, opt-in logind `sleep:idle:handle-lid-switch` block inhibition was held while the service ran, released on stop, and absent after lab mode was turned off; `/overview` returned HTTP 200 before and after | Seven injected-readiness cases verify admission refusal, durable pause, interruption requests, reservation release, and no auto resume. Actual lid behavior, AC-loss, thermal-pressure, low-disk, shutdown, and longer availability still need T480 qualification |
| Tailscale on ThinkPad | Serve configured on the T480 on 2026-09-26 with exact owner login; HTTPS `/overview` returned HTTP 200, missing/wrong identity headers returned 403 on loopback, service remained active, and no public Funnel entry was enabled; iPhone enrollment subsequently confirmed | Tailnet policy and full iPhone workflows remain unqualified |
| iPhone 12 mini | Owner reported enrollment; server confirmed an active subscription | Verify all views, Home Screen behavior, reconnect and approval handling |
| ThinkPad-to-Mac transport | Direct setup and bounded helper/IPC inspection passed; full transport unqualified | USB-A to USB-C at topology `1-1`, USB `1209:316d`, interface `00`, hashed serial binding, chip `0x8103`. One-shot and persistent helper checks completed fixed read-only requests and exited cleanly, with socket removal and owner-lock release verified for the persistent path. Target version banner previously matched host release tag `v1.6.1`; exact target binary, boot epoch, reviewed coordinator dispatch, failure/recovery and native channel remain pending; see [probe evidence](evidence/2026-09-26-proxy-helper.json) |
| Hardware-helper boundary | Typed bounded IPC now includes inspect-only snapshots; fixed physical observer and one-shot supervised probe implemented | 42 socket/deny-guard cases, 11 PTY transport cases, 13 observer cases, 14 supervisor cases and 4 coordinator/IPC cases pass. Durable intent refusal survives actual process death; startup/request/cleanup stalls are bounded. Physical persistent inspections and normal shutdown passed, retaining no capabilities, no boot epoch and `qualified=false`. Separate service packaging is prepared with coordinator process binding and source maintenance guards; actual unit permissions/lifecycle, qualified dispatch and recovery remain pending; see [harness contract](PROXY-HARNESS.md) |
| Live m1n1 adapter | Autonomous selection disabled; explicit attended native qualification implemented | Exact reviewed artifacts and single-use attendance approval required. Physical native channel, return and recovery remain pending |
| Native run manifests and result channel | Host acquisition CLI and RAM-only J313 candidate implemented | Synthetic collector/acquisition/import checks cover complete/partial/unknown results, deadlines and retained bytes; 54 combined native checks pass. Actual packaged ARM64 collector streamed complete synthetic data plus observed Linux self-report into artifact storage. One-shot ACM ownership/exchange passes synthetic PTY checks. Physical source/timing, independent boot identity, reviewed dispatch and return/recovery remain pending. Explicit `native-run` now supplies the attended qualification route; normal startup remains disabled |
| Reproducible target builds | Actual pinned candidate assembled and session-linked at `520d05b` | Independent assembly matched all seven output hashes. Kernel/DTB/modules and 37 userspace packages are pinned; input bytes, provider metadata, source/recipe/tool and output digests are recorded. This reproduces assembly from signed binaries, not the provider kernel compilation. No qualified known-good image or physical return yet; see [build evidence](evidence/2026-09-26-native-build.json) |
| Power measurement | Unqualified | Establish sensor provenance, energy boundary, cadence, noise and observer effect |
| Real investigation | Not started | Requires the live transport and measurement gates |

The first release remains incomplete until the physical gates and one real,
bounded, multi-cycle investigation are complete. Replay evidence must never be
used to claim an M1 power improvement.

The EP0 follow-up candidate adds correlated status-wrapper entry/return probes
and a separate raw-event page. Its exact source review and all 500 host tests
pass; 53 published artifacts and packaged source bytes match. Physical behavior
of the new event page remains unverified. See
[EP0 candidate evidence](evidence/2026-09-28-native-ep0-build.json).
