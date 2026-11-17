#!/bin/bash
# m1hv-ds: one deep-sleep entry through apple_deepsleep (the clean-room driver), unattended, for a
# Linux boot under the m1n1 hypervisor. Runs only when the command line has m1hv.ds=1
# (m1hv-ds.service). Waits m1hv.delay seconds, then runs the bare-metal script
# /var/lib/m1power-ds/real.sh (echo mem > /sys/power/state, logs around it). Each step goes to
# the kernel log (the guest console) and to /var/lib/m1power-ds/hv-ds-<time>.txt.
L=/var/lib/m1power-ds/hv-ds-$(date +%Y%m%d-%H%M%S).txt
mkdir -p /var/lib/m1power-ds
say() { echo "m1hv-ds: $(date +%T.%3N) $*" | tee -a "$L" > /dev/kmsg; }
DELAY=$(sed -n 's/.*m1hv.delay=\([0-9]*\).*/\1/p' /proc/cmdline); DELAY=${DELAY:-120}
say "start; kernel $(uname -r); entry in $DELAY s"
sleep "$DELAY"
say "mem_sleep $(cat /sys/power/mem_sleep); online $(cat /sys/devices/system/cpu/online)"
dmesg | grep 'apple-deepsleep' | head -20 | while read -r l; do say "boot: ${l:0:160}"; done
dmesg | grep -q 'apple-deepsleep: enabled' || { say "apple-deepsleep is not enabled: no entry"; exit 1; }
say "entry: /var/lib/m1power-ds/real.sh"; sync
/var/lib/m1power-ds/real.sh
say "real.sh returned $?; $(head -2 /var/lib/m1power-ds/real.out | tail -1)"
sync
