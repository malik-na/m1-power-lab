#!/bin/bash
# Proves the run scripts' checks fail on the mistakes they exist for (2026-11-16):
#   1. a process left on the Mac's port from an earlier run -> hv_preflight refuses, naming it
#   2. a second console reader -> session.sh console refuses
#   3. a clean state -> hv_preflight passes
#   4-9 (2026-11-17): a strict-mode caller gets the answer; to-proxy.sh reboots a proxy it finds
#      and fails when m1-hvboot fails; postcommit.sh waits for each probe, prints its first line
#      and refuses a reused tag. Stubs stand in for the Mac, the guest and the tools.
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
# 4: a caller in strict mode (m1-hvboot) gets the check's answer, not a silent exit from fuser's
# status. 2026-11-17: m1-hvboot ended with status 1 on a clean state, and nothing printed.
out=$(HV_TTYS="$tmp/port2" bash -c 'set -euo pipefail; source "$1"; hv_preflight; echo reached' _ "$S/lib.sh" 2>&1) || true
case "$out" in *reached*|*"run_guest.py still running"*) ok "4 strict-mode caller gets an answer";; *) bad "4 strict-mode caller ended silently: '$out'";; esac
# 5-6: to-proxy.sh against stubs (a fake USB device directory, m1tb, m1-hvboot, hv-reboot.sh).
# 2026-11-17: it handed out a used proxy as fresh, and it exited 0 when m1-hvboot had failed.
mkdir -p "$tmp/dev" "$tmp/tb"; echo "m1n1 uartproxy" > "$tmp/dev/product"
printf '#!/bin/bash\nexit 0\n' > "$tmp/tb/m1tb"
printf '#!/bin/bash\necho rebooted >> "%s/calls"; rm -f "%s/dev/product"; echo "the M1 left the proxy"\n' "$tmp" "$tmp" > "$tmp/hv-reboot.sh"
printf '#!/bin/bash\necho hvboot >> "%s/calls"; echo "m1n1 uartproxy" > "%s/dev/product"; echo "proxy: m1n1"; exit ${HVBOOT_RC:-0}\n' "$tmp" "$tmp" > "$tmp/tb/m1-hvboot"
chmod +x "$tmp/tb/m1tb" "$tmp/tb/m1-hvboot" "$tmp/hv-reboot.sh"
toproxy() { M1_USB_DEV="$tmp/dev" M1_TB_DIR="$tmp/tb" M1_HV_REBOOT="$tmp/hv-reboot.sh" M1_TB_POLL=0.1 "$S/to-proxy.sh" 2>&1; }
: > "$tmp/calls"; out=$(toproxy); rc=$?
[ $rc = 0 ] && [ "$(tr '\n' ' ' < "$tmp/calls")" = "rebooted hvboot " ] && ok "5 a proxy that is already there is rebooted before it is handed out" || bad "5 proxy already there: rc=$rc calls='$(tr '\n' ' ' < "$tmp/calls")': $out"
rm -f "$tmp/dev/product"; out=$(HVBOOT_RC=1 toproxy); rc=$?
[ $rc != 0 ] && echo "$out" | grep -q "m1-hvboot failed" && ok "6 a failed m1-hvboot is a failed to-proxy.sh" || bad "6 failed m1-hvboot: rc=$rc: $out"

# 7-9: postcommit.sh against a stub guest (a copy of the script beside stub golinux.sh and
# to-proxy.sh; the stub shell answers each hv.run_script line after 1 s with "[name] reading"
# and "[name] done"). 2026-11-17: a second probe was "ended" by the first one's last line, a
# reused tag was judged on the earlier run's file, and each probe's first line was not printed.
pc="$tmp/pc/kit/harness"; mkdir -p "$pc" "$tmp/pc/kit/runs/20261116-linux" "$tmp/pc/probes"
cp "$S/postcommit.sh" "$pc/"; : > "$pc/dram_gate.py"; : > "$tmp/pc/probes/probeA.py"; : > "$tmp/pc/probes/probeB.py"
printf '#!/bin/bash\nexit 0\n' > "$pc/to-proxy.sh"; printf '#!/bin/bash\necho stopped\n' > "$pc/stop.sh"
cat > "$pc/golinux.sh" <<'STUB'
#!/bin/bash
S=$(cd "$(dirname "$0")" && pwd); R=$(dirname "$S")/runs/20261116-linux; T=$1
rm -f "$S/hvin"; mkfifo "$S/hvin"; sleep 30 > "$S/hvin" & holder=$!
{ echo "booting"; sleep 1; echo "TTY> HV: All CPUs exited"; printf '>>> '
  while read -r line; do n=$(basename "${line#*\"}" '.py")'); sleep 1; echo "[$n] reading 1 2 3"; echo "[$n] done"; printf '>>> '; done; } < "$S/hvin" > "$R/run-$T.out" 2>&1 &
sleep 8; kill $holder; rm -f "$S/hvin"
STUB
chmod +x "$pc"/*.sh
out=$(PROBE_TIMEOUT=6 "$pc/postcommit.sh" t1 "$tmp/pc/probes/probeA.py" "$tmp/pc/probes/probeB.py" 2>&1)
echo "$out" | grep -q '^\[probeB\] done' && ok "7 a second probe is waited for and its lines printed" || bad "7 second probe: $out"
[ "$(echo "$out" | grep -c '^\[probe[AB]\] reading')" = 2 ] && ok "8 each probe's first line is printed" || bad "8 first lines: $out"
out=$(PROBE_TIMEOUT=6 "$pc/postcommit.sh" t1 "$tmp/pc/probes/probeA.py" 2>&1); rc=$?
[ $rc != 0 ] && echo "$out" | grep -q "tag t1 is taken" && ok "9 a reused tag is refused" || bad "9 reused tag: rc=$rc: $out"
exit $fail
