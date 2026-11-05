#!/bin/bash
# m1power-stress: a maclab --script test of suspend reliability under a
# Wi-Fi link power configuration, on the kernel the job boots.
#
# Payload: agent.py, m1power.c, Makefile, lib.sh, plan.json
# ({"cycles": 15, "awake_s": 30, "sleep_s": 30, "boot_settle_s": 60,
#   "knobs": {"aspm": "powersupersave", ...}}), optionally module-build.tar.zst.
# Each sleep stays well under the two minutes after which labd notifies.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
# shellcheck source=lib.sh
. "$MACLAB_IN/lib.sh"

work=$(mktemp -d /run/m1power-stress.XXXXXX)
trap 'unload_m1power; rm -rf "$work"' EXIT
cp "$MACLAB_IN/agent.py" "$work/agent.py"
plan() { python3 -c "import json; print(json.load(open('$MACLAB_IN/plan.json')).get('$1', '$2'))"; }

load_m1power "$work"
if [ ! -e /sys/kernel/debug/m1power/waketimer ]; then
	log "no wake timer on this boot: cannot run unattended suspend cycles"
	exit 2
fi
wait_uptime "$(plan boot_settle_s 60)"

sets=()
while IFS='=' read -r knob value; do
	[ -n "$knob" ] && sets+=(--set "$knob" "$value")
done < <(python3 -c "import json; [print(f'{k}={v}') for k, v in json.load(open('$MACLAB_IN/plan.json')).get('knobs', {}).items()]")

python3 -I "$work/agent.py" stress --cycles "$(plan cycles 15)" --awake "$(plan awake_s 30)" \
	--sleep "$(plan sleep_s 30)" "${sets[@]}" --restore --force --out "$MACLAB_OUT/result.json" >/dev/null
rc=$?
journalctl -k -b --no-pager | grep -iE 'brcmf|D3|failed to suspend' > "$MACLAB_OUT/wifi-kernel.txt"
log "stress exited $rc"
exit $rc
