# The clean-room deep-sleep driver on the M1: runs ds2 and ds3 (2026-11-17)

**Question.** Does the M1 sleep with the driver written from the macOS observations
(`~/Work/deepsleep-clean`, 54/54 tests), wired into the kernel branch
`m1power/deepsleep-clean-kernel` (`~/Work/deepsleep-kernel`)?

**Answer so far.** No. The entry dies at its first 32-bit access to a word that macOS only ever
accesses as 64 bits. The spec had no access widths; it has them now (section 1.8, R49).

## What was run

All over Thunderbolt, kernel booted once with `tools/tb/m1-bootonce`, command line
`apple_deepsleep.enable=1 apple_deepsleep.alarm_secs=60 systemd.watchdog_sec=0 no_console_suspend`.

| Run | Kernel | Extra | Result |
|---|---|---|---|
| rehearsal | ds2 (`003d7fb99`) | `pm_test=processors` | devices suspended, cores 7..1 "offline, parked", 5 s, CPU1..7 up, rc=0, 8 cores online |
| ds2 real | ds2 | `panic=10` | devices suspended 10:46:05.19 (host log: tunnel torn down); the M1's port dropped 10:46:16.31 (11.12 s later); cold boot into Omarchy (kernel start 10:46:28) |
| ds2b real | ds2 | `panic=25` | 10:50:52.12 and 10:51:03.26: 11.14 s. The restart does not move with the panic delay |
| ds3 real | ds3 (`ec5e3cc08`) | `panic=10 apple_deepsleep.trace=1` | 11:00:31.23 and 11:00:42.38: 11.15 s. Fault record in the power chip, below |

## Readings

- After ds2 and ds2b the power chip's alarm register `0xd008` still held an older value
  (`11 be 08 00`), not the driver's (`d7 da 08 00`): the entry never reached its power-chip step.
- The chip did not power down at the commit: the M1's Thunderbolt port stayed up for about 10 s.
- After each run: `macsmc-reboot: PMU logged 1 boot error(s) and 0 panic(s)`.
- ds3's record at power-chip `0x9f04`-`0x9f0d`: `44 c5 00 40 02 00 02 10 63 00` = 'D', reason
  'E' (oops) with the SError-pending bit set, address `0x200024000`, kind 1 (32-bit read), core 0,
  access count 99. In the driver's sequence that is the first read of `0x200024000`, in the
  memory controller's quiesce action, right after the wait on `0x200001c04`
  (`var/m1-state/pmu-20261117-*-after-ds3.txt`).
- In every one of the six macOS captures `0x200024000` is read and written as 64 bits
  (`var/spec/widths.tsv`). Of the 3,833 address-and-direction pairs the driver touches, 7 use a
  width macOS never used, all 32-bit accesses to 64-bit words of the memory controller:
  `0x200024000` R/W, `0x200024008` R/W, `0x200027000` W, `0x200067000` W, `0x2000a7000` W.
  Eight pairs macOS was never seen to access at all: two power-domain words in `0x23b700000`
  (R and W; hidden by the hypervisor's guard) and the core start/stop words at `0x23b754000` (W;
  handled by the hypervisor, not logged).

## Not known

- What resets the machine about 10 s after the fault (no watchdog was armed by us, and it is not
  the panic delay).
- Which earlier access left the SError pending.
- Whether the chip powers down once the entry completes: no run has got that far.

## How the fault record works

`apple_deepsleep.trace=1`: before each access to a new 16 KiB page the kernel side writes ten
bytes to the power chip's spare bytes `0x9f04`-`0x9f0d` (the only state that survives the reset):
'D', reason, address (5 bytes), kind and core, access count. `tools/tb/m1-pmu-dump` reads them
after the reboot; `DS_SCENARIO=g DS_POLL=1 cargo test --offline --test sequence -- --ignored
--nocapture` in `drivers/soc/apple/deepsleep/hosttest` prints the driver's sequence to match.

## Run ds4 (11:19): past the memory controller, stopped at the power manager's table

Kernel ds4 (`751f8724a`: the driver with the seven widths corrected; 63/63 tests). Same timing
(devices suspended 11:19:51.20, port dropped 11:20:02.21). Record: `44 c5 00 90 54 3b 02 20 ad
00` = oops with SError pending, 64-bit read of `0x23b549000`, core 0, access count 173: the
first read of the power manager's quiesce after the memory controller and error handler steps.

Reading `0x23b549000` (32 bits, `/dev/mem`) under the stock kernel at 11:21: the M1 reset at
once (back at 11:22:10, `PMU logged 1 boot error(s)`). `apple_pmp` was loaded. In the captures
macOS reads this block (`0x23b52c000`-`0x23b55bffc`, R6) only after it has stopped the `pmp`
coprocessor (R4, R5). Linux's pmp driver does nothing at suspend. So the power manager's quiesce
depends on a step the tests had left out of the driver's scope.

## Runs ds5, ds6, ds7 (12:21-12:58)

