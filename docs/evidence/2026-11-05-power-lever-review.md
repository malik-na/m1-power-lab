# Power lever review, 2026-11-05

Output of a source-and-docs investigation (six lenses: CPU idle, display coprocessors, PMGR domains, PCIe/Wi-Fi/BT, the s2idle path, periodic wakers) against linux-aurora @ b798f2b, each proposal checked by two adversarial reviewers (mechanism, safety). No experiment in it had been run when it was written; measured outcomes are recorded in [STATUS](../STATUS.md). File:line references are to that kernel tree.

# M1 Air (J313) power-lever experiment queue

Everything below assumes the following:
- Run only after the current measurement finishes, and one experiment at a time.
- Discard any block that spans a Wi-Fi reassociation, and do not pin or alter the network config.
- Lab (maclab) boots run untuned. Compare a Lab boot only with another Lab boot. Experiments that need a boot per arm use normal boots with m1power-tune applied, at least 3 boots per arm, in random order.
- Where the expected saving is below the ~10 mW A/B resolution, the deciding signal is the mechanism (IRQ rate, `s2idle_pd_entries`, `domains_stayed_on`), not watts.
- Verdict tags:
  - KEEP: both verifiers kept the proposal.
  - SPLIT: one verifier refuted it, the other kept it.

## Ranked queue

### 1. Wi-Fi: shorten the post-traffic awake tail from 2000 ms to 200 ms

- **Verdict:** KEEP. Idle only.
- **Saving:** 10–40 mW idle (most likely 15–30). Sleep: 0.
- **Mechanism:** brcmfmac clamps cfg80211's default timeout of -1 to 2000 ms (`cfg80211.c:3478-79`), while the firmware default is about 200 ms.
- **Setup:**
  ```
  IF=$(basename $(dirname $(ls -d /sys/class/net/*/phy80211|head -1)))
  ```
- **Read** (the subcommand must be `0x1`; the value is bytes 5–8 of the reply, little-endian: `d0 07 00 00` = 2000, `c8 00 00 00` = 200):
  ```
  iw dev $IF vendor recv 0x001018 0x1 0x06 0x01 0x00 0x00 0x10 0x00 0x00 0x00 0x14 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x70 0x6d 0x32 0x5f 0x73 0x6c 0x65 0x65 0x70 0x5f 0x72 0x65 0x74 0x00 0x00 0x00
  ```
- **Apply** (persistent route; `CONFIG_CFG80211_WEXT=y` is set). This call also forces power save on, so apply it after the `wifi_ps` knob and never inside a `wifi_ps=off` arm:
  ```
  python3 -c 'import fcntl,socket,struct,sys;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);fcntl.ioctl(s,0x8B2C,struct.pack("16siBBH8x",sys.argv[1].encode(),200000,0,0,0x2000))' $IF
  ```
- **Revert:** the same command with `2000000`. A reboot also restores it.
- **Knob arms:** 200 vs 2000 ms. Add 50 ms if 200 wins. Read the value back after every resume; a phy re-register resets it to 2000.
- **Risk:** Downlink latency rises by up to one beacon interval. No crash path. The revert is local.
- **Confirms:** readback shows 200 and paired idle power drops by at least 10 mW.
- **Kills:** readback shows 200 but the result is null over 6 or more pairs. That would mean this firmware ignores the setting.

### 2. Diagnostic: hardware power-domain state and genpd hold audit

