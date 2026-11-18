#!/bin/bash
# Reboot the M1 Air from the M3 Max over the USB-C cable (no button press): an Apple VDM sent by
# tuxvdmtool through the kernel tipd driver's debugfs file usb/tipd/<dev>/command. That file
# exists only when tps6598x-core is built with CONFIG_TYPEC_TPS6598X_DEBUG_COMMANDS
# (var/safe-restart/install.sh puts such a build in /lib/modules/$(uname -r)/updates/).
#
# This script never loads, unloads or rebinds a driver, and runs tuxvdmtool with --no-recover so
# that it does not either: on 2026-11-17 a module swap under a live USB4 link to the M1 left a
# stale XDomain, and the M1's next login crashed the M3's Thunderbolt driver
# (docs/proposals/m1-safe-restart.md). Without the command file it refuses.
#
# Usage: M1_CLAIM=<who> m1-reboot.sh [reboot|nop|dfu|"reboot serial"|which]
#   which   find the M1's port and check it; send nothing, needs no claim.
# The caller must hold the M1: tools/tb/m1-claim take <who> "<why>", then M1_CLAIM=<who>.
# The port is the one whose Type-C partner is the M1: PD identity 0xd50005ac (Apple, USB host)
# or a Thunderbolt XDomain (another host) behind that port's CIO. When neither shows (a frozen M1
# can lose both), name it: M1_PORT=<dev>, e.g. 1-0c; it must still have a partner.
# Env: TUXVDMTOOL (default var/safe-restart/tuxvdmtool/target/release/tuxvdmtool, must know
#      --no-recover), M1R_LOG (log file), M1R_SYS and M1R_SUDO (sysfs root and sudo, for tests).
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
CMD=${1:-reboot}
SYS=${M1R_SYS:-/sys}
SUDO=${M1R_SUDO-sudo -n}
TUX=${TUXVDMTOOL:-$R/var/safe-restart/tuxvdmtool/target/release/tuxvdmtool}
LOG=${M1R_LOG:-$R/var/m1-reboot/$(date +%Y%m%d-%H%M%S).log}
mkdir -p "$(dirname "$LOG")"

log() { printf '%s m1-reboot: %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG" >&2; }
die() { log "REFUSED: $*"; exit 1; }

case "$CMD" in
reboot|nop|dfu|"reboot serial"|which) ;;
*) die "unknown command '$CMD' (reboot|nop|dfu|\"reboot serial\"|which)";;
esac
log "command '$CMD', log $LOG"

# 1. The caller holds the M1 (not merely: nobody holds it).
if [ "$CMD" != which ]; then
	holder=$("$R/tools/tb/m1-claim" show | awk '{print $1}')
	[ -n "${M1_CLAIM:-}" ] || die "M1_CLAIM is not set; take the M1 first (tools/tb/m1-claim take <who> ...; M1_CLAIM=<who>). Held now by: $holder"
	"$R/tools/tb/m1-claim" check >/dev/null || die "$("$R/tools/tb/m1-claim" check)"
	[ "$holder" = "$M1_CLAIM" ] || die "the M1 is not claimed by '$M1_CLAIM' (claim: $holder)"
	log "claim: held by $M1_CLAIM"
fi

