#!/bin/bash
# Follow-up to m1power-s2r-mem.sh, run as root on the boot after the attempt
# (lab exec or ssh). Prints the pre-sleep snapshot and what the PMU and the
# logs say about the sleep: the stage letter the driver left in 0x9f0a, the
# RTC alarm event latch 0xd00c, boot_stage, and the time from the entry to
# this boot.
set -u
STATE=/var/lib/m1power-s2r
NV=$(ls -d /sys/bus/nvmem/devices/spmi_nvmem* 2>/dev/null | head -1)
pmu_at() { [ -n "$NV" ] && dd if="$NV/nvmem" bs=1 skip=$(($1)) count="$2" 2>/dev/null | od -An -tx1; }
PRE=$(ls -t "$STATE"/pre-*.txt 2>/dev/null | head -1)
echo "== pre-sleep snapshot: $PRE"; [ -n "$PRE" ] && cat "$PRE"
ls -l "$STATE" | tail -6
echo "== now"
echo "date_epoch $(date +%s.%N)  uptime $(cut -d' ' -f1 /proc/uptime)  boot_epoch $(( $(date +%s) - $(cut -d. -f1 /proc/uptime) ))"
echo "kernel $(uname -r)"
echo "pmu_rtc_d000_d00f $(pmu_at 0xd000 16)"
echo "pmu_scratch_9f00_9f1f $(pmu_at 0x9f00 32)"
s=$(pmu_at 0x9f0a 1 | tr -d ' '); [ -n "$s" ] && printf 'stage letter at 0x9f0a: %s (%b)\n' "$s" "\\x$s"
# 0x9f04 'L' + the RTC second of the commit; now vs boot gives commit->boot
python3 - "$(pmu_at 0x9f04 5)" "$(pmu_at 0xd002 6)" "$(cut -d' ' -f1 /proc/uptime)" <<'PY'
import sys
note = bytes.fromhex(sys.argv[1].replace(" ", "")); rtc = bytes.fromhex(sys.argv[2].replace(" ", ""))
up = float(sys.argv[3])
now = int.from_bytes(rtc[2:6], "little")
if note[:1] == b"P":
    t = int.from_bytes(note[1:5], "little")
    print(f"'P' note: the suspend reached prepare (RTC {t:#x}) but not the commit; boot at prepare + {now - up - t:.1f} s"
          " (about the dead-man time: a hang after prepare, see the stage letter for the phase)")
elif note[:1] == b"L":
    commit = int.from_bytes(note[1:5], "little")
    boot = now - up
    print(f"commit RTC {commit:#x}, now {now:#x}, uptime {up:.1f} s -> boot at commit + {boot - commit:.1f} s")
    print("  about alarm_s + 2..10 s: the SoC slept and woke on the alarm; about 5-8 s: the off failed (WD2);"
          " about the dead-man time: the wake hung in m1n1 and WD1 reset it")
else:
    print(f"no 'L' note at 0x9f04 ({note.hex()}): the finisher did not reach the commit")
PY
for z in /sys/class/power_supply/macsmc-battery/energy_now /sys/class/power_supply/macsmc-battery/charge_now; do
	[ -e "$z" ] && echo "$(basename "$z") $(cat "$z")"
done
[ -e /sys/kernel/debug/m1power/smc ] && grep -E "zSLa|zSPa" /sys/kernel/debug/m1power/smc
echo "== previous boot's last lines (needs a persistent journal)"
journalctl -b -1 -n 40 --no-pager 2>/dev/null | tail -40
