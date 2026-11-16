#!/bin/bash
# Proves the run scripts' checks fail on the mistakes they exist for (2026-11-16):
#   1. a process left on the Mac's port from an earlier run -> hv_preflight refuses, naming it
#   2. a second console reader -> session.sh console refuses
#   3. a clean state -> hv_preflight passes
# No Mac needed: a temporary file stands in for the port.
set -u
S=$(cd "$(dirname "$0")" && pwd); K=$(cd "$S/.." && pwd); source "$S/lib.sh"
tmp=$(mktemp -d); trap 'kill $holder $locker 2>/dev/null; rm -rf "$tmp"' EXIT
fail=0; ok() { echo "ok   $1"; }; bad() { echo "FAIL $1"; fail=1; }

: > "$tmp/port"; sleep 30 < "$tmp/port" & holder=$!
out=$(HV_TTYS="$tmp/port" hv_preflight 2>&1) && bad "1 stale holder: preflight passed" || {
	echo "$out" | grep -q "held by pid(s) $holder" && ok "1 stale holder refused, pid named" || bad "1 stale holder: pid not named: $out"; }
kill $holder; wait $holder 2>/dev/null

( flock -n 9 && sleep 30 ) 9> "$tmp/lock" & locker=$!; sleep 0.3
out=$(M1N1_CONSOLE_LOCK="$tmp/lock" RUN="$tmp" VUART_LOG="$tmp/v.log" timeout 5 "$K/session.sh" console 2>&1); rc=$?
[ $rc = 1 ] && echo "$out" | grep -q "another console reader" && ok "2 second console reader refused" || bad "2 second reader: rc=$rc: $out"
kill $locker; wait $locker 2>/dev/null

: > "$tmp/port2"
out=$(HV_TTYS="$tmp/port2" hv_preflight 2>&1) && ok "3 clean state passes" || {
	echo "$out" | grep -q "run_guest.py still running" && ok "3 (a real run_guest.py is running now: refused, as it must be)" || bad "3 clean state refused: $out"; }
exit $fail
