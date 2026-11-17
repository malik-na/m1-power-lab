# The DRAM controllers are in a different state under macOS, from early boot (2026-11-16)

## Wide reading at the commit (823 words each)

`S2R_SNAP_LIST=var/recfg/commit-snap-list-wide.json`: the earlier 249 words plus the memory-cache
controller, the eight DRAM controllers (the words the engine's program reads) and the AOP's
configuration words. macOS 13.5 (hv 135snap2) against Linux run41 (hv lx14), no read errors.
54 differ; beyond the flag and status bits already known from the 279-word reading:

| Word | macOS 13.5 | Linux run41 |
|---|---|---|
| DCS0-7 +0x7b0 (low nibble) | **0** on all eight | **3** on all eight |
| ps_dcs0-4, actual state | 4 (idle) | f |
| power gates PMGR+0x1c0d8, +0x1c0f0, bit 30 | set | clear |
| MCC planes +0x680/+0x684 | iBoot's CTRR-A bounds for that boot | (differ per boot; not a system difference) |

AON clock words and the AOP's configuration words: equal.

The engine's program reads these: sequence 7 checks `DCSn+0x7b0 & 0xf == 3` on all eight
controllers; sequence 4 checks bit 30 of power gates +0xd8, +0x108, +0xf0.

## When macOS gets there (hv run 135dcs1, `S2R_DCS=1`)

The tracer now traces the AP's writes to the DRAM controllers and the memory-cache controller, and
samples DCS0/7+0x7b0, ps_dcs0 and gate +0xd8 at every AP->AOP message. At the first sample, 2.37 s
after the guest start, +0x7b0 is already 0 and ps_dcs0 moves between f, 4 and 0 with the gate's bit
30 following: the controllers power-gate themselves when idle. Under Linux (bare metal, 4000
samples; and at the commit under the hypervisor) +0x7b0 stays 3, ps_dcs 0x1f0002ff, gates clear.

XNU's writes before that (t 0.45-1.86 s; `var/commit-state/macos135-dcs-mcc-boot-writes.json`):
a table on DCS0 (+0x580 = 0x71, +0x584 = 0x1ff, nine 5-word entries at +0x58c..+0x640); on every
controller +0xdc4 = 0x0813057f, +0xdbc = 0x01800180, **+0xc = 0x070a1100** (Linux has 0x070a0100),
+0x7a0 = 0xc0000; on every memory-cache plane +0x72c = 0xffffffff, +0x730 = 0x30000 (Linux: 0).
It also writes each ps_dcs word 0x0f0000ff then 0x1f0000ff, and ~500 words in PMGR+0x34000.

## Tried under Linux, live (bare metal, /dev/mem)

All 113 of those controller words written with macOS's values (read back as written): +0x7b0 stayed
3 and the controllers did not start gating, over 2.5 s. The machine kept running. So those writes
alone do not switch the state; what does is not found yet.

## Next

- Sample +0x7b0 from the guest's first instruction on, to find the moment it leaves 3 under macOS
  and the writes just before it (the PMGR+0x34000 block and the PMP's start are candidates).

## The recipe, and the test of it (2026-11-17)

- Per-write sampling under macOS (hv 135dcs3, `S2R_DCS=2`): +0x7b0 leaves 3 during XNU's
  `DCSn+0xc = 0x070a1100` writes (bit 12), with the auto flag already on the ps_dcs words.
- At the m1n1 proxy (no guest): bit 12 on all eight controllers alone changes nothing; adding
  the auto flag (bit 28) on ps_dcs0-7 switches all eight to 0 at once, ps_dcs0 reads 0x1000030f
  (gated) and gate +0xd8 reports. Sixteen writes; XNU's table and MCC words are not needed for it.
- Once Linux runs, the same writes do nothing: live on bare metal (with and without XNU's table,
  with the power-state words as XNU has them), and in the driver's slow part at the commit
  (**run 42**, kernel 7.2.11-run42 = s2r-rs1-135 0008e4871, `dram_gate=1`: record byte 0x9f11 =
  0x80, 0 of 8 switched; restart 29.8 s from release to Omarchy as before). Without XNU's table
  the auto-flag rewrite crashed live Linux once.
- **Switched before the guest starts** (`harness/dram_gate.py`, hv runs lx16/lx17, Linux run41):
  all eight read 0 after the script, Linux boots and runs normally, and at its commit all eight
  still read 0 (lx17 snapshot). **With real S2R (lx16) the M1 still restarted**: commit
  00:35:41.44, Omarchy on Thunderbolt 00:36:11.39 (29.95 s), no wake.

So the +0x7b0 state, though the engine's program reads it and Linux differs from macOS in it, is
not what decides the restart. What still differs at the commit with it equal (lx17 against
135snap2, 42 of 823 words): the DRAM controllers' domains are busy under Linux (ps_dcs actual f,
gates +0xd8/+0xf0 bit 30 clear) and idle under macOS (dcs0-4 actual 4, bit 30 set); the rest is
flag and status bits, iBoot's CTRR bounds and the watchdog words.

## 2026-11-17: what keeps the controllers' domains busy (lx18-lx21, proxy probes)

Not found. What the runs show, each with what it does not show. Three reviewers attacked a first
wording of these on the recorded data; the limits below are theirs.

| Reading | Run | Limit |
|---|---|---|
| After the commit, with the AOP, PMP, SIO and NVMe cores' run control written 0 and the apcie_gp, apcie_st and ans2 targets written off, each held 12 s, all eight ps_dcs read fully on in every sample. | lx19 (`harness/dcs_idle_probe.py`) | The probe printed the values before the writes only. That the stops took effect was not read back. It reads them back now. |
| The M1 left the bus 99.9 s after the commit in both lx19 and lx20 (last hypervisor log write to the M3 kernel's USB disconnect line). Watchdog 2 reads 0x23d2b0024 = 0x8f0d1800 (100 s at 24 MHz), 0x23d2b002c = 4. | lx19, lx20 | Each loss falls in the same second as a probe step (lx19: the SMC core's stop; lx20: a read in the clock block after the proxy had stopped answering). Cause not separated. In lx18 the M1 restarted 8 s after the commit with the SMC stop as the probe's last step. The probes now write both watchdogs off and leave the SMC alone. |
| At a fresh proxy, after the switch, the eight domains read fully on in 3-18 % of reads, dcs2 and dcs3 in 63-76 %. Starting the other seven cores changes nothing. | pidle1 (`harness/proxy_idle_probe.py`) | The share per controller differs between proxy boots (dcs2: 76, 15, 70 in three runs). |
| Linux's commit values written in (101 of the 129 words that differ from the proxy's): **after the 44 power-state words dcs2 and dcs3 read fully on in 95-100 % of reads and the other six in 0 %**, gate +0xd8 off in 3-5 % of reads (about 20 % before). | pidle1 | Which word does it is not known: the probe compared with a tolerance of 34 points. Not written: the eight ps_dcs words, the eight +0x7b0 words, eight counters, and four clock words (NCO 0x23b048000, dividers +0x58000/+0x5c000/+0x60000). The probe now prints every word and names the change of level per controller. |
| In a Linux boot under the hypervisor, switched before the guest starts, the last sample series with any idling is at 4.268 s (kernel time about 1.61 s, udev loading drivers). All 88 series after it read fully on. | lx21 (`S2R_DCS=3`, `harness/dcs_series.py`) | **Not established that they never idle again**: series were taken only after hooked writes, and 68 s of the 77.5 s to the commit have none (42 s without one before the commit). The tracer now has a clock (`hv_tick.py`, a series every 250 ms); not yet run on the M1. |
| Between the last idling series and the first fully-on one (4.268-4.410 s) the trace has: the NVMe coprocessor's start, SMC key traffic, ps_spi1-3 = 0xf0. Other drivers probing in those 0.14 s are not in the trace. | lx21 | |
| At a fresh proxy: after m1n1's `nvme_init` all eight read fully on in 68-93 % of reads, and are back at their shares 2 s later, also after `nvme_shutdown`. The SMC handshake, key endpoint and NTAP = 1, and the three SPI writes leave the shares where they were. | pidle2-nvme, pidle3-spi-smc | The NVMe domain was already on (ps_ans2 0x0f0023ff before and after), so this is the coprocessor's start, not a cold power-up. In pidle3 dcs2 and dcs6 were at 70 % and 81 % before the SMC steps. |
| Putting the proxy's values back after the commit: six AON words, no change; then the proxy stopped answering in the clock block. | lx20 (`harness/dcs_idle_probe2.py`) | The word that hung it is not known (last error at 0x23b05c000). The four clock words are skipped now. |

