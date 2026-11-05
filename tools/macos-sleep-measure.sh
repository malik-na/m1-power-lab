#!/bin/sh
# Measure macOS sleep power on this Mac with built-in tools only.
#
#   sh macos-sleep-measure.sh before    # on battery, then the Mac sleeps
#   sh macos-sleep-measure.sh after     # next morning, after waking it
#
# Records the battery's raw charge (mAh) and voltage before and after, and
# every sleep/wake/dark wake macOS logged in between, then prints the
# average power over the night. Nothing on the Mac is changed except that
# `before` puts it to sleep (pmset sleepnow). Results: ~/m1-sleep/.
set -u
DIR="$HOME/m1-sleep"
mkdir -p "$DIR"

field() { # top-level AppleSmartBattery integer field
	ioreg -rn AppleSmartBattery | grep -E "^ +\"$1\" = -?[0-9]+$" | head -1 | awk -F' = ' '{print $2}'
}
snapshot() { # NAME
	{
		echo "time=$(date '+%Y-%m-%d %H:%M:%S %z')"
		echo "epoch=$(date +%s)"
		for k in AppleRawCurrentCapacity AppleRawMaxCapacity Voltage InstantAmperage CurrentCapacity CycleCount; do
			echo "$k=$(field "$k")"
		done
		echo "external=$(ioreg -rn AppleSmartBattery | grep -E '^ +"ExternalConnected" = ' | head -1 | awk -F' = ' '{print $2}')"
	} > "$DIR/$1.txt"
	cat "$DIR/$1.txt"
}
get() { grep "^$2=" "$DIR/$1.txt" | cut -d= -f2-; }

case "${1:-}" in
before)
	ext=$(ioreg -rn AppleSmartBattery | grep -E '^ +"ExternalConnected" = ' | head -1 | awk -F' = ' '{print $2}')
	if [ "$ext" = "Yes" ]; then
		echo "Unplug the charger first: the measurement needs the Mac on battery."
		exit 1
	fi
	pmset -g > "$DIR/pmset-settings.txt"
	sw_vers > "$DIR/sw_vers.txt"
	snapshot before
	echo "Sleeping in 10 s. Leave the lid as it is, or close it; don't plug in the charger."
	echo "In the morning: open the lid, log in, and run: sh $0 after"
	sleep 10
	pmset sleepnow
	;;
after)
	[ -f "$DIR/before.txt" ] || { echo "no before.txt; run 'before' first"; exit 1; }
	snapshot after
	start=$(get before time | cut -c1-19)
	pmset -g log | awk -v s="$start" '($1" "$2) >= s' | grep -E "	(Sleep|Wake|DarkWake|Start|Failure)	|Entering Sleep|DarkWake from|Wake from" > "$DIR/pmset-log.txt"
	t0=$(get before epoch); t1=$(get after epoch)
	c0=$(get before AppleRawCurrentCapacity); c1=$(get after AppleRawCurrentCapacity)
	v0=$(get before Voltage); v1=$(get after Voltage)
	full=$(get after AppleRawMaxCapacity)
	awk -v t0="$t0" -v t1="$t1" -v c0="$c0" -v c1="$c1" -v v0="$v0" -v v1="$v1" -v full="$full" 'BEGIN {
		h = (t1 - t0) / 3600; mah = c0 - c1; v = (v0 + v1) / 2000
		mwh = mah * v
		printf "elapsed      %.2f h\n", h
		printf "charge used  %d mAh (%d -> %d of %d)\n", mah, c0, c1, full
		printf "energy       %.0f mWh at %.2f V average\n", mwh, v
		printf "average      %.0f mW over the whole night (sleep and any wakes)\n", mwh / h
		printf "per hour     %.2f %% of a full charge\n", 100 * mah / full / h
	}' | tee "$DIR/summary.txt"
	echo "wakes logged: $(grep -c -E 'DarkWake|Wake from' "$DIR/pmset-log.txt")  (details in $DIR/pmset-log.txt)"
	echo
	echo "Paste the lines above, and $DIR/pmset-log.txt if it is short, back to Claude."
	;;
*)
	echo "usage: sh $0 before|after"
	exit 2
	;;
esac
