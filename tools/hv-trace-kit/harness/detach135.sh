#!/bin/bash
# After go135.sh and drive135.sh (real sleep armed, guest running on a build from ~/m1n1-next):
# detach the hypervisor from this host. Puts two lines for the hypervisor shell into the FIFO,
# interrupts the guest once; the shell runs detach() (harness/detach.py, read it first), which
# lets the guest run on with no host and ends run_guest.py itself (go135.sh then cleans up).
# When this prints "detached" the cable can come out. Afterwards: harness/detach_readout.py.
#   ARGS  python arguments for detach(), e.g. ARGS='mb=96' or ARGS='skip="0x23bc34000+0x4000"'
# Not run by its author (no hardware access): written after drive135.sh.
S=$(cd "$(dirname "$0")" && pwd); T=${1:?tag}
R=/home/naeem/Projects/m1-power-lab/tools/hv-trace-kit/runs/20261116-mac135; O=$R/run-$T.out; HVIN=$S/hvin
[ -p "$HVIN" ] || { echo "no $HVIN: go135.sh is not running"; exit 1; }
P=$(ps -eo pid,args | awk '$2 ~ /python$/ && /run_guest/ {print $1}')
[ -n "$P" ] || { echo "run_guest.py is not running"; exit 1; }
n=$(wc -l < $O)
# The lines wait in the FIFO (run_guest.py holds its read end); the shell the interrupt opens
# reads them. If detach() fails nothing is armed: the guest is still attached, and either runs
# on (the FIFO has no writer left: end of input) or stays paused in the shell (macos-up.sh keeps
# a writer open; its pid is in hvin.holder).
# PRE: hypervisor-shell lines run before detach() (e.g. harness/awake_snap.py), newline-terminated.
printf '%bhv.run_script("%s/detach.py")\ndetach(%s)\n' "${PRE:-}" "$S" "${ARGS:-}" > "$HVIN"
kill -INT $P
timeout 180 bash -c "until tail -n +$n $O | grep -a -q -E 'DETACHED|ARMED|Traceback|Error'; do sleep 0.5; done"
sleep 1
tail -n +$n $O | grep -a -E '^\[detach\]|^\[touch\]|Error|Traceback' | tail -30
if tail -n +$n $O | grep -a -q 'DETACHED'; then echo "detached $(date +%T): the cable can come out"
else
	echo "NOT detached $(date +%T): read $O. Still attached."
	[ -f "$S/hvin.holder" ] && echo "the guest is paused in the hypervisor shell; 'kill \$(cat $S/hvin.holder)' ends the shell's input and lets it run on"
	exit 1
fi
