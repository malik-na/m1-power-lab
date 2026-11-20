#!/bin/bash
# Milestone 3 (2026-11-20): onerun.sh with a step before the sleep: read the SEP's domain word
# 0x23b700c00 and PMGR 0x23b74c200; with mode "msg" first send the SEP its sleep request through
# the probe kernel's apple_sep trigger and poll the word until bits 4-7 read 0 (10 s). A message
# that is not answered or a word that does not gate: no sleep is started (exit 2).
# Usage: M1_CLAIM=<who> tools/tb/probe-run/m3run.sh <kernel.tar.zst> <tag> <cmdline> <out-prefix> <read|msg> [cand mask]
S=$(cd "$(dirname "$0")" && pwd); cd /home/naeem/Projects/m1-power-lab
pkg=$1 tag=$2 cl=$3 out=$4 mode=$5 mask=${6:-0xffffe}
[ "$mode" = msg ] && TRIG=${SEP_TRIGGER:?set SEP_TRIGGER to the probe_sleep path on the M1}
krel=$(zstd -dc "$pkg" | tar -t | sed -n 's|^usr/lib/modules/\([^/]*\)/vmlinuz$|\1|p' | head -1)
echo "$(date +%T) bootonce $tag ($krel) mode=$mode"
M1_CLAIM=${M1_CLAIM:?export M1_CLAIM=<who> after m1-claim take} timeout 400 tools/tb/m1-bootonce "$pkg" "$tag" "$cl" > $out-bootonce.log 2>&1 || { echo "bootonce failed"; exit 1; }
t0=$(date +%s)
while [ $(( $(date +%s) - t0 )) -lt 300 ]; do
  r=$(timeout 8 tools/tb/m1tb "uname -r; cat /proc/uptime" 2>/dev/null) && case "$r" in *$krel*) up=$(echo "$r" | sed -n 2p | cut -d. -f1); [ "${up:-0}" -ge 40 ] && break;; esac
  sleep 4
done
case "$r" in *$krel*) ;; *) echo "test kernel not up: $r"; exit 1;; esac
rd='python3 -c "import mmap,os,struct,sys
fd=os.open(\"/dev/mem\",os.O_RDONLY|os.O_SYNC)
for a in (0x23b700c00,0x23b74c200):
  pg=a&~0x3fff; m=mmap.mmap(fd,0x4000,mmap.MAP_SHARED,mmap.PROT_READ,offset=pg); print(\"%#x=%#010x\"%(a,struct.unpack_from(\"<I\",m,a-pg)[0]),end=\" \"); m.close()
print()"'
{
echo "pre $(date +%T): $(timeout 15 tools/tb/m1tb "$rd")"
timeout 15 tools/tb/m1tb 'lsmod | grep -E "^apple_sep"; dmesg | grep -E "apple_sep.*(ready in|retrying)" | tail -3'
} | tee $out-pre.txt
if [ "$mode" = msg ] || [ "$mode" = rmmod ]; then
  # Safety check 2026-11-20: the trigger and polls run before begin arms watchdog 1. Hold
  # /dev/watchdog0 open (apple_wdt, 120 s, never pinged) so a hang here ends by itself; start.sh's
  # unbind stops it (apple_wdt stops on unregister) just before real.sh, as in milestone 2.
  timeout 20 tools/tb/m1tb "systemd-run --unit=m3wd\$(date +%H%M%S) python3 -c \"import fcntl,os,struct,time; f=os.open('/dev/watchdog0',os.O_WRONLY); fcntl.ioctl(f,0xc0045706,struct.pack('i',120)); os.write(f,b'1'); time.sleep(100000)\"; sleep 2; python3 -c \"import mmap,os,struct; fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC); m=mmap.mmap(fd,0x4000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0x23d2b0000); print('wd1 bite %#x control %d' % (struct.unpack_from('<I',m,0x14)[0], struct.unpack_from('<I',m,0x1c)[0]))\"" | tee -a $out-pre.txt
  grep -q 'wd1 bite 0xaba95000 control 4' $out-pre.txt || { echo "watchdog not armed: no trigger" | tee -a $out-pre.txt; exit 2; }
  if [ "$mode" = msg ]; then
  timeout 120 tools/tb/m1tb "for i in 1 2 3; do echo 1 > $TRIG && { echo trigger ok try \$i; break; }; echo trigger failed try \$i; sleep 5; done; dmesg | grep 'probe_sleep:' | tail -12" | tee -a $out-pre.txt
  grep -q 'probe_sleep: reply' $out-pre.txt || { echo "no SEP reply: no sleep started" | tee -a $out-pre.txt; exit 2; }
  else
  # The old driver's 13.5 recipe (var/run22-src/run22.sh 20-26): unload the enclave's driver; an
  # enclave without traffic gates itself 1.4-3 s later.
  timeout 60 tools/tb/m1tb "rmmod apple_sep; echo rmmod rc=\$? \$(date +%T.%N | cut -c1-12); lsmod | grep -c '^apple_sep' ; dmesg | grep apple_sep | tail -5" | tee -a $out-pre.txt
  fi
  gated=
  for i in $(seq 1 30); do
    l=$(timeout 15 tools/tb/m1tb "$rd"); echo "poll $(date +%T.%N | cut -c1-12): $l" | tee -a $out-pre.txt
    w=$(echo "$l" | sed -n 's/.*0x23b700c00=\(0x[0-9a-f]*\).*/\1/p')
    [ -n "$w" ] && [ $(( (w >> 4) & 0xf )) -eq 0 ] && { gated=1; break; }
    sleep 0.5
  done
  [ -n "$gated" ] || { echo "SEP did not read gated: no sleep started" | tee -a $out-pre.txt; exit 2; }
fi
$S/start.sh $mask | tee $out-start.txt
grep -q started $out-start.txt || exit 1
$S/waitread.sh $krel | tee $out-after.txt
