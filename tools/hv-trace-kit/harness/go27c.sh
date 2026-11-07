#!/bin/bash
# Wait for a fresh m1n1 proxy, chainload the local m1n1 build, then boot macOS 27 under the
# hypervisor in SPTM emulation mode, watchdog armed, FIFO stdin for the hv shell.
K=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit; PY=$K/venv/bin/python; R=$K/runs/20261106/mac27
S=$(cd "$(dirname "$0")" && pwd); T=${1:?tag}; shift
source $(dirname "$0")/m1dev.sh
until M1N1DEVICE=$(m1dev); do sleep 0.5; done; export M1N1DEVICE; echo "proxy device $M1N1DEVICE"; export M1N1_ELF="${M1N1_ELF:-/home/naeem/m1n1/build/m1n1-raw.elf}"
old=$(stat -c %Y /dev/ttyACM0 2>/dev/null || echo 0)
if [ "${FRESH:-1}" = 1 ]; then
  echo "waiting for a fresh proxy"
  until [ -e /dev/ttyACM0 ] && [ "$(stat -c %Y /dev/ttyACM0)" != "$old" ]; do sleep 0.5; done
  sleep 3
fi
if [ "${CHAIN:-1}" = 1 ]; then
  cd /home/naeem/m1n1/proxyclient
  BIN=${M1N1_BIN:-../build/m1n1.bin}
  want=$(strings $BIN | sed -n 's/.*##m1n1_ver##\(v[0-9.]*-[0-9]*-g[0-9a-f]*\).*/\1/p' | head -1)
  for attempt in 1 2 3; do
    old=$(stat -c %Y $M1N1DEVICE)
    timeout 60 $PY tools/chainload.py -r $BIN 2>&1 | grep -v "^TTY>\|RuntimeWarning" | tail -2
    sleep 3; until M1N1DEVICE=$(m1dev) && [ "$(stat -c %Y $M1N1DEVICE)" != "$old" ]; do sleep 0.5; done
    export M1N1DEVICE; sleep 4
    got=$(cat /sys/class/tty/$(basename $M1N1DEVICE)/device/../product 2>/dev/null | sed 's/.* //')
    echo "proxy device after chainload $M1N1DEVICE: running $got, uploaded $want"
    case "$want" in "$got"*) [ -n "$got" ] && break;; esac
    echo "chainload did not take (attempt $attempt)"; [ $attempt = 3 ] && { echo "giving up"; exit 1; }
  done
fi
export M1N1_NO_ECL_HOLD=${M1N1_NO_ECL_HOLD:-}
echo "start $(date +%T) NO_ECL_HOLD=${M1N1_NO_ECL_HOLD}"
cd $R; rm -f $S/hvin; mkfifo $S/hvin
( exec 3>$S/hvin; sleep 7200 ) &
timeout ${GUEST_TIMEOUT:-14400} $PY -u /home/naeem/m1n1/proxyclient/tools/run_guest.py --sptm-mode ${MODE:-emulation} "$@" -m $S/arm_wdt.py ${EXTRA_M:+-m $EXTRA_M} \
  -p $K/kc/sptm27/sptm.macho -t $K/kc/sptm27/txm.macho -l hv-$T.log $K/kc/kernelcache-27.macho \
  -- "${BOOTARGS:-debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0 -v}" > run-$T.out 2>&1 < $S/hvin
echo "run_guest exit $? $(date +%T)"
