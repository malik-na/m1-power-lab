# macOS 13.5's wake path under the hypervisor, and its last second before sleep (run 135r2, 2026-11-16)

macOS 13.5 under the m1n1 hypervisor (`~/m1n1` bd6a43d4 + 31359cdc, bb15bb28, 1eb39afa), real S2R
pass-through, one sleep (`pmset sleepnow`, 18:5x). Trace `tools/hv-trace-kit/runs/20261116-mac135/`
(private: s2r-trace-135r2.jsonl, run-135r2.out).

## The wake: sequences 10 and 11, not 4-7

Read by the host right after the reconnect, before the guest ran again:

```
[s2r] at the wake: breadcrumb 0x8000000 progress 0x22  WD2 cnt 0x19c02be cmp 0x7270e00 ctl 0x0
      AOP 0x1c 0xff0  wake status 0x0 0x400000 0x0
```

- Progress 0x22 is the last code sequence 10 writes (0x120bc), right before its closing AOP
  handshake (0x54, 0x50, poll bit 3 clear) and its exit breadcrumb. The breadcrumb register
  holds one bit, the last one written: bit 27 is past sequence 11's entry (bit 22); sequence 11's
  tail is not decoded (the decoder stops at 0x162c8).
- WD2: compare 5 s (0x7270e00), control 0 (disarmed), count 1.13 s since the last arm.
- Sequence 10 is the S2R_AOP -> AWAKE path. Its first steps: arm WD2 for 5 s, PMGR+0x34000 writes,
  progress 0x21, **power chip 0x0201 = 00**, **second power chip 0x2808 = 05**.

**What this says about Linux.** Every Linux run comes back from its restart with 0x0201 = 01, the
value sequence 1 writes. So under Linux, sequence 10 never reached its first power-chip write, and
sequence 5 (0x0201 = 02) never ran either. Either the chip sat in S2R_AOP/AOP_DDR until the reset,
or a wake sequence stalled before its power-chip write: sequence 4 arms WD2 for 5 s and then waits
for the AOP (`0x23d2c001c = 0x15`, poll `& 0xaa0 == 0x20`).

**Correction to runs 36-38.** `wd2_extend_s=100` moved only the deadline sequence 0 had set.
Sequences 4, 6 and 10 arm WD2 again for 5 s on entry. "Not watchdog 2" holds only for sequence 0's
arm; a stall in sequence 4 would still be a WD2 reset ~5 s after it starts. Runs 36-38's restart
~5.5 s after the release is consistent with that.

## macOS's last second before the commit (13.5)

| t (s) | Coprocessor | Messages |
|---|---|---|
| 635.767 | SMC | MBSE slpw |
| 635.817 | SIO | ep0x20 per-channel stops (0x11..0x15) |
| 635.888 | AOP | 0xa4 to ep 0x22, 0x21, 0x26, **each answered 0x87** |
| 635.929 | AOP | **0xa2 to ep 0x24 and 0x25** (a command in their rings), answered 0x85 |
| 635.950 | PMP | 0x20e 0x54/0x55 notifications; DCP/DCPEXT AP power 0x20, queues 0xa3 |
| 635.980 | SMC, PMP | WKTP = 02; PMP 0x208 0x63, answered 0x209 |
| 636.012 | AOP | 0xa4 to ep 0x28, 0x24, 0x20, 0x25, each answered 0x87 |
| 636.134 | AOP | 0xa4 to ep 0x27; AOP syslog (ep 2) 0x50 messages echoed; 0x87 |
| 636.139 | AOP | AP power 0x201, echoed |
| 636.160 | ANS (NVMe) | syslog echoed; AP power 0x201; **IOP power 0x201**, acked |
| 636.246 | SMC | MBSE slpa; AP power 0x201 |
| 636.250 | power chip | 0x9f01 = 0x50 |
| 636.280 | SIO | AP power 0x201; IOP power 0x201, acked |
| 636.283 | PMP | AP power 0x201; IOP power 0x201, acked |
| 636.32 | AP | CPU_START, PS writes, RTC alarm, last core down |

Linux (aop.rs `QUEUE_OP`) sends 0xa4 to the same eight endpoints at once, waits for no answer, never
sends the 0xa2 commands to 0x24/0x25, and sends AP power 0x201 50 ms later.

## Next

1. Capture the content of macOS's 0xa2 commands to ep 0x24/0x25 (tracer `S2R_AFK_DUMP=1`: reads
   the AFK ring entry behind each AP doorbell through the AOP DART).
2. One Linux run with the AOP quiesce done as macOS does (the 0xa2 commands, the stops in its
   order with each answer waited for, AP power 0x201 acked), plus the other coprocessors' 0x201
   states from the table.

## Runs 135r5 and 135r6: what macOS writes to AOP endpoints 0x24 and 0x25 (repeated, identical)

The tracer reads the AFK ring entry behind each AP doorbell from a synchronous hook on the AOP send
registers (135r3 crashed the session doing the read from an async event; 135r4 failed on the
state it left). Both runs slept and woke with the same signature as 135r2 (breadcrumb 0x8000000,
progress 0x22, WD2 off, AOP 0x1c 0xff0, wake status +0x20 = 0x400000): three of three.

Endpoint 0x24 is the ambient light sensor and 0x25 the lid angle sensor (Linux aop_als.rs: property
0x00 = report interval in µs, 0x16 "batch interval", 0x5c "raw interval"). Before the sleep, ALS
reports arrive every 0.389 s. Times relative to MBSE slpw:

| t (s), 135r5 / 135r6 | Endpoint | Ring entry (EPIC set property) |
|---|---|---|
| -6.69 / -6.72 | 0x24 ALS | 0x16 = 0; 0x5c = 0; **0x00 (interval) = 0**; ALS reports stop |
| +0.16 / +0.17 | 0x25 LAS | **0x00 (interval) = 0** |
| +0.17 / +0.18 | 0x24 ALS | 0x00 = 0 again |
| +0.13..+0.41 | all eight | 0xa4 stops, each answered 0x87 (the order of the first two batches differs between runs) |
| +0.41 / +0.41 | mgmt | AP power 0x201, echoed |

After the wake macOS writes ALS 0x16 = 10000, 0x5c = 0, 0x00 = 200000 and the reports resume.

Linux: aop_als.rs sets the interval to 200000 µs at probe and has no suspend path; aop_las.rs has
none either. If the modules are bound (they are built for the run kernels: aop_als.ko, aop_las.ko;
whether they were loaded in runs 36-38 is not recorded), the AOP keeps sampling and reporting
through Linux's sleep. A sensor report needs the AOP's DRAM ring, which is the S2R_AOP -> AOP_DDR
transition (sequence 4, WD2 armed, AOP handshake). This is the leading candidate, not yet tested.
