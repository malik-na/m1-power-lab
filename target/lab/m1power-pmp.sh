#!/bin/bash
# m1power-pmp: a maclab --script test that starts the PMP v1 firmware on a
# lab kernel built from malik-na/linux-aurora@m1power/pmp-v1 and measures idle
# power before and after, on the same boot (the PMP cannot be stopped again).
#
# Payload: agent.py, m1power.c, Makefile, lib.sh, plan.json
# ({"windows": 4, "measure_s": 40, "after_settle_s": 45, "boot_settle_s": 120,
#   "modprobe_args": ""}), optionally module-build.tar.zst.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
# shellcheck source=lib.sh
. "$MACLAB_IN/lib.sh"

work=$(mktemp -d /run/m1power-pmp.XXXXXX)
cp "$MACLAB_IN/agent.py" "$work/agent.py"
agent() { python3 -I "$work/agent.py" "$@"; }
plan() { python3 -c "import json; print(json.load(open('$MACLAB_IN/plan.json')).get('$1', '$2'))"; }
finish() {
	agent restore >/dev/null 2>&1 || true
	unload_m1power
	rm -rf "$work"
}
trap finish EXIT

load_m1power "$work"
wait_uptime "$(plan boot_settle_s 120)"
agent knob display off > "$MACLAB_OUT/display.json" 2>&1

dmesg | grep -E 'pms_sram|always-on domain|PMPv1|pmp|apple-pmp-v1' > "$MACLAB_OUT/dmesg-before.txt"
[ -e /sys/kernel/debug/m1power/pmgr_ps ] && grep -E '^(pmp|pms_sram|dcs|mcc|nub_fabric|smx|rmx|imx) ' /sys/kernel/debug/m1power/pmgr_ps > "$MACLAB_OUT/pmgr-before.txt"
[ -e /sys/kernel/debug/m1power/pmgr_duty ] && cat /sys/kernel/debug/m1power/pmgr_duty > "$MACLAB_OUT/duty-before.txt"

windows=$(plan windows 4)
measure=$(plan measure_s 40)
for i in $(seq 1 "$windows"); do
	agent record --duration "$measure" --interval 1 --out "$MACLAB_OUT/before-$i.json" >/dev/null 2>&1
done

log "starting the PMP"
journalctl --sync
# shellcheck disable=SC2046
timeout 60 modprobe apple-pmp-v1 $(plan modprobe_args "") > "$MACLAB_OUT/modprobe.txt" 2>&1
echo "rc=$?" >> "$MACLAB_OUT/modprobe.txt"
sleep 5
journalctl --sync
dmesg | grep -E 'PMPv1|apple-pmp-v1|23b300000|pmp|RTKit' | tail -200 > "$MACLAB_OUT/dmesg-pmp.txt"
started=0
grep -q 'handshake complete' "$MACLAB_OUT/dmesg-pmp.txt" && started=1
log "PMP handshake complete: $started"

sleep "$(plan after_settle_s 45)"
for i in $(seq 1 "$windows"); do
	agent record --duration "$measure" --interval 1 --out "$MACLAB_OUT/after-$i.json" >/dev/null 2>&1
done
# Stage 2: device power reports, when the module loaded with reports=0 has
# a switch for them.
reports=/sys/kernel/debug/apple_pmp_v1/reports
if [ "$started" = 1 ] && [ -e "$reports" ] && [ "$(plan reports_phase 1)" = 1 ]; then
	log "turning on PMP device power reports"
	echo 1 > "$reports"
	sleep 5
	dmesg | grep -E 'PMPv1' | tail -80 > "$MACLAB_OUT/dmesg-reports.txt"
	sleep "$(plan after_settle_s 45)"
	for i in $(seq 1 "$windows"); do
		agent record --duration "$measure" --interval 1 --out "$MACLAB_OUT/reports-$i.json" >/dev/null 2>&1
	done
fi
[ -e /sys/kernel/debug/m1power/pmgr_ps ] && grep -E '^(pmp|pms_sram|dcs|mcc|nub_fabric|smx|rmx|imx) ' /sys/kernel/debug/m1power/pmgr_ps > "$MACLAB_OUT/pmgr-after.txt"
[ -e /sys/kernel/debug/m1power/pmgr_duty ] && cat /sys/kernel/debug/m1power/pmgr_duty > "$MACLAB_OUT/duty-after.txt"
dmesg | grep -E 'PMPv1|23b300000' | tail -60 > "$MACLAB_OUT/dmesg-end.txt"

STARTED=$started python3 - <<'PY'
import glob, json, os
out = os.environ["MACLAB_OUT"]
def windows(prefix):
    rows = []
    for path in sorted(glob.glob(os.path.join(out, prefix + "-*.json"))):
        try:
            summary = json.load(open(path)).get("summary", {})
            rows.append({k: summary.get(k) for k in ("sys_w", "sys_w_sd", "soc_w", "load_acc_w", "irq_s", "n")})
        except (OSError, ValueError):
            pass
    return rows
def lines(name):
    try:
        return open(os.path.join(out, name)).read().splitlines()
    except OSError:
        return []
result = {
    "kind": "pmp-start",
    "kernel": os.uname().release,
    "job": os.environ.get("MACLAB_JOB"),
    "pmp_started": os.environ["STARTED"] == "1",
    "before": windows("before"),
    "after": windows("after"),
    "reports": windows("reports"),
    "dmesg_reports": lines("dmesg-reports.txt")[-40:],
    "modprobe": lines("modprobe.txt"),
    "dmesg_pmp": lines("dmesg-pmp.txt")[-80:],
    "dmesg_end": lines("dmesg-end.txt")[-30:],
    "dmesg_before": lines("dmesg-before.txt")[-20:],
    "pmgr_before": lines("pmgr-before.txt"),
    "pmgr_after": lines("pmgr-after.txt"),
    "duty_before": lines("duty-before.txt"),
    "duty_after": lines("duty-after.txt"),
    "status": "complete",
}
with open(os.path.join(out, "result.json"), "w") as handle:
    json.dump(result, handle, indent=1, sort_keys=True)
PY
log "done"
