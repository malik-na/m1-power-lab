#!/bin/bash
# Lab job script for m1power/s2r-pmu-rtc (v2, head 7e874c1b05d0).
#
# Checks the Sera PMU RTC alarm on t8103:
#   1. the opt-in DT fixup ran (needs --cmdline apple_t8103_pmu_alarm=1) and
#      rtc-macsmc logged the PMU alarm bytes as firmware left them;
#   2. SPMI's parent interrupt is live (no "NOTIFY not delivered", no storm);
#   3. an awake +5 s alarm raises the RTC's interrupt and the driver takes it
#      as the alarm;
#   4. only if all of that passed AND m1power's wake timer is armed as a backup
#      wake: one s2idle sleep, `rtcwake -m freeze -s 30`. The backup fires at
#      75 s, so the job never sleeps longer than that (lab budget: 120 s in
#      total; the lab cannot wake the Mac and apple_wdt stops in s2idle).
# It records which source woke the Mac.
#
# PMU access: reads only, through nvmem sysfs, of 0xd000-0xd00b and 0xd00e;
# 0xd00c once, after the alarm. The driver itself writes only the alarm's own
# bits and, by default, never writes 0xd00c (rtc_macsmc.event_clear=0).
#
# Payload: lib.sh, m1power.c, Makefile (target/lab, target/kmod) and the
# build's module-build.tar.zst (slimmed: vmlinux dropped), so m1power.ko can
# be built on the Lab boot. Result: $MACLAB_OUT/result.txt, first line
# "VERDICT ...".
#
# Run (kernel build b1105-175339-6471, release 7.2.11-lab7e874c1b-264d):
#   P=/home/naeem/Projects/m1-power-lab/target
#   lab run naeems-m1-airr --kernel b1105-175339-6471 \
#     --cmdline apple_t8103_pmu_alarm=1 --script lab-rtcwake-test.sh \
#     --payload lib.sh=$P/lab/lib.sh --payload m1power.c=$P/kmod/m1power.c \
#     --payload Makefile=$P/kmod/Makefile \
#     --payload module-build.tar.zst=payload/module-build.tar.zst \
#     --script-timeout 20m --no-wait
#   (paths relative to this script's directory)
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
MACLAB_TEST=pmu-rtc
# shellcheck source=/dev/null
. "$MACLAB_IN/lib.sh"
exec > "$MACLAB_OUT/log.txt" 2>&1

BACKUP_S=75	# m1power wake timer, armed just before the sleep
SLEEP_S=30	# the RTC alarm the sleep is meant to end on

work=$(mktemp -d /run/pmu-rtc.XXXXXX)
RTC=
VERDICT="not finished"
finish() {
	[ -n "$RTC" ] && echo 0 > "$RTC/wakealarm" 2>/dev/null
	unload_m1power
	rm -rf "$work"
	{ echo "VERDICT $VERDICT"; echo; cat "$MACLAB_OUT/log.txt"; } > "$MACLAB_OUT/result.txt"
}
trap finish EXIT
stop() { VERDICT="$*"; log "STOP: $*"; exit 0; }

irq_count() { # IRQ -> total over CPUs
	tr ', ' '\n\n' < "/sys/kernel/irq/$1/per_cpu_count" | awk '{ s += $1 } END { print s + 0 }'
}
dmesg_since() { dmesg | awk -v n="$1" 'NR > n'; }

echo "== kernel"; uname -r; cat /proc/cmdline
grep -qw 'apple_t8103_pmu_alarm=1' /proc/cmdline || log "cmdline lacks apple_t8103_pmu_alarm=1: the fixup stays off"

echo "== fixup, SPMI and RTC messages"
dmesg | grep -iE 't8103-pmu-alarm|macsmc-rtc|apple-spmi|spmi|NOTIFY not delivered|stuck|alarm IRQ|firmware alarm state' | tail -40

DT=/proc/device-tree/soc/spmi@23d0d9300
echo "== live DT"; ls "$DT"; ls "$DT/pmic@f/nvmem-layout"
[ -e "$DT/interrupts" ] && od -An -tx1 "$DT/interrupts"

SPMI_STATS=$(ls /sys/bus/platform/devices/*/irq_stats 2>/dev/null | grep -i spmi | head -1)
spmi_stats() { [ -n "$SPMI_STATS" ] && cat "$SPMI_STATS"; }
echo "== interrupts"
grep -E 'spmi|rtc|[[:space:]]343[[:space:]]' /proc/interrupts
echo "spmi irq_stats ($SPMI_STATS): $(spmi_stats)"
echo "mem_sleep: $(cat /sys/power/mem_sleep 2>/dev/null)"

for r in /sys/class/rtc/rtc*; do
	case "$(readlink -f "$r/device/driver")" in *macsmc*) RTC=$r ;; esac
done
[ -n "$RTC" ] || stop "no macsmc RTC"
DEVNAME=$(basename "$(readlink -f "$RTC/device")")
RTC_IRQ=$(grep -lFx "$DEVNAME" /sys/kernel/irq/*/actions 2>/dev/null | head -1 | cut -d/ -f5)
echo "== rtc $RTC ($DEVNAME), irq ${RTC_IRQ:-none}"
cat "$RTC/name"; echo "wakeup: $(cat "$RTC/device/power/wakeup" 2>/dev/null)"
[ -e "$RTC/wakealarm" ] || stop "no wakealarm: the RTC has no alarm (fixup off or alarm cells missing)"
[ -n "$RTC_IRQ" ] || stop "no IRQ action named $DEVNAME"

