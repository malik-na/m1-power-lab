#!/bin/bash
# Spin-test watcher: wait for the USB drop (last core tearing down), then the return, then read
# the PMU scratch bytes (0x9f0a 'S'/'R', 0x9f0b tenths survived, WDT nibbles) before anything else.
S=$(cd "$(dirname "$0")" && pwd); source $S/m1dev.sh; T=${1:?tag}
R=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit
until ! m1dev >/dev/null; do sleep 0.3; done; echo "USB down $(date +%T.%N | cut -c1-12)"
until D=$(m1dev); do sleep 0.3; done; echo "USB back $(date +%T.%N | cut -c1-12) as $D"; sleep 3
M1N1DEVICE=$D timeout 60 $R/venv/bin/python -I $S/crumb.py 2>&1 | grep -v "RuntimeWarning\|^TTY>"
M1N1DEVICE=$D timeout 90 $R/venv/bin/python -I $S/batt.py 2>&1 | grep -E "^time|^B0|^PSTR|^PPBR|^PDTR"
cd $R && mkdir -p runs/20261106/mac27/$T && M1N1DEVICE=$D timeout 150 venv/bin/python -I pmu_postmortem.py --m1n1 ~/m1n1 --tag after-$T --out runs/20261106/mac27/$T 2>&1 | grep -v "RuntimeWarning\|^TTY>" | grep -E "fault_shadow\(ADT\)|first word set bits: bit|boot_stage|alarm_ctrl|rtc_alarm block" | head -6
