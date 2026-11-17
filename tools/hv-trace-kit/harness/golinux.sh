#!/bin/bash
# Linux (Omarchy, kernel 7.2.11-run39) as the m1n1 hypervisor guest: raw m1n1 guest image with bootargs,
# DTB (atc0 port off), initramfs and kernel appended (var/hvlinux/guest-run39.bin). Same tracer and modules as go135.sh.
# The guest console (ttySAC0) goes to vuart.log.
K=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit; PY=$K/venv/bin/python; R=$K/runs/20261116-linux
S=$(cd "$(dirname "$0")" && pwd); T=${1:?tag}; shift
source $S/m1dev.sh
source $S/lib.sh
hv_preflight || exit 1
until M1N1DEVICE=$(m1dev); do sleep 0.5; done; export M1N1DEVICE; echo "proxy device $M1N1DEVICE"
export M1N1_HV_NO_DEBUG_TRAP=${M1N1_HV_NO_DEBUG_TRAP:-1}
export M1N1_ELF="${M1N1_ELF:-/home/naeem/m1n1/build/m1n1-raw.elf}"
export S2R_LOG=$R/s2r-trace-$T.jsonl S2R_ARM_AT_START=${S2R_ARM_AT_START:-1} S2R_SNAP_WAKE=${S2R_SNAP_WAKE:-1}
echo "start $(date +%T)"
mkdir -p $R; cd $R
trap hv_cleanup EXIT
hv_start_reader $R $T || exit 1
hv_start_fifo
PROBE=(); [ -n "${M1N1_HV_WDT_CPU:-}" ] && PROBE=(-C "${GUEST_CPUS:-0123456}"); export M1N1_HV_WDT_CPU
timeout ${GUEST_TIMEOUT:-7200} $PY -u /home/naeem/m1n1/proxyclient/tools/run_guest.py "$@" "${PROBE[@]}" -m $S/freeze_probe.py -m $S/arm_wdt.py -m $S/real_s2r.py -m ${S2R_TRACER:-$K/hv_s2r_trace.py} \
  -l hv-$T.log -r ${GUEST:-/home/naeem/Projects/m1-power-lab/var/hvlinux/guest-run39.bin} \
  > run-$T.out 2>&1 < $S/hvin
echo "run_guest exit $? $(date +%T)"
