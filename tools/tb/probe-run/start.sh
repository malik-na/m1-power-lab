#!/bin/bash
# start one sleep on the booted test kernel: cand, unbind apple_wdt, pre 0x0201, real.sh
cd /home/naeem/Projects/m1-power-lab
tools/tb/m1tb 'P=/sys/module/apple_deepsleep/parameters; echo '"${1:-0xffffe}"' > $P/cand; [ ! -e /sys/bus/platform/drivers/apple-watchdog/23d2b0000.watchdog ] || echo 23d2b0000.watchdog > /sys/bus/platform/drivers/apple-watchdog/unbind; f=$(ls /sys/bus/nvmem/devices/spmi_nvmem*/nvmem | head -1); echo kernel=$(uname -r) pre0201=$(od -An -tx1 -j513 -N1 $f) cand=$(cat $P/cand) wdt=$(cat $P/wdt) m1fix=$(cat $P/m1fix 2>/dev/null) probe_k=$(cat $P/probe_k) boot=$(cat /proc/sys/kernel/random/boot_id); systemd-run --unit=m1run$(date +%H%M%S) /bin/bash /var/lib/m1power-ds/real.sh >/dev/null 2>&1; echo started $(date +%T)'
