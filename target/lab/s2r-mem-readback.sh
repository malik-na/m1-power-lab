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
v=$(pmu_at 0x9f0b 1 | tr -d ' '); [ -n "$v" ] && printf 'm1n1 reset-path mark at 0x9f0b: %s (%b; 76 = v = m1n1 reached at the wake)\n' "$v" "\\x$v"
c=$(pmu_at 0x9f0c 1 | tr -d ' '); if [ -n "$c" ]; then
	if [ "$v" = 76 ]; then echo "0x9f0c: $c (m1n1 at the wake: bit 7 = SPMI TX FIFO empty, bits 6..0 = attempts the 'v' write took)"
	else x=$((16#$c)); echo "0x9f0c: $c (kernel at the commit: valid=$((x>>7&1)) slpw=$((x&1)) WKTP=$((x>>1&1)) slpa=$((x>>2&1)) SMC-AP-0x201-acked=$((x>>3&1)) MCC-flushed=$((x>>4&1)))"; fi
fi
echo "pmu_fault_log_d200 $(pmu_at 0xd200 16)"
echo "pmu_fault_shadow_a478 $(pmu_at 0xa478 8)"
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
elif note[:1] in (b"L", b"l"):
    commit = int.from_bytes(note[1:5], "little")
    boot = now - up
    print(f"commit RTC {commit:#x}, now {now:#x}, uptime {up:.1f} s -> boot at commit + {boot - commit:.1f} s")
    if note[:1] == b"l":
        print("  'l': m1n1's wake handler consumed the note: the SoC woke from S2R and reached m1n1")
    d = boot - commit
    # test-8 stage-2 build: each wake-path stage re-arms WD1 (wake at alarm 60 s, boot ~11 s)
    table = [(41, "the final wfi returned (cpu0 not power-gated; kernel 30 s mark)"),
             (71, "full wake path: m1n1 consumed the note and reset at once (expect 'v', 'w', 'l')"),
             (86, "stage A: cpu0 ran its first instruction at the RVBAR, died before the stack load"),
             (101, "stage B: stack loaded, died before C"),
             (116, "stage C: C reached, hung on the nub-spmi access itself"),
             (136, "SPMI TX FIFO never empty (no 'v'), or note read failed ('v' present)"),
             (156, "SPMI: no or wrong reply on every attempt"),
             (181, "no wake-path stage ran: Linux's dead-man (170 s)")]
    best = min(table, key=lambda t: abs(t[0] - d))
    print(f"  test-8 decode: nearest {best[0]} s -> {best[1]} (off by {d - best[0]:+.1f} s)")
    print("  (older builds: about alarm_s + 2..10 s = woke on the alarm; 5-8 s = WD2, the off failed; ~181 = dead-man)")
else:
    print(f"no 'L' note at 0x9f04 ({note.hex()}): the finisher did not reach the commit")
PY
for z in /sys/class/power_supply/macsmc-battery/energy_now /sys/class/power_supply/macsmc-battery/charge_now; do
	[ -e "$z" ] && echo "$(basename "$z") $(cat "$z")"
done
[ -e /sys/kernel/debug/m1power/smc ] && grep -E "zSLa|zSPa" /sys/kernel/debug/m1power/smc
echo "== previous boot's last lines (needs a persistent journal)"
journalctl -b -1 -n 40 --no-pager 2>/dev/null | tail -40
