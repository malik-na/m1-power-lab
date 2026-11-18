#!/bin/bash
# The facts a status update rests on, read now, each with its time. A status update quotes these
# lines; what is not here is "not read". (2026-11-18: four status updates stated things nobody had
# read: "an earlier hypervisor build", "the second auditor is still working", "apparently",
# "seem".)
#   tools/status.sh
set -u
repo=$(cd "$(dirname "$0")/.." && pwd); cd "$repo"
now() { date +%T; }
echo "now $(now)"
echo "m1 claim: $(tools/tb/m1-claim show)"
usb=$(cat /sys/bus/usb/devices/1-1/product 2>/dev/null || echo none)
echo "m1 usb (m1n1 proxy/hypervisor if named so): $usb"
k=$(timeout 6 tools/tb/m1tb 'echo "$(uname -r) up_since=$(uptime -s | tr " " _)"' 2>/dev/null) \
	|| k=$(timeout 8 ssh -o ConnectTimeout=5 m1ts 'echo "$(uname -r) up_since=$(uptime -s | tr " " _)"' 2>/dev/null) \
	|| k="no answer on Thunderbolt or tailnet"
echo "m1 linux: $k"
R=tools/hv-trace-kit/runs/20261116-mac135
f=$(ls -t $R/wake-readout-*.log 2>/dev/null | head -1)
[ -n "$f" ] && echo "last hypervisor run $(basename "$f" .log | sed 's/wake-readout-//'): $(tail -1 "$f" | cut -c1-110)"
for t in var/commit-walk/*.tsv; do [ -s "$t" ] && echo "$(basename "$t"): $(wc -l < "$t") rows, last: $(tail -1 "$t" | cut -c1-110)"; done
echo "kernel tree: $(git -C ~/Work/deepsleep-kernel log --oneline -1 | cut -c1-90); uncommitted: $(git -C ~/Work/deepsleep-kernel status --short | wc -l)"
echo "driver repo: $(git -C ~/Work/deepsleep-clean log --oneline -1 | cut -c1-90); uncommitted: $(git -C ~/Work/deepsleep-clean status --short | wc -l)"
for w in ~/Work/deepsleep-tests-r* ~/Work/deepsleep-glue-tests-r*; do
	[ -d "$w/.git" ] || continue
	echo "workspace $(basename "$w"): $(git -C "$w" log --oneline -1 | cut -c1-70); uncommitted: $(git -C "$w" status --short | wc -l)"
done | tail -3
echo "lab repo: $(git log --oneline -1 | cut -c1-90)"
b=$(sudo -n docker ps --format '{{.Status}}' 2>/dev/null | head -1)
echo "kernel build: ${b:-none running}; last package $(ls -l --time-style=+%F_%T ~/.cache/m1-s2r-kb/io-clean/out/kernel.tar.zst 2>/dev/null | awk '{print $6}')"
W=~/.claude/projects/-home-naeem-Projects-m1-power-lab
for m in $(ls -t "$W"/*/subagents/workflows/*/agent-*.meta.json "$W"/*/subagents/agent-*.meta.json 2>/dev/null | head -6); do
	j=${m%.meta.json}.jsonl
	d=$(grep -o '"description":"[^"]*"' "$m" | head -1 | cut -d'"' -f4)
	t=$(ls -l --time-style=+%T "$j" 2>/dev/null | awk '{print $6}')
	echo "agent \"$d\": last step $t"
done
