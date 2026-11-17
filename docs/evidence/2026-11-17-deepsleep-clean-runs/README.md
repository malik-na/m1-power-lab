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
