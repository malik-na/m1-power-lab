#!/bin/bash
# CPU offline/online test for m1power/s2r-cpu-hotplug.
# Runs as root on the M1 (lab run --script). Writes everything to
# $MACLAB_OUT (or ./out). Never suspends: it does not touch /sys/power,
# rtcwake, systemctl suspend/hibernate or any network configuration.
#
# The phase follows the kernel command line (read back from debugfs):
#
#   apple_cpu_hotplug=park                       -> phase "park"
#     1. cpu1..cpu7, CYCLES (default 100) offline/online cycles each
#     2. whole P cluster (cpu4-7) down together, then up, max(CYCLES/10,1)
#     3. every secondary down for 10 s, then up, 3 times
#
#   apple_cpu_hotplug=powerdown[-legacy] panic=10 oops=panic -> phase "powerdown"
#     Only an m1n1 stage 2 older than v1.9.9 with powerdown-legacy really
#     powers down. Otherwise the kernel must fall back to park and say why
#     (debugfs powerdown_fallback; always for v1.9.9+, re-entry "mpidr"):
#     the script checks that, reports "park fallback" and runs the park
#     phase instead.
#     1. cpu7 only (cpu4-6 stay online, so cpu7 is never the last core of
#        its cluster): PD_CYCLES (default 1) offline/online cycles, with
#        the per-cycle checks below. Re-run with PD_CYCLES=100 once 1 passes.
#     2. only with PD_LAST_CORE=1: cpu7, cpu6, cpu5 down (powered off), then
#        cpu4 down, which must be parked, not powered off. Off by default.
#
# After every stage: no new kernel warning/error lines, every CPU
# stuck=0 status_timeouts=0 flush_timeouts=0, else stop at once.
# Exit 0 = PASS, 1 = FAIL, 2 = SKIP (cpu7 cannot power down).
set -u
CYCLES=${CYCLES:-100}
PD_CYCLES=${PD_CYCLES:-1}
PD_LAST_CORE=${PD_LAST_CORE:-0}
# Extended regex of warn/err lines unrelated to CPU hotplug to ignore.
IGNORE_RE=${IGNORE_RE:-'^$'}
OUT=${MACLAB_OUT:-./out}
mkdir -p "$OUT"
LOG="$OUT/hotplug.log"
exec > >(tee -a "$LOG") 2>&1

dbg=/sys/kernel/debug/apple_cpu_hotplug
sys=/sys/devices/system/cpu
mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug

snap() { # name
	cat "$dbg" > "$OUT/state-$1.txt" 2>&1
}

fail() {
	echo "FAIL: $*"
	cat "$dbg"
	snap fail
	dmesg > "$OUT/dmesg-fail.txt"
	exit 1
}

echo "== $(date -Is) $(uname -r)"
cat /proc/cmdline
dmesg > "$OUT/dmesg-before.txt"
grep -h . /proc/device-tree/chosen/asahi,m1n1-stage2-version 2>/dev/null | tr -d '\0' |
	sed 's/^/m1n1 stage2: /'
dmesg | grep 'apple-cpu-hotplug' | tee "$OUT/dmesg-hotplug-boot.txt"
for w in /sys/class/watchdog/watchdog*; do
	[ -e "$w" ] && echo "$w: $(cat "$w/identity" 2>/dev/null) state=$(cat "$w/state" 2>/dev/null) timeout=$(cat "$w/timeout" 2>/dev/null)"
done

[ -r "$dbg" ] || fail "no $dbg: apple_cpu_hotplug= missing or ops not installed"
[ -e $sys/cpu7/online ] || fail "no cpu7/online"
[ ! -e $sys/cpu0/online ] || echo "note: cpu0 has an online file; it must refuse"
snap before
cat "$dbg"