NV=$(ls -d /sys/bus/nvmem/devices/spmi_nvmem* 2>/dev/null | head -1)
pmu_at() { # OFFSET COUNT
	[ -n "$NV" ] && dd if="$NV/nvmem" bs=1 skip=$(($1)) count="$2" 2>/dev/null | od -An -tx1
}
pmu() { echo "0xd000-0xd00b: $(pmu_at 0xd000 12)  0xd00e: $(pmu_at 0xd00e 1)"; }
echo "== PMU before ($NV)"; pmu

echo "== awake alarm, +5 s"
n0=$(dmesg | wc -l)
c0=$(irq_count "$RTC_IRQ")
echo 0 > "$RTC/wakealarm"
echo +5 > "$RTC/wakealarm" || stop "could not set the awake alarm"
echo "wakealarm set: $(cat "$RTC/wakealarm")"
pmu
sleep 8
c1=$(irq_count "$RTC_IRQ")
echo "wakealarm after: '$(cat "$RTC/wakealarm")'"
echo "rtc irq $RTC_IRQ: $c0 -> $c1"
echo "spmi irq_stats: $(spmi_stats)"
echo "== PMU after the awake alarm"; pmu; echo "0xd00c: $(pmu_at 0xd00c 1)"
echo "== new kernel messages"; dmesg_since "$n0"

# Gate: sleep only on a proven alarm path.
[ "$c1" -ge $((c0 + 1)) ] || stop "awake alarm raised no RTC interrupt ($c0 -> $c1): no sleep"
dmesg_since "$n0" | grep -q 'alarm IRQ: .*: fired' || stop "RTC interrupt came but the driver did not take it as the alarm: no sleep"
dmesg | grep -qE 'NOTIFY not delivered|interrupt [0-9]+ stuck' && stop "SPMI interrupt is dead (polling): no sleep"
spmi_stats | grep -q 'dead_irq 0' || stop "SPMI irq_stats missing or dead_irq set: no sleep"
[ "$(cat "$RTC/device/power/wakeup" 2>/dev/null)" = enabled ] || stop "RTC wakeup not enabled: no sleep"
[ -e /sys/power/pm_wakeup_irq ] || stop "no /sys/power/pm_wakeup_irq to tell the wake source: no sleep"
log "awake alarm passed"

echo "== backup wake: m1power wake timer, $BACKUP_S s"
load_m1power "$work"
WT=/sys/kernel/debug/m1power/waketimer
[ -e "$WT" ] || stop "awake alarm passed, but no m1power wake timer for a backup wake: no sleep"
echo "$BACKUP_S" > "$WT" || stop "could not arm the m1power wake timer: no sleep"
grep -q '^armed 1' "$WT" || stop "m1power wake timer did not arm: no sleep"
WDT_IRQ=$(awk '/^irq /{print $2}' "$WT")
cat "$WT"

echo "== rtcwake -m freeze -s $SLEEP_S"
s0=$(irq_count "$RTC_IRQ"); st0=$(spmi_stats)
grep -iE 'rtc|macsmc|m1power' /sys/kernel/debug/wakeup_sources 2>/dev/null
n1=$(dmesg | wc -l)
f0=$(awk '/^fired_total /{print $2}' "$WT")
t0=$(date +%s)
rtcwake -d "$(basename "$RTC")" -m freeze -s "$SLEEP_S"; rc=$?
t1=$(date +%s)
WAKE_IRQ=$(cat /sys/power/pm_wakeup_irq 2>/dev/null)
echo "rtcwake rc $rc, slept $((t1 - t0)) s, pm_wakeup_irq '${WAKE_IRQ}' (rtc $RTC_IRQ, m1power wdt $WDT_IRQ)"
echo "== m1power wake timer after"; cat "$WT"
f1=$(awk '/^fired_total /{print $2}' "$WT"); echo 0 > "$WT"
s1=$(irq_count "$RTC_IRQ")
echo "rtc irq $RTC_IRQ: $s0 -> $s1"
echo "spmi irq_stats: $st0 -> $(spmi_stats)"
grep -iE 'rtc|macsmc|m1power' /sys/kernel/debug/wakeup_sources 2>/dev/null
echo "== new kernel messages"; dmesg_since "$n1" | tail -60
echo "== PMU after"; pmu; echo "0xd00c: $(pmu_at 0xd00c 1)"

if [ "$rc" -ne 0 ]; then
	VERDICT="awake alarm ok; rtcwake failed (rc $rc), slept $((t1 - t0)) s"
elif [ "$WAKE_IRQ" = "$RTC_IRQ" ]; then
	VERDICT="PASS: woken by the PMU RTC alarm after $((t1 - t0)) s"
elif [ -z "$WAKE_IRQ" ] && [ -n "$f1" ] && [ "${f1:-0}" -gt "${f0:-0}" ]; then
	# m1power wakes through pm_system_wakeup(), which leaves pm_wakeup_irq empty
	VERDICT="awake alarm ok; sleep woken by the m1power BACKUP after $((t1 - t0)) s, not the RTC"
elif [ -n "$WDT_IRQ" ] && [ "$WAKE_IRQ" = "$WDT_IRQ" ]; then
	VERDICT="awake alarm ok; sleep woken by the m1power BACKUP after $((t1 - t0)) s, not the RTC"
else
	VERDICT="awake alarm ok; woken by irq '${WAKE_IRQ}' after $((t1 - t0)) s (neither rtc $RTC_IRQ nor wdt $WDT_IRQ)"
fi
log "$VERDICT"
