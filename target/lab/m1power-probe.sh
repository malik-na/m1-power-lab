#!/bin/bash
# m1power probe: a maclab --script test (runs as root on the Lab boot).
#
# Payload (in $MACLAB_IN): agent.py, m1power.c, Makefile, plan.json.
# Builds m1power.ko against this boot's kernel headers when they exist (SMC
# energy counters and the s2idle wake timer), falls back to macsmc-hwmon when
# they don't, runs `agent.py probe`, and leaves result.json, the module build
# log and a few facts in $MACLAB_OUT for labd to collect.
set -u
: "${MACLAB_OUT:?}" "${MACLAB_IN:?}"
log() { printf '[m1power-probe] %s\n' "$*"; }

work=$(mktemp -d /run/m1power-probe.XXXXXX)
loaded_here=0
cleanup() {
	if [ "$loaded_here" = 1 ]; then
		echo 0 > /sys/kernel/debug/m1power/waketimer 2>/dev/null || true
		rmmod m1power 2>/dev/null || true
	fi
	rm -rf "$work"
}
trap cleanup EXIT

release=$(uname -r)
cp "$MACLAB_IN/agent.py" "$work/agent.py"
{
	echo "kernel=$release"
	echo "cmdline=$(cat /proc/cmdline)"
	echo "model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
} > "$MACLAB_OUT/facts.txt"

if [ -d /sys/kernel/debug/m1power ]; then
	log "m1power module already loaded"
elif [ -e "/lib/modules/$release/build/Makefile" ]; then
	mkdir -p "$work/kmod"
	cp "$MACLAB_IN/m1power.c" "$MACLAB_IN/Makefile" "$work/kmod/"
	build=(make -C "$work/kmod" KDIR="/lib/modules/$release/build")
	# Kernels built with clang want LLVM=1; fall back to it if gcc fails.
	if "${build[@]}" > "$MACLAB_OUT/kmod-build.log" 2>&1 \
		|| { command -v clang >/dev/null && "${build[@]}" LLVM=1 >> "$MACLAB_OUT/kmod-build.log" 2>&1; }; then
		if insmod "$work/kmod/m1power.ko"; then
			loaded_here=1
			log "built and loaded m1power.ko for $release"
		else
			log "insmod failed; using macsmc-hwmon only"
		fi
	else
		log "module build failed (see kmod-build.log); using macsmc-hwmon only"
	fi
else
	log "no headers for $release; using macsmc-hwmon only (no wake timer)"
fi

python3 -I "$work/agent.py" probe --plan "$MACLAB_IN/plan.json" --out "$MACLAB_OUT/result.json"
rc=$?
log "probe exited $rc"
exit $rc
