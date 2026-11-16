# Run 28: releasing fpwm1 brings back run 19's stuck domain (2026-11-16)

Run 27b with one change: `pmgr_pwrstate.always_on=fpwm1` removed (the hold run 22 added because,
in run 19, ps_fpwm1 switched off "stays busy, 0xa00"). Kernel 7.2.11-run26, 13.5 firmware, cable in,
cold start (0x0201 = 04, boot bec45b8a), lab job j1116-004642-2671, force-discharge set at the gate
(06:27:15.19, read back Discharging -0.39 A). Before the gate, with the hold released, fpwm1 read
0x000002ff (on: the backlight PWM driver itself holds it while awake).

## Result

- ENTRY 06:27:24.250. The driver refused in its last-stage precheck and undid the entry:
  trace `fail precheck 0x23b7001e0 0xa00` (Fail::Precheck = 6 on FPWM1_PS), stage byte 0x9f0a = 0x06.
- The machine came back into the same boot (no reset): verdict `RETURNED`, Wi-Fi silent 23 s,
  no Thunderbolt host loss until the lab's own reboot at 06:31:02. 0x0201 stayed 04; the RECORD
  bytes stayed 0 (cleared, never written).
- So under 13.5 firmware too, once Linux switches fpwm1 off at suspend its power word reads 0xa00:
  actual and target 0 but bit 11 (m1n1 pmgr.py: PARENT_MISSING) and bit 9 (WAS_CLKGATED) set. The
  sleep program waits for bit 11 = 0 on every domain it switches off, so the driver refuses.

## What it establishes

The two stuck states are linked to the SIO island: held on (runs 22, 27b) the domain lets the
sequence through its power-state checks but island gate #45 never reports ready; released (runs
19, 28) the domain itself stays flagged with bit 11 when Linux turns it off. Next: which parent of
ps_fpwm1 is off when Linux turns it off (bit 11 = parent missing), i.e. the order in which Linux
powers the SIO island down versus the order the chip's sleep program uses.