mode=$(sed -n 's/^mode: //p' "$dbg")
fallback=$(sed -n 's/^powerdown_fallback: //p' "$dbg")
reentry=$(sed -n 's/^m1n1: .* reentry=//p' "$dbg")
want=park
grep -qw 'apple_cpu_hotplug=powerdown\(-legacy\)\?' /proc/cmdline && want=powerdown
echo "requested: $want, active: $mode, m1n1 re-entry: $reentry, fallback: ${fallback:-?}"
[ -n "$fallback" ] || fail "debugfs has no powerdown_fallback line (old kernel?)"
note=$mode
if [ "$want" = powerdown ] && [ "$reentry" = mpidr ] && [ "$mode" != park ]; then
	fail "powerdown active with m1n1 re-entry mpidr; it must fall back to park"
fi
if [ "$want" = powerdown ] && [ "$mode" = park ]; then
	[ "$fallback" != - ] || fail "powerdown fell back to park without a reason"
	dmesg | grep -q 'apple-cpu-hotplug: powerdown refused' ||
		fail "no 'powerdown refused' line in dmesg"
	echo "PARK FALLBACK: $fallback; running the park phase"
	note="park fallback from powerdown: $fallback"
elif [ "$want" != "$mode" ]; then
	fail "requested $want but the kernel runs $mode"
elif [ "$fallback" != - ]; then
	fail "mode $mode but powerdown_fallback=$fallback"
fi

# --- helpers ---------------------------------------------------------------

warn_base=$(dmesg --level=warn,err,crit,alert,emerg | wc -l)
check_dmesg() { # stage
	local new
	new=$(dmesg --level=warn,err,crit,alert,emerg | tail -n +$((warn_base + 1)) |
		grep -Ev "$IGNORE_RE")
	warn_base=$(dmesg --level=warn,err,crit,alert,emerg | wc -l)
	if [ -n "$new" ]; then
		echo "$new"
		fail "new kernel warnings during $1"
	fi
}

field() { # cpu name -> value from debugfs
	sed -n "s/^cpu$1 .* $2=\([^ ]*\).*/\1/p" "$dbg"
}

check_state() { # stage
	local c
	for c in 1 2 3 4 5 6 7; do
		[ "$(field $c stuck)" = 0 ] || fail "$1: cpu$c stuck ($(field $c stuck))"
		[ "$(field $c status_timeouts)" = 0 ] || fail "$1: cpu$c status_timeouts"
		[ "$(field $c flush_timeouts)" = 0 ] || fail "$1: cpu$c flush_timeouts"
	done
	check_dmesg "$1"
}

set_online() { # cpu value
	echo "$2" > $sys/cpu$1/online || fail "echo $2 > cpu$1/online"
	[ "$(cat $sys/cpu$1/online)" = "$2" ] || fail "cpu$1 online != $2"
}

check_runs_on() { # cpu: prove the CPU executes code again
	taskset -c "$1" true || fail "taskset -c $1"
}

# cpu0 must refuse (no file, or a write that fails).
if [ -e $sys/cpu0/online ] && echo 0 > $sys/cpu0/online 2>/dev/null; then
	fail "cpu0 went offline"
fi

# --- park -------------------------------------------------------------------

if [ "$mode" = park ]; then
	echo "== park 1: cpu1..7 x$CYCLES each"
	for c in 1 2 3 4 5 6 7; do
		p0=$(field $c parks)
		for i in $(seq "$CYCLES"); do
			set_online $c 0
			[ "$(field $c state)" = parked ] || fail "cpu$c offline but state=$(field $c state)"
			set_online $c 1
			check_runs_on $c
		done
		p1=$(field $c parks)
		[ $((p1 - p0)) = "$CYCLES" ] || fail "cpu$c parks $p0 -> $p1, expected +$CYCLES"
		[ "$(field $c restarts)" = 0 ] || fail "cpu$c restarts in park mode"
		[ "$(field $c powerdowns)" = 0 ] || fail "cpu$c powerdowns in park mode"
		check_state "park 1 cpu$c"
		echo "cpu$c ok ($CYCLES cycles)"
	done
	snap park1

	n=$((CYCLES / 10 > 0 ? CYCLES / 10 : 1))
	echo "== park 2: P cluster down together x$n"
	for i in $(seq $n); do
		for c in 7 6 5 4; do set_online $c 0; done
		sleep 0.2
		for c in 4 5 6 7; do set_online $c 1; check_runs_on $c; done
	done
	check_state "park 2"

	echo "== park 3: all secondaries down 10 s x3"
	for i in 1 2 3; do
		for c in 7 6 5 4 3 2 1; do set_online $c 0; done
		[ "$(grep -c ^processor /proc/cpuinfo)" = 1 ] || fail "more than one CPU online"
		sleep 10
		for c in 1 2 3 4 5 6 7; do set_online $c 1; done
		for c in 1 2 3 4 5 6 7; do check_runs_on $c; done
	done
	check_state "park 3"
