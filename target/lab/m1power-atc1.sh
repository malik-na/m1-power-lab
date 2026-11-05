#!/bin/bash
# m1power-atc1: a maclab --script test for an unused USB-C port's power cost.
#
# 1. Crash check: unbind the port's dwc3-apple controller and its PHY once.
#    Stock kernels oops here on a never-connected port (dwc3_apple_remove
#    dereferences NULL driver data); the script stops and the lab recovers.
# 2. Paired A/B of the port bound vs unbound (so its ATC power domains can
#    switch off), with the same statistics as `m1power ab`.
# 3. One self-waking sleep each way, when the m1power wake timer is loaded.
#
# Payload: agent.py, m1power.c, Makefile, lib.sh, plan.json
# ({"usb_device": "502280000.usb", "pairs": 3, "settle_s": 10, "measure_s": 30,
#   "sleep_s": 90, "boot_settle_s": 60}), optionally module-build.tar.zst.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
# shellcheck source=lib.sh
. "$MACLAB_IN/lib.sh"

work=$(mktemp -d /run/m1power-atc1.XXXXXX)
cp "$MACLAB_IN/agent.py" "$work/agent.py"
agent() { python3 -I "$work/agent.py" "$@"; }
plan() { python3 -c "import json,sys; print(json.load(open('$MACLAB_IN/plan.json')).get('$1', '$2'))"; }

DEV=$(plan usb_device 502280000.usb)
KNOB="usbport:$DEV"
finish() {
	# Leave the port bound unless the driver crashed (then the lab reboots).
	[ "${OOPSED:-0}" = 1 ] || agent knob "$KNOB" bound >/dev/null 2>&1 || true
	unload_m1power
	rm -rf "$work"
}
trap finish EXIT

load_m1power "$work"
wait_uptime "$(plan boot_settle_s 60)"
agent knob display off > "$MACLAB_OUT/display.json" 2>&1 || true

oopses() { dmesg | grep -c "Unable to handle kernel" || true; }
genpd_atc() { grep -E "^${1:-atc}" /sys/kernel/debug/pm_genpd/pm_genpd_summary 2>/dev/null; }

genpd_atc > "$MACLAB_OUT/atc-domains-bound.txt"
before=$(oopses)
log "unbinding $DEV and its PHY (crash check)"
agent knob "$KNOB" unbound > "$MACLAB_OUT/unbind.json" 2>&1
unbind_rc=$?
sleep 3
after=$(oopses)
genpd_atc > "$MACLAB_OUT/atc-domains-unbound.txt"
dmesg | tail -80 > "$MACLAB_OUT/dmesg-after-unbind.txt"
OOPSED=0
[ "$after" -gt "$before" ] && OOPSED=1

write_result() { # extra-json
	python3 - "$@" <<PY
import json, os, sys
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
    "kind": "atc1-ab",
    "kernel": os.uname().release,
    "job": os.environ.get("MACLAB_JOB"),
    "usb_device": "$DEV",
    "module": "$M1POWER_MODULE",
    "unbind_rc": $unbind_rc,
    "oops": bool($OOPSED),
    "domains_bound": lines("atc-domains-bound.txt"),
    "domains_unbound": lines("atc-domains-unbound.txt"),
    "ab": load("ab.json"),
    "sleep_bound": load("sleep-bound.json"),
    "sleep_unbound": load("sleep-unbound.json"),
    "status": "complete",
}
with open(os.path.join(out, "result.json"), "w") as handle:
    json.dump(result, handle, indent=1, sort_keys=True)
PY
}

if [ "$OOPSED" = 1 ]; then
	log "kernel oopsed unbinding $DEV: stock dwc3-apple remove() bug reproduced"
	write_result
	exit 1
fi
log "unbind clean; domains now: $(tr '\n' ' ' < "$MACLAB_OUT/atc-domains-unbound.txt")"
agent knob "$KNOB" bound > "$MACLAB_OUT/rebind.json" 2>&1 || log "rebind failed"

agent ab --knob "$KNOB" --b unbound --pairs "$(plan pairs 3)" --settle "$(plan settle_s 10)" \
	--measure "$(plan measure_s 30)" --detail --force --out "$MACLAB_OUT/ab.json" >/dev/null
log "A/B done"

if [ -e /sys/kernel/debug/m1power/waketimer ]; then
	secs=$(plan sleep_s 90)
	agent sleep --seconds "$secs" --force --restore --out "$MACLAB_OUT/sleep-bound.json" >/dev/null 2>&1 \
		|| log "bound sleep failed"
	agent sleep --seconds "$secs" --force --restore --set "$KNOB" unbound --out "$MACLAB_OUT/sleep-unbound.json" >/dev/null 2>&1 \
		|| log "unbound sleep failed"
fi

write_result
log "done"
