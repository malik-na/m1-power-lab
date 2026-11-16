#!/bin/bash
# After go135.sh: wait for the guest to boot, interrupt once, watchdog off, real S2R on, continue.
# Then the owner logs in and runs pmset relative wake 120; sleep 20; pmset sleepnow.
S=$(cd "$(dirname "$0")" && pwd); T=${1:?tag}; WAKE=${WAKE:-resume}
R=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit/runs/20261116-mac135; O=$R/run-$T.out; HVIN=$S/hvin
until [ -f $O ] && grep -q Jumping $O; do sleep 1; done
sleep ${ARM_DELAY:-30}
P=$(ps -eo pid,args | awk '$2 ~ /python$/ && /run_guest/ {print $1}'); n=$(wc -l < $O)
kill -INT $P; timeout 60 bash -c "until tail -n +$n $O | grep -q '>>>'; do sleep 0.5; done" || { echo "no shell prompt"; exit 1; }
printf 'p.write32(0x23d2b0000 + 0x1c, 0); print("WDT off", hex(p.read32(0x23d2b0000 + 0x1c)))\nreal_s2r_on(wake="%s")\n' "$WAKE" > $HVIN
timeout 60 bash -c "until tail -n 40 $O | grep -q 'wake handler registered'; do sleep 0.5; done" && echo "real S2R armed $(date +%T)" || echo "real_s2r_on did not confirm"
# cont() over the FIFO does not resume (2026-11-16, Python 3.14); end the shell's input instead:
# the console exits and the hypervisor continues the guest. Later shells get EOF at once.
kill $(ps -eo pid,args | awk '$2=="sleep" && $3=="7200" {print $1}') 2>/dev/null
timeout 30 bash -c "until [ \$(stat -c %Y $R/vuart.log) -gt \$(( \$(date +%s) - 5 )) ]; do sleep 1; done" && echo "guest running again $(date +%T)" || echo "guest did not resume"
grep -a -E '\[s2r-real\]|WDT off' $O | tail -8