One probe output is not a reading: the first pidle2 ran on the hypervisor shell lx21 had left
(same USB identity as a proxy) and was overwritten. `harness/to-proxy.sh` now reboots any proxy it
finds before handing it out.

Open, in the order the data points: the power-state word after which dcs2 and dcs3 stop idling at
the proxy; a clocked series through a whole Linux boot; which driver loads in the 0.14 s.

## 2026-11-17: whole-SoC touch map (lx22, lx23, 135map1, 135map2)

`tools/hv-trace-kit/hv_touch_map.py` traps every page of the SoC's device space on first access
per 10 s epoch (and logs chosen ranges in full); `harness/touch_report.py` names the devices from
the Apple device tree. Linux booted to its sleep commit under it; macOS booted and idled at the
login window (its sleep entry is not captured yet).

- macOS touched 150 devices and reg blocks, Linux 97. 284 pages only macOS, 33 only Linux.
- **macOS keeps two things running that Linux never does** (full log, 135map2 against lx23:
  929,672 accesses in 231 s against 93 in 80 s):
  - every core writes `0x23bc34000` (in the PMP's block) about 5,500 times a second in total;
    cores 0-3 write 1, cores 4-7 write 2;
  - 2-3 times a second core 0 writes `0x20010000c=1, 0x200100014=1, 0x200014050=2,
    0x20010000c=0, 0x200100014=0` (memory cache controller).
  Linux writes `0x20010000c`/`0x200100014` once at its sleep commit and the rest never.
- Also only under macOS, in most epochs: 22 temperature-sensor pages, AON words `0x23d2a8000` and
  `0x23d2dc000`, the display coprocessor's mailbox.
- Not tested: whether either of the two lets the DRAM controllers idle.

### macOS's sleep entry under the touch map (135map3, 2026-11-17 02:23)

Sleep clicked at the login window; commit 61.1 s into the run. In the last 0.23 s before the
commit macOS, on core 0, in the memory controller's space: (1) `0x20010000c=1, 0x200100014=1,
0x200001c00=0`, both back to 0, 27 reads of `0x200001c04` down to 0; (2) clears `0x200158000`
(`0x3fcffffffff`), `0x200024000` and `0x200024008` (`0x1ffff`) one bit at a time; (3) clears
`0x200200584` (`0x1fe`) one bit at a time; (4) writes 0 to `0x200027000`, `0x200067000`,
`0x2000a7000`, `0x200155000` and to `+0x21008`/`+0x21000` of the four blocks at
`0x200000000/40000/80000/c0000`; (5) writes **`DCSn+0x7a0 = 0` on all eight DRAM controllers**.
Linux's commit (lx23) does step 1 only; its sleep driver has none of the words of steps 2-5.
Whether steps 2-5 decide the restart is not tested. Values in order: private
`var/map-20261117/macos-sleep-entry-memory-controller.json`.

A second capture (135map4, 02:30) with seven minutes of settled idle before the click gives the
same final sequence: **135 writes, identical words, order and values in both captures**. The sleep
entry lasts about 21 s; 80 of the 130 device pages it touches are never touched in 5.5 minutes of
idle before it. Ordered values: private `var/map-20261117/macos-memory-controller-shutdown.json`.

### Run 43 (2026-11-17 02:53): the memory controller quieted as macOS does: still restarts

Kernel 7.2.11-run43 = s2r-rs1-135 5804b4c3d (local commit), package sha256 5d6c5979…, run 41's
set plus `apple_s2r_rs.mem_quiet=1` (no `dram_gate`): after the cache flush the driver clears the
pending status bit of the four event blocks, writes `MCC+0x55000`, the blocks' enable and mask
words and `DCSn+0x7a0` to 0, in macOS's order.

- Bare metal, real entry: Thunderbolt link dropped 02:53:49.87, the M1 back as Omarchy
  02:54:19.65: **29.8 s, the same restart as runs 36-42**. Postmortem: restart 'wake-restart',
  power chip 0x0201 00 -> 01, FAIL as a sleep-and-wake cycle.
- That the driver made the writes was checked under the hypervisor with the memory-controller
  space logged in full (lx24, same kernel, non-real commit): enables 0x700 and masks -> 0,
  `MCC+0x55000` 0xffffffff -> 0, `DCSn+0x7a0` 0xc0000 -> 0 on all eight, status 0x4000000 -> 0 on
  three blocks; the fourth block's status read 0x14000000 before and 0x10000000 after (bit 28
  stays; macOS never shows it). The counters' enable words read 0 already.
- So these words, set as macOS sets them before its commit, do not decide the restart on their
  own. Not done in this run: macOS's two idle-time patterns (the PMP word 0x23bc34000, the
  memory-cache burst with 0x200014050), and bit 28 of the fourth block's status.

### Full capture of macOS's sleep and wake under the hypervisor (135full1, 2026-11-17 03:26-03:35)

`hv_touch_map.py` with every device access logged from 03:29:33 (about 21,000 a second; macOS's
own idle patterns ran at their usual rate under it), real sleep passed through, register
snapshots at the switch (793 words) and at the wake (265 words).

- Sleep clicked at the login window; USB link lost 03:32:31, m1n1 back 03:32:32: **the sleep
  lasted about one second.** Wake status `+0x20 = 0x400000`: wake source 54, the power chip's
  interrupt line. The same as the run of 2026-11-16 (`docs/evidence/2026-11-16-hv-macos135-s2r`,
  0.65 s). The hypervisor's alarm was set to 900 s. What raised the line is not read yet.
- Captured: 4,795,686 accesses before the wake (3 min of idle, the sleep entry) and 1,173,329
  in the 2.5 min after it. Not captured: a snapshot at the commit (the hook on a CPU leaving the
  guest does not run when the sleep is passed through), and a sleep of any length.
- So macOS under the hypervisor has only ever been seen asleep for about a second.

### The one-second wake was our hypervisor's doing; with it fixed macOS sleeps 15 minutes (135full3, 2026-11-17 03:48-04:11)

- **Cause, read:** macOS's last act on the power chip's bus controller before its sleep is to
  leave one interrupt enabled (`0x23d0d9338 = 1`, status `0x23d0d9378` bit 0: a reply has
  arrived) with that status acknowledged (135full1, the last bus accesses before the commit).
  m1n1's commit path (`src/hv/hv_cpu_power.c`) then sends up to nine commands of its own (stage
  markers, the wake handler's address, the alarm) and `src/spmi.c` never writes the status
  words. At a bare proxy `0x23d0d9378` reads 1.
- **Fix, in the running image:** `harness/spmi_ack_patch.py` makes the commit path's last
  power-chip write (a debug breadcrumb) a write of 1 to `0x23d0d9378`. m1n1's code is
  read-only (a plain write is dropped) and the proxy does not survive the MMU being off (the Mac
  reset itself), so a 13-instruction routine run on the Mac does the write.
- **Result:** Sleep clicked at the login window; last logged access 03:53:28; **no wake for
  900 s**; `HV: S2R wake entry` 04:08:28 with wake status `+0x20 = 0x400000` (source 54), 900 s
  after the commit = the alarm the hypervisor set. macOS re-entered and ran on at its usual rate
  (about 21,000 logged accesses a second for the 2.6 min recorded).
- **Capture** (`runs/20261116-mac135/touch-135full3.jsonl`, 929 MB, private): 212 s of idle as a
  touch map, then every device access: 109 s to the commit (3,602,038 accesses), the wake
  snapshot (265 words), 2.6 min after the wake (3,478,759). Snapshot of 793 words before the
  full log. No snapshot at the commit (that hook does not run with a real sleep).
- The Mac's USB device stayed listed on this Mac through the sleep: "still enumerated" does not
  mean "awake".
- Not known: whether a key press wakes it (the alarm came first or the key did nothing).

### Second full capture: 320 s asleep, woken by the spacebar (135full4, 2026-11-17 04:15-04:28)

Same setup as 135full3 (patched hypervisor, every device access logged from 04:19:15), **no wake
alarm** (`ALARM=0`: "left as macOS set it").

- Sleep clicked at the login window; last logged access 04:19:58. Nothing for five minutes.
- Signal to the operator 04:25:08; he pressed the **spacebar**; `HV: S2R wake entry` 04:25:18.6,
  **320 s after going down**. Wake status `+0x20 = 0x400000`: source 54 again, so a key press
  also arrives through the power chip's interrupt line.
- macOS re-entered and ran on (22,000-26,000 logged accesses a second for the 2.7 min recorded).
- Capture `runs/20261116-mac135/touch-135full4.jsonl` (813 MB, private): 227 s of idle as a
  touch map, then every access: 43 s to the commit (2,232,589), the wake snapshot (265 words),
  2.7 min after the wake (3,995,479).
- With 135full3 there are now two captures of the same procedure: one woken by the alarm after
  900 s, one by a key after 320 s.

### A chainloaded hypervisor build survives a real sleep and wake (135chain2, 2026-11-17 05:02-05:08)

Asahi's documented way to run a changed m1n1 is to chainload it over USB before each run, not to
reinstall the boot object. `chainload.py -r` puts the new image at the same base as the installed
one (0x802b58000 both), so the locked reset vector points into the new image. Test: m1n1 built
from `m1power/hv-detached` (the status acknowledgement now in `src/hv/hv_cpu_power.c`, local
commit) chainloaded over the installed v2.0.0-131, macOS 13.5 booted on it, alarm 60 s. Sleep
entry 05:07:05, `HV: S2R wake entry` 05:08:06 (61 s) with the handler inside the chainloaded
image, macOS re-entered and ran on (about 23,000 logged accesses a second). No in-memory patch.
(135chain1, the first try, was a Restart clicked by mistake: macOS's console shows
`systemWillShutdown` and `IOPlatformHaltRestartAction`.)

### Cable-free capture: the hypervisor's detached mode (det1-det5, 2026-11-17 05:47-06:56)

A new mode of our m1n1 fork (`~/m1n1-next`, branch `m1power/hv-detached`, commit 5e741690, new
`src/hv/hv_detached.c`; host tools `harness/detach.py`, `detach_readout.py`, `detach135.sh`;
`harness/macos-up.sh` brings macOS up on the chainloaded build). Once armed, the M1 runs the guest
with no host: the four kinds of exits the host used to handle are handled on the M1, readings go
to a log in the M1's RAM with the M1's own timer value, a real sleep and its wake need no host,
and a host that connects later reads the log out.

| Run | Cable | What happened (seconds from the detach marker, M1 timer) | Log |
|---|---|---|---|
| det1 | in | no sleep: 15 s, read-out, continued, 43 s, read-out | 1,850,478 entries, 0 dropped |
| det2 | in | Sleep clicked; last core down 220.913; wake 340.307 on the spacebar (119.4 s asleep) | 917,798 |
| det4 | **out** 06:40:12-06:40:58 | last core down 215.248; wake 216.839 (1.6 s: the trackpad was touched); a second Sleep was cancelled by a key before its commit | 1,067,168 |
| det5 | **out** 06:48:22-06:55:51 | last core down 62.156 (06:48:45); wake 477.695 on the spacebar (**415.5 s asleep, nothing attached**); 258,193 accesses after the wake | 576,012 |

In every run: 0 entries dropped, no exit the M1 could not handle, wake status `+0x20 = 0x400000`,
368 system-register accesses and 7 secondary cores handled on the M1 after each wake. The four
busiest pages (0x23b738000, 0x23bc34000, 0x210e20000, 0x211e20000) were left untrapped in det2-5
so that the 125 MiB log lasts about 40 minutes of running; with them (det1) a detached macOS makes
about 49,000 logged accesses a second.

det3 was not a detached run: the setup was interrupted, macOS put itself to sleep after 11 minutes
at the login window with the tracer's clock still running, and the M1 restarted into Omarchy 13 s
after that commit (06:12:54 to 06:13:07). Cause not established; the clock is to be off, or the
hypervisor detached, before any real sleep.

### Unattended detached runs that lost their log (det6, det7, 2026-11-17 07:20-08:03)

m1n1 `m1power/hv-detached` ed07f5bb (v2.0.0-138) adds a 793-word register snapshot at the sleep
commit and a log of each core's system-register accesses on its way down. Not yet read back:

- **det6**: detached 07:23:43, cable in, nobody at the M1. Screen dark at 07:33 (camera). The M3
  saw the m1n1 USB device leave and return at 07:43:42 (the wake: macOS's own alarm) and leave for
  good at 07:44:35; Omarchy up 07:44:48. The log was in the M1's RAM and went with the restart.
  The snapshot at the commit did not stop the sleep (the M1 stayed down until its alarm). Why it
  restarted 53 s after the wake is not read. A detached run supports one sleep, and macOS goes
  back to sleep after an alarm wake: a guess.
- **det7**: the next attempt was interrupted during the boot and never detached. macOS put
  itself to sleep 11 minutes later with the tracer's clock still running and the M1 restarted
  (Omarchy up 08:03:04). The same as det3: twice now.
- `harness/detached-wake-readout.sh` (watch for the wake from this Mac, read out 20 s later) was
  written for this and has not run.
