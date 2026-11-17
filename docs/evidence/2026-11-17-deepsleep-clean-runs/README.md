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
