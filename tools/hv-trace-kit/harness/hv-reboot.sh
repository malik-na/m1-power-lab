#!/bin/bash
# Reboot the M1 out of a hypervisor run or the bare proxy, without the operator.
#   harness/hv-reboot.sh [run.out]
# With a run_guest.py alive: interrupt it, wait for its shell prompt in the run's output
# (default: the newest run-*.out under runs/), send p.reboot() through the FIFO. Otherwise:
# p.reboot() straight over the proxy. Then stop this Mac's side (harness/stop.sh).
# If the proxy no longer answers, this cannot help: tools/tb/m1-look shows the Mac's screen, and
# a power cycle is the operator's.
S=$(cd "$(dirname "$0")" && pwd); K=$(cd "$S/.." && pwd); source "$S/lib.sh"; source "$S/m1dev.sh"
P=$(hv_run_guests | head -1)
if [ -n "$P" ] && [ -p "$S/hvin" ]; then
	O=${1:-$(ls -t "$K"/runs/*/run-*.out | head -1)}; n=$(wc -l < "$O")
	# The shell must find a writer on the FIFO, or it reads end-of-input at once and the guest
	# just continues (the drive scripts end the first shell that way on purpose).
	sleep 60 > "$S/hvin" & W=$!
	kill -INT "$P"
	timeout 60 bash -c "until tail -n +$n '$O' | grep -aq '>>>'; do sleep 0.5; done" || echo "no shell prompt in $O (hypervisor not answering)"
	( printf 'p.reboot()\n' > "$S/hvin" ) & sleep 5; kill $W 2>/dev/null
else
	dev=$(m1dev) && PYTHONPATH=$HOME/m1n1/proxyclient M1N1DEVICE=$dev timeout 30 "$K/venv/bin/python" -c 'from m1n1.setup import *; p.reboot()' > /dev/null 2>&1
fi
"$S/stop.sh" > /dev/null 2>&1
for i in $(seq 1 12); do [ -e /sys/bus/usb/devices/1-1/product ] || { echo "the M1 left the proxy"; exit 0; }; sleep 1; done
echo "the M1 is still at the proxy"; exit 1