- **Verdict:** KEEP. Idle and sleep.
- **Saving:** 0 mW by itself. It gates items 7, 8 and 12 and the dead-end checks.
- **Apply:** add a read-only debugfs file `pmgr_ps` to `target/kmod/m1power.c`:
  - Get a regmap with `syscon_node_to_regmap()` for each `apple,pmgr` node (0x23b700000 and 0x23d280000). Never use plain `ioremap`; it must be non-posted or a regmap.
  - Iterate the `apple,pmgr-pwrstate` children whose status is okay, and `regmap_read(reg[0])`.
  - Print target `v&0xf`, actual `(v>>4)&0xf`, min `(v>>16)&0xf`, auto `(v>>28)&1`, bit 11 BUSY (m1n1 calls it PARENT_OFF), and the WAS_CLK/WAS_PWR flags (bits 9/8).
  - Sample about 200 times at 20–50 ms with jitter. Report the fraction of samples with actual < 0xf.
  - Add the same snapshot in `wdt_irq_handler` (`m1power.c:308`, `IRQF_NO_SUSPEND`) to capture the state during s2idle. Treat it as an upper bound.
  - Never read the regmap debugfs `registers` file.
- **Also run:**
  ```
  cat /sys/kernel/debug/pm_genpd/pm_genpd_summary
  grep -l . /sys/kernel/debug/pm_genpd/*/devices
  cat /sys/kernel/debug/devices_deferred
  dmesg | grep -E 'sync_state\(\) pending|deferred-off|always-on domain'
  find /sys/devices -path '*power/wakeup' -exec grep -l enabled {} +
  ```
  Mailbox IRQ rates over 60 s, matched by name:
  ```
  grep -E '(231c08000|271c08000|206408000|24a408000)\.mbox-(recv|send)' /proc/interrupts
  ```
  After a resume, read fpwm1/sio/sio_busif at offsets 0x1e0/0x1c8/0x1c0. This feeds item 12.
- **Revert:** reinsert the previous `m1power.ko`. Do this only when no block or armed wake timer is running.
- **Risk:** Very low. Reading only the device-tree-listed offsets is safe.
- **Kills:** any domain that reads actual ≤ 4 more than 90% of the time, or is gated in the s2idle snapshot. Drop that domain's gating lever.

### 3. Diagnostic: wake attribution and per-wake cost calibration

- **Verdict:** KEEP. Idle (and a sleep cross-check).
- **Saving:** 0 mW. It bounds the waker hunt; expect about 5–25 mW total.
- **Trace (60 s, display off).** Save `buffer_size_kb` and `trace_clock` first. Events:
  `power:cpu_idle irq:irq_handler_entry ipi:ipi_entry ipi:ipi_send_cpu csd:csd_queue_cpu csd:csd_function_entry timer:hrtimer_expire_entry timer:timer_expire_entry workqueue:workqueue_execute_start sched:sched_waking sched:sched_wakeup block:block_rq_issue`
  - Without the csd events, IPI1 cannot be attributed; `ipi_send` alone always shows the generic callback.
  - State 0 = WFI, 1 = PD. Attribute each idle exit to the next event on that CPU.
  - Report results per cluster (cpu0–3 E, cpu4–7 P).
- **Same session, gates item 11:**
  ```
  bpftrace -e 'kretprobe:rcu_needs_cpu /retval/ {@[cpu]=count();} interval:s:30{exit();}'
  ```
- **Calibration:** template unit `m1lab-waker@CPU-RATE.service` running `/usr/local/lib/m1lab/waker.py`. The script sets timer slack with `prctl(29,1)`, pins to the CPU and sleeps 1/rate in a loop. Arms: `service:m1lab-waker@0-50`, `@0-1000`, `@4-50`, `@4-1000`, each against off.
  - Use 50 Hz, not 100 Hz: 50 Hz keeps CPU PD eligible, 1000 Hz forces WFI.
  - Log `cpuN/cpuidle/state1/usage` during each arm.
  - The original one-line Python command has a SyntaxError.
- **Revert:**
  ```
  echo > set_event   # then restore saved trace_clock and buffer_size_kb
  systemctl stop 'm1lab-waker@*'
  # remove the unit and script, then: systemctl daemon-reload
  ```
- **Risk:** None to stability. Do not measure power during the trace window.

### 4. Fabric/DCS performance state: discovery only