# 2. The M1's port, from its partner.
declare -A LABEL=() WHY=()
for p in "$SYS"/class/typec/port*; do
	n=${p##*/}; [[ $n =~ ^port[0-9]+$ ]] || continue
	[ -e "$p-partner" ] || continue
	dev=$(basename "$(readlink -f "$p/device")")
	label=$(tr -d '\0' < "$p/device/of_node/connector/label" 2>/dev/null || true)
	idh=$(cat "$p-partner/identity/id_header" 2>/dev/null || echo none)
	log "partner on $n ($dev, '${label:-no label}'): id_header $idh"
	[[ $label == "USB-C "* ]] || continue
	LABEL[$dev]=$label
	[ "$idh" = 0xd50005ac ] && WHY[$dev]+="PD identity Apple host; "
	for s in "$p"/supplier:platform:*.cio; do
		[ -e "$s" ] || continue
		cio=${s##*supplier:platform:}
		for x in "$SYS"/bus/thunderbolt/devices/*; do
			grep -qx 'DEVTYPE=thunderbolt_xdomain' "$x/uevent" 2>/dev/null || continue
			[[ $(readlink -f "$x") == */"$cio"/* ]] || continue
			WHY[$dev]+="Thunderbolt XDomain ${x##*/} '$(cat "$x/vendor_name" 2>/dev/null) $(cat "$x/device_name" 2>/dev/null)' on $cio; "
		done
	done
done
found=("${!WHY[@]}")
for d in "${found[@]}"; do log "M1 candidate $d (${LABEL[$d]}): ${WHY[$d]}"; done
if [ -n "${M1_PORT:-}" ]; then
	[ -n "${LABEL[$M1_PORT]:-}" ] || die "M1_PORT=$M1_PORT has no Type-C partner on a USB-C port"
	if [ ${#found[@]} -gt 0 ] && [ -z "${WHY[$M1_PORT]:-}" ]; then
		die "M1_PORT=$M1_PORT, but the readings point at: ${found[*]}"
	fi
	DEV=$M1_PORT; log "port named by M1_PORT: $DEV"
elif [ ${#found[@]} -eq 1 ]; then
	DEV=${found[0]}
elif [ ${#found[@]} -eq 0 ]; then
	die "no USB-C partner identifies as the M1 (no PD identity 0xd50005ac, no XDomain). Ports with a partner: ${!LABEL[*]}. Check the cable, then name the port with M1_PORT=<dev>"
else
	die "several ports look like the M1: ${found[*]}; name one with M1_PORT=<dev>"
fi
PORT=${LABEL[$DEV]}
n=0; for d in "${!LABEL[@]}"; do [ "${LABEL[$d]}" = "$PORT" ] && n=$((n + 1)); done
[ $n -eq 1 ] || die "label '$PORT' is not unique"
log "M1 on $DEV ('$PORT')"

# 3. That controller has the command file. Never swap modules to get one.
TIPD=$SYS/kernel/debug/usb/tipd/$DEV
if ! $SUDO test -e "$TIPD/command"; then
	mod=$(modinfo -n tps6598x_core 2>/dev/null || echo unknown)
	if $SUDO test -d "$TIPD"; then why="the driver is bound but has no command interface"; else why="no tipd debugfs directory (driver not bound, or debugfs not mounted)"; fi
	die "$TIPD/command is missing: $why. tps6598x_core is $mod (kernel $(uname -r)). Build and install tps6598x-core with CONFIG_TYPEC_TPS6598X_DEBUG_COMMANDS for this kernel (var/safe-restart/); this script does not swap modules"
fi
log "command interface present: $TIPD/command"

# 4. tuxvdmtool that cannot rebind.
[ -x "$TUX" ] || die "tuxvdmtool not found at $TUX (build var/safe-restart/tuxvdmtool)"
"$TUX" --help 2>&1 | grep -q -- '--no-recover' || die "$TUX has no --no-recover; use the patched build"
log "tuxvdmtool: $TUX"

if [ "$CMD" = which ]; then log "which: done, nothing sent"; echo "$DEV $PORT"; exit 0; fi

# 5. Send it.
mkdir -p "$R/var/m1-reboot"; exec 9>"$R/var/m1-reboot/lock"
flock -n 9 || die "another m1-reboot.sh is running"
log "running: $SUDO env RUST_LOG=info $TUX --no-recover -c '$PORT' $CMD"
set +e
# shellcheck disable=SC2086  # "reboot serial" is two words on purpose
$SUDO env RUST_LOG=info "$TUX" --no-recover -c "$PORT" $CMD 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
set -e
log "tuxvdmtool exit $rc"
exit "$rc"
