#!/bin/bash
# Drive one automated macOS-27 sleep test: wait for boot, disarm WDT + arm tracer, wait for the
# lid-closed auto-sleep ('slpw'), then probe at the given delays. Usage: drive.sh TAG DELAY...
S=$(cd "$(dirname "$0")" && pwd); T=$1; shift
R=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit/runs/20261106/mac27; O=$R/run-$T.out; HVIN=${HVIN:-$S/hvin}
cd $R
brk() {  # interrupt the guest and wait for the shell prompt
  local P n; P=$(ps -eo pid,args | awk '$2 ~ /python$/ && /run_guest/ {print $1}'); n=$(wc -l < $O)
  kill -INT $P; timeout 40 bash -c "until tail -n +$n $O | grep -q '>>>'; do sleep 0.5; done"
}
after() { tail -n +$(( $(grep -n "Type ^D to start" $O 2>/dev/null | tail -1 | cut -d: -f1) + 1 )) $O; }
until [ -f $O ] && { grep -q Jumping $O || after | grep -q Traceback; }; do sleep 1; done
grep -q Jumping $O || { echo "boot failed"; exit 1; }
# arm early (Jumping + ARM_DELAY s): with the lid closed macOS sleeps from the login screen
# within ~1 min of boot, before launchd shows on the console
sleep ${ARM_DELAY:-25}
brk; printf 'p.write32(0x23d2b0000 + 0x1c, 0); print("WDT off", hex(p.read32(0x23d2b0000 + 0x1c)))\ns2r_arm("%s")\n%bcont()\n' "$T" "${ARM_EXTRA:-}" > $HVIN
echo "armed $(date +%T)"
timeout 1200 bash -c "until grep -q 77706c73 $O; do sleep 1; done" || { echo "no sleep within 20 min"; exit 1; }
echo "slpw $(date +%T)"; t0=$(date +%s)
for d in "$@"; do
  while [ $(( $(date +%s) - t0 )) -lt $d ]; do sleep 1; done
  grep -q 626e6170 $O && { echo "panicked before +$d"; break; }
  brk
  printf 'probe_midsleep("+%s s")\nfor c in range(8):\n    try:\n        hv.cpu(c); print("=== CPU", c); context()\n    except Exception as e: print("cpu", c, "err", e)\n\nhv.cpu(0)\ncont()\n' $d > $HVIN
  timeout 120 bash -c "until tail -n 5 $O | grep -q 'Returning from exception'; do sleep 0.5; done"
  echo "probe +$d done $(date +%T)"
done
timeout 400 bash -c "until grep -q 626e6170 $O; do sleep 2; done"; echo "end $(date +%T)"
