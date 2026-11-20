# Milestone 3 report: the Secure Enclave at Linux's commit (2026-11-20)

Probe lane. 5 M1 boots (2 sleeps; run 5 on Naeem's "Yes, build it"), 2/4 agents, 2/2 builds.
`probe/m3-sep` `ecbbcc4aa` (local, never merged). Cards `docs/experiments/2026-11-20-m3-sep-*.md`;
raw `var/milestone3/`; `tools/tb/probe-run/m3run.sh` (modes read, msg, rmmod, idle).

## Finding

The SEP is ruled out. Gated as macOS's (`0x1000230f`) before the entry and at Linux's commit,
sequence 0 still does not start: `0x0201` 04 -> 04, back at 165 s (run 5). By the stop condition
the deep-sleep work stops: no known difference from macOS remains.

| Run | What | Reading | Outcome |
|---|---|---|---|
| 1 | entry as milestone 2 (cand `0xffffe`), k 172 | before `0x1f0022ff`; at core 0's last write `0x1f0020ff`, `0x23b74c200` low byte 4; 04 -> 04; 166 s | SEP fully on at the commit |
| 2 | sleep request, tag `0x7f` | no reply, no SEP message after; `0x1f0022ff` | no sleep started |
| 3 | sleep request, Aurora's tag 8 (`0x020c0800`) | the same | no sleep started |
| 4 | `rmmod apple_sep`, wait 50 s | `0x1f0022ff` throughout | no sleep started |
| 5 | `apple_sep.xart_guard=0`, nothing sent | before `0x1000230f`; at the commit `0x1000230f`, `0x23b74c200` 4; 04 -> 04; 165 s | SEP gated as macOS: no sequence 0 |

## Why runs 2-4 could not gate it

The probe tree's apple_sep guards xART on T8103 (level 1). It refused the enclave's rewrite of a
kind-4 record at 14.47 s, and after that the enclave answered nothing: LOAD_CATACOMB,
REGISTER_SERIAL and the sleep request all timed out. omacom/linux-aurora#506 records the same
silence after a refused locker. The stock kernel (linux-aurora 7.3.0-aurora0test5) runs with the
guard off on M1. With `xart_guard=0` the probe kernel's enclave finished its bring-up (sensor
bound) and gated itself, as on stock.

## Notes

- The message: Aurora `linux-integration` `1f38ff8f4` `proto.rs` `op_sleep` (endpoint 0, type `0x0c`,
  param 2; reply type 1, same tag). It was never answered here, so whether t8103 answers it is
  unknown; macOS sends no SEP message anyway.
- The safety check found that the probe's trigger ran before any watchdog was armed. Closed
  before run 2 by holding watchdog 1 at 120 s; runs 2-4 came back on stock by it, no hands.
- `0x23b74c200` read 4 (bit 2 set) in every state: SEP on, gated, stock idle.

The M1 is on its default kernel (stock Omarchy, up since 05:54:32), and the claim is released.
Kernel trees stay local.