- **Verdict:** SPLIT. Four lens versions, each with one refuting and one keeping verifier.
- **Applies to:** both idle and sleep. This is the only lever class large enough to matter.
- **Saving:** 0 if firmware (PMP v1) already owns these registers, which is plausible. Otherwise 50–200 mW in sleep and 0–150 mW at idle with the display off.
- **Status:** Not a lever until the register is identified.
- **Known corrections:**
  - The "AIC-relative" match is false: 0x23b204000 is AIC+0x104000, while the t6001 misc block is at AIC+0x10c000.
  - t8103 `perf-regs` point at pmgr+0x34000/0x78000/0x7c000 and 0x23d2b4000, not at reg[31].
  - 0x23b70c000 is the ANE power-state block. Exclude it.
  - On J313 the idle governor can never engage: `isp_sys` is disabled, so `voters_ok` is false, and the internal panel is not a voter.
- **Step 0a, offline:**
  - Ask Asahi or dd-dreams (base-M1 PMP v1 work) whether t8103 has a host-writable fabric/DCS performance-state block.
  - Alternatively, trace macOS writes with the m1n1 hypervisor on 0x23b204000–0x23b208000 and the `perf-regs` targets.
- **Step 0b, attended, read-only:**
  ```
  cat /proc/cmdline   # needs panic=N
  for o in $(seq 0 1024 15360); do busybox devmem $((0x23B204000+o)) 32; done
  ```
  Sample at 1 s: idle with display off, idle with display on, during `stress-ng --cpu 8`, and under GPU load.
  - Values that move by themselves: firmware owns them. Stop; saving is 0.
  - Static words with desired == actual (bits 3:0 == 7:4): go to 0c.
- **Step 0c, attended Lab boot:** write the fabric value one step lower by hand. Check that bits 7:4 follow, and that the panel, NVMe and Wi-Fi survive for 60 s. Restore the value. A paired idle A/B is possible this way.
- **Step 1, only after 0c passes:**
  - Patch `apple-pmgr-misc.c:451` from `!base` to `IS_ERR(base)`.
  - Add a node inside the soc bus, which carries nonposted-mmio, with both `reg-names`, `apple,fabric-min-ps=<traced>` and `apple,dcs-min-ps=<boot DCS>`.
- **Revert:** boot the old DTB. The driver suppresses bind attributes, so it cannot be unbound.
- **Risk:**
  - SError or panic from a wrong address.
  - An s2idle hang with no automatic recovery: the m1power wake timer never sets `RESET_EN`, and apple_wdt stops in s2idle. Every sleep test needs someone at the machine.
  - DCS lowered too far: no resume.

### 5. Wi-Fi PM_MAX (PS-Poll) on top of item 1

- **Verdict:** KEEP. Idle only.
- **Saving:** 0–30 mW on top of item 1. Probably mostly overlaps item 1.
- **Safety net first** (restores PM_FAST after 10 minutes):
  ```
  systemd-run --unit=m1-pm-revert --on-active=600 /usr/bin/iw dev $IF vendor send 0x001018 0x1 0x56 0x00 0x00 0x00 0x04 0x00 0x00 0x00 0x14 0x00 0x00 0x00 0x01 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x02 0x00 0x00 0x00
  ```
- **Apply:** the same `vendor send` with last value `0x01`.
- **Verify** (GET_PM; the value is bytes 5–8, `01` = PM_MAX):
  ```
  iw dev $IF vendor recv 0x001018 0x1 0x55 0x00 0x00 0x00 0x04 0x00 0x00 0x00 0x14 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00 0x00
  ```
- **Revert:** raw SET_PM with value `0x02`, then `systemctl stop m1-pm-revert.timer`. Do not toggle power save off and on for this; that path resends pm2_sleep_ret.
- **Risk:** About 100 ms extra downlink latency, possible stalls with the access point, and possible lab-agent timeouts. Revert before any sleep test: PM_MAX survives resume.
- **Kills:** null against item 1's arm, or ping loss.

