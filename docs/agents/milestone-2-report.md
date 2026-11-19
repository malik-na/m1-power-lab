# Milestone 2 report: what the always-on engine waits on after Linux's cores go idle (2026-11-20)

Probe lane. 8 of 8 M1 runs, 0 of 1 hypervisor runs, 5 of 12 sub-agents, about 0.85M of 150M
sub-agent tokens, 2 probe builds. Branches in `~/Work/dsk-probe-m1-leads` (never merged):
`probe/m2-aop` `a9680e86b`, `probe/m2-cache` `e1442a487`. Cards: `docs/experiments/2026-11-20-m2-*.md`.
Runs: `var/milestone2/runs.tsv` and `run<N>-start.txt` / `-after.txt`.

## Finding

No lead starts sequence 0. In all 8 runs `0x0201` read 04 before and after, and the stock kernel
came back 165-166 s after the start (watchdog 1). There was never a 5 s reset. With every
change below, the engine still takes the cores going idle, stops watchdog 2 and never enters
AWAKE->AOP_DDR.

## The leads

| Lead | Reading on the M1 (run) | Verdict |
|---|---|---|
| 1 Always-on words at the commit, macOS against Linux | 20 of 24 equal: AOP config `0x23d2c0000`-`3c`, the S2R timer, `0x23d2b8028`/`040`, watchdog 2, `0x23d0d9378`, MSG, ATC1, NUB words. ATC0_USB_AON/ATC0_USB differ (Linux turns them off; left on, run 6-7: no change). Cluster words differ from the 0 macOS writes, but macOS's value at its commit was never read (3, 6, 7, 8) | out |
| 2 The 11 SMC shared-memory writes | One slot of a 17-slot log ring (11 words, time, code, two kernel pointers), written 2818 times in det33 by one function, with no mailbox write after it (desk, `var/commit-state/r10-det33-detached.txt`) | out (a log) |
| 3 The engine's cores-idle window | Core 0 held 20 ms and 50 ms: no watchdog-2 reset. Held 3 s (milestone 1): reset at 5 s. The window is 50 ms to 3 s; Linux's 1.65 ms is inside it (1, 2) | out (timing) |
| 4 The AOP | Clean-room kernels never told it "AP power `0x201`" (`CONFIG_APPLE_S2R_RS` is off). Tried that alone and after the old driver's sensor and queue stops; the AOP echoed and the SMC handshake (slpw, slpa, AP `0x201`) succeeded (3, 4) | out (not sufficient) |
| Old driver: L1 clean before WFI | Set/way clean+invalidate with the cache off, on every core (5) | out |
| Old driver: first port's domains on | Left on as found (`0x2ff`, 6). With the L1 clean and the AOP sequence too (7) | out |
| P cluster `0x23b718004` | `0x10` at once, `0x50` 50 ms later (4, 5, 8). The old driver's run 26 read P `0x50` as well | unlikely (meaning of `0x50` not known) |

Source note: the old driver's L1 clean is known only second-hand: its team's plan
(`var/catchup/PLAN.md` 149-153) and status board (`var/catchup/hv-STATUS.md` 103) describe the
old code. That ATC0 was on at the old driver's trigger is an inference from run evidence. The
off-limits trees were not opened. Details: side notes `old-vs-clean-entry.md`.

## What remains unread

- The Secure Enclave. The old driver sent it a sleep message and waited for its domain
  `0x23b700c00` to read gated before every entry, and some of its runs reached sequence 1. The
  clean-room entry leaves the SEP on (`0x1f0020ff`) or forces its domain down (C1) without a
  message. Its value at the commit, and PMGR `0x23b74c200` bit 2 (an unverified "wait for the
  SEP's power gate"), are not read.
- The E cluster word `0x23b718000` raw (k 156), and macOS's cluster words with its cores down.

## Recommendation

By the stop condition (memory, 2026-11-19), this milestone gave no solid next step: the
deep-sleep work stops here. The one difference still unread is the SEP. Testing it would take
2 runs: read `0x23b700c00` and `0x23b74c200` at the commit, then gate the SEP by message before
the entry, as the old driver did. That is Naeem's choice to make. Not the build lane: nothing
here has made sequence 0 start.

## Left over

- The M1 is on its default kernel (stock Omarchy), claim released, after this report.
- `tools/tb/probe-run/onerun.sh` worked for all 8 runs; `m1-cand-runs` was not used or fixed.
- The probe branches are committed locally in the probe worktree and not pushed (kernel repos stay local).
