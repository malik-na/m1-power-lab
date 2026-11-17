#!/bin/bash
# macOS 13.5 under the hypervisor, ready for a sleep test, in one command.
#   harness/macos-up.sh <tag>
# Steps, each checked: fresh proxy (to-proxy.sh); chainload the build in $M1N1_NEXT (default
# ~/m1n1-next; CHAINLOAD=0 runs the installed image and applies spmi_ack_patch.py instead);
# go135.sh with the touch-map tracer; drive135.sh (watchdog off; REAL_S2R=1 arms a real sleep
# with ALARM seconds, default 0 = no alarm); the shell's input kept open for a later reboot;
# wait until macOS has idled steadily; with FULL=1 (default) switch to full logging.
# Prints "READY" and the tag's files, or says which step failed. The Sleep click is the operator's.
#   env: ALARM, REAL_S2R (default 1), FULL (default 1), FULL_SKIP (ranges left unlogged),
#        S2R_TOUCH_FULL (ranges logged in full from the start), SETTLE_EPOCHS (default 34)
set -u
S=$(cd "$(dirname "$0")" && pwd); K=$(dirname "$S"); source "$S/m1dev.sh"
T=${1:?tag}; R=$K/runs/20261116-mac135; NEXT=${M1N1_NEXT:-$HOME/m1n1-next}
[ -e "$R/run-$T.out" ] && { echo "tag $T is taken"; exit 1; }
"$S/stop.sh" | tail -1; "$S/to-proxy.sh" | tail -1 || exit 1
EXTRA=()
if [ "${CHAINLOAD:-1}" = 1 ]; then
	export M1N1_ELF=$NEXT/build/m1n1-raw.elf
	( cd "$HOME/m1n1" && M1N1DEVICE=$(m1dev) PYTHONPATH=$HOME/m1n1/proxyclient timeout 120 "$K/venv/bin/python" proxyclient/tools/chainload.py -r "$NEXT/build/m1n1.bin" 2>&1 | grep -v '^TTY>' | tail -1 )
	sleep 6
	case "$(cat /sys/bus/usb/devices/1-1/product 2>/dev/null)" in m1n1*) echo "chainloaded: $(cat /sys/bus/usb/devices/1-1/product)";; *) echo "chainload failed: no proxy"; exit 1;; esac
else
	M1N1DEVICE=$(m1dev) PYTHONPATH=$HOME/m1n1/proxyclient timeout 60 "$K/venv/bin/python" -c "from m1n1.setup import *; exec(open('$S/spmi_ack_patch.py').read())" 2>&1 | grep 'ack-patch' | tail -1
	EXTRA=(-m "$S/spmi_ack_patch.py")
fi
rm -f "$R/ctl-$T"
( S2R_TRACER=$K/hv_touch_map.py S2R_TOUCH_LOG=$R/touch-$T.jsonl S2R_TOUCH_EPOCH=5 S2R_TOUCH_CTL=$R/ctl-$T nohup "$S/go135.sh" "$T" "${EXTRA[@]}" > "$R/go-$T.log" 2>&1 & )
sleep 2
REAL_S2R=${REAL_S2R:-1} ALARM=${ALARM:-0} PROGRESS=$R/touch-$T.jsonl "$S/drive135.sh" "$T" 2>&1 | tail -1 | cut -c1-110
( nohup sleep 7200 > "$S/hvin" 2>/dev/null & echo $! > "$S/hvin.holder" )
timeout 240 bash -c "until [ \$(grep -c '\"ev\": \"epoch\"' $R/touch-$T.jsonl 2>/dev/null) -ge ${SETTLE_EPOCHS:-34} ] || grep -aq 'Traceback' $R/run-$T.out; do sleep 5; done"
grep -aq 'Traceback' "$R/run-$T.out" && { echo "FAILED: the host side raised an error"; tr -cd '\11\12\15\40-\176' < "$R/run-$T.out" | grep -A3 Traceback | tail -4 | cut -c1-150; exit 1; }
if [ "${FULL:-1}" = 1 ]; then
	echo "full ${FULL_SKIP:-}" > "$R/ctl-$T"
	timeout 30 bash -c "until grep -q '\"mode\": \"full\"' $R/touch-$T.jsonl; do sleep 1; done" || { echo "FAILED: full logging did not start"; exit 1; }
	a=$(grep -c '"ev": "acc"' "$R/touch-$T.jsonl"); sleep 10; b=$(grep -c '"ev": "acc"' "$R/touch-$T.jsonl")
	echo "full logging: about $(( (b - a) / 11 )) accesses per second"
fi
echo "READY $(date +%T): tag $T, run-$T.out touch-$T.jsonl vuart-$T.log in $R"
