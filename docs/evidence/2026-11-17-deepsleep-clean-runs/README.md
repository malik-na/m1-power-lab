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

## Runs ds19p-74, ds19p-75 (2026-11-18 07:05-07:11): the cores at their final write, read by the probe

Kernel ds19 with `apple_deepsleep.probe=1` (`var/deepsleep/ds19p.cmdline`: ds19's plus probe),
`probe_k` set at run time; cable and charger in. Each run: no wake at the alarm, watchdog reset
about 150 s after the start, `0x0201` = `00`. Decode per the glue's probe table (record byte 1
`'q'` = probe record with the watchdog armed; `[2..3]` k with bit 15 = captured; `[4..7]` the
value; `[8..9]` = 76 values captured).

| k | Record | Value | Meaning (4 bits per core c at bits 4c..4c+3) |
|---|---|---|---|
| 74 | `44 71 4a 80 00 00 00 00 4c 00` | `0x00000000` | at each core's final write: `ISR_EL1` F, I, A and `IPI_SR_EL1` bit 0 all clear, cores 0-7 |
| 75 | `44 71 4b 80 ef ee ee fe 4c 00` | `0xfeeeeeef` | ISTATUS of the four timer controls (bit 0 EL2 virtual, 1 EL2 physical, 2 `CNTV_CTL_EL02`, 3 `CNTP_CTL_EL02`): core 0 and core 7 `0xf` (all four set), cores 1-6 `0xe` (all but the EL2 virtual timer) |

So at every core's final write nothing is pending at the core (`ISR_EL1`, fast IPI), while most
timers' conditions are met (ISTATUS 1). Whether those timers are enabled and unmasked is not in
these two values (the per-core controls are probe k = 18 + 7c + r, r 2-5; not read).

## Runs ds19p, k 20-28 and 67-70 (2026-11-18 17:31-18:16): the timer controls at the final write

Twelve probe runs of ds19 (`probe=1`, `wdt=120`, cable and charger in), one value each, the
per-core timer controls at the core's final write (probe k = 18 + 7c + r; r 2 EL2 virtual
`CNTV_CTL_EL0`, 3 EL2 physical `CNTP_CTL_EL0`, 4 `CNTV_CTL_EL02`, 5 `CNTP_CTL_EL02`; bit 0
ENABLE, 1 IMASK, 2 ISTATUS). Every run ended in the watchdog reset; every record was 'q' with the
value captured.

| Core | EL2 virtual | EL2 physical | guest virtual | guest physical |
|---|---|---|---|---|
| 0 | `0x4` (off, condition met) | `0x7` (on, masked, met) | `0x7` | `0x7` |
| 1 | `0x0` | `0x0` | `0x0` | `0x7` |
| 7 | `0x0` | `0x0` | `0x0` | `0x7` |

So no timer is on and unmasked at any of these cores' final write; several are on, masked, with
their condition met. Each value is from a separate run. For core 7, run ds19p-75 (07:11) showed
all four ISTATUS bits set, while these runs read ISTATUS 0 for three of them: run-to-run
variation or a misreading in one of the two modes; not settled. Cores 2-6 not read.

## Hypervisor round 9: candidates injected into macOS (det26-det32r, 2026-11-18 19:09-21:11)

Readings only, every run **[HV-CHANGED]**. Taken for the spec's open question 68 (section 8.2,
candidates C1-C17, at lab commit 99aee86). In each run the hypervisor put one candidate's words
into the state Linux reads before its entry, at the start of macOS's sleep entry. Times are the
M3's clock unless "t" (s from the detach marker, the M1's timer) is given; T is the last core's
sleep-path record. Where a reading was not taken, the text says "unknown".

**Short answer.** Seven candidates were run, in the order asked:
- **C2, C6, C5, C7: macOS powered down and woke at the 90 s alarm** with the words in Linux's
  state at the commit.
- **C4: woke, but the write was not taken.** The words read 0 straight after the hypervisor
  wrote 3, and 0 at the commit, so this run does not test C4.
- **C3 and C17: no power-down, no wake, a restart, twice each.** In all four the hypervisor's
  commit note was never written.
  - C3: the restart came about 144-153 s after the injection.
  - C17: it came about 5-19 s after the injection, near the time the commit comes in the runs
    that woke.
- **Not run:** C9, C16 and C14, left for a later round (the coordinator's stop after det32r).

### The change and the runs

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commits `0eef8cb2` and
  `52a272cf` on top of `9ec6b9c7`, not pushed. The build the runs used reports itself on USB as
  `v2.0.0-145-gfea`: it was built from `52a272cf`'s source before that commit was amended from
  `fea0c2c2`. The option is `hv_s2r_cand`, 0 (off) by default; `hv_s2r_cand = N` does the
  following:
  - **Where it acts:** once, at macOS's first write of I2C3's power-domain word `0x23b700208`
    after the detach. The hypervisor traps that write (a traced page) and makes the candidate's
    writes on the trapping core before passing macOS's write on.
  - **Why there:** it is the first step of macOS's idle sleep entry (the audio path's I2C3 cycles,
    phase E1). In det12, det21, det23 and det24 that word's first write came 7.52-7.55 s before
    T, with no write of it in the 420-430 s of idle before. That makes it the latest point before
    the entry at which the hypervisor runs without a new trap or timer. The writes are made by the
    hypervisor with no other change to macOS's path.
  - **Logging:** each word is read before and after (detached log kind 28, seq 200 + N), with a
    time record at the start and end. At the end of the commit note the last core reads the words
    again (phase 4) and writes power-chip scratch `0x9f0a` = `0x80 | N`, plus `0x40` if injected
    and `0x20` if every word still read the injected value.
  - **No restore:** the injection is never undone. The wake's own I2C3 writes do not inject
    again.
  - **Watchdog:** with `hv_s2r_wd1_secs` set, watchdog 1 is also armed at the injection, before
    the writes, with the same 150 s bite. That is the way out if the entry hangs before the
    commit. The commit re-arms it (count 0) as in every run since det11. This is part of the
    change. C2, C6, C4, C5 and C7 had it and powered down and woke as det18 did without it.