- **ds5** (`905004705`, the logic widened to macOS's whole kernel sleep path, 107 tests): record
  `44 d0 00 42 00 35 02 10 01 00` = panic, SError pending, 32-bit read of `0x235004200` (sio's
  translator), count 1. Linux had powered sio's domain off before the entry.
- **ds6** (`401649d27`, `apple_deepsleep.dump=1`, rehearsal only, no crash): all 137 power-domain
  words logged at the moment the entry would run (`var/deepsleep/ds6-ps-dump.txt`). Against
  macOS at the start of its platform sleep actions (`var/spec/ps-at-e3.tsv`, captures D-G):
  Linux requests off where macOS requests on for GPIO, SIO_BUSIF, SIO, SIO_CPU, FPWM1, SPI_P,
  UART_P, UART_N, UART0-8, AUDIO_P, PMS_SRAM, ANS2; on where macOS has off for RMX, DISP0_FE,
  DISP0_CPU0, DISPEXT_FE, DISPEXT_CPU0, ATC1_COMMON; other bits differ on DCS0-7, PMP, SEP,
  APCIE_GP. Spec 1.9 / R50 added.
- **ds7** (`409997fce`, the logic turns on the domains macOS has on, 125 tests): **no reset.**
  The entry stopped by itself before the commit and Linux carried on: `enter: the entry stopped
  before the commit: -110, wait on 0x236408114 did not end`; cores 1-7 came back, `PM: suspend
  exit` 0.6 s later, rc=1, 8 cores online. So the domain turn-on, the watchdog words, the
  power-chip register and the SPMI controllers' step all ran; the first mailbox exchange with
  `sio` got no reply. On this boot `apple-sio` had failed to probe (`error -ETIME: sending SIO
  parameter 0x23`), so `sio` was not running. `begin` logged `sio translator ... (domains not
  on: 0 given), pmp translator +0x200 0x0 (read)`.

## Run ds8 (13:23): through the sleep actions, stopped in the power manager's quiesce

Kernel ds8 (`1897a7ea6`: `sio` and `pmp` taken as found; 145 tests). Devices suspended
13:23:03.07, port dropped 13:23:16.12 (13.0 s; the entry is longer now). Record
`44 54 e0 87 74 3b 02 10 b9 00` = 'T' (a wait of the logic timed out), no SError pending,
address `0x23b7487e0`, 32-bit read, core 0. That is the wait of R22 in the power manager's
quiesce: the entry had done the domain turn-on, every platform sleep action (including the read
of the `pmp` block, which did not fault with `pmp` stopped), the memory controller and the error
handler. The machine reset afterwards (the hardware was quiesced and the entry has no way back).

Read under the stock kernel afterwards: `0x23b748000`, `400`, `800`, `c00` all 0 (macOS: 1);
status words `0x23b7483e0` = `0x616100`, `7e0` = `0x7f7f00`, `be0` = 0, `fe0` = `0x6c6c00`. In
all six captures macOS stops each of the four sub-blocks and reads its status until the low
byte is 0 (`0x494900`, 0, `0x494900`, `0x515100`); the spec had only the first, as a literal
(now R22a). Also seen in the power chip after this run: byte `0x9f03` reads `0x50` (`0x30`
before); `0x9f01` reads `0x30`. Not explained.

## Run ds9 (14:03): the entry runs to its end; the chip does not power down

Kernel ds9 (`a25fc534a`: the power manager's sub-blocks taken as found; 169 tests), `trace=1`,
alarm +60 s. Devices suspended 14:03:16.04.

- Record in the power chip: `44 52 00 f5 1d 00 00 60 ac 00` = 'R': the logic's `enter` returned
  Ok, i.e. every step ran, including core 0's own last system-register writes (`CYC_OVRD_EL1`).
  Alarm register `0xd008` = `2d 09 09 00`: the driver's alarm, written in the power-chip step.
- The M1 did **not** reset (every earlier run reset about 10 s after its failure) and did not
  wake at the alarm: screen dark (camera 14:09:42), no answer for 7 minutes.
- The M3 logged nothing about the Thunderbolt link between 14:03:16 and 14:10:09 (two lines, the
  tunnel teardown at the suspend). At each earlier reset of the M1 it logged link errors and a
  disconnect at once. So the M1's Thunderbolt port stayed up: the SoC was not powered down. The
  cores were in their wait instruction with interrupts masked.
- 14:10:09 `tools/m1-reboot/m1-reboot.sh reboot`: the M1 acknowledged and rebooted into Omarchy
  (up 14:10:24). **On the M3** the script's swap of the USB-C controller module restarted the
  Thunderbolt stack, and at 14:10:38 the M3's kernel faulted in `thunderbolt` (`ring_work` ->
  `tb_ctl_rx_callback` -> `mutex_lock`, NULL pointer). The M3 keeps running; `thunderbolt0` is
  down. The M1 is reached over the tailnet (`ssh m1ts`) since.

**Where this leaves the question.** Doing what macOS's kernel sleep path does, as far as the
tests hold the driver to it, is not enough for the chip to power down from Linux's state.
Known differences that remain: the display and second-port domains are on (macOS: off, with
their coprocessors shut down first); the other device-level shutdowns of phase E2 (graphics,
storage, always-on processor) are not done; `DCS0`-`7`, `PMP`, `SEP` control words differ in the
bits above the request; 59 domain words are not observed for macOS; many written values are
macOS's own.

## Run ds10 (16:31): the commit snapshot is read; the way back panics in the audio switch's wake action

Both Macs were restarted before this run (the M3's Thunderbolt driver fault after ds9 is gone;
the Thunderbolt link is back). Kernel ds10 (`b9dc545ba`, package sha256 `66084bd4...47ee`): the
same logic as ds9, plus `apple_deepsleep.snap=1`: at the commit point the glue reads the 792
words of macOS's commit snapshot, then runs the logic's `leave_early` and `leave_late` without
powering anything down, and is to log the words afterwards. Command line: ds7's plus `snap=1`.

- `real.sh` started 16:31:56. The M3 logged the M1's retimer and host disconnect at 16:32:04.86.
  The M1 was next seen in stock Omarchy with a kernel start time of 16:32:16 (camera frame
  16:34:46: desktop). So it reset; `real.out` holds only its first line.
- Record in the power chip: `44 d0 04 82 40 38 02 30 4b 00` = 'P' (panic) with bit 7 (an SError
  pending), last access a 32-bit write to `0x238408204` by core 0, count low 16 bits `0x004b`.
- `0x238408204` is in neither `enter` nor the snapshot reads (host sequence with `DS_SNAP=1`).
  The logic writes it only in the audio switch's wake action (W3): block 2 of six at
  `0x238400000`, offset `0x204`, the third write of that block. So `enter`, the snapshot and
  `leave_early` (the memory controller's re-enable among it) completed, and `leave_late` ran up
  to that action. The count is then 65536 + 75.
- Inferred, not read: the first write to block 2 raised an asynchronous SError that was taken
  two writes later (`cpu_suspend()` has restored the exception masks by then) and the kernel
  panicked on it. Blocks 0 and 1 took their 22 writes.
- The reset followed the panic within about 2 s, not after the 10 s of `panic=10`. Cause unknown.
- The 792 words were lost: they are printed after the wake calls and never reached the disk.

Next: the glue keeps the snapshot's way back alive across SErrors (records each, continues), so
the words reach the log.

## Run ds11 (16:46): the same panic; skipping the SError is not enough

Kernel ds11 (`683d833a3`, package sha256 `4453febb...8fa3`): ds10 plus a hook that records an
SError on the `snap=1` way back and returns from it (at most 64, and not the same one five times
running), and the snapshot words logged before the wake calls. Command line as ds10.

- `real.sh` started 16:46:28; the M3 logged the M1's host disconnect at 16:46:36.43; the M1 was
  back in stock Omarchy, kernel start 16:46:48 (camera frame 16:48:54: desktop).
- Record: `44 d0 04 82 40 38 02 30 42 00` = 'P', bit 7 set, last access the same 32-bit write to
  `0x238408204` by core 0, count low 16 bits `0x0042`.
- Nothing else survived. Whether the hook ran and gave up, or was not reached, is not read.

Next: the hook reads the core's documented fault registers (Asahi docs, `L2C_ERR_STS`, `_ADR`,
`_INF`), clears the fault there, and the record carries the fault's own address.

## Run ds12 (16:56): past the audio switch; a wait in the wake times out; the snapshot is lost a third time

Kernel ds12 (`ef9661d63`, package in `var/kernels/ds12/`): ds11 plus the hook reading the core's
L2 fault registers (`L2C_ERR_STS`/`_ADR`/`_INF`, Asahi docs "hw/cpu/system-registers") and
clearing the fault there; a panic record carries the fault's address when one is flagged.

- `real.sh` started 16:56:05; host disconnect on the M3 16:56:13.32; the M1 back in stock
  Omarchy, kernel start 16:56:25 (camera frame 16:57:02: desktop).
- Record: `44 54 04 80 71 3b 02 10 d2 00` = 'T' (a wait of the logic timed out), no SError bit,
  a 32-bit read of `0x23b718004` by core 0, count low 16 bits `0x00d2`. That word is one of the
  power manager's pair `0x23b718000`/`004` that the wake writes back and polls.
- So the wake calls ran past the audio switch's action (where ds10 and ds11 stopped). After the
  failed wait the glue returned to Linux; the machine reset all the same. Cause unknown.
- The 792 words were lost again.

Three kernels have now failed to bring the snapshot back on bare metal. By the rule of
2026-11-17 (`docs/agents/cleanroom-cycle.md`) the next reading is taken under the hypervisor.

## Hypervisor round 1: Linux's entry as the guest (dsh1, dsh2, 2026-11-17 17:05-17:25)

Observation round under the three-strikes rule. Two runs of the ds12 kernel as the m1n1
hypervisor's guest. Neither produced the 792 words at Linux's commit. What was read is below.

### What was run

- **Guest image** `var/hvlinux/guest-ds12hv.bin` (dsh1) and `guest-ds12hv-d240.bin` (dsh2)
  (private), assembled with `tools/hv-trace-kit/guest/mkguest.py` from: guest m1n1
  `~/m1n1-guest` 0504a43d (the earlier guests' stage, checked byte for byte against
  `guest-run43hv.bin`); kernel `7.2.11-ds12` from `var/kernels/ds12/kernel-ds12.tar.zst`
  (sha256 `cbb9426f...`); the initramfs `m1-bootonce` built for ds12 on the M1, copied from
  `/boot/efi/s2r/ds12/initramfs.img` (sha256 `eda5652d...`, equal on both ends); DTB
  `var/hvlinux/ds12/j313-hv-ds.dtb`. This DTB is `j313-hv.dts` (the run39 DTB with the proxy
  port disabled; the ds12 package's own `t8103-j313.dtb` decompiles to the same text) plus
  the mailbox below. Command line `var/hvlinux/ds12/bootargs-ds12hv.txt`: the M1's root/LUKS
  words, `console=ttySAC0,115200 earlycon loglevel=7`, all of `var/deepsleep/ds7.cmdline`
  (`enable=1 alarm_secs=60 trace=1 dump=1`, `snap` left at 0), and `m1hv.ds=1 m1hv.delay=120`
  (dsh1) or `240` (dsh2). `apple_sep` was not blacklisted (ds7's line has no blacklist).
- **The mailbox.** The driver needs `/chosen/asahi,s2r-mailbox`. On bare metal (Omarchy,
  stock kernel, read 17:06) it is `0x802df4a40`. Under the hypervisor nothing provides
  one: `s2r-mailbox` / `S2RMBOX1` appear in no branch of `~/m1n1`, `~/m1n1-guest` or
  `~/m1n1-next`. So for this round:
  - the DTB names `0x9d0000000` and reserves 16 KiB there (`/reserved-memory/s2r-mailbox@9d0000000`);
  - `tools/hv-trace-kit/harness/ds_mailbox.py` (a `run_guest.py -m` module) writes a mailbox of
    the layout the driver checks at boot (magic, version 1, 8 cores, armed 1, boot core 0, one slot
    per MPIDR). The reset-vector field is 0, and no loader reads the slots at a wake.

  The driver accepted it both times: `mailbox at 0x00000009d0000000: version 1, 8 cores,
  loader reset vector 0x0, 0 resumes so far`, then `enabled: mem_sleep "deep" ...; alarm +60 s`.
- **The entry** is made by `m1hv-ds.service` / `tools/hv-trace-kit/guest/ds.sh`, installed on
  the M1 (runs only with `m1hv.ds=1`). It runs `/var/lib/m1power-ds/real.sh` (as ds9) after
  `m1hv.delay` seconds.
- Before each run: `tools/tb/m1-hvboot var/kernels/ds12/kernel-ds12.tar.zst` (17:09:42 -> proxy
  17:09:57; 17:14:52 -> 17:15:08). Nothing else was on the M3's USB, and the preflight was clean.

### dsh1 (17:10-17:12): no real commit; the entry stops before the commit

Setup: installed hypervisor image (v2.0.0-131), `harness/golinux.sh dsh1 -m harness/ds_mailbox.py`
with `S2R_SNAP_LIST=var/recfg/commit-snap-list-wide.json` (the tracer reads the 792 words when
the last core leaves the guest, as in lx14), and `harness/drivelinux.sh` with the new
`REAL_S2R=0` (watchdog 1 off, real sleep not armed). Tracer `hv_s2r_trace.py`, as the 13.5
entry captures. Files: `tools/hv-trace-kit/runs/20261116-linux/{run,vuart,console,go}-dsh1.*`,
`s2r-trace-dsh1.jsonl` (8,491 MMIO events, 565 SPMI commands; private).

- Guest kernel up; entry 17:12:23.8 (guest clock). `PM: suspend entry (deep)` at 132.35 s, then
  `begin` (power-chip clock 603463 s, alarm bytes `83 35 09 00` for `0xd008`), 137
  power-domain words dumped (`ps prepare`, in `vuart-dsh1.log`), and cores 7..1 `offline, parked`.
  The last line was `enter: mailbox armed: core 0 resumes at 0x81eb41038, cores 1-7 enter at
  0x81eb41514`.
- Trace at the end (tracer time): the seven `CPUSTART W 23b754000+0` writes (`0x10, 0x2, 0x20,
  0x4, 0x8, 0x40, 0x80`, swallowed by the hypervisor in this mode) at 136.47-136.51. Then
  `ps_cpu` words `0x23b7001c8`/`1c0` <- `0xf0000ff`, and at 136.68 core 1: `ACC_OVRD_EL1 <-
  0x1800101526076207` (skipped), `CYC_OVRD_EL1 <- 0x3000001`. With bit 0 set, the hypervisor
  takes the core out of the guest ("Guest is shutting down CPU"; hardware CYC_OVRD read back
  `0x2000000`).
- The guest then logged `enter: the entry stopped before the commit: -110, core 1 did not
  answer` and `Enabling non-boot CPUs ...`. So without a real commit the hypervisor cannot
  hold this driver at its commit point: the last-core snapshot never ran (one core left the
  guest, not eight).
- Power-chip records written afterwards (trace): `0x9f04 <- 44 46 00 f5` ('D','F') and then
  `44 58 00 f5` ('D','X') at 137.41. The last access traced was at 139.656: core 0
  `W32 0x23d2b0010 = 0x0` (tracer label: AON watchdog, WD1 +0x10).
- The M1 then left USB (host `SerialException`, `run_guest exit 1` 17:12:32) and was next in
  Omarchy with a kernel start of 17:12:43 (frame `var/m1-look/20261117-171325-state-after-dsh1.jpg`:
  desktop). The cause of this restart is unknown.
- Power chip after it (`var/m1-state/pmu-20261117-171335-after-dsh1.txt`): `0x9f00: 00 30 00 50
  44 58 00 f5 1d 00 00 61 05 00`. The record is 'D', reason byte `0x58` ('X'), and bytes 2-8 are
  `00 f5 1d 00 00 61 05`. The trace had written `0x9f0d = 0xc8`, and it reads 0 now.

### dsh2 (17:15-17:25): real commit, detached hypervisor (the det8 means); no wake

The same means as det8 (`macos135-det8-real-commit.json`): `~/m1n1-next` `m1power/hv-detached`
ed07f5bb (v2.0.0-138), chainloaded with `chainload.py -r` (17:15:16); `golinux.sh dsh2` with
`M1N1_ELF=~/m1n1-next/build/m1n1-raw.elf`, the touch map (`S2R_TRACER=hv_touch_map.py`,
epoch 5 s) and the mailbox module; `drivelinux.sh dsh2` with `WAKE=resume`
(`real_s2r_on(wake="resume")`, alarm left to the guest, 7 deferred PS words, "wake lands in THIS
image"); then `detach()` (`harness/detach.py`, as `detach135.sh` does) with the default
`commit_snap` = `var/recfg/commit-snap-list-wide.json`.

Detach was timed to 45 s before the guest's entry. The detached log keeps its first entries
when it fills, and the commit snapshot goes into the same log, so a short full-logging
window keeps room for it.

| Time (M3) | Reading |
|---|---|
| 17:15:22 | run start; mailbox written; touch map trapping 20,479 MiB of device space |
| 17:15:41 | guest `m1hv-ds: start; entry in 240 s` (driver enabled, same lines as dsh1) |
| 17:16:4x | watchdog 1 off, real sleep armed (resume) |
| 17:18:55.7-57.2 | `pre-detach` snapshot (793 words, 0 errors); full logging of 16 zones; tables: 8 power-manager words, 793 commit-snapshot words, 265 wake-snapshot words; log 4,126,208 entries (125 MiB) at `0x80d8c8000`; wake re-enters the guest at `0x817968000`; `DETACHED` |
| 17:19:41 | the guest's scheduled entry (`real.sh`) |
| 17:19:45.707 | M3 kernel: `usb 1-1: USB disconnect` (the hypervisor's own USB detach is part of its commit path) |
| 17:20:4x | the driver's alarm (+60 s from `begin`): no USB device returned |
| 17:22:13, 17:23:12, 17:24:02 | `m1-state.sh`: not reachable over USB or Thunderbolt. Frames `var/m1-look/20261117-1722*`/`1723*`/`1724*`: dark room, the panel a faint uniform dim rectangle. Whether the backlight is on is not read. |
| to 17:24:45 | USB watcher (`runs/20261116-linux/usbwatch-dsh2.log`): device not back |

The M3 kernel logged nothing after the USB disconnect (no link errors). Under m1n1 the M1 shows
the M3 a USB device only, not a Thunderbolt one. So "powered down" and "running with USB
off" cannot be told apart from here. For macOS under the same build (det8), the device left
and came back within a second at the alarm wake.

### Readings and files

- **Commit snapshot (792 words): not read.** dsh1 never reached the commit. In dsh2 the words
  were to be written by the last core into the detached log in the M1's RAM, and that log
  is read out only over USB after a wake. No wake came, so the words are unread, and a
  power cycle loses them. `var/commit-state/linux-ds12-hv-commit.json` does not exist.
- **Nearest reading:** the same 792 words read over the proxy at 17:18:55.7, Linux awake under
  the hypervisor, 46 s before its entry (`var/commit-state/linux-ds12-hv-dsh2-predetach.json`,
  private). This is not Linux at its commit. Against macOS det8 at its commit, word for word:
  **667 equal, 125 different, 0 unreadable**. By block: 55 SoC clock-generator words, 40
  power-state words, 9 other PMGR words, 8 memory-cache words (`MCC.planeN+0x680` `0xc15`
  vs `0x800`, `+0x684` `0xc41` vs `0x82c`), 8 `DCSn+0x7b0` (3 vs 0), 5 AON clock words.
- **Comparison table** `var/commit-state/linux-ds12-hv-vs-macos-det8.tsv` (private): address,
  name, macOS det8 at commit, Linux at commit (all 792 "not read"), Linux awake pre-detach,
  comparison. **At commit: 0 equal, 0 different, 792 unreadable.**
- **MMIO trace across the entry:** dsh1 traced with `hv_s2r_trace.py` up to the stopped entry
  and the return (above). dsh2's full log of the entry is in the M1's RAM, unread. The touch map
  up to the detach is `runs/20261116-linux/touch-dsh2.jsonl` (670 touch records, 37 epochs).
- **After the commit under the hypervisor (dsh2):** by 17:24:45 (5 min after the USB
  disconnect) there was no wake at the driver's +60 s alarm, no reset, and no USB or
  Thunderbolt answer. Whether the SoC powered down is unknown.

### Not done, and why

- No commit snapshot and no comparison at the commit (above).
- dsh2's detached log was not read out: it needs a wake.
- The M1 was left as of 17:24: not reachable, screen dark in the frame. Getting it back needs
  a power-button hold. Detached mode arms no watchdog, and `tools/m1-reboot/m1-reboot.sh` is
  not to be used.
- No Asahi or Aurora documentation was needed: no register is interpreted here beyond the
  tracer's own labels.

## Hypervisor round 2: macOS 13.5, fresh capture (det9, 2026-11-17 17:37-17:54)

A repeat of det8 (`docs/evidence/2026-11-16-dram-controller-state/README.md`, "The moment of
sleep, read on the M1"), unattended. Run B (the same with watchdog 1 armed) was not run;
see the end of this section.

### The no-hands way out, checked before the run

The only step that ends a det8-type run without hands is the hypervisor's alarm:
`ALARM=90`, so `real_s2r_on(alarm=90)`, so at the commit the hypervisor writes the power chip's
alarm register `0xd008` to its clock plus 90 s (`~/m1n1-next` `src/hv/hv_cpu_power.c`).
Nothing else ends the run if that wake fails:
- `drive135.sh` writes watchdog 1's control to 0 before arming, and all three AON watchdogs
  read control 0 at arm;
- detached mode arms no watchdog;
- the hypervisor's software watchdog (`hv_wdt.c`) needs a CPU withheld from the guest.

Naeem allowed the `0xd008` write for this run, and accepted that a missed wake needs his hands.
After a wake, the read-out leaves macOS stopped in the hypervisor's proxy, and
`harness/hv-reboot.sh` reboots the M1 over USB.

### What was run

Exactly det8's recipe and build, with one addition:

- `ALARM=90 FULL_SKIP=<det8's four pages> harness/macos-up.sh det9` (17:37:48):
  `to-proxy.sh` (Omarchy -> proxy), chainload `~/m1n1-next` ed07f5bb (v2.0.0-138, the build
  of 07:19, unchanged), `go135.sh` with the touch map and det8's boot arguments, then
  `drive135.sh` (`WDT off 0x0`, `RTC alarm at the commit: now + 90 s`, 7 deferred power words,
  "wake lands in THIS image"). Full logging started after the settle (about 1,645 accesses/s,
  the four busy pages `0x23b738000`, `0x23bc34000`, `0x210e20000`, `0x211e20000` left out as
  in det8). READY at 17:41:47.
- `harness/detach135.sh det9` with `ARGS='commit_snap=".../var/recfg/commit-snap-list-wide-ps.json"'`
  (17:41:53). **The one addition:** the commit list is det8's 793 entries, unchanged and read
  first, plus the 66 power-domain words of the driver's `ps_words.h` that are not in it (859
  entries, 858 addresses; sha256 `2b9f4955...`). Then `nohup harness/detached-wake-readout.sh det9`.
- Nobody at the M1. Afterwards: `harness/hv-reboot.sh` (17:52:23), then `tools/tb/m1-pmu-dump`.

Files (private): `tools/hv-trace-kit/runs/20261116-mac135/*-det9.*`, among them
`detached-det9.jsonl` (1,229,123 lines), `touch-det9.jsonl`; `var/commit-state/macos135-det9-*`;
`var/m1-state/pmu-20261117-175256-after-det9.txt`.

### Readings

| | det9 | det8 |
|---|---|---|
| Hypervisor run start / detach (M3 clock) | 17:38:12 / 17:41:53 | 08:31:24 / 08:35:01 |
| Last core in its sleep path (T), from the detach | 434.399 s (about 17:49:07) | 438.067 s |
| Order of the cores going down | first core 5 at 434.399453 | |
| Wake record, asleep | 524.683 s; **90.28 s** | 528.394 s; 90.33 s |
| USB device left / back (the wake, M3 clock) | 17:50:36.699 / 17:50:37.312 | 08:43:48.45 / 08:43:49.16 |
| AON wake status `+0x1c / +0x20 / +0x24` at the wake | `0x0 / 0x400000 / 0x0` | the same |
| Log entries / dropped | 1,230,245 / 0 (1,228,347 accesses, 684 system-register records) | 1,221,379 / 0 |
| Handled by the hypervisor alone | pmgr 30, cpustart 28, sysreg 368, secondary 7 | the same counts |
| Read-out | 545.45 s from the detach (20.8 s after the wake) | 549.23 s |

**b. Commit snapshot: 858 words, 0 errors.** Against det8 on the 792-word list
(`var/commit-state/macos135-det9-vs-det8-commit.tsv`): **774 equal, 18 different, 0
unreadable.** The 18:
- `MCC.plane0-3+0x680` (`0xe59`, det8 `0x800`) and `+0x684` (`0xe85`, det8 `0x82c`): 8 words;
- `DCS3+0x500` `0x1440004` (det8 `0x2440004`);
- SoC clock word `0x23b040020` `0xc5100000` (det8 `0x85100000`);
- `ps_dcs0`, `ps_dcs1`, `ps_dcs5` `0x1f0003ff` (det8 `0x1000030f`); `ps_dcs2`, `ps_dcs3`
  `0x1400034f` (det8 `0x1f0003ff`);
- power-gate words `0x23b71c0d8`, `+108`, `+120`: `0x80040307` (det8 `0xc0040307`).

Saved as `macos135-det9-real-commit.json` (det8's format and word list). The 66 extra
domain words are in `macos135-det9-commit-psextra.json` (0 errors). The time the read took is
not in the read-out.

**b. Wake snapshot: 264 words.** Against det8 (`macos135-det9-vs-det8-wake.tsv`): 259 equal,
5 different: `ps_dcs2`, `ps_dcs3` (`0x1f0003ff`, det8 `0x1000030f`), `ps_dcs4`, `ps_dcs5`
(`0x1000030f`, det8 `0x1f0003ff`), and AON clock `0x23d240000` `0x91100010` (det8 `0x80100010`).

**a. The 125 words that differ between Linux awake (dsh2) and macOS at its commit.** Table:
`var/commit-state/macos135-det9-125words-writes.tsv`, one row per write. Columns: macOS's
value in the touch map's `pre-full` snapshot (about 17:41) and in its `pre-detach` snapshot
(17:41:53, both awake, before any sleep request), the commit value, and every write between the
detach and T. A write is either a logged access or a power-manager word the hypervisor handled
itself. Each row has its time relative to T, its core and PC. The phase column uses the
spec's time windows (sections E1-E6 of `docs/spec/macos-13.5-sleep-wake-observed.md`); the
windows were not re-derived for this capture.
- None of the 125 lies in the four untrapped pages: every write to them by the main
  processors is in the log.
- **12 of the 125 were written** between the detach and T, 194 writes:
  - 145 in the E1 window (ps_i2c3 140, ps_i2c0 20 over E1 and E3);
  - 45 in E3 (display front ends and coprocessors, rmx, gfx, disp0_cpu0);
  - 3 in E5: the clock words `0x23b04014c` and `0x23b040154` <- `0x80100000` at T-0.0208 s,
    and `ps_sio` <- `0xf0000ff` at T-0.0160 s (a hypervisor-handled word);
  - 1 in E6: `ps_sio_cpu` <- `0x400024f` at T-0.0160 s.
- Awake (`pre-detach`) against the commit: 93 equal, 32 different. **6 of the 32 have a logged
  write. 26 changed with no write by the main processors in the log:**
  - 10 SoC clock words, in bit 8 or bit 30, e.g. `0x23b040020` `0x85100100` -> `0xc5100000`;
  - 8 power-state words: `ps_dcs0`, `1`, `2`, `3`, `5`, `ps_pmp` (`0x1000030f` -> `0x1f0f03ff`),
    `ps_pms_sram`, `ps_ans2`;
  - 3 power-gate words;
  - `0x23b720030`, `34`, `44` (`0x14d514d` -> `0x1515151`, `0x1404940` -> `0x1494949`);
  - AON clock words `0x23d240040` and `0x23d240314`.

  What changed them is not read.
- Periodic snapshots were not needed: none of the 125 is in an untrapped page.

**c. The 66 power-domain words not in the 792-word list:** read at the commit with the rest,
0 errors (`macos135-det9-commit-psextra.json`). With the 71 already in the list, all 137 domain
words of `ps_words.h` now have a macOS value at the commit.

**d. The wake.**
- The alarm as armed: the hypervisor's, now + 90 s at the commit. The wake record came 90.28 s
  after T, with AON wake status `+0x20 = 0x400000`, as in det8. The earlier captures read the
  same status for a key-press wake: an alarm and a key are not told apart by this word.
- Words read by the hypervisor at the wake:
  - `0x23d2b8028 = 0x8000000`, `0x23d2b8040 = 0x22`, `0x23d2c001c = 0xff0`;
  - watchdog 2: count `0x23d2b0020 = 0x76e28b` (0.325 s at 24 MHz), alarm `0x7270e00`,
    control 0. det8 read count `0x76e68f`, 0.325 s, the same within 1 ms.
- Power chip after the reboot (17:52:56): alarm register `0xd008 = 3a 3e 09 00` (605754 s).
  The clock then read 605895 s, so the alarm fell at about 17:50:35; the M3 saw the wake at
  17:50:36.7. Scratch from `0x9f04`: `48 00 01 3f ff ff 47 50 00`, which is:
  - 'H', the hypervisor's wake note (layout in `hv_cpu_power.c`: status map `0x0100`,
    `0x3f` = "no message pending", command `0xff`);
  - 'G' at `0x9f0a`: guest entered without a host.

  `0xd000 = 01` (03 after dsh1). Which power-chip register holds the wake cause is not known
  here, so the chip's own record of the wake source is not read.
- macOS's own watchdog writes before the sleep (log): WD0 count `0x23d2b0000 <- 0` and
  **WD1 count `0x23d2b0010 <- 0` at T-0.462 s**, WD0 control `0x23d2b000c <- 0` at T-0.035 s.
  No other write to the watchdog page between the detach and T.

### Run B (watchdog 1 armed 600 s before the detach): not run

Readings that make it impossible as specified:
- **600 s does not fit.** The AON watchdog's alarm word is 32 bits at 24 MHz
  (`arm_wdt.py`: `WDT_SECONDS * 24_000_000`): the longest alarm is 178.9 s.
- **It would fire before the sleep.** Armed just before the detach, any value would expire
  about 179 s later, while macOS is still awake: T came 434-438 s after the detach in det8 and
  det9 (the idle sleep, about 11 min after boot). So the M1 would reset before the sleep.
- **macOS restarts the count anyway.** It writes watchdog 1's count to 0 at T-0.462 s (det9
  log) and does not touch its control word in that window. An armed watchdog 1 would restart
  its count there.

Whether an AON watchdog counts while the chip is asleep is still unknown. The nearest
reading: watchdog 2's count at the wake was 0.325 s in both det8 and det9, though the two
captures slept 90.33 s and 90.28 s.

### M1 left

In Omarchy, stock kernel `7.3.0-0test5-1-ARCH`, up since 17:52:36. Reached over Thunderbolt;
the camera frame `var/m1-look/20261117-175359-state-after-det9.jpg` shows the desktop.

## Run ds13 (17:59): Linux on bare metal, the snapshot words read just before the entry

Kernel ds13 (`7089d2873`, package in `var/kernels/ds13/`), command line ds7's plus
`apple_deepsleep.snap=4`: in the suspend path, with cores 1-7 parked and before the driver's
first access, the glue reads the 792 words of macOS's commit snapshot list and returns without
calling the driver.

- `real.sh` started 17:59:18; `echo mem` returned 1 at 17:59:22 with all eight cores online
  again. The machine stayed up; the log reached the disk.
- All 792 words were read ("0 not read"); no SError was recorded.
- Against macOS det9 at its commit, word for word: 674 equal, 118 different. The 118 by the
  tracer's block labels: 54 SoC clock words, 40 power-state words, 8 memory-cache words, 5
  always-on words, 3 other power-manager words, and one word in each of the eight DRAM channels.
- The 137 power-domain words were also logged twice in this run (`dump=1`): at `prepare` and at
  `wake`.

Files (private): `var/deepsleep/ds13-snap0-dmesg.txt` (the log lines),
`var/commit-state/linux-ds13-bare-preentry.json` (same word list and format as the macOS
snapshots), `var/commit-state/linux-ds13-bare-preentry-vs-macos-commit.tsv` (det8, det9, Linux,
per word), `var/commit-state/linux-ds13-bare-ps-words.json` (the 137 domain words at the two
phases).

This is Linux's state before the driver runs, not at its commit. What the driver's entry then
changes is not read here.

## Hypervisor round 3: macOS 13.5, the spec stage's open readings (det10, 2026-11-17 18:26-18:41)

One capture by the det8/det9 recipe and build, with the same no-hands way out (the
hypervisor's alarm 90 s after the commit). It carries readings 1, 4, 5 and 6 of the spec stage's
list. Readings 2 and 3 are taken only as far as this capture's log goes (below).

### Correction to round 2's table

The phase column of `var/commit-state/macos135-det9-125words-writes.tsv` used the spec's fixed
time windows. It has been regenerated with the phases taken from the console line before each
write, the spec's method (section 4.1a). The phase starts relative to T:

| Phase | Starts at | Marker |
|---|---|---|
| E1 | -7.558 | first of "Set PowerStage (4 -> 6)" / "awdl0 disable" |
| E2 | -0.877 | "PM response took" |
| E3 | -0.478 | "IOCPUSleepKernel enter" |
| E4 | -0.0903 | first stop-bit record |
| E5 | -0.0897 | first quiesce action |
| E6 | -0.0159 | interrupt-controller quiesce action |

The display-domain writes at T-0.73 are therefore in **E2** (not E3), and SIO_CPU's write at
T-0.016 is in **E5** (not E6). By phase, det9's 194 writes are now E1 145, E2 45, E5 4. The
round 2 text above keeps the old labels; this table and the regenerated file supersede them.

### What was run

- `ALARM=90 FULL_SKIP=<det8's four pages> S2R_TOUCH_FULL="0x23b300000+0x4000,0x235004000+0x4000"
  harness/macos-up.sh det10` (18:26:46; hypervisor run start 18:27:09, READY 18:30:44, about
  1,685 accesses/s in full logging). Same chainloaded build (`~/m1n1-next` ed07f5bb), boot
  arguments and checks as det9: alarm "now + 90 s", "wake lands in THIS image", all three
  watchdogs at control 0. **Addition for reading 5:** the two translator pages logged in full
  from macOS's boot.
- `PRE='hv.run_script(".../harness/awake_snap.py")\nawake_snap("<list>", "awake-extra")\n'
  ARGS='commit_snap="<list>"' harness/detach135.sh det10` (18:30:51-18:30:53), with `<list>` =
  `var/recfg/commit-snap-list-r3.json` (863 entries, 862 addresses). That is round 2's list
  plus the four sub-block status words `0x23b7483e0`, `7e0`, `be0`, `fe0`.
  `0x23b720030`-`48` and all 29 words of the spec's R52 / 4.1a item 3 were already in it.
  - **Addition for readings 1 and 4:** the new `harness/awake_snap.py` reads that whole list
    once with macOS awake, in the hypervisor shell just before the detach (snapshot
    "awake-extra"), and puts the touch map's own 793-word list back. The wake-snapshot list
    therefore stays at 265 words: detached mode takes at most 320.
  - The same list is read at the commit.
  - `detach135.sh` gained `PRE` (hypervisor-shell lines run before `detach()`).
- `harness/detached-wake-readout.sh det10`, nobody at the M1; then `harness/hv-reboot.sh` and
  `tools/tb/m1-pmu-dump`.

Files (private): `tools/hv-trace-kit/runs/20261116-mac135/*-det10.*`;
`var/commit-state/macos135-det10-*`; `var/recfg/commit-snap-list-r3.json`,
`var/recfg/r52-29-words.json`; `var/m1-state/pmu-20261117-184042-after-det10.txt`.

### The run

| | det10 | det9 |
|---|---|---|
| Detach (M3) | 18:30:53 | 17:41:53 |
| T (last core in its sleep path), from the detach | 431.378 s (about 18:38:04) | 434.399 s |
| Asleep (wake record) | **90.18 s** | 90.28 s |
| USB device left / back (the wake) | 18:39:33.612 / 18:39:34.224 | 17:50:36.699 / 17:50:37.312 |
| AON wake status `+0x1c / +0x20 / +0x24` | `0x0 / 0x400000 / 0x0` | the same |
| Log entries / dropped; accesses | 995,348 / 0; 993,447 | 1,230,245 / 0 |
| Handled by the hypervisor alone | pmgr 30, cpustart 28, sysreg 368, secondary 7 | the same |
| Power chip afterwards | `0xd008 = b3 49 09 00` (608691 s; the clock read 608761 s at 18:40:42, so the alarm fell at about 18:39:32); `0x9f04`: `48 00 01 3f ff ff 47 50 00` | the same pattern |

- **Commit snapshot:** 862 words, 0 errors. Against det8 (792): 774 equal, 18 different.
  Against det9: **768 equal, 24 different**. All 24 are among the words that have already
  varied between captures:
  - 8 `MCC.planeN+0x680/684` (`0xad1`/`0xafd` this time);
  - `DCS1`, `2`, `4`, `5`, `6`, `7` `+0x500` (`0x1440004`, det9 `0x2440004`);
  - `0x23b040020`;
  - `ps_dcs0`-`3`, `ps_dcs5`;
  - power-gate words `0x23b71c0d8`, `0f0`, `108`, `120`.
- **Wake snapshot:** 264 words. Against det8: 262 equal, 2 different (`ps_dcs4`, `ps_dcs5`).
- The phase starts by the console lines are E1 -7.548, E2 -0.876, E3 -0.481, E4 -0.0911,
  E5 -0.0906, E6 -0.0157 (s from T).

### The six readings

1. **Sub-block status words with the sub-blocks on** (awake-extra, 18:30:5x), then their
   commit values:

   | Word | Awake | Commit |
   |---|---|---|
   | `0x23b7483e0` | `0x4d4d01` | `0x515100` |
   | `0x23b7487e0` | `0x404001` | `0x494900` |
   | `0x23b748be0` | `0x1` | `0x0` |
   | `0x23b748fe0` | `0x404001` | `0x494900` |

   The awake reads had 0 errors and did not disturb the run.
2. **Sub-blocks and `0x23b720030`-`48` together:** taken only from what macOS itself
   accessed (`macos135-det10-subblocks.tsv`). Between the detach and T, macOS touches the
   sub-block words only in one burst in E5, T-0.015895 to T-0.015801. For each block it reads
   the control word (`0x1`), writes 0, then reads its status until the low byte is 0:
   - `7e0`: nine reads of `0x494002`, then `0x494900`;
   - `be0`: `0x0`;
   - `fe0`: `0x494002` x3, then `0x494900`;
   - `3e0`: `0x514d02` x2, then `0x515100`.

   The order is `400`, `800`, `c00`, `000`, the same as det9. macOS accesses none of
   `0x23b720030`-`48` in that window.

   Their awake (awake-extra) and commit values: `030` `0x14d514d` -> `0x1515151`, `034`
   `0x1404940` -> `0x1494949`, `044` `0x1404940` -> `0x1494949`; `038` `0x1313131`, `03c`
   `0x1262626`, `040` `0x1000000` and `048` `0x17a7a7a` are unchanged.

   **Not taken:** reading `0x23b720030`.. at each sub-block write needs a read by the
   hypervisor at those writes. Detached mode reads extra words only at the commit and at the
   wake, and the four writes come within 0.1 ms of each other with no host attached.
3. **When the 29 words change:** `macos135-det10-29words.tsv`. 22 of the 29 differ between
   awake (pre-detach) and the commit. Of the 29, the only one macOS accesses between the detach
   and T is ANS2 (4 reads). For the others the change lies somewhere in the 431 s between the
   detach and the commit, as in G and H.

   **Not taken:** periodic snapshots during the entry. They need the host's clock or a sampler
   on the M1. The hypervisor's clock must be stopped before a real sleep (det3 and det7
   restarted the M1 with it running), and detached mode has no sampler. This needs either a
   hypervisor change (a periodic read of a word list into the detached log) or a capture whose
   end is not the alarm wake. Neither was done here.
4. **The 66 domain words with macOS awake:** read in awake-extra, 0 errors
   (`macos135-det10-awake-vs-commit-new.tsv`; 70 rows with the four status words). Awake
   against commit, 57 equal, 13 different:
   - the four status words;
   - ECPU1-3 and PCPU0-3 `0x1f0` -> `0x100`;
   - PCPM `0x21f0` -> `0x2100`;
   - APCIE_ST `0x1000030f` -> `0x0f000300`.
5. **Where the translator values come from** (`macos135-det10-translators.tsv`). On the two
   pages logged in full from boot: 1,178 accesses before the detach. All writes to the three
   words come from one PC, `0xfffffe0015022d8c`, all 32-bit, about 2.2-2.9 s after the touch
   map started:
   - `0x23b300200` <- `0x0`, then `0x808217dc`;
   - `0x235004210` <- `0x0`, then `0x80821a38`;
   - `0x235004200` <- `0x0`, then `0x80822854`.

   After the wake the same PC writes the same three values again (T+90.226, T+90.226, T+90.535).
   What the values point at is not read.
6. **Widths:**
   - **`0x690000004`** (det9 and det10 alike): read 32-bit (`0x100007`) at T-0.49; written
     **16-bit** (width log2 = 1) with `0x0` at T-0.041 (PC `...ff70`); after the wake, read
     32-bit (`0x100000`) and written 32-bit (`0x100007`).
   - **The guarded power-manager words and the core start/stop words:** before the detach
     (boot and secondary-core start) all 67 accesses the hypervisor's hooks logged in det10
     were 32-bit (`+off:32` in `run-det10.out`).
   - **Not read:** the widths during the entry. The detached hypervisor writes a fixed width
     (2) into its `pmgr` and `cpustart` records (`hv_detached.c`), so the width macOS used
     there is not recorded.

### Not done in this round

- The extra reads in 2, the periodic snapshots in 3 and the entry-time widths in 6, for the
  reasons given there.
- The items the coordinator set aside: another starting state, a stopped coprocessor,
  macOS's own alarm, and Linux at its commit.

### M1 left

In Omarchy, stock kernel `7.3.0-0test5-1-ARCH`, up since 18:40:18, reached over Thunderbolt;
the camera frame `var/m1-look/20261117-184049-state-after-det10.jpg` shows the desktop.

## Run ds14 (19:12): the round-6 driver; the entry stops at DISP0_CPU0, which does not report off

Kernel ds14 (`097627a21`, package in `var/kernels/ds14/`): the driver logic at `63e2b0f`
(196/196 from tests `e0161ed`: the power domains brought to macOS's commit state from Linux's
state, the extra coprocessor reads, the wake putting back what the entry changed). Command
line ds7's plus `apple_deepsleep.snap=2`.

- `real.sh` started 19:12:07; `echo mem` returned 1 at 19:12:12 with all eight cores online.
  The machine stayed up on ds14 (no reset, no hang); the log reached the disk
  (`var/deepsleep/ds14-dmesg.txt`).
- The driver's log: `enter: the entry stopped before the commit: -110, wait on 0x23b710018 did
  not end`. Record in the power chip: `44 54 18 00 71 3b 02 10 02 00` = 'T', a 32-bit read of
  `0x23b710018` by core 0.
- `0x23b710018` is DISP0_CPU0 (first written here as DISP0_FE, a misreading of the spec by the
  orchestrator; corrected by the spec agent, DISP0_FE is `0x23b700360`). Before the entry it read `0x1404024f`; after the failed entry it
  reads `0x14040240`: the request (low four bits) went from `0xf` to 0, the state bits (4-7)
  stayed at 4.
- The 137 power-domain words at `prepare` and at `wake` of this run
  (`var/commit-state/linux-ds14-bare-ps-words.json`, private): 41 differ. Among them: the cores'
  words `0x100` -> `0x1f0`; twelve words `..244` -> `..200`; FPWM1 `0xa00` -> `0x200`;
  `0x23b7001c0`/`1c8`/`1d0` `0x0f000200` -> `0x1400024f`; nineteen words `0x200` -> `0x2ff`;
  `0x23b7003e0` `0x0f000300` -> `0x1f0003ff`, `0x23b7003f0` `0x0f002300` -> `0x1f0023ff`;
  `0x23d280060` `0x1400024f` -> `0x1f0002ff`.
- After the return Linux logged `thunderbolt 0-1: failed request link state change, aborting`
  once a second. The M1 was rebooted to stock Omarchy (kernel 7.3.0-0test5) afterwards.
- Also read after this run: power-chip byte `0x9f03` is `0x00` (`0x50` after ds8 to ds12).
  Not explained.

## Linux awake, stock kernel (19:35): the display, graphics, storage and I/O domain words

Read over `/dev/mem` on the M1 in stock Omarchy (kernel 7.3.0-0test5, display on, nothing
suspended), one 32-bit read each: `0x23b710018` (DISP0_CPU0) = `0x1404024f`; `0x23b700360`
(DISP0_FE) = `0x20ff`; `0x23b700368` = `0x23ff`; `0x23b700378` = `0x1404024f`; `0x23b7003f8`
(GFX) = `0x1000230f`; `0x23b7003f0` = `0x1000230f`; `0x23b7003e0` = `0x0f000300`; `0x23b7001d0`
(SIO_CPU) = `0x1400024f`; `0x23d280060` = `0x1400024f`. So DISP0_CPU0 reads state 4 with the
display on and Linux awake, not only in the suspend path.

## Run ds15 (19:35): Linux on bare metal, the coprocessors' state words just before the entry

Kernel ds15 (`8c3a99266`: the logic as ds14, the glue's `snap=4` reading extended), command line
ds13's (`snap=4`). In the suspend path, cores 1-7 parked, before the driver's first access: the
792 snapshot words, then for six coprocessors the words +`0x44`, +`0x48`, +`0x8110`, +`0x8114`,
each coprocessor's reads skipped if one of its power-domain words reports state 0, and those
domain words read before and after. The driver is not called.

- `real.sh` started 19:35:06; `echo mem` returned 1 at 19:35:09, eight cores online, machine up,
  log on disk (`var/deepsleep/ds15-snap4-dmesg.txt`). 792 of 792 words read; no SError recorded.

| Coprocessor | +0x44 | +0x48 | +0x8110 | +0x8114 | Its domain words (same before and after the reads) |
|---|---|---|---|---|---|
| `dcp` | `0x10` | `0x2d` | `0x2ff01` | `0x2aa01` | RMX `0x1f0000ff`, DISP0_FE `0x20ff`, DISP0_CPU0 `0x1404024f` |
| `dcpext` | `0x10` | `0x2d` | `0x27701` | `0x2ee01` | RMX `0x1f0000ff`, DISPEXT_FE `0x23ff`, DISPEXT_CPU0 `0x1404024f` |
| `gfx-asc` | skipped | | | | GFX `0x0f002b00` |
| `ans` | skipped | | | | ANS2 `0x0f002300`, APCIE `0xff`, APCIE_ST `0x0f000200` |
| `sio` | skipped | | | | SIO_BUSIF, SIO, SIO_CPU all `0x0f000200` |
| `pmp` | skipped | | | | PMP `0x1f0000ff`, PMS_SRAM `0x0f000300` |

So at the point where the driver's entry begins under Linux, `dcp` and `dcpext` read +`0x44` =
`0x10` with their processor domains at state 4 and their blocks answering; the domains of
`gfx-asc`, `ans` and `sio` report state 0; `pmp`'s were not read because PMS_SRAM reports
state 0 (PMP itself reports on).

## Run ds16 (20:26): the round-7 driver reaches the commit; the M1 stays dark, no reset, no wake

Kernel ds16 (`5e1aadaa2`, package in `var/kernels/ds16/`): the driver logic at `2695243`
(218/218 from tests `e508cf7`: domains turned off by macOS's forms, `dcp`, `dcpext`, `gfx-asc`,
`ans` stopped before their domains, the first port's domains off at the commit, the 16-bit PCIe
write). Command line ds14's (`snap=2`: the commit comparison is written to the power-chip
record at the commit, then the entry goes on).

- `real.sh` started 20:26:46. The M3 logged the M1's retimer and host disconnect at 20:26:49.4.
- After that the M1 answered on nothing (Thunderbolt, USB, tailnet). No reset: at every earlier
  failed entry it was back within about 30 s. No wake at the alarm (+60 s). Camera frames at
  20:28:34 and later: black (the room was dark as well).
- 21:52:12 the M3's Thunderbolt port re-initialised; the M1 was up in stock Omarchy with kernel
  start 21:52:28. What restarted it is not read (Naeem had been asked to press a key and, if
  nothing happened, to hold the power button; his answer is not in yet).
- Record in the power chip after the restart: `44 43 3f 00 27 02 28 02 29 00`. Reason 'C': the
  commit comparison, which the glue writes at the commit point. So the entry ran to the commit.
  M (words whose value at the commit is neither the driver's last write nor the reading before
  the entry) = `0x003f` = 63. The first three such words by index: `0x0227` = 551
  (`0x23b04003c`), `0x0228` = 552 (`0x23b040040`), and `0x0029`; if the record's last byte was
  not written, that is `0x0229` = 553 (`0x23b040044`), the next word, else index 41
  (`0x200080684`). All with bit 15 clear: the expected value was the reading before the entry.
  These are SoC clock words; under macOS the spec's R52 lists clock words that change with no
  logged write.
- Other power-chip bytes after this run: `0x9f01` = `0x30`, `0x9f03` = `0x50` (`0x00` after
  ds14, `0x50` after ds8 to ds12); alarm register `0xd008` = `12 63 09 00` (615186 s), the clock
  at the dump 620301 s (5115 s later); `0xd00c` = `00` (`01` in the dumps after ds10 to ds12).
  Full dump: `var/m1-state/pmu-20261117-215301-after-ds16.txt` (private).
- `real.out` holds its first line only; the kernel log of that boot kept three driver lines.

Not known: whether the chip powered down after the commit or stayed up with its cores stopped.
The M3 cannot tell the two apart here, because the driver itself now turns the first port's
domains off during the entry. The M1 was on mains with a full battery, so the battery does not
tell either.

## Observation round 4: after ds16's commit (readings taken 2026-11-17 21:55-22:05)

Readings from what already existed, plus read-only reads on the M1 in stock Omarchy (boot of
21:52:28). No run.

### 1. Power-chip bytes that differ between the groups of dumps

Source: `var/m1-state/pmu-*.txt` (`tools/tb/m1-pmu-dump`, read through the kernel's nvmem
device). **There is no dump after ds9**; its record and alarm bytes exist only in this file's
ds9 section. No dumps after ds13 or ds15. Every byte not listed below is equal in all of these
dumps, apart from the scratch record `0x9f04`-`0x9f0c` and the clock/alarm bytes `0xd002`-`0xd00a`.

| Register | before run 41 / 42 | 07:50 | ds2-ds5 | ds8 | ds10, ds11, ds12 | dsh1 | det9, det10 | ds14 | **ds16** |
|---|---|---|---|---|---|---|---|---|---|
| `0x0201` | 01 / 01 | 00 | 00 | 00 | **04** | 04 | 00 | 00 | **04** |
| `0x9f03` | 50 / 30 | 50 | 30 | 50 | 50 | 50 | 00 | 00 | **50** |
| `0xa47c` | 08 | 08 | 08 | 08 | **1c** | 1c | 08 | 08 | **0c** |
| `0xa47d` | 00 | 00 | 00 | 00 | **04** | 04 | 00 | 00 | **04** |
| `0xd000` | 41 / 01 | 41 | 01 | 01 | **03** | 03 | 01 | 01 | 01 |
| `0xd00c` | 00 | 00 | 00 | 00 | **01** | 01 | 00 | 00 | **00** |
| second chip `0x2808` | 04 / 04 | 05 | 05 | 05 | 05 | 05 | 05 | 05 | 05 |

What the sources say these registers are:
- **`0x0201`.** The lab's decode of macOS's always-on sleep program
  (`docs/evidence/2026-11-16-run36-38-restart/README.md`,
  `docs/evidence/2026-11-16-hv-macos135-wake/README.md`) says sequence 1 (entering sleep)
  writes 01, sequence 5 writes 02 and the wake sequence 10 writes 00. `docs/hardware/m1-air-j313.md`
  says it reads 04 after a power-button start and 01 after a wake-restart.
  - Readings here: the self-resets of ds10-ds12 and dsh1, and the reboots of ds14, left it
    unchanged (04 carried from the cold start before ds10; 00 carried from det10).
  - After ds16 it reads 04. In ds14's dump (19:14) it read 00.
- **`0x9f03`.** "boot-error-stage" (the M1's device tree, `docs/hardware/m1-air-j313.md`). The
  lab guide `var/s2r-static/PMU-WAKE-READING-GUIDE.md` expects 0x50 after a reset or cold boot;
  that expectation is not measured.
- **`0xa47b`-`0xa47e`, the fault shadow.** The ADT's `info-fault_shadow`; the bit names are the
  ADT's `info-fault_name-N`, as read by `pmu_postmortem.py` (e.g.
  `runs/20261106/mac27/try44/postmortem-*.json`). The bytes are a little-endian word starting at
  `0xa47b`:
  - `0x000800` = bit 11 `wdog,reset_in_1` (every dump except the two groups below);
  - after ds10-ds12 and dsh1, `0x041c00` = bits 10 `btn_rst,btn_seq_reset`, 11
    `wdog,reset_in_1`, 12 `dbg_rst,reset_in_2` and 18 `timeout,dblclick_timeout`;
  - **after ds16, `0x040c00` = bits 10 `btn_rst,btn_seq_reset`, 11 and 18
    `timeout,dblclick_timeout`.** Bits 10 and 18 were not set at ds14's dump (19:14).
- **`0xd000`, `0xd00c`.** The ADT's "rtc_alarm block"; `0xd001` is "pm-setting". The lab
  guide (partly inferred, citing Aura's tests) reads `0xd00c` = 01 as the alarm event latched and
  `0xd000` = 03 as a fired-alarm status.
  - Readings: 03/01 only after ds10-ds12 and dsh1. In those runs the driver's alarm time passed
    while the M1 had restarted and Linux was running.
  - After det9 and det10, whose alarm did wake the chip (under macOS), both read 01/00 after the
    reboot.
  - After ds16 the clock (`0xd004`-`0xd007`, s) had passed the alarm (`0xd008` = 615186 s) by
    5115 s, with `0xd000`/`0xd00c` = 01/00.
  - Not known: whether a power-button start, or macOS, clears these.
- **Second chip `0x2808`.** Written 05 by macOS's wake sequence 10 (lab decode). 05 since 07:50
  in every dump, including after ds16's restart, so it carries no information about ds16.

Read on the M1 now (`/sys/bus/nvmem/devices/spmi_nvmem0/nvmem`, read-only, 21:58):
- fault log `0xd200`: 16 bytes of 0;
- `0x9f00`-`0x9f1f`, `0xa470`-`0xa48f` and `0xd000`: as in the 21:53 dump;
- `0xd100` (rtc offset): `6f 3d 2d 84 79 35 00 00`;
- `0xa67b`: a different value at each read since 2026-11-06, not interpreted.

### 2. The M3's flight recorder

Source: `var/m3-blackbox/d84a42bc-*.log` (ds16) and `612cd1db-*.log` (ds9), one BEAT line a
second. The M1 is on the M3's `port2`: the partner left that port during the M1's reboot at
14:02:44.

| | ds9 (14:03:16-14:10:09) | ds16 (20:26:49-21:52:41) |
|---|---|---|
| port2 partner | present, the M3's role `source`, throughout | present, the M3's role `source`, throughout |
| `thunderbolt0` | interface present, carrier 0 | **interface absent (`-`)** |
| M3 mains, battery current | `ac=1`, 0 | `ac=1`, 0 |
| Gaps in the record | none | **21:02:41-21:47:22: the M3 itself was in s2idle (45 min)** |

- After the restart: `tb0` = 0 at 21:52:41, 1 at 21:52:42.
- At 21:52:51 the M3's mains partner on `port0` left (`ac=0`, battery -0.79 A).
- The record has no current or voltage of `port2`, so it cannot tell how much power the M1 drew.

### 3. The M3's kernel log

Source: `journalctl -k`, this boot for ds16 and boot -1 for ds9.
- **ds9:** after the tunnel teardown at 14:03:16, nothing about the port until the module swap
  of 14:10:09. The link stayed trained; there was no lane message in between.
- **ds16:**
  - 20:26:49.27-.33: 60 `Gen2/3 link error` lines (both lanes);
  - 20:26:49.37 `retimer disconnected`, 20:26:49.40 `host disconnected`;
  - from 20:26:50.42, `lane_init.c:936: Timeout reading AT register` about every 0.1 s (21,513
    lines to 21:02:42);
  - 21:02:42 the M3's own `PM: suspend entry (s2idle)`. On resume at 21:47:22 the M3 restarted
    its USB-C/Thunderbolt stack, and the same timeouts went on (2,872 lines to 21:52:10.58);
  - **21:52:10.654 `SBX disconnected!`**, then the lane state machine restarted, timeouts again
    21:52:28-21:52:34.9, `Entering Connected` 21:52:35.07, `new host found` 21:52:40.96.
- **Comparison with an ordinary reboot.** The same sequence ("SBX disconnected!", Phase 1, about
  9 s of "Timeout reading AT register", "SBX disconnected!", "Connected") appears at the
  ordinary reboot that started ds16's kernel (20:25:48-20:26:15).
- So for 85 minutes the M3's controller saw a partner on the port whose sideband did not
  answer its AT-register reads. In ds9 the link stayed trained with no such lines.
  Which state of the M1 gives these timeouts (powered down, or up with the port's domains off)
  is not read: no capture shows what this log looks like while the M1 is known to be powered
  down.

### 4. On the M1 now: what the restart was

Read-only:
- **Power chip:** the fault shadow gained `btn_rst,btn_seq_reset` (bit 10) and
  `timeout,dblclick_timeout` (bit 18) after 19:14, and `0x0201` = 04, the value the lab's notes
  record after a power-button start.
- **Kernel log of this boot:** `macsmc-reboot: PMU logged 1 boot error(s) and 0 panic(s)` at
  21:52:35. The three boots before it printed no such line. The same line followed ds2-ds3's
  resets. Per the Aurora survey (`docs/evidence/2026-11-06-aurora-silicon-survey.md`, B3: aura
  `src/pmu_counter.c`), iBoot counts unclean boots at `leg_scrpad+2` = `0x9f02`; the dump reads
  `0x9f02` = 00 after Linux's boot.
- **Times:** M3 `SBX disconnected!` at 21:52:10.654; the M1's kernel start at 21:52:28; its RTC
  set the system clock at 21:52:28.57.

These readings are what the chip records for a button reset. Whether Naeem pressed it is his
answer, not yet in.

**Not readable:**
- How long the SoC was powered. The power chip's clock runs in every state. The previous
  boot's journal ends at 20:26:46 (`real.sh` start).
- The boot loader's wake mailbox counters: the loader published a new mailbox this boot
  (`0x8021cca40`; `0x802df4a40` at 17:06), so the previous boot's counters were not read.
- SMC keys that count sleep or power events: none is known to this lab, so none was read.

### An observation design for the next bare-metal run (readings only)

| To tell | Reading | What it needs |
|---|---|---|
| Whether the chip powered down | The M1's battery charge (`macsmc-battery` `charge_now`/`energy_now`) logged right before the entry and right after the restart, divided by the dark time. The two states differ by about an order of magnitude in draw; the size comes from the Aurora survey's macOS 0.109 W asleep, so it is documentation, not a reading on this M1. | The M1 not charging during the run: on battery with the charger out **and** the M3 not sourcing power on `port2` (it is `source` in every run so far). Either a cable or hub that carries no power (a second cable), or the M3's port set to sink, which is an M3 setting and a risk to weigh. |
| The same, from the M3 | Repeat this log's port readings (section 3) with the M1 in a known powered-down sleep: bare-metal macOS sleeping with the cable in. That gives the "powered down" signature of the AT-register timeouts. | A bare-metal macOS sleep. Without the hypervisor, the wake needs a key or macOS's own alarm, so hands or a macOS login. |
| Whether the always-on processor's sleep program ran (sequence 1), or a wake sequence ran | Power chip `0x0201` after the restart: 01 = sequence 1, 02 = sequence 5, 00 = wake sequence 10, unchanged = none (lab decode). | The run must **not** end with the power button, which writes 04. Read before the run (it reads 00 now if nothing writes it), and after a self-reset. |
| Whether the alarm fired | `0xd00c` and `0xd000` after the restart, with the clock past the alarm. | Two calibrations, both read-only: (a) the alarm passing while the chip is known up (dsh1, ds10-ds12 give 01/03); (b) a known sleep and wake (det9 and det10 give 00/01 after macOS ran). Whether a power-button start clears them is unknown and needs hands to calibrate. |
| Whether a wake began | A marker written at the wake entry before anything else, in the boot loader (stage 1 v1.6.1-dirty), and read after the restart. The hypervisor does this with 'W' -> 'Z' at `0x9f04`/`0x9f0a`. | A boot-loader change, writing only inside `0x9f04`-`0x9f0d` (the glue's record shares those bytes). Not done. |
| Whether the M3 missed part of it | The M3 must not sleep during a run: it was in s2idle 21:02-21:47. | An inhibitor on the M3 (`systemd-inhibit` around the run). |
| What ends the run without hands | (1) Watchdog 1 armed by the glue just before the commit, at most 178.9 s (32-bit at 24 MHz). If the SoC stays up, it resets and that reset is itself a reading; whether it counts while powered down is unknown (det9/det10: watchdog 2 read 0.325 s at both wakes). This is a glue change, an AON register, not the power chip. (2) The alarm, already armed, which did not end ds16. (3) A reset over the cable (`tools/m1-reboot/m1-reboot.sh`, a USB-C VDM): barred, because it crashed the M3's Thunderbolt driver today. | (1) needs the implementation stage; (3) would need the M3-side risk removed first. No power-chip write outside `0x9f04`-`0x9f0d` and the alarm register is needed by any of these. |

## Run ds16b (22:07): ds16 again with Naeem at the M1; on battery through the dark period

Kernel ds16 again, command line ds14's (`snap=2`), `snap_k` set to 3 at run time. Naeem was at
the M1; the M3 was kept awake.

- Before: battery "Full", `charge_now` 3,274,000 µAh, on mains. Power chip before the run:
  `0x0201` = `04`.
- `real.sh` started 22:07:26; host disconnect on the M3 22:07:29.78. Naeem unplugged the charger
  and the M3 cable once the screen was dark (the M3 lost the port partner between 22:07:41 and
  22:08:03).
- No wake at the alarm (+60 s). At about 22:18:25 Naeem pressed the space bar once: no answer
  on the tailnet in the 30 s after. He then held the power button; kernel start 22:20:29.
- Record: `44 43 40 00 2a 02 2b 02 3c 00` = 'C' again (the commit was reached), M = 64 (63 in
  ds16), surprises 3 and 4 by index: 554 (`0x23b040048`) and 555 (`0x23b04004c`), SoC clock
  words. The record's last two bytes again do not hold a third index (`3c 00`; ds16: `29 00`).
  The glue's author states the ten bytes go out as three SPMI commands (`0x9f04`-`07`,
  `0x9f08`-`0b`, `0x9f0c`-`0d`): in both runs the third did not land.
- Power chip after: `0x0201` = `04`, fault shadow `0x040c00`, `0xd000` = `01`, `0xd00c` = `00`,
  alarm 621226 s, clock at the read 622061 s; the kernel logged "PMU logged 1 boot error(s)".
- Battery after the restart (on battery, `current_now` about -373 mA):
  `charge_now` = `charge_full` in every sample from 22:20:48 to 22:22:40, rising 3,280,000 ->
  3,292,000 µAh, capacity 100 %. The gauge does not count down near full, so this reading does
  not tell how much the dark period drew (`var/deepsleep/ds16b-battery-after.txt`).

Not known, still: whether the chip powered down. Read in both runs: the record is cut at the
same place, after its second SPMI command.

## Run ds16c (22:25): ds16 with every diagnostic off; dark, no wake from any source

Kernel ds16, command line without `snap`, `trace`, `dump` (`var/deepsleep/ds16c.cmdline`), M3
cable and charger plugged in. `real.sh` started 22:25:41; host disconnect on the M3 22:25:44.47.
No wake at the alarm (+60 s). Naeem, at the M1: nothing visible at the alarm time; then a key
press, a short press of the power button, and the lid closed and opened, about 20 s apart: no
reaction to any. He held the power button; kernel start 22:30:05. Record after: `44 61 00 ...`
('a': armed, no failure recorded, as expected with trace off). `0x0201` = `04`, fault shadow
`0x040c00`, `0xd000` = `01`, `0xd00c` = `00`. So the outcome of ds16 and ds16b does not come
from the snapshot or the trace marks.

## Run ds17 (22:36): on battery, watchdog 1 armed at the commit; the M1 resets about 120 s later

Kernel ds17 (`2bdbfc491`: ds16's logic; the glue's `apple_deepsleep.wdt=N` arms the SoC's
watchdog 1 at the commit point to reset N s later, after a 'W' mark in the record). Command line
ds16c's plus `wdt=120`. Naeem had unplugged the M3 cable and the charger before the start: the
M1 read `ac=0`, "Discharging", -377 mA at 22:36:04; the run was started over the tailnet.

- `real.sh` started 22:36:10. No answer at the alarm time (+60 s).
- The M1 answered on the tailnet at 22:38:41 in stock Omarchy, kernel start 22:38:26: about
  133 s after the entry began, i.e. a reset at about the watchdog's 120 s plus the boot.
  Naeem, who was at the M1: he did not touch it in that time.
- Record: `44 57 00 40 2c 3d 02 30 7e 00` = 'W': the commit point was reached and the watchdog
  armed there. The last access before it: a 32-bit write to `0x23d2c4000` by core 0. All ten
  bytes landed this time.
- Power chip after: `0x0201` = `04` (unchanged; by the lab's decode of macOS's always-on sleep
  program a sleep entry writes `01` and a wake `00`); fault shadow `0x040c00`; `0xd000` = `01`,
  `0xd00c` = `00`; fault log at `0xd200` all zero. The kernel logged "PMU logged 1 boot
  error(s)".

Read together: 120 s after the commit, with nothing plugged into the M1, the SoC's watchdog
still counted and reset the machine, and the power chip's sleep byte was not written. The
earlier dark periods (ds16, ds16b, ds16c) ended only with the power button.

## Hypervisor round 5: macOS with watchdog 1 armed at the commit (det11, 2026-11-17 22:57-23:11)

**Short answer: with watchdog 1 armed at the commit (bite 150 s), macOS powered down and woke at
the 90 s alarm exactly as in det8-det10. At the wake entry watchdog 1's count read 13.9 ms: it
did not count through the 89.5 s of sleep.**

### The change and the run

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commit `bb8873c0`, not
  pushed (on top of ed07f5bb), in `src/hv/hv_cpu_power.c` and `src/hv/hv_detached.c`:
  - `hv_s2r_wd1_secs`, 0 (off) by default. When set, the last core writes watchdog 1 with the
    same four writes as the glue (`0x23d2b001c` <- 0, `0x23d2b0010` <- 0, `0x23d2b0014` <- N x
    24 MHz, `0x23d2b001c` <- 4) right after it programs the power chip's alarm, so as late as
    the commit path allows, before the core's own power-down write. The four writes are logged
    as `commit-write` records.
  - The wake path reads watchdog 1's count, bite and control, and watchdog 0's count, as its
    first instructions, before it re-arms watchdog 1 as its own 60 s fallback (it always did
    that). They go into the log as `wake-reg` records.
- **Host side:** `harness/real_s2r.py` `real_s2r_on(wd1=N)` and `harness/drive135.sh` `WD1=N`.
- **N = 150 s:** later than the 90 s alarm, so "woke at the alarm" (about 90 s) and "reset by
  the watchdog" (about 150 s) are told apart by time. It is also below the bite word's limit
  (178.9 s at 24 MHz).
- **No-hands ways out:** the alarm; and, if the chip stayed up, the watchdog itself.
- **Commands:** `WD1=150 ALARM=90 FULL_SKIP=<det8's four pages> harness/macos-up.sh det11`
  (22:57:25; READY 23:01:24). `harness/detach135.sh det11` with det10's commit list, at
  23:08:22-23:08:23: late, because the M1 was on hold for the coordinator meanwhile; no
  awake-extra snapshot this time. `harness/detached-wake-readout.sh det11`. Then
  `harness/hv-reboot.sh` (23:10:50) and `tools/tb/m1-pmu-dump`.
- Files (private): `tools/hv-trace-kit/runs/20261116-mac135/*-det11.*`,
  `var/commit-state/macos135-det11-*`, `var/m1-state/pmu-20261117-231124-after-det11.txt`.

### Readings

1. **Sleep and wake.**
   - At arm: `RTC alarm at the commit: now + 90 s`, `watchdog 1 at the commit: bites 150 s
     after the commit`.
   - Last core in its sleep path (T) at 24.438 s after the detach (about 23:08:47). The
     hypervisor's watchdog writes went out at T+1.3 ms: bite `0xd693a400` = 3,600,000,000 = 150 s.
   - Wake record at 113.951 s: **asleep 89.51 s** (det9 90.28, det10 90.18). USB device
     left/back 23:10:16.039 / 23:10:16.653, as at det8-det10's wakes.
   - Wake status `+0x1c/+0x20/+0x24` = `0x0 / 0x400000 / 0x0`, as det8-det10. No reset.
   - Read out at 134.7 s; 332,701 entries, 0 dropped.
2. **The watchdog at the wake entry** (before the wake path touched it):

   | Word | Value at the wake entry |
   |---|---|
   | Watchdog 1 count `0x23d2b0010` | **`0x51ae8` = 334,568 ticks = 13.9 ms at 24 MHz** |
   | Watchdog 1 bite `0x23d2b0014` | `0xd693a400` (as written) |
   | Watchdog 1 control `0x23d2b001c` | `0x4` (as written) |
   | Watchdog 0 count `0x23d2b0000` | `0x51b57` (13.9 ms) |
   | Watchdog 2 count `0x23d2b0020` | `0x76f11b` (0.325 s; det8-det10 also 0.325 s) |

   So the bite time and control survived the sleep. The count read 13.9 ms, not about 89.5 s:
   it did not keep counting through the sleep, and watchdog 0's count reads the same 13.9 ms.
   Whether the counts restarted at the chip's power-up or were held is not separated by this
   reading.

   Writes to the watchdog page in the log:
   - macOS, before T only, as in det9 and det10: WD0 count <- 0 and WD1 count <- 0 at T-0.466 s,
     WD0 control <- 0 at T-0.035 s.
   - After the wake: none in the 20.8 s logged.
   - The hypervisor's wake path re-armed watchdog 1 for 60 s at its start and wrote its control
     to 0 before re-entering macOS (its existing code).
3. **Power chip afterwards** (after the reboot, 23:11:24):

   | Register | det11 | det9, det10 |
   |---|---|---|
   | `0x0201` | 00 | 00 |
   | `0x9f03` | 00 | 00 |
   | fault shadow `0xa47b` | `0x000800` | `0x000800` |
   | `0xd000` / `0xd00c` | 01 / 00 | 01 / 00 |
   | `0x9f04`- | `48 00 01 3f ff ff 47 50 00` | the same |

   The fault shadow's button bits, set after ds16 and ds17, were clear again after this
   macOS boot.
4. **The entry's last second against det10.**
   - Phase starts (console lines, s from T): E1 -7.528, E2 -0.849, E3 -0.483, E4 -0.0908,
     E5 -0.0902, E6 -0.0152 (det10: -7.548, -0.876, -0.481, -0.0911, -0.0906, -0.0157).
   - Commit snapshot: 862 words, 0 errors. Against det10 (792 words): 772 equal, 20 different,
     all in the groups that varied before: `MCC.planeN+0x680/684`, `DCSn+0x500` (n = 1, 2, 4-7),
     `ps_dcs0`, `ps_dcs1`, power-gate `0x23b71c0d8`, `0f0`, `108`, `120`.
   - Wake snapshot against det8: 261 equal, 3 different.
   - This capture's idle period before the entry was 24 s instead of about 430 s: the detach
     came late.

The M1 is left in stock Omarchy (kernel 7.3.0-0test5, up since 23:11:04); the camera frame
`var/m1-look/20261117-231127-state-after-det11.jpg` shows the desktop.

## Runs ds17-1, ds17-2, ds17-3 (23:13-23:23): three watchdog runs, the same result each time

Kernel ds17, command line `var/deepsleep/ds17.cmdline` (`wdt=120`, `alarm_secs=60`, snap and
trace off), the M3 cable and charger plugged in (`ac=1`), Naeem at the desk and not touching the
M1. Taken after Hypervisor round 5 showed macOS powering down and waking with watchdog 1 armed
at its commit (the watchdog does not keep that chip up, and its count does not run in sleep).

| Run | Sleep started | M3: host disconnect | Kernel start after reset | Record (`0x9f04`) |
|---|---|---|---|---|
| 1 | 23:13:32 | 23:13:35.38 | 23:15:47 | `44 57 00 40 2c 3d 02 30 7f 00` |
| 2 | 23:17:04 | 23:17:07.95 | 23:19:20 | `44 57 00 40 2c 3d 02 30 81 00` |
| 3 | 23:20:42 | 23:20:46.05 | 23:22:58 | `44 57 00 40 2c 3d 02 30 80 00` |

- In each: no wake at the alarm (+60 s); a reset about 135 s after the start (the 120 s watchdog
  plus the entry and the boot); record 'W' (the commit point reached, the watchdog armed there),
  last access a 32-bit write to `0x23d2c4000` by core 0.
- Power chip after each: `0x0201` = `00` (as macOS's wake in det11 left it: no sleep entry wrote
  `01`), `0x9f03` = `50`, fault shadow `0x000800` (bit 11 `wdog,reset_in_1` only: a watchdog
  reset, no button bits), `0xd000` = `01`, `0xd00c` = `00`.

With ds17 on battery (22:36) that is four of four: after Linux's commit the SoC stays powered
until the watchdog resets it, with and without the M3's cable and charger; under macOS the same
armed watchdog does not stop the power-down (det11).

## Hypervisor round 6: macOS's last steps, each core's own state, and after the commit (det12-det17, 2026-11-17 23:52 to 2026-11-18 01:00)

Readings only. Where a reading was not taken, the text says "unknown". Times are the M3's clock
unless "s from the detach" is given; T is the last core's sleep-path record.

### The change and the runs

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, two local commits on top of
  `bb8873c0`, not pushed:
  - `2ced1fab`: three options, each 0 (off) by default.
    - `hv_s2r_core_state`: each core records its own state at its sleep `CYC_OVRD_EL1` write,
      before the hypervisor stops a timer or clears a pending bit. Records go into the detached
      log as kind 25 (`core-state`). The last core also writes two per-core bitmaps into power-chip
      scratch `0x9f0b` and `0x9f0c`, over the alarm byte.
    - `hv_s2r_keep_state`: the guest's timers (`CNTP_CTL_EL02`, `CNTV_CTL_EL02`), the guest timer
      FIQ enable and the pending virtual IRQ/FIQ bits are left as macOS left them. Only the
      hypervisor's own EL2 timers are stopped.
    - `hv_s2r_sample_ms` / `_max_ms` / `_pmu_every`: the last core samples the brief's words after
      its whole commit, then goes down (kind 26 `sample`).
  - `2cb8a180`: `hv_s2r_sample_hold`, 0 by default. The sampler never goes down. It keeps a summary
    in power-chip scratch `0x9f04`-`0x9f0c`, because a reset keeps that scratch and loses the RAM
    log. At its bound it resets through watchdog 1.
- **Host side:** `harness/real_s2r.py` `real_s2r_on(core_state=, keep_state=, sample_ms=,
  sample_max_ms=, sample_pmu_every=, sample_hold=)`. `harness/drive135.sh` takes `S2R_ARGS`.
  `harness/detached_fmt.py` names kinds 25-27.
- **Commit list:** `var/recfg/commit-snap-list-r6.json` (880 entries) is det10's list plus 17
  words:
  - the AP wake-source masks `0x23d004008`-`0x23d004018`;
  - `0x23d2b8028`, `0x23d2b8040`;
  - watchdog 0's count; watchdog 1's count, bite and control; watchdog 2's count, bite and
    control;
  - `0x23d2c4000`, `0x23b71c360`, `0x23d0d9378`.

  The always-on clock words `0x23d240024`, `03c` and `048` were already in the list. The same list
  was read awake ("awake-extra") before det12's detach.
- **Recipe:** det11's recipe for every run:
  - `WD1=150 ALARM=90 FULL_SKIP=<det8's four pages> S2R_ARGS='...' harness/macos-up.sh detNN`;
  - `harness/detach135.sh detNN` with `commit_snap=<r6 list>`;
  - `harness/detached-wake-readout.sh detNN`;
  - afterwards `harness/hv-reboot.sh` (det12) or nothing (the runs that reset), then
    `tools/tb/m1-pmu-dump`.

  The M1 was claimed as `observation` throughout.
- **The no-hands way out, named before each run:**
  - the hypervisor's alarm at commit + 90 s;
  - watchdog 1 at commit + 150 s (the four writes of R61);
  - for the hold sampler, its own bound of 20 s, then watchdog 1 set to bite at once.

  Every run ended without hands.
- **Files (private):**
  - `tools/hv-trace-kit/runs/20261116-mac135/*-det1[2-7].*`;
  - `var/commit-state/r6_core_state.py` with its output `r6-det12.txt`;
  - `var/commit-state/r6_snapdiff.py` with `macos135-det12-vs-det11.txt`;
  - `var/m1-state/pmu-20261118-*-after-det1[2-7].txt`;
  - camera frames `var/m1-look/20261118-*`.

| Run | Options (besides `core_state=1`, WD1 150, alarm 90) | T (from the RTC alarm, or the log) | Outcome |
|---|---|---|---|
| det12 | none | 431.639 s after the detach (log), about 00:04:10 | **asleep 89.47 s, woke at the alarm** (wake status `0 / 0x400000 / 0`), log read out |
| det13 | `keep_state=1` | about 00:18:44 | **no wake; reset about 5-6 s after the commit**: USB gone 00:18:50.2, Linux kernel start 00:19:02 |
| det14 | `sample_ms=10, sample_max_ms=3000, sample_pmu_every=10` | about 00:31:27 | sampler ran 2.9-3.0 s, then core 0 went down; **no wake; reset**: USB gone 00:31:34.3, kernel 00:31:47 |
| det15 | as det16 | - | not run: macOS panicked while booting under the hypervisor, before the arm (`i2c0::_runInterruptMode RxFIFO doesn't have enough bytes ... hpmBusManager`, `vuart-det15.log`); the M1 restarted into Linux at 00:34:20 |
| det16 | `sample_ms=10, sample_max_ms=20000, sample_pmu_every=10, sample_hold=1` | about 00:47:14 | sampler ran 4.9 s with no change; **reset**: USB gone 00:47:20.4, kernel 00:47:33 |
| det17 | `keep_state=1` (det13 repeated) | about 00:59:31 | **no wake; reset about 6 s after the commit**: USB gone 00:59:37.0, kernel 00:59:49 |

How T was found for the runs that reset (their RAM log was lost):
- At the commit the hypervisor set the alarm to the power chip's clock + 90 s. The dump after
  the reset reads both the alarm `0xd008` and the clock `0xd004`, so T = dump time + (alarm −
  clock) − 90 s. The error is about ±2 s: whole seconds, plus the dump's own time stamp.
- In det13, det14 and det17, `0x9f04` still held the hypervisor's `'W'` wake note, unconsumed.
  The wake trampoline consumes that note, so the next start was a normal boot, not a wake. In
  det16 the hold sampler had replaced the note with its own `'E'` record.
- Power chip after each reset: `0x0201` = `00`, `0x9f03` = `50`, `0xd000` = `41`, fault shadow
  `0xa47b`-`d` = `00 08 00`.
- After det11 and det12 (alarm wakes): `0x9f03` = `00`, `0xd000` = `01`, the same fault shadow.

### 1. Each core's own state at its final `CYC_OVRD_EL1` write (det12; `r6-det12.txt`)

**How the readings were taken.**
- Each core read these at the start of the hypervisor's `CYC_OVRD` handler, before any write of
  the hypervisor's. Timer and `HCR_EL2` values are what the hypervisor had last set, or what the
  guest had left.
- At EL2 (E2H), `CNTP_CTL_EL0` / `CNTV_CTL_EL0` are the hypervisor's own EL2 timers.
- `ISR_EL1` read at EL2 gives the physical I/F/A lines.
- `IPI_SR_EL1` and `PMCR0_EL1` are given twice: the hardware register, and the guest's view that
  the hypervisor keeps (it emulates both).
- These reads made the cores' way down longer: the first `CYC_OVRD` write came at 431.639064 s,
  the last core-down at 431.639360 s, about 0.3 ms. In J it was 31 µs. The outcome was unchanged
  (89.47 s asleep, alarm wake).

Order of the `CYC_OVRD` writes: cores 4, 5, 1, 3, 7, 6, 2, then core 0 about 30 µs later. Every
core wrote `0x3000001`, from guest PC `0xfffffe0014a05f1c`.

Equal on all eight cores:

| Register | Value |
|---|---|
| `CNTP_CTL_EL02` (guest physical timer) | `0x6`: disabled, masked, status set; `CNTP_CVAL_EL02` 0 |
| `CNTKCTL_EL12` | `0x4f` |
| `CNTVOFF_EL2` / `CNTHCTL_EL2` | `0x1286d8f3` / `0xc00` |
| `ISR_EL1` at EL2 | 0 |
| `IPI_SR_EL1` hardware | 0; guest view (hypervisor's "IPI pending") 0; "IPI queued" 0 |
| `IPI_CR_EL1` | `0x600` |
| `PMCR0_EL1` hardware and guest view | `0x7003400`; PMC pending 0; `PMSR_EL1` 0; `UPMCR0_EL1` 0; `UPMSR_EL1` 0 |
| `ACC_OVRD_EL1` | `0x1800101526076207` |
| `CYC_OVRD_EL1` before the write | `0x2000000` |
| SPRR timer pending (hypervisor) | 0 |
| hypervisor's EL2 timers | physical `CTL` 1 (enabled), compare 0.4-0.7 ms ahead; virtual `CTL` 7 (enabled, masked, status set) |
| guest `PSTATE` (`SPSR_EL2`) | D, A, I, F all masked, EL1t; `SSBS` set on cores 1, 3, 2, 0 |

Differing between cores:

| Core (order down) | 4 | 5 | 1 | 3 | 7 | 6 | 2 | 0 |
|---|---|---|---|---|---|---|---|---|
| `CNTV_CTL_EL02` (guest virtual timer) | `0x1` | `0x1` | `0x5` | `0x1` | `0x1` | `0x1` | `0x5` | `0x5` |
| its compare minus the guest's counter then | +89.387 s | +89.387 s | −0.034 s | +0.877 s | +89.387 s | +89.387 s | −0.083 s | −0.083 s |
| `VM_TMR_FIQ_ENA_EL2` | 3 | 3 | 2 | 3 | 3 | 3 | 2 | 2 |
| `HCR_EL2` | `..0029` | `..0029` | `..0069` | `..0029` | `..0029` | `..0029` | `..0069` | `..0069` |

How to read the per-core rows:
- `0x1` = enabled, unmasked, not fired; `0x5` = enabled, unmasked, fired.
- The guest's counter is `CNTPCT_EL0` − `CNTVOFF_EL2`.
- `HCR_EL2` is `0x80032480200029` or `...69`. Bit 6 is the virtual FIQ pending bit (VF).
- So the guest's virtual timer was **enabled and unmasked on all eight cores**. It had already
  fired on cores 1, 2 and 0. On those three cores the hypervisor held a virtual FIQ pending
  (VF) and had masked that timer's FIQ (`VM_TMR_FIQ_ENA` bit 0 clear). No core had a virtual IRQ
  pending.
- On the other five the timer was due 0.88 s later (core 3) or 89.39 s later (cores 4, 5, 7, 6).

These are the values that R59's writes turn off in every power-down.

**The interrupt controller as each core read it** (`0x23b100000` +). Every core read the same
values:
- `+0x2024` (IPI mask, read through the SET register) `0x80000001`;
- all 28 `+0x4180` words (IRQ mask, read through the CLR register, which macOS reads)
  `0xffffffff`;
- all 28 `+0x4000` software-pending words 0;
- the 11 `+0x5004` words 0, and the 11 `+0x5028` words `0x80000001`;
- line state `+0x4200` (HW_IRQ_MON) non-zero in 13 words: `+0x4214` `0x8000000`, `4218` `0x1020`,
  `421c` `0xa0155000`, `4220` `0xa0000000`, `4230` `0x1550000`, `4234` `0x2800`, `4238`
  `0x140000`, `423c` `0x80000000`, `4240` `0x2`, `4244` `0x80000a00`, `4248` `0x2282`, `4250`
  `0x5`; the rest 0.

The register names and the SET/CLR read convention are taken from the Asahi Linux
documentation, https://asahilinux.org/docs/hw/soc/aic/ (documentation, not an observation). That
page also says reading `+0x2004` acknowledges, so it was not read. That every IRQ is masked
follows from that convention; it was not tested here.

Each core's last logged writes before T (det12 log): `PMCR0_EL1` `0x7003400` and `IPI_SR_EL1` 1
on cores 0, 1, 2, 3, 5, 6, 7, at T-0.092 to T-0.091 s. Core 4's are not in the logged window.

**Leaving them as macOS left them (det13 and det17, `keep_state=1`).** The hypervisor still
stopped its own two EL2 timers, and did everything else of A6 as in det12. **Both runs: no
alarm wake; the M1 restarted into a normal boot about 5-6 s after the commit** (T from the
alarm register; the reset from the USB loss and the kernel start time).
- The commit itself got through the held words, the wake note and the alarm. Scratch `0x9f0a`
  read `'P'`, and the bitmaps written after the alarm are present. Whether the last core's
  `CYC_OVRD` write followed is not read.
- Bitmaps (written at the commit, read after the reset):

  | Bitmap | det13 | det17 |
  |---|---|---|
  | `0x9f0c` (guest timer enabled and unmasked) | `0xff`, all eight cores | `0xff` |
  | `0x9f0b` (virtual IRQ/FIQ or a hypervisor-held IPI/PMC interrupt pending) | `0x03`, cores 0 and 1 | `0x09`, cores 0 and 3 |

- Whether the SoC powered down before the reset: unknown. What reset it: unknown.

### 2. After the commit: seven cores down, core 0 sampling

**At the commit, before the instrument's writes** (det12 snapshot, read about 1 ms after T),
against the same list read awake about 7 min earlier:

| Word | Awake | At the commit | At the wake entry (det12) |
|---|---|---|---|
| `0x23d2b8028` | `0x0` | `0x1000000` | `0x8000000` |
| `0x23d2b8040` | `0x20` | `0x20` | `0x22` |
| watchdog 2 count / bite / control | `0x4ee0c17e` / `0x80befc00` / 0 | `0x62189` (16.7 ms) / `0x7270e00` (5 s) / **4** | `0x770474` (0.326 s) / `0x7270e00` / 0 |
| watchdog 0 / 1 count | running | 0.455 s / 0.455 s; watchdog 1 bite `0x55d4a800`, control 0 | 14.1 ms / 14.1 ms (watchdog 1 control 4, bite 150 s, the instrument's) |
| `0x23d2c4000` | 1 | **0** | not read |
| `0x23b71c090` | `0x8004030c` | `0x8004030c` | not read |
| `0x23b71c360` | `0xc004030b` | `0xc004030b` | not read |
| `0x23d0d9378` | 0 | 0 | not read |

So at the commit watchdog 2 had been armed, about 16.7 ms earlier, with a 5 s bite and control 4.
No write of macOS's to the watchdog page is in the log after T-0.035 s (the counts at T-0.466 s,
`0x23d2b8008`, `800c` and `000c` at T-0.035 s; R15). Who armed it is not read.

**det16, sampling with seven cores down** (`sample_hold=1`). This is the scratch summary read
after the reset:
- `'E'`; 4.9 s sampled (`0x31` tenths);
- last `0x23d2b8040` low byte `0x20`; last `0x23d2b8028 >> 24` = `0x01`; last power chip `0x0201`
  `00`;
- flags `0x19`:
  - watchdog 2 control bit 2 set;
  - watchdog 2 counting;
  - `0x23b71c360` bit 30 set;
  - `0x23d2c4000` bit 0 clear;
  - `0x23b71c090` bit 30 clear;
  - no read failed, the 0x0201 reads included;
- first change / last change / changes: **0 / 0 / 0**.

So for the 4.9 s that core 0 kept sampling, none of these changed:
- the progress words, `0x23d2c4000` and the two power gates (read every 10 ms);
- power-chip `0x0201` (read every 100 ms).

Watchdog 2 counted with control bit 2 set. The scratch stopped at 4.9-5.0 s, the bound (20 s) was
not reached, and the M1 started a normal boot. 4.9-5.0 s after sampling began is about when
watchdog 2's 5 s bite, armed about 16.7 ms before T, falls due. What reset the SoC was not read.

**det14** (the sampler logs to RAM and goes down after a 3 s bound): the RAM log was lost with the
reset. The scratch read:
- `'q'` (the sampler stopped and core 0 went on to its `CYC_OVRD` write);
- last update at 2.9 s;
- progress low byte `0x20`.

No alarm wake followed. The reset came about 7 s after the commit (±2 s).

**Not read in any run:** the progress words after 4.9 s with a core up; and anything after the
last core goes down in a run that then resets.

### 3. Wake-source masks and always-on clock words

| Word | Awake (det12, 23:56:5x) | At the commit (det12) |
|---|---|---|
| `0x23d004008` | `0xf3ffafff` | `0xf3ffafff` |
| `0x23d00400c` | `0xffb97eff` | `0xffb97eff` |
| `0x23d004010` | `0xfffdeffe` | `0xfffdeffe` |
| `0x23d004014` | `0xffffffff` | `0xffffffff` |
| `0x23d004018` | `0x03ffff87` | `0x03ffff87` |
| `0x23d240024` | `0x81100100` | `0x81100100` |
| `0x23d24003c` | `0x81100100` | `0x81100100` |
| `0x23d240048` | `0x82100100` | `0x82100100` |

The commit snapshot against det11 (862 common words): 850 equal, 12 differ, all in groups that
varied before:
- `MCC.planeN+0x680/684` (`0xb48`/`0xb74`);
- `ps_dcs0`, `ps_dcs2`, `ps_dcs6`;
- power gate `0x23b71c120`.

Wake snapshot: 259 of 264 equal to det11 (five DCS domain words).

### Left out, and why

- **The brief's item 4** (a commit with nothing of the instrument's own except macOS's final writes
  and watchdog 1): not run. That run leaves macOS's own alarm in place, and its time is not read.
  Watchdog 1 does not count while the chip is asleep (J, R61). So if such a run powered down
  properly, nothing named would wake it without hands. Moving the wake note before the entry
  also changes what macOS reads at `0x9f08` during the entry (the code comment in
  `hv_s2r_register_wake`).
- **The sampler's full history after the commit:** each run that sampled ended in a reset that
  lost the RAM log. Only the scratch summaries above survive.
- **Which of the two kept items matters in det13/det17:** the guest timers left enabled, or the
  virtual FIQs left pending. Not separated: one keep-state configuration was run, twice.
- **AON wake status words, SMC, and the second power chip** at the commit: not added. The brief did
  not ask for them, and their read side effects are not established.

### M1 left

In stock Omarchy (kernel 7.3.0-0test5-1-ARCH, up since 2026-11-18 00:59:49), reached over
Thunderbolt. The camera frame `var/m1-look/20261118-010014-state-after-round6.jpg` shows the
desktop.

## Hypervisor round 7: watchdog 2 around macOS's writes of `0x23d2c4000`, the CPU block and power-gate records, the keep-state split (det18-det22c, 2026-11-18 02:08-03:35)

Readings only. Where a reading was not taken, the text says "unknown". Times are the M3's clock
unless "t" (s from the detach, the M1's timer) is given; T is the last core's sleep-path record.
Taken for the spec's open questions 60, 59 and 61, in that order.

### The change and the runs

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commit `ff8caba0` on top of
  `2cb8a180`, not pushed. Every option 0 (off) by default:
  - `hv_s2r_keep_timers`: the guest's timers (`CNTP_CTL_EL02`, `CNTV_CTL_EL02`) and the guest timer
    FIQ enable (`VM_TMR_FIQ_ENA_EL2`) are left as they were at the core's sleep `CYC_OVRD_EL1`
    write; the pending virtual IRQ/FIQ (`HCR_EL2` VI/VF) are cleared as in every earlier
    power-down.
  - `hv_s2r_keep_vfiq`: the pending virtual IRQ/FIQ are left; the guest's timers and the timer FIQ
    enable are written 0 as in every earlier power-down.
  - (`hv_s2r_keep_state`, round 6, is both at once; unchanged.)
  - `hv_s2r_c4_probe`: on each guest write of `0x23d2c4000` (a traced page: the access traps and
    the hypervisor does it), the writing core reads `0x23d2c4000`, watchdog 2's count, bite and
    control (`0x23d2b0020`, `24`, `2c`), `0x23d2b8028` and `0x23d2b8040` just before the write and
    again just after it, then the timer count; reads only. Log kind 28, each record pushed to
    memory at once.
  - The commit-snapshot table holds 2048 words (detached layout 3; was 1024).
- **Host side:** lab commit `546e9e4`: `harness/real_s2r.py` `real_s2r_on(keep_timers=,
  keep_vfiq=, c4_probe=)`, `harness/detached_fmt.py` (layout 3, kind 28 as `c4-probe` records),
  test `tests/core/test_hv_detached.py::test_s2r_timer_write_probe_records` (the layout test
  checks the struct against the build).
- **Commit list:** `var/recfg/commit-snap-list-r7.json`, 1329 entries: round 6's 880, the CPU
  start/stop block `0x23b754000`-`0x23b75401c` (8 words), and every word of the power-gate page
  from `0x23b71c000` to `0x23b71c704` not already in the list (441; with the 9 already there, all
  450). The same list was read awake ("awake-extra", over the proxy with the guest paused) at each
  detach, about 7 min before the commit. Before the runs the 8 CPU-block words were read once on
  Linux awake (`tools/regmap/scan.sh`, hwdb snapshot 16): all 0, no fault. The power-gate page
  had been read whole on Linux before (hwdb snapshot 12); its non-zero words end at `+0x704`.
- **Recipe:** round 6's, every run: `WD1=150 ALARM=90 FULL_SKIP=<det8's four pages>
  S2R_ARGS='core_state=1, c4_probe=1[, keep_timers=1 | keep_vfiq=1]' harness/macos-up.sh detNN`;
  `PRE=<awake_snap of the r7 list> ARGS='commit_snap=<r7 list>' harness/detach135.sh detNN`;
  `harness/detached-wake-readout.sh detNN`; afterwards `harness/hv-reboot.sh` (the runs that woke)
  and `tools/tb/m1-pmu-dump`. The M1 was claimed as `observation` throughout.
- **The no-hands way out, named before each run:** the hypervisor's alarm at commit + 90 s;
  watchdog 1 at commit + 150 s; and for the keep runs, the reset 5-7 s after the commit seen in
  det13 and det17. Every run ended without hands.
- **Files (private):** `tools/hv-trace-kit/runs/20261116-mac135/*-det18.*`, `*-det19*`, `*-det20*`,
  `*-det21.*`, `*-det22*`; `var/commit-state/r7_probe.py` (outputs `r7-det18.txt`,
  `r7-det19b.txt`, `r7-det21.txt`), `r7_wd2start.py` (`r7-wd2start-det*.txt`),
  `r7-det*-core-state.txt` (round 6's `r6_core_state.py`), `r7-pwrgate-records.md`;
  `var/m1-state/pmu-20261118-*-after-det*.txt`; camera frames `var/m1-look/20261118-0*`.

| Run | Options besides `core_state=1, c4_probe=1`, WD1 150, alarm 90 | T | Outcome |
|---|---|---|---|
| det18 | none | t = 445.324 s | **asleep 89.58 s, woke at the alarm**, wake status `0 / 0x400000 / 0`, log read out |
| det19 | `keep_timers=1` | - | not run: macOS panicked while booting under the hypervisor, before the arm (`i2c0::_runInterruptMode RxFIFO doesn't have enough bytes ... hpmBusManager`, as det15); the M1 restarted into Linux by itself |
| det19b | `keep_timers=1` | t = 433.068 s | **asleep 89.74 s, woke at the alarm**, wake status `0 / 0x400000 / 0`, log read out **[HV-CHANGED setup; outcome as without it]** |
| det20 | `keep_vfiq=1` | - | not run: the same boot panic |
| det20b | `keep_vfiq=1` | about 02:59:12 (±2 s, from the alarm register) | **no wake; reset**: USB device gone 02:59:18.05, Linux kernel start 02:59:30 (M1 clock) **[HV-CHANGED]** |
| det21 | `keep_timers=1` (det19b repeated) | t = 433.659 s | **asleep 89.62 s, woke at the alarm**, wake status `0 / 0x400000 / 0`, log read out **[HV-CHANGED setup; outcome as without it]** |
| det22, det22b | `keep_vfiq=1` | - | not run: the same boot panic, twice |
| det22c | `keep_vfiq=1` (det20b repeated) | about 03:34:02 (±2 s) | **no wake; reset**: USB device gone 03:34:08.81, Linux kernel start 03:34:21 (M1 clock) **[HV-CHANGED]** |

T for the runs that reset is found as in round 6: T = dump time + (alarm `0xd008` − clock
`0xd004`) − 90 s. Of nine bring-ups, four ended in that boot panic before the arm; the options
of this round are written only at the arm.

Power chip after each run:

| Run | `0x0201` | `0x9f03` | `0x9f04`-`0x9f0c` | `0xa47b`-`d` | `0xd000` | `0xd00c` |
|---|---|---|---|---|---|---|
| det18, det19b, det21 (after `hv-reboot.sh`) | `00` | `00` | `48 00 01 3f ff ff 47 50 00` | `00 08 00` | `01` | `00` |
| det20b | `00` | `50` | `57 f0 d1 83 00 02 50 0f ff` | `00 08 00` | `41` | `00` |
| det22c | `00` | `50` | `57 f0 31 a9 00 02 50 07 ff` | `00 08 00` | `41` | `00` |

In det20b and det22c `0x9f04` still held the hypervisor's `'W'` wake note, unconsumed, and
`0x9f0a` its `'P'` stage mark (as det13, det17). `0x9f0b`/`0x9f0c` are round 6's per-core bitmaps
of macOS's own state at each core's final write, before the hypervisor's writes: `0x9f0c` `0xff`
(guest timer enabled and unmasked on all eight cores) in both; `0x9f0b` (a virtual IRQ/FIQ or a
hypervisor-held interrupt pending) `0x0f` (cores 0-3) in det20b, `0x07` (cores 0-2) in det22c.

At the wake entry of det18, det19b and det21: `0x23d2b8028` `0x8000000`, `0x23d2b8040` `0x22`,
`0x23d2c001c` `0xff0`, watchdog 2 bite `0x7270e00`, control 0, count `0x76dfe1` / `0x770fbd` /
`0x76edf3` (0.325-0.326 s); watchdog 1 bite `0xd693a400`, control 4, count 13.7-13.9 ms; as in
det11 and det12.

### 1. Watchdog 2 and the always-on words around macOS's three writes of `0x23d2c4000` (question 60)

macOS wrote `0x23d2c4000` = 1 three times in each of det18, det19b, det21, from core 0, the same
guest PC within a run (det18 `0xfffffe00157be2d0`), at T−15.6/−4.1/−0.97 ms (det18),
T−16.1/−4.6/−0.97 ms (det19b), T−16.0/−4.2/−0.96 ms (det21). No other access to the word is in
the logs. The "before" reads ended 11.9 / 21.1 / 11.5 µs after the trap's access record of the write
(det18 / det19b / det21), the "after" reads 9.4-11.4 µs after the "before" reads.

| Write | Read | `0x23d2c4000` | WD2 count | WD2 bite | WD2 control | `0x23d2b8028` | `0x23d2b8040` |
|---|---|---|---|---|---|---|---|
| 1 | before | **1** | 42.6 / 52.7 / 56.4 µs | `0x7270e00` | **4** | **`0x1000000`** | `0x20` |
| 1 | after | 0 | 52.1 / 64.4 / 65.8 µs | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 2 | before | 0 | 11.575 / 11.562 / 11.776 ms | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 2 | after | 0 | 11.584 / 11.571 / 11.785 ms | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 3 | before | 0 | 14.712 / 15.180 / 15.040 ms | `0x7270e00` | 4 | `0x1000000` | `0x20` |
| 3 | after | 0 | 14.721 / 15.188 / 15.049 ms | `0x7270e00` | 4 | `0x1000000` | `0x20` |

(Counts det18 / det19b / det21, at 24 MHz; every other value the same in all three runs.)

So, in all three runs:
- **Before macOS's first write of `0x23d2c4000` reached the hardware, watchdog 2 was already
  armed** (bite 5 s, control 4) with a count of 43-56 µs, and `0x23d2b8028` already read
  `0x1000000`. Awake (the r7 list read at the detach) they read bite `0x80befc00`, control 0,
  `0x23d2b8028` 0.
- `0x23d2c4000` read 1 before the first write and 0 after each of the three writes of 1.
- Nothing in the six words changed at any of the three writes except the count.
- `0x23d2b8040` read `0x20` throughout (awake also `0x20`).

**When the count started**, from each set (count subtracted from the timer count read just after;
`var/commit-state/r7_wd2start.py`): det18 t = 445.3080573, det19b t = 433.0520395, det21
t = 433.6433051, from the first set. The later sets put it 7-10 µs later (the watchdog's count
runs about 0.05 % slower than the timer, or is read with an offset; not separated), so the start
is good to about ±10 µs. Against the access log (a write's record is put before the write
reaches the hardware; the log has every access to the device space except det8's four skipped
pages and the zones the hypervisor holds, 1.2 of the spec):

| Log record (core 0) | det18 | det19b | det21 |
|---|---|---|---|
| `W 0x23b71c080` = `0x80000000`, `W 0x23b71c088` = `0x80000000` | −29, −25 µs | −32, −29 µs | −29, −25 µs |
| `R 0x23b718000` = `0xf`, `W 0x23b718000` = 0 | −18, −14 µs | −16, −12 µs | −19, −15 µs |
| `R 0x23b718004` = `0xf`, **`W 0x23b718004` = 0** | −9, **−1.3 µs** | −9, **−5.5 µs** | −11, **−7.1 µs** |
| *watchdog 2's count 0* | 0 | 0 | 0 |
| guarded `0x23b7001c8`, `1c0`: read, write (the writes held by the hypervisor, A3) | +4 to +19 µs | −1.5 to +14 µs | +9 to +32 µs |
| `R`/`W 0x23b7001d0` (`0x1400024f` -> `0x400024f`) | +22, +25 µs | +16, +19 µs | +34, +38 µs |
| the first `W 0x23d2c4000` = 1 | +31 µs | +32 µs | +45 µs |

In each run the computed start falls 1.3-7.1 µs after the record of macOS's write
`0x23b718004` = 0 (in det19b also 1.5 µs after the next record, the hypervisor's read of the
guarded `0x23b7001c8`); within the ±10 µs above, the nearest earlier access that reaches the
hardware as a write is `0x23b718004` = 0 and the nearest later one `0x23b7001d0`. That the
timing coincides is a reading; what arms watchdog 2 is not read. (Round 6's "within about 0.3 ms of the first write" came from the count at the commit;
this round gives 31-45 µs **before** it.)

### 2. The keep-state split (question 59) **[HV-CHANGED]**

Each core's own state at its final `CYC_OVRD_EL1` write (round 6's records, before the
hypervisor's writes; `r7-det*-core-state.txt`) was as in det12 and K in all three runs that
woke:

| Run | Guest virtual timer fired (`CNTV_CTL_EL02` `0x5`), `HCR_EL2` VF set, `VM_TMR_FIQ_ENA_EL2` 2 | Enabled, not fired (`0x1`), VF clear, `VM_TMR_FIQ_ENA_EL2` 3: due after the core's final write |
|---|---|---|
| det18 | cores 1, 3, 2, 0 | cores 5, 6, 4, 7: +89.39 s |
| det19b | cores 1, 3, 0 | core 2: +0.063 s; cores 4, 6, 5, 7: +89.39 s |
| det21 | cores 1, 2, 0 | core 3: +0.062 s; cores 7, 5, 6, 4: +89.39 s |

`CNTP_CTL_EL02` `0x6` (disabled) on every core in every run. Order of the cores' sleep writes:
core 0 made its `CYC_OVRD_EL1` write last in det18 and det19b (the last-core record is core 0's);
in det21 core 0's state record came last (t 433.659058) but core 4 took the last-core path
(core 0 counted 7th at 433.659304, core 4 8th at 433.659305). So:
- **(b) `keep_timers=1`** (det19b, det21): every core went down with its guest virtual timer
  enabled and unmasked as macOS left it (fired on three cores, due 62-63 ms later on one core,
  due 89.4 s later on the rest) and its timer FIQ enable as found (2 on the fired cores,
  3 on the rest); the hypervisor cleared VF. **Both runs: power-down, alarm wake after 89.7 s
  and 89.6 s**, the same as det18 without the option.
- **(a) `keep_vfiq=1`** (det20b, det22c): the guest timers and timer FIQ enables written 0; the
  pending virtual FIQ left on the cores the bitmap names (det20b cores 0-3, det22c cores 0-2).
  **Both runs: no alarm wake, a reset about 6-7 s after the commit**, as det13 and det17 (both
  items kept).
- Whether the SoC powered down before the reset in det20b and det22c: unknown. What reset it:
  unknown. Whether the last core's `CYC_OVRD_EL1` write followed the commit: not read (the RAM log
  is lost with the reset).

### 3. The CPU start/stop block and the power-gate page (question 61)

Commit snapshots: 1328 words (the list less one duplicate), 0 read errors in each run, read from
T + 1 µs to T + 1.8-2.6 ms. Awake: the same list at each detach.

**CPU start/stop block `0x23b754000`-`0x23b75401c`:** awake all 8 words 0 (three runs; Linux
awake also 0); **at the commit `0x23b754000` = `0xfe` and `0x23b754004` = `0xfe`**, the other six
0, in all three runs. macOS's writes to the block in the entry (passed to the hardware by the
hypervisor in real-sleep mode, A4): cores 4, 1, 5, 2, 3, 6, 7 each write their own bit (`0x10`,
`0x2`, `0x20`, `0x4`, `0x8`, `0x40`, `0x80`) to `+0x0` at T−0.090 s (det18); no write to `+0x4`
in the entry. After the wake core 0 writes `+0x4`, `+0x8`, `+0xc` once per core.

**Power-gate page `0x23b71c000`-`0x23b71c707`:** 450 words. The page's non-zero words fall in a
header (`+0x000`-`+0x08c`: `0x80000000` at `+0x000`, `010`, ... `080` and `088`) and from `+0x090`
in groups of six words every `0x18` bytes (69 groups to `+0x6f0`; the grouping is the lab's
reading of the values' stride, not a documented layout). macOS's only writes to the page in the
entry are `0x23b71c080` and `0x23b71c088` = `0x80000000` (both read `0x80000000` before), at
T−15.7 ms (det18). Words that differ between awake and the commit, or between runs:

| Word | Awake det18 / det19b / det21 | Commit det18 / det19b / det21 |
|---|---|---|
| `0x23b71c0d8` | `0xc0040307` (all) | `0x80040307` (all) |
| `0x23b71c0ec` | `0x6000000` / `0xc000000` / 0 | `0xc000000` / 0 / `0xc000000` |
| `0x23b71c0f0` | `0xc0040307` (all) | `0x80040307` / `0xc0040307` / `0xc0040307` |
| `0x23b71c104` | `0xc000000` (all) | 0 (all) |
| `0x23b71c108` | `0xc0040307` (all) | `0x80040307` (all) |
| `0x23b71c11c` | `0xc000000` (all) | `0xc000000` / 0 / `0xc000000` |
| `0x23b71c120` | `0xc0040307` (all) | `0x80040307` / `0xc0040307` / `0x80040307` |
| `0x23b71c134` | `0xc000000` (all) | 0 / 0 / `0xc000000` |
| `0x23b71c198` | `0x8004031b` (all) | `0xc004031b` (all) |
| `0x23b71c1ac` | 0 (all) | `0xc000000` (all) |
| `0x23b71c1b0` | `0x8004030a` (all) | `0xc004030a` (all) |
| `0x23b71c1c4` | 0 (all) | `0xc000000` (all) |
| `0x23b71c1d8`, `1f0`, `208`, `220`, `238` | 0 (all) | `0x30000000` (all) |
| `0x23b71c330` | `0xc0040317` (all) | `0x80040317` (all) |
| `0x23b71c344` | `0xc000000` (all) | 0 (all) |
| `0x23b71c348` | `0xc0040302` (all) | `0x80040302` (all) |
| `0x23b71c35c` | `0xc000000` (all) | 0 (all) |
| `0x23b71c5a0` | `0xc004030e` (all) | `0x8004030e` (all) |
| `0x23b71c5b4` | `0xc000000` (all) | 0 (all) |

None of these words is written by macOS in the logged entry. Every other word of the page has one
value in all six readings (awake and at the commit, three runs; det18's values below).
`0x23b71c090` `0x8004030c` and `0x23b71c360` `0xc004030b` at the commit, as in det12.

The whole page in det18 (hex, "a -> **c**" where the commit value differs from the awake one):

| Offset | +0x0 | +0x4 | +0x8 | +0xc | +0x10 | +0x14 |
|---|---|---|---|---|---|---|
| `+0x000` | 80000000 | 0 | 0 | 0 | | |
| `+0x010` | 80000000 | 0 | 0 | 0 | | |
| `+0x020` | 80000000 | 0 | 0 | 0 | | |
| `+0x030` | 80000000 | 0 | 0 | 0 | | |
| `+0x040` | 80000000 | 0 | 0 | 0 | | |
| `+0x050` | 80000000 | 0 | 0 | 0 | | |
| `+0x060` | 80000000 | 0 | 0 | 0 | | |
| `+0x070` | 80000000 | 0 | 0 | 0 | | |
| `+0x080` | 80000000 | 0 | 80000000 | 0 | | |
| `+0x090` | 8004030c | 150002 | 90c0c0c | 11081008 | 0 | 0 |
| `+0x0a8` | c0040301 | 110001 | 10c0c0c | 11081008 | 0 | c000000 |
| `+0x0c0` | 80040608 | 60006 | 10b0b01 | 66020102 | 0 | 0 |
| `+0x0d8` | c0040307 -> **80040307** | d0004 | 40c0c1a | 44181010 | 0 | 6000000 -> **c000000** |
| `+0x0f0` | c0040307 -> **80040307** | d0004 | 40c0c1a | 44181010 | 0 | c000000 -> **0** |
| `+0x108` | c0040307 -> **80040307** | d0004 | 40c0c1a | 44181010 | 0 | c000000 |
| `+0x120` | c0040307 -> **80040307** | d0004 | 40c0c1a | 44181010 | 0 | c000000 -> **0** |
| `+0x138` | 80040308 | 50001 | 1070701 | 11020102 | 0 | 0 |
| `+0x150` | 80040309 | a0002 | 1060601 | 11020102 | 0 | 0 |
| `+0x168` | c0040306 | c0002 | 1070701 | 11020102 | 0 | c000000 |
| `+0x180` | c0040305 | b0001 | 1060601 | 11020102 | 0 | c000000 |
| `+0x198` | 8004031b -> **c004031b** | 2b0003 | 30c1414 | 22081008 | 0 | 0 -> **c000000** |
| `+0x1b0` | 8004030a -> **c004030a** | d0001 | a0c1414 | 11081008 | 0 | 0 -> **c000000** |
| `+0x1c8` | c0040324 | 50003 | 3040404 | 21081008 | 0 -> **30000000** | c000000 |
| `+0x1e0` | c0040324 | 50003 | 3040404 | 21081008 | 0 -> **30000000** | c000000 |
| `+0x1f8` | c004033f | 1c0004 | 7040404 | 21081008 | 0 -> **30000000** | c000000 |
| `+0x210` | c0040312 | 160003 | 30c0c0c | 21081008 | 0 -> **30000000** | c000000 |
| `+0x228` | c0040320 | 140003 | 30c0c0c | 21081008 | 0 -> **30000000** | c000000 |
| `+0x240` | c0040307 | 3f0002 | 10c1414 | 22101008 | 0 | c000000 |
| `+0x258` | c0040308 | a0001 | 90c1414 | 11081008 | 0 | c000000 |
| `+0x270` | c0040321 | 50003 | 3040404 | 21081008 | 30000000 | c000000 |
| `+0x288` | c0040321 | 50003 | 3040404 | 21081008 | 30000000 | c000000 |
| `+0x2a0` | c004030e | a0001 | 4040404 | 21081008 | 30000000 | c000000 |
| `+0x2b8` | c004030c | 120002 | 20c0c0c | 11081008 | 0 | c000000 |
| `+0x2d0` | c0040309 | 140002 | 20c180c | 22281008 | 0 | c000000 |
| `+0x2e8` | c004030e | 280002 | 20c0c0c | 11081008 | 0 | c000000 |
| `+0x300` | c0040332 | 310004 | 60c0c0c | 44081008 | 0 | c000000 |
| `+0x318` | c0040304 | f0002 | 10c0c0c | 22081008 | 0 | c000000 |
| `+0x330` | c0040317 -> **80040317** | 1c0001 | 370c1010 | 11081008 | 0 | c000000 -> **0** |
| `+0x348` | c0040302 -> **80040302** | 10002 | 10c0c0c | 11081008 | 0 | c000000 -> **0** |
| `+0x360` | c004030b | 190002 | 20c0c0c | 11081008 | 0 | c000000 |
| `+0x378` | c0040301 | 10010 | 10c0c0c | 11081009 | 0 | c000000 |
| `+0x390` | c0080860 | 1680024 | 60204020 | ff202020 | 0 | c000000 |
| `+0x3a8` | c0080860 | 1680024 | 60204020 | ff202020 | 0 | c000000 |
| `+0x3c0` | c0040311 | 4c0004 | 20c0c0c | 11081008 | 0 | c000000 |
| `+0x3d8` | c0040304 | d0001 | 10c0c0c | 21081008 | 30000000 | c000000 |
| `+0x3f0` | c004030b | 1b0002 | 10c0c0c | 21081008 | 30000000 | c000000 |
| `+0x408` | c004030b | 1b0002 | 10c0c0c | 21081008 | 30000000 | c000000 |
| `+0x420` | c0040316 | 1f0004 | 30c0c0c | 44081008 | 0 | c000000 |
| `+0x438` | c0040326 | 1b0002 | 80c0c0c | 21081008 | 30000000 | c000000 |
| `+0x450` | c0040326 | 1b0002 | 80c0c0c | 21081008 | 30000000 | c000000 |
| `+0x468` | c0040318 | 1f0001 | 40c0c0c | 21081008 | 30000000 | c000000 |
| `+0x480` | c0040326 | 240002 | 40c0c0c | 11081008 | 0 | c000000 |
| `+0x498` | c0040311 | 140003 | 30c0c0c | 63081008 | 30000000 | c000000 |
| `+0x4b0` | c004036a | 2c0006 | 6d0c0c0c | a5081008 | 30000000 | c000000 |
| `+0x4c8` | c0040326 | 130002 | 50c0c0c | 21081008 | 30000000 | c000000 |
| `+0x4e0` | c0040309 | 50001 | 20c0c0c | 21081008 | 30000000 | c000000 |
| `+0x4f8` | c0040309 | 1f0001 | 80c0c0c | 1109100c | 0 | c000010 |
| `+0x510` | c0040316 | 400003 | 30c0c0c | 11081008 | 0 | c000000 |
| `+0x528` | c0040314 | 300003 | 20c0c0c | 11081008 | 0 | c000000 |
| `+0x540` | c004030f | 1c0002 | 20c0c0c | 11081008 | 0 | c000010 |
| `+0x558` | c0040321 | 290003 | 60c0c0c | 22081008 | 0 | c000010 |
| `+0x570` | c004030d | 150001 | 20c0c0c | 11081008 | 0 | c000010 |
| `+0x588` | c004030d | 150001 | 20c0c0c | 11081008 | 0 | c000010 |
| `+0x5a0` | c004030e -> **8004030e** | 230003 | 2040404 | 22081008 | 0 | c000000 -> **0** |
| `+0x5b8` | 80040302 | 140001 | 10c0c0c | 11081008 | 0 | 0 |
| `+0x5d0` | c0040306 | 90001 | 10c0c0c | 11081008 | 0 | c000000 |
| `+0x5e8` | c0040312 | 2b0003 | 30c0c0c | 11081008 | 0 | c000000 |
| `+0x600` | c0040302 | 140001 | 10c0c0c | 11081008 | 0 | c000000 |
| `+0x618` | c0040306 | 90001 | 10c0c0c | 11081008 | 0 | c000000 |
| `+0x630` | c0040312 | 2b0003 | 30c0c0c | 11081008 | 0 | c000000 |
| `+0x648` | c0040301 | f0003 | 10c380c | 330c140c | 0 | c000000 |
| `+0x660` | c0040301 | c0001 | 10e700e | 11141414 | 0 | c000000 |
| `+0x678` | c004030b | 160003 | 90c380c | 42081008 | 30000000 | c000000 |
| `+0x690` | c00403b0 | 7c0019 | d10cd20c | 33081008 | 0 | c000000 |
| `+0x6a8` | c0040307 | 2d0002 | 30cd20c | 11081008 | 0 | c000000 |
| `+0x6c0` | c0040307 | 2d0003 | 30cd20c | 22081008 | 0 | c000000 |
| `+0x6d8` | c0040307 | 2d0005 | 30cd20c | 44081008 | 0 | c000000 |
| `+0x6f0` | c0040307 | 2d0009 | 30cd20c | 88081008 | 0 | c000000 |

### Left out, and why

- **Nothing of the three asked readings.** Question 60: three captures (det18, det19b, det21).
  Question 59: each half of the split run twice (det19b and det21; det20b and det22c); the
  configuration that had failed twice (`keep_state=1`, det13 and det17) was not run again.
  Question 61: the 8 CPU-block words and the 450 power-gate words, awake and at the commit, three
  times.
- **In the runs that reset (det20b, det22c)** the RAM log, with its probe records, commit
  snapshot and per-core records, was lost; only the power chip's scratch survives. Whether the
  SoC powered down before the reset, and what reset it: unknown.
- **What arms watchdog 2** and what sets `0x23d2b8028` bit 24: not read. The probe gives their
  state at macOS's writes of `0x23d2c4000` only; the earliest reading has both already set.
- **The probe itself** is a change: about 10-20 µs of hypervisor reads inside each of the three
  writes. The runs with it and no keep option (det18) and with `keep_timers` (det19b, det21)
  powered down and woke as det11 and det12 did without it.
- **The boot panic** (`i2c0 ... hpmBusManager`) ended four bring-ups before the arm (det19, det20,
  det22, det22b); each time the M1 restarted into Linux by itself. Its cause was not looked into.
- Open question 55 (macOS's commit without the instrument's last-core acts) was not asked for and
  was not run.

### M1 left

In stock Omarchy (kernel 7.3.0-0test5-1-ARCH, up since 2026-11-18 03:34:21 after det22c's
reset), reached over Thunderbolt. The camera frame
`var/m1-look/20261118-033445-state-after-det22c.jpg` shows the desktop.

## Linux awake, stock kernel (2026-11-18 03:54): the power-gate header and CPU block words

Read over `/dev/mem` on the M1 in stock Omarchy (kernel 7.3.0-0test5, awake, nothing
suspended), one 32-bit read each, for the spec's open question 64: `0x23b71c000` = `0x0`;
`0x23b71c040` = `0x80000000`; `0x23b754000` = `0x0`; `0x23b754004` = `0x0`. (The spec: macOS
reads `0x23b71c000` = `0x80000000` awake and at its commit in every capture.) The same words at
Linux's commit are not read.

## Hypervisor round 8: the power-gate header word `0x23b71c000` cleared before the cores' final writes (det23, det24, 2026-11-18 03:58-04:32)

Readings only. Times are the M3's clock unless "t" (s from the detach, the M1's timer) is given;
T is the last core's sleep-path record. Taken for the spec's open question 67. Naeem stopped the
round after det24 ("Stop after this one"); det25 (both header words) was brought up but not run,
and question 66 was not run.

**Short answer: with `0x23b71c000` written 0 by the hypervisor in the cores' sleep path, and
reading 0 at the commit, macOS powered down and woke at the 90 s alarm in both runs (asleep
90.00 s and 89.65 s), as det18 did without the change. [HV-CHANGED]**

### The change and the runs

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commit `9ec6b9c7` on top of
  `ff8caba0`, not pushed. One option, `hv_s2r_pg_clear`, 0 (off) by default:
  - bit 0: the hypervisor writes `0x23b71c000` = 0; bit 1: also `0x23b71c040` = 0 (not run);
  - once per sleep, on the first core to take the hypervisor's sleep `CYC_OVRD_EL1` path, before
    that core's own `CYC_OVRD_EL1` write and after macOS's last write to the page (`0x23b71c080`,
    `088` at about T−15.7 ms, round 7);
  - bit 2 clear (det23, `pg_clear=1`): the write comes after that core's round-6 state record;
    bit 2 set (det24, `pg_clear=5`): before it;
  - the two header words are read just before and just after the write (log kind 28, seq 100),
    and again at the end of the commit note into power-chip scratch `0x9f0a` (over `'P'`):
    `0xc0 | (0x23b71c000 bit 31) | (0x23b71c040 bit 31) << 1`, for a run that resets. Both runs
    woke, and the wake path rewrites the scratch, so that byte was not needed.
- **Host side:** `harness/real_s2r.py` `real_s2r_on(pg_clear=)`.
- **Recipe:** det18's (round 7), with one change:
  - `WD1=150 ALARM=90 FULL_SKIP=<det8's four pages> S2R_ARGS='core_state=1, c4_probe=1, pg_clear=N' harness/macos-up.sh detNN`;
  - `PRE=<awake_snap of the r7 list> ARGS='commit_snap=<r7 list>' harness/detach135.sh detNN`;
  - `harness/detached-wake-readout.sh detNN`, `harness/hv-reboot.sh`, `tools/tb/m1-pmu-dump`.

  The M1 was claimed as `observation` throughout.
- **No same-session control run.** The build with the option off is the round-7 code plus the
  option's unused branches. The control is det18 (round 7, 2026-11-18 02:16).
- **The no-hands way out, named before each run:** the hypervisor's alarm at commit + 90 s;
  watchdog 1 at commit + 150 s; and the reset 5-7 s after the commit seen in every failed run.
- **Boot panic:** none in three bring-ups (det23, det24, det25).
- **Files (private):**
  - `tools/hv-trace-kit/runs/20261116-mac135/*-det23.*`, `*-det24.*`, `*-det25.*`;
  - `var/commit-state/r8-det23.txt`, `r8-det24.txt` (`r7_probe.py`), `r8-det2[34]-core-state.txt`
    (`r6_core_state.py`), `r8-det2[34]-vs-det18.txt` (`r6_snapdiff.py`);
  - `var/m1-state/pmu-20261118-041248-after-det23.txt`, `pmu-20261118-042720-after-det24.txt`,
    `pmu-20261118-043229-after-det25-bringup.txt`;
  - camera frame `var/m1-look/20261118-043227-state-after-round8.jpg`.

| Run | `pg_clear` | Detach | T | Outcome |
|---|---|---|---|---|
| det23 | 1 (`0x23b71c000`, after the first core's state record) | 04:02:17 | t = 425.210867 (core 0) | **asleep 89.998 s, woke at the alarm**: USB gone 04:10:50.541, back 04:10:51.155; wake status `0 / 0x400000 / 0`; log read out, 0 dropped **[HV-CHANGED]** |
| det24 | 5 (`0x23b71c000`, before the first core's state record) | 04:17:16 | t = 433.976776 (core 0) | **asleep 89.649 s, woke at the alarm**: USB gone 04:25:58.541, back 04:25:59.155; wake status `0 / 0x400000 / 0`; log read out, 0 dropped **[HV-CHANGED]** |
| det25 | 7 (both words, before) | - | - | not run: macOS came up (READY 04:31:35, no panic); the stop came before the detach; the M1 was rebooted out of the hypervisor with `hv-reboot.sh` (04:31:52) without a sleep |

### 1. The write and the word at the commit

| | det23 | det24 |
|---|---|---|
| Core that wrote | core 2 | core 4 |
| Read just before (t) | 425.210853: `0x23b71c000` `0x80000000`, `0x23b71c040` `0x80000000` | 433.976488: the same |
| Read just after (t) | 425.210861: `0x23b71c000` **`0x0`**, `0x23b71c040` `0x80000000` | 433.976495: `0x23b71c000` **`0x0`**, `0x23b71c040` `0x80000000` |
| The cores' state records began | t 425.210572-425.210604 (all eight) | t 433.976486-433.976526 |
| Core-down records (each logged just before that core's own `CYC_OVRD_EL1` write) | core 1 425.210853, core 3 .210855, cores 4, 6, 5, 7 .210860-.210861, core 2 .210864, core 0 (last) .210867 | cores 7, 5, 1, 6, 2, 4, 3 433.976756-.976769, core 0 (last) .976776 |
| The write against the cores' final writes | 6-14 µs before T. Before the down records of six cores; at the same time as cores 1 and 3 logged going down (their final writes follow their records; at this resolution, before or after the clear is not separated) | **281-288 µs before T, 261 µs before the first core-down record: before every core's final write** |
| Commit snapshot (T + 1 µs to T + 2 ms): `0x23b71c000` / `0x23b71c040` | **`0x0`** / `0x80000000` | **`0x0`** / `0x80000000` |
| Awake (r7 list at the detach) | `0x80000000` / `0x80000000` | `0x80000000` / `0x80000000` |

So in both runs the word read 0 at the commit, and macOS's power-down and alarm wake followed.
No access by macOS to `0x23b71c000` is in either log between the clear and the wake.

At the wake, as in every earlier capture, core 0 read `0x23b71c000` = 0 and wrote it
`0x80000000`, then read and wrote `0x23b71c040` = `0x80000000`. This came at wake + 7.7 ms
(det23) and + 7.8 ms (det24); det18: + 7.5 ms.

### 2. The rest of the commit, against det18

- macOS's three writes of `0x23d2c4000` = 1 (core 0): det23 at T−15.8 / −4.1 / −0.98 ms, det24
  at T−15.8 / −4.1 / −0.95 ms.
- Watchdog 2 at the first write: already armed. Bite `0x7270e00`, control 4, count 38 µs (det23)
  and 57 µs (det24). `0x23d2b8028` read `0x1000000` and `0x23d2b8040` `0x20` at all three
  writes. All as det18.
- Each core's state at its final write (round-6 records):
  - det23: guest virtual timer fired (`CNTV_CTL_EL02` `0x5`) on cores 2, 1 and 0; `HCR_EL2` VF
    set on cores 3, 2, 1 and 0.
  - det24: fired on cores 1 and 0; VF set on cores 1 and 0.
  - The rest as in round 7.
- CPU start/stop block at the commit: `0x23b754000` = `0x23b754004` = `0xfe`, the other six 0
  (awake all 0), as det18.
- Commit snapshot against det18 (1328 words): 18 differ in det23 and 23 in det24.
  - Besides `0x23b71c000` and the watchdog counts, all are in groups that varied before:
    `MCC.planeN+0x680/684`, `ps_dcs` words `0x23b700300`-`338`, the power-gate group
    `0x23b71c0d8`-`134`, and in det24 `0x2002c0500`.
  - In det24 the power-gate group read differently from round 7: awake `0x23b71c120` =
    `0x80040307` and `0x23b71c0ec` = 0, and at the commit `0x23b71c0d8`, `0f0`, `108` and `120` =
    `0xc0040307`. In det18, det19b and det21 those four read `0x80040307` at the commit, except
    `0f0` in det19b and det21 and `120` in det19b (`0xc0040307`).
- At the wake entry (det23 / det24):
  - `0x23d2b8028` `0x8000000`, `0x23d2b8040` `0x22`, `0x23d2c001c` `0xff0`;
  - watchdog 2 count `0x77066e` / `0x76f2c8` (0.325 s), bite `0x7270e00`, control 0;
  - watchdog 1 count `0x52c8e` / `0x51957` (13.8 / 13.9 ms), bite `0xd693a400`, control 4.

  As in det11-det21.

### 3. Power chip afterwards

| After | `0x0201` | `0x9f03` | `0x9f04`-`0x9f0c` | `0xa47b`-`d` | `0xd000` | `0xd00c` |
|---|---|---|---|---|---|---|
| det23, det24 (after `hv-reboot.sh`) | `00` | `00` | `48 00 01 3f ff ff 47 50 00` | `00 08 00` | `01` | `00` |
| det25's bring-up, rebooted without a sleep | `00` | `ff` | `00 00 00 00 00 00 00 00 00` | `00 08 00` | `01` | `00` |

det23 and det24 are the same as det18, det19b and det21.

### Left out, and why

- **`0x23b71c040` cleared as well** (`pg_clear=7`, det25): brought up, not run. Naeem stopped the
  round.
- **Question 66** (a pending interrupt at a core after its final write): not run, for the same
  reason. A draft of an instrument for 66(b) was written and not built or run. It turns on the
  fired timer's FIQ to the core and counts the hypervisor's FIQ entries on cores already down.
  It is kept outside the repositories, in the session scratchpad (`round8-full.patch`). For
  66(a), round 6's records show the guest's `PSTATE` with D, A, I and F all masked at each
  core's final write. A pending virtual FIQ there is not taken as an exception, so a core
  leaving its wait need not enter the hypervisor. Counting those exits would need the
  hypervisor to trap `WFI`, which changes the wait being measured.
- **A same-session control with the option off:** not run (see above). det18 is the control.

### M1 left

In stock Omarchy (kernel 7.3.0-0test5-1-ARCH, up since 2026-11-18 04:32:05, after the reboot
out of det25's bring-up), reached over Thunderbolt. The camera frame
`var/m1-look/20261118-043227-state-after-round8.jpg` shows the desktop. The claim is released.

## Run ds19 (2026-11-18 07:00): round 8's driver and glue; the same outcome as ds17

Kernel ds19 (`07e52310e`, package `var/kernels/ds19/`, sha256 `d11bb2f5...2bf`): the logic at
deepsleep-clean `46dfa94` (261/261 from tests `202e351`: each core's last job masks D/A/I/F,
masks a fired timer, writes `PMCR0_EL1` = `0x7003400`, clears HCR_EL2 VI/VF, writes
`IPI_SR_EL1` = 1, then R43's accesses), and the glue after the independent glue tests (126/126 at
`3329bdf`) and review (pending SError taken before core 0's final write, no record after a final
write, R61's arming order, AIC per-core setup redone after a wake, translator pages mapped, DAIF
and HCR_EL2 served). Command line `var/deepsleep/ds19.cmdline` (`wdt=120`, `alarm_secs=60`, no
snap, trace or probe). Cable and charger in (`ac=1`).

- Sleep started 07:00:47; the M3 saw the host disconnect at 07:00:50.41. No wake at the alarm.
- The M1 came back in stock Omarchy with kernel start 07:03:02 (about 135 s after the start:
  the 120 s watchdog plus entry and boot, as ds17-1..3).
- Record `44 57 00 40 2c 3d 02 30 9b 00` = 'W' (commit reached, watchdog armed), last access a
  32-bit write to `0x23d2c4000` by core 0. Power chip after: `0x0201` = `00`, `0x9f03` = `50`,
  fault shadow `0x000800` (watchdog reset only), `0xd000` = `01`, `0xd00c` = `00`.

So with the cores' final state as R59/R65 now ask, the SoC still stays up after the commit until
the watchdog. What each core actually had pending at its final write is not read in this run
(probe off).