### 6. AOP ambient-light-sensor stream during s2idle

- **Verdict:** KEEP. Sleep (idle effect is negligible).
- **Saving:** 2–6 mW in sleep. The mechanism signal is very clear.
- **Pre-check:**
  ```
  lsmod | grep -w aop_als
  cat /sys/bus/iio/devices/*/name
  ls /lib/firmware/apple/aop-als-cal.bin*
  ```
  If `aop_als` is not bound, stop. Cheap attribution: compare 30 s deltas of `24a408000.mbox-recv` with the sensor covered and under bright light.
- **Apply:** boot once with `modprobe.blacklist=aop_als` (edit the entry at the bootloader for one boot; no initramfs rebuild). Arms go on separate boots in random order, 2 sleeps per boot. Do not use A,A,B,B within one boot: unbinding does not disarm the sensor (`aop_als.rs:403-405`).
- **Revert:** boot without the parameter, or `modprobe aop_als`, which re-arms the sensor immediately.
- **Risk:** Low. Loses the ambient light sensor only.
- **Confirms:** cpu0 `s2idle_pd_entries` falls from about 1500–4000 to about 1–3, and `mbox-recv` goes to about 0.
- **Kills:** the rate is unchanged. Try `aop_las`; if that also changes nothing, the traffic comes from the AOP core itself. Stop.

### 7. Disable the WFI idle state on the E cores

- **Verdict:** cpu-idle lens KEEP; wakeups lens SPLIT. The split concerns the mechanism: the deployed governor is menu, and only teo stops the tick in the single-state case.
- **Applies to:** idle.
- **Saving:** 0–5 mW. Expect a drop in arch_timer IRQ/s.
- **Pre-check:** 60 s delta of `state0/time` and `state1/time` per CPU. Skip if WFI is under 5% everywhere. Also check `fuser -v /dev/cpu_dma_latency`.
- **Apply:**
  ```
  for f in /sys/devices/system/cpu/cpu[0-3]/cpuidle/state0/disable; do echo 1 > $f; done
  ```
- **Arms:**
  - (a) menu with WFI off vs menu.
  - (b) `echo teo > /sys/devices/system/cpu/cpuidle/current_governor` plus WFI off vs menu.
- **Revert:** write `0` to the same files and set the governor back to `menu`.
- **Risk:** Low. It silently disables PM QoS latency limits between 1 and 10 µs, so never persist it on a null result. Revert it before sleep A/Bs.
- **Follow-up if it wins:** set `target_residency` to 1000, then 500, at `cpuidle-apple.c:114`.

### 8. Disable wakeup on the unused USB-C controller (atc1 first)

- **Verdict:** KEEP. Sleep only.
- **Saving:** 0–10 mW.
- **Gate:** item 2's s2idle snapshot shows atc1_usb at actual 0xf.
- **Preconditions:** on battery, nothing plugged in, no external display. Check that `38304c000.mux`, `50304c000.mux`, `383000000.phy` and `503000000.phy` are bound.
- **Apply:**
  ```
  echo disabled > /sys/bus/platform/devices/502280000.usb/power/wakeup
  ```
  Use the exact device. The `wakeup:2280000.usb` substring is too broad once a cable is attached.
- **Verify:** atc1_usb is absent from `domains_stayed_on`, and dmesg is clean for `atcphy|dwc3|Failed to reach`.
- **Mandatory before any A/B:** after resume, plug a USB3 device into the left port. `lsusb -t` must show 5000M with no PIPE errors. The t8103 ATC PHY has no restore-after-power-off path (`atc.c:5431-39`), so the PHY may lose its probe-time setup. If the attach fails, reboot; replugging does not fix it.
- **Then:** repeat for 382280000.usb. Do not extend this to the PCIe, brcmfmac, tps6598x or macsmc wakeup entries.
- **Revert:** write `enabled`. If a cable was attached while wakeup was disabled, reboot (dwc3 latches `sys_wakeup` at `core.c:1779`).