- **Linux's values written** (spec 8.2 and the Linux readings it cites):

  | Cand. | Words | Written |
  |---|---|---|
  | C2 | `0x23b748400`, `800`, `c00`, `000` (R22a's order) | 0 each; then each status word (`0x23b7487e0`, `be0`, `fe0`, `3e0`) read until its low byte is 0, at most 10 ms |
  | C6 | `0x23b71c000` | 0 |
  | C4 | DCSn+`0x7b0` = `0x2002007b0` + n × `0x40000`, n = 0-7 | 3 |
  | C3 | `0x23b058000`, `0x23b05c000`, `0x23b060000` | `0x444`, `0x666`, `0x333` |
  | C5 | the twelve domains `0x23b700118`, `120`, `128`, `148`-`168`, `1a8`, `1b0`, `1d8`, `1e8` | (v & ~`0x3ff`) \| 4 (request 4), then read until bits 4-7 = 4, at most 10 ms |
  | C7 | `0x23d24003c`, `0x23d240048` | `0x01101100`, `0x00101100` |
  | C17 | the 28 SoC clock words of 8.2 C17 (`0x23b040000`-`0x23b040138`) | bits 24-27 = 6 (`0x23b0400b0`: 2), the other bits as read |

  Also written in the code, never run: C9 (MSG, ATC1_COMMON, ATC1_USB_AON, ATC1_PCIE, ATC1_USB
  on, request `0xf`, no bit 28), C14 (the six audio words and `0x23b048000` = 0), C16 (GPIO off,
  R56 form 1).
- **Host side:** `harness/real_s2r.py` `real_s2r_on(cand=N)`.
- **Recipe:** det18's (round 7) with `cand=N`:
  - `WD1=150 ALARM=90 FULL_SKIP=0x23b738000+0x4000,0x23bc34000+0x4000,0x210e20000+0x4000,0x211e20000+0x4000 S2R_ARGS='core_state=1, c4_probe=1, cand=N' harness/macos-up.sh detNN`;
  - `PRE=<awake_snap of commit-snap-list-r7.json> ARGS='commit_snap=<that list>' harness/detach135.sh detNN`;
  - `harness/detached-wake-readout.sh detNN`, then `harness/hv-reboot.sh` (the runs that woke),
    then `tools/tb/m1-pmu-dump` once Linux answered.

  The M1 was claimed as `observation` throughout. The runs were driven unattended, one after
  another, by a session script. No boot panic happened in nine bring-ups.
- **The no-hands ways out, named before the runs:**
  - the hypervisor's alarm at commit + 90 s;
  - watchdog 1 at commit + 150 s;
  - watchdog 1 armed at the injection (150 s), for a hang before the commit;
  - the 5-7 s reset of the earlier failed runs.

  Every run ended without hands.
- **The time of a restart** is the M3's "USB device gone" time. Linux's kernel started 12-13 s
  later each time (M1 clock).
  - In the runs that woke, the detach marker came 1.27-1.74 s before the read-out script's
    "watching" stamp. The injection came at t = 427.94-434.99, and T 7.45-7.59 s after the
    injection.
  - For the runs that restarted, the RAM log is lost, so their injection time is not read. The
    ranges below are worked out from those intervals.
- **Files (private):**
  - `tools/hv-trace-kit/runs/20261116-mac135/*-det26*` to `*-det32r*`;
  - `var/commit-state/r9_cand.py` and its outputs `r9-det26.txt`, `r9-det27.txt`,
    `r9-det28.txt`, `r9-det30.txt`, `r9-det31.txt`;
  - `var/m1-state/pmu-20261118-*-after-det2[6-9]*.txt`, `*-after-det3[0-2]*.txt`;
  - camera frames `var/m1-look/20261118-20*-det29r-d*.jpg` and `20261118-21*-det32r-d*.jpg`.

| Run | Cand. | Injection (t, T−) | Words after the injection / at the commit | Outcome |
|---|---|---|---|---|
| det26 | C2 | 433.751, T−7.448 (core 3) | control words 1 -> 0; status `0x23b7487e0` `0x494002` -> `0x494900`, `be0` 0, `fe0` `0x494900`, `3e0` `0x515100` (unchanged); at the commit the same | **asleep 89.463 s, woke at the alarm**, wake status `0 / 0x400000 / 0` **[HV-CHANGED]** |
| det27 | C6 | 432.943, T−7.494 (core 1) | `0x80000000` -> 0; 0 at the commit | **asleep 89.621 s, woke at the alarm**, `0 / 0x400000 / 0` **[HV-CHANGED]** |
| det28 | C4 | 431.300, T−7.513 (core 3) | **0 before and 0 after the write of 3**, on all eight; 0 at the commit: the write was not taken | asleep 89.725 s, woke at the alarm, `0 / 0x400000 / 0`. Not a test of C4 **[HV-CHANGED setup; candidate not in Linux's state]** |
| det29 | C3 | not read (log lost) | not read | **no wake; restart**: USB gone 19:55:19.2-19.7 + t 578.9-579.4 = 20:04:58.556; kernel 20:05:11. That is about injection + 144-151 s, or about 136-144 s after the time T came in the runs that woke **[HV-CHANGED]** |
| det29r | C3 (det29 repeated) | not read | not read | **no wake; restart**: USB gone 20:19:12.975 (t 580.5-581.0, about injection + 146-153 s); kernel 20:19:25 **[HV-CHANGED]** |
| det30 | C5 | 434.990, T−7.552 (core 1) | all twelve request 0 -> request 4 (`0x0f000200` -> `0x0f000244`, `0x200` -> `0x244`); the same at the commit | **asleep 89.664 s, woke at the alarm**, `0 / 0x400000 / 0` **[HV-CHANGED]** |
| det31 | C7 | 427.940, T−7.590 (core 3) | `0x81100100` -> `0x01101100`, `0x82100100` -> `0x00101100`; the same at the commit | **asleep 89.477 s, woke at the alarm**, `0 / 0x400000 / 0` **[HV-CHANGED]** |
| det32 | C17 | not read | not read | **no wake; restart**: USB gone 20:58:46.200 (t 446.4-446.9, about injection + 11-19 s, about 4-12 s after the time T came in the runs that woke); kernel 20:58:58 **[HV-CHANGED]** |
| det32r | C17 (det32 repeated) | not read | not read | **no wake; restart**: USB gone 21:10:40.060 (t 439.7-440.1, about injection + 5-12 s, within −3 to +5 s of the time T came in the runs that woke); kernel 21:10:51 **[HV-CHANGED]** |

### 1. The runs that woke (C2, C6, C4, C5, C7)

- **Access by macOS between the injection and T:** none, to any injected word (the full access
  log).
  - C2 is the exception, as expected: macOS's own R22a at T−16.1 ms read each control word 0,
    wrote it 0 and read its status. The status values were `0x494900`, 0, `0x494900` and
    `0x515100`, as at det18's commit.
- **macOS's wake:**
  - wrote the four sub-blocks 1 (C2);
  - read `0x23b71c000` = 0 and wrote it `0x80000000` (C6, T+89.629);
  - lowered the twelve request-4 domains by its own form 3 ((v & ~`0x3ff`) | `0x340`, reads
    `0x200`), as at every wake (C5).
- **C7 at the wake entry:** the hypervisor's wake snapshot, read before macOS ran, had
  `0x23d24003c` = `0x81100100` again, with no write by anyone in the log, while `0x23d240048`
  still read `0x00101100`.
- **C4:** DCSn+`0x7b0` read 0 just before the hypervisor's write, 0 just after it (1 µs later)
  and 0 at the commit, on all eight. The commit list has also read 0 there in every earlier
  capture. Whether some other way would take a write from EL2 is unknown.
- **Wake entry:** as det18 in all five: `0x23d2b8028` `0x8000000`, `0x23d2b8040` `0x22`,
  `0x23d2c001c` `0xff0`; watchdog 2 count 0.325 s, bite `0x7270e00`, control 0; watchdog 1
  count 14.0-14.1 ms, bite `0xd693a400`, control 4. The scratch byte `0x9f0a` is rewritten
  by the wake path, so it was not needed in these runs.
- **Power chip after `hv-reboot.sh`, all five:**
  - `0x0201` = `00`, `0x9f03` = `00`;
  - `0x9f04`-`0x9f0c` = `48 00 01 3f ff ff 47 50 00`;
  - `0xa47b`-`d` = `00 08 00`, `0xd000` = `01`, `0xd00c` = `00`.

  These are the same as det18, det23 and det24.

### 2. How the C3 and C17 runs ended

Power chip after the restart (Linux up, `tools/tb/m1-pmu-dump`):

| Run | `0x0201` | `0x9f03` | `0x9f04`-`0x9f0c` | `0xa47b`-`d` | `0xd000` | `0xd008`-`b` (alarm) | `0xd00c` |
|---|---|---|---|---|---|---|---|
| det29 (C3) | `00` | **`ff`** | all `00` | `00 08 00` | `01` | `c9 ab 0a 00` = det28's alarm, unchanged | `00` |
| det29r (C3) | `00` | **`ff`** | all `00` | `00 08 00` | `01` | `c9 ab 0a 00`, unchanged | `00` |
| det32 (C17) | `00` | `00` | all `00` | `00 08 00` | `01` | `ee b8 0a 00` = det31's alarm, unchanged | `00` |
| det32r (C17) | `00` | `00` | all `00` | `00 08 00` | `01` | `ee b8 0a 00`, unchanged | `00` |

What these readings show:
- **The commit was not reached in any of the four.**
  - At the commit the hypervisor writes the `'W'` note at `0x9f04`, then the alarm, then
    `0x9f0a` (the round-9 byte). None of them is there. `0x9f04`-`0x9f0c` are as the arm left
    them (cleared by `hv_s2r_register_wake`), and the alarm register still holds the
    previous run's value.
  - So in all four the last core never reached the hypervisor's commit path. Whether macOS's
    own entry ran to its end (R22, the cores' final writes) is not read.
- **Not like the earlier failed runs.** The runs that reset after a commit (det13, det17,
  det20b, det22c) left `'W'` unconsumed, `0x9f03` = `50` and `0xd000` = `41`. Here `0xd000` is
  `01` in all four, and `0x9f03` is `ff` after both C3 runs and `00` after both C17 runs. (After
  det25's bring-up, rebooted with no sleep, `0x9f03` also read `ff`.) What `0x9f03` and
  `0xd000` record is not established.
- **The fault shadow** `0xa47b`-`d` = `00 08 00` reads the same after every run of this round,
  the alarm wakes included, so it does not tell how these runs ended. What reset the SoC:
  unknown.
- **C3, the timing:** about injection + 144-153 s in both runs.
  - Watchdog 1, armed at the injection with a 150 s bite, falls due then. macOS's own write of
    the watchdog 1 count (at T−0.466 s in every capture, R15) would have restarted that count
    7 s later, so the bite would then have come at about injection + 157 s. The two fall within
    the error of the timing, so whether macOS reached that write is unknown.
  - Camera frames in det29r: the login window at t ≈ 424; the M1's display dark (backlight off)
    from t ≈ 454 to t ≈ 564; the restart at t ≈ 581. The entry turned the display off, and the
    display stayed off until the restart.
- **C17, the timing:** a restart about 5-19 s after the injection, at about the time the commit
  comes in the runs that woke (T is injection + 7.5 s), and well before any armed watchdog
  could bite.
  - Camera frames in det32r: the login window at t ≈ 427, the display dark at t ≈ 437, the USB
    device gone at t ≈ 440, the Omarchy boot screen at t ≈ 457. No other screen in between.
  - Whether macOS panicked, the SoC reset by itself, or the SoC powered down and came up again
    without the hypervisor's wake path is not read.

### Left out, and why

- **C9, C16, C14:** not run. The coordinator stopped the round after det32r ("C3 and C17 on
  Linux are now worth more than the remaining macOS injections"). Their writes are in the
  option and were never run.
- **C4:** the injection did not take (above), so C4 is not tested by this round.
- **C1, C8, C10, C11, C12, C13, C15:** not carried, as open question 68 says.
- **Where C3 and C17 stop:** the RAM log, with the injection records and macOS's accesses after
  them, is lost with each restart. The scratch registers that survive are kept zero by the
  recipe until the commit (macOS reads `0x9f08` in its entry). A later run that injected C3 or
  C17 at the first core's sleep write instead (after macOS's whole entry, like round 8's
  `pg_clear`) would tell an effect through macOS's entry from one at the commit. Such a variant
  was drafted, then not built or run.
- **A same-session control with the option off:** not run. det18 is the control. C2, C6, C4,
  C5 and C7 are controls for the trigger and the watchdog armed at the injection.

### M1 left

In stock Omarchy (kernel 7.3.0-0test5-1-ARCH, up since 21:10:51 after det32r's restart), reached
over Thunderbolt. The camera frame `var/m1-look/20261118-211256-state-now.jpg` shows the desktop.
The claim is released.

## Linux awake (2026-11-18 21:15): the C3 words against the CPU clusters' state

Stock Omarchy (7.3.0-0test5), read over `/dev/mem`. Found: `cpufreq/boost` = 1; both policies on
the `performance` governor at their maximum (E-cluster 2064 MHz, P-cluster 3204 MHz) while idle.

| Setting | `0x23b058000` | `0x23b05c000` | `0x23b060000` | E-cluster cmd `0x210e20020` | P-cluster cmd `0x211e20020` |
|---|---|---|---|---|---|
| (a) as found, idle | `0x444` | `0x666` | `0x333` | `0x105105` | `0x10f10f` |
| (b) max freq = min, boost 0, idle | `0x444` | `0x666` | `0x333` | `0x101101` | `0x101101` |
| (c) max freq, boost 1, cpu0 and cpu4 busy | `0x444` | `0x666` | `0x333` | `0x105105` | `0x10f10f` |
| (d) restored, idle | `0x444` | `0x666` | `0x333` | `0x105105` | `0x10f10f` |

The C3 words do not follow the CPU clusters' state (the clusters went to state 1 and back; the
words stayed). Settings restored afterwards.

## Runs ds20, candidate switches one at a time (2026-11-18 21:17-22:48)

Kernel ds20 (`7cec0b40b`: logic `713a453`, 308/308 from tests `2808844`; glue with
`apple_deepsleep.cand`, 132/132 glue tests at `ecd2ef8`), command line
`var/deepsleep/ds20.cmdline` (`wdt=30`, alarm +60 s, no diagnostics), cable and charger in.
Each run: `tools/tb/m1-cand-runs` (booted once, `cand` set, a real sleep). Results in
`var/commit-walk/ds20-cand.tsv`.

| Switch | Outcome | Record (`0x9f04`) |
|---|---|---|
| C3 (`0x8`) | DARK: no answer, Thunderbolt link still up, screen dark; power button | `44 61 00 ...` ('a': armed only; the commit not reached; no failure recorded) |
| C5 (`0x20`) | DARK: same; power button | `44 54 c0 01 70 3b 02 10 80 00` ('T': a wait timed out, a 32-bit read of `0x23b7001c0` (SIO_BUSIF) by core 0; the M1 then hung instead of returning to Linux) |
| C17 (`0x20000`), C1 (`0x2`), C4 (`0x10`), C8 (`0x100`), C9 (`0x200`), C10 (`0x400`), C13 (`0x2000`), C15 (`0x8000`) | RESET ~62 s after the start: commit reached, watchdog reset | `44 57 00 40 2c 3d 02 30 xx 00` ('W') each |

After every RESET: `0x0201` = `04`, fault shadow `0x000c00`. Not run alone yet: C2, C6, C7, C11,
C12, C14, C16. No switch alone let the SoC power down.

## Safe M1 restart over USB-C: installed and tested (2026-11-18 23:50-23:58)

The proposal `docs/proposals/m1-safe-restart.md` (option (a)): the M3's stock USB-C port-controller
driver (tipd `tps6598x-core`, `sn201202x`), rebuilt from the running kernel's exact source with
only `CONFIG_TYPEC_TPS6598X_DEBUG_COMMANDS=y`, loaded from the M3's boot (`updates/`, UKI rebuilt;
stock image saved in `/boot/efi/safe-restart/`). `tools/m1-reboot/m1-reboot.sh` (3b4f1df) no
longer swaps modules; `tuxvdmtool` runs with `--no-recover` (no unbind or rebind).

- After the M3 reboot: the `command` file on all four ports, the modules from `updates/`, taint
  4100, no oops, the M1's Thunderbolt link back, mains on.
- `nop` (enter and leave the controller's debug mode, no VDM): exit 0; no M3 kernel line; the
  Thunderbolt link stayed up; the M1 answered.
- `reboot` with the M1 healthy (up since 22:47:58): the M1 acknowledged (reply `0x05ac8052`);
  the M3 logged `host disconnected` 23:57:52, two Thunderbolt controller bring-ups, `new host
  found` 23:58:18; the M1 answered at 23:58:23, up since 23:58:05. No oops, no
  `duplicate filename` on the M3.

Not yet tested: a restart of a frozen M1 (the real case).

## Run ds20, all candidate switches but C3 and C5 together (2026-11-19 00:05-00:08)

`cand` = `0x3ffd6` (C1, C2, C4, C6-C17), otherwise as the single-switch runs. Outcome RESET 63 s
after the start: record `44 57 00 40 2c 3d 02 30 a0 00` ('W': commit reached, watchdog armed),
`0x0201` = `04`, fault shadow `0x001c00` (bit 12 set since the USB-C restart test at 23:57). So
with every candidate but C3 and C5 on together, the SoC still stays up after the commit.

## Hypervisor round 10: what lowers the performance-state words (proxy series, det33, det34, det34b, 2026-11-19 00:31-01:04)

Readings only. Taken for the spec's open question 70 (the C3 words `0x23b058000`, `0x23b05c000`,
`0x23b060000`; spec at lab `c8b735c`). Values are written `058000/05c000/060000`. Where a
reading was not taken, the text says "unknown". Nothing here says which agent writes the words:
the readings give an order of events, not a cause.

**Short answer.**
- **Bare m1n1 proxy, no OS, 300 s at 1 s:** the words did not move (`0x444/0x666/0x333` in all 301
  samples), nor did `pmp`'s +`0x44`/+`0x48` (`0x0`/`0x2a`) or the PMP, PMS_SRAM, PMS power-state words.
- **macOS boot, two captures (det33, det34b), the same in both:**
  1. The words read the proxy's values in every sample up to and including the first one after
     macOS's `W 0x23bc00044` = `0x10` (`pmp` started; no sample between t 0.76 and 2.76). In the
     next one, taken after `pmp`'s RTKit
     handshake and endpoint `0x20`'s first exchange, they read **`0x444/0x444/0x444`**
     (det33: t 2.765 -> 3.003 s; det34b: 2.757 -> 3.256 s).
  2. From then until about 69 s they sit at `0x444/0x444/0x444` with one-sample rises of the first
     two (`0x555`, `0x666`): of the samples from t 3.5 to 69 s, 31 of 235 (det33) and 22 of 247
     (det34b) differ from the sample before.
  3. **At 69.5 s (det33) and 69.25 s (det34b) all three change in one sample to
     `0x333/0x444/0x222`.** The last `pmp` mailbox message before that sample, in both, is
     endpoint `0x20` message **`0x0020e00000550000`**, sent 127 ms (det33) and 22 ms (det34b)
     before it. No other endpoint-`0x20` message lies between the sample before and that sample.
     In the same sample `ps_PMP` and `ps_PMS_SRAM` read `0x1000030f` for the first time (before:
     `0x1f0f03ff` / `0x1f0003ff`).
  4. After that the third word stays `0x222` in every sample. The first two rise for single
     samples now and then.
- **macOS idle, entry, sleep and wake (det33, one capture, the detached hypervisor's own clock at
  250 ms):**
  - Idle for 448 s: `0x333/0x444/0x222` with 17 one-sample rises of the first two words (incl.
    `0x80000555` and `0x80000444`: bit 31 set). One endpoint-`0x20` message in the first 447 s
    (`0x0020e00000540000` at t 440.9).
  - The entry: unchanged up to the last sample, 0.16 s before T. This includes macOS's
    `0x0020e00000550001` (T−0.82 s) and `pmp`'s stop (`W 0x23bc00044` = 0 at T−0.43 s). The
    commit snapshot reads the same.
  - **Wake:** the first sample, 1.1 ms after the guest's re-entry, reads `0x333/0x555/0x333`, and
    the second (0.25 s later) the same. macOS restarts `pmp` (`W 0x23bc00044` = `0x10`, 0.354 s
    after the re-entry) and sends endpoint `0x20` messages, among them `0x0020e00000550001`
    (0.459 s) and **`0x0020e00000550000`** (0.469 s); the last before the next sample is
    `0x0020e00000540000` (0.470 s). That next sample (0.50 s after the re-entry) reads **`0x333/0x444/0x222`**, and every sample to the read-out (35.8 s) the
    same.

### The change and the runs

- **Proxy series (`c3idle1`):** `harness/proxy-probe.sh c3idle1 harness/c3_proxy_series.py 300 1`
  (new script, reads only) at a freshly booted installed m1n1 proxy (`v2.0.0-131-gbd6`),
  00:31:54-00:36:54. Each second, 32-bit reads of: the three words; `pmp` +`0x44`, +`0x48`;
  `ps_PMP` `0x23b7003d8`, `ps_PMS_SRAM` `0x23b7003e0`, `ps_PMS` `0x23b700140`; the cluster
  command words `0x210e20020`, `0x211e20020`.
- **Host side** (lab, this commit):
  - `hv_touch_map.py` `S2R_TOUCH_SAMPLE`, unset (off) by default: a list of words read over the
    proxy at each clock tick until full logging starts, with the guest stopped. A word written
    `addr@cond` is read only while the power-state word `cond` has actual state (bits 4-7) `0xf`.
    Record `tsample`.
  - `real_s2r_on(tick_ms=, tick_words=)` sets the hypervisor's detached clock (below).
  - `detached_fmt.py` decodes kind 29 as `tick-sample`, with a test in
    `tests/core/test_hv_detached.py`.
- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commit `5c696a89` on top of
  `52a272cf`, not pushed; build `v2.0.0-146-g5c6`. One option, `hv_det_tick_ms`, 0 (off) by
  default:
  - While detached, on the hypervisor's own 1 kHz tick (core 0, under the hypervisor lock), it
    reads the up-to-16 words of `hv_det_tick_addr[]` every N ms. Each read is 32-bit and guarded,
    and has the same optional power-state condition. Each word is logged as kind 29, with the
    sample number.
  - The tick does not run while core 0 is down, so there is no sampling during the sleep.
- **Sampled words** (both clocks): the three words; `pmp` +`0x44` and +`0x48`, each conditioned on
  `ps_PMP`; `ps_PMP`, `ps_PMS_SRAM`, `ps_PMS`, `ps_DCS0` (`0x23b700300`).
- **Recipe:** det18's, with these changes:
  - `S2R_TOUCH_TICK=250` (the touch map's clock at 250 ms instead of 1 s);
  - `S2R_TOUCH_FULL=0x23bc00000+0x4000,0x23bc08000+0x4000,0x210e20000+0x4000,0x211e20000+0x4000`:
    `pmp`'s control page, its mailbox page and both CPU clusters' pages logged in full from the
    instrument's start (the rest of device space as the 5 s touch map);
  - `FULL=0`, so the boot clock kept sampling past the login window;
  - the switch to full logging was made by hand once the camera showed the login window.

  In full:
  - `WD1=150 ALARM=90 FULL=0 S2R_TOUCH_TICK=250 S2R_TOUCH_SAMPLE=... S2R_TOUCH_FULL=...
    S2R_ARGS='core_state=1, c4_probe=1, tick_ms=250, tick_words=[...]' harness/macos-up.sh detNN`;
  - then (det33 only) `full <det8's four pages>` into the control file;
  - `PRE=<awake_snap of commit-snap-list-r7.json> ARGS='commit_snap=<that list>'
    harness/detach135.sh det33`;
  - `harness/detached-wake-readout.sh det33 35` (read-out 35 s after the wake, not 20);
  - `harness/hv-reboot.sh`, `tools/tb/m1-pmu-dump`.

  The M1 was claimed as `observation` throughout and released at the end.
- **The no-hands way out, named before det33:** the hypervisor's alarm at commit + 90 s; watchdog
  1 at commit + 150 s. For a hang before the commit, the hypervisor's own proxy stays reachable
  over USB, so `detach_readout.py --reboot` would end the run. The boot captures needed none,
  because the host stayed attached. Every run ended without hands; the USB-C restart was not
  used.
- **Files (private):**
  - `tools/hv-trace-kit/runs/20261119-proxy/c3idle1.out`;
  - `tools/hv-trace-kit/runs/20261116-mac135/*-det33.*`, `*-det34.*`, `*-det34b.*`
    (`touch-*.jsonl`, `detached-det33.jsonl`, `run-*.out`, `vuart-*.log`);
  - the scripts `var/commit-state/r10_c3_series.py`, `r10_pmp_msgs.py`, `r10_window.py`, and
    their outputs:
    - `r10-det33-boot.txt`, `r10-det34b-boot.txt` (every change of a sampled word);
    - `r10-det33-pmp-boot.txt`, `r10-det34b-pmp-boot.txt`, `r10-det33-pmp-detached.txt`
      (`pmp` traffic merged with the samples);
    - `r10-det33-detached.txt`, `r10-det33-wake-window.txt`;
  - `var/m1-state/pmu-20261119-005236-after-det33.txt`, `pmu-20261119-010450-after-det34b.txt`;
  - camera frames `var/m1-look/20261119-0*`.

| Run | What | Outcome |
|---|---|---|
| c3idle1 | proxy, no OS, 300 s at 1 s | no word moved |
| det33 | boot sampled 0-207.8 s (788 samples), login window on the camera at 00:41:19 (t ≈ 203 s); detach 00:41:31; idle, entry, sleep, wake sampled by the detached clock (1931 samples) | T = 448.277 s after the detach; **asleep 89.87 s, woke at the alarm**, wake status `0 / 0x400000 / 0`; USB device left/back 00:50:28.469 / 00:50:29.183; read out at wake + 35.8 s: 1,239,407 records, 0 dropped; commit snapshot 1328 words, 0 errors |
| det34 | boot | **macOS did not boot:** after the arm (00:53:52, CNTPCT 54 s) the run logged 16 trapped system-register accesses (det33: 304), no device access and no console output for 180 s; the camera showed m1n1's logo. Cause not read. Rebooted with `hv-reboot.sh` |
| det34b | boot (det34 repeated) | boot sampled 0-395.3 s (1534 samples), READY 01:00:39; no sleep: rebooted with `hv-reboot.sh` (run_guest's exit 01:04:22) |

Power chip after det33 (alarm wake, then `hv-reboot.sh`):
- `0x0201` `00`, `0x9f03` `00`;
- `0x9f04`-`0x9f0c` `48 00 01 3f ff ff 47 50 00`;
- `0xa47b`-`d` `00 08 00`, `0xd000` `01`, `0xd00c` `00`.

These are det18's values. After det34b (rebooted without a sleep): `0x9f03` `ff`, `0x9f04`-`0x9f0c` all
`00`, the rest the same (as after det25's bring-up).

### 1. Bare proxy, no OS (`c3idle1`)

301 samples, 0 changes. Every sample:
- the words `0x444/0x666/0x333`;
- `pmp` +`0x44` `0x0`, +`0x48` `0x2a`;
- `ps_PMP`, `ps_PMS_SRAM`, `ps_PMS` `0xf0000ff`;
- cluster commands: E `0x100105`, P `0x100101`.

### 2. macOS boot (det33, det34b)

Times "t" are seconds from the touch map's start, on the M3's clock at receipt (the tick samples
are taken with the guest stopped; device accesses are timed by the USB link's buffering). The
CPU clusters' pages, `pmp`'s control page and mailbox are logged in full. Other pages show only
their first access per 5 s epoch, so "no access" to them between two samples is **not**
established.

| Step | det33 | det34b |
|---|---|---|
| first sample (hypervisor running, guest not yet at `pmp`) | t 0.255: `0x444/0x666/0x333`, `pmp` +`0x44` 0, +`0x48` `0x2a` | t 0.255: the same |
| CPU clusters | macOS writes their command words only at t 1.09-1.12: each `0x40002101101`, then `0x40000101101` twice; also `+0x400`-`+0x4f8` and `+0x580`-`+0x648` = 0, `+0x660`, `+0x0f8`. No cluster write after that in the capture. Its first reads of the E cluster include `+0x6a8` = `0x4444443333222110` and `+0x6e0` = `0x6666665555444333`; the P cluster `+0x6a8`/`+0x6b0`/`+0x6e0`/`+0x6e8` are read too | the same writes at t 1.04-1.06 (the same values) |
| `pmp` started | t 2.6748 `R 0x23bc00044` = 0, `W` = `0x10` (core 2) | t 2.6018 (core 3) |
| sample after the start | n 4, t 2.765: words unchanged; +`0x44` `0x10` | n 4, t 2.757: the same |
| between it and the next sample | RTKit management exchange on endpoint 0 (t 2.675-2.694), endpoints 1-3. Endpoint `0x20`: `RECV 0x0`, `SEND 0x000100000003c000` (t 2.70); then at t 2.975-2.981 `RECV 0x000200000023b549`, `SEND 0x0020000000010003`, `RECV 0x0020100000010003`, `SEND 0x0020200000010000`, `RECV 0x0020300000010000` | endpoint `0x20`: the same five at t 3.212-3.228, then `SEND 0x0020e000005c0000/…0001/…0000`, `0x0020c00000640021` (`RECV …d…`), `SEND 0x0020a00000640020` (t 3.243) |
| **first change** | **n 5, t 3.003: `0x444/0x444/0x444`** (058000 unchanged; 05c000 `0x666`->`0x444`; 060000 `0x333`->`0x444`); `ps_PMP` `0x1f0f03ff`, `ps_PMS` `0x1f0002ff` | **n 5, t 3.256: the same** |
| t 3.5-69 | 31 of 235 samples differ from the one before: 05c000 `0x444`<->`0x555` (also `0x666`), 058000 now and then `0x555` (first at n 97, t 28.5); 060000 `0x444` throughout | 22 of 247; the same pattern (058000 first `0x555` at t 25.8) |
| endpoint `0x20` from t 5.4 / 4.5 s | single `0x0020e…` messages (ids `0x63`-`0x68`, `0x5c`) up to t 50.1, none t 50.1-69.38 | a burst of 30 `0x00204…`/`0x00205…` pairs at t 24.98-25.01; `0x0020e00000660000` at t 49.16; none t 49.16-69.23 |
| sample before the second change | n 243, t 69.255: `0x444/0x444/0x444` | n 253, t 69.006: the same |
| between them (all logged accesses and first touches) | t 69.334-69.347 first touches of `0x23b2e0c00`, `0x211ef1600`, `0x211000000`, `0x211ef4600`; **`dcpext`** (`0x271c00000`, ADT `/arm-io/dcpext`) `R 0x271c08110` = `0x29901`, `R 0x271c00048` = `0x2e`; `R 0x27130c040` = `0x6000400`; **`pmp` `SEND` endpoint `0x20` `0x0020e00000550000` (t 69.3808, core 0)**; `R 0x23b700368` (DISPEXT_FE's power-state word) = `0x23ff`; `R 0x27200c000` = 0; `W 0x272008014` = 1; first touches of `0x211ee9000`, `0x211eec000`, `0x23b2a1000`, `0x23b2a4000`, `0x210ee1000`, `0x210000000`, `0x210ee4000`, `0x23b281200`, `0x23b284200`, `0x211ee1400`, `0x211ee4400`, `0x23b299200`, `0x23b29c200` (t 69.40-69.49); the clusters' pages read only (`+0x20` `0x40000101101`, `+0x588` 0) | first touches `0x211ee9000`, `0x211eec000`; `dcpext` `R 0x271c08110` = `0x29901`, `R 0x271c00048` = `0x2e`; `R 0x27130c040` = `0x6000400`; **`SEND` `0x0020e00000550000` (t 69.2321, core 0)**; `R 0x23b700368` = `0x23ff`; `R 0x27200c000` = 0; `W 0x272008014` = 1; the clusters' pages read only |
| **second change** | **n 244, t 69.508: `0x333/0x444/0x222`**; same sample: `ps_PMP` `0x1000030f`, `ps_PMS_SRAM` `0x1000030f` (first time), `ps_DCS0` `0x1000030f`, `pmp` +`0x44`/+`0x48` not read (condition) | **n 254, t 69.254: the same**, with the same power-state readings |
| afterwards | 060000 `0x222` in every sample; 543 samples t 70-209.4, one not at `0x333/0x444/0x222` (05c000 `0x555`, t 107.0); `ps_PMP` alternates between `0x1f0f03ff` and `0x1000030f` (`pmp` +`0x44` `0x10` whenever read) | 1278 samples t 70-395, 14 one-sample rises of the first two words; 060000 `0x222` throughout |

Endpoint `0x20` messages with id `0x55` in the boot captures: `SEND 0x0020a00000550023` /
`RECV 0x0020b00000550023` at t 3.55 (det33) and 3.64 (det34b), and `SEND 0x0020e00000550000` at
the second change. No `0x0020e…550001` in either boot.

*Documentation, not an observation:* in the ADT's power-manager table
(`var/map-20261117/adt/pmgr-devices.json`), device id `0x55` is DISPEXT_FE (power-state word
`0x23b700368`, flag `notify_pmp`), id `0x54` DISP0_FE. The other ids seen in `0x0020e…`
messages are also devices with `notify_pmp`: `0x5c` JPG, `0x63` GFX, `0x64` ISP_SYS,
`0x65` VENC_SYS, `0x66` AVD_SYS, `0x68` ANE_SYS. That the message's id field is this device id
is not established; it is a match of numbers.

### 3. macOS idle, entry, sleep and wake (det33, detached clock)

Times are seconds from the detach marker (the M1's timer). Every access in the log is complete
(full logging) except det8's four skipped pages.

- **Idle, t 0-447:**
  - 1784 samples. 17 have a rise of the first two words for one sample: 05c000 `0x555`, `0x666`,
    `0x80000555`, `0x80000444`; 058000 `0x444`, `0x555`. 060000 is `0x222` in every sample.
  - Endpoint `0x20`: one message, `SEND 0x0020e00000540000` at t 440.92. There are 10
    endpoint-4 messages in the whole log.
  - `ps_PMP` alternates between `0x1f0f03ff` and `0x1000030f`.
- **Entry:**
  - Endpoint `0x20`: `SEND 0x0020e00000550001` at t 447.4617 and `0x0020e00000540001` at 447.4645,
    then `SEND 0x0020800000630000` / `RECV 0x0020900000630000` at 447.468. In the samples after
    them (n 1786, 447.616 on), the words are unchanged.
  - Endpoint 0 management (`0x00b0000000000201`, `0x0060000000000201` / `0x0070000000000201`) at
    447.846.
  - `R 0x23bc00048` = `0x2e`, `R 0x23bc00044` = `0x10`, `W 0x23bc00044` = 0 at 447.8461.
  - Samples n 1787 (447.866) and n 1788 (448.117): `0x333/0x444/0x222`, `pmp` +`0x44` 0, +`0x48`
    `0x2e`, `ps_PMP` `0x1f0f03ff`.
  - T (last core) 448.2775. The commit snapshot (448.2775-448.2796) has `0x333/0x444/0x222`,
    `ps_PMP` `0x1f0f03ff`.
- **Sleep:** no samples (core 0 down); the gap between samples is 90.03 s.
- **Wake:**

  | t | Reading or access |
  |---|---|
  | 538.1498 | wake entry; the wake snapshot reads `0x333/0x555/0x333`, `ps_PMP` `0xf0003ff` |
  | 538.1501 | re-entry of the guest |
  | 538.1512 (n 1789) | `0x333/0x555/0x333`; `pmp` +`0x44` 0, +`0x48` `0x2a`; `ps_PMP` `0xf0003ff`, `ps_PMS_SRAM` `0xf000300`, `ps_PMS` `0xf0002ff` |
  | 538.159-538.161 | macOS's 89 reads of `0x23b058068`/`080`/`098` (as R70) |
  | 538.1789 | `0x23b050000`: R `0x80000000`, W 0, W `0x80000000`; `0x23b054000` the same. Neither page is the three words' |
  | 538.4016 (n 1790) | `0x333/0x555/0x333`; `ps_PMP` `0x1f0003ff` |
  | 538.4016-538.5046 | 24,576 writes over `0x23b544000`-`0x23b55bfff` (and the rest of that range before 538.40, not counted here); the `0x23b300000` page at 538.5046 |
  | 538.5047 | `W 0x23bc00044` = `0x10` (`pmp` started) |
  | 538.5048-538.5054 | endpoint 0 handshake |
  | 538.5957 | endpoint `0x20` `SEND 0x0020e00000630001` |
  | 538.6087 | `SEND 0x0020e00000550001` |
  | 538.6107 | `SEND 0x0020e00000540001` |
  | 538.6187 | **`SEND 0x0020e00000550000`** |
  | 538.6198 | `SEND 0x0020e00000540000` |
  | 538.6517 (n 1791) | **`0x333/0x444/0x222`**; `pmp` +`0x44` `0x10`, +`0x48` `0x2c`, `ps_PMP` `0x1f0f03ff` |
  | to 573.755 (n 1931) | `0x333/0x444/0x222` in every sample; read-out at 573.978 |

  The other pages accessed in the window 538.40-538.65 are listed in `r10-det33-wake-window.txt`
  (among them `dcp` and `dcpext` mailboxes, `0x27200c000`/`0x272008000`, `0x23200c000`/
  `0x232008000`, the SMC mailbox, the power manager's power-state page).
  No access to `0x23b058000`, `0x23b05c000` or `0x23b060000` anywhere in the detached log (R70
  holds in this capture).

### Left out, and why

- **Which agent writes the words:** not read. The readings give the order of events only. In both
  boots and the one wake, the first sample at the awake values follows `pmp`'s start and an
  endpoint-`0x20` message `0x0020e00000550000`. At the boot it also coincides with the first
  `0x1000030f` reading of `ps_PMP` and `ps_PMS_SRAM`. Separating "`pmp` acts on that message" from
  "something else in the same 22-250 ms" would need a finer clock, or that message withheld or
  delayed (an [HV-CHANGED] run, not done).
- **The first change at t ≈ 3 s:** the 0.24-0.50 s between the two samples holds `pmp`'s start,
  RTKit's handshake and endpoint `0x20`'s first exchanges (plus other blocks' first touches). Which
  one comes first in time is not resolved by these samples.
- **Pages other than `pmp`'s two and the clusters' during the boot:** first touch per 5 s epoch
  only (the touch map). A boot with everything logged in full was not run.
- **Wake series:** one capture (det33); 35.8 s of samples after the wake. A second sleep and wake
  was not run.
- **Boot clock side effects:** the 250 ms clock stops the guest about 4 times a second. det34's
  boot stalled before macOS ran (cause not read); det33 and det34b booted. The detached clock's
  reads by core 0 every 250 ms ran through det33's idle and entry, and the sleep and wake came as
  in det18 (asleep 89.87 s, the same wake status).
- **`pmp` +`0x44`/+`0x48` while `ps_PMP` read other than actual state `0xf`:** not read (the
  condition). These are the `off` entries in the files.

### M1 left

In stock Omarchy (kernel 7.3.0-0test5-1-ARCH, up since 2026-11-19 01:04:29), reached over
Thunderbolt. The camera frame `var/m1-look/20261119-010452-state-after-round10.jpg` shows the
desktop. The claim is released.

## Linux round: pmp and the endpoint-0x20 message (2026-11-19 01:10-01:15)

Readings only, on bare metal: stock Omarchy, kernel `7.3.0-0test5-1-ARCH` (package `linux-aurora
7.3.0.aurora0test5-1`, built 2026-11-14), up since 01:04:29, awake, nothing suspended. The camera
frame `var/m1-look/20261119-011007-state-linuxobs-start.jpg` shows the Omarchy desktop. The M1 was
claimed as `linux-obs` and driven over Thunderbolt. Registers were read over `/dev/mem`, 32-bit,
read-only. `pmp`'s mailbox FIFOs were not read (a read of a receive FIFO takes a message); only
its two control words were. No message was sent to `pmp` (see 4).

**Short answer.** On this kernel nothing in Linux reaches `pmp`. The M1's device tree has no
node for `pmp`, its mailbox or its DART. The `apple_pmp` module is loaded, but it has no `t8103`
compatible and no device bound. `pmp`'s CPU control word reads `0x0`, both mailbox directions read
empty, and the three words read `0x444/0x666/0x333`, unchanged over 60 s.

### 1. Is pmp running under Linux?

- **Device tree (live, `/sys/firmware/devicetree/base`):**
  - Root compatible `apple,j313 apple,t8103 apple,arm-platform`.
  - No node at `0x23bc00000` (`pmp`), `0x23bc08000` (its mailbox) or `0x23b300000` (its DART).
    No node name and no `compatible` contains `pmp`, and no property is named `apple,pmp*`. The
    `soc` node's only mailboxes are `mailbox@381100000` and `mailbox@501100000`.
  - The power-manager children `power-controller@3d8` (label `pmp`) and `power-controller@3e0` are
    present.
- **Drivers:**
  - `apple_pmp` (`/lib/modules/7.3.0-0test5-1-ARCH/kernel/drivers/soc/apple/apple-pmp.ko`,
    BuildID `09e1db6a6b62…`; source paths in it `/src/linux-aurora/src/linux-test73/drivers/soc/
    apple/pmp.rs`) is loaded, used by `appledrm` and `aurora`.
  - Its aliases are only `apple,t8132-pmp-v2`, `t8140`, `t8142`, `t6041`, `t6050`, `t6000`. Its
    strings also contain `apple,t6030-pmp-v2` and `/soc/pmp@380500000`.
  - `/sys/bus/platform/drivers/apple_pmp/` has no device link. Neither does
    `apple-pmp-report` nor `apple-pmp-report-entry` (built in as `pmp_report`). No platform device
    is bound to any driver whose name contains `pmp` or `rtkit` (only the driver `rtkit-helper` is
    listed).
  - `dmesg` has no line containing `pmp`. `/sys/kernel/debug/apple-pmp-report/` is empty.
- **Power domains** (`/sys/kernel/debug/pm_genpd/pm_genpd_summary`): `pmp` on, `pms` on, `pms_busif`
  on, `pms_sram` `off-0`, `pms_fpwm0`-`4` `off-0`.
- **Words (01:10:54):**

  | Word | Value |
  |---|---|
  | `pmp` +`0x44` (`0x23bc00044`, CPU control) | `0x0` |
  | `pmp` +`0x48` | `0x2a` |
  | mailbox A2I control `0x23bc08110` | `0x20001` |
  | mailbox I2A control `0x23bc08114` | `0x20001` |
  | `ps_PMP` `0x23b7003d8` | `0x1f0000ff` |
  | `ps_PMS_SRAM` `0x23b7003e0` | `0x0f000300` |
  | `ps_PMS` `0x23b700140` | `0x1f0000ff` |
  | `ps_DCS0` `0x23b700300` | `0x1f0002ff` |
  | E-cluster cmd `0x210e20020` / P-cluster cmd `0x211e20020` | `0x105105` / `0x10f10f` |

  *Documentation, not an observation* (aurora-silicon/linux `integration/aurora` `1f38ff8f4`,
  `drivers/soc/apple/mailbox.c`): bit 17 of a control word is EMPTY, bit 16 FULL, bit 0
  RECV_ENABLE; offset `0x44` of the coprocessor's page is its CPU control, and its "run" bit is
  what `pmp.rs` sets to start it.
  - `pmp` +`0x44`/+`0x48` read as in round 10's bare proxy (`0x0`/`0x2a`). They do not read as in
    macOS after it starts `pmp` (+`0x44` `0x10`).
- **Endpoints started:** no RTKit instance exists for `pmp` in this kernel, so there is nothing to
  read them from. With +`0x44` at `0x0`, no endpoint list was read from `pmp` itself.

### 2. The three words under Linux

- **01:10:54:** `0x23b058000` = `0x444`, `0x23b05c000` = `0x666`, `0x23b060000` = `0x333`.
- **01:13:24-01:14:24:** 60 samples at 1 s of the three words, `pmp` +`0x44`/+`0x48`, both mailbox
  control words, `ps_PMP`, `ps_PMS_SRAM`, `ps_PMS` and `ps_DCS0`. **0 changes**: every sample is the
  01:10:54 reading.
- File (private): `var/commit-state/linux-pmp-series-20261119.txt`.

### 3. Does Linux send endpoint-0x20 messages to pmp?

**The running kernel.** These come from the M1's module and DT (above), not from source:
- no `pmp` device and no mailbox device for `0x23bc08000` exist;
- `apple_pmp` matches no `t8103` compatible.

A kernel RTKit or mailbox client therefore has nothing to bind to. The hardware readings agree:
`pmp`'s CPU control is `0x0`, and both mailbox directions read EMPTY. No endpoint-`0x20` traffic
was observed, and none has a path in this kernel.

**Reference source.** This is aurora-silicon/linux `integration/aurora` at `1f38ff8f4`, read as
data. It is not the M1's exact tree: the M1's module was built from `linux-test73`. Its compatible
list matches the M1 module's aliases.
- `arch/arm64/boot/dts/apple/t8103-peripherals.dtsi`:
  - `pmp: coprocessor@23bc00000` (`"apple,t8103-pmp", "apple,pmp"`; power domains `ps_pmp`,
    `ps_pms_sram`; `iommus = <&pmp_dart 0>`);
  - `pmp_mailbox@23bc08000` (`apple,t8103-asc-mailbox`, `apple,asc-mailbox-v4`);
  - `pmp_dart` `iommu@23b300000`.

  All three are `status = "disabled"`. No driver in that tree matches `apple,t8103-pmp` or
  `apple,pmp`.
- `drivers/soc/apple/pmp.rs`:
  - `PMP_ENDPOINT = 0x20`. Messages sent on it:
    - replies to the firmware's requests, `(opcode | 1) << 48` with opcodes `0x10` (IOVA table),
      `0x12` (malloc), `0x14` (free), `0x30` (set buffer), `0x32`/`0x34`/`0x36` (ioreg);
    - for `0x36`, the reply `0x37 << 48`;
    - power commands (`apple_pmp_send_power_command`): `(1 << 53) | (command << 44) |
      (device_id << 40) | (enabled << 32)`.
  - The reply awaited for a power command is `(1 << 53) | ((command + 1) << 44)` (`pmp_power.rs`).
- `drivers/soc/apple/pmp-export.c` `apple_pmp_set_device_power`: refuses any command other than
  `0x0e`/`0x0f`, any `device_id > 15` and any `enabled > 1`.
  - Its one caller in that tree is `drivers/gpu/drm/apple/iomfb_v26_6.c` `keep_display_power`,
    for J613 only: `(0x0f, 8, 1)`.
- macOS's message `0x0020e00000550000` has bit 53 set, `0xe` in bits 44-47, `0x55` in bits 16-23
  and `0` in bits 0-15. In the reference format, `device_id` goes at bit 40 and `enabled` at bit
  32, and `device_id` is limited to 0-15. The reference function therefore cannot produce this
  word.

### 4. The message itself: not sent

**No safe path exists on this kernel.**
- There is no existing interface: no `pmp` device, no RTKit instance, no mailbox device.
- No kernel driver owns `0x23bc08000`, but with `pmp`'s CPU stopped (+`0x44` `0x0`) a word put
  into its mailbox reaches no endpoint.
- To reach endpoint `0x20`, `pmp`'s firmware would first have to be started, and that has not
  been done under Linux on this machine.

**What a test path would need**, from what is present on the M1 and from round 10's macOS
captures:
- **Kernel support, present:**
  - `CONFIG_OF_OVERLAY=y`, `CONFIG_APPLE_MAILBOX=y`, `CONFIG_APPLE_RTKIT=y`, `CONFIG_APPLE_DART=y`;
  - `of_overlay_fdt_apply`, `apple_mbox_get`, `apple_rtkit_init`, `apple_rtkit_wake`,
    `apple_rtkit_start_ep` and `apple_rtkit_send_message` exported (`Module.symvers`);
  - the headers at `/lib/modules/7.3.0-0test5-1-ARCH/build`;
  - modules are signed, but `CONFIG_MODULE_SIG_FORCE` is not set.
- **Device-tree nodes, by overlay:** nodes for the mailbox (`0x23bc08000`, AIC 511-514), the DART
  (`0x23b300000`, AIC 515) and a test device holding `mboxes`, `iommus` and the `ps_pmp` and
  `ps_pms_sram` power domains. `ps_pms_sram` reads `off-0` now; in macOS it reads `0x1000030f`
  from the second change onward.
- **A test module** that starts `pmp`'s CPU (+`0x44` run bit) and completes RTKit's boot with the
  buffer requests macOS answered at boot (`r10-det33-pmp-boot.txt`, t 2.675-2.70):
  - endpoint 0 handshake;
  - endpoints 1, 2 and 3 with buffer replies (`0x0010400000018000`, `0x0010100000034000`, ep 3
    `0x0001000000004000`/`0x0002000000010000`);
  - start of endpoint `0x20`;
  - then endpoint `0x20`'s own opening: `RECV 0x0`, macOS `SEND 0x000100000003c000`,
    `RECV 0x000200000023b549`, `SEND 0x0020000000010003` / `RECV 0x0020100000010003`,
    `SEND 0x0020200000010000` / `RECV 0x0020300000010000`.

  Only then the messages wanted: `0x0020e00000550001`, then `0x0020e00000550000`, reading the words
  before and after.
  - The meaning of these opening words, and whether `pmp`'s SRAM needs anything written before the
    start, are not read. The reference driver's opening (`(0x10|1) << 48` for the IOVA table)
    differs from macOS's `0x0001…` above.
- **Why it was not run:** the brief excludes crash-prone steps with the Thunderbolt cable in.
  Starting a power-management coprocessor whose start-up has never run under Linux here, with an
  untested DART and buffer setup, is such a step. Whether it would crash is unknown.

### Left out

- The test module and overlay (section 4): not written, not built, not loaded.
- The M1's exact source tree (`linux-test73`): not on the M3. The running kernel was read from its
  module, its DT, its config and `Module.symvers`. The protocol was read from the reference tree.
- `pmp`'s SRAM, its other register pages, and what macOS writes to them before starting `pmp`: not
  read.
- The mailbox FIFOs: not read.

### M1 left

In stock Omarchy (kernel `7.3.0-0test5-1-ARCH`, up since 01:04:29, not rebooted in this round),
reached over Thunderbolt. No module was loaded, and the two reader scripts copied to `/root` were
removed. The camera frame `var/m1-look/20261119-011527-state-linuxobs-end.jpg` shows the desktop. The
claim is released.

## macOS's pmp start-up and endpoint-0x20 exchange (from round-10 captures)

Readings only, from captures already on the M3. No M1 run was made and the M1 was not claimed.
Sources:
- round 10's det33 and det34b boots (`touch-det33.jsonl`, `touch-det34b.jsonl`);
- det33's detached log (idle, entry, wake);
- for what those do not log in full, two earlier macOS boots:
  - det10 (2026-11-17 18:27): `pmp`'s DART page logged in full from boot;
  - `135map4` (2026-11-17 02:30, `docs/evidence/2026-11-16-dram-controller-state`): `0x23b500000`+`0x40000`
    logged in full from boot;
- det18 and det23's detached logs, to compare the entry and the wake.

Boot times "t" are seconds from the touch map's start, on the M3's clock at receipt. Detached
times are the M1's timer from the detach. Field names come from aurora-silicon/linux
`integration/aurora` `1f38ff8f4` (`drivers/soc/apple/rtkit.c`, `mailbox.c`, `pmp.rs`,
`pmp_bootargs.rs`, `drivers/iommu/apple-dart.c`, `drivers/pmdomain/apple/pmgr-pwrstate.c`) and
Asahi's `hw/soc/asc.md`. They are names for fields, not readings of what the firmware does with
them. Where a field's meaning is only inferred from the values, it is marked *(guess)*.

**Short answer.**
- **The same in every boot read (det33, det34b, det10, `135map4`):**
  1. macOS reads `pmp`'s SRAM header and its boot-argument block. In `135map4` it writes the block
     back with the values it read.
  2. It sets up `pmp`'s DART (det10).
  3. It writes `0x20001` to the I2A control word, then `0x10` to `+0x44`.
  4. RTKit's handshake follows: version 12, endpoints `0x00`-`0x04` and `0x20`, and buffers for
     endpoints 1-4 at IOVAs `0x18000`, `0x34000`, `0x4000`/`0x10000` and `0x20000`.
  5. Endpoint `0x20` opens with `RECV 0x0` and `SEND 0x000100000003c000`.
  6. `pmp` then sends `0x000200000023b549` (0.27 s and 0.59 s later). macOS at once reads byte
     `0x23b549400` of `pmp`'s SRAM; that page holds the names `BAT`, `DRAM`, `ECPU`, `PCPU`,
     `ECORE0`…
  7. Two request/reply pairs follow (`0x0020000000010003`/`…1…0003`,
     `0x0020200000010000`/`…3…0000`).
  8. Then the endpoint-`0x20` traffic: the `0x0020e…` messages, request/reply pairs with codes
     8/9, a/b, c/d and 4/5, and the `0x0020e00000550000` at 69 s.

  Through the end of endpoint `0x20`'s opening, det33 and det34b have the same messages, word for
  word and in the same order. After that they have the same kinds of message, with small
  differences in count and order (section 3).
- **What macOS writes to `pmp`'s memory before starting it:** only the 0x2d0-byte boot-argument
  block at SRAM `+0x3a800` (54 tagged records, decoded below). In `135map4` it was written back
  unchanged. Nothing else in `0x23b500000`-`0x23b53ffff` is written before the start. The rest of
  the SRAM (`0x23b540000` on) was not logged in full in any boot.
- **At the entry (det33; det18 and det23 the same):**
  1. Endpoint-`0x20` messages for ids `0x55`/`0x54`, both `…0001` and `…0000`, and `0x63`
     (8/9).
  2. `SET_AP_PWR_STATE` and `SET_IOP_PWR_STATE` `0x201`.
  3. I2A control `0x22200`; `+0x44` = 0.
  4. The DART's streams are disabled.
  5. macOS reads the whole `__DATA` segment of `pmp`'s SRAM (`0x23b52c000`-`0x23b55bfff`,
     49,152 words) and 12 64-bit words at `0x23b549000`-`0x2a0`.
- **At the wake (det33; det18 and det23 the same):**
  1. macOS writes the power-state words of `PMP`, `PMS_SRAM` and `PMS`.
  2. It writes the same 12 64-bit words, then all of `__DATA` back. In det33 every byte equals what
     it read at the entry.
  3. It sets up the DART again (new TTBR), writes I2A control `0x20001` and `+0x44` = `0x10`.
  4. The handshake is short: no endpoint is started, no buffer is requested, and endpoint `0x20`'s
     opening is not repeated.
  5. Endpoint-`0x20` messages follow 91 ms later: `…630001`, `…550001`, `…540001`, **`…550000`**,
     `…540000`.

### Coverage

| Block | det33/det34b boot | det33 detached (idle, entry, wake) | det10 boot | `135map4` boot |
|---|---|---|---|---|
| `pmp` control page `0x23bc00000` (`+0x44`, `+0x48`) | full | full | first touch per 5 s | first touch per 5 s |
| `pmp` mailbox page `0x23bc08000` | full | full | first touch per 5 s | first touch per 5 s |
| `pmp` SRAM `0x23b500000`+`0x80000` (ADT `/arm-io/pmp` reg 2) | first touch per 5 s | full | first touch per 5 s | **full for `+0`-`+0x3ffff`** |
| DART `0x23b300000` (ADT `/arm-io/dart-pmp`) | first touch per 5 s | full | **full** | first touch per 5 s |
| power-state words `0x23b7003d8` (PMP), `0x3e0` (PMS_SRAM), `0x140` (PMS) | first touch of their page per 5 s; tick samples every 250 ms | full; tick samples every 250 ms | first touch | first touch |
| `pmp` reg 1 `0x23b850000`+`0x200000`, other `pmp` pages in `0x23bc00000`+`0x60000` | first touch per 5 s | full | first touch | first touch |

- "First touch per 5 s" shows only the first access to each 16 KiB page in each 5 s epoch. A page
  is re-armed only after it is touched, so a page with no touch after its first epoch had no
  access at all.
- In the boot captures, full-logged pages arrive through the hypervisor's asynchronous log;
  first touches are synchronous traps. Their relative order is by receipt time only.
- In the detached log every record has the M1's timer, and the order is exact.
- `0x23bc34000` lies in `pmp`'s ADT range and in the power manager's (`/arm-io/pmgr` reg 22,
  `0x23bc2c000`+`0x40000`). It is written `0x1`/`0x2` from 1.3 s on, from the same pc as the
  power-state words (det33 `0xfffffe0015fba2d0`), and is one of det8's four pages left out of
  full logging. It is not counted as `pmp`'s here.
- `pmp` reg 1 and the other `0x23bc…` pages: no access in any of these captures.

*ADT (`var/map-20261117/adt/adt.bin`), not an observation of traffic:*
- `/arm-io/pmp`: `iop,ascwrap-v4`, role `PMP`, interrupts 512, 511, 514, 513.
- `iop-pmp-nub`: firmware `t8103pmp`, `pre-loaded` 1, `region-base` `0x23b500000`, `region-size`
  `0x80000`, `sram-index` 1.
- `segment-ranges`: `__TEXT` phys `0x23b500000` (IOVA `0x100000000`, `0x2c000` bytes) and
  `__DATA` phys `0x23b52c000` (IOVA `0x10002c000`, `0x30000` bytes).
- `/arm-io/dart-pmp`: `dart,t8020`; `sids` `0x8001`, `bypass` `0x8000`; tunables (offset,
  value) `+0x60` `0x80006100`, `+0x68` `0x0f0f0f`, `+0x6c` `0x080808`.

### 1. Boot: every logged access to pmp, its SRAM, its DART and its power-state words, to the start

| Step | det33 t | det34b t | Access (value) |
|---|---|---|---|
| sample n 3 | 0.755 | 0.755 | `+0x44` 0, `+0x48` `0x2a`; ps_PMP, ps_PMS_SRAM, ps_PMS `0x0f0000ff` (as the bare proxy). No sample until n 4 |
| SRAM header | 2.6593 | 2.5893 | first touch `R 0x23b500020` = 0 |
| boot-argument page | 2.6620 | 2.5916 | first touch `R 0x23b53a800` = `0x53544b47` (`STKG`) |
| `__TEXT` string | 2.6652 | 2.5942 | first touch `R 0x23b52a384` = `0x694b5452` (`RTKi`) |
| `__DATA` string | 2.6682 | 2.5967 | first touch `R 0x23b52f3a8` = `0x20746f6e` (`not `) |
| DART | 2.6714 | 2.5997 | first touch `R 0x23b300000` (PARAMS1) = `0x0ed01020` |
| I2A control | 2.6736-2.6744 | 2.6015 | `R 0x23bc08114` = `0x20001`, `W` = `0x20001` |
| **CPU start** | 2.6747-2.6748 | 2.6017-2.6018 | `R 0x23bc00044` = 0, **`W 0x23bc00044` = `0x10`** |
| RTKit handshake | 2.6750-2.7004 | 2.6029-2.6228 | section 2 |
| sample n 4 | 2.7646 | 2.7568 | `+0x44` `0x10`, `+0x48` `0x0c` / `0x2c`; ps_PMP `0x1f0f00ff`, ps_PMS_SRAM `0x1f0000ff`, ps_PMS `0x1f0000ff`; the three C3 words unchanged |
| `pmp`'s table | 2.9764 | 3.2131 | first touch `R` byte `0x23b549400` = `0x42`, 1.4 ms after `RECV 0x000200000023b549` |
| sample n 5 | 3.0035 | 3.2560 | ps_PMP `0x1f0f03ff`, ps_PMS_SRAM `0x1f0003ff`, ps_PMS `0x1f0002ff`; C3 words `0x444/0x444/0x444` |

- **Same pc:** in det33 the SRAM first touches come from pc `0xfffffe00175ceac4`. That is the pc
  of the entry's 49,152-word `__DATA` read in the same boot's detached log.
- **What the boot captures leave out:**
  - between the four SRAM first touches and the CPU start, later accesses to those four pages are
    not logged;
  - no other SRAM page is touched before 5 s. In det33 and det34b no SRAM page and not the DART
    page is touched again after the first epoch (to 207.9 s and 395.3 s);
  - the power manager's page `0x23b700000` is first-touched at 0.43 s, so macOS's writes to ps_PMP,
    ps_PMS_SRAM and ps_PMS during the boot are not logged. Only the samples show them: unchanged at
    0.755, changed by 2.76.
- **Boot argument block, `135map4`** (`0x23b500000`-`0x23b53ffff` in full). macOS's SRAM
  accesses before the start, in order (t 2.6286-2.6679), all 32-bit from one pc (`…2ac4` reads,
  `…2a64` writes):
  1. `R +0x20`-`+0x5c`, `+0xc0`-`+0xfc` (all 0), `+0x204`-`+0x240`:
     - `+0x204` `0x64697575` (`uuid`);
     - `+0x208` 5;
     - `+0x20c` `0x2a384`, `+0x210` `0x2f3a8` (offsets of the two strings below);
     - four words `0x4c1b7143 0xef30a65c 0x42e17fa0 0xc3523543`;
     - 0, 0;
     - **`+0x22c` `0x3a800`**, **`+0x230` `0x2d0`**;
     - `+0x234` `0x2c000`, 0, `+0x23c` `0x3b52c000`, `+0x240` 2.
  2. `R +0x3a800`-`+0x3aacc` (180 words = `0x2d0` bytes).
  3. The header again, then `R +0x2a384`-`+0x2a3c0` (`RTKit-2062.141.1.release`, `stk_fail`,
     `management`, …) and `R +0x2f3a8`-`+0x2f3e4` (`not set`, …).
  4. The header a third time.
  5. **`W +0x3a800`-`+0x3aacc`, 180 words, every one equal to what was read.**

  The first touch of the DART follows at 2.6687 and the `+0x44` read at 2.6732. *Documentation,
  not an observation:* the reference `pmp.rs` reads the boot arguments from the same places
  (`BOOTARGS_UUID` `0x204` = `uuid`, version 5, offset at `0x22c`, size at `0x230`) and patches
  them in place.
  - The block parses as 54 records: 4-byte tag, 4-byte size, then the value.
  - Values in `135map4`, read and written the same:

    `STKG`(8) `0x1eb718d1d8305600`, `DBUG` 0, `DART` 1, `DOCK` 0, `PWRG` 1, `CLKG` 1, `NRGD` 1,
    `NRGS` 1, `PMON` 1, `PMUT` 0, `SMPL` 0, `TCAP` `0x3e8`, `TGPH` 0, `BDID` `0x26`, `PBAT` 1,
    `FSTD` 1, `SCHT` 1, `ANRG` 0, `PNRB` 0, `SMSK` `0xffffffff`, `CMSK` `0xffffffff`, `DENP` 0,
    `MSGQ` 0, `SLID`(8) 0, `CSSS`(8) 0, `v8Fq` 0, `DSRL`(1) 0, `DSVS`(8) 0, `DSCL`(8) 0,
    `RTSZ` `0x5c000`, `PTPB`(8) 0, `IGNT`(1) 0, `SNeo`(1) 0, `PTVB`(8) 0, `T1Ps`(8) 0, `GptB`(8) 0,
    `GptS`(8) `0x4000`, `PplB`(8) 0, `PTPS`(8) 0, `GxPB`(8) 0, `GxPS`(8) 0, `DSZS`(8) 0, `DSZL`(8) 0,
    `TUNS`(8) `0x103aad0`, `TUNZ` `0x1e8`, `RTTO`(8) 0, `McRA` `0x4000`, `SOC_` `0x8103`, `SOCR`
    `0x11`, `CpAd`(8) `0x23b800000`, `WrAd`(8) `0x23bc00000`, `DEVf`(1) 0, `IOBA`(8) 0, `IOSZ` 0.
  - Whether the values were the same in det33 and det34b is not read: their first word matches
    (`STKG`), and the rest of that page is not logged.
  - In `135map4`, nothing else in `0x23b500000`-`0x23b53ffff` is accessed from then until the
    entry's read of `0x23b52c000`-`0x23b53fffc` at 653.8 s.
- **DART set-up at boot, det10** (DART page in full; t 2.2051-2.2338, in this order):
  1. `R +0x0` `0x0ed01020`, `R +0x4` (PARAMS2) `0x11037` (twice), `R +0x60` (CONFIG)
     `0x80016100`, `W +0xfc` (STREAMS_ENABLE) = 0, `R +0x80`-`+0x8c` (REMAP) `0x03020100`,
     `0x07060504`, `0x0b0a0908`, `0x0f0e0d0c`.
  2. `R +0x0`, `+0x4`, `+0x60`, `R +0xf0` 0, `W +0xfc` = 0, `W +0x200` (TTBR sid 0) = 0, `W +0x2f0`
     = 0, `W +0x34` (STREAM_SELECT) = `0xffffffff`, `W +0x20` (STREAM_COMMAND) = `0x100000`
     (INVALIDATE).
  3. `R +0x60` `0x80016100`, `R +0x68` `0xf0f0f`, `R +0x6c` `0x80808` (already the ADT tunables),
     `R +0x20` `0x100000`, `W +0x100` (TCR sid 0) = `0x80` (TRANSLATE_ENABLE), `W +0x13c` (TCR sid
     15) = `0x100` (BYPASS_DART).
  4. Then, received after det10's first touches of I2A control (2.2164) and `+0x44` (2.2210): `W
     +0x200` = **`0x808217dc`** (valid, table at `0x8217dc000`), `R +0xfc` 0, `W +0xfc` = 1.

  No DART access after that in det10's boot. Whether the TTBR write came before or after the CPU
  start is not established: the two arrive by different paths, and `+0x44`'s write was not logged
  in det10.

### 2. RTKit start-up (boot): every mailbox message, in order

det33 times; det34b has the same messages and values in the same order (2.6029-2.6228).
Messages are written as the 64-bit word, then the endpoint. `+0x110`/`+0x114` status polls
(302/229 reads in det33's boot) are left out.

| t | Dir | Ep | Message | Decoded (reference field names) |
|---|---|---|---|---|
| 2.6750 | RECV | 0 | `0x00100000000c000c` | HELLO, versions 12..12 |
| 2.6765 | SEND | 0 | `0x00200000000c000c` | HELLO_REPLY 12..12 |
| 2.6771 | RECV | 0 | `0x008000000000001f` | EPMAP base 0, bitmap `0x1f` (endpoints 0-4), not last |
| 2.6774-2.6783 | SEND | 0 | `0x0050000100000002`, `…02…`, `…03…` | STARTEP 1, 2, 3 (flag bit 1) |
| 2.6787 | SEND | 3 | `0x0008000000000000` | kdebug type 8 (START) |
| 2.6795 | RECV | 3 | `0x00010000000003e9` | kdebug type 1 (GET_BUFFER), count `0x3e9` |
| 2.6823 | SEND | 0 | `0x0050000400000002` | STARTEP 4 |
| 2.6827 | SEND | 0 | `0x0080000000000001` | EPMAP reply, base 0, bit 0 set ("more") |
| 2.6832 | RECV | 0 | `0x0088000100000001` | EPMAP base 1, bitmap 1 (endpoint `0x20`), last |
| 2.6841 | SEND | 3 | `0x0001000000004000` | kdebug SET_BUFFER0, IOVA `0x4000` |
| 2.6844 | SEND | 3 | `0x0002000000010000` | kdebug SET_BUFFER1, IOVA `0x10000` |
| 2.6846 | SEND | 0 | `0x0088000100000000` | EPMAP reply, base 1, last |
| 2.6849 | RECV | 1 | `0x0010100000000000` | crashlog BUFFER_REQUEST, 1 page, IOVA 0 |
| 2.6851 | SEND | 1 | `0x0010400000018000` | reply: 4 pages at IOVA `0x18000` |
| 2.6854-2.6926 | both | 4 | `RECV 0x0011000000000000` / `SEND 0x0011000000020000`; `RECV 0x00c0000000000000`; 10 × `0x0080000000000000` each way | ioreport BUFFER_REQUEST `0x10` pages, reply IOVA `0x20000`; type `0xc`; type 8 echoed |
| 2.6928 | RECV | 0 | `0x0070000000000020` | IOP_PWR_STATE_ACK `0x20` (ON). No SET_IOP_PWR_STATE was sent before it |
| 2.6929 | SEND | 0 | `0x00b0000000000020` | SET_AP_PWR_STATE `0x20` |
| 2.6932 | RECV | 2 | `0x0080000050000010` | syslog INIT: 16 entries, message size `0x50` |
| 2.6933 | RECV | 2 | `0x0010100000000000` | syslog BUFFER_REQUEST, 1 page |
| 2.6934 | SEND | 2 | `0x0010100000034000` | reply: 1 page at IOVA `0x34000` |
| 2.6939 | RECV | 0 | `0x00b0000000000020` | AP power state `0x20` acknowledged |
| 2.6980 | SEND | 0 | `0x0050002000000002` | **STARTEP `0x20`** |
| 2.6985 | RECV | `0x20` | `0x0000000000000000` | *(guess: `pmp`'s hello on endpoint `0x20`)* |
| 2.7004 | SEND | `0x20` | `0x000100000003c000` | *(guess: a buffer at IOVA `0x3c000`, like the replies above)* |
| 2.7020-2.9714 | both | 4 | 115 × `0x0080000000000000` each way | ioreport type 8, echoed |
| 2.9750 | RECV | `0x20` | `0x000200000023b549` | `0x23b549` × `0x1000` = `0x23b549000`, a page of `pmp`'s `__DATA`. macOS reads `0x23b549400` 1.4 ms later *(guess: "here is my table")* |
| 2.9752 | RECV | 2 | `0x0050000000000000` | syslog LOG, index 0 (macOS echoes it at 2.9807) |
| 2.9784 / 2.9787 | SEND / RECV | `0x20` | `0x0020000000010003` / `0x0020100000010003` | code 0 / 1, number 1, argument 3 |
| 2.9799 / 2.9805 | SEND / RECV | `0x20` | `0x0020200000010000` / `0x0020300000010000` | code 2 / 3, number 1, argument 0 |

- **Endpoints and buffers.** Endpoints started: 1, 2, 3, 4, `0x20`. The endpoint map lists only
  0-4 and `0x20`; there is no OSLog (8) and no endpoint 7.
- **IOVAs answered by macOS:** `0x4000`, `0x10000`, `0x18000`, `0x20000`, `0x34000`, `0x3c000`.
  These are DART addresses. Where they map in DRAM is not read: the page tables at the TTBR are in
  DRAM, which is not logged.
- **No crashlog or syslog content** was read: the buffers are in DRAM. Endpoint 2 sent one LOG
  message (index 0) at 2.9752.
- **Endpoint 4 at boot, to the 0x55 message (det33 = det34b):**
  - 132 × type 8 each way;
  - 2 × `0x0040000000000000` each way (32.0 s, 49.4 s);
  - the one buffer exchange and the one `0x00c…`.
- **Same in det10 and `135map4`:** the first touches give the same pattern: `R 0x23b549400` =
  `0x42` at 2.7130 and 3.1748. macOS's `0x0020e00000550000` appears, as a first touch of the
  mailbox page, at 68.15 s in both.
- **Page `0x23b549000`** (from det33's entry read, not from the boot):
  - 16-byte name slots at `+0x400`-`+0x55f`: `BAT`, `DRAM`, `ECPU`, `PCPU`, `ECORE0`-`3`, `PCORE0`-`3`,
    `ECPM`, `PCPM`, …, `VDEC`, `GPU SRAM`;
  - 64-bit words at `+0x0`-`+0xa0` and `+0x200`-`+0x2a0` *(guess: per-name counters)*.

### 3. Endpoint 0x20 at boot: the message format, and every message up to 0x550000

*Format, as far as the values show:*
- Every message after the opening has bit 53 set (`0x0020…`).
- Bits 44-47 are a code:
  - macOS sends even codes 0, 2, 4, 8, `0xa`, `0xc`, `0xe`;
  - `pmp` answers 0, 2, 4, 8, `0xa` and `0xc` with code + 1;
  - **code `0xe` is never answered in any capture.**
- Bits 16-31 are a number:
  - for codes 8, `0xa`, `0xc` and `0xe` it is always an ADT power-manager device id flagged
    `notify_pmp`: `0x54` DISP0_FE, `0x55` DISPEXT_FE, `0x5c` JPG, `0x63` GFX, `0x64` ISP_SYS, `0x65`
    VENC_SYS, `0x66` AVD_SYS, `0x68` ANE_SYS, `0xe3` ATC1_PCIE, `0x15c` ATC1_PCIE-V;
  - this is a match of numbers *(guess: the device id)*.
- Bits 0-15 are an argument:
  - code `0xe`: 0 or 1 *(guess: device off/on)*;
  - codes `0xa`/`0xc`: `0x20`-`0x23`, echoed in the reply.
- Codes 0-3 carry number 1, and code 4 carries 0 or 2. Their replies (code 5) carry 0. These
  numbers are not shown to be device ids.

*Documentation, not an observation:* the reference `pmp_power.rs` uses the same marker bit 53, a
command at bit 44 and the reply `(command + 1) << 44`. It puts `device_id` at bit 40 and
`enabled` at bit 32, so its layout does not match these words.

Every endpoint-`0x20` message in det33's boot, from the opening to the 0x55 message (det34b: the
same set and counts, except `0x0020e000005c0001`, `0x0020e00000640001` and `0x0020e00000660001` ×3
instead of ×4, and no `0x0020e00000e3…`/`0x0020e000015c…`):

| Message | Count (det33) | First t (det33) | Answered by |
|---|---|---|---|
| `0x0020000000010003` | 1 | 2.9784 | `0x0020100000010003` |
| `0x0020200000010000` | 1 | 2.9799 | `0x0020300000010000` |
| `0x0020e00000630001` (GFX, 1) | 2 | 3.0628 | none |
| `0x0020800000630000` (GFX) | 1 | 3.0730 | `0x0020900000630000` |
| `0x0020e00000680001` (ANE_SYS, 1) | 3 | 3.1134 | none |
| `0x0020e00000660001` / `…0000` (AVD_SYS) | 4 / 4 | 3.1501 | none |
| `0x0020e000005c0001` / `…0000` (JPG) | 4 / 4 | 3.2080 | none |
| `0x0020800000680000` (ANE_SYS) | 3 | 3.2225 | `0x0020900000680000` |
| `0x0020e00000640001` / `…0000` (ISP_SYS) | 4 / 4 | 3.2410 | none |
| `0x0020a00000540022` (DISP0_FE, `0x22`) | 1 | 3.3876 | `0x0020b00000540022` |
| `0x0020c00000640021` (ISP_SYS, `0x21`) | 1 | 3.4111 | `0x0020d00000640021` (0.11 s later) |
| **`0x0020a00000550023` (DISPEXT_FE, `0x23`)** | 1 | **3.5477** | `0x0020b00000550023` |
| `0x0020a00000640020` (ISP_SYS, `0x20`) | 1 | 3.5761 | `0x0020b00000640020` |
| `0x0020e00000e30001` / `…0000` (ATC1_PCIE) | 1 / 1 | 3.6150 | none |
| `0x0020e000015c0001` / `…0000` (ATC1_PCIE-V) | 1 / 1 | 3.6152 | none |
| `0x0020e00000650001` / `…0000` (VENC_SYS) | 1 / 1 | 3.8551 | none |
| `0x0020400000020000` / `0x0020400000000000` | 36 / 36, alternating | 24.7131-24.8235 | each `0x0020500000000000` |
| **`0x0020e00000550000` (DISPEXT_FE, 0)** | 1 | **69.3808** (det34b 69.2321) | none |

- **Before the 0x55 message:** no `0x0020e…0055…0001` precedes it in either boot. The only earlier
  message with number `0x55` is the code-`0xa` pair at 3.55 (det34b 3.64).
- **After it, for the rest of the boot captures** (det33 to 207.9 s, det34b to 395.3 s): no
  mailbox traffic on `pmp` at all. Both pages are logged in full.
- **det33 detached, idle 0-447 s:** one endpoint-4 pair (164.4 s) and `0x0020e00000540000`
  (440.9 s).
- **The first C3 change refined:** by receipt time, everything in section 2 up to
  `SEND 0x000100000003c000` comes **before** sample n 4, and that sample still reads
  `0x444/0x666/0x333`.
  - Between n 4 and n 5 (the first `0x444/0x444/0x444`):
    - in both boots: `RECV 0x000200000023b549`, the syslog LOG pair, the code 0/1 and 2/3 pairs;
    - det34b adds three `…5c…` code-`0xe` messages and the c/d (`0x64`) and a (`0x64`) messages.
  - The earliest `pmp` event common to both windows is `RECV 0x000200000023b549`.
  - Records can arrive late, so an access received after a sample may have happened before it.

### 4. Entry (det33 detached; det18 and det23 the same sequence)

| t | Access |
|---|---|
| 447.4617 | `SEND 0x0020e00000550001`, then `0x0020e00000540001` (447.4645) |
| 447.4677 | `SEND 0x0020800000630000` / `RECV 0x0020900000630000` |
| 447.4783 | **`SEND 0x0020e00000550000`**, then `0x0020e00000540000` (447.4791). Section 3 of round 10 lists only the `…0001` pair; the log has both. The C3 words were already `0x333/0x444/0x222` and stayed so |
| 447.8455-447.8460 | `SEND 0x00b0000000000201` (SET_AP_PWR_STATE `0x201`, IDLE in the reference) / echoed; `SEND 0x0060000000000201` (SET_IOP_PWR_STATE `0x201`) / `RECV 0x0070000000000201` |
| 447.8461 | `W 0x23bc08114` = `0x22200` (RECV_ENABLE clear); `R +0x48` = `0x2e` (CPU_STOPPED already set); `R +0x44` = `0x10`; **`W +0x44` = 0** |
| 447.8461 | DART: `R +0x40` (ERROR) `0x6000400`, `R +0xfc` 1, `R +0x100` `0x80`, `R +0xfc` 1, **`W +0xfc` = 0**, `R +0x13c` `0x100`, `R +0xfc` 0, `W +0xfc` = 0, `R +0x40`, `R +0x100c` 0 |
| 447.8461-448.1519 | **`R` 49,152 words `0x23b52c000`-`0x23b55bffc` in order**, one pc (`…ceac4`, the boot's SRAM-read pc) |
| 448.2605 | `R` 12 64-bit words: `0x23b549000`/`200`, `008`/`208`, `010`/`210`, `018`/`218`, `090`/`290`, `0a0`/`2a0` |
| 448.2775 | T (last core) |

- No access to the ps_PMP, ps_PMS_SRAM or ps_PMS words anywhere in idle or entry: the detached log
  is full.
- The samples read ps_PMP `0x1f0f03ff`, `+0x44` 0, `+0x48` `0x2e` after the stop.
- det18 (444.58-445.31) and det23 (424.47-425.19) have the same steps:
  - the same management words, I2A word and `+0x44`;
  - 49,164 SRAM reads over the same range (det18 from two CPUs).

### 5. Wake (det33 detached; det18 and det23 the same sequence)

| t | Access |
|---|---|
| 538.1498 / 538.1501 | wake entry / guest re-entered |
| 538.1512 (n 1789) | `+0x44` 0, `+0x48` `0x2a`; ps_PMP `0x0f0003ff`, ps_PMS_SRAM `0x0f000300` (target and actual 0), ps_PMS `0x0f0002ff` |
| 538.1623-538.1624 | ps_PMP: `R 0x0f0003ff`, `W 0x0f0000ff`, `R`, `W 0x0f0000ff`, `R`, **`W 0x1f0000ff`** (AUTO_ENABLE) |
| 538.1624 | ps_PMS_SRAM: `R 0x0f000300`, `W 0x0f000000`, `R` ×3, **`W 0x0f00000f`** (target `0xf`), `R 0x0f00030f`, `R 0x0f0003ff` (actual `0xf`), **`W 0x1f00000f`** |
| 538.1636 | ps_PMS: `R 0x0f0002ff`, `W 0x0f0000ff` ×2 (with reads), **`W 0x1f0000ff`** |
| 538.1680 | `W` the 12 64-bit words at `0x23b549000`-`2a0`, the values read at the entry |
| 538.2963-538.5046 | **`W` 49,152 words `0x23b52c000`-`0x23b55bffc` in order** (pc `…cea64`). **Every byte written equals the byte read at the entry** (196,608 of 196,608). This replaces round 10's "24,576 writes over `0x23b544000`-`0x23b55bfff`", which counted only the part after the sample at 538.4016 |
| 538.5046 | DART: `R +0x0` `0x0ed01020`, `R +0x4` `0x11037`, `R +0x60` `0x10000`, `R +0xf0` 0; **`W +0xfc` = 1**; **`W +0x200` = `0x80822544`** (table at `0x822544000`); `W +0x2f0` = 0; `W +0x34` = `0xffffffff`; `W +0x20` = `0x100000` |
| 538.5046-538.5047 | DART: `W +0x60` = `0x80016100` (read `0x10000`); `W +0x68` = `0xf0f0f` (read `0x20202`); `W +0x6c` = `0x80808` (read 0); `W +0x100` = `0x80`; `W +0x13c` = `0x100` |
| 538.5047 | `W 0x23bc08114` = `0x20001`; `R +0x44` 0; **`W +0x44` = `0x10`** (same pc as the boot's start, `0xfffffe00153e6174`) |
| 538.5048-538.5054 | `RECV 0x00100000000c000c` / `SEND 0x00200000000c000c`; `RECV 0x008000000000001f` / **`SEND 0x008000000000001f`**; `RECV 0x0088000100000001` / **`SEND 0x0088000100000001`** (the replies echo the bitmap, unlike the boot's); `RECV 0x0070000000000020` (unsolicited, as at boot); `SEND`/`RECV 0x00b0000000000020` |
| — | No STARTEP, no buffer request on any endpoint, no endpoint-`0x20` opening (`0x0`, `0x3c000`, `0x23b549`, codes 0-3) |
| 538.5957 | `SEND 0x0020e00000630001` |
| 538.6087 / 538.6107 | `SEND 0x0020e00000550001` / `0x0020e00000540001` |
| 538.6187 / 538.6198 | **`SEND 0x0020e00000550000`** / `0x0020e00000540000` |
| 538.6517 (n 1791) | C3 words `0x333/0x444/0x222`; `+0x44` `0x10`, `+0x48` `0x2c`, ps_PMP `0x1f0f03ff` |
| 538.7486 | endpoint 4 `0x0040000000000000` each way |

- **det18 and det23:** the same steps.
  - The SRAM writes start about 4 ms after the ps writes: det18 534.9203-535.2472, det23
    515.2270-515.5622. Their writes equal their entries' reads in count and non-zero count.
  - The handshake words are the same.
  - The endpoint-`0x20` messages: det18 `…630001`, `…540001`, `…550001`, `…550000`, `…540000`;
    det23 `…630001`, `…550001`, `…540001`, `…540000`, `…550000`.
- *Documentation, not an observation:* `+0x48` bits per Asahi `asc.md`: 5 MBOXES_TO_AP_EMPTY,
  3 FIQ_NOT_PENDING, 2 IRQ_NOT_PENDING, 1 CPU_STOPPED, 0 CPU_IDLE.
  - `0x2a`: stopped (bare proxy, before each start).
  - `0x2c`: running.
  - `0x0c`: running with a message waiting for macOS.
  - `0x28`: an IRQ pending.
  - `0x2e`: stopped (at the entry, before macOS cleared `+0x44`).
- Power-state bits per the reference `pmgr-pwrstate.c`: 28 AUTO_ENABLE, 24-27 PS_AUTO, 16-19
  PS_MIN, 9/8 WAS_CLKGATED/WAS_PWRGATED, 7-4 actual, 3-0 target.

### Not covered by these captures

- **Boot accesses to the SRAM and the DART in det33 and det34b:** first touch per 5 s only.
  - The boot-argument read and write-back is read only in `135map4`; the DART set-up at boot only
    in det10. Each is one boot, not round 10's.
  - No boot logged SRAM `0x23b540000`-`0x23b57ffff` (the end of `__DATA`, incl. `0x23b549000`) in
    full. Whether macOS writes there before the start is not read. In det33 and det34b the first
    touch of page `0x23b548000` is a read at 2.98 s, after the start.
- **The power-state words during the boot:** only the 250 ms samples (one gap 0.76-2.76 s); the
  writes are not logged. The wake's sequence (section 5) may differ from the boot's.
- **DRAM:** the IOVA buffers (`0x4000`-`0x3c000`), the DART page tables (`0x8217dc000` in det10,
  `0x822544000` in det33), and the crashlog, syslog and ioreport contents are not logged.
- **Timing within the boot:** receipt times. Sync and async records are not ordered against each
  other, nor against the samples, to better than the USB buffering.
- **What each endpoint-`0x20` field means:** inferred from values only (marked *guess*). No message
  was sent or withheld, so which message lowers the C3 words is still not established.
- **The four pages left out of the detached full log** (`0x23b738000`, `0x23bc34000`,
  `0x210e20000`, `0x211e20000`) are not seen at the entry or the wake.

### Files (private)

- `var/commit-state/r10_pmp_startup.py`: the decoder. It covers every access to `pmp`'s blocks,
  its SRAM, its DART and the three power-state words; mailbox messages are decoded by RTKit field,
  status polls and endpoint 4 are folded, and SRAM runs are summarized.
- Its outputs:
  - `var/commit-state/r10-pmpstart-det33-boot.txt`, `r10-pmpstart-det34b-boot.txt` (0 to just after
    the 0x55 message);
  - `r10-pmpstart-det33-entry.txt` (440-448.3);
  - `r10-pmpstart-det33-wake.txt` (538.0-539.5).
- The det10, `135map4`, det18 and det23 readings were made with the same script, over the same
  windows, from `tools/hv-trace-kit/runs/20261116-mac135/touch-det10.jsonl`,
  `touch-135map4.jsonl`, `detached-det18.jsonl` and `detached-det23.jsonl`.

## Earlier Linux runs with pmp started (readings collected 2026-11-19)

Readings only. They come from the lab's evidence READMEs and the private run files those cite. No
M1 run was made and the M1 was not claimed. No driver source was read.

In every run of sections 1-5 `pmp` was started by an out-of-tree module, `apple-pmp-v1`. It was loaded with
`modprobe` after boot, on a kernel booted with `apple_pmp_v1_hold=1`. The module is named only to
identify the runs, in the run logs' and command lines' own words.

Trace times `t` are seconds from the tracer's start.

Firmware:
- 13.5 from 2026-11-14 on. The bring-up log of that day reads `system firmware 13.5 ; iBoot
  iBoot-8422.141.2`.
- The runs of 2026-11-05 and 2026-11-08 ran on the earlier, macOS-27-era firmware. Evidence
  `2026-11-16-run36-38-restart` calls it "the earlier system firmware (runs 1-11)".

**Correction.** Section 4 of "Linux round: pmp and the endpoint-0x20 message" says starting
`pmp`'s firmware "has not been done under Linux on this machine". It also calls its start-up one
that "has never run under Linux here". That holds for the stock kernel `7.3.0-0test5` read in
that round, but not for the machine.

`pmp` was started under Linux, with its RTKit handshake and its endpoint-`0x20` opening answered:
- on bare metal on 2026-11-05 and 2026-11-14, in runs 37 and 39, and by command line in runs
  40-43 (2026-11-16/17); started, by the README, on 2026-11-08;
- as the hypervisor's guest in lx3, lx4, lx9, lx11-lx14 and lx16-lx24 (2026-11-16/17).

In eleven of the traced hypervisor runs Linux sent `0x0020e00000550000` (section 5).

### 1. How it was started (the same in every logged start)

Sources:
- the bare-metal bring-up of 2026-11-14 17:49 (`pmp-bringup-20261114-174901.txt`): the module's
  kernel-log lines and the script's own register reads;
- the hypervisor trace of lx12 (`s2r-trace-lx12.jsonl`, events `pmp-tx`/`pmp-rx`).

The run-37 and run-39 kernel logs show the same endpoint-`0x20` words. The lx3-lx21 traces show
the same management, buffer and endpoint-`0x20` words.

- **Before the load:**
  - The loader's tree has no `pmp` node (`nodes compatible apple,t8103-pmp-v1: []`).
  - With `apple_pmp_v1_hold=1` the log reads `ps_pmp and ps_pms_sram marked always-on`.
  - `ps_PMP` `0x1f0000ff`, `ps_PMS_SRAM` `0x1f0000ff`. The stock kernel reads PMS_SRAM
    `0x0f000300` (Linux round above).
  - `pmp` +`0x44` `0x0`, +`0x48` `0x2a`; both mailbox control words `0x20001`.
- **Device tree, by overlay at the load:**
  - The log line reads `added /soc/pmp@23b850000, /soc/iommu@23b300000 and /soc/mbox@23bc08000`.
  - Afterwards `/proc/device-tree/soc/pmp@23b850000` exists in memory only. In the log's words,
    "the next boot's tree comes from the loader again".
- **Before the CPU's release** the log has three lines:
  - an SRAM line (`SRAM head 14000095 00000000 …, 898/1024 words set`);
  - a DRAM energy-model line (512 bytes from the device tree);
  - a DART line (34 windows).

  Nothing more about them is in the log.
- **RTKit management endpoint** (lx12, t 132.209-132.226):
  - RECV HELLO `0x00100000000c000c`;
  - SEND SET_IOP_POWER `0x220`;
  - SEND HELLO_ACK `0x00200000000c000c`;
  - endpoint map: RECV `0x008000000000001f` and `0x0088000100000001`; SEND `0x0080000000000001`
    and `0x0088000100000000`;
  - SEND START_EP for endpoints 1, 2, 3 and 4;
  - RECV IOP_POWER_ACK `0x20`; AP power `0x20` sent and echoed;
  - SEND START_EP `0x20` (`0x0050002000000002`).
- **Buffer requests answered:**

  | Endpoint | RECV | SEND |
  |---|---|---|
  | 1 | `0x0010100000000000` | `0x00101000fffec000` |
  | 4 | `0x0011000000000000` | `0x00110000fffd0000` |
  | 2 | `0x0010100000000000` | `0x00101000fffcc000` |

  Endpoint 4 then exchanges `0x00c0000000000000` once each way. It exchanges
  `0x0080000000000000` 125 times each way, t 132.2175-132.2891.
- **Endpoint `0x20` opening:**
  - RECV `0x0`;
  - SEND `0x00010000ffff0000`;
  - RECV `0x000200000023b549`, 63-65 ms later;
  - SEND `0x0020000000010003` / RECV `0x0020100000010003`;
  - SEND `0x0020200000010000` / RECV `0x0020300000010000`.

  The firmware's syslog reads `main.cpp:4480: PMP started`. Against macOS's opening (round 10,
  above) only the second word differs: macOS sends `0x000100000003c000`.
- **Device reports at the start.** Seen in runs 37 and 39 and in every hypervisor run with `pmp`
  started. Runs 40-43 load the module the same way (their run scripts), but no log of their start
  was kept.
  - 13 SEND words: `0x0020e00000540001`, **`…550001`**, `…5c0000`, `…5d0000`, `…630001`,
    `…640000`, `…650000`, `…660000`, `…680000`, `…de0001`, `…e30001`, `…15b0001`, `…15c0001`.
  - The module's log names id `0x55` DISPEXT_FE, state 1, power word `0x23ff`.
  - No word answers them in the traces.
  - With `reports=0` (both runs of 2026-11-14) none were sent.
- **After the start, running:** `ps_PMP` `0x1f0f03ff`, `ps_PMS_SRAM` `0x1f0003ff` (run 37's log,
  just after the load). The same two values after the stop (2026-11-14, S1-S3).
  - macOS reads PMS_SRAM `0x1000030f` from its second change on (round 10).
  - No Linux reading in these files shows `0x1000030f`.
- **Stopped as macOS stops it, with no sleep** (2026-11-14, +5 s):
  - The log reads `stopped as macOS does (AP 0x201, IOP 0x201, CPU halted)`.
  - Then +`0x44` `0x0`, +`0x48` `0x2e`; mailbox control words `0x25501` (A2I), `0x24401` (I2A).
  - The power chips' words and the engine port were unchanged at S1, S2 (+5 s) and S3 (+30 s).

### 2. At the entry (hypervisor traces)

- **Run 39's kernel (lx3, lx4):**
  - No `0x0020e…` and no `0x208` message at the entry.
  - AP `0x201` and IOP `0x201` were sent 0.001-0.002 s after `slpw`, and both were answered: lx4
    79.9367-79.9383, lx3 76.1775-76.1786.
- **Run 40's and 41's kernels** (command line `apple_pmp_v1.mac_notes=1`; traced in lx9,
  lx11-lx14, lx16-lx21):
  - The messages come after `slpa`, after the power chip's `0x9f01` = `0x50` and after SIO's AP
    and IOP `0x201`.
  - Within 3 ms: SEND `0x0020e00000550001`, `…540001`, **`…550000`**, `…540000` and
    `0x0020800000630000`; RECV `0x0020900000630000`.
  - Then AP `0x201` and IOP `0x201`, both answered.
  - `…550000` comes 0.117-0.189 s after `slpw`. lx12: `slpw` 139.6623, `slpa` 139.7800,
    `…550000` 139.7837, IOP answer 139.7858.
  - Apart from the endpoint-4 traffic, the word sequence is identical in lx11-lx21.
- **Answers:** no word answers any `0x0020e…` word in any trace.
- **macOS's entry, for comparison** (det33, with det18 and det23 the same; section 4 of "macOS's
  pmp start-up and endpoint-0x20 exchange" above):
  - `…550001`, `…540001`, then `0x0020800000630000` / `0x0020900000630000`, then `…550000`,
    `…540000`.
  - AP and IOP `0x201` follow 0.37 s later.
  - Linux puts the `0x208` pair after `…540000`, and its idle follows in under 1 ms.
  - In 135r6 (evidence `2026-11-16-hv-linux-entry`), `0x20e` comes at `slpw` +0.20 s and
    `0x208` dev `0x63` at +0.23 s. The idle comes last, at +0.72 s.
- **After an entry that did not reach its commit:**
  - The entry stopped in lx3 after the SEP's RECV `0x100` at 76.1789, and in lx9 by the driver's
    own stop.
  - Linux then sent SET_IOP_POWER `0x220`: lx3 at 76.5975, lx9 at 141.7568.
  - `pmp` did not answer in either trace (to t 386.5 and 144.06).
  - The 2026-11-08 self-test also reports a failed wake after the idle: "the following wake →
    -62".

### 3. The three C3 words and the power-state words

- **Read in four runs only:** at the hypervisor's snapshot when the last core reached Linux's
  commit (L28), in lx12, lx13, lx14 and lx17.
  - `0x23b058000` = `0x333`, `0x23b05c000` = `0x444`, `0x23b060000` = `0x222`.
  - `ps_PMP` `0x1f0f03ff`, `ps_PMS_SRAM` `0x1f0003ff`, `ps_PMS` `0x1f0002ff`, `ps_DCS0`
    `0x1f0002ff` (lx17: `0x1f0003ff`).
  - Each snapshot came after `…550000`: 0.25 s after in lx12 and lx13, 0.37 s in lx14, 0.32 s
    in lx17.
- **Not read in any run with `pmp` started:**
  - before the start;
  - between the start and the entry;
  - between `…550000` and the commit.
- **No control run:** one pmp-started run without `…550000` had its commit snapshotted (lx4).
  That snapshot had 30 words, and these three were not among them. So these runs do not separate
  the start, the message and the entry as the cause of the change.
- **Without `pmp`,** Linux awake reads `0x444/0x666/0x333` (L27). Source:
  `var/commit-state/linux-live-wide.json`, 2026-11-17 00:24; `ps_PMS_SRAM` reads `0x0f000300`
  in the same file.
- **`pmp` +`0x44`/+`0x48` while `pmp` runs under Linux:** not read in these files. The traces log
  the mailbox only. The bare-metal reads come before the load or after the stop.

### 4. The runs

**Bare metal.**
- "Record" is the power chip's `0x9f10`-`0x9f17`.
- Byte 6 is read as in the evidence of runs 37, 39 and 40: `01` means the `pmp` idle was
  answered; `0x47` means the late steps ran in macOS's order, `pmp` idled after the SMC's AP
  `0x201`.
- The C3 words were read in no bare-metal run.

| Run (date, firmware) | Kernel | Started | Idle, answer | `…550001` / `…550000` | PMP / PMS_SRAM | End | Source |
|---|---|---|---|---|---|---|---|
| `j1105-151447-7dbc`, `-154719-3e5d`, `-155048-25e6` (11-05, macOS-27-era) | `7.2.11-labf1f05ca2-9b06` | overlay; handshake complete; "PMP started"; 13 `0x20e` reports "accepted" | no sleep (idle power windows) | words not in the lab's files | not in the lab's files | no sleep | `docs/STATUS.md` (PMP v1 entries); evidence `2026-11-06-status-report.html` |
| test 2: row 9 of "The last three Linux runs" (11-08, macOS-27-era) | not stated (the README's kernel line: `m1power/s2r-mem`) | started (README: `pmp_v1`) | AP + IOP `0x201` between `slpw` and `slpa`; answer not stated | not stated | not read | 180.9 s, no wake (the runs' watchdog-1 net: 170 s after the commit); no results byte kept yet | evidence `2026-11-07-linux-s2r` |
| idle self-test (11-08, macOS-27-era) | same | started | idle answered; the following wake → -62 | not stated | not read | no sleep | same |
| bring-up 17:49 (11-14, 13.5), `j1114-121806-cbe0` | `7.2.11-labsep14` #78 | section 1; reports off | stopped at +5 s (AP and IOP `0x201`, CPU halted) | none sent | `0x1f0000ff`/`0x1f0000ff` -> `0x1f0f03ff`/`0x1f0003ff` (after the stop) | no sleep; CPU halted from +5 s (+`0x44` `0x0`) | `var/m1-state/20261116-131425-run38/m1power-s2r/pmp-bringup/pmp-bringup-20261114-174901.txt` |
| acceptance cycle 18:25 (11-14, 13.5), `j1114-125406-8dbc` | `labsep14` #82 | handshake ready; "S2R hook registered"; reports off | not recorded | none sent | not read | next boot 25 s after the entry, "wake-restart"; `0x0201` `04`->`04`; `0xa47b` `000c` unchanged; watchdog 1 net 170 s | same dir: `run25-20261114-182459.txt`, `acceptance/20261114-182516-single.result` |
| run 37 (11-16, 13.5), `j1116-073205-9163` | `7.2.11-run37` | section 1; reports on | between `slpw` and `slpa`; byte 6 `01` | `…550001` at the start; entry not logged | `0x1f0f03ff`/`0x1f0003ff` after the start | type-C partner gone 4.3-5.3 s after the release; watchdog 2 moved to 100 s; `0x9f02` unchanged; next boot 28 s after the entry; `0x0201` `01`->`01`; record `d2 01 04 05 64 01 01 01` | same dir: `run22-20261116-130310.txt`, `acceptance/20261116-130326-single.result`; `var/m1-state/pmu-20261116-130412-after-run37.txt`; evidence `2026-11-16-run36-38-restart` |
| run 39 (11-16, 13.5), `j1116-143547-0578` | `7.2.11-run39` | section 1; reports on | byte 6 `01` | `…550001` at the start; entry not logged | `0x1f0000ff`/`0x1f0000ff` before; after not kept | restart 5.0 s after the release; record `d2 01 04 05 64 01 01 31` | `var/lab-logs/j1116-143547-0578/prevboot/kernel.txt`; `var/m1-state/pmu-20261116-200855-after-run39.txt`; evidence `2026-11-16-run39-aop-sensors` |
| run 40 (11-16, 13.5) | `7.2.11-run40`, `mac_notes=1` | by command line and run script; no kept log of the start | byte 6 `0x47` | not read: the log after `rmmod apple-sep` was not kept | not read | restart 5.0 s after the release; record `d2 01 04 05 64 01 47 31` | `var/run22-src/run40.cmdline`; `var/m1-state/pmu-20261116-210051-after-run40.txt`; evidence `2026-11-16-run40-mac-order` |
| run 41 (11-16, 13.5) | `run41` (+ `mac_state`) | as run 40 | `0x47` | not read | not read | release to Omarchy 30.0 s; record as run 40 | `var/run22-src/run41.cmdline`; `var/m1-state/pmu-20261116-232145-after-run41.txt`; evidence `2026-11-16-run41-mac-state` |
| run 42 (11-17, 13.5) | `run42` (+ `dram_gate`) | as run 40 | `0x47` | not read | not read | release to Omarchy 29.8 s; record `d2 80 04 05 64 01 47 31` | `var/run22-src/run42.cmdline`; `var/m1-state/pmu-20261117-002415-after-run42.txt`; evidence `2026-11-16-dram-controller-state` |
| run 43 (11-17 02:53, 13.5) | `run43` (+ `mem_quiet`) | as run 40 | not in the lab's files | not read | not read | release to Omarchy 29.8 s; "wake-restart"; `0x0201` `00`->`01`; record not in the lab's files | `var/run22-src/run43.cmdline`; evidence `2026-11-16-dram-controller-state` |

The 11-14 17:43 attempt (`j1114-121211-baef`) did not load: "an apple_pmp module is already
loaded".

**Under the hypervisor** (13.5, m1n1 hypervisor; "non-real" means the CPUs exit to m1n1 at the
commit). The traces log the `pmp` mailbox in full. Times are the HELLO, the SEND of `…550000`,
and the answer to IOP `0x201`.

| Run (date) | Kernel, mode | HELLO | `…550000` | IOP `0x201` answered | C3 at the commit | PMP / PMS_SRAM at the commit | End |
|---|---|---|---|---|---|---|---|
| lx3 (11-16) | run39 | 73.39 | not sent (`…550001` at the start only) | 76.1786 | no commit | no commit | entry stopped after the SEP's `0x100` (README: in prepare); SET_IOP_POWER `0x220` at 76.5975 not answered |
| lx4 (11-16) | run39, non-real | 72.47 | not sent | 79.9383 | not in the 30-word snapshot | not read | snapshot 80.2737; CPUs exited |
| lx9 (11-16) | run40, freeze probe | 132.87 | 140.2657 | 140.2689 | not read | not read | entry stopped by the driver (cores parked `0x0 0x7e`); the M1 stopped answering about 4 s later |
| lx11 (11-16) | run40, real | 132.94 | 140.5034 | 140.5055 | not read | not read | commit 23:02:33.89; Omarchy on Thunderbolt 23:03:04.00 (30.1 s); restart about 5 s after the commit (README, inferred); `0x0201` `01` |
| lx12 (11-16) | run40, non-real, 279 words | 132.21 | 139.7837 | 139.7858 | `0x333/0x444/0x222` (140.0354) | `0x1f0f03ff`/`0x1f0003ff` | CPUs exited |
| lx13 (11-16) | run41, non-real, 279 words | 72.84 | 80.4013 | 80.4033 | the same (80.6556) | the same | CPUs exited |
| lx14 (11-16) | run41, non-real, 823 words | 73.22 | 80.5976 | 80.5996 | the same (80.9720) | the same | CPUs exited |
| lx16 (11-17) | run41, DRAM gating switched before the guest, real | 72.90 | 80.4645 | 80.4680 | not read | not read | commit 00:35:41.44; Omarchy 00:36:11.39 (29.95 s); no wake |
| lx17 (11-17) | as lx16, non-real, 823 words | 72.10 | 79.4731 | 79.4751 | the same (79.7947) | the same | CPUs exited |
| lx18 (11-17) | run41, probe after the commit | 72.87 | 80.2888 | 80.2908 | not read | not read | restart 8 s after the commit (the probe's last step: the SMC stop) |
| lx19 (11-17) | as lx18 | 72.70 | 80.2284 | 80.2317 | not read | not read | off the bus 99.9 s after the commit (watchdog 2 at 100 s; cause not separated); the probe wrote `pmp`'s run control 0 after the commit, not read back |
| lx20 (11-17) | as lx18 | 72.99 | 80.3256 | 80.3271 | not read | not read | as lx19 |
| lx21 (11-17) | run41, DCS series | 73.90 | 81.5332 | 81.5365 | not read | not read | CPUs exited |
| lx22, lx23 (11-17) | run41, touch map | console: started, 13 reports | not logged (first touch per page only) | not logged | not read | first touches at t 72.6-72.8, before the start: `ps_PMP` `0x1f0000ff`, +`0x44` `0x0` | CPUs exited |
| lx24 (11-17) | run43, touch map | as lx22 | not logged | not logged | not read | as lx22 | CPUs exited |

Sources:
- traces `tools/hv-trace-kit/runs/20261116-linux/s2r-trace-<run>.jsonl` (events `pmp-tx`,
  `pmp-rx`, `snap`), `console-lx16.out` to `console-lx24.out`, `touch-lx22.jsonl` to
  `touch-lx24.jsonl`, `hv-<run>.log`;
- snapshots `var/commit-state/linux-run40-lx12.json`, `linux-run41-lx13.json`,
  `linux-run41-lx14-wide.json`, `linux-run41-dramgate-lx17-wide.json`;
- guest command lines `var/hvlinux/bootargs-run39hv.txt`, `-run40hv`, `-run41hv`, `-run43hv`;
- kernels and endings: evidence `2026-11-16-hv-linux-entry`, `2026-11-16-run40-mac-order`,
  `2026-11-16-hv-linux-real-s2r`, `2026-11-16-run41-mac-state` and
  `2026-11-16-dram-controller-state`.

### 5. Was `0x0020e00000550000` sent?

- **Yes, by Linux, in 11 traced hypervisor runs,** once each at the entry: lx9, lx11, lx12, lx13,
  lx14, lx16, lx17, lx18, lx19, lx20 and lx21. They ran from 2026-11-16 22:38 to 2026-11-17
  01:04, on kernels run40 and run41. It is the third of the six words in section 2. No word
  answered it.
- **Bare-metal runs 40-43** had the same switch on their command lines. Whether they sent it:
  not read. The kernel log after `rmmod apple-sep` was not kept (run 40's evidence), and no
  mailbox trace exists.
- **lx22-lx24** had the same switch. The touch map does not log the mailbox words.
- **`…550001`:**
  - sent at every logged start with reports on (runs 37 and 39; lx3, lx4, lx9-lx24);
  - sent again at the entry, just before `…550000`, in the runs that sent `…550000`.
- **No earlier evidence README says Linux sent either word:**
  - `2026-11-16-hv-linux-entry` (lx4) says Linux sent no `0x20e`;
  - run 40's README lists `apple_pmp_v1.mac_notes=1` but not the words.

### Not started (for completeness)

- **Bare metal:**
  - every other run log in the M1's state copies (`var/m1-state/*/m1power-s2r/run2[25]-*.txt`,
    2026-11-14 to 11-16), including run 38 (`pmp=not-started`). Each reads "PMP state:
    not-started" and has no load;
  - the clean-room runs ds2-ds20 (ds15: `ps_PMS_SRAM` `0x0f000300`);
  - `j1105-144905-7bbc` (2026-11-05): "the PMP never started" (`docs/STATUS.md`).
- **Hypervisor:**
  - lx1, lx2, lx5-lx8, lx10 and lx15 have no `pmp` mailbox traffic (lx5-lx8 and lx10 froze
    early; lx15's console has no `PMPv1` line);
  - dsh1 and dsh2 have no `pmp` traffic and no touch of `0x23bc…` either. dsh2's pre-detach
    words read `0x444/0x666/0x333`, PMS_SRAM `0xf000300`.

## Hypervisor round 11: macOS without the endpoint-0x20 0x55 message (det35, det36, det37, 2026-11-19 01:20-02:04)

Readings only. Taken to test round 10's open point: does macOS's endpoint-`0x20` message
`0x0020e00000550000` to `pmp` (mailbox `0x23bc08000`) cause the three words `0x23b058000`,
`0x23b05c000`, `0x23b060000` (written `058000/05c000/060000`) to change? The hypervisor **dropped**
the message: it was never put into the mailbox. It was not delayed. Where a reading was not taken,
the text says "unknown".

**Short answer.**
- **With the message dropped (det36, every send of it; det37, only the one after the wake):**
  - **Boot (det36):** at the drop (t 69.348) and for the 123 s sampled after it, the words stayed
    at `0x444/0x444/0x444`. `060000` never read `0x222` and `058000` never read `0x333`
    (481 samples, t 70-192; none of the 734 boot samples). `ps_PMP` and `ps_PMS_SRAM` **never read
    `0x1000030f`** in the whole run. They read `0x1f0f03ff` / `0x1f0003ff` in every sample from
    `pmp`'s start to the sleep (728 boot samples, 1815 detached samples of idle and entry), and in
    141 of the 143 after the wake (the first two: `0xf0003ff` / `0xf000300`, then `0x1f0003ff`). `pmp` +`0x44` read
    `0x10` throughout (`pmp` running). In det35 and det37, where the boot message was sent, all three
    changed together to `0x333/0x444/0x222`. The change came in the first sample after the send:
    214 ms after it in det35 and 72 ms in det37. `ps_PMP` and `ps_PMS_SRAM` then read `0x1000030f`
    in 344-394 of the following 452-495 samples.
  - **Idle and entry without it (det36):**
    - `058000` went `0x444` -> `0x333` in the first sample after macOS's `0x0020e00000540000`
      (t 447.65, the only endpoint-`0x20` message between those two samples).
    - `060000` went `0x444` -> `0x222` in the first sample after `pmp` was stopped (`W 0x23bc00044`
      = 0 at t 454.512; the 0x55 message had been dropped at 454.220).
    - So at the commit the snapshot read `0x333/0x444/0x222`, as in det35.
  - **Wake without it (det36, det37):**
    - The first sample after the re-entry read `0x333/0x555/0x333`, as in det33 and det35.
    - The sample after `pmp`'s restart and macOS's messages (0x55 dropped) read
      **`0x333/0x444/0x444`**, and it stayed so in all 141 samples to the read-out (35 s).
    - With the message sent (det35, and det33 in round 10) that sample and the rest read
      `0x333/0x444/0x222`.
- **macOS still went to its idle sleep and powered down** in all three runs: asleep 89.6-90.2 s,
  woke at the hypervisor's 90 s alarm, wake status `0 / 0x400000 / 0`. That is the same outcome as
  det18 and det33. The power chip afterwards read det18's values.
- **macOS was not broken by the drop:** it booted to the login window (camera) and reached idle,
  sleep and wake as without it. Whether it waited for a reply to the message was not read (see
  "Left out").

### The change and the runs

- **Hypervisor:** `~/m1n1-next` branch `m1power/hv-detached`, local commits on top of `5c696a89`,
  not pushed:
  - `be2bd182` (build `v2.0.0-147-gbe2bd182`, used by det35);
  - `c2d99a4e` (build `v2.0.0-148-gc2d99a4e`, used by det36 and det37).

  Off by default (`hv_hold_msg` = 0). With `hv_hold_msg` = V, a guest write of the 64-bit value V to
  `hv_hold_reg` (`0x23bc08800`, the mailbox's send word 0) through a traced or plain mapping is not
  done, and neither is the endpoint word at `+8` that sends it. `be2bd182` matched only two separate
  64-bit writes. macOS writes both words with one 128-bit store (both trace records carry the same
  PC), so det35 dropped nothing. `c2d99a4e` also drops a 128-bit store whose first word is V.
  - The trace event is still emitted (before the write), so the touch map / detached log shows the
    access.
  - Each drop is counted (`hv_hold_count`) and timed (`hv_hold_t[]`, CNTPCT), and while detached
    it is logged as kind 30 (`hold`, one record for each word).
  - `hv_hold_where` = 1 drops only after a detached real-S2R wake has re-entered the guest.
- **Host side** (lab, this commit):
  - `harness/real_s2r.py`: `real_s2r_on(hold_msg=, hold_reg=, hold_where=, hold_max=)`, and
    `hold_state()`, which prints the count and times;
  - `harness/detached_fmt.py`: kind 30 decoded as `hold`, with a test in
    `tests/core/test_hv_detached.py`.
- **Recipe:** round 10's det33 recipe, unchanged except for the hold:
  - `WD1=150 ALARM=90 FULL=0 S2R_TOUCH_TICK=250 S2R_TOUCH_SAMPLE=<the nine words>
    S2R_TOUCH_FULL=<pmp's two pages, both clusters' pages> S2R_ARGS='core_state=1, c4_probe=1,
    tick_ms=250, tick_words=[<the nine words>], hold_msg=0x0020e00000550000[, hold_where=1]'
    harness/macos-up.sh detNN`. The option is set at the arm, about 30 s into the guest.
    - In det33-det37 macOS sent the boot message at t 68.7-69.4. No boot message was sent before
      the arm (the boot logs from t 0).
  - Once `macos-up.sh` printed READY and the camera showed the login window: `full <det8's four
    pages>` into the control file. `pmp`'s mailbox page stays logged.
  - `PRE='hold_state("pre-detach")' + <awake_snap of commit-snap-list-r7.json>
    ARGS='commit_snap=<that list>' harness/detach135.sh detNN`.
  - `harness/detached-wake-readout.sh detNN 35`, then `harness/hv-reboot.sh` and
    `tools/tb/m1-pmu-dump`.
  - macOS went to its idle sleep by itself. Nobody clicked anything.

  The M1 was claimed as `observation` throughout and released at the end.
- **The no-hands way out, named before each run:**
  - the hypervisor's alarm at commit + 90 s;
  - watchdog 1 at commit + 150 s;
  - for a hang before the commit: the hypervisor's proxy over USB (`detach_readout.py --reboot`);
  - for a boot hang: the attached host and `hv-reboot.sh`.

  Every run ended without hands; the USB-C restart was not used.
- **Files (private):**
  - `tools/hv-trace-kit/runs/20261116-mac135/*-det35.*`, `*-det36.*`, `*-det37.*`;
  - `var/commit-state/r11-det3{5,6,7}-boot.txt`, `-pmp-boot.txt`, `-detached.txt`,
    `-pmp-detached.txt` (round 10's `r10_c3_series.py` and `r10_pmp_msgs.py`);
  - `r11-det36-window-447.txt`, `r11-det36-window-454.txt`, `r11-det36-wake-window.txt`,
    `r11-det37-wake-window.txt` (`r10_window.py`);
  - `r11-commit-diff-det35-det36.txt`;
  - `var/m1-state/pmu-20261119-013442-after-det35.txt`, `pmu-20261119-014908-after-det36.txt`,
    `pmu-20261119-020421-after-det37.txt`;
  - camera frames `var/m1-look/20261119-012013-*`, `-012310-*`, `-013828-*`, `-015346-*`,
    `-020439-*`.

| Run | Build, hold | Messages dropped (`hv_hold_count` / `hold` records) | Boot: words after the 0x55 send | Sleep | Wake: words after the 0x55 send |
|---|---|---|---|---|---|
| det35 | `-147`, every send (matched none) | 0 at the detach; no `hold` record | sent t 68.7922; n 251 (t 69.006): `0x333/0x444/0x222` | T 456.550 s after the detach; **asleep 89.62 s, woke at the alarm**; wake status `0 / 0x400000 / 0`; USB left/back 01:33:22.442 / :23.067 | sent t 546.6274; n 1824 (546.670): `0x333/0x444/0x222` |
| det36 | `-148`, every send | 1 at the detach (CNTPCT `0x8364241f`, 37.75 s after the arm); detached: t 454.2196 (entry) and 545.0880 (wake) | dropped t 69.3481; `0x444/0x444/0x444` to the end (t 192.3) | T 454.945; **asleep 89.66 s, woke at the alarm**; `0 / 0x400000 / 0`; USB 01:47:44.424 / :45.036 | dropped t 545.0880; n 1818 (545.110): `0x333/0x444/0x444`, to the end |
| det37 | `-148`, after the wake only | 0 at the detach; detached: t 540.3114 (wake) | sent t 68.6922; n 250 (t 68.764): `0x333/0x444/0x222` | T 449.676; **asleep 90.17 s, woke at the alarm**; `0 / 0x400000 / 0`; USB 02:02:57.375 / :57.988 | dropped t 540.3114; n 1797 (540.343): `0x333/0x444/0x444`, to the end |

All three read-outs were complete: 1,227,499 / 1,280,243 / 1,198,282 log entries were kept, 0
dropped. Each commit snapshot has 1328 words and 0 errors.

The power chip after each run (alarm wake, then `hv-reboot.sh`):
- `0x0201` `00` (row `0x0200` `20 00 …`);
- `0x9f04`-`0x9f0c` `48 00 01 3f ff ff 47 50 00`;
- `0xa47b`-`d` `00 08 00`;
- `0xd000` `01`.

These are det18's and det33's values.

### 1. Did the drop happen?

- **det36, boot:** `hold_state` at the detach read count 1, at CNTPCT `0x8364241f`. The touch map
  has macOS's 128-bit store of `0x0020e00000550000` / `0x20` at t 69.3481 (core 0, pc `…811258`).
  - The mailbox's A2I control word `0x23bc08110` read `0x28801` before that send (t 49.715), and
    the same `0x28801` just after it (t 69.348).
  - After each message that was sent, the next read of that word differs from the one before it.
    For example, in det37: `0x21101`, `0x22201`, `0x23301` around its sends at t 49.76-68.69.
- **det36 and det37, wake:** the detached log has a `hold` pair at each drop. The A2I control word
  read `0x24401` before and after the dropped send in both runs (det36 t 545.078 / 545.088; det37
  t 540.310 / 540.311).
- **det35:** count 0 at the detach and no `hold` record. The message went out at boot, at the entry
  (t 455.806) and at the wake (t 546.627). det35 is therefore a run without the drop: a third
  boot after det33 and det34b, and a second sleep and wake after det33.

### 2. Boot

| Step | det35 (sent) | det36 (dropped) | det37 (sent) |
|---|---|---|---|
| `pmp` started (`W 0x23bc00044` = `0x10`) | t 2.6683 | t 2.4570 | t 2.7039 |
| first change | n 5, t 3.257: 05c000 `0x666`->`0x444`, 060000 `0x333`->`0x444` | n 7, t 3.754: 05c000 `0x666`->`0x555` (`0x444` from n 10, t 4.504), 060000 `0x333`->`0x444` | n 6, t 3.754: 05c000 `0x666`->`0x555` (`0x444` from n 11), 060000 `0x333`->`0x444` |
| t 4-68 | `0x444/0x444/0x444` with one-sample rises of the first two words | the same | the same |
| `0x0020e00000550000` | sent, t 68.7922 | **dropped**, t 69.3481 | sent, t 68.6922 |
| next sample | n 251, t 69.006: **`0x333/0x444/0x222`**; `ps_PMP` and `ps_PMS_SRAM` `0x1000030f` | n 251-276 (t 69.3-75.8): **`0x444/0x444/0x444`**; `ps_PMP` `0x1f0f03ff`, `ps_PMS_SRAM` `0x1f0003ff` | n 250, t 68.764: **`0x333/0x444/0x222`**; `0x1000030f` |
| samples t 70 to the full switch | 452 (to t 185.3): 058000 `0x333` in all; 060000 `0x222` in all; `ps_PMP` `0x1000030f` in 394, `0x1f0f03ff` in 58 | 481 (to t 192.3): 058000 `0x444` 480 (`0x555` 1); 05c000 `0x444` 476; **060000 `0x444` in all 481; `ps_PMP` `0x1f0f03ff` in all; `ps_PMS_SRAM` `0x1f0003ff` in all**; `pmp` +`0x44` `0x10` in all | 495 (to t 196.8): 058000 `0x333` 492; 060000 `0x222` in all; `ps_PMP` `0x1000030f` in 347 |

`ps_PMS` read `0x1f0002ff` in every boot sample after t 70 in all three runs. `ps_DCS0` alternated
in all three. In det36's whole boot (734 samples) 058000 read `0x444` (726) or `0x555` (8), 060000
`0x333` (6, before the first change) or `0x444` (728).

### 3. Idle and entry (detached clock, 250 ms)

| | det35 (sent) | det36 (dropped) | det37 (sent until the wake) |
|---|---|---|---|
| samples, detach to the last core | 1821 | 1815 | 1794 |
| 058000 | `0x333` 1812, `0x444` 8, `0x555` 1 | `0x444` until t 447.533; **`0x333` from t 447.783** (29 samples, to the commit) | `0x333` 1789, `0x444` 5 |
| 060000 | `0x222` in all | `0x444` until t 454.303; **`0x222` from t 454.553** (2 samples, to the commit) | `0x222` in all |
| `ps_PMP` / `ps_PMS_SRAM` | `0x1000030f` in 1336 / 1336 | `0x1f0f03ff` / `0x1f0003ff` in all 1815 | `0x1000030f` in 1238 / 1236 |
| endpoint-`0x20` messages at the entry | `0x0020e00000540000` (t 449.21); `…540001`, `…550001`, `0x0020800000630000` (455.77); `…540000`, **`…550000` sent** (455.806) | `…540000` (447.654); `…540001`, `…550001`, `0x0020800000630000` (454.20-454.21); `…540000` (454.2189), **`…550000` dropped** (454.2196) | `…540000` (442.34); `…550001`, `…540001`, `0x0020800000630000` (448.90-448.91); **`…550000` sent** (448.917), `…540000` (448.925) |
| `pmp` stopped (`W 0x23bc00044` = 0) | t 456.12 | t 454.512 | t 449.251 |
| commit snapshot: words, `ps_PMP` | `0x333/0x444/0x222`, `0x1f0f03ff` | `0x333/0x444/0x222`, `0x1f0f03ff` | `0x333/0x444/0x222`, `0x1f0f03ff` |

det36, the two changes:
- **058000 `0x444` -> `0x333`** between n 1786 (t 447.533) and n 1787 (t 447.783). In that window,
  `pmp`'s mailbox carried two endpoint-4 exchanges (`0x0040000000000000`, t 447.561 and 447.622)
  and one endpoint-`0x20` message, **`0x0020e00000540000`** at t 447.6545. The other pages accessed
  are listed in `r11-det36-window-447.txt`.
  - *Documentation, not an observation:* `0x54` is DISP0_FE's id in the ADT's power-manager table
    (round 10).
- **060000 `0x444` -> `0x222`** between n 1813 (t 454.303) and n 1814 (t 454.553). In that
  window, with no endpoint-`0x20` message (`0x55` had been dropped at 454.2196, before n 1813):
  - endpoint-0 management `0x00b0000000000201`, `0x0060000000000201` / `RECV 0x0070000000000201`
    (t 454.5115-454.5120);
  - `W 0x23bc08114` = `0x2ff00`;
  - `R 0x23bc00048` = `0x2e`, `R 0x23bc00044` = `0x10`, `W 0x23bc00044` = 0 (t 454.5120);
  - other pages (`r11-det36-window-454.txt`).

  In the same sample `pmp` +`0x44` read 0 and +`0x48` `0x2e`.

The commit snapshots of det35 and det36 (1328 words each) differ in 23 words
(`r11-commit-diff-det35-det36.txt`). None of them is one of the three words, `ps_PMP`, `ps_PMS_SRAM`
or `pmp`'s. The ones that differ are:
- DCS4-7's power-state words;
- MCC `+0x680`/`+0x684` on all four planes;
- six power-gate page words (`0x23b71c0f0`, `0x23b71c104`, `0x23b71c108`, `0x23b71c11c`,
  `0x23b71c120`, `0x23b71c134`);
- `0x23b700030`/`0x23b700038`;
- the three watchdog counts.

### 4. Sleep and wake

- **Asleep:** last core to wake entry 89.62 s (det35), 89.66 s (det36), 90.17 s (det37). The wake
  status was `0 / 0x400000 / 0` in all three.
- **The wake snapshot and first sample, the same in all three:**
  - the words `0x333/0x555/0x333`;
  - `ps_PMP` `0xf0003ff`, `ps_PMS_SRAM` `0xf000300`, `ps_PMS` `0xf0002ff`;
  - `pmp` +`0x44` 0, +`0x48` `0x2a`.

  The wake snapshots of det35 and det36 (264 words) differ only in DCS0-2 and DCS4-7's power-state
  words.
- **Second sample:** `ps_PMP` / `ps_PMS_SRAM` / `ps_PMS` `0x1f0003ff` / `0x1f0003ff` / `0x1f0002ff`;
  the words are unchanged.
- **`pmp` restarted** (`W 0x23bc00044` = `0x10`) 0.35 s after the wake entry in all three: t 546.513
  (det35), 544.9586 (det36), 540.1892 (det37). The endpoint-0 handshake follows.
- **Endpoint `0x20`**, in the same order in all three: `…630001`, `…540001`, `…550001`,
  `…540000`, `…550000`. The last two are 0.8 ms (det35), 10.3 ms (det36) and 1.8 ms (det37) apart:
  - det35: `…550000` sent at 546.6274;
  - det36: dropped at 545.0880;
  - det37: dropped at 540.3114.
- **The next sample** (22-42 ms after `…550000`):
  - det35 (n 1824, 546.670): **`0x333/0x444/0x222`**;
  - det36 (n 1818, 545.110) and det37 (n 1797, 540.343): **`0x333/0x444/0x444`**, with `pmp`
    +`0x44` `0x10` and `ps_PMP` `0x1f0f03ff`.

  In det36 and det37, 05c000 `0x555` -> `0x444` and 060000 `0x333` -> `0x444` came in that one
  sample.
- **To the read-out** (35 s, 143 samples after the wake entry):

  | | det35 | det36 | det37 |
  |---|---|---|---|
  | 058000 | `0x333` (all 143) | the same | the same |
  | 05c000 | `0x444` (141), `0x555` (2) | the same | the same |
  | 060000 | `0x222` (141) | `0x444` (141) | `0x444` (141) |
  | `ps_PMP` | `0x1000030f` (112) | `0x1f0f03ff` (141), never `0x1000030f` | as det36 |
  | `ps_PMS_SRAM` | `0x1000030f` (112) | `0x1f0003ff` (142), never `0x1000030f` | as det36 |

- The window from the sample before the change to the sample after it is listed in
  `r11-det36-wake-window.txt` and `r11-det37-wake-window.txt`.

### Left out, and why

- **A delayed send:** not run. The message was dropped, not held and sent later, so whether the
  words and `ps_PMP` move when it arrives late is not read.
- **Whether `pmp` itself or something that `pmp` drives writes the words:** not read. These runs
  show the order of events with the message present or absent, nothing more:
  - **Message absent:**
    - 060000 did not go to `0x222` while `pmp` ran (boot, idle, wake). In det36's entry it went
      to `0x222` once `pmp` was stopped.
    - 058000 went to `0x333` after `0x0020e00000540000` (det36 idle). After the wake it read
      `0x333` from the first sample, before any message.
    - `ps_PMP` and `ps_PMS_SRAM` never read `0x1000030f`.
  - **Message present:** these readings came in the first 250 ms sample after it. Round 10 and
    this round together have that for three boots and two wakes.
- **The drop at the entry only:** not run. det36 dropped at boot, entry and wake together. det37
  dropped at the wake only.
- **A reply to the message:** `pmp`'s receive side (`R 0x23bc08830`/`838`) was logged in full. Its
  traffic around the drops was not compared with det35's beyond the windows listed above.
- **The macOS console (`vuart-det3*.log`):** not read for this round.
- **det35's first build** dropped nothing (the 128-bit store). Its readings are used here as a
  run with the message sent.
- **The camera** was looked at at each boot (login window in det35-det37) and before and after
  the round. It was not looked at during the sleeps; the sleeps are read from the log and USB.

### M1 left

In stock Omarchy (kernel `7.3.0-0test5-1-ARCH`, up since 2026-11-19 02:03:56), reached over
Thunderbolt. The camera frame `var/m1-look/20261119-020439-state-after-round11.jpg` shows the
desktop. The claim is released. On the M3, the three FIFO holders (`sleep 7200`) that this
round's `macos-up.sh` runs had left were stopped by pid. One from 00:38 (pid 58327, round 10)
was left running.

## ds21: every candidate together reaches the commit; the C3 record; the watchdog under the test command line (2026-11-19 02:54-03:05)

Readings only. Spec at lab `f411b43` (D8 (a), (b), (f); open questions 74, 81).

### The two runs

Kernel ds21 (kernel tree `a1688faaf`: logic `ae983f3` plus glue round 3; package
`var/kernels/ds21/kernel.tar.zst`, sha256 `8d4a5849...4c583402`, re-checked before Part 2),
command line `var/deepsleep/ds21.cmdline` (`panic=10 systemd.watchdog_sec=0
apple_deepsleep.enable=1 apple_deepsleep.alarm_secs=60 no_console_suspend
apple_deepsleep.wdt=30`), cable and charger in. Each run `tools/tb/m1-cand-runs`: stock kernel,
ds21 booted once, `cand` set to the mask, `real.sh` started; the outcome is the first answer
(polled from 15 s after the start). Rows in `var/commit-walk/ds21-cand.tsv` (private). `cand` bit
n is Cn (`0x3fffe` = C1-C17; C18 is bit 18 and was off; `0x1020` = C5 and C12). On the ds21 boot
of Part 2 below, the module's parameters read `snap=0`, `probe=N`, `trace=N`, `wdt=30` (the walk
is not on this command line), so by D8 (b) the commit-point step's record is the C3 record when
`cand_c3` is on and 'W' otherwise.

| Mask | Ended | Outcome | Record `0x9f04`-`0x9f0d` | `0x0201` | fault shadow `0xa47b`-`d` |
|---|---|---|---|---|---|
| `0x3fffe` (C1-C17) | 02:55:52 | RESET, first answer on the stock kernel 63 s after the start | `44 56 64 43 36 64 f3 00 00 00` | `00` | `00 08 00` |
| `0x1020` (C5, C12) | 02:57:46 | RESET, 62 s | `44 57 00 40 2c 3d 02 30 58 00` | `00` | `00 08 00` |

**Record 1, `0x3fffe` (`cand_c3` on): the C3 record, decoded by D8 (f).**
- Byte 0 `0x44` = 'D' (the glue's layout). Byte 1 `0x56` = 'V': the record's letter, the glue's
  (D8 (f) does not name it; no lab document names 'V'). It is read as the C3 record because
  `cand_c3` was on and none of `snap=2`, the walk or `probe=1` was set (D8 (b)).
- Bytes 2-6 hold the nine 4-bit codes, slot s in byte 2 + s/2, the **low nibble for an even s,
  the high nibble for an odd s**:

  | Byte | Value | Low nibble -> slot | High nibble -> slot |
  |---|---|---|---|
  | 2 | `0x64` | 4 -> slot 0 | 6 -> slot 1 |
  | 3 | `0x43` | 3 -> slot 2 | 4 -> slot 3 |
  | 4 | `0x36` | 6 -> slot 4 | 3 -> slot 5 |
  | 5 | `0x64` | 4 -> slot 6 | 6 -> slot 7 |
  | 6 | `0xf3` | 3 -> slot 8 | `0xf` = no slot coded `0xe` |

- Code d (0..`0xd`) = the value read was exactly d x `0x111`. Bytes 7-9 `00 00 00`, as D8 (f)
  gives when no slot is coded `0xe`.
- The nine values (slots in D8 (a)'s order; `0x23b058000`, `0x23b05c000`, `0x23b060000` at each
  place):

  | Place | `0x23b058000` | `0x23b05c000` | `0x23b060000` |
  |---|---|---|---|
  | (i) entry start, slots 0-2 | `0x444` | `0x666` | `0x333` |
  | (ii) after R22's trigger, slots 3-5 | `0x444` | `0x666` | `0x333` |
  | (iii) after R38's third write, slots 6-8 | `0x444` | `0x666` | `0x333` |

  **All nine were read** (no code `0xf`) and every one has the
  d x `0x111` form; none was "not read". The bytes are exactly D8 (f)'s own example for
  "Linux's values at all three places" (`64 43 36 64 f3 00 00 00`), the values Linux reads awake
  (L27). macOS at the commit reads `0x333`/`0x444`/`0x222` (8.2 C3), which would have given
  `43 32 24 43 f2 00 00 00`.
- Since the C3 record is made only at the commit-point step (D8 (b), (f)), finding it says the
  commit point was reached.

**Record 2, `0x1020` (`cand_c3` off): 'W', in the layout the earlier records of this file use.**
That layout, as decoded above (ds3 `44 c5 00 40 02 00 02 10 63 00`, ds10 'P', ds17 'W', ds20
'T'): byte 0 'D'; byte 1 the reason letter (bit 7 = SError pending); bytes 2-6 the last
access's address, little-endian (40 bits); byte 7 the access's kind and core (`0x10` decoded as
"32-bit read by core 0" (kind 1), `0x30` as "32-bit write by core 0"); bytes 8-9 the access
count's low 16 bits, little-endian. The split of byte 7 into kind and core fields is not written
out in this file; every decoded example has core 0.
- Byte 0 `0x44` 'D'; byte 1 `0x57` = 'W', bit 7 clear (no SError pending).
- Bytes 2-6 `00 40 2c 3d 02` -> `0x0023d2c4000`: the last access is to `0x23d2c4000`.
- Byte 7 `0x30`: a 32-bit write by core 0.
- Bytes 8-9 `58 00` -> count low 16 bits `0x0058` (88).
- So: the commit point was reached, the last access before the record a 32-bit write of
  `0x23d2c4000` by core 0, the same as every 'W' since ds17 (L17, L25, L26). Bytes 2-7 are equal
  to ds20's 'W' records; byte 8 differs (ds20: `0x8c`-`0xde` alone, `0xa0` with `0x3ffd6`;
  ds17: `0x7e`-`0x81`). What the count's value means across kernels is not read here.

**Against ds20** (`var/commit-walk/ds20-cand.tsv`; "Runs ds20, candidate switches one at a
time", L25, L26):

| | ds20 | ds21 |
|---|---|---|
| C3 | alone (`0x8`): DARK 246 s, record 'a' only (commit not reached), power button | with C1-C17 (`0x3fffe`): commit reached (C3 record), RESET 63 s |
| C5 | alone (`0x20`): DARK 247 s, 'T' on a 32-bit read of `0x23b7001c0` (SIO_BUSIF), power button | with C12 (`0x1020`): commit reached ('W'), RESET 62 s |
| Others | C1, C4, C8, C9, C10, C13, C15, C17 alone and `0x3ffd6` together: RESET 62-63 s, 'W' | (not run) |
| `0x0201` after a RESET | `04` | `00` |
| fault shadow after a RESET | `0x000c00`; `0x001c00` after `0x3ffd6` | `0x000800` (bit 11 `wdog,reset_in_1` only) |

The two kernels differ in both logic (`713a453` against `ae983f3`) and glue, and the ds21 runs
set C3 and C5 together with other candidates, not alone; these rows do not say which of those
differences let the entry reach the commit. `0x0201` read `00` after hypervisor round 11 (its
last reading before these runs, at about 02:04) and `00` after both runs; by the lab's decode of
macOS's always-on sleep program a sleep entry writes `01`. Not read between 02:04 and the first
run.

**Camera frames.** `var/m1-look/20261119-025550-state-now.jpg` and
`var/m1-look/20261119-025745-state-now.jpg`, taken by `m1-cand-runs` after the M1 had answered
on the stock kernel: both show the M1's screen lit with the Omarchy desktop (the wallpaper, the
top bar; the bar's clock reads about 02:55 and 02:57). They show the state after the reset, not
during the sleep. A frame at 02:59:25 (`var/m1-look/20261119-025925-state-now.jpg`, before Part
2) shows the same desktop.

**What these runs do not show.**
- Whether the SoC began its power-down after the commit: no trace, no snapshot, no time of the
  M1's port dropping, no M3-side log in the rows. That the M1 answered on the stock kernel about
  62-63 s after the start, with the fault shadow's bit 11 alone, is what ds20's RESET rows also
  read; it does not say whether the chip powered down before the reset.
- Whether the reset was watchdog 1's bite at `wdt=30` or another reset: the fault shadow names
  bit 11 `wdog,reset_in_1`; the time of the reset itself (as against the first answer) is not
  read.
- C5's four reads (PMS, SIO_BUSIF, SIO, SIO_CPU right after C12's last turn-on; open question
  74): the 'W' record does not carry them, so in `0x1020` it is not read in which state C5 found
  its parents, nor whether it lowered the twelve domains or skipped them by its gate. The same in
  `0x3fffe`.
- Which candidates acted in `0x3fffe` beyond C3's reads: no record carries them.
- Whether the C3 words moved between the reads, or after place (iii): the record holds three
  readings per word; all equal.

### Watchdog reads (open question 81, read-only, no sleep started, no `/dev/mem`)

Claim `obs-ds21` taken 02:59, released 03:05. Raw outputs kept in the session only.

| Read | Stock (`7.3.0-0test5-1-ARCH`, up 02:57:25, Omarchy's own command line) | ds21 (`7.2.11-ds21`, up 03:00:22, ds21's command line) |
|---|---|---|
| `/sys/class/watchdog/` | `watchdog0` -> `/sys/devices/platform/soc/23d2b0000.watchdog/watchdog/watchdog0` | `watchdog0` -> `/sys/devices/virtual/watchdog/watchdog0` (no `device` link) |
| Files in `watchdog0/` | `dev`, `device`, `power`, `subsystem`, `uevent` | `dev`, `power`, `subsystem`, `uevent` |
| `state`, `timeout`, `bootstatus`, `identity`, `hw_running`, `timeleft`, `nowayout` | **do not exist** (`CONFIG_WATCHDOG_SYSFS` is not set) | **do not exist** (same) |
| Driver bound to `/soc/watchdog@23d2b0000` (`apple,t8103-wdt`) | `apple-watchdog`, module `apple_wdt` (built in) | `apple-watchdog`, module `apple_wdt` (built in) |
| `/dev/watchdog`, `/dev/watchdog0` | `10,130`, `248,0` | `10,130`, `248,0` |
| Kernel config | `WATCHDOG_CORE=y`, `APPLE_WATCHDOG=y`, `WATCHDOG_HANDLE_BOOT_ENABLED=y`, `WATCHDOG_OPEN_TIMEOUT=0`, `WATCHDOG_NOWAYOUT` not set, `WATCHDOG_SYSFS` not set | the same (and `SOFT_WATCHDOG=m`, not loaded) |
| `watchdog` module parameters | `handle_boot_enabled=Y`, `open_timeout=0`, `stop_on_reboot=-1` | the same |
| `systemctl show` | `WatchdogDevice=/dev/watchdog0`, `RuntimeWatchdogUSec=30s`, `RebootWatchdogUSec=2min`, `RuntimeWatchdogPreUSec=0`, `KExecWatchdogUSec=0` | `WatchdogDevice=` (empty), `RuntimeWatchdogUSec=0`, `RebootWatchdogUSec=0`, `RuntimeWatchdogPreUSec=0`, `KExecWatchdogUSec=0` |
| Where the 30 s / 2 min come from | `/etc/systemd/system.conf.d/90-maclab-watchdog.conf` (`RuntimeWatchdogSec=30s`, `RebootWatchdogSec=2min`; no package owns it) | the same file is present; `systemd.watchdog_sec=0` on the command line; the values read 0 |
| Journal "Watchdog"/"watchdog" lines, this boot | kernel `watchdog: NMI not fully supported`, `watchdog: Hard watchdog permanently disabled` (the lockup detector); systemd `Using hardware watchdog /dev/watchdog0: 'Apple SoC Watchdog', version 0.` and `Watchdog running with a hardware timeout of 30s.` (02:57:31); boltd `watchdog: enabled [pulse: ...]` (boltd's own systemd service watchdog) | kernel the same two lockup-detector lines; boltd the same; **no systemd hardware-watchdog line** |
| Holders of `/dev/watchdog*` (every `/proc/*/fd`) | pid 1 `systemd`, fd 15 -> `/dev/watchdog0` (again after the return at 03:04) | **none** |

- Identity: on stock, systemd's line names it "Apple SoC Watchdog", version 0; on ds21 not read
  (no sysfs file, and the device was not opened, since opening it starts it).
- Whether the hardware watchdog was running on ds21 (`hw_running`) is not read: no sysfs file
  and no `/dev/mem` read in this part. On ds21 no process holds the device and systemd reports no
  runtime or reboot watchdog.
- The device node is `23d2b0000.watchdog`: the same block as the spec's watchdog-1 words
  `0x23d2b0014`, `0x23d2b001c`. Which of those words `apple_wdt` programs is not read here.
- On ds21 the journal's kernel lines are stamped Nov 10 20:09 (the clock before it was set at
  boot).

### Left out

- Open question 81's `0x23d2b0014`, `0x23d2b001c` over `/dev/mem` (excluded from this part),
  `hw_running` (no such file), and its second part (a `wdt` run taking the exception on
  purpose).
- Open question 74 (C5's four reads): needs a record that carries them; not in ds21's 'W'.

### M1 left

`systemctl reboot` from ds21 at 03:04:02; stock Omarchy (`7.3.0-0test5-1-ARCH`, up since
03:04:18) answered on Thunderbolt at 03:04:40, with systemd holding `/dev/watchdog0` and
`RuntimeWatchdogUSec=30s` again. The frame `var/m1-look/20261119-030454-state-now.jpg` shows the
desktop. ds21's kernel stays on the ESP under `s2r/ds21` (as `m1-bootonce` leaves it); the
default boot entry is untouched. The claim is released.

## Linux round: the pmp client at boot (ds22p, cand 0x40000) (2026-11-19 03:44-03:50)

Readings only, on bare metal, boot only: no sleep and no `pm_test` were started. The M1 was
claimed as `linux-obs-pmp` and driven over Thunderbolt. Registers were read over `/dev/mem`,
32-bit, `O_RDONLY` and `PROT_READ`, with the same eleven addresses as the round "Linux round: pmp
and the endpoint-0x20 message". `pmp`'s mailbox FIFOs were not read. Nothing was written to any
of these registers. The driver's and the client's source were not read. Raw output (private):
- `var/commit-state/linux-pmp-client-ds22p-20261119.txt` (steps 1, 3 and 4);
- `var/commit-state/linux-pmp-client-ds22p-dmesg-20261119.txt` (ds22p's full `dmesg`).

**Short answer.** The client bound, mapped four buffers and then waited 6 s for `pmp`'s word
`0x000200000023b549`, which did not come. The client then logged that it had stopped `pmp`'s
mailbox and given PMP and PMS_SRAM back to genpd. From 39 s after boot onward, `pmp` +`0x44` read
`0x0`, as on the stock kernel. The three words stayed `0x444/0x666/0x333` in every sample. Four
words differ from the stock kernel: `pmp` +`0x48`, both mailbox control words and `ps_PMP`. No
reading was taken during the client's 6 s window.

### 1. Stock kernel, before (03:44:50)

- `7.3.0-0test5-1-ARCH`, up since 03:04:17. The camera frame
  `var/m1-look/20261119-034425-state-linuxobs-pmp-start.jpg` shows the Omarchy desktop.
- `apple_pmp` **is loaded** (`98304 2 appledrm,aurora`), as in the earlier round, with no device
  under `/sys/bus/platform/drivers/apple_pmp/` (only `bind`, `module`, `uevent`, `unbind`).
  `apple_pmp_v1` is not loaded. `dmesg` has no line containing `pmp`.
- genpd: `pmp` on, `pms` on, `pms_busif` on, `pms_sram` `off-0`, `pms_fpwm0`-`4` `off-0`.

| Word | 03:44:50 |
|---|---|
| `0x23b058000` / `0x23b05c000` / `0x23b060000` | `0x444` / `0x666` / `0x333` |
| `pmp` +`0x44` / +`0x48` | `0x0` / `0x2a` |
| mailbox A2I `0x23bc08110` / I2A `0x23bc08114` | `0x20001` / `0x20001` |
| `ps_PMP` `0x23b7003d8` | `0x1f0000ff` |
| `ps_PMS_SRAM` `0x23b7003e0` | `0x0f000300` |
| `ps_PMS` `0x23b700140` | `0x1f0000ff` |
| `ps_DCS0` `0x23b700300` | `0x1f0002ff` |

These are the 01:10:54 values of the earlier round, word for word.

### 2. The boot

`tools/tb/m1-bootonce var/kernels/ds22p/kernel.tar.zst ds22p var/deepsleep/ds22p.cmdline` at
03:45:07. The kernel `7.2.11-ds22p` was up since 03:45:22 and answered on Thunderbolt by 03:45:54.
Nothing was frozen, and `m1-reboot.sh` was not used.
- Command line extra words: `panic=10 systemd.watchdog_sec=0 apple_deepsleep.enable=1
  apple_deepsleep.alarm_secs=60 no_console_suspend apple_deepsleep.cand=0x40000`.
- Module parameters read back: `cand=262144` (`0x40000`), `enable=Y`, `wdt=0`, `alarm_secs=60`,
  `dump=N`, `probe=N`, `trace=N`, `snap=0`.
- The camera frame `var/m1-look/20261119-034850-state-linuxobs-pmp-ds22p.jpg` shows the Omarchy
  desktop.

### 3. ds22p: the client's log, complete

Every `dmesg` line of the boot from `apple-deepsleep` or `apple-deepsleep-pmp`, in order. There
are no others.
```
[    0.067774] apple-deepsleep: cores: logical CPU of cores 0-7 (MPIDR 0-3, 10100-10103): 0 1 2 3 4 5 6 7
[    0.067782] apple-deepsleep: mailbox at 0x0000000803c50a40: version 1, 8 cores, loader reset vector 0x803b80000, 0 resumes so far
[    0.069009] apple-deepsleep: pmp: C18: nodes for pmp, its mailbox and its translator added; the client boots at its probe
[    0.069012] apple-deepsleep: enabled: mem_sleep "deep" sleeps through the tested logic; power chip /soc/spmi@23d0d9300/pmic@f; alarm +60 s
[    0.069166] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 16384 bytes at IOVA 0x4000 (bus 0x000000081173c000)
[    0.069302] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 65536 bytes at IOVA 0xc000 (bus 0x0000000806100000)
[    0.069313] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 16384 bytes at IOVA 0x20000 (bus 0x000000080e228000)
[    0.069413] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 65536 bytes at IOVA 0x28000 (bus 0x0000000806110000)
[    6.105254] apple-deepsleep: pmp: boot: a wait ran out, for 0x000200000023b549; 0 received messages dropped, 0 sends failed, 0 accesses refused (first 0x0)
[    6.105316] apple-deepsleep-pmp 23bc00000.coprocessor: pmp not running: mailbox stopped, PMP and PMS_SRAM given back to genpd
```
- Between `0.069413` and `6.105254` the kernel logged other drivers' lines (iommu groups,
  `simpledrm`, "genpd: Disabling unused power domains" at `0.162310`, "Freeing initrd memory" at
  `0.190076`), and nothing from the client. The client's next lines come immediately before
  "Freeing unused kernel memory" and `Run /init`.
- **Step by step, what was and was not logged:**

  | Step | Logged |
  |---|---|
  | DT nodes for `pmp`, mailbox and translator | yes (`0.069009`) |
  | power domains (PMP, PMS_SRAM) on | no line; only the final "given back to genpd" |
  | SRAM block | no line |
  | translator (DART) setup | no line beyond the node line; four buffer lines (IOVA `0x4000`, `0xc000`, `0x20000`, `0x28000`) |
  | start (+`0x44`) | no line |
  | endpoint 0 handshake, endpoints 1-3 | no line |
  | endpoint `0x20` opening | the wait for `0x000200000023b549` ran out (`6.105254`) |
  | endpoint-`0x20` `0x55` word | no line (not reached, by the log's own order) |
  | refused accesses | `0 accesses refused (first 0x0)`; `0 sends failed`; `0 received messages dropped` |

  In macOS's capture (sections above), `0x000200000023b549` is the word `pmp` sends on endpoint
  `0x20` after macOS's `SEND 0x000100000003c000`.
- No line in this boot contains `SError`, `Internal error`, `Unable to handle`, a DART fault, or
  `timeout` other than the client's own "wait ran out". The `asahi` GPU driver logs
  `MMU: IO map: 0x23bc00000:0x4000` at `6.369223`, after the client's last line.
- `journalctl -k -b -p warning` has the client's two lines at `6.105`, and none other from it.

**Devices and drivers on ds22p (03:46):**
- DT nodes added:
  - `soc/coprocessor@23bc00000`: compatible `apple,t8103-pmp-deepsleep-c18`, no `status`. Its
    `reg` is `ctrl` `0x23bc00000`+`0x10000`, `sram` `0x23b500000`+`0x80000` and `dart`
    `0x23b300000`+`0x4000`. It has no `mboxes`, `iommus` or `power-domains` property.
  - `soc/mailbox@23bc08000`: `apple,t8103-asc-mailbox`, `apple,asc-mailbox-v4`, no `status`;
    interrupts AIC 511-514.
  - `soc/iommu@23b300000`: `apple,t8103-dart`, `status = "disabled"`.
- Bound devices:
  - `23bc00000.coprocessor` is bound to `apple-deepsleep-pmp`. It has a device link to supplier
    `23bc08000.mailbox`, and its runtime PM status reads `unsupported`.
  - `23bc08000.mailbox` is bound to `apple-mailbox`.
  - No device at `0x23b300000` is bound to `apple-dart`.
- `apple_pmp` **is loaded** (`49152 1 asahi`). Its aliases are `apple,t6000-pmp-v2` and
  `apple,t8140-pmp-v2`, and no device is bound to it. `apple_pmp_v1` is not loaded (the file
  `apple-pmp-v1.ko` exists).
- genpd after the client gave up: `pmp` on, `pms` on, `pms_busif` on, `pms_sram` `off-0`,
  `pms_fpwm0`-`4` `off-0` (as on the stock kernel).

### 4. ds22p: the words, once a second

First sample at 03:46:01 (39 s after boot, about 33 s after the client's last line). Then 120
samples at 1 s, 03:46:38-03:48:37. **0 changes**: all 121 samples read:

| Word | ds22p (every sample) | Stock, step 1 | macOS (round 10, det33/34b) |
|---|---|---|---|
| three words | `0x444/0x666/0x333` | same | `0x444/0x444/0x444` from n 5 (t 3.0), `0x333/0x444/0x222` after the `0x55` word |
| `pmp` +`0x44` | `0x0` | same | `0x10` from n 4 (t 2.76) |
| `pmp` +`0x48` | **`0x8`** | `0x2a` | `0x2a` before the start; `0x0c`/`0x2c` at n 4; `0x2e` after the stop at entry |
| A2I `0x23bc08110` | **`0x107801`** | `0x20001` | not in the sampled set |
| I2A `0x23bc08114` | **`0x26600`** | `0x20001` | macOS writes `0x22200` at the entry's stop (t 447.85) |
| `ps_PMP` | **`0x1f0f00ff`** | `0x1f0000ff` | `0x1f0f00ff` at n 4; `0x1f0f03ff` / `0x1000030f` later |
| `ps_PMS_SRAM` | `0x0f000300` | same | `0x1f0000ff` at n 4; `0x1000030f` after the `0x55` word |
| `ps_PMS` | `0x1f0000ff` | same | `0x1f0000ff` at n 4; `0x1f0002ff` at n 5 |
| `ps_DCS0` | `0x1f0002ff` | same | |

- **First sample that differs from step 1:** the first one, 03:46:01. The four bold words differ;
  the three words, +`0x44`, `ps_PMS_SRAM`, `ps_PMS` and `ps_DCS0` do not.
- **Against macOS:** no sample reaches `0x444/0x444/0x444`, +`0x44` `0x10` or `ps_PMS_SRAM`
  `0x1000030f`. `ps_PMP` reads `0x1f0f00ff`, the value macOS's sample n 4 read. `+0x48` `0x8` is
  none of the values read under macOS above.
- What the four changed words held during the client's 6 s (0.07-6.1 s after kernel start): not
  read.

### 5. Stock kernel, after (03:49:48)

`systemctl reboot` from ds22p at 03:49:06. Stock `7.3.0-0test5-1-ARCH`, up since 03:49:21,
answered on Thunderbolt at 03:49:41.
- The eleven words read exactly as in step 1: `0x444/0x666/0x333`, +`0x44` `0x0`, +`0x48` `0x2a`,
  A2I/I2A `0x20001`/`0x20001`, `ps_PMP` `0x1f0000ff`, `ps_PMS_SRAM` `0x0f000300`, `ps_PMS`
  `0x1f0000ff`, `ps_DCS0` `0x1f0002ff`.
- genpd `pms_sram` `off-0`, `pmp` on, `pms` on. No `coprocessor@23bc0…` node. `apple_pmp` loaded
  (`98304 2 appledrm,aurora`).
- The camera frame `var/m1-look/20261119-034950-state-linuxobs-pmp-end.jpg` shows the desktop.

### Left out

- Readings during the client's 6 s boot window: none (the first read was 39 s after boot).
- What the client wrote to +`0x44`, the SRAM, the DART or the mailbox: the client logs no line for
  these steps, and its source was not read.
- `pmp`'s SRAM (`0x23b500000`-`0x23b57ffff`, incl. `0x23b549000`), the DART's registers and the
  mailbox FIFOs: not read.
- Whether `pmp` ran at all during the window, or its CPU was started, cannot be told from these
  readings.

### M1 left

In stock Omarchy (`7.3.0-0test5-1-ARCH`, up since 03:49:21), reached over Thunderbolt. The
default boot entry is untouched. ds22p's kernel stays on the ESP under `s2r/ds22p`, and its
modules under `/usr/lib/modules/7.2.11-ds22p` (as `m1-bootonce` leaves them). The reader script
copied to `/root` was removed. The claim is released.

## Linux round: the pmp client at boot, second build (ds23p) (2026-11-19 04:10-04:15)

This round repeats the ds22p round (section above) with the client's next build: package
`var/kernels/ds23p/kernel.tar.zst`, kernel `7.2.11-ds23p`. Its command line `var/deepsleep/
ds23p.cmdline` is byte for byte ds22p's (`apple_deepsleep.enable=1 apple_deepsleep.cand=0x40000`,
`alarm_secs=60`, no `wdt`, `systemd.watchdog_sec=0`, `panic=10`). The parameters read back the
same.
- Boot only: no sleep, no `pm_test`.
- The same eleven words, read with the same read-only 32-bit `/dev/mem` reader; each sample now
  also carries `/proc/uptime`. The reader was piped over ssh and nothing was copied to the M1.
- Claimed as `linux-obs-pmp`. The driver's and the client's source were not read.
- Raw output (private): `var/commit-state/linux-pmp-client-ds23p-20261119.txt` and
  `var/commit-state/linux-pmp-client-ds23p-dmesg-20261119.txt`.

**Short answer.** `pmp` did not answer. As with ds22p, the client's 6 s wait for
`0x000200000023b549` ran out. This time the probe failed with `-110` and left no driver bound,
where ds22p's client stayed bound.
- The domains now attach through the node's `power-domains`, and `pms_sram` stays **on**
  (`ps_PMS_SRAM` `0x1f0000ff`; ds22p: `off-0`, `0x0f000300`).
- The other ten words are ds22p's values in every sample, from 23.4 s after kernel start to
  155 s. The three words never moved from `0x444/0x666/0x333`.

### 1. Stock kernel, before (04:10:16)

- `7.3.0-0test5-1-ARCH`, up since 03:49:21. The frame
  `var/m1-look/20261119-041013-state-linuxobs-ds23p-start.jpg` shows the Omarchy desktop.
- The eleven words read exactly as in the ds22p round's steps 1 and 5:
  - the three words `0x444/0x666/0x333`;
  - +`0x44` `0x0`, +`0x48` `0x2a`;
  - A2I/I2A `0x20001`/`0x20001`;
  - `ps_PMP` `0x1f0000ff`, `ps_PMS_SRAM` `0x0f000300`, `ps_PMS` `0x1f0000ff`, `ps_DCS0`
    `0x1f0002ff`.
- genpd: `pms_sram` `off-0`, `pmp` on, `pms` on.
- `apple_pmp` loaded (`98304 2 appledrm,aurora`), with no device bound; `apple_pmp_v1` not
  loaded. No `dmesg` line contains `pmp`.

### 2. The boot

`m1-bootonce ... ds23p` issued the reboot at 04:10:32. `7.2.11-ds23p` was up since 04:10:47, and
the series started on the first ssh that answered, at 04:11:11. Nothing was frozen, and
`m1-reboot.sh` was not used. The frame `var/m1-look/20261119-041350-state-linuxobs-ds23p.jpg`
shows the Omarchy desktop.

### 3. ds23p: the client's log and the kernel's lines about the pmp node, complete

Every line from `apple-deepsleep`, `apple-deepsleep-pmp`, the device core or genpd that names the
pmp node, its domains or its probe. There are no others: no `devices_deferred` entry, no
`genpd` line other than the general one at `0.161897`, no DART fault, no SError or oops.
```
[    0.067738] apple-deepsleep: cores: logical CPU of cores 0-7 (MPIDR 0-3, 10100-10103): 0 1 2 3 4 5 6 7
[    0.067747] apple-deepsleep: mailbox at 0x00000008038b4a40: version 1, 8 cores, loader reset vector 0x8037e4000, 0 resumes so far
[    0.068888] apple-deepsleep: pmp: /soc/power-management@23b700000/power-controller@3e0 given phandle 0xff for pmp's power-domains
[    0.069093] apple-deepsleep: pmp: C18: nodes for pmp, its mailbox and its translator added; the client boots at its probe
[    0.069096] apple-deepsleep: enabled: mem_sleep "deep" sleeps through the tested logic; power chip /soc/spmi@23d0d9300/pmic@f; alarm +60 s
[    0.069200] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 16384 bytes at IOVA 0x4000 (bus 0x000000080e4bc000)
[    0.069320] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 65536 bytes at IOVA 0xc000 (bus 0x0000000806100000)
[    0.069330] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 16384 bytes at IOVA 0x20000 (bus 0x0000000810810000)
[    0.069334] apple-deepsleep-pmp 23bc00000.coprocessor: buffer: 16384 bytes at IOVA 0x28000 (bus 0x0000000810814000)
[    0.161897] PM: genpd: Disabling unused power domains
[    6.150185] apple-deepsleep: pmp: boot: a wait ran out, for 0x000200000023b549; 0 received messages dropped, 0 sends failed, 0 accesses refused (first 0x0)
[    6.150221] apple-deepsleep-pmp 23bc00000.coprocessor: error -ETIMEDOUT: not started
[    6.150247] apple-deepsleep-pmp 23bc00000.coprocessor: probe with driver apple-deepsleep-pmp failed with error -110
[   27.616421] apple-pmgr-pwrstate 23b700000.power-management:power-controller@3e0: sync_state() pending due to 23bc00000.coprocessor
[   27.616436] apple-pmgr-pwrstate 23b700000.power-management:power-controller@3d8: sync_state() pending due to 23bc00000.coprocessor
```
`journalctl -k -b -p warning` has the three lines at `6.150` and no other line naming the client or
the node. The `asahi` GPU driver again logs `MMU: IO map: 0x23bc00000:0x4000` (`6.521625`).

**Step by step, against ds22p:**

| Step | ds22p | ds23p |
|---|---|---|
| power-domains given to the node | no line; node has no `power-domains` | `0.068888`: `power-controller@3e0` given phandle `0xff`; the node has `power-domains = <0x7a 0xff>` (`pmp` `@3d8`, `pms_sram` `@3e0`), `power-domain-names` `pmp`, `pms_sram` |
| nodes added | `0.069009` | `0.069093` (same text) |
| buffers | IOVA `0x4000` 16 KB, `0xc000` 64 KB, `0x20000` 16 KB, `0x28000` **64 KB** | the same IOVAs and sizes, but `0x28000` is **16 KB** |
| SRAM block, translator setup, start (+`0x44`), endpoint 0 handshake, endpoints 1-3 | no line | no line |
| endpoint-`0x20` opening | wait for `0x000200000023b549` ran out at `6.105254` | the same wait ran out at `6.150185`; 0 dropped, 0 failed sends, 0 refused accesses |
| `0x55` word | no line | no line |
| outcome | "pmp not running: mailbox stopped, PMP and PMS_SRAM given back to genpd"; device stays **bound** | "error -ETIMEDOUT: not started"; **probe failed with error -110**; no driver bound |
| later | nothing | `27.616`: `sync_state()` pending on `power-controller@3e0` and `@3d8` due to `23bc00000.coprocessor` |

**Devices on ds23p (04:13):**
- `soc/coprocessor@23bc00000`: compatible `apple,t8103-pmp-deepsleep-c18`. Its `reg` is the
  same as ds22p's (`ctrl` `0x23bc00000`+`0x10000`, `sram` `0x23b500000`+`0x80000`, `dart`
  `0x23b300000`+`0x4000`), plus `power-domains` (above). No driver is bound.
  - Device links: supplier `power-controller@3d8` and supplier `power-controller@3e0`, both
    `status=available`, `sync_state_only=0`.
  - No supplier link to the mailbox; ds22p had one, to `23bc08000.mailbox`.
  - `waiting_for_supplier` `0`; runtime status `unsupported`.
- `soc/mailbox@23bc08000`: as in ds22p, bound to `apple-mailbox`.
- `soc/iommu@23b300000`: compatible now `apple,t8103-pmp-dart-deepsleep-c18` (ds22p:
  `apple,t8103-dart`), `status = "disabled"`, not bound to `apple-dart`.
- genpd: **`pms_sram` on**, `pmp` on, `pms` on, `pms_busif` on, `pms_fpwm0`-`4` `off-0`. Neither
  `pmp` nor `pms_sram` lists a device.
- `apple_pmp` loaded (`49152 1 asahi`, aliases `apple,t6000-pmp-v2`, `apple,t8140-pmp-v2`), no
  device bound; `apple_pmp_v1` not loaded.

### 4. ds23p: the words, once a second

- **First sample: 04:11:11, `/proc/uptime` 23.43 s** (17 s after the client's last line at
  6.15 s). This was the earliest the M1 answered over ssh.
- That series ran 5 samples (23.43-27.43 s). The ssh `timeout 6` used for the early start cut it
  off. A second series of 120 samples at 1 s then ran from 04:11:23 to 04:13:22 (uptime
  35.71-155.14 s).
- **0 changes** across all 125 samples:

| Word | ds23p (every sample, 23.4-155 s) | ds22p (39-158 s) | Stock (steps 1 and 5) | macOS (round 10) |
|---|---|---|---|---|
| three words | `0x444/0x666/0x333` | same | same | `0x444/0x444/0x444` from t 3.0; `0x333/0x444/0x222` after the `0x55` word |
| `pmp` +`0x44` | `0x0` | `0x0` | `0x0` | `0x10` from t 2.76 |
| `pmp` +`0x48` | `0x8` | `0x8` | `0x2a` | `0x2a`, then `0x0c`/`0x2c`, `0x2e` |
| A2I `0x23bc08110` | `0x107801` | `0x107801` | `0x20001` | not sampled |
| I2A `0x23bc08114` | `0x26600` | `0x26600` | `0x20001` | macOS writes `0x22200` at the entry's stop |
| `ps_PMP` | `0x1f0f00ff` | `0x1f0f00ff` | `0x1f0000ff` | `0x1f0f00ff` at n 4 |
| `ps_PMS_SRAM` | **`0x1f0000ff`** | `0x0f000300` | `0x0f000300` | `0x1f0000ff` at n 4; `0x1000030f` after the `0x55` word |
| `ps_PMS` | `0x1f0000ff` | same | same | `0x1f0000ff` at n 4 |
| `ps_DCS0` | `0x1f0002ff` | same | same | |

- **Against step 1:** the first sample (23.43 s) already differs in +`0x48`, A2I, I2A, `ps_PMP` and
  `ps_PMS_SRAM`.
- **Against ds22p:** only `ps_PMS_SRAM` differs.
- **Against macOS:** `ps_PMP` and `ps_PMS_SRAM` now both read macOS's sample-n-4 values
  (`0x1f0f00ff`, `0x1f0000ff`). +`0x44` never reads `0x10`. The three words never reach
  `0x444/0x444/0x444`.
- 0-23 s (including the client's 0.07-6.15 s window): not read.

### 5. Stock kernel, after (04:14:41)

`systemctl reboot` from ds23p after 04:13:50 (the exact time was not recorded). Stock `7.3.0-0test5-1-ARCH`, up since
04:14:17, answered at 04:14:35.
- The eleven words read exactly as in step 1 (`ps_PMS_SRAM` `0x0f000300` again).
- genpd `pms_sram` `off-0`, `pmp` on, `pms` on. No `coprocessor@23bc0…` node. `apple_pmp`
  loaded as before.
- The frame `var/m1-look/20261119-041442-state-linuxobs-ds23p-end.jpg` shows the desktop.

### Left out

- Readings before 23.4 s after kernel start, so none inside the client's window.
- What the client wrote to +`0x44`, the SRAM, the DART or the mailbox: it logs no line for those
  steps, and its source was not read.
- `pmp`'s SRAM (incl. `0x23b549000`), the DART's registers and the mailbox FIFOs: not read.
- Whether `pmp`'s CPU ran during the window cannot be told from these readings.

### M1 left

In stock Omarchy (`7.3.0-0test5-1-ARCH`, up since 04:14:17), with the default boot entry
untouched. `m1-bootonce` removed ds22p's ESP copy; ds23p's kernel stays on the ESP under
`s2r/ds23p`, with its modules under `/usr/lib/modules/7.2.11-ds23p`. No file was left in `/root`.
The claim is released.

## Linux round: pmp's translator and SRAM after the client's failed start (ds23p) (2026-11-19 04:17-04:19)

One more boot-only run of ds23p: the same package, command line and rules as the round above. No
sleep and no `pm_test` were started. The M1 was claimed as `linux-obs-pmp`.
- Reads were taken once each, 32-bit, over `/dev/mem` (`O_RDONLY`, `PROT_READ`), and nothing was
  written to any register.
- Each address was logged (stdout and an fsync'd file) before it was read. The power-state words
  were read first, and the rest only because `ps_PMP` read on (bits 4-7 `0xf`). The SRAM was read
  only because `ps_PMS_SRAM` also read on.
- Raw output (private): `var/commit-state/linux-pmp-dart-sram-ds23p-20261119.txt`.
- DART register names are from Aurora Silicon's `drivers/iommu/apple-dart.c` (aurora-silicon/linux
  `integration/aurora` `1f38ff8f4`, read as reference only): `DART_T8020_*`. These are
  *documentation, not observations*:
  - `STREAM_COMMAND` `0x20`, `STREAM_SELECT` `0x34`, `ERROR` `0x40`, `ERROR_ADDR_LO` `0x50`,
    `ERROR_ADDR_HI` `0x54`, `CONFIG` `0x60`, `STREAMS_ENABLE` `0xfc`, `TCR` `0x100`, `TTBR`
    `0x200`;
  - `ERROR` bit 31 is the error flag, bits 24-27 the stream, bits 0-11 the code (bit 4 read
    fault, 3 write fault, 2 no PTE, 1 no PMD, 0 no TTBR); TTBR bit 31 is valid.

**The boot.** Reboot at 04:17:39; `7.2.11-ds23p` up since 04:17:53. The client's log matches the
round above line for line, apart from its addresses and times:
- buffers at IOVA `0x4000` (bus `0x80ea94000`), `0xc000`, `0x20000`, `0x28000`;
- `6.154191` the wait for `0x000200000023b549` ran out;
- `6.154255` probe failed with error -110;
- `29.66` `sync_state()` pending on `@3e0` and `@3d8`.

The reads ran at `/proc/uptime` 26.31-26.32 s, with **no fault**: all 32 reads returned, and no
`dmesg` line followed them. The frame `var/m1-look/20261119-041832-state-linuxobs-dart-ds23p.jpg`
shows the Omarchy desktop.

**Readings at 26.31 s, beside macOS's** (macOS columns are from the section "macOS's pmp start-up
and endpoint-0x20 exchange (from round-10 captures)": det10's boot set-up, t 2.205-2.234; the
entry at t 447.85; the wake at t 538.50):

| Address | ds23p, 26.3 s after boot | macOS |
|---|---|---|
| `ps_PMP` `0x23b7003d8` | `0x1f0f00ff` | `0x1f0f00ff` at sample n 4 |
| `ps_PMS_SRAM` `0x23b7003e0` | `0x1f0000ff` | `0x1f0000ff` at n 4 |
| `ps_PMS` `0x23b700140` | `0x1f0000ff` | `0x1f0000ff` at n 4 |
| DART +`0x0` (PARAMS1) | `0x0ed01020` | `0x0ed01020` (boot, wake) |
| DART +`0x4` (PARAMS2) | `0x11037` | `0x11037` |
| DART +`0x60` (CONFIG) | `0x80016100` | boot: read `0x80016100`; wake: read `0x10000`, written `0x80016100` |
| DART +`0x68` / +`0x6c` | `0xf0f0f` / `0x80808` | boot: read `0xf0f0f` / `0x80808`; wake: read `0x20202` / `0`, written `0xf0f0f` / `0x80808` |
| DART +`0x80`-`0x8c` (REMAP) | `0x03020100 0x07060504 0x0b0a0908 0x0f0e0d0c` | the same (boot) |
| DART +`0xf0` | `0x0` | `0` (boot, wake) |
| DART +`0xfc` (STREAMS_ENABLE) | **`0x1`** | boot: written `0`, then `1` last; entry: read `1`, written `0`; wake: written `1` |
| DART +`0x100` (TCR sid 0) | `0x80` (TRANSLATE_ENABLE) | written `0x80` (boot, wake); entry read `0x80` |
| DART +`0x13c` (TCR sid 15) | `0x100` (BYPASS_DART) | written `0x100` (boot, wake); entry read `0x100` |
| DART +`0x200` (TTBR sid 0) | **`0x8080ea90`** (valid, table at `0x80ea90000`) | `0x808217dc` (det10 boot), `0x80822544` (wake): valid, other tables |
| DART +`0x2f0` | `0x0` | written `0` (boot, wake) |
| DART +`0x20` (STREAM_COMMAND) | `0x100000` | boot: written `0x100000`, read back `0x100000` |
| DART +`0x40` (ERROR) | `0x6000400` | entry: read `0x6000400` |
| DART +`0x50` (ERROR_ADDR_LO) | `0x63253bb9` | not read by macOS in the logged captures |
| DART +`0x54` (ERROR_ADDR_HI) | `0x0` | not read |
| DART +`0x100c` | `0x0` | entry: read `0` |
| `pmp` +`0x44` | `0x0` | `0x10` from n 4 (running); `0` after the entry's stop |
| `pmp` +`0x48` | `0x8` | `0x2a` before the start; `0x0c`/`0x2c` at n 4; `0x2e` after the stop |
| mailbox A2I `0x23bc08110` | `0x107801` | not in the logged set |
| mailbox I2A `0x23bc08114` | `0x26600` | boot: written `0x20001`; entry's stop: written `0x22200` |
| SRAM +`0x204` `0x23b500204` | `0x64697575` (`uuid`) | `0x64697575` (`135map4`) |
| SRAM +`0x22c` | `0x3a800` | `0x3a800` |
| SRAM +`0x230` | `0x2d0` | `0x2d0` |

- **What is the same as macOS:**
  - the DART's PARAMS, CONFIG, `+0x68`/`+0x6c` and REMAP words, as macOS read them at boot;
  - TCR sid 0 `0x80`, TCR sid 15 `0x100` and `+0x2f0` `0`, as macOS wrote them;
  - STREAMS_ENABLE `1`, as macOS left it at the end of its boot set-up;
  - STREAM_COMMAND `0x100000`;
  - ERROR `0x6000400`, the value macOS read at the entry;
  - the three power-state words, at macOS's sample-n-4 values;
  - the SRAM header words: SRAM answers, and holds the boot-argument offset and size macOS read.
- **What differs from macOS:**
  - TTBR sid 0 points at another table (`0x80ea90000`; macOS's two logged values also differ from each other);
  - `pmp` +`0x44` reads `0x0`, not macOS's `0x10` while `pmp` runs;
  - +`0x48` reads `0x8`, a value not read under macOS;
  - I2A control reads `0x26600`, not macOS's written `0x20001` (boot) or `0x22200` (stop).
- By the reference's bit layout, ERROR `0x6000400` has the flag (bit 31) clear, stream 6 in
  bits 24-27, and code `0x400`: none of the five named fault bits 0-4 is set. This is
  documentation applied to a reading; what code bit 10 means is not read.
- `0x80ea90000` (the TTBR's table) lies 16 KB below the client's first buffer (bus
  `0x80ea94000`): two readings set side by side, nothing more.

**After.** `systemctl reboot` at 04:18:43. Stock `7.3.0-0test5-1-ARCH`, up since 04:19:00,
answered at 04:19:22. Its eleven words read as in every stock reading tonight
(`0x444/0x666/0x333`, +`0x44` `0x0`, +`0x48` `0x2a`, `0x20001`/`0x20001`, `0x1f0000ff`,
`0x0f000300`, `0x1f0000ff`, `0x1f0002ff`). The frame
`var/m1-look/20261119-041925-state-linuxobs-dart-end.jpg` shows the desktop.

### Left out

- The DART's page tables at `0x80ea90000`, and what IOVAs they map: not read.
- The DART's other streams' TCR and TTBR words, beyond sid 0, sid 15's TCR and `+0x2f0`: not read.
  STREAM_SELECT (`+0x34`, which macOS only wrote) was not read either.
- The SRAM beyond the three header words: the boot-argument block at `+0x3a800`, `__DATA`, and
  `0x23b549000`. Whether the block holds macOS's 54 records is not read.
- The values of these registers during the client's 0.07-6.15 s window, and before the client
  ran: not read. Whether macOS's own boot leaves ERROR at `0x6000400` before the start is not
  logged.
- What ERROR_ADDR_LO `0x63253bb9` refers to: not read.

### M1 left

In stock Omarchy (`7.3.0-0test5-1-ARCH`, up since 04:19:00), with the default boot entry
untouched. ds23p's kernel stays on the ESP under `s2r/ds23p`. The read log
`/var/lib/m1power-pmpdart.log` was removed before the reboot, and its absence was checked on stock.
The claim is released.

## Hypervisor round 12: what macOS maps for pmp, and its opening page (det38, det39, 2026-11-19 04:46-04:57)

Readings only, two macOS 13.5 boots under the hypervisor, no sleep. Taken for the spec's open
questions 83, 84 (g) and 85 (lab `7a6e366`): what macOS's translator for `pmp` (DART
`0x23b300000`, ADT `/arm-io/dart-pmp`) maps, and what the page at IOVA `0x3c000` holds. The table
was walked from DRAM with every guest CPU stopped (m1n1's rendezvous), reads only: the DART's
registers by 32-bit reads, the table pages and every DRAM page it maps by memory reads. No page
the DART maps to MMIO was read. Times `t` are seconds from the touch map's start. Where a reading
was not taken, the text says so.

**Short answer.**
- **One table, stream 0, the same at every point read (2.6 s to 77.3 s).** TCR0 `0x80`, TCR15
  `0x100`, ENABLED_STREAMS `0x1`, one valid TTBR (`0x200`: det38 `0x808229f8`, det39 `0x8082282c`).
  The L1 table has 5 valid entries (indices 0, 96, 97, 98, 99: IOVA `0x0`-`0x1ffffff` and
  `0xc0000000`-`0xc7ffffff`), each pointing at one L2 page.
- **113 valid 16 KiB pages:**
  - **13 DRAM pages**, IOVA `0x4000`-`0x4bfff` (not `0x0`, `0xc000`, `0x14000`, `0x1c000`,
    `0x30000`, `0x38000`). Their physical addresses differ between the two boots.
  - **100 MMIO pages, `0x190000` bytes, IOVA `0xc0000000`-`0xc6003fff`**, in 34 ranges. **Each range
    is one ADT `/arm-io/pmp` `reg` entry, at its address and size: every non-zero entry from index 3
    (`pio-reg-index` = 3) to 43.** Identical in both boots.
  - Count, total and span are those of the earlier Linux module's "34 windows" (`0x190000` bytes
    at `0xc0000000`-`0xc6004000`, as this round's brief quotes them from spec round 15e). That
    module's own IOVA-to-address list is not read here, so whether each window sits at the same
    IOVA is not compared.
- **Not mapped:** `pmp` reg 0 (`0x23bc00000`, control and mailbox), reg 1 (`0x23b850000`), reg 2
  (the SRAM `0x23b500000`), and the SRAM segments' IOVAs `0x100000000` / `0x10002c000` (ADT
  `segment-ranges`).
- **Every PTE ends in `0x3`:** bit 0 (VALID) and bit 1 (SP_DIS in the reference driver). Bits 7/8
  (NO_WRITE / NO_READ in the reference) are clear. The subpage fields (bits 40-63) are 0.
- **When `pmp`'s CPU is released, its DART has no table yet** (det39, read inside the trap of
  macOS's `W 0x23bc00044` = `0x10`, before the write was done): TTBR `0x200` = 0,
  ENABLED_STREAMS = 0. The TCRs are already set. The TTBR write (`0x8082282c`) and the enable come
  after it, from another CPU. det38's log has the same order, by receipt time.
- **Page IOVA `0x3c000`** (both boots byte for byte the same at each point):
  - **When macOS writes `0x000100000003c000`, and just after:** 77 non-zero bytes, all in
    `+0x2000`-`+0x207f`. That 0x80-byte block equals bytes `0x80`-`0xff` of the ADT property
    `/arm-io/pmp/iop-pmp-nub` `energy-model-dram-configs` (0x200 bytes; the node's `dram-capacity`
    is 8). The rest of the page is zero.
  - **By the read of `pmp`'s `0x000200000023b549`:** `+0x0`-`+0x19cf` written (3197 bytes changed;
    `+0x2000` block unchanged). A header reading `EHUB`, `PM`, `FAST_DIE`, then **90 records of
    0x48 bytes** (two 32-bit words, then a 64-byte name): `ehub-node-mask`,
    `pm-device-sampling-mask`, `pm-device-counter-mask`, `pm-dcs-rt-*-bw-threshold-v*`,
    `pm-gpu-constraint-p1..p6-dcs/-soc`, `pm-gpu-read/write-bw-threshold-*`,
    `pm-ane-bw-threshold-*`, `pm-sep-bw-threshold-*`, `fast-die-*`.
  - **No guest CPU wrote the page** between the opening word and 139 s (det39: writes to the page
    trapped from the opening word on: 0 writes). **No guest CPU read it** in that time either.
  - The first 0x40 bytes were still zero at every mailbox access up to the one just before
    `pmp`'s reply was read (det39: changed at `t` 4.15, the reply read at 4.21).
  - Unchanged from the reply to 77.3 s.
- **Page IOVA `0x48000`, `+0x2000`-`+0x228f`: a table of 41 (IOVA, size) pairs, one for each
  `pmp` reg index 3-43, each the IOVA and size the DART maps that entry at** (all 34 non-zero
  entries match; the 7 zero-size entries are zero). Present when the opening word is written.
  Words `+0x0`/`+0x4`/`+0x8` went 0/0/0 -> 2/`0x01000000`/`0x01000000` before the reply with no
  guest CPU write.
- **Page IOVA `0x40000`:** a table of names and numbers (`SOC`, `VMIN` `0x28d`, `VNOM` `0x2bf`,
  `VMAX` `0x371`, `DCS`, `DISP`, `ECPU`, `PCPU`, `GPU`, `ISP`, `VENC`, `VDEC`, `ANE`, `PCIE`, `ATC0`,
  `NRO0`, …). Empty when the opening word is written; 64 non-zero bytes just after it, 164 at the
  reply, 224 at the 0x55 message. No guest CPU write. macOS's CPUs read `+0x0`-`+0x2c0` right
  after the reply (288 reads, t 4.245-4.284, 7 pcs).
- **At 77.3 s, 6.2 s after `0x0020e00000550000`:** the TTBR, the five L1 entries and all 113 PTEs
  are as at the opening word. The three pages are as at the 0x55 message. Between the reply and the
  0x55 message only `0x40000` changed (164 -> 224 non-zero bytes).

### The runs

- **Hypervisor:** `~/m1n1-next` `c2d99a4e` (build `v2.0.0-148-gc2d99a4e`, round 11's), unchanged;
  `hv_hold_msg` left 0. The proxy client is `~/m1n1` (`c288f8d4`), unchanged.
- **Host side, private (`var/commit-state/`):**
  - `r12_pmp_dart.py`, a run_guest script loaded before the touch map. It traps the mailbox page
    `0x23bc08000` synchronously, and with `R12_CTRL=1` the control page `0x23bc00000` too. Dumps:
    - `start-pre`: macOS's `W +0x44` = `0x10`, before the write (det39);
    - `open-pre`: the `W 0x23bc08800` = `0x000100000003c000`, before the write;
    - `open-post`: the next mailbox access, the write done;
    - `reply`: the read of `0x000200000023b549` from `0x23bc08830`;
    - `m55-pre` / `m55-post`: the same for `0x0020e00000550000`;
    - `late`: the first clock tick 6 s after `m55-pre`.

    Each dump is the DART's words, the L1 and L2 pages and the 13 DRAM pages. With
    `R12_PAGE_TRAP` (det39: `0x3c000,0x40000,0x48000`), guest CPU writes to those DRAM pages are
    trapped synchronously and their reads traced, from `open-pre` on. Writes through `pmp`'s DART
    are not seen by such a trap. At `start-pre` it also reads `pmp`'s SRAM header and its
    boot-argument block (32-bit reads).
  - `r12-macos-up.sh`: `harness/macos-up.sh` with that script added to run_guest.
- **Recipe:** round 11's boot, without the hold and the sleep:
  - `R12_OUT=<dir> [R12_CTRL=1 R12_PAGE_TRAP=0x3c000,0x40000,0x48000] FULL=0 REAL_S2R=0
    SETTLE_EPOCHS=24 S2R_TOUCH_TICK=250 S2R_TOUCH_SAMPLE=<round 10's nine words>
    S2R_TOUCH_FULL=0x23bc00000+0x4000,0x23bc08000+0x4000,0x23b300000+0x4000
    var/commit-state/r12-macos-up.sh detNN`;
  - the camera showed the login window;
  - `harness/hv-reboot.sh`.

  The M1 was claimed as `observation` for each run and released between them and at the end.
- **The no-hands way out:** the attached host and `hv-reboot.sh`; for a dead hypervisor,
  `tools/m1-reboot/m1-reboot.sh`. Neither boot hung; both ended with `hv-reboot.sh`.

| Run | Run times | `+0x44` / opening / reply / 0x55 (t) | Dumps | Page traps |
|---|---|---|---|---|
| det38 | 04:46:40-04:49:20, log to t 148 | async log 2.33 / 2.62 / 3.82 / 71.11 | open-pre, open-post, reply, m55-pre, m55-post, late (77.3) | none |
| det39 | 04:54:24-04:56:54, log to t 139 | trap 2.32 / 2.64 / 4.21 / 71.15 | start-pre (0 PTEs), then the same six (late 77.3) | 3 pages from 2.64: 0 writes, 288 reads |

- **Login window on the camera** in both runs (04:49:08, 04:56:41). No dump error. Every dump took
  0.017-0.061 s of host time.
- **Timing changed by the traps:** the reply was read 1.2 s (det38) and 1.58 s (det39) after the
  opening word. Round 10's captures, without the mailbox trapped, show 0.27-0.59 s. The page
  contents were still the same in both runs.

### 1. The DART's words (every dump; det39's `start-pre` where it differs)

- PARAMS1 `0x0ed01020`, PARAMS2 `0x11037`, CONFIG `0x80016100`, `+0x68` `0xf0f0f`, `+0x6c`
  `0x80808`, REMAP `0x03020100 0x07060504 0x0b0a0908 0x0f0e0d0c` (det38's log).
- ERROR `0x6000400` in every dump, `start-pre` included.
- ENABLED_STREAMS `0x1` (`start-pre`: 0).
- TCR sids 0-14 `0x80`, sid 15 `0x100`, both at `start-pre` already. macOS's own writes in the log
  are only to sid 0 and sid 15.
- TTBR sid 0 slot 0: as above (`start-pre`: 0).
  - Of the other 63 TTBR words, `+0x2f0` reads 0 (macOS writes it 0). The other 62 hold non-zero
    values with bit 31 clear (det38: `+0x204` `0x73e9665`, `+0x208` `0xbbde7a3`, …), the same at
    every dump of a boot, `start-pre` included. No table was walked for them.

### 2. The mapping, by range (det38 = det39 for every MMIO entry)

DRAM, physical addresses det38 / det39:

| IOVA | det38 PA | det39 PA | Named in the captures' messages |
|---|---|---|---|
| `0x4000` | `0x8229f0000` | `0x822860000` | kdebug SET_BUFFER0 |
| `0x8000` | `0x8229ec000` | `0x82285c000` | — |
| `0x10000` | `0x8229fc000` | `0x822830000` | kdebug SET_BUFFER1 |
| `0x18000` | `0x8228c8000` | `0x8227ec000` | crashlog buffer |
| `0x20000`, `0x24000`, `0x28000`, `0x2c000` | `0x8228d8000`, `d4000`, `d0000`, `cc000` | `0x822880000`, `83c000`, `838000`, `834000` | ioreport buffer `0x20000` |
| `0x34000` | `0x8228dc000` | `0x8227f0000` | syslog buffer |
| `0x3c000` | `0x822a64000` | `0x822868000` | endpoint `0x20` opening word |
| `0x40000` | `0x822a60000` | `0x8228a4000` | — |
| `0x44000` | `0x822a9c000` | `0x8228a0000` | — |
| `0x48000` | `0x822a98000` | `0x82289c000` | — |

MMIO, with the ADT `/arm-io/pmp` reg index each range equals, and the other ADT nodes whose `reg`
covers it:

| IOVA | Size | PA | `pmp` reg | Also inside |
|---|---|---|---|---|
| `0xc0000000` | `0x4000` | `0x200024000` | 3 | `mcc` reg 1, `error-handler` reg 2 |
| `0xc0004000` | `0x4000` | `0x200064000` | 4 | `mcc` reg 1, `error-handler` reg 5 |
| `0xc0008000` | `0x4000` | `0x2000a4000` | 5 | `mcc` reg 1, `error-handler` reg 8 |
| `0xc000c000` | `0x4000` | `0x2000e4000` | 6 | `mcc` reg 1, `error-handler` reg 11 |
| `0xc0010000` | `0x4000` | `0x200158000` | 7 | `mcc` reg 0, `error-handler` reg 0 |
| `0xc0014000`-`0xc0020000` | 4 × `0x4000` | `0x200204000`, `244000`, `284000`, `2c4000` | 8-11 | `mcc` reg 2, `error-handler` reg 17 |
| `0xc0024000` | `0x4000` | `0x200170000` | 35 | `mcc` reg 0, `error-handler` reg 0 |
| `0xc1000000` | `0x4000` | `0x204d10000` | 17 | `sgx` reg 0, reg 1 |
| `0xc1004000` | `0x4000` | `0x204e20000` | 38 | `sgx` reg 0 |
| `0xc1008000` | `0x8000` | `0x204d80000` | 43 | `sgx` reg 0 |
| `0xc2000000`-`0xc200c000` | 4 × `0x4000` | `0x210058000`, `158000`, `258000`, `358000` | 18-21 | `pmgr` reg 10-13, one each |
| `0xc2010000` | `0x60000` | `0x210e20000` | 22 | `pmgr` reg 5 (`0x210e20000`+`0x2000`), 7, 9 |
| `0xc2070000` | `0x4000` | `0x210e48000` | 23 (also inside reg 22) | `pmgr` reg 7 |
| `0xc2074000` | `0x8000` | `0x210ee0000` | 42 | — |
| `0xc3000000`-`0xc300c000` | 4 × `0x4000` | `0x211058000`, `158000`, `258000`, `358000` | 24-27 | `pmgr` reg 19, 20, 24, 25, one each |
| `0xc3010000` | `0x60000` | `0x211e20000` | 28 | `pmgr` reg 14 (`0x211e20000`+`0x2000`), 16, 18 |
| `0xc3070000` | `0x4000` | `0x211e48000` | 29 (also inside reg 28) | `pmgr` reg 16 |
| `0xc3074000`, `0xc307c000`, `0xc3084000` | 3 × `0x8000` | `0x211ee0000`, `ee8000`, `ef0000` | 39, 40, 41 | — |
| `0xc4000000` | `0x14000` | `0x23d100000` | 30 | `pmgr` reg 23, `dockchannel-uart` reg 1 |
| `0xc4014000` | `0x30000` | `0x23d128000` | 31 | `pmgr` reg 23, `dockchannel-uart` reg 0 |
| `0xc4044000` | `0x4000` | `0x23d0d8000` | 32 | `nub-spmi` reg 0-2 |
| `0xc5000000` | `0x4000` | `0x26b90c000` | 33 | `ane` reg 0 |
| `0xc6000000` | `0x4000` | `0x23c100000` | 37 | `gpio` reg 0 |

`pmgr`'s wide `reg` ranges 6, 8, 15, 17, 26 and 27, and the `mtrtempsensor*` nodes' 16 MiB ranges, also cover the
`0x210…`/`0x211…` rows. They are left out of the last column.

- **ADT values** (the tree m1n1 held in this run, `r12-adt.bin`):
  - `/arm-io/pmp`: `pio-reg-index` 3, `pio-vm-base` `0xc0000000`, `pio-vm-size` `0x40000000`;
    44 `reg` entries, 7 of them of size 0 (12-16, 34, 36).
  - `/arm-io/dart-pmp`: `pio-vm-base` `0xc0000000`, `pio-vm-size` `0x40000000`,
    `pio-granularity` `0x1000000`, `vm-size` `0xbff00000`, `page-size` `0x4000`, `sids` `0x8001`,
    `bypass` `0x8000`.
  - Its child `mapper-pmp` `pio-range`: 34 (address, size) pairs, 32 non-zero and 2 zero.
    - The 32 are `pmp` reg 3-11, 17-22, 24-28, 30-33, 35, 37-43, with their sizes, `0x188000` in
      all.
    - Not listed: reg 23 and reg 29. They lie inside reg 22 and reg 28 and are mapped a second time
      on their own (`0xc2070000`, `0xc3070000`), which brings the total to `0x190000`.
- **The IOVA layout, as it reads:**
  - One 16 MiB IOVA slot (`pio-granularity`) for each 16 MiB block of physical address, in the
    order the blocks first appear by reg index: `0x200…` -> `0xc0`, `0x204…` -> `0xc1`, `0x210…` ->
    `0xc2`, `0x211…` -> `0xc3`, `0x23d…` -> `0xc4`, `0x26b…` -> `0xc5`, `0x23c…` -> `0xc6`.
  - Within a slot, the ranges are packed in reg-index order.

  This describes this table. It is not a reading of how macOS built it.

### 3. Page IOVA 0x3c000

- **`open-pre` = `open-post`** (both boots): 77 non-zero bytes, `+0x2000`-`+0x207e`. They equal
  `energy-model-dram-configs[0x80:0x100]`. The property has four 0x80-byte blocks, beginning
  `08000000 06000000`, `08000000 ff000000`, `10000000 06000000`, `10000000 ff000000`; this is the
  second.
  - Who wrote it is not read: no trap was on the page before the opening word. The page was not
    mapped at `start-pre` (det39).
- **`reply`:** `+0x0`-`+0x19cf`, then the `+0x2000` block; the rest zero.
  - Header, 32-bit words:
    - `+0x00` `0x42554845` (`EHUB`);
    - `+0x14` 2, `+0x18` 1;
    - `+0x20` `PM`;
    - `+0x38` `0x3f`, `+0x3c` 1;
    - `+0x40` `FAST_DIE`;
    - `+0x54` 1, `+0x58` `0x1a`, `+0x5c` `0x40`.
  - Then 90 records of 0x48 bytes from `+0x80`. Records 0, 64 and 89:
    - `+0x080`: a 0, b 0, `ehub-node-mask`;
    - `+0x1280`: a `0x00ffff02`, b `0x13880000`, `fast-die-ts`;
    - `+0x1988`: a `0x00010808`, b `0x000c0000`, `fast-die-pacc-ts5i-offset`.

    The full list, with both words, is in `r12-det38-tables-reply.txt`.
  - Counts: 1 `ehub` record, 2 `pm-device-*`, 17 `pm-dcs-*`, 12 `pm-gpu-constraint-*`, 16
    `pm-gpu-read/write-bw-threshold-*`, 8 `pm-ane-*`, 8 `pm-sep-*`, 26 `fast-die-*`.
  - The 13.5 kernelcache (`kc/kernelcache-13.5.macho`) contains the string
    `pm-device-sampling-mask`. The other names are found neither in it nor in the ADT as whole
    strings.
- **Who wrote it (det39):**
  - Guest CPU writes to the page were trapped from `open-pre` to the end of the log (t 139): none.
  - Guest CPU reads were traced over the same time: none.
  - The first 0x40 bytes, read at every mailbox access from `open-pre` to the reply, changed once,
    at `t` 4.1535. That was the status read after macOS's endpoint-4 echo `W 0x0080000000000000`
    (t 4.1456). It returned `0x209b01`; the reply word itself was read at 4.2135. The page is
    mapped in `pmp`'s DART. Whether another device's translator maps the same physical page is
    not read.
- **`m55-pre`, `m55-post`, `late`:** byte for byte as at `reply`.

### 4. Pages IOVA 0x48000 and 0x40000

- **`0x48000`:**
  - `+0x2000`-`+0x228f`: 41 slots of (64-bit IOVA, 64-bit size). Slot k holds `pmp` reg (k + 3):
    the IOVA and size where the DART maps it. All 34 non-zero entries match; reg 12-16, 34 and 36
    are zero, and so is slot 41 (reg 44, which does not exist).
  - Present at `open-pre` in both boots.
  - `+0x0` (32-bit words): 0 0 0 at `open-pre`, 2 `0x01000000` `0x01000000` at `reply`. No guest
    CPU write (det39).
  - No guest CPU read of the page.
- **`0x40000`:**
  - Non-zero bytes: 0 (`open-pre`), 64 (`open-post`), 164 (`reply`), 224 (`m55-pre` and later).
    The same counts and bytes in both boots.
  - No guest CPU write (det39).
  - Guest CPU reads, det39: 288 at t 4.245-4.284, `+0x0`-`+0x2c0`, from 7 pcs, CPU 2 only (8- and
    64-bit). None after.
- **The boot-argument block, det39 at `start-pre`:**
  - SRAM `+0x22c`/`+0x230` = `0x3a800`/`0x2d0`.
  - 54 records, the same tags and values as `135map4`'s except `STKG`
    (`0xe6c69c09006dc582`).
  - `IOBA` 0, `IOSZ` 0. No record holds `0x3c000`, `0x40000` or `0x48000`.
- **The other DRAM pages, at `late`:**
  - `0x4000`, `0x8000`, `0x44000`: zero.
  - `0x10000`: `+0x0`-`+0x1fff` all `0xff`.
  - `0x18000`: all `0xef`.
  - `0x20000`: begins `bROI…Duty cycle`; `0x24000`-`0x2c000` hold more such records.
  - `0x34000`: syslog entry `main.cpp:4480`, `PMP started`.
  - Between the boots, `0x20000`-`0x2c000` differ at some of the points; the rest are the same at
    each point.

### Left out, and why

- **Who wrote what was already there when the opening word was written** (the `+0x2000` block at
  `0x3c000`, the window table at `0x48000`): the traps go on at `open-pre`. Before that the pages'
  physical addresses are not known, and at `start-pre` nothing is mapped.
- **`pmp`'s own accesses** to these pages: a stage-2 trap sees only the guest's CPUs. What `pmp`
  reads, and when, is not observable this way.
- **Writes the trap could miss:** a write by another bus master to the same physical page is not
  trapped either. Which other translators map these pages is not read.
- **The MMIO behind the 34 ranges:** not read.
- **Sleep and wake:** no sleep was taken. The wake's new TTBR (det33 `0x80822544`) has not been
  walked.
- **The earlier Linux module's own window list:** not read. Only its count, total and span, as
  this round's brief quotes them from spec round 15e, are compared above.
- **Decoding the records:** the meaning of the two words in each 0x48-byte record, of the `EHUB`
  header, and of the `0x40000` and `0x48000` header words is not read.
- **Timing:** the synchronous traps on the mailbox and control pages slowed macOS's side of the
  exchange (reply read 1.2-1.6 s after the opening word, against 0.27-0.59 s untrapped).
- **Order of the pmp start and the TTBR write:** the two run on different CPUs (det38: CPUs 2 and
  0; det39: 0 and 1). The order seen in det39 is that boot's, under traps.

### Files (private)

- `var/commit-state/r12_pmp_dart.py`, `r12-macos-up.sh`; decoders `r12_analyze.py`,
  `r12_tables.py`, `r12_pio.py`.
- Dumps: `var/commit-state/r12-det38/` and `r12-det39/`:
  - `r12-<tag>.json`: the DART's words, the L1 entries, every PTE, the DRAM pages read;
  - `r12-<tag>-pt-<pa>.bin`: the table pages;
  - `r12-<tag>-iova-<iova>.bin`: the DRAM pages;
  - `r12-events.jsonl`: the dumps, the traps, every traced read, the boot-argument words, the
    header watch;
  - `r12-bootargs.bin`; `r12-adt.bin`, `r12-adt-pmp.txt`, `r12-adt-regs.json`.
- Decoder outputs:
  - `var/commit-state/r12-det38-analysis.txt`, `r12-det39-analysis.txt`;
  - `r12-det38-tables-reply.txt`, `r12-det39-tables-reply.txt`;
  - `r12-det38-pio.txt`, `r12-det39-bootargs.txt`.
- Hypervisor logs: `tools/hv-trace-kit/runs/20261116-mac135/*-det38.*`, `*-det39.*`.
- Camera frames:
  - `var/m1-look/20261119-044603-*` (before), `-044908-*` (det38 login window);
  - `-045352-*` (before det39), `-045641-*` (det39 login window), `-045725-*` (after).

### M1 left

In stock Omarchy (`7.3.0-0test5-1-ARCH`, up since 04:57:02; camera 04:57:25 shows the desktop),
default boot entry untouched. The claim is released.

## Linux round: the pmp client's log and pmp's crash log (ds24p, ds25p, ds26p)

Three boot-only runs of the kernel-side `pmp` client, run by the orchestrator on 2026-11-19
between about 04:43 and 05:02 IST (raw files written 04:43, 04:53, 05:00). No sleep was started.
After each run the M1 was rebooted to the stock kernel. This section is written from the raw files
only. The observation agent did not use the M1 and did not read the client's source.

| Run | Kernel (client commit) | Command line | Raw (private, `var/commit-state/`) |
|---|---|---|---|
| ds24p | `7.2.11-ds24p` #28 (`eac8f107d`), probe line "build 0000000" | `var/deepsleep/ds24p.cmdline` | `linux-pmp-client-ds24p-dmesg-20261119.txt` |
| ds25p | `7.2.11-ds25p` #29 (`96700062d`), "build 9670006" | the same | `linux-pmp-client-ds25p-dmesg-20261119.txt` |
| ds26p | `7.2.11-ds26p` #30 (`a7b0d2022`), "build a7b0d20" | `var/deepsleep/ds26p.cmdline` = ds24p's + `apple_deepsleep.pmp_opening_bytes=0x400000` | `linux-pmp-client-ds26p-dmesg-20261119.txt`, `-words-` |

- ds24p's command line: `panic=10 systemd.watchdog_sec=0 apple_deepsleep.enable=1
  apple_deepsleep.alarm_secs=60 no_console_suspend apple_deepsleep.cand=0x40000 log_buf_len=4M`
  after the stock root arguments.
- ds24p is the first build that logs the client's steps (`#1`-`#74`). ds25p adds hex dumps of
  the client's four buffers, taken twice: once when a crashlog word naming its buffer arrives
  (before `#70`), and once at the failed boot.
- ds26p maps 4 MiB for the opening's buffer: `buffer: 4194304 bytes at IOVA 0x28000 (bus
  0x0000000806400000), mapped 0x400000 for the opening by pmp_opening_bytes (0x4000 asked), IOVA
  0x28000-0x427fff`.
- `linux-pmp-client-ds24p-crashlog-20261119.txt` is a failed attempt to read ds24p's freed
  crash-log buffer afterwards. The 16 KiB read had 5068 non-zero bytes that do not begin with
  `EHLC`. They hold `0xffff80…`-shaped words, so the memory had been reused. It is not used below.

**Short answer.**
- **The same exchange in all three boots, word for word: 46 words**, from `pmp`'s first
  management word to the client's opening word `0x0001000000028000` on endpoint `0x20`. Then
  comes a crashlog word `0x0010100000004000` (`#69`), which the client answers. Then the 6 s wait
  for `0x000200000023b549` runs out. Only the times, and the bus addresses of the buffers, differ.
- **`pmp` wrote a crash log** into the client's crashlog buffer (IOVA `0x4000`). It was decoded
  from ds25p's and ds26p's dumps. The two dumps of a boot are byte for byte the same (at about
  0.07 s and at about 6.1 s).
  - In both boots: pc `0x1027a10`, lr (x30) `0x10166d0`, sp `0x1039fc0`, psr `0x600002c5`, esr
    `0xbe000000`.
  - far differs: **`0x36140` (ds25p)** and **`0x210e70000` (ds26p)**.
  - The orchestrator's quick decode is confirmed.
- **pmp's mailbox history** in the crash log is the last 16 words of the client's log, `#50` to
  `#68`, in order and in both directions. It ends with the opening word.
- **pmp's own table of mappings** (section `Ccdp`) lists the client's four buffers at the IOVAs
  and sizes the client gave. The opening's entry reads **IOVA `0x28000`, size `0xf000`**, where
  the client mapped `0x4000` (ds24p, ds25p).
  - ds25p's far `0x36140` = `0x28000` + `0xe140`. That is inside that `0xf000` range and outside
    the client's `0x4000` mapping.
  - Laid on macOS's layout (opening at `0x3c000`), `+0xe140` is `0x4a140`. That is slot 20 of
    the (IOVA, size) table at `0x48000`+`0x2000`, the slot for `pmp` reg 23. This is arithmetic
    on two sets of numbers, not a reading of what `pmp` read.
- **The translator's ERROR word after the wait:** `0x6000400` in ds24p and ds25p (macOS's value
  in every round-12 dump) and **`0x80000800`** in ds26p.

### 1. The exchange, word by word

Taken from the `#N boot: received|sent` lines. Times are the client's `boot+…us` (hex µs). Steps
`#20`, `#23`, `#30`, `#58`, `#64`, `#67` are "wait ended: <the word above> came" lines. Words
and order are identical in the three boots (checked by script, all 46).

| # | Dir | Endpoint | Word | ds24p | ds25p | ds26p |
|---|---|---|---|---|---|---|
| 19 | received | 0x0 mgmt | `0x00100000000c000c` | 0x389 | 0x39a | 0x46b |
| 21 | sent | 0x0 mgmt | `0x00200000000c000c` | 0x38f | 0x3a7 | 0x478 |
| 22 | received | 0x0 mgmt | `0x008000000000001f` | 0x3ab | 0x3d0 | 0x4a4 |
| 24 | sent | 0x0 mgmt | `0x0050000100000002` | 0x3b0 | 0x3da | 0x4ad |
| 25 | sent | 0x0 mgmt | `0x0050000200000002` | 0x3b3 | 0x3df | 0x4b2 |
| 26 | sent | 0x0 mgmt | `0x0050000300000002` | 0x3b6 | 0x3e4 | 0x4b6 |
| 27 | sent | 0x0 mgmt | `0x0050000400000002` | 0x3b9 | 0x3ea | 0x4ba |
| 28 | sent | 0x0 mgmt | `0x0080000000000001` | 0x3bc | 0x3ee | 0x4bf |
| 29 | received | 0x0 mgmt | `0x0088000100000001` | 0x3d1 | 0x407 | 0x4e5 |
| 31 | sent | 0x0 mgmt | `0x0088000100000000` | 0x3d7 | 0x410 | 0x4ee |
| 32 | received | 0x1 crashlog | `0x0010100000000000` | 0x406 | 0x44b | 0x526 |
| 33 | sent | 0x1 crashlog | `0x0010400000004000` | 0x40a | 0x452 | 0x52d |
| 34 | received | 0x4 ioreport | `0x0011000000000000` | 0x459 | 0x49a | 0x570 |
| 35 | sent | 0x4 ioreport | `0x001100000000c000` | 0x45d | 0x4a0 | 0x576 |
| 36 | received | 0x4 ioreport | `0x00c0000000000000` | 0x4a3 | 0x4e3 | 0x5ae |
| 37 | received | 0x4 ioreport | `0x0080000000000000` | 0x4a6 | 0x4e8 | 0x5b5 |
| 38 | sent | 0x4 ioreport | `0x0080000000000000` | 0x4a9 | 0x4ed | 0x5ba |
| 39-56 | received / sent, alternating | 0x4 ioreport | `0x0080000000000000` (9 more pairs) | 0x4cf-0x5fe | 0x514-0x68b | 0x5d2-0x6fc |
| 57 | received | 0x0 mgmt | `0x0070000000000020` | 0x61e | 0x6a9 | 0x71c |
| 59 | sent | 0x0 mgmt | `0x00b0000000000020` | 0x624 | 0x6b1 | 0x723 |
| 60 | received | 0x2 syslog | `0x0080000050000010` | 0x639 | 0x6c6 | 0x739 |
| 61 | received | 0x2 syslog | `0x0010100000000000` | 0x63b | 0x6ca | 0x73f |
| 62 | sent | 0x2 syslog | `0x0010100000020000` | 0x63f | 0x6d0 | 0x744 |
| 63 | received | 0x0 mgmt | `0x00b0000000000020` | 0x680 | 0x710 | 0x785 |
| 65 | sent | 0x0 mgmt | `0x0050002000000002` | 0x686 | 0x719 | 0x78f |
| 66 | received | 0x20 pmp | `0x0000000000000000` | 0x6a7 | 0x736 | 0x7ac |
| 68 | sent | 0x20 pmp | `0x0001000000028000` | 0x6ac | 0x73e | 0x7b5 |
| 69 | received | 0x1 crashlog | `0x0010100000004000` | 0x740 | 0x7d3 | 0x8a4 |
| 70 | sent | 0x1 crashlog | `0x0010400000004000` | 0x744 | 0x1462 | 0x84371 |

- **`#69` came 0x94 / 0x95 / 0xef µs after `#68`.** ds25p's and ds26p's `#70` is late because
  the first dump runs between `#69` and `#70`. ds26p's dump covers the 4 MiB opening.
- **`#71`, the same in all three:** `wait RAN OUT after 0x5b91ee / 0x5b8db6 / 0x5b94f1 us for
  0x000200000023b549; last word received: 0x0010100000004000`. No word came after `#69`.
- **`#72`, after the wait:** `A2I +0x8110 0x107801, PMP 0x1f0f00ff, PMS_SRAM 0x1f0000ff, PMS
  0x1f0000ff, translator +0x40 0x6000400` (ds24p, ds25p). ds26p reads the same except
  **`translator +0x40 0x80000800`**.
- **`#73`, the stop (all three):** `+0x8114 read 0x26601 wrote 0x26600, +0x48 read 0x8, +0x44 read
  0x10 wrote 0x0`.
- **`#74`:** `0x2 words received not answered`. Then `0 received messages dropped, 0 sends
  failed, 0 accesses refused`, `error -ETIMEDOUT: not started`, and probe failed with -110.
- **Later, the same in all three:** `asahi 206400000.gpu: MMU: IO map: 0x23bc00000:0x4000`, and
  `sync_state() pending due to 23bc00000.coprocessor` for `@3e0` and `@3d8` (27.6 / 28.1 /
  30.7 s).
- **Before the start, the same in all three:**
  - `#6`: domains `0x1f0000ff` ×3;
  - `#7`: SRAM `0xe4 words read, 0xb4 written back, first not as read: none`;
  - `#8`-`#17`: translator writes `+0xfc`=0, `+0xfc`=0, `+0x200`=0, `+0x2f0`=0,
    `+0x34`=`0xffffffff`, `+0x20`=`0x100000`, `+0x100`=`0x80`, `+0x13c`=`0x100`, `+0x200`=TTBR,
    `+0xfc`=1;
  - `#18`: `+0x8114 read 0x20001 wrote 0x20001, +0x44 read 0x0 wrote 0x10`.
  - The TTBRs were `0x8080ea90` (ds24p, the same as ds23p's), `0x80810ac4` (ds25p) and
    `0x8080eac0` (ds26p).
- **ds26p's words file**, read at about 25 s: `c3_058 0x444`, `c3_05c 0x666`, `c3_060 0x333`,
  `pmp+44 0x0`, `pmp+48 0x8`. These are the stock values of the three C3 words, `+0x44` as the
  client's stop wrote it, and `+0x48` as `#73` read it.

### 2. pmp's crash log (ds25p, ds26p)

The 16 KiB buffer was rebuilt from the `dump at the failed boot: crashlog +XXXX:` rows. A row
"the line above N more times" repeats the row before it, and the left-out rows are zero.
- The rebuilt buffers have `0x39bb` (ds25p) and `0x39f2` (ds26p) non-zero bytes, and
  `0xec6`/`0xed6` non-zero 32-bit words. These are the counts the client's own dump line prints.
- The "at a crashlog word" dump rebuilds to the same bytes in each boot.
- The two boots differ in 176 bytes, all inside `Ctim`, `Crg8`, `Ccst`, `CasC`, `Cmbx`
  (timestamps) and `Crtk`.
- Field names for `Crg8` are from upstream Linux `drivers/soc/apple/rtkit-crashlog.c`, `struct
  apple_rtkit_crashlog_regs`. That is documentation applied to these bytes. Its 0x350-byte size
  equals this section's content size.

**Container.**
- `+0x0`: `EHLC` (`CLHE`), then the words `0x301`, `0x850`, `0xa`; `+0x10`-`+0x1f` zero.
- Sections from `+0x20`. Each one has a 16-byte header: the reversed fourcc, `0xefefefef`, a
  word (below), and the section's size including the header.
- At `+0x830` the 16-byte container header is repeated (`CLHE 0x301 0x850 0xa`).
  - `0x850` = `0x830` + `0x20`.
  - There are 9 sections; with the trailer that makes 10 = `0xa`. This is arithmetic, and the
    meaning of these words is not read.
- From `+0x850` to the end (`+0x3fff`): `0xef` bytes. That is the fill macOS's crashlog page held
  at round 12's `late` dump.

| Offset | Section | 3rd word | Size | ds25p = ds26p? |
|---|---|---|---|---|
| `0x020` | `Cver` | `0x200` | `0x60` | same |
| `0x080` | `Ctim` | `0x100` | `0x20` | differs |
| `0x0a0` | `Crg8` | `0x400` | `0x360` | differs |
| `0x400` | `Ccst` | `0x400` | `0x40` | differs (one word) |
| `0x440` | `CasC` | `0x101` | `0x50` | differs |
| `0x490` | `Cmbx` | `0x300` | `0x1b0` | differs (timestamps only) |
| `0x640` | `Crtk` | `0x300` | `0x130` | differs |
| `0x770` | `Ccdp` | `0x200` | `0x90` | same |
| `0x800` | `Csta` | `0x100` | `0x30` | same |

**`Crg8`, registers** (content at `+0xb0`; offsets below are from the content start):

| Field | Offset | ds25p | ds26p |
|---|---|---|---|
| unk_0 / unk_4 | +0x0 / +0x4 | `0xa` / `0x33c` | `0xa` / `0x33c` |
| x0 | +0x8 | `0x80010001` | `0x80010001` |
| x1 | +0x10 | `0x4` | `0x4` |
| x2, x3 | | 0, 0 | 0, 0 |
| x4 | +0x28 | `0x104d488` | `0x104d488` |
| x5 | | 0 | 0 |
| x6 | +0x38 | `0x300000` | `0x300000` |
| x7 | +0x40 | `0x10171d8` | `0x10171d8` |
| x8, x9 | | 1, 1 | 1, 1 |
| x10 | +0x58 | `0xb0bed0ff` | `0xb0bed0ff` |
| x11 | +0x60 | `0x1c` | `0x1c` |
| **x12** | +0x68 | `0x40` | `0x104f4ec` |
| **x13** | +0x70 | `0x0` | `0xffffffffc0710000` |
| **x14** | +0x78 | `0x11b` | `0x3f889` |
| x15 | | 1 | 1 |
| x16, x17, x18 | | 0, 0, 0 | 0, 0, 0 |
| x19 | +0xa0 | `0x104d160` | `0x104d160` |
| x20, x21 | | 4, 4 | 4, 4 |
| x22 | | 0 | 0 |
| x23 | +0xc0 | `0x105b000` | `0x105b000` |
| x24 | +0xc8 | `0x9fff0000` | `0x9fff0000` |
| x25 | +0xd0 | `0x105b3d8` | `0x105b3d8` |
| x26, x27, x28 | | 1, `0x28`, 1 | 1, `0x28`, 1 |
| x29 | +0xf0 | `0x1039ff0` | `0x1039ff0` |
| x30 (lr) | +0xf8 | `0x10166d0` | `0x10166d0` |
| sp | +0x100 | `0x1039fc0` | `0x1039fc0` |
| pc | +0x108 | `0x1027a10` | `0x1027a10` |
| psr | +0x110 | `0x600002c5` | `0x600002c5` |
| cpacr | +0x118 | `0x300000` | `0x300000` |
| fpsr, fpcr | | 0, 0 | 0, 0 |
| unk[0..63] | +0x130 | non-zero only at [16] `0x3e800000000`, [18] `0x3d09000000000`, [20] `0xff`, [22] `0xff00000000`, [24] `0x100000001` | the same five, and also [0] `0x2d5e666b`, [2] `0x4bb71b00`, [4] `0x3f6999999999999a`, [6] `0xc020bb2b3461309c`, [8] `0x3fc999999999999a`, [10] `0x40800000`, [12] `0x4166e36000000000`, [14] `0x3ec00000`, [32] `0x3ff0000000000000` |
| **far** | +0x330 | **`0x36140`** | **`0x210e70000`** |
| unk_X | +0x338 | `0xffffffffffffffff` | `0xffffffffffffffff` |
| **esr** | +0x340 | **`0xbe000000`** | **`0xbe000000`** |
| unk_Z | +0x348 | 0 | 0 |

- **esr `0xbe000000`**, by the Arm architecture's ESR_ELx layout: EC `0x2f` (SError interrupt), IL
  1, ISS 0. psr `0x600002c5`: Z and C set, D, I and F masked, A not masked, mode EL1h. This is
  architecture documentation applied to the values.
- **far for an SError:** the architecture does not define FAR_ELx to hold a fault address for an
  SError exception. Whether RTKit's `far` field was written at this exception, and in which
  address space it lies, is not read.
- **The 64 unknown words** are 0x200 bytes, the size of 32 128-bit registers. Whether they are
  those registers is not read.
  - Read as IEEE-754, some of ds26p's extra words are 0.003125, -8.3656, 0.2, 12000000.0 and 1.0
    (doubles). `0x4bb71b00` and `0x40800000` read as 24000000.0 and 4.0 (floats).
  - That is a reading of bit patterns, not a decode.
- **Where the addresses fall in `Ccdp`'s first two entries** (below):
  - pc, lr and x7 lie in `0x1000000`-`0x102beff`, the entry for physical `0x23b500000`, `pmp`'s
    SRAM;
  - sp, x29, x4, x19, x23 and x25 lie in `0x102c000`-`0x105b71f` (physical `0x23b52c000`).

**`Ccst`** (content `+0x410`, u64):
- ds25p: `0xc000000000000000`, `0x1027a10`, `0x1001c70`, `0x10040c0`, `0x1025b2c`,
  `0x10193c8`;
- ds26p: the same except `0x1004124` for `0x10040c0`.
- The second value is pc. Whether this is a call stack is not read.

**`CasC`** (content `+0x450`):
- ds25p: words `0x82`, `0x5000fbfc`; u64 **`0x0600000000036140`**; word `0x3`; the rest zero.
- ds26p: `0x80`, `0x5000fbfc`, **`0x0600000210e70000`**, `0x3`.
- In each boot, the low 40 bits of the u64 equal that boot's far. The top byte is `0x06` in both.
  The meaning of the other words is not read.

**`Cmbx`, the mailbox history** (content `+0x4a0`):
- Content `+0x0`-`+0x1b` holds the words `0x27701`, `0x11111101`, `0x25501`, 0, 0, 0, 0. Their
  meaning is not read.
- From content `+0x1c` there are 16 entries of `0x18` bytes. Each is u64 endpoint, u64 word, u32
  time, u32 zero. The last 4 bytes of the section are zero.
- This layout is read from the bytes. Upstream's mailbox-entry struct is also `0x18` bytes. The
  field order was not compared with it.

| k | Endpoint | Word | ds25p time | ds26p time | Client's log |
|---|---|---|---|---|---|
| 0-6 | 0x4 | `0x0080000000000000` | `0xfba0f95` … `0xfba1cf5` | `0xfb77a6d` … `0xfb7882d` | `#50`-`#56` |
| 7 | 0x0 | `0x0070000000000020` | `0xfba1efc` | `0xfb78a34` | `#57` received |
| 8 | 0x0 | `0x00b0000000000020` | `0xfba2075` | `0xfb78bc5` | `#59` sent |
| 9 | 0x2 | `0x0080000050000010` | `0xfba21b0` | `0xfb78ce4` | `#60` received |
| 10 | 0x2 | `0x0010100000000000` | `0xfba21d0` | `0xfb78d04` | `#61` received |
| 11 | 0x2 | `0x0010100000020000` | `0xfba2361` | `0xfb78ee1` | `#62` sent |
| 12 | 0x0 | `0x00b0000000000020` | `0xfba2888` | `0xfb79414` | `#63` received |
| 13 | 0x0 | `0x0050002000000002` | `0xfba2a61` | `0xfb795f1` | `#65` sent |
| 14 | 0x20 | `0x0000000000000000` | `0xfba2c2c` | `0xfb797bc` | `#66` received |
| 15 | 0x20 | `0x0001000000028000` | `0xfba2db1` | `0xfb79961` | `#68` sent |

- **The entries match the client's last 16 logged words before `#69`**, in order. They hold no
  direction flag. The crashlog word `#69` is not in the history.
- **Times:**
  - From entry 0 to entry 15 is `0x1e1c` ticks (ds25p) and `0x1ef4` (ds26p). Over the same words
    the client's log spans `0x142` and `0x14b` µs (`#50`-`#68`): 23.94 ticks per client µs in
    both. That is arithmetic, consistent with a 24 MHz count; the clock is not read.
  - **`Ctim`** (content u64): `0xfba32b7` (ds25p), `0xfb7a6ac` (ds26p). That is `0x506` / `0xd4b`
    ticks after entry 15, about 54 / 142 µs at that ratio.
  - The client logged `#69` 149 / 239 µs after `#68`.

**`Crtk`** (content `+0x650`):
- First words `0x80000000`, `0x39`, `0x39`, 0.
- Then three records with names. Each has a value `0x800`, a second value, a count n, the name,
  and n code addresses. The count comes just before the name, and the addresses after it.

| Name | Second value ds25p / ds26p | Addresses, ds25p | Addresses, ds26p |
|---|---|---|---|
| `rtk_ep_work` | `0x3d0` / `0x410` | none (n 0) | none (n 0) |
| `power` | `0x460` / `0x460` | `0x1017418`, `0x102437c`, `0x10193c8` | `0x1019234`, `0x1019008`, `0x1024240`, `0x10193c8` |
| `main` | `0x3e0` / `0x3e0` | `0x10188a8`, `0x10191e8`, `0x102b7a4`, `0x100301c`, `0x1015a98` | the same |

- Other words: `0x1` before `power`'s record, with `0x102f3b0` just before its `0x800`.
  `0x2 0xf 0xf 0x2` and `0x10508c8` come before `main`'s.
- Neither pc nor lr is among the listed addresses. `0x10193c8` is the last of `power`'s and the
  last of `Ccst`'s.
- Which task was running at the exception is not read.

**`Ccdp`** (content `+0x780`): six records of `0x14` bytes, each u64 A, u64 B, u32 size. They
are the same in both boots.

| A | B | Size | Matches |
|---|---|---|---|
| `0x1000000` | `0x23b500000` | `0x2bf00` | `pmp` SRAM (ADT segment at IOVA `0x100000000`) |
| `0x102c000` | `0x23b52c000` | `0x2f720` | SRAM `+0x2c000` (ADT segment `0x10002c000`) |
| `0x10c0000` | `0x4000` | `0x4000` | the client's crashlog buffer |
| `0x10c4000` | `0xc000` | `0x10000` | the client's ioreport buffer |
| `0x10d4000` | `0x20000` | `0x1000` | the client's syslog buffer (`0x1000` asked) |
| `0x10d5000` | `0x28000` | **`0xf000`** | the opening word's IOVA |

- The A values are packed end to end from `0x10c0000` by the sizes in the B/size columns.
- The client's opening word `0x0001000000028000` holds no `0xf000` that this reading can see.
  Where `pmp` took `0xf000` from is not read.

**`Csta`** (content `+0x810`): 0, 0, 0, 0, `0x64`, then zero. The meaning is not read.

**`Cver`** (content `+0x30`):
- 16 bytes `43 71 1b 4c 5c a6 30 ef a0 7f e1 42 43 35 52 c3`;
- from `+0x40`: `RTKit: RTKit-2062.141.1.release - Client: not set`.

### 3. The other buffers

| Buffer | ds25p (both dumps) | ds26p (both dumps) |
|---|---|---|
| ioreport, IOVA `0xc000`, `0x10000` | `0x171` non-zero bytes, `0x91` words; **not dumped as hex** by this build | the same counts |
| syslog, IOVA `0x20000`, `0x1000` asked, `0x4000` mapped | `0x40` non-zero bytes: 16 words `0xffffffff` at `+0x0`, `+0x70`, … `+0x690` (every `0x70`), the rest zero | byte for byte the same |
| opening, IOVA `0x28000` | `0x4000` mapped, all zero | `0x400000` mapped, all zero (`0x20000` zero rows) |

- The syslog buffer holds no text. The ioreport bytes are not in the logs.
- **The translator's ERROR (`+0x40`) after the wait:**
  - `0x6000400` (ds24p, ds25p) is the value macOS's DART read in every round-12 dump, `start-pre`
    included, and ds23p's at 26 s.
  - `0x80000800` (ds26p): by the reference layout quoted in the ds23p translator section, the
    flag (bit 31) is set, stream 0, code `0x800` (bit 11). None of the five named fault bits 0-4
    is set.
  - ERROR_ADDR was not read in these runs.

### 4. Set beside round 12 (what macOS maps for pmp)

| Use | The client (buffer lines) | macOS (round 12) |
|---|---|---|
| crashlog | `0x4000`, `0x4000` | `0x18000` (one page; all `0xef` at `late`) |
| ioreport | `0xc000`, `0x10000` | `0x20000`-`0x2ffff` (four pages) |
| syslog | `0x20000`, `0x1000` asked / `0x4000` mapped | `0x34000` |
| endpoint `0x20` opening | `0x28000`, `0x4000` (ds26p: `0x400000`, to `0x427fff`) | `0x3c000`, with `0x40000`, `0x44000`, `0x48000` also mapped |
| kdebug | no line in the client's log | `0x4000`, `0x10000` |
| unnamed DRAM | — | `0x8000` |
| MMIO (34 ranges, `0xc0000000`-`0xc6003fff`) | no line in the client's log; whether it maps any is not in the log | `pmp` reg 3-43 |

**Arithmetic of the two far values** (coincidences of numbers, not readings of `pmp`'s accesses):
- **ds25p `0x36140`:**
  - `0x36140` = `0x28000` + `0xe140`.
  - The client's opening mapping ends at `0x2bfff`, so `0x36140` is `0xa140` bytes past its end.
  - `pmp`'s `Ccdp` entry for the opening (`0x28000`, `0xf000`, so to `0x36fff`) contains it.
- **The same offset on macOS's layout:**
  - `0x3c000` + `0xe140` = `0x4a140` = `0x48000` + `0x2000` + `0x140`.
  - That is byte 0 of slot 20 (`0x140` / `0x10`) of the (IOVA, size) table. Slot k is `pmp` reg
    k+3, so slot 20 is **reg 23**: IOVA `0xc2070000`, size `0x4000`, physical `0x210e48000`.
  - macOS's `0x3c000` + `0xf000` = `0x4b000` covers that table (`0x4a000`-`0x4a28f`).
  - In ds25p the client's IOVA `0x36140` is not mapped (its log has no DART fault line).
- **ds26p `0x210e70000`:**
  - The client's 4 MiB mapping covers `0x36140`, with zeros there.
  - `0x210e70000` lies inside `pmp` reg 22 (`0x210e20000`, size `0x60000`) at `+0x50000`, which
    macOS maps at IOVA `0xc2060000`.
  - Its low bits `0x70000` equal those of reg 23's IOVA `0xc2070000`.
  - It is not a client IOVA.
- `0x6000400` and the stream-6 reading apply equally to macOS's healthy boots, so ERROR in ds24p
  and ds25p does not mark a fault by itself.

### What these readings do not show

- Why `pmp` raised the exception, or what it was doing. The register values and section names
  are bytes, decoded by upstream's struct and the Arm ESR layout only.
- Whether `far` is meaningful for this SError, and in which address space (IOVA, `pmp` virtual,
  or physical) `0x36140` and `0x210e70000` lie. The `Ccdp` and round-12 arithmetic only shows where
  the numbers fall.
- What `pmp` expected in the opening region. The client's opening buffer was zero at both dumps
  in both boots, where macOS's page set held the `+0x2000` block at `0x3c000`, the window table at
  `0x48000`, and so on.
- The ioreport buffer's bytes; ds24p's crash log (its buffer was reused before it was read).
- The translator's page tables and ERROR_ADDR in these boots.

### M1 left

Not read by this agent. The orchestrator rebooted the M1 to the stock kernel after each run.
