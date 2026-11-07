#!/bin/bash
# Reboot the M1 Air from the M3 Max over the USB-C cable (no button press).
# Needs the M3 Max's USB-C driver with the tipd debugfs command interface: Omarchy's
# kernel (omacom/linux-aurora 2026.10.11.14) lacks it, so tipd-port/ is that release's
# tipd driver with debugfs.c ported from aurora-silicon/linux 2661d71e. The module swap
# lasts until the M3 Max reboots; this script reloads it when needed.
# Usage: m1-reboot.sh [reboot|nop|dfu|"reboot serial"]   (sudo -n must work)
set -eu
D=$(cd "$(dirname "$0")" && pwd); CMD=${1:-reboot}
TUX=${TUXVDMTOOL:-$HOME/Work/aurora/tuxvdmtool/target/release/tuxvdmtool}
if ! sudo -n test -e /sys/kernel/debug/usb/tipd/2-08/command; then
	K=/lib/modules/$(uname -r)/build
	[ -f "$D/tipd-port/tps6598x-core.ko" ] || make -s -C "$K" M="$D/tipd-port" modules
	sudo -n rmmod sn201202x tps6598x_core 2>/dev/null || true
	if ! { sudo -n insmod "$D/tipd-port/tps6598x-core.ko" && sudo -n insmod "$D/tipd-port/sn201202x.ko"; }; then
		echo "ported modules failed to load; restoring the stock ones" >&2
		sudo -n rmmod sn201202x tps6598x_core 2>/dev/null || true; sudo -n modprobe sn201202x; exit 1
	fi
	sleep 3
fi
# Use the M3 Max port whose Type-C partner is a Mac (id_header 0xd50005ac: Apple, USB host
# capable); serial works only on "USB-C Left Back" (and needs a cable with SBU wires).
PORT=""
for p in /sys/class/typec/port*-partner; do
	[ "$(cat "$p/identity/id_header" 2>/dev/null)" = 0xd50005ac ] || continue
	dev=$(basename "$(readlink -f "${p%-partner}/device")")
	PORT=$(tr -d '\0' < /sys/bus/spmi/devices/$dev/of_node/connector/label 2>/dev/null | sed 's/^USB-C //')
done
[ -n "$PORT" ] || { echo "no Mac found on any USB-C port" >&2; exit 1; }
echo "M1 on: $PORT"
sudo -n env RUST_LOG=info "$TUX" -c "$PORT" $CMD
