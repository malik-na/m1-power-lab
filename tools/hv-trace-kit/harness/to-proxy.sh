#!/bin/bash
# Bring the M1 to a freshly booted m1n1 proxy, from wherever it is (Omarchy, just restarted, or a
# proxy or hypervisor shell).
#   harness/to-proxy.sh [kernel.tar.zst]     (the package goes to tools/tb/m1-hvboot)
# A proxy that is already there is always rebooted first: a used proxy and the shell a hypervisor
# run leaves look the same on USB as a fresh one, and nothing on this Mac tells them apart
# (2026-11-17: a probe ran on the shell lx21 had left; then a stamp taken from the device's sysfs
# link moved by itself 11 minutes after the device appeared). The cost is one reboot.
# Exit status: 0 only when m1-hvboot succeeded (its preflight included) and the proxy is there.
# The three paths below are overridable for harness/test-lib.sh only.
S=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$S/../../.." && pwd)
DEV=${M1_USB_DEV:-/sys/bus/usb/devices/1-1}; TB=${M1_TB_DIR:-$repo/tools/tb}; REBOOT=${M1_HV_REBOOT:-$S/hv-reboot.sh}
at_proxy() { case "$(cat "$DEV/product" 2>/dev/null)" in m1n1*) return 0;; esac; return 1; }
if at_proxy; then
	echo "the M1 is at a proxy already: rebooting it for a fresh one"
	"$REBOOT" | tail -1
	at_proxy && { echo "the M1 did not leave the proxy"; exit 1; }
fi
# After a restart the M1 takes about 40 s to answer over Thunderbolt again.
timeout ${M1_TB_WAIT:-180} bash -c "until timeout 8 '$TB/m1tb' true > /dev/null 2>&1; do sleep ${M1_TB_POLL:-3}; done" || { echo "the M1 does not answer over Thunderbolt (tools/tb/m1-look shows its screen)"; exit 1; }
out=$("$TB/m1-hvboot" "$@" 2>&1); rc=$?
echo "$out" | tail -3
[ $rc = 0 ] || { echo "m1-hvboot failed (status $rc)"; exit 1; }
at_proxy || { echo "m1-hvboot did not reach the proxy"; exit 1; }
