#!/bin/bash
# No-sleep self-test of the PMP idle path (Linux S2R test 2's hook): start the PMP
# (pmp_v1, needs apple_pmp_v1_hold=1), then idle it (AP 0x201, IOP 0x201, each acked)
# and wake it again through /sys/module/apple_s2r/parameters/pmp_idle_test.
set -u
: "${MACLAB_OUT:?}"
exec > "$MACLAB_OUT/log.txt" 2>&1
result() { printf '%s\n' "$*" > "$MACLAB_OUT/result.txt"; }
grep -qw apple_pmp_v1_hold=1 /proc/cmdline || { result "VERDICT SKIP needs apple_pmp_v1_hold=1"; exit 0; }
modprobe apple-pmp-v1 2>&1; sleep 5
dmesg | grep -E "PMPv1|PMP power hook" | tail -12
dmesg | grep -q "PMPv1: S2R idle hook registered" || { result "VERDICT FAIL the PMP did not come up"; exit 0; }
echo 1 > /sys/module/apple_s2r/parameters/pmp_idle_test; rc=$?
sleep 1
dmesg | grep -E "PMP idle test|PMPv1|rtkit|RTKit" | tail -20
idle=$(dmesg | grep -o "PMP idle test: idle .* -> -\?[0-9]*" | tail -1)
wake=$(dmesg | grep -o "PMP idle test: wake -> -\?[0-9]*" | tail -1)
result "VERDICT rc=$rc | $idle | $wake"
