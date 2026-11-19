# Coprocessors around the sleep: sio, dcp, dcpext, gfx-asc, ans, aop, smc, sep

macOS tells six coprocessors to idle and stops them by register before the commit; `aop` and `smc` only get a notice; `sep` gets nothing.
2026-11-20. `pmp` has its own card (`pmp.md`); this card covers the rest and the rules shared with `pmp`.

## Established

Every coprocessor has a control page (+`0x44` run bit 4, +`0x48` status) and a mailbox (+`0x8114` I2A control, bit 0 receive enable). [section 0]
Addresses read: `sio` `0x236400000`, `dart-sio` `0x235004000`, `gfx-asc` `0x206400000`, `dcpext` `0x271c00000`, `smc` mailbox `0x23e408800`. [1.9; E2a; spec line 1559]

| Coproc | Linux on the M1 | macOS's entry | macOS's wake |
|---|---|---|---|
| `sio` | Running awake on stock once the loader's tree had the `sio` alias (boot.bin `0a1e47f3`) [memory m1-s2r-stuck-islands, 11-16 07:57]; at the driver's entry its three domains read `0x0f000200` (off) [L15]; ds7: Linux's driver failed to start it (-ETIME) [L6] | R4, then R5's register stop; R10's `dart-sio` steps [R4; R5; D3 (b)] | R5w: +`0x8114`=`0x20001`, +`0x44` 0->`0x10`, boots [R5w; W3] |
| `dcp` | Running at the driver's entry: +`0x44` `0x10`, +`0x48` `0x2d` [L15] | R4 + endpoint stops `0x00a4…` on `0x20`-`0x2c` (each answered `0x0087…`), then R5a; `dart-dcp` +`0xfc` streams off [R5a] | restarted, endpoints started, stopped again by R5a; dark wake: stays stopped, domains off; key wake: started and left running [R58] |
| `dcpext` | Running, domains on [L15] | as `dcp` [R5a] | as `dcp`, but stays stopped after key wakes too [R58] |
| `gfx-asc` | GFX on awake; `0x0f002b00` (off, bit 11) at the driver's entry [L14; L15] | R4, R5a [R4; R5a] | boots at W+3.83 s [section 6, W4] |
| `ans` | ANS2 on awake; `0x0f002300` at the entry [L14; L15] | R4, R5a; APCIE_ST off [R5a; R7] | boots at W+3.84 s, APCIE_ST on [W4] |
| `aop` | an earlier driver had `aop_als` bound (43 lux) [memory m1-s2r-stuck-islands, run 39] | AP power `0x201` only; no +`0x44`/+`0x48` access [R4; section 0] | AP power `0x20`; endpoints restarted `0x00a3…`/`0x0086…` [W4] |
| `smc` | its entry messages under Linux not read [4.4a C16] | key `MBSE` = "slpw", then "slpa"; AP power `0x201` [R3; R4; 4.4a C16] | AP power `0x20` echoed; `MBSE` = "waka" `0x77616b61` [W3] |
| `sep` | SEP domain `0x1f0020ff` (fully on) before the entry [C1] | no message; never +`0x44`/+`0x48`; its domain `0x1000230f` (power-gated by automatic power) awake and at the commit [C1; R4] | domain written `0x1000200f`; boots at W+3.81 s [C1; W4] |

