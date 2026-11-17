#!/bin/bash
# After harness/detach135.sh, cable in: wait for the M1 to wake from its sleep, then read the
# detached log out before macOS can go back to sleep.
#   nohup harness/detached-wake-readout.sh <tag> [seconds after the wake, default 20] &
# The wake is seen from this Mac as the m1n1 USB device leaving and coming back within a second
# (the hypervisor's wake path brings USB up again). 2026-11-17, run det6: an alarm wake was left
# alone; 53 s later the M1 reset (cause not read; macOS goes back to sleep after such a wake and a
# detached run supports one sleep) and the log in its RAM was lost.
# Writes runs/20261116-mac135/detached-<tag>.jsonl and .raw, and one status line per step to
# runs/20261116-mac135/wake-readout-<tag>.log (the last line starts with DONE or FAILED).
S=$(cd "$(dirname "$0")" && pwd); K=$(dirname "$S"); source "$S/m1dev.sh"
T=${1:?tag}; D=${2:-20}; R=$K/runs/20261116-mac135; L=$R/wake-readout-$T.log
say() { echo "$(date +%T.%3N) $*" >> "$L"; }
say "watching for the wake (USB device leaving and returning), read-out $D s after it"
P=/sys/bus/usb/devices/1-1/product
end=$(( $(date +%s) + ${WATCH_SECS:-3600} ))
until ! [ -e $P ]; do [ $(date +%s) -ge $end ] && { say "FAILED: no wake within ${WATCH_SECS:-3600} s"; exit 1; }; sleep 0.1; done
say "USB device gone"
timeout 20 bash -c "until [ -e $P ]; do sleep 0.1; done" || { say "FAILED: the device did not come back within 20 s (a restart, not a wake?)"; exit 1; }
say "USB device back: the wake"
sleep "$D"
[ -e $P ] || { say "FAILED: the device left again before the read-out"; exit 1; }
M1N1DEVICE=$(m1dev) M1N1_ELF=${M1N1_ELF:-$HOME/m1n1-next/build/m1n1-raw.elf} PYTHONPATH=$HOME/m1n1/proxyclient timeout 600 "$K/venv/bin/python" "$S/detach_readout.py" -o "$R/detached-$T.jsonl" --raw "$R/detached-$T.raw" > "$R/readout-$T.out" 2>&1
rc=$?
[ $rc = 0 ] && say "DONE: $(grep -a 'records' "$R/readout-$T.out" | tail -1 | cut -c1-150)" || say "FAILED: read-out status $rc: $(tail -1 "$R/readout-$T.out" | cut -c1-150)"
