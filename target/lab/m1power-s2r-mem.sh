#!/bin/bash
# Lab job script for m1power/s2r-mem stage 1: one real suspend-to-RAM on t8103.
#
# Kernel: malik-na/linux-aurora m1power/s2r-mem (apple-s2r.c + the hotplug S2R
# deep stop). Cmdline: apple_s2r=1 apple_cpu_hotplug=park.
#
# What it does:
#   1. checks the driver registered "mem" (dmesg "apple-s2r: enabled",
#      /sys/power/mem_sleep offers deep);
#   2. writes a pre-sleep snapshot (time, PMU RTC, PMU scratch 0x9f00-0x9f1f,
#      the RTC alarm block) to $MACLAB_OUT and, synced, to
#      /var/lib/m1power-s2r/, because the wake does not resume: it comes back
#      through the locked RVBAR into m1n1 and boots again, so this job ends
#      with the Mac rebooting, and only /var survives for the follow-up read;
#   3. sets the driver's PMU alarm (apple_s2r.alarm_secs, default 60 s) and
#      enters "mem". The SoC should power off within about 0.7 s and the
#      alarm should bring it back.
# If the entry is refused (a device's suspend failed, the CPUs did not go
# offline) the write to /sys/power/state returns and the job reports it.
#
# The follow-up, on the next boot (lab exec or ssh): s2r-mem-readback.sh.
set -u
: "${MACLAB_OUT:?}"
MACLAB_TEST=s2r-mem
exec > "$MACLAB_OUT/log.txt" 2>&1
log() { printf '[%s %s] %s\n' "$MACLAB_TEST" "$(date +%T.%N | cut -c1-12)" "$*"; }
result() { printf '%s\n' "$*" > "$MACLAB_OUT/result.txt"; }

ALARM=${S2R_ALARM_S:-60}
STATE=/var/lib/m1power-s2r
mkdir -p "$STATE"
STAMP=$(date +%Y%m%d-%H%M%S)
PRE="$STATE/pre-$STAMP.txt"

NV=$(ls -d /sys/bus/nvmem/devices/spmi_nvmem* 2>/dev/null | head -1)
pmu_at() { [ -n "$NV" ] && dd if="$NV/nvmem" bs=1 skip=$(($1)) count="$2" 2>/dev/null | od -An -tx1; }

log "kernel $(uname -r): $(cat /proc/cmdline)"
grep -qw apple_s2r=1 /proc/cmdline || { result "VERDICT SKIP cmdline lacks apple_s2r=1"; exit 0; }
dmesg | grep -E "apple-s2r|apple-cpu-hotplug" | tail -20
dmesg | grep -q "apple-s2r: enabled" || { result "VERDICT FAIL apple-s2r did not register (see log)"; exit 0; }
# Linux test 2: with apple_pmp_v1_hold=1, start the PMP (pmp_v1) so apple-s2r can idle it
if grep -qw apple_pmp_v1_hold=1 /proc/cmdline; then
	modprobe apple-pmp-v1 2>&1 || modprobe apple_pmp_v1 2>&1
	sleep 5
	dmesg | grep -E "PMPv1|PMP power hook" | tail -15
	dmesg | grep -q "PMPv1: S2R idle hook registered" || { result "VERDICT SKIP the PMP did not come up (no S2R idle hook)"; exit 0; }
fi
log "mem_sleep: $(cat /sys/power/mem_sleep)"
grep -q deep /sys/power/mem_sleep || { result "VERDICT FAIL no deep in mem_sleep"; exit 0; }
P=/sys/module/apple_s2r/parameters
echo "$ALARM" > "$P/alarm_secs"
echo 1 > "$P/stop_cores"
log "alarm_secs $(cat $P/alarm_secs) stop_cores $(cat $P/stop_cores) deadman_secs $(cat $P/deadman_secs)"
log "sync_on_suspend $(cat /sys/power/sync_on_suspend 2>/dev/null)"
[ -e /sys/class/typec/port0 ] && log "typec: $(for p in /sys/class/typec/port?; do echo -n "$(basename $p) $(cat $p/power_role 2>/dev/null) partner=$(ls $p | grep -c partner); "; done)"
log "online CPUs: $(cat /sys/devices/system/cpu/online)"

