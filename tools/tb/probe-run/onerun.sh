#!/bin/bash
# Used by milestone 1 (2026-11-20) because m1-cand-runs' start step failed on probe kernels.
# Usage: M1_CLAIM=<who> tools/tb/probe-run/onerun.sh <kernel.tar.zst> <tag> <cmdline> <out-prefix> [cand mask]
# Writes <out-prefix>-start.txt (0x0201 before, params) and -after.txt (reset time, record, 0x0201, shadow).
# onerun.sh <pkg> <tag> <cmdline> <out-prefix> [mask]: boot once, start one sleep, read the result
S=$(cd "$(dirname "$0")" && pwd); cd /home/naeem/Projects/m1-power-lab
pkg=$1 tag=$2 cl=$3 out=$4 mask=${5:-0xffffe}
krel=$(zstd -dc "$pkg" | tar -t | sed -n 's|^usr/lib/modules/\([^/]*\)/vmlinuz$|\1|p' | head -1)
echo "$(date +%T) bootonce $tag ($krel)"
M1_CLAIM=${M1_CLAIM:?export M1_CLAIM=<who> after m1-claim take} timeout 400 tools/tb/m1-bootonce "$pkg" "$tag" "$cl" > $out-bootonce.log 2>&1 || { echo "bootonce failed"; exit 1; }
t0=$(date +%s)
while [ $(( $(date +%s) - t0 )) -lt 300 ]; do
  r=$(timeout 8 tools/tb/m1tb "uname -r; cat /proc/uptime" 2>/dev/null) && case "$r" in *$krel*) up=$(echo "$r" | sed -n 2p | cut -d. -f1); [ "${up:-0}" -ge 40 ] && break;; esac
  sleep 4
done
case "$r" in *$krel*) ;; *) echo "test kernel not up: $r"; exit 1;; esac
$S/start.sh $mask | tee $out-start.txt
grep -q started $out-start.txt || exit 1
$S/waitread.sh $krel | tee $out-after.txt