### 9. Switch off the external-display coprocessor (dcpext) in the boot device tree

- **Verdict:** display lens SPLIT; pmgr lens KEEP. Idle and sleep.
- **Saving:** 0–10 mW.
- **Gate:** item 2 shows dispext_* at actual 0xf, and the `271c08000.mbox` IRQ count moves.
- **Apply:**
  ```
  pacman -S --needed dtc
  # copy the package t8103-j313.dtb to D=/root/dtb-nodcpext/t8103-j313.dtb, then:
  fdtput -d $D /aliases dcpext   # otherwise m1n1 kboot re-enables dcpext and apple-drm never binds
  for n in /soc/dcp@271c00000 /soc/mbox@271c08000 /soc/iommu@27130c000 /soc/iommu@271304000; do fdtput -t s $D $n status disabled; done
  P=$(fdtget -t x $D /soc/iommu@231304000 phandle)
  fdtput -t x $D /soc/display-subsystem iommus $P 0 0 0 0 fc000000
  fdtput -t u $D /soc/power-management@23b700000/power-controller@378 apple,min-state 0   # set 0; deleting the property leaves the bootloader's value
  ```
  Do not touch the typec endpoints; dtc fails, and the mux code already tolerates the disabled node. Then deploy and reboot:
  ```
  cp /etc/default/update-m1n1 /root/update-m1n1.bak
  env DTBS=$D update-m1n1   # keeps boot.bin.old
  reboot
  ```
  Never use a Limine or GRUB `devicetree` entry: it bypasses m1n1's device-tree fixups. Do not run `omarchy update` while this image is installed.
- **Verify:** `pm_genpd_summary` shows dispext off, eDP is connected, the backlight works, `/sys/class/typec` shows both ports, and charging works.
- **Revert:**
  ```
  cp /root/update-m1n1.bak /etc/default/update-m1n1
  update-m1n1
  reboot
  ```
  If unbootable: from 1TR or macOS, copy `m1n1/boot.bin.old` over `m1n1/boot.bin`.
- **Cost:** no USB-C display output.

### 10. Park the P-cluster (keep work on the E-cores)

- **Verdict:** SPLIT (refuted on magnitude). Idle only.
- **Saving:** 0–10 mW. The value is the measurement.
- **Gate:** P-core `state1/usage` delta. Skip if cpu4–7 wake fewer than 5 times per second.
- **Apply:**
  - Save the workqueue mask and the per-IRQ affinities to `/run/m1lab-pcore-park`.
  - `systemctl set-property --runtime {system.slice,user.slice,init.scope} AllowedCPUs=0-3`
  - Check `/sys/fs/cgroup/system.slice/cpuset.cpus.effective` reads `0-3`.
  - `echo f > /sys/devices/virtual/workqueue/cpumask`
  - `for p in $(pgrep -P 2) 2; do taskset -apc 0-3 $p; done`
  - The IRQ affinity step does nothing: AIC already targets cpu0.
- **Revert:** set `AllowedCPUs=` (empty) on the same units, `systemctl revert` them, restore the saved masks, and run taskset with 0-7.

### 11. Housekeeping wakers

- **Verdict:** KEEP. Idle only.
- **Saving:** 1–3 mW, below resolution. Do not spend an A/B slot on this.
- **Options, each low value:**
  - `sysctl -w kernel.watchdog_thresh=60` keeps lockup detection; revert with `10`.
  - Stop oomd only together with its socket: `systemctl stop systemd-oomd.socket systemd-oomd.service`.
  - Identify the disk writer with item 3's `block_rq_issue`. Run that with the host's SSH session idle, since the harness itself may be the writer.
- Drop the `dirty_writeback` arm. The steady write rate looks like fsync, which that setting does not batch.