# Pre-check: is the RVBAR target (the resident stage-2 m1n1) reserved from Linux and intact?
# cpu0's locked RVBAR lives in its cpu-impl-reg (t8103 cpu0: 0x210050000; bit 0 lock, 47:12 address).
{
	echo "== RVBAR pre-check"
	python3 - <<'PY' 2>&1
import mmap, os, struct, hashlib, glob
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x210050000)
rv = struct.unpack("<Q", m[0:8])[0]; m.close()
addr = rv & 0x0000fffffffff000
print(f"cpu0 RVBAR reg {rv:#x}: address {addr:#x}, locked {rv & 1}")
for line in open("/proc/iomem"):
    a, b = [int(x, 16) for x in line.split(":")[0].strip().split("-")]
    if a <= addr <= b or (addr - 0x200000 <= a <= addr + 0x200000):
        print("iomem:", line.rstrip())
esp = next((f for f in ("/boot/efi/m1n1/boot.bin", "/efi/m1n1/boot.bin", "/boot/m1n1/boot.bin") if os.path.exists(f)), None)
ref = open(esp, "rb").read(0x1000) if esp else b""
try:
    pg = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=addr)
    live = pg[:0x1000]; pg.close()
    print("RVBAR page sha", hashlib.sha256(live).hexdigest()[:16], "ESP stage-2 first page sha", hashlib.sha256(ref).hexdigest()[:16],
          "MATCH" if live == ref else "DIFFERENT", "first words", live[:16].hex())
except Exception as e:
    print("RVBAR page not readable via /dev/mem:", e, "(STRICT_DEVMEM refuses System RAM: the page is NOT nomap-reserved)")
PY
	echo "cpu-start alive mask 0x23b754004: $(python3 -c "
import mmap,os,struct; fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC); m=mmap.mmap(fd,0x4000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x23b754000); print(hex(struct.unpack('<I',m[4:8])[0]))" 2>&1)"
} | tee "$MACLAB_OUT/rvbar-precheck.txt"
cp "$MACLAB_OUT/rvbar-precheck.txt" "$STATE/rvbar-precheck-$STAMP.txt"

{
	echo "stamp $STAMP"
	echo "kernel $(uname -r)"
	echo "date_epoch $(date +%s.%N)"
	echo "uptime $(cut -d' ' -f1 /proc/uptime)"
	echo "alarm_s $ALARM"
	echo "pmu_rtc_d000_d00f $(pmu_at 0xd000 16)"
	echo "pmu_scratch_9f00_9f1f $(pmu_at 0x9f00 32)"
	for z in /sys/class/power_supply/macsmc-battery/energy_now /sys/class/power_supply/macsmc-battery/charge_now \
		/sys/class/power_supply/macsmc-battery/current_now /sys/class/power_supply/macsmc-battery/status; do
		[ -e "$z" ] && echo "$(basename "$z") $(cat "$z")"
	done
	if [ -e /sys/kernel/debug/m1power/smc ]; then
		grep -E "zSLa|zSPa" /sys/kernel/debug/m1power/smc 2>/dev/null
	fi
} | tee "$PRE" > "$MACLAB_OUT/pre.txt"
sync
log "snapshot in $PRE"

result "VERDICT ENTERED mem at $(date +%T) (alarm +$ALARM s); a reboot after this is the expected wake"
cp "$MACLAB_OUT/result.txt" "$STATE/entered-$STAMP.txt"
sync
sleep 1

echo deep > /sys/power/mem_sleep
log "echo mem > /sys/power/state"
if echo mem > /sys/power/state; then
	rc=0
else
	rc=$?
fi
# Only reached if the entry was refused or (later stages) resumed.
log "returned rc=$rc"
dmesg | tail -120 > "$MACLAB_OUT/dmesg-after.txt"
result "VERDICT RETURNED rc=$rc: the suspend did not reach the SoC power-off (see dmesg-after.txt)"
cp "$MACLAB_OUT/result.txt" "$STATE/returned-$STAMP.txt"
sync
