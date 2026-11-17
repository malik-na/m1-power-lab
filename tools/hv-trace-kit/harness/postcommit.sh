#!/bin/bash
# One non-real Linux commit under the hypervisor, then one or more probe scripts in its shell.
#   harness/postcommit.sh <tag> [probe.py ...]      (env GUEST, KPKG; S2R_* go to the tracer)
# Brings the M1 to a fresh proxy (harness/to-proxy.sh), runs golinux.sh with dram_gate.py, waits
# for "All CPUs exited", runs each probe with hv.run_script, and prints its "[tag]" lines.
# A probe ends with a line containing "] done"; a dead link or a traceback ends the wait too.
# A tag names one run: an existing run-<tag>.out is refused, because the waits below read that
# file and would be answered by the earlier run's text.
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); K=$(dirname "$S"); repo=$(cd "$K/../.." && pwd)
T=${1:?tag}; shift; R=$K/runs/20261116-linux; O=$R/run-$T.out
[ -e "$O" ] && { echo "tag $T is taken: $O exists (a tag names one run)"; exit 1; }
export GUEST=${GUEST:-$repo/var/hvlinux/guest-run41hv.bin}
"$S/to-proxy.sh" ${KPKG:-$repo/var/kernels/run41/kernel-run41.tar.zst} || exit 1
# NO_DRAM_GATE=1: the guest as Linux leaves the DRAM controllers (no switch before it starts).
GATE=(-m "$S/dram_gate.py"); [ -n "${NO_DRAM_GATE:-}" ] && GATE=()
nohup "$S/golinux.sh" "$T" "${GATE[@]}" > "$R/go-$T.log" 2>&1 &
timeout 400 bash -c "until [ -f $O ] && grep -aq 'All CPUs exited' $O; do sleep 1; done" || { echo "no commit within 400 s"; tail -5 "$O" | cut -c1-160; exit 1; }
echo "commit seen $(date +%T)"; sleep 1
for probe in "$@"; do
	# This probe's output starts on the line after the last one there now; its first line follows
	# the shell's ">>> " prompt.
	n=$(( $(wc -l < "$O") + 1 ))
	printf 'hv.run_script("%s")\n' "$(realpath "$probe")" > "$S/hvin"
	timeout ${PROBE_TIMEOUT:-400} bash -c "until tail -n +$n $O | grep -aq -E '\] done|Traceback'; do sleep 1; done" || echo "probe $probe: no end within ${PROBE_TIMEOUT:-400} s"
	echo "probe $(basename "$probe") ended $(date +%T)"
	tail -n +$n "$O" | tr -cd '\11\12\15\40-\176' | sed 's/^\(>>> \)*//' | grep -E '^\[|Exception|Error' | cut -c1-190
done
ls /dev/ttyACM* 2>/dev/null || { echo "the proxy's ports are gone: the M1 left the hypervisor shell"; "$S/stop.sh" | tail -1; }
