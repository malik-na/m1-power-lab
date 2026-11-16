#!/bin/bash
# Stop every host-side process of a hypervisor run: run_guest.py, console readers, FIFO holders.
# By pid from exact matches (no pkill -f: it matches the calling shell too).
S=$(cd "$(dirname "$0")" && pwd); source "$S/lib.sh"
pids="$(hv_run_guests) $(cat "$S/hvin.holder" 2>/dev/null)"
for t in $(hv_ttys); do pids="$pids $(fuser "$t" 2>/dev/null)"; done
pids=$(echo $pids | tr ' ' '\n' | sort -u | tr '\n' ' ')
[ -n "${pids// /}" ] && { echo "stopping: $pids"; kill $pids 2>/dev/null; sleep 1; }
rm -f "$S/hvin" "$S/hvin.holder"
hv_preflight && echo "clean"
