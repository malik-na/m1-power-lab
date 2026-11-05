#!/bin/bash
# m1power probe: a maclab --script test (runs as root on the Lab boot).
#
# Payload (in $MACLAB_IN): agent.py, m1power.c, Makefile, lib.sh, plan.json,
# and optionally module-build.tar.zst from the lab build of a test kernel.
# Loads m1power.ko when it can (SMC energy counters and the s2idle wake timer;
# macsmc-hwmon otherwise), runs `agent.py probe`, and leaves result.json, the
# module build log and a few facts in $MACLAB_OUT for labd to collect.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
# shellcheck source=lib.sh
. "$MACLAB_IN/lib.sh"

work=$(mktemp -d /run/m1power-probe.XXXXXX)
trap 'unload_m1power; rm -rf "$work"' EXIT

cp "$MACLAB_IN/agent.py" "$work/agent.py"
{
	echo "kernel=$(uname -r)"
	echo "cmdline=$(cat /proc/cmdline)"
	echo "model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
} > "$MACLAB_OUT/facts.txt"

load_m1power "$work"
python3 -I "$work/agent.py" probe --plan "$MACLAB_IN/plan.json" --out "$MACLAB_OUT/result.json"
rc=$?
log "probe exited $rc"
exit $rc
