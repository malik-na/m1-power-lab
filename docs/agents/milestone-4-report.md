# Milestone 4 report: Aurora's pre-commit steps, one batch (2026-11-20)

Probe lane; 4/4 runs + 1, 2/2 builds + 1, 4/5 agents + 2 (run 5 on Naeem's word). `probe/m4-batch` `59394c943`, `0ac81077f`, `73589d996` (local, never merged). Cards `docs/experiments/2026-11-20-m4-*.md`; raw `var/milestone4/`.

## Finding

None of the steps starts sequence 0, nor does a commit with no device access after it (run 5). With all of them on together, plus cand `0xffffe`, the SEP
gated (`xart_guard=0`, `0x1000230f`) and m1fix 11 (macOS's wake masks, AMCC clear, ATC0 as found):
`0x0201` 04 -> 04, stock back 165 s after the start, in every run.

| Item | Built | Reading | Outcome |
|---|---|---|---|
| 1 debug link cut | read only | DEBUG_USB `0x23d2800b8` state 0 at the commit, cable in, as macOS | Aurora's test would not cut; no cable-out run |
| 2 last WFI (timers, IPI_SR, AIC ack) | yes | core 0: no FIQ/IRQ/timer/IPI pending at its last write | ruled out |
| 3 BUSY-latched PS words | yes | 0 of 137 ADT words latched before R22 | condition met; ruled out |
| 4 `0x23d2b8008` = 0 | yes | 0 at the commit; value before the write not read | 0 does not start it |
| 5 AIC masked after the commit | yes | re-mask ran (R36 had masked all already) | ruled out |
| 6 PMC voters | no | no t8103 word named | not built |

| Run | Kernel, switches | k | Reading |
|---|---|---|---|
| 1 | m4batch, m4fix 31 | 173 | `0x99206000`: above, and one wake bit pending+unmasked at core 0's last write |
| 2 | same | 180 | 0: not in wake word 1 (not the alarm line) |
| 3 | m4batch2, m4fix 63 (masks pending sources) | 185 | `0x80000000`: none pending at the commit-point step |
| 4 | m4batch2, m4fix 31 (run 1's) | 186 | `0x80000000`: none pending at core 0's last write |

Run 1's bit did not repeat: in runs 3-4 nothing was unmasked and pending (C14 met), still 04.

Not covered: the cable out (the software cut is "not clearly safe" for the M3, the safety check:
fast repeated re-attach never tried; a pulled cable needs Naeem); k 174 (runs went to the wake bit).

## Run 5 (Naeem's "Yes, run it"): the quiet commit
Build 3 `73589d996`, m4fix bit 6: no device access from R38's third write to the WFIs (no SPMI
record, no re-arm; watchdog 1 armed in begin). 04 -> 04, 166 s, 'Da' standing: ruled out.
Still open: watchdog 1 armed at the commit (macOS off; armed it slept, R61); the cable in.
## macOS's words (from existing captures; the hypervisor run is blocked)
macOS writes `0x23d2b8008` = 0 at T-18 ms (det36), as m4fix bit 3; watchdog 1 control 0 (K);
cores 0-7 ISR 0, IPI_SR 0 (det18). Cluster words at its commit: not read; the macOS volume now
boots macOS natively, no m1n1 proxy (2026-11-20-m4-macos-cluster-words.md).
The M1 is on its default kernel (Omarchy stock, up since 07:44:31), claim released.
