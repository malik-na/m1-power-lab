#!/bin/bash
# Read and decode the M1 boot loader's wake breadcrumb: power-chip scratch bytes 0x9f04-0x9f0d.
#   tools/m1n1/read-breadcrumb.sh                 read on the M1 over Thunderbolt (read only)
#   tools/m1n1/read-breadcrumb.sh --hex "44 56 43 32 24 43 f2 5a 01 00"   decode given bytes
#
# Read through the kernel's nvmem device (as tools/tb/m1-pmu-dump does), so no command is put on
# the SPMI controller Linux owns, and nothing is written. Run it right after the M1 is back from a
# sleep run, before another sleep: the next sleep's records overwrite these bytes.
#
# The loader (m1n1 mb2 + breadcrumb, ~/Work/m1n1-mb2-breadcrumb, branch m1power/wake-breadcrumb)
# writes only 0x9f0b and 0x9f0c, and only on the M1's boot CPU at the reset vector (a wake; a cold
# boot enters at _start and writes nothing):
#   0x9f0b  'Z' the reset vector ran (first code, before any RAM data is read; watchdog 1 set to 30 s)
#           'M' then: the S2R mailbox was gone (magic or quiet lost), no resume possible
#           'U' then: the mailbox had no slot for the boot CPU
#           'N' then: core 0's slot had no entry; the boot CPU parked (watchdog 45 s)
#           'H' then: branching to core 0's slot entry (watchdog 75 s; the kernel's wakemark stub
#               sets 60 s, cpu_resume does not touch it)
#   0x9f0c  the AP wake sources the reset vector read (AON 0x23d00401c..2c), one bit each:
#           0 src54 NUB.SPMI0Sw3IRQ  1 src50 NUB.APWakeupTime  2 src49 NUB.APWatchdog
#           3 src40 NUB.WakeupAP     4 src76 SMC.CPUWakeupAP    5 src131-134 ATC0/1 CIO/USB
#           6 another named source (12, 14, 26, 27, 47, 64, 81)  7 any unnamed source bit
# The glue's commit record (D8 (f), 'D','V') writes all ten bytes at the commit point, so a
# breadcrumb found after a run that has 'D','V' at 0x9f04 was written after that commit. Its
# bytes 7-8 (0x9f0b/0c) are 0 when byte 6's high nibble is f; otherwise they hold a C3 value and a
# breadcrumb cannot be told from it. 0x9f0d is cleared by iBoot at every boot.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)

if [ "${1:-}" = --hex ]; then
	hex=${2:?"--hex needs ten bytes"}
	meta="given bytes"
else
	raw=$("$here/../tb/m1tb" -o BatchMode=yes 'python3 -I -' <<'EOF'
NV = "/sys/bus/nvmem/devices/spmi_nvmem0/nvmem"
with open(NV, "rb") as f:
    f.seek(0x9f04)
    b = f.read(10)
up = float(open("/proc/uptime").read().split()[0])
import time
print(" ".join("%02x" % x for x in b))
print("read on the M1 at %s, uptime %.0f s, booted %s, boot_id %s" % (
    time.strftime("%F %T"), up, time.strftime("%F %T", time.localtime(time.time() - up)),
    open("/proc/sys/kernel/random/boot_id").read().strip()))
EOF
)
	hex=$(printf '%s\n' "$raw" | sed -n 1p)
	meta=$(printf '%s\n' "$raw" | sed -n 2p)
fi

python3 -I - "$hex" "$meta" <<'EOF'
import sys
b = bytes(int(x, 16) for x in sys.argv[1].split())
if len(b) != 10:
    sys.exit("need 10 bytes, got %d" % len(b))
print("0x9f04-0x9f0d: " + " ".join("%02x" % x for x in b) + "   (" + sys.argv[2] + ")")

def ch(x):
    return chr(x) if 0x20 < x < 0x7f else "."

rec = None
if b[0] == ord("D"):
    letter = b[1] & 0x7f
    serr = " (SError pending)" if b[1] & 0x80 else ""
    names = {"V": "C3 commit record: the commit point was reached",
             "a": "armed (begin)", "w": "woke (end): the kernel's wake path finished",
             "r": "wake path top ran", "A": "armed",
             "P": "panic", "E": "die/oops", "T": "logic wait timed out", "X": "other failure",
             "t": "trace mark", "R": "entered", "F": "failing", "K": "core job done",
             "Q": "probe record", "q": "probe record, watchdog 1 armed at the commit",
             "W": "armed (compare)", "c": "compare, armed", "C": "compare", "S": "snapshot",
             "e": "leave early", "l": "leave late", "b": "back"}
    rec = chr(letter)
    print("record: 'D','%s'%s  %s" % (rec, serr, names.get(rec, "(letter not known to this reader)")))
else:
    print("record: no 'D' record at 0x9f04 (first byte %02x '%s')" % (b[0], ch(b[0])))

if rec == "V":
    codes = []
    for s in range(9):
        codes.append((b[2 + s // 2] >> (4 if s % 2 else 0)) & 0xf)
    print("  C3 slot codes 0-8: " + " ".join("%x" % c for c in codes) +
          "  (d = d*0x111, e = other value, f = not read)")
    trusted = (b[6] >> 4) == 0xf
    if not trusted:
        print("  byte 6 high nibble is %x: slot %d had another value; 0x9f0b/0c held it at the commit,"
              " so a breadcrumb there is ambiguous" % (b[6] >> 4, b[6] >> 4))
else:
    trusted = False
    if rec in ("w", "r"):
        print("  the kernel's wake path wrote this after the loader: the wake reached Linux"
              " (the loader's breadcrumb was overwritten)")
    else:
        print("  not the commit record: the breadcrumb bytes below may be stale or part of this"
              " record; judge with the run's log")

m, s = b[7], b[8]
marks = {"Z": "the boot CPU's reset vector ran (a wake reached the CPU); stopped before the"
              " later marks (reset about 30 s after it: before the mailbox check; 45 s: after it)",
         "M": "reset vector ran; the S2R mailbox was gone (magic or quiet lost, RAM not as left)",
         "U": "reset vector ran; the mailbox had no slot for the boot CPU's MPIDR",
         "N": "reset vector ran; core 0's slot had no entry: the boot CPU parked",
         "H": "reset vector ran and the loader branched to core 0's slot entry (reset about 75 s"
              " after the wake: the kernel stub never ran; 60 s: the wakemark stub ran)"}
print("0x9f0b-0c: %02x %02x" % (m, s))
if chr(m) in marks:
    print("breadcrumb: '%s'  %s" % (chr(m), marks[chr(m)]))
    srcs = ["src54 NUB.SPMI0Sw3IRQ", "src50 NUB.APWakeupTime", "src49 NUB.APWatchdog",
            "src40 NUB.WakeupAP", "src76 SMC.CPUWakeupAP", "src131-134 ATC0/1 CIO/USB",
            "other named (12,14,26,27,47,64,81)", "an unnamed source"]
    on = [srcs[i] for i in range(8) if s & (1 << i)]
    print("wake sources at the reset vector: " + (", ".join(on) if on else "none set"))
    if not trusted:
        print("caution: not after a clean 'D','V' commit record; may be stale or coincidental")
elif m == 0 and s == 0 and rec == "V" and trusted:
    print("breadcrumb: none. After this commit record no code of the loader's reset vector wrote"
          " (no wake reached the boot CPU, the image in RAM was lost, or the SPMI write failed)."
          " Reset time about commit + watchdog: never woke; about wake + 30 s: the vector ran and SPMI failed.")
else:
    print("breadcrumb: none recognised")
EOF
