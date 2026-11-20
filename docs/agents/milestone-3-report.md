# Milestone 3 report: the Secure Enclave at Linux's commit (2026-11-20)

Probe lane. 4 of 4 M1 boots (1 sleep), 2 of 4 sub-agents, 2 of 2 probe builds (the first failed
to compile). Branch `probe/m3-sep` `ecbbcc4aa` in `~/Work/dsk-probe-m1-leads` (never merged).
Cards: `docs/experiments/2026-11-20-m3-sep-at-commit.md`, `2026-11-20-m3-sep-sleep-message.md`.
Runs: `var/milestone3/runs.tsv`, `run<N>-pre.txt` / `-start.txt` / `-after.txt`. Script:
`tools/tb/probe-run/m3run.sh` (modes read, msg, rmmod).

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

## Prior art

The message comes from Aurora (`linux-integration` `1f38ff8f4`, `drivers/soc/apple/proto.rs`
`op_sleep`: endpoint 0, type `0x0c`, param 2; reply type 1, same tag; its T8140 commit then
waits for the domain's bit 10). The lab's old plan records the same message with tag 1
(`var/catchup/PLAN.md` 22-23). The old 13.5 runs gated the SEP by unloading its driver, and the
enclave gated itself 1.4-3 s later (`var/run22-src/run22.sh` 20-26, run26 README).

## Why the probe kernel's SEP stays on: not read

On every probe boot the SEP's Touch ID sensor bring-up fails (REGISTER_SERIAL ETIMEDOUT,
"retrying in 10 s"), and the entropy survey reads EIO, though the SEP answers other control
requests (they come back as zeros). On stock, apple-mesa binds the sensor and the SEP gates.
That the failed sensor holds the SEP on is an inference.

## Safety

The safety check found one gap: the trigger and the polls ran before `begin` armed watchdog 1.
It was closed before run 2: `/dev/watchdog0` is held open at 120 s, and `start.sh`'s unbind stops
it. Runs 2-4 each came back on stock by that watchdog, with no hands needed.

## Next step (Naeem's pick)

By the stop condition the deep-sleep work stops, unless Naeem takes the one remaining step: one
run of the message card on a kernel whose SEP gates when idle (`0x1000230f` before the entry),
with the deep-sleep driver as in run 1, then read `0x0201`. Getting there means finding why the
probe kernel's SEP stays on (the sensor, the stock kernel's apple_sep and apple-mesa against the
probe tree's). That is new work beyond this milestone's budget.

## Left over

The M1 is on its default kernel (stock Omarchy, up since 05:29:26), and the claim is released.
Kernel trees stay local.
