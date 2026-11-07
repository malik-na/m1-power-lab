#!/bin/bash
# Control for the S2R DRAM retention probe: does a page survive a plain WD1 reset (no sleep)?
# Kernel cmdline must keep Linux below 0x980000000 (mem=5G) so /dev/mem may write there.
# Writes the same 512-word pattern the apple-s2r driver writes at .prepare, sets the PMU
# note so the ESP stage-2 m1n1 checks it on the next cold boot ('R'/'r'/'X' at 0x9f0b),
# then resets the SoC through AON WD1 exactly as the S2R dead-man does.
set -u
: "${MACLAB_OUT:?}"
exec > "$MACLAB_OUT/log.txt" 2>&1
result() { printf '%s\n' "$*" > "$MACLAB_OUT/result.txt"; }
grep -qw mem=5G /proc/cmdline || { result "VERDICT SKIP needs mem=5G"; exit 0; }
N=$(ls -d /sys/bus/nvmem/devices/spmi_nvmem* | head -1)
python3 - <<'PY'
import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x980000000)
pat = lambda i: (0x6d31707772657421 ^ ((i * 0x9e3779b97f4a7c15) & (2**64 - 1))) & (2**64 - 1)
for i in range(512):
    m[8*i:8*i+8] = struct.pack("<Q", pat(i))
ok = sum(struct.unpack("<Q", m[8*i:8*i+8])[0] == pat(i) for i in range(512))
print(f"pattern written, read back {ok}/512")
m.flush(); m.close(); os.close(fd)
PY
# 'L' note (keep the RTC bytes as they are) and clear the m1n1 mark so the cold boot checks
printf 'L' | dd of="$N/nvmem" bs=1 seek=$((0x9f04)) conv=notrunc 2>/dev/null
printf '\0' | dd of="$N/nvmem" bs=1 seek=$((0x9f0b)) conv=notrunc 2>/dev/null
echo "pmu 9f04: $(dd if=$N/nvmem bs=1 skip=$((0x9f04)) count=1 2>/dev/null | od -An -c)  9f0b: $(dd if=$N/nvmem bs=1 skip=$((0x9f0b)) count=1 2>/dev/null | od -An -tx1)"
result "VERDICT RESET-REQUESTED: WD1 reset with the retention pattern in place; read 0x9f0b on the next boot"
sync; sleep 1
python3 - <<'PY'
import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
w = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x23d2b0000)
def wr(off, v): w[off:off+4] = struct.pack("<I", v)
wr(0x1c, 0); wr(0x10, 0); wr(0x14, 0x100000); wr(0x1c, 4)
import time; time.sleep(5)
print("still here after WD1 reset request")
PY
