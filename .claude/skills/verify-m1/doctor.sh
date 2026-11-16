#!/bin/bash
# verify-m1 doctor: READ-ONLY check of whether the M1 Air is worth driving right now.
#   .claude/skills/verify-m1/doctor.sh          (run from anywhere on the M3 Max)
# Prints one line per check and a verdict. Exit 0 = drivable, 1 = not drivable (reason printed),
# 2 = the M1 cannot be reached at all. Changes nothing on either machine.
set -uo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
tb="$repo/tools/tb"
bad=0
say() { printf '%-22s %s\n' "$1" "$2"; }
fail() { say "$1" "FAIL: $2"; bad=1; }

# --- M3 Max side ---------------------------------------------------------------------------
if [ -e /sys/class/net/thunderbolt0 ] && [ "$(cat /sys/class/net/thunderbolt0/carrier 2>/dev/null)" = 1 ]; then
	say "cable link" "up ($(cat /sys/bus/thunderbolt/devices/0-1/device_name 2>/dev/null), $(cat /sys/bus/thunderbolt/devices/0-1/rx_lanes 2>/dev/null)x$(cat /sys/bus/thunderbolt/devices/0-1/rx_speed 2>/dev/null))"
	via=m1tb
else
	say "cable link" "down (no thunderbolt0 carrier): using Wi-Fi (m1ts)"
	via=m1ts
fi
if pgrep -f 'tools/tb/m3-blackbox' >/dev/null; then say "M3 flight recorder" "running"
elif [ "$via" = m1tb ]; then fail "M3 flight recorder" "not running while the cable is in: start $tb/m3-blackbox & (see SKILL.md, Launch)"
else say "M3 flight recorder" "not running (cable out: optional)"; fi
say "M3 power" "ac=$(cat /sys/class/power_supply/macsmc-ac/online 2>/dev/null) battery=$(cat /sys/class/power_supply/macsmc-battery/capacity 2>/dev/null)%"

# --- M1 side ---------------------------------------------------------------------------------
if [ "$via" = m1tb ]; then m1() { "$tb/m1tb" -o BatchMode=yes -o ConnectTimeout=5 "$@"; }
else m1() { ssh -o BatchMode=yes -o ConnectTimeout=6 m1ts "$@"; }; fi
out=$(m1 'set -u
echo "host=$(hostname)"
echo "kernel=$(uname -r)"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"
echo "uptime=$(cut -d" " -f1 /proc/uptime)"
echo "cmdline_lab=$(grep -oE "maclab\.[a-z_]+=[^ ]*|apple_s2r_rs\.[a-z_]+=[^ ]*" /proc/cmdline | tr "\n" " ")"
echo "fw=$(tr -d "\0" < /sys/firmware/devicetree/base/chosen/asahi,system-fw-version 2>/dev/null) iboot=$(tr -d "\0" < /sys/firmware/devicetree/base/chosen/asahi,iboot1-version 2>/dev/null)"
b=/sys/class/power_supply/macsmc-battery
echo "battery=$(cat $b/capacity)% $(cat $b/status) $(cat $b/current_now)uA behaviour=$(grep -o "\[[a-z-]*\]" $b/charge_behaviour)"
echo "ac=$(cat /sys/class/power_supply/macsmc-ac/online)"
for p in /sys/class/typec/port?; do echo "typec.$(basename $p)=$(grep -o "\[[a-z]*\]" $p/power_role) partner=$([ -e $p-partner ] && (cat $p-partner/identity/id_header 2>/dev/null || echo present) || echo none)"; done
nv=$(for d in /sys/bus/nvmem/devices/spmi_nvmem*; do [ "$(dd if=$d/nvmem bs=1 skip=$((0x0201)) count=1 2>/dev/null | wc -c)" = 1 ] && echo $d; done | tail -1)
echo "pmu0201=$(dd if=$nv/nvmem bs=1 skip=$((0x0201)) count=1 2>/dev/null | od -An -tx1 | tr -d " ")"
echo "m1power_ko=$(lsmod | grep -q "^m1power " && echo loaded || echo absent)"
echo "wifi_ps=$(iw dev wlan0 get power_save 2>/dev/null | awk "{print \$3}")"
gw=$(ip -4 route show default | awk "{print \$3; exit}")
echo "gateway_rtt=$(ping -c3 -i0.2 -W1 -q $gw 2>/dev/null | tail -1 | cut -d= -f2)"
echo "lab_job_out=$(ls -t /var/lib/maclab/jobs 2>/dev/null | head -1)"
' 2>&1) || { say "M1" "UNREACHABLE via $via: $out"; echo "VERDICT: not drivable (M1 unreachable)"; exit 2; }
while IFS= read -r l; do k=${l%%=*}; v=${l#*=}; say "M1 $k" "$v"; done <<< "$out"
kv() { sed -n "s/^$1=//p" <<< "$out"; }
[ "$(kv wifi_ps)" = on ] && fail "M1 wifi" "power save is ON: earlier tuning left Wi-Fi with high latency; standing rule: do not change it, report it"
case "$(kv kernel)" in 7.3.0-0test5-1-ARCH) ;; *) say "M1 kernel note" "not the stock kernel: a lab test boot is in progress or a test kernel stayed" ;; esac
[ -n "$(kv cmdline_lab)" ] && fail "M1 boot" "this is a lab/test boot ($(kv cmdline_lab)): something else is driving it"

# --- lab ----------------------------------------------------------------------------------------
ls=$(timeout 20 lab status naeems-m1-air-r25 2>&1 | head -1)
say "lab" "$ls"
case "$ls" in *READY*) ;; *OFFLINE*) say "lab note" "lab-agent cannot reach labd: lab runs will not start; m1tb/m1ts still work" ;; *) fail "lab" "the lab is using the M1 (job or boot in progress): do not drive it" ;; esac

[ $bad = 0 ] && echo "VERDICT: drivable via $via" || echo "VERDICT: not drivable (see FAIL lines)"
exit $bad