### 12. RCU offload and workqueue power_efficient (boot arms)

- **Verdict:** KEEP. Idle only.
- **Saving:** 0 ± 5 mW. Offloading alone may cost power.
- **Gate:** item 3's `rcu_needs_cpu` count × 3 should be well above 100/s. Otherwise skip.
- **Apply:**
  ```
  sed -i -E '/^GRUB_CMDLINE_LINUX_DEFAULT=/ s/"$/ rcu_nocbs=all"/' /etc/default/grub
  omarchy-mac-boot-update
  grep -c rcu_nocbs /etc/default/limine   # should print 1
  ```
  Check the M1's own layout first: the command line is baked into the UKI. Run `workqueue.power_efficient=1` as a separate arm. The lazy-RCU variant is a kernel build with `RCU_LAZY=y`; HZ=250 gets its own arm.
- **Revert:** restore `/etc/default/grub`, run the update, and reboot.

### 13. fpwm0/1/2 parent fix in the device tree

- **Verdict:** KEEP. Sleep only.
- **Saving:** 0 mW. This is a correctness fix.
- **Gate:** item 2's post-resume read. If fpwm1 later reaches 0xf, or sio reads 0xf during the error, the error is cosmetic, or the wrong parent is suspected. Drop it.
- **Apply:** add `power-domains = <&ps_sio>;` to `ps_fpwm0/1/2` (`t8103-pmgr.dtsi` around lines 245/253/261) and deploy via the m1n1 DTBS route as in item 9.
- **Confirms:** 5 suspend cycles with no `PS fpwm1` error and the keyboard backlight working.

### 14. Power the Wi-Fi/BT chip off in s2idle (kernel patch)

- **Verdict:** SPLIT. Sleep only. Parked.
- **Saving:** 0–15 mW net of the firmware reload (about 2 J per wake, including dark wakes).
- **The patch must:**
  - request PWREN and PERST# itself when the bootloader trained the link;
  - on resume, redo the PERST#, PORT_STATUS_READY, LTSSM START and link-up sequence, plus a 100 ms wait;
  - unbind 01:00.1 before suspend and bind it after. J313 has no hci_bcm4377 resume recovery; it is gated to j493.
- **Also required:** a post-resume watchdog that reboots if 01:00.0 has not returned within 15 s.
- **Risk:** It risks the lab's only control channel. Do not pursue unless items 1–9 are exhausted.

## Dead ends

- **Putting the internal DCP's RTKit firmware to IDLE across s2idle.** Both verifiers refuted it. `apple_rtkit_idle` has no callers, and the IDLE-to-wake path through INIT relies on a stale endpoint map. A failed wake leaves the internal panel black. Saving is about 0 because auto-PM already gates the coprocessor.
- **dcp.c patch to drop the sleep wakeup pin for dcpext.** Both refuted. `dcp->external` is true only for t6030 (`dcp.c:4328`), so the patch is a no-op on t8103. The dcpext firmware does run. A real fix needs DCP shutdown and restart support.
- **SIO/audio island.** Both refuted.
  - mca2 is Speaker Sense, held PREPARED by speakersafetyd with no clocks running: about 1 mW.
  - Unbinding ADMAC leaves its DART link's RPM_ACTIVE reference held, and the DART cannot be unbound.
  - dpa0's parent is audio_p, spi_p feeds the keyboard, and uart_p feeds serial0.
- **atc1: drop always-on plus unbind.** Both refuted. atcphy1 has no runtime PM and dcpext holds the crossbar, so atc1_usb keeps atc1_common on regardless. Already measured at -5 mW with a confidence interval spanning 0.
- **Bluetooth quiesce to D3hot.** Both refuted.
  - Wakeup is disabled by default, and the 180 mW L1-substates gain implies BT already reaches D3hot in sleep.
  - An unbound function returns to D0 at the first resume and stays there, a sleep regression of about +180 mW.
  - LTR exists only on function 0.
  - The rfkill re-test is safe but expected to be null.
