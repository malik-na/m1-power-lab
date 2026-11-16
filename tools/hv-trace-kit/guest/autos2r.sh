#!/bin/bash
# m1hv-autos2r: one suspend-to-RAM entry, unattended, for a Linux boot under the m1n1 hypervisor
# (no network or console there). Runs only when the command line has m1hv.autos2r=1
# (m1hv-autos2r.service). Each step is logged to the disk and to the kernel log.
L=/var/lib/m1power-s2r/hv-autos2r-$(date +%Y%m%d-%H%M%S).txt
mkdir -p /var/lib/m1power-s2r
say() { echo "m1hv: $(date +%T.%3N) $*" | tee -a "$L" > /dev/kmsg; }
DELAY=$(sed -n 's/.*m1hv.delay=\([0-9]*\).*/\1/p' /proc/cmdline); DELAY=${DELAY:-90}
say "start; kernel $(uname -r); entry in $DELAY s"
sleep "$DELAY"
say "mem_sleep $(cat /sys/power/mem_sleep); $(dmesg | grep -c 'apple_s2r_rs: enabled for') enabled line(s)"
say "aop sensors: $(lsmod | awk '$1 ~ /aop/ {printf "%s ", $1}')"
modprobe apple-pmp-v1; say "modprobe apple-pmp-v1 rc=$?"
for i in $(seq 1 30); do dmesg | grep -q 'PMPv1: S2R idle hook registered' && break; sleep 1; done
say "pmp hook: $(dmesg | grep -c 'PMPv1: S2R idle hook registered')"
echo force-discharge > /sys/class/power_supply/macsmc-battery/charge_behaviour 2>/dev/null
say "battery $(cat /sys/class/power_supply/macsmc-battery/status 2>/dev/null) ac $(cat /sys/class/power_supply/macsmc-ac/online 2>/dev/null)"
# The Secure Enclave as the lab's run script brings it up (run39.sh): not loaded at boot
# (modprobe.blacklist=apple_sep), loaded with no writes, its bring-up waited for, and unloaded
# directly before the write of "mem" (enter.sh).
if lsmod | grep -q '^apple_sep'; then say "apple-sep already loaded at boot: no entry"; exit 1; fi
modprobe apple-sep xart_writes=0 provision_keybag=0 xart_guard=2; say "modprobe apple-sep rc=$?"
for j in $(seq 1 40); do dmesg | grep -qE "apple_sep.*hwrng: (registered|survey failed after)" && break; sleep 0.25; done
say "sep bring-up: $(dmesg | grep -E 'apple_sep.*hwrng: (registered|survey failed after)' | tail -1 | cut -c1-100)"
sync; sleep 2
rmmod apple-sep; rc=$?; say "rmmod apple-sep rc=$rc"
[ $rc = 0 ] || { say "the Secure Enclave's driver could not be unloaded: no entry"; exit 1; }
say "entry: echo mem > /sys/power/state"; sync
echo mem > /sys/power/state; rc=$?
say "returned from the entry rc=$rc"
dmesg | grep -E 'apple_s2r_rs|s2r-trace|PM: ' | tail -40 >> "$L"
sync
