#!/bin/bash
# Wake-mode-1 watcher: wait for the USB drop and the return, then read the stage marker and the note
# (crumb.py) and show whether the device that came back is the live hypervisor image (its base is
# the chainloaded one, not a fresh boot). Leaves the M1 in that state for interactive work.
S=$(cd "$(dirname "$0")" && pwd); source $S/m1dev.sh; T=${1:?tag}
R=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit
until ! m1dev >/dev/null; do sleep 0.3; done; echo "USB down $(date +%T.%N | cut -c1-12)"
until D=$(m1dev); do sleep 0.3; done; echo "USB back $(date +%T.%N | cut -c1-12) as $D"; sleep 3
M1N1DEVICE=$D timeout 60 $R/venv/bin/python -I $S/crumb.py 2>&1 | grep -v "RuntimeWarning\|^TTY>"
M1N1DEVICE=$D timeout 60 $R/venv/bin/python -I -c "
import sys; sys.path.insert(0, '/home/naeem/m1n1/proxyclient')
from m1n1.setup import *
print('clkgen now:', ' '.join('%#x' % p.read32(r) for r in (0x23b040140, 0x23b040144, 0x23b040148, 0x23b04014c, 0x23b040154)))
print('PS ATC0_USB %#x AON %#x COMMON %#x UART0 %#x' % (p.read32(0x23d280098), p.read32(0x23d280088), p.read32(0x23b700420), p.read32(0x23b700270)))
print('WD1 ctl %#x WD2 ctl %#x s2r-timer %#x' % (p.read32(0x23d2b001c), p.read32(0x23d2b002c), p.read32(0x23d2c4000)))
import time
for k in range(2):
    c = u.mrs((3, 3, 14, 0, 1)); print('CNTPCT %#x = %.3f s at host %.3f' % (c, c / 24e6, time.time())); time.sleep(10)
print('base', hex(p.get_base()))
" 2>&1 | grep -v "RuntimeWarning\|^TTY>"
