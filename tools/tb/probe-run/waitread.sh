#!/bin/bash
# wait for the M1 to answer on a kernel other than the test one; read the record, 0x0201, shadow, boot time
cd /home/naeem/Projects/m1-power-lab
t0=$(date +%s); testk=${1:-m1leads}
while [ $(( $(date +%s) - t0 )) -lt 420 ]; do
  r=$(timeout 8 tools/tb/m1tb 'uname -r' 2>/dev/null) && case "$r" in *$testk*) ;; *) break;; esac
  sleep 3
done
echo "answered $(date +%T) after $(( $(date +%s) - t0 ))s kernel=$r"
timeout 20 tools/tb/m1tb 'uptime -s; f=$(ls /sys/bus/nvmem/devices/spmi_nvmem*/nvmem|head -1); python3 -c "import os,sys;f=os.open(sys.argv[1],os.O_RDONLY);g=lambda a,n:(os.lseek(f,a,0),os.read(f,n).hex(\" \"))[1];print(g(0x9f04,10),\"|0201\",g(0x201,1),\"|shadow\",g(0xa47b,3),\"|d000\",g(0xd000,1))" $f'
