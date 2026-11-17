#!/bin/bash
# On the M1 (installed as /var/lib/m1power-ds/real.sh): a real deep sleep through the
# deep-sleep driver; the power chip alarm is the wake.
# It refuses to start a sleep that could reach the commit without the watchdog armed there
# (apple_deepsleep.wdt): on 2026-11-17 four runs left the M1 dark until Naeem held the power
# button. apple_deepsleep.snap=4 never calls the driver and is allowed without it.
# ALLOW_NO_WDT=1 overrides, for a run Naeem has asked for by name.
O=/var/lib/m1power-ds/real.out; : > $O
P=/sys/module/apple_deepsleep/parameters
wdt=$(cat $P/wdt 2>/dev/null || echo 0); snap=$(cat $P/snap 2>/dev/null || echo 0)
if [ "$snap" != 4 ] && [ "${wdt:-0}" -lt 1 ] && [ "${ALLOW_NO_WDT:-0}" != 1 ]; then
	echo "refused $(date +%T): apple_deepsleep.wdt is ${wdt:-absent}; no sleep without the watchdog" | tee -a $O; exit 3
fi
echo "start $(date +%T) $(uname -r) boot $(cat /proc/sys/kernel/random/boot_id) online $(cat /sys/devices/system/cpu/online) wdt=$wdt snap=$snap" >> $O
dmesg > /var/lib/m1power-ds/real-dmesg-before.txt; sync; sleep 2; sync
echo none > /sys/power/pm_test
echo mem > /sys/power/state; echo "rc=$? back $(date +%T) online $(cat /sys/devices/system/cpu/online)" >> $O; sync
dmesg | grep -i -E "deepsleep|PM: |is up|failed|error|Call trace|Unable|BUG|WARNING" | tail -80 >> $O; echo done >> $O; sync
dmesg > /var/lib/m1power-ds/real-dmesg-after.txt; sync
