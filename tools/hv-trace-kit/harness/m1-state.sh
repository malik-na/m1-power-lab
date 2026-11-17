#!/bin/bash
# What is the M1 doing right now? Every reading this Mac can take, in one command, before
# anything is said about its state. 2026-11-17: "at the login window" and then "asleep" were said
# from logs alone while the M1 had restarted into Omarchy 20 minutes earlier; a photo had been
# taken and not looked at.
#   harness/m1-state.sh [label]
# Prints one VERDICT line from the readings, the readings, and the path of a camera frame.
# The frame is to be LOOKED AT (Read it): the verdict cannot see a login window or a dark screen.
S=$(cd "$(dirname "$0")" && pwd); K=$(dirname "$S"); repo=$(cd "$K/../.." && pwd)
usb=$(cat /sys/bus/usb/devices/1-1/product 2>/dev/null)
tb=$(timeout 8 "$repo/tools/tb/m1tb" 'echo "$(uname -r), up since $(uptime -s)"' 2>/dev/null | tail -1)
rg=$(ps -eo etimes,args | awk '$2 ~ /python$/ && /run_guest/ {print $1; exit}')
last=$(ls -t "$K"/runs/*/touch-*.jsonl "$K"/runs/*/s2r-trace-*.jsonl 2>/dev/null | head -1)
age=""; [ -n "$last" ] && age=$(( $(date +%s) - $(stat -c %Y "$last") ))
if [ -n "$tb" ]; then verdict="LINUX is running on the M1 ($tb)"
elif [ -n "$usb" ] && [ -n "$rg" ] && [ -n "$age" ] && [ "$age" -le 15 ]; then verdict="a GUEST is running under the hypervisor, host attached (log written $age s ago)"
elif [ -n "$usb" ] && [ -n "$rg" ]; then verdict="hypervisor attached but SILENT for ${age:-?} s: asleep, detached, stopped in its shell, or hung: the readings cannot tell"
elif [ -n "$usb" ]; then verdict="the m1n1 device is listed and no host process drives it: bare proxy, detached guest, or asleep: the readings cannot tell"
else verdict="NOT REACHABLE over USB or Thunderbolt: off, asleep with the port down, booting, or hung"; fi
echo "VERDICT: $verdict"
echo "  usb 1-1: ${usb:-none}   thunderbolt: ${tb:-no answer}   run_guest: ${rg:+alive ${rg} s}${rg:-none}   newest log: ${last:+$(basename "$last"), ${age} s ago}"
echo "  frame: $("$repo/tools/tb/m1-look" "state-${1:-now}" 2>&1 | tail -1)"