fi

# --- powerdown -------------------------------------------------------------

if [ "$mode" = powerdown ]; then
	[ "$(field 7 can_powerdown)" = 1 ] || {
		echo "SKIP: cpu7 can_powerdown=0 (see dmesg: reservation or mapping)"
		exit 2
	}
	grep -qw 'panic=[0-9]*' /proc/cmdline || echo "note: no panic= on the command line; a panic will not reboot by itself"
	for c in 4 5 6; do
		[ "$(cat $sys/cpu$c/online)" = 1 ] || fail "cpu$c must be online so cpu7 is not the last P core"
	done

	echo "== powerdown 1: cpu7 x$PD_CYCLES (cpu4-6 online)"
	for i in $(seq "$PD_CYCLES"); do
		d0=$(field 7 powerdowns); r0=$(field 7 restarts)
		set_online 7 0
		st=$(field 7 state)
		[ "$st" = off ] || fail "cpu7 offline but state=$st, park reason $(field 7 last_park_reason)"
		[ "$(field 7 powerdowns)" = $((d0 + 1)) ] || fail "cpu7 powerdowns did not count"
		[ "$i" = 1 ] && snap pd-cpu7-off
		set_online 7 1
		check_runs_on 7
		[ "$(field 7 restarts)" = $((r0 + 1)) ] || fail "cpu7 restarts did not count"
		[ "$(field 7 state)" = running ] || fail "cpu7 online but state=$(field 7 state)"
		check_state "powerdown 1 cycle $i"
		[ "$i" = 1 ] && { snap pd-cpu7-cycle1; echo "cpu7 cycle 1 ok"; }
	done
	# GoFetch mitigation: if m1n1 set HID11.DISABLE_DMP at boot it must be set now.
	b=$(sed -n '/^cpu7 /,/^cpu/{s/^  boot: .* hid11=\([^ ]*\).*/\1/p}' "$dbg")
	l=$(sed -n '/^cpu7 /,/^cpu/{s/^  last: .* hid11=\([^ ]*\).*/\1/p}' "$dbg")
	echo "cpu7 HID11 boot=$b last=$l dmp_restores=$(field 7 dmp_restores) reg_mismatches=$(field 7 reg_mismatches)"
	if [ -n "$b" ] && [ -n "$l" ] && (( (b >> 30) & 1 )) && ! (( (l >> 30) & 1 )); then
		fail "cpu7 lost HID11.DISABLE_DMP"
	fi
	echo "cpu7 ok ($PD_CYCLES cycles)"

	if [ "$PD_LAST_CORE" = 1 ]; then
		echo "== powerdown 2: last P core must park"
		for c in 7 6 5; do
			set_online $c 0
			[ "$(field $c state)" = off ] || fail "cpu$c state=$(field $c state), expected off"
		done
		set_online 4 0
		[ "$(field 4 state)" = parked ] || fail "cpu4 (last P core) state=$(field 4 state), expected parked"
		[ "$(field 4 last_park_reason)" = last ] || echo "cpu4 park reason: $(field 4 last_park_reason)"
		sleep 1
		for c in 4 5 6 7; do set_online $c 1; check_runs_on $c; done
		check_state "powerdown 2"
	fi
fi

snap after
cat "$dbg"
dmesg > "$OUT/dmesg-after.txt"
if dmesg | grep -E "may not have shut down|failed to come online|failed to boot|apple-cpu-hotplug: .*(power status|uart0|stuck|L1-clean|differ)|Oops|BUG:|SError"; then
	fail "kernel reported a problem"
fi
echo "PASS ($note)"