- **pm_wakeup_irq attribution.** Both refuted. `IRQF_NO_SUSPEND` mailbox IRQs and the lab timer (which ends sleep through `pm_wakeup_ws_event`) never set it, so it reads ENODATA. The ledger's `irqs_during` against `s2idle_pd_entries` already does this attribution.
- **ALS unbind as a lever.** Unbinding does not disarm the sensor; only blacklisting or a patch works (item 6).
- **SMC writes.** MBSE `susp`/`slpw` risk an unclean power-off. NTAP off kills lid and button wake. No documented key drops rails.
- **Other things that cannot be powered off.**
  - Removing always-on from dcs*/mcc/smx/sbr/aic/nub_*/sep/debug*: the machine hangs.
  - disp0: its firmware cannot be restarted.
  - Runtime unbind of dispext: it tears down the whole DRM device, internal panel included.
  - apcie_gp/pcie_ref: the tunables are applied only by m1n1.
  - Userspace Wi-Fi chip power-off: nothing restarts the link (no LTSSM restart), and removing function 0 drops ASPM, about +200 mW.
- **Already disabled or already measured.** Unused PCIe ports are disabled and have no per-port domain. Root-port D3hot adds nothing. Wi-Fi rfkill in sleep was null. The gfx domain is already auto-gated.
- **No effect.**
  - `fw_devlink.sync_state=timeout`: stay_on and DEFER_OFF fall on the same domains.
  - tps6598x wakeup knob: tipd is not a hard wake source on J313.
  - kcompactd sysctl: the 500 ms wait is fixed.
  - brcmfmac console timer: off unless debug is enabled.
  - Thermal polling: there are no thermal zones.
  - Runtime `wq_power_efficient`: the parameter is read-only.
  - nohz_full shortcut: confounds the tick.
- **Not possible on this machine.** Hibernation, P-core offline, CLPC/PMC on t8103, the PMP v2 driver on M1, a deeper CPU P-state or a Linux-controlled cluster state, and frequency caps (already tested as null).

## Strategic conclusions

1. **Small levers don't add up to much.** All the per-domain, peripheral and wakeup levers together are realistically 30–60 mW idle (most of it Wi-Fi items 1 and 5) and at most about 20 mW in sleep. Knobs will not take sleep from 0.44 W to tens of mW.
2. **Fabric/DCS is the only large lever.** At 50–200 mW it is the only knob-scale lever that could matter, and its first blocker is ownership. On base M1 the fabric and DCS are probably run by PMP v1 firmware. Getting it needs one of two things:
   - identifying the registers and who owns them, via an m1n1 hypervisor trace of macOS or from Asahi's base-M1 PMP v1 work; or
   - a PMP v1 host driver, which is a large reverse-engineering project.
3. **macOS-level sleep (tens of mW) needs SoC deep sleep, not s2idle.** Specifically:
   - The application processor powers down (ACC_OVRD enDeepSleep, CYC_OVRD force_down/disWfiRetn), and wake is a CPU reset into a resume stub at the locked RVBAR, provided by m1n1.
   - A Linux suspend-to-RAM path without PSCI.
   - Full stop and restart of every RTKit coprocessor, including DCP full shutdown, which the kernel says it does not yet support.
   - The PMGR sleep sequence (SLP_S2R/SLP_DDR) for DRAM self-refresh and fabric, probably through PMP v1.

   That is multi-month upstream work and nothing to do with a userspace knob. The Wi-Fi/BT chip is not the gap: macOS keeps it powered.
4. **Practical endpoint.** Ship item 1, plus item 5 if it adds anything. Run diagnostics 2 and 3 once to close out the per-domain questions with data. Treat item 4 as the one research thread worth pursuing, and follow Asahi's PMP v1 and PSCI/RFC work for the deep-sleep path.