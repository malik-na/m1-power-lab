#!/usr/bin/env bash
# Host-side helper for the M1 (t8103) macOS sleep-entry trace. Run on the Linux host.
#
#   ./session.sh check                 host prerequisites (no device needed)
#   ./session.sh devices               list ttyACM nodes and which ones are the m1n1 proxy (sysfs, read-only)
#   ./session.sh wait                  wait for the m1n1 proxy to enumerate
#   ./session.sh console               XNU/vuart console reader (2nd terminal), logged to $RUN/vuart.log
#   ./session.sh ping                  NOP + chip id over the proxy (read-only)
#   ./session.sh postmortem TAG        read-only PMU/AON post-mortem (run BEFORE `guest`)
#   ./session.sh guest                 boot macOS under the hypervisor with the tracer
#   ./session.sh reboot                reboot the M1 from proxy mode (no PMU writes)
#   ./session.sh clear-counters [--yes] print, then (with --yes) clear the PMU boot-error/panic
#                                      counters: ONE SPMI write, the same as upstream run_guest.py.
#                                      Run it last, after every postmortem file is saved.
#   ./session.sh summarize             write $RUN/summary.txt from the trace
#
# Environment (defaults in brackets):
#   M1N1   m1n1 checkout, same commit as the m1n1.bin installed on the Mac [~/m1n1]
#   KC     kernelcache Mach-O from kc_extract.py [$KIT/kc/kernelcache-13.5.macho]
#   RUN    run directory [$KIT/runs/<date>]
#   PY     python with pyserial+construct+asn1 [$KIT/venv/bin/python]
#   BOOTARGS  guest boot-args [docs/sw/m1n1-hypervisor.md set]
#   M1N1DEVICE / M1N1SEC  proxy / console tty [auto: the 1209:316d interface 00 / 02, else /dev/ttyACM0 / 1]
#   S2R_*  tracer options, see hv_s2r_trace.py CFG
#
# Device access: the lab's recorded path is /dev/ttyACM0 + /dev/ttyACM1, root:uucp 0660
# (docs/LAB-INVENTORY.md:61-74, docs/PROXY-HARNESS.md:46-49). Without the optional udev
# rule, run every device command as:  sudo -E -u "$USER" -g uucp ./session.sh <cmd>
# (-E keeps S2R_*, BOOTARGS and M1N1* settings; sudo drops them otherwise)
set -euo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
M1N1="${M1N1:-$HOME/m1n1}"
KC="${KC:-$KIT/kc/kernelcache-13.5.macho}"
RUN="${RUN:-$KIT/runs/$(date +%Y%m%d)}"
PY="${PY:-$KIT/venv/bin/python}"
BOOTARGS="${BOOTARGS:-debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0}"
PIN=70757dc74c2dac485188acaa2fa7e73be5b108ee
mkdir -p "$RUN"

die() { echo "error: $*" >&2; exit 1; }

# m1n1 proxy tty for USB interface $1 (00 = proxy, 02 = secondary/console), from sysfs only.
m1n1_tty() {
    local t d u
    for t in /sys/class/tty/ttyACM*; do
        [ -e "$t/device" ] || continue
        d=$(readlink -f "$t/device"); u=$(dirname "$d")
        [ "$(cat "$d/bInterfaceNumber" 2>/dev/null)" = "$1" ] || continue
        [ "$(cat "$u/idVendor" 2>/dev/null)" = "1209" ] || continue
        [ "$(cat "$u/idProduct" 2>/dev/null)" = "316d" ] || continue
        echo "/dev/$(basename "$t")"; return 0
    done
    return 1
}
resolve() {
    if [ -z "${M1N1DEVICE:-}" ]; then M1N1DEVICE=$(m1n1_tty 00 || echo /dev/ttyACM0); fi
    SEC="${M1N1SEC:-$(m1n1_tty 02 || echo /dev/ttyACM1)}"
    export M1N1DEVICE
}
need_access() {
    resolve
    [ -e "$M1N1DEVICE" ] || die "$M1N1DEVICE not present (is the Mac in m1n1 proxy mode and cabled?)"
    [ -r "$M1N1DEVICE" ] && [ -w "$M1N1DEVICE" ] || die "no rw access to $M1N1DEVICE ($(stat -c '%U:%G %a' "$M1N1DEVICE")). Run: sudo -E -u \"$USER\" -g uucp $0 ${CMD}"
}
CMD="${1:-}"

case "${1:-}" in
check)
    ok=1
    [ -d "$M1N1/proxyclient" ] || { echo "MISSING m1n1 checkout at $M1N1"; ok=0; }
    if [ -d "$M1N1/.git" ]; then
        head=$(git -C "$M1N1" rev-parse HEAD)
        [ "$head" = "$PIN" ] && echo "m1n1 at verified commit $PIN" \
            || echo "WARN m1n1 at $head; the kit was checked against $PIN (ABI must match the m1n1.bin on the Mac)"
    fi
    [ -x "$PY" ] || { echo "MISSING $PY (python3 -m venv $KIT/venv && $KIT/venv/bin/pip install -r $M1N1/requirements.txt)"; ok=0; }
    [ -x "$PY" ] && "$PY" -c 'import serial, construct, asn1; print("python deps ok")' || ok=0
    modinfo cdc_acm >/dev/null 2>&1 && echo "cdc_acm module available" || { echo "MISSING cdc_acm kernel module"; ok=0; }
    [ -e /etc/udev/rules.d/70-m1n1.rules ] && echo "optional udev rule installed (/dev/m1n1, /dev/m1n1-sec)" \
        || echo "no udev rule (fine): device commands need  sudo -E -u \"$USER\" -g uucp $0 <cmd>"
    getent group uucp >/dev/null && echo "group uucp exists" || echo "WARN no uucp group; check the ttyACM group with ./session.sh devices"
    [ -f "$KC" ] && "$PY" - "$KC" <<'PYEOF' || { echo "MISSING/BAD kernelcache $KC"; ok=0; }
import sys
b = open(sys.argv[1], "rb").read(16)
assert int.from_bytes(b[:4], "little") == 0xfeedfacf, "not a Mach-O"
print("kernelcache Mach-O ok, filetype", hex(int.from_bytes(b[12:16], "little")))
PYEOF
    python3 -I "$KIT/s2r_decode.py" selftest
    python3 -I "$KIT/kc_extract.py" --selftest
    ls -l /dev/m1n1 /dev/m1n1-sec /dev/ttyACM* 2>/dev/null || echo "no proxy device connected (fine for now)"
    [ $ok = 1 ] && echo "CHECK OK" || die "fix the items above"
    ;;
devices)
    for t in /sys/class/tty/ttyACM*; do
        [ -e "$t/device" ] || { echo "no ttyACM devices"; break; }
        d=$(readlink -f "$t/device"); u=$(dirname "$d")
        echo "/dev/$(basename "$t")  usb $(basename "$u")  $(cat "$u/idVendor" 2>/dev/null):$(cat "$u/idProduct" 2>/dev/null)  if$(cat "$d/bInterfaceNumber" 2>/dev/null)  $(stat -c '%U:%G %a' "/dev/$(basename "$t")")"
    done
    echo "m1n1 proxy: $(m1n1_tty 00 || echo none)   console: $(m1n1_tty 02 || echo none)"
    ;;
wait)
    echo "waiting for the m1n1 proxy (USB 1209:316d) ..."
    if [ -n "${M1N1DEVICE:-}" ]; then
        while [ ! -e "$M1N1DEVICE" ]; do sleep 0.5; done
    else
        until m1n1_tty 00 >/dev/null; do sleep 0.5; done
    fi
    resolve
    echo "present: $(ls -l "$M1N1DEVICE")   console: $SEC"
    [ -r "$M1N1DEVICE" ] && [ -w "$M1N1DEVICE" ] || echo "NOTE: no rw access; use  sudo -E -u \"$USER\" -g uucp $0 <cmd>"
    ;;
console)
    sec="${M1N1SEC:-auto}"
    echo "XNU console on ${sec} (auto = USB 1209:316d interface 02) -> $RUN/vuart.log (Ctrl-C to quit; reconnects)"
    "$PY" - "$sec" "$RUN/vuart.log" <<'PYEOF'
import os, sys, time, serial
dev, path = sys.argv[1], sys.argv[2]

def find():
    if dev != "auto":
        return dev
    base = "/sys/class/tty"
    for t in sorted(os.listdir(base)):
        if not t.startswith("ttyACM"):
            continue
        try:
            d = os.path.realpath(f"{base}/{t}/device"); u = os.path.dirname(d)
            rd = lambda f: open(f).read().strip()
            if (rd(f"{d}/bInterfaceNumber"), rd(f"{u}/idVendor"), rd(f"{u}/idProduct")) == ("02", "1209", "316d"):
                return f"/dev/{t}"
        except OSError:
            pass
    return None

with open(path, "ab", buffering=0) as log:
    while True:
        try:
            d = find()
            if d is None:
                time.sleep(0.5)
                continue
            with serial.Serial(d, 500000, timeout=0.2) as s:
                print(f"[console] opened {d}", flush=True)
                while True:
                    data = s.read(4096)
                    if data:
                        log.write(data); sys.stdout.buffer.write(data); sys.stdout.flush()
        except (serial.SerialException, OSError):
            time.sleep(0.5)
        except KeyboardInterrupt:
            break
PYEOF
    ;;
ping)
    need_access
    "$PY" - "$M1N1" <<'PYEOF'
import sys; sys.path.insert(0, sys.argv[1] + "/proxyclient")
from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import bootstrap_port
iface = UartInterface(); p = M1N1Proxy(iface, debug=False); bootstrap_port(iface, p)
p.nop(); print(f"proxy OK, chip id {p.get_chipid():#x}, base {p.get_base():#x}")
PYEOF
    ;;
postmortem)
    need_access
    tag="${2:-pm}"
    "$PY" "$KIT/pmu_postmortem.py" --m1n1 "$M1N1" --tag "$tag" --out "$RUN"
    ;;
guest)
    need_access
    [ -f "$KC" ] || die "kernelcache $KC not found"
    export S2R_LOG="${S2R_LOG:-$RUN/s2r-trace-$(date +%H%M%S).jsonl}"
    echo "trace -> $S2R_LOG ; hv log -> $RUN/hv.log ; boot-args: $BOOTARGS"
    cd "$RUN"
    "$PY" "$M1N1/proxyclient/tools/run_guest.py" -l "$RUN/hv-$(date +%H%M%S).log" \
        -m "$KIT/hv_s2r_trace.py" "$KC" -- "$BOOTARGS"
    ;;
reboot)
    need_access
    "$PY" - "$M1N1" <<'PYEOF'
import sys; sys.path.insert(0, sys.argv[1] + "/proxyclient")
from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import bootstrap_port
iface = UartInterface(); p = M1N1Proxy(iface, debug=False); bootstrap_port(iface, p)
print("rebooting the M1"); p.reboot()
PYEOF
    ;;
clear-counters)
    need_access
    ls "$RUN"/postmortem-*.txt >/dev/null 2>&1 || die "no postmortem-*.txt in $RUN yet; save the post-mortem first"
    "$PY" "$KIT/pmu_clear_counters.py" --m1n1 "$M1N1" --out "$RUN" ${2:+"$2"}
    ;;
summarize)
    last=$(ls -t "$RUN"/s2r-trace-*.jsonl 2>/dev/null | head -1)
    [ -n "$last" ] || die "no trace in $RUN"
    python3 -I "$KIT/s2r_decode.py" summarize "$last" | tee "$RUN/summary-$(basename "$last" .jsonl).txt"
    ;;
*)
    sed -n '2,30p' "$0"; exit 2 ;;
esac
