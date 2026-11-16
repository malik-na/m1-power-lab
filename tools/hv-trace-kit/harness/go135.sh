#!/bin/bash
# macOS 13.5 (pre-SPTM) under the hypervisor with real S2R pass-through: no chainload (the Mac's
# boot object is the current ~/m1n1/build/m1n1.bin, so m1n1-raw.elf's symbols match and the wake
# lands in this image), tracer armed from boot, watchdog armed, FIFO stdin for the hv shell.
K=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit; PY=$K/venv/bin/python; R=$K/runs/20261116-mac135
S=$(cd "$(dirname "$0")" && pwd); T=${1:?tag}; shift
source $S/m1dev.sh
until M1N1DEVICE=$(m1dev); do sleep 0.5; done; export M1N1DEVICE; echo "proxy device $M1N1DEVICE"
export M1N1_ELF="${M1N1_ELF:-/home/naeem/m1n1/build/m1n1-raw.elf}"
export S2R_LOG=$R/s2r-trace-$T.jsonl S2R_ARM_AT_START=${S2R_ARM_AT_START:-1} S2R_SNAP_WAKE=${S2R_SNAP_WAKE:-1}
echo "start $(date +%T)"
cd $R; rm -f $S/hvin; mkfifo $S/hvin
( exec 3>$S/hvin; sleep 7200 ) &
timeout ${GUEST_TIMEOUT:-7200} $PY -u /home/naeem/m1n1/proxyclient/tools/run_guest.py "$@" -m $S/arm_wdt.py -m $S/real_s2r.py -m $K/hv_s2r_trace.py \
  -l hv-$T.log $K/kc/kernelcache-13.5.macho \
  -- "${BOOTARGS:-debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0}" > run-$T.out 2>&1 < $S/hvin
echo "run_guest exit $? $(date +%T)"