- R4's exchange is exactly: send `0x00b0000000000201`, echoed; send `0x0060000000000201`, answered `0x0070000000000201` (endpoint 0). [R5a, round 7]
- The register stop (R5, R5a): +`0x8114` written with the value read, bit 0 cleared; +`0x48` read (`0x2e` in all 76 stops); +`0x44` read `0x10`, written 0. [R5; R5a]
- macOS never met a stopped or silent coprocessor; what +`0x48` reads then is not observed. [R5; D3 reasons (1)]
- Linux's `dcp`/`dcpext` read +`0x48` `0x2d` where macOS read `0x2e` before its stop. [L15]
- Aurora's T8140 driver refuses a sleep unless `dcp`, `dcpext`, `pmp`, `sio` have run bit clear or domain off; "a commit with the PMP and SIO still running reset the SoC 5.5 s later". [deep-dive 2.2, Coprocessors]
- The 11 writes macOS makes to SMC shared memory `0x23fe5f1f8`-`220` after its last `0x23d2c4000` write (and the 22 at `0x23fe5f098`) are slots of a log ring: 17 slots of 11 words (`0x23fe5f040`-`0x23fe5f32b`; time low/high, a code `0x61f00xx`, two kernel pointers, two counts, two flags), each slot written by the same 11 stores (pc `0xfffffe0014beaaec`-`b3c`), 2818 slots over det33's run; no SMC mailbox write follows them. A log, not a sleep step: lead 2 of milestone 2 is out (inference: the SMC could still read the ring, nothing tells it to). [var/commit-state/r10-det33-detached.txt, `grep 0x23fe5f`; spec E6 step 4, line 2086]
- Clean-room kernels (ds20-ds29, the milestone-1 probes) never send the AOP "AP power `0x201`": the AOP's sleep hook (`drivers/soc/apple/aop.rs` `s2r_hook`, line 2436) is built only with `CONFIG_APPLE_S2R_RS`, which their config leaves out; Linux boots the AOP itself and it runs at the entry ("AOP IS READY"). The old driver (s2r_rs) sent it, with sensor and queue stops, and its runs read `0x0201` = 01. The SMC's handshake is in `macsmc.c` (any mem suspend). [~/.cache/m1-s2r-kb/io-clean/config; var/commit-state/ds28-all-dmesg-20261119.txt 1063-1128; evidence 2026-11-16-run39-aop-sensors; ~/Work/dsk-probe-m1-leads drivers/mfd/macsmc.c 595-665]
- With the clean-room entry plus the AOP told "AP power `0x201`" (echoed), and with the old driver's whole AOP sequence (sensors off, 8 ordered queue stops, then `0x201`), and the SMC handshake succeeding (slpw, slpa, AP `0x201`): sequence 0 still does not start (`0x0201` 04 -> 04, back at 165 s). The AOP and SMC messages are not the gate [docs/experiments/2026-11-20-m2-aop-ap-power.md, milestone-2 runs 3-4].

## Decided

- Found running: the driver does what macOS does, messages included. Found stopped: nothing is sent. Silent: a bounded wait, then the register stop. Domain found off: not touched. [D3]
- `sio` or `pmp` found stopped (domain on, +`0x44` bit 4 clear): no message, no write to control page, mailbox or translator, no R6; at the wake no R6w, R55, R5w; for `sio` no `dart-sio` access and no W1-8. [D3 (b)]
- `sio` or `pmp` found silent: register stop, then R73's two +`0xfc` writes and R6 (`pmp`) or R10's `dart-sio` part (`sio`); at the wake R6w and R55 / W1-8, but no R5w: it stays stopped. [D3 (c)]
- The wake does not restart `dcp`, `dcpext` or any R5a-stopped coprocessor; their own Linux drivers do. D1 still puts the domains back. [D2]
- `sep`'s domain is lowered by R56 form 2 after the last stop, behind switch `cand_c1`. [C1]
- `sio`'s family is turned on (not `sio` itself) behind `cand_c12`. [C12]
- Code: `~/Work/deepsleep-kernel` `52669b5bb`, `drivers/soc/apple/deepsleep/logic/mailbox.rs` (messages, stops) and `coproc.rs` (state reads before the entry). [their headers]

## Open

- What each coprocessor answers under Linux, and how long it takes. Settled by logging R4's replies in a Linux entry. [open questions 38, 50; D3]
- What `sio` does once its domains are on under Linux (+`0x44`, +`0x48` there). Settled by one read with `cand_c12` on. [C12 "Not observed"; L6]
- What Linux's display driver does with a `dcp` found stopped after the wake. Settled by a wake that reaches Linux. [D2]
- The `smc` outbox at Linux's commit (Aurora: a queued event wakes at once). Settled by reading the `smc` entry messages and outbox in a Linux run. [4.4a C16; deep-dive 3.5]
- Whether `sep` at full power blocks the power-down on the M1 (Aurora T8140: "a commit with it running never returned"). Settled by a run with `cand_c1` on and the SEP word read at the commit. [C1]

## Read more
- Spec `docs/spec/macos-13.5-sleep-wake-observed.md` R4-R6 (lines 4032-4080) and D2-D3 (lines 4897-4975).
- Spec section 3 "E2a. How a coprocessor is stopped before its domain goes off" (line 1758).
- Spec R58 (line 4495) and section 6 "W4. Drivers power up" (line 3660).
- Spec L15 (line 8193): the coprocessors' words under Linux at the driver's entry.
- `docs/reference/asahi-aurora-sleep-deep-dive.md` sections 2.2 (Coprocessors) and 3.6.
