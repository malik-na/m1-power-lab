# Milestone 3 report: the Secure Enclave at Linux's commit (2026-11-20)

Probe lane. 4/4 M1 boots (1 sleep), 2/4 agents, 2/2 builds. `probe/m3-sep` `ecbbcc4aa` (local, never
merged). Cards `docs/experiments/2026-11-20-m3-sep-*.md`; raw `var/milestone3/`; `tools/tb/probe-run/m3run.sh`.

## Finding

The SEP is not ruled out, and not shown to be the gate. Linux's SEP is fully on at the commit
(macOS's is gated), and on the probe kernel it could not be gated by message or by idling, so no
commit with the SEP gated was run.

| Run | What | Reading | Outcome |
|---|---|---|---|
| 1 | entry as milestone 2 (cand `0xffffe`), k 172 | before: `0x23b700c00` `0x1f0022ff`; at core 0's last write `0x1f0020ff` (request f, state f, bit 28), `0x23b74c200` low byte 4; `0x0201` 04 -> 04; back at 166 s | SEP fully on at the commit, despite C1 |
| 2 | sleep request, tag `0x7f` (`0x020c7f00`) | no reply in 5 s, no SEP message after; word `0x1f0022ff` | no sleep started |
| 3 | same, Aurora's tag 8 (`0x020c0800`) | the same | no sleep started |
| 4 | old recipe: `rmmod apple_sep`, wait | `0x1f0022ff` in 30 polls over 50 s | no sleep started |

Stock Omarchy on the same machine, SEPOS booted and idle: `0x23b700c00` = `0x1000230f` (macOS's
value), `0x23b74c200` = 4 (read 04:58 and 05:29:48).

## Notes

- The message: Aurora `linux-integration` `1f38ff8f4` `proto.rs` `op_sleep` (endpoint 0, type `0x0c`,
  param 2; reply type 1, same tag); the old plan has it with tag 1 (`var/catchup/PLAN.md` 22-23).
- Why the probe kernel's SEP stays on: not read. Every probe boot its Touch ID sensor bring-up
  fails (REGISTER_SERIAL ETIMEDOUT) and entropy reads zeros (EIO); on stock apple-mesa binds the
  sensor and the SEP gates. The sensor holding it on is an inference.
- Safety check gap (trigger before `begin`'s watchdog) closed before run 2: `/dev/watchdog0` held
  at 120 s; runs 2-4 each came back on stock by it, no hands.

## Next step (Naeem's pick)

Stop (the stop condition), or one more step: find why the probe kernel's SEP stays on (stock's
apple_sep/apple-mesa against the probe tree's), then one run with it gated (`0x1000230f`) before
the entry and `0x0201` read. New work beyond this milestone's budget.

The M1 is on its default kernel (stock Omarchy, up since 05:29:26), and the claim is released.
Kernel trees stay local.
