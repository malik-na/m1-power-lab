#!/bin/bash
# m1power-display: a maclab --script test of display-on idle power on the
# kernel the job boots (for DCP driver experiments).
#
# Payload: agent.py, m1power.c, Makefile, lib.sh, plan.json
# ({"pairs": 4, "settle_s": 15, "measure_s": 30, "backlight": "16",
#   "boot_settle_s": 90}), optionally module-build.tar.zst.
#
# Holds an idle inhibitor so the session's idle daemon does not blank the
# panel mid-block, fixes the backlight, then runs a paired display on/off
# A/B (the panel's cost at that backlight) and records PMGR gating, display
# coprocessor interrupts and DCP kernel lines with the panel on and off.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
# shellcheck source=lib.sh
. "$MACLAB_IN/lib.sh"

work=$(mktemp -d /run/m1power-display.XXXXXX)
cp "$MACLAB_IN/agent.py" "$work/agent.py"
agent() { python3 -I "$work/agent.py" "$@"; }
plan() { python3 -c "import json; print(json.load(open('$MACLAB_IN/plan.json')).get('$1', '$2'))"; }
inhibitor=""
finish() {
	agent restore >/dev/null 2>&1 || true
	[ -n "$inhibitor" ] && kill "$inhibitor" 2>/dev/null
	unload_m1power
	rm -rf "$work"
}
trap finish EXIT

load_m1power "$work"
wait_uptime "$(plan boot_settle_s 90)"
systemd-inhibit --what=idle --who=m1power --why="display power experiment" sleep 3600 &
inhibitor=$!

agent knob backlight "$(plan backlight 16)" > "$MACLAB_OUT/backlight.json" 2>&1

irq_rates() { # SECONDS -> top interrupt rates
	cp /proc/interrupts "$work/irq0"
	sleep "$1"
	python3 - "$work/irq0" "$1" <<'PY'
import sys
def parse(p):
    rows = {}
    lines = open(p).read().splitlines()
    n = len(lines[0].split())
    for line in lines[1:]:
        x = line.split()
        rows[x[0]] = (sum(int(v) for v in x[1:1 + n] if v.isdigit()), " ".join(x[1 + n:]))
    return rows
a, b = parse(sys.argv[1]), parse("/proc/interrupts")
secs = float(sys.argv[2])
for n, k, name in sorted(((b[k][0] - a.get(k, (0,))[0], k, b[k][1]) for k in b), reverse=True)[:12]:
    if n:
        print(f"{n / secs:8.1f}/s {name}")
PY
}

for state in on off; do
	agent knob display "$state" > "$MACLAB_OUT/display-$state.json" 2>&1
	sleep 10
	irq_rates 10 > "$MACLAB_OUT/irq-$state.txt"
	[ -e /sys/kernel/debug/m1power/pmgr_duty ] && cat /sys/kernel/debug/m1power/pmgr_duty > "$MACLAB_OUT/pmgr-duty-$state.txt"
done

agent ab --knob display --a off --b on --pairs "$(plan pairs 4)" --settle "$(plan settle_s 15)" \
	--measure "$(plan measure_s 30)" --force --out "$MACLAB_OUT/ab.json" >/dev/null
rc=$?
dmesg | grep -iE 'dcp|iomfb|apple-drm|appledrm' | tail -80 > "$MACLAB_OUT/dcp-kernel.txt"

python3 - <<'PY'
import json, os
out = os.environ["MACLAB_OUT"]
def load(name):
    try:
        with open(os.path.join(out, name)) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None
def lines(name):
    try:
        with open(os.path.join(out, name)) as handle:
            return handle.read().splitlines()
    except OSError:
        return []
result = {
    "kind": "display-ab",
    "kernel": os.uname().release,
    "job": os.environ.get("MACLAB_JOB"),
    "ab": load("ab.json"),
    "irq_on": lines("irq-on.txt"),
    "irq_off": lines("irq-off.txt"),
    "pmgr_duty_on": lines("pmgr-duty-on.txt"),
    "pmgr_duty_off": lines("pmgr-duty-off.txt"),
    "dcp_kernel": lines("dcp-kernel.txt")[-40:],
    "status": "complete",
}
with open(os.path.join(out, "result.json"), "w") as handle:
    json.dump(result, handle, indent=1, sort_keys=True)
PY
log "display A/B exited $rc"
exit $rc
