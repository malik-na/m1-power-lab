#!/bin/bash
# Runs ON THE M1 as root (read-only): prints a tar stream of everything Linux can say about
# the hardware, one text file per subsystem, for tools/regmap/hwdb.py to load.
#   tools/tb/m1tb 'bash -s' < tools/regmap/collect-inventory.sh > inv.tar
# Reads sysfs, procfs, debugfs (m1power's SMC keys and PMGR domains if the module is loaded)
# and a few tool outputs. Writes nothing outside a temporary directory.
set -u
T=$(mktemp -d)
cd "$T" || exit 1
kv() { # kv DIR: "attribute=value" for every readable regular file directly in DIR
	for f in "$1"/*; do
		[ -f "$f" ] && [ -r "$f" ] || continue
		case "$(basename "$f")" in uevent|modalias|descriptors|config|rom|resource*|remove|rescan|new_id|remove_id|bind|unbind|nvmem|edid) continue ;; esac
		v=$(timeout 1 head -c 300 "$f" 2>/dev/null | tr '\n\0' '  ') || continue
		printf '%s=%s\n' "$(basename "$f")" "$v"
	done
}
section() { printf '\n### %s\n' "$1"; }

{ uname -a; cat /proc/cmdline; cat /sys/firmware/devicetree/base/model 2>/dev/null | tr '\0' '\n'
  cat /sys/firmware/devicetree/base/compatible 2>/dev/null | tr '\0' ' '; echo
  date -Is; cat /proc/sys/kernel/random/boot_id; } > identity.txt

for d in /sys/bus/platform/devices/*; do
	of=$(readlink -f "$d/of_node" 2>/dev/null | sed 's#^/sys/firmware/devicetree/base##')
	drv=$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)
	pm=$(cat "$d/power/runtime_status" 2>/dev/null)
	printf '%s\t%s\t%s\t%s\n' "$(basename "$d")" "${of:--}" "${drv:--}" "${pm:--}"
done > platform.tsv

for d in /sys/bus/usb/devices/*; do
	section "$(basename "$d")"; kv "$d"
done > usb.txt
lsusb -t > lsusb-t.txt 2>&1 || true

for d in /sys/class/typec/* /sys/class/typec/*/identity /sys/class/usb_power_delivery/* /sys/class/usb_role/*; do
	[ -d "$d" ] || continue; section "${d#/sys/class/}"; kv "$d"
done > typec.txt

for d in /sys/class/power_supply/*; do section "$(basename "$d")"; kv "$d"; done > power_supply.txt

for d in /sys/class/backlight/* /sys/class/leds/*; do
	[ -d "$d" ] || continue; section "${d#/sys/class/}"; kv "$d"
done > backlight_leds.txt

for d in /sys/class/input/input*; do
	section "$(basename "$d")"; kv "$d"; echo "device=$(readlink -f "$d/device")"
	for c in "$d"/capabilities/*; do printf 'cap.%s=%s\n' "$(basename "$c")" "$(cat "$c")"; done
done > input.txt

for d in /sys/class/drm/*; do section "$(basename "$d")"; kv "$d"; done > drm.txt
for d in /sys/class/drm/card*-*; do [ -r "$d/edid" ] && { echo "### $(basename "$d")"; od -An -tx1 "$d/edid"; }; done > edid.txt 2>/dev/null

cat /proc/asound/cards > sound-cards.txt 2>&1
for d in /sys/class/sound/*; do section "$(basename "$d")"; kv "$d"; done > sound.txt

for d in /sys/class/hwmon/*; do
	section "$(basename "$d") $(cat "$d/name" 2>/dev/null)"; kv "$d"
done > hwmon.txt
for d in /sys/class/thermal/*; do section "$(basename "$d")"; kv "$d"; done > thermal.txt

for d in /sys/devices/system/cpu/cpu[0-9]*; do
	section "$(basename "$d")"; kv "$d"; kv "$d/cpufreq" 2>/dev/null | sed 's/^/cpufreq./'
	for s in "$d"/cpuidle/state*; do [ -d "$s" ] && kv "$s" | sed "s/^/$(basename "$s")./"; done
	kv "$d/topology" | sed 's/^/topology./'
done > cpu.txt
cat /proc/cpuinfo > cpuinfo.txt

for d in /sys/bus/pci/devices/*; do section "$(basename "$d")"; kv "$d"; echo "driver=$(basename "$(readlink "$d/driver" 2>/dev/null)")"; done > pci.txt
lspci -nnk > lspci.txt 2>&1 || true

for bus in i2c spi spmi serio mdio_bus nvmem rtc watchdog iommu mmc block net bluetooth ieee80211 remoteproc mailbox misc dma_heap; do
	for d in /sys/bus/$bus/devices/* /sys/class/$bus/*; do
		[ -e "$d" ] || continue
		section "$bus/$(basename "$d")"; kv "$d"
		echo "driver=$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)"
		echo "of_node=$(readlink -f "$d/of_node" 2>/dev/null | sed 's#^/sys/firmware/devicetree/base##')"
	done
done > buses.txt 2>/dev/null

for d in /sys/kernel/iommu_groups/*; do printf '%s\t%s\n' "$(basename "$d")" "$(ls "$d/devices" | tr '\n' ' ')"; done > iommu_groups.tsv
cat /proc/interrupts > interrupts.txt
cat /proc/iomem > iomem.txt
lsmod > lsmod.txt
for m in /sys/module/*/parameters; do for p in "$m"/*; do [ -r "$p" ] && printf '%s.%s=%s\n' "$(basename "$(dirname "$m")")" "$(basename "$p")" "$(head -c 200 "$p" 2>/dev/null | tr '\n' ' ')"; done; done > module_params.txt 2>/dev/null
dmesg > dmesg.txt 2>&1
for d in /sys/class/regulator/* /sys/class/devlink/*; do [ -d "$d" ] && { section "${d#/sys/class/}"; kv "$d"; }; done > regulator_devlink.txt 2>/dev/null
ls -la /sys/kernel/debug/clk 2>/dev/null | head -0; cat /sys/kernel/debug/clk/clk_summary > clk_summary.txt 2>/dev/null
cat /sys/kernel/debug/pm_genpd/pm_genpd_summary > genpd_summary.txt 2>/dev/null
cat /sys/kernel/debug/gpio > gpio.txt 2>/dev/null
cat /sys/kernel/debug/pinctrl/*/pins > pinctrl.txt 2>/dev/null
cat /sys/kernel/debug/wakeup_sources > wakeup_sources.txt 2>/dev/null
cat /sys/kernel/debug/devices_deferred > devices_deferred.txt 2>/dev/null
if [ -d /sys/kernel/debug/m1power ]; then
	cat /sys/kernel/debug/m1power/smc_keys > smc_keys.txt 2>/dev/null
	cat /sys/kernel/debug/m1power/pmgr_ps > pmgr_ps.txt 2>/dev/null
	cat /sys/kernel/debug/m1power/wdt_regs > wdt_regs.txt 2>/dev/null
fi
iw dev > iw.txt 2>&1; iw phy >> iw.txt 2>&1
btmgmt info > bt.txt 2>&1 || true
cat /sys/class/dmi/id/* > dmi.txt 2>/dev/null
tar -cf - .
cd / && rm -rf "$T"
