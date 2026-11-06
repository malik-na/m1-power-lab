# PMU RTC wake test, run 2 (j1106-045307-bccd): did not run

maclab reported the job as "hung". It was not a kernel hang:

- UPower's history on the M1 shows the battery at 4% at 10:26 IST, draining
  at 3.2 W, when the Mac rebooted into the test kernel. It did not come back
  until the charger was connected (about 10:56).
- The test kernel then booted normally. Its journal starts with the clock
  systemd saved at shutdown (10:26), and rtc-macsmc set the real time
  (10:56) 4 s into boot. maclab's no-contact deadline (armed at 10:26) had
  passed, so the deadline service rebooted to the known-good kernel at once.
  The test script never ran.
- With the new kernel (`f5035a3`), the boot log shows the NOTIFY message as
  a warning only, and the PMU alarm state read cleanly:
  `firmware alarm state: ctrl 0x01 alarm 0x002996fa event 0x00 mask 0x00`
  (the alarm run 1 armed, disarmed; MONITOR left set).

Why the battery was empty: from 05:28 to 10:26 the M1 drew a steady
3.1-3.5 W (UPower rate history), with the panel on. Omarchy's idle
(screensaver at 150 s, lock at 300 s) never ran on any boot: the shell logs
`stay-awake: enabled state-file` and `idle-cycle-cancel: stay-awake`. The
state file `~/.local/state/omarchy/indicators/stay-awake` was created on
2026-11-04 15:57 by the bar's stay-awake toggle; nothing in m1-power-lab
writes it. Left as is (the owner's setting).

The 3.2 W is also about 1.3 W more than the panel-on cost measured on
2026-11-05 (about 1.9 W at backlight 16, static image); not explained yet.
