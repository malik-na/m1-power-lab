#!/bin/bash
# Run a host-side probe script against a freshly booted m1n1 proxy and print its tagged lines.
#   harness/proxy-probe.sh <name> <script.py> [args...]     output: runs/<day>-proxy/<name>.out
S=$(cd "$(dirname "$0")" && pwd); K=$(dirname "$S"); source "$S/m1dev.sh"
N=${1:?name}; P=${2:?script}; shift 2; D=$K/runs/$(date +%Y%m%d)-proxy; mkdir -p "$D"
[ -e "$D/$N.out" ] && { echo "name $N is taken: $D/$N.out exists (a name is one run)"; exit 1; }
"$S/stop.sh" | tail -1; "$S/to-proxy.sh" || exit 1
M1N1DEVICE=$(m1dev) PYTHONPATH=$HOME/m1n1/proxyclient timeout ${PROBE_TIMEOUT:-300} "$K/venv/bin/python" -u "$P" "$@" > "$D/$N.out" 2>&1
echo "rc=$? $(date +%T) $D/$N.out"
# All of the probe's own lines: a cut list hid the first steps of pidle3 (2026-11-17).
tr -cd '\11\12\15\40-\176' < "$D/$N.out" | grep -E '^\[(pidle|dram|idle|idle2)\]|Error|Exception' | cut -c1-200
ls /dev/ttyACM0 > /dev/null 2>&1 || echo "the proxy's ports are gone"
