# Shared by the m1power maclab job scripts (sourced from $MACLAB_IN/lib.sh).
#
# load_m1power WORKDIR
#   Loads m1power.ko for the running kernel, building it from the payload's
#   m1power.c against, in order: the installed headers, or a module-build
#   archive from the lab build ($MACLAB_IN/module-build.tar.zst, checked
#   against the running release). Sets M1POWER_MODULE to one of
#   already | built | none, and M1POWER_LOADED_HERE to 1 when it insmodded.

log() { printf '[%s] %s\n' "${MACLAB_TEST:-m1power}" "$*"; }

M1POWER_MODULE=none
M1POWER_LOADED_HERE=0

_m1power_build() { # KDIR LOG
	local kdir=$1 out=$2
	mkdir -p "$work/kmod"
	cp "$MACLAB_IN/m1power.c" "$MACLAB_IN/Makefile" "$work/kmod/"
	# Kernels built with clang want LLVM=1; gcc usually works against them
	# too (with warnings), so try it first and fall back to clang if present.
	make -C "$work/kmod" KDIR="$kdir" > "$out" 2>&1 && return 0
	command -v clang >/dev/null && make -C "$work/kmod" KDIR="$kdir" LLVM=1 >> "$out" 2>&1
}

load_m1power() {
	work=$1
	local release kdir=""
	release=$(uname -r)
	if [ -d /sys/kernel/debug/m1power ]; then
		M1POWER_MODULE=already
		log "m1power module already loaded"
		return 0
	fi
	if [ -e "/lib/modules/$release/build/Makefile" ]; then
		kdir="/lib/modules/$release/build"
	elif [ -f "$MACLAB_IN/module-build.tar.zst" ]; then
		mkdir -p "$work/module-build"
		if tar --zstd -xf "$MACLAB_IN/module-build.tar.zst" -C "$work/module-build"; then
			if grep -q "\"release\": \"$release\"" "$work/module-build/IDENTITY.json"; then
				kdir="$work/module-build/build"
			else
				log "module-build is for another release than $release; not using it"
			fi
		fi
	fi
	if [ -z "$kdir" ]; then
		log "no headers or module-build for $release: macsmc-hwmon only, no wake timer"
		return 0
	fi
	if _m1power_build "$kdir" "$MACLAB_OUT/kmod-build.log" && insmod "$work/kmod/m1power.ko"; then
		M1POWER_MODULE=built
		M1POWER_LOADED_HERE=1
		log "built and loaded m1power.ko for $release"
	else
		log "could not build or load m1power.ko (see kmod-build.log): macsmc-hwmon only"
	fi
}

unload_m1power() {
	if [ "$M1POWER_LOADED_HERE" = 1 ]; then
		echo 0 > /sys/kernel/debug/m1power/waketimer 2>/dev/null || true
		rmmod m1power 2>/dev/null || true
	fi
}

wait_uptime() { # SECONDS
	local up
	up=$(cut -d. -f1 /proc/uptime)
	[ "$up" -lt "$1" ] && sleep $(($1 - up))
	return 0
}
