# harness/lib.sh: what every hypervisor run script shares. Source it; do not run it.
# The run script is the one owner of a run's host-side processes: it checks that nothing is left
# from an earlier run, starts the one console reader, and stops what it started when it exits.
# 2026-11-16: five console readers left by earlier runs raced on the Mac's console port and
# killed the hypervisor link in six runs (docs/evidence/2026-11-16-run40-mac-order).

# The Mac's serial ports as the M3 sees them (HV_TTYS overrides, for the test).
hv_ttys() { ls /dev/ttyACM* 2>/dev/null; }

# Processes whose command is run_guest.py itself. Matched on the argument, not with pkill -f or
# pgrep -f, which also match the shell that runs the check.
hv_run_guests() { ps -eo pid=,args= | awk '{for (i = 2; i <= 5; i++) if ($i ~ /\/run_guest\.py$/) {print $1; break}}'; }

# Refuse to start a run while anything holds the Mac's ports or an earlier run_guest.py lives.
hv_preflight() {
	local bad=0 t h
	for t in ${HV_TTYS:-$(hv_ttys)}; do
		# fuser exits 1 when nothing holds the file: under a caller's "set -e -o pipefail" that
		# ended the caller silently (m1-hvboot, 2026-11-17).
		h=$({ fuser "$t" 2>/dev/null || true; } | tr -s ' ' | sed 's/^ //')
		if [ -n "$h" ]; then
			echo "preflight: $t is held by pid(s) $h:"
			ps -o pid=,lstart=,args= -p "${h// /,}" | cut -c1-140 | sed 's/^/preflight:   /'
			bad=1
		fi
	done
	h=$(hv_run_guests | tr '\n' ' ')
	if [ -n "${h// /}" ]; then echo "preflight: run_guest.py still running: $h"; bad=1; fi
	if [ $bad != 0 ]; then
		echo "preflight: stop them first (harness/stop.sh); a run starts with nothing on the Mac's ports"
		return 1
	fi
}

# The one console reader of this run: $1 run directory, $2 tag. Log: <run dir>/vuart-<tag>.log
# (one file per run, so a wait on it cannot match an earlier run's text).
hv_start_reader() {
	RUN="$1" VUART_LOG="$1/vuart-$2.log" "$K/session.sh" console > "$1/console-$2.out" 2>&1 &
	HV_READER=$!
	sleep 1
	kill -0 "$HV_READER" 2>/dev/null || { cat "$1/console-$2.out"; echo "the console reader did not start"; return 1; }
	echo "console reader pid $HV_READER -> $1/vuart-$2.log"
}

# The hypervisor shell's input: a FIFO held open by one process whose pid is on file, so the
# drive scripts end it by pid.
hv_start_fifo() {
	rm -f "$S/hvin"; mkfifo "$S/hvin"
	sleep 7200 > "$S/hvin" &
	HV_HOLDER=$!
	echo "$HV_HOLDER" > "$S/hvin.holder"
}

hv_cleanup() {
	kill ${HV_READER:-} ${HV_HOLDER:-} 2>/dev/null
	rm -f "$S/hvin" "$S/hvin.holder"
}
