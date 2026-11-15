#!/bin/bash
# Crash-tolerant read-only register scan of the M1, run on the M3 Max.
#   tools/regmap/scan.sh LIST LABEL [SNAPSHOT_STATE]
# LIST: lines "<hex address> <4|8> [# label]". Reads go through mrd-stream on the M1 (one
# access per word, device memory), streamed over ssh: each "reading <addr>" line reaches the
# M3 Max before the read is made. If the M1 goes down mid-list, the last address it announced
# is recorded as a fault, the scan waits for the M1 to come back, skips that address and goes
# on. Results: var/regmap/scan-<LABEL>/ (raw streams, faults.txt, reads.txt) and the database
# var/hwdb/m1-hw.db (one snapshot for the scan, reg_read rows, read_fault rows).
# Transport: M1TB_VIA=m1ts (default: Wi-Fi/Tailscale, so an M1 crash cannot disturb the M3
# Max's USB-C link) or m1tb (the cable).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
LIST=$1 LABEL=$2 STATE=${3:-"awake, $(date +%F)"}
VIA=${M1TB_VIA:-m1ts}
DELAY=${DELAY_US:-150000}
out="$repo/var/regmap/scan-$LABEL"; mkdir -p "$out"
DB="$repo/var/hwdb/m1-hw.db"
m1() { if [ "$VIA" = m1tb ]; then "$here/../tb/m1tb" -o BatchMode=yes -o ConnectTimeout=5 "$@"; else ssh -o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=2 -o ServerAliveCountMax=3 m1ts "$@"; fi; }
say() { printf '%s %s\n' "$(date +%T)" "$*" | tee -a "$out/scan.log"; }

grep -E '^\s*0x[0-9a-fA-F]+\s+[48]' "$LIST" > "$out/todo.txt"
: > "$out/reads.txt"; touch "$out/faults.txt"
kernel=$(m1 'uname -r') || { say "M1 not reachable"; exit 2; }
boot=$(m1 'cat /proc/sys/kernel/random/boot_id')
sid=$(sqlite3 "$DB" "INSERT INTO snapshot (taken_at, kernel, boot_id, state, source) VALUES (datetime('now','localtime'), '$kernel', '$boot', 'register scan $LABEL: $STATE', '$out'); SELECT last_insert_rowid();")
say "scan $LABEL: $(wc -l < "$out/todo.txt") words via $VIA, kernel $kernel, snapshot $sid"

# FAST=1: no delay per word; after a crash, step from the first unread word with the slow
# delay for SLOW_WINDOW words, so the culprit is still named exactly; then fast again.
FAST=${FAST:-0}; SLOW_WINDOW=${SLOW_WINDOW:-64}
slow_left=0
pass=0
drop_through() { awk -v a="$1" 'f{print} $1==a{f=1}' "$out/todo.txt" > "$out/todo.next" && mv "$out/todo.next" "$out/todo.txt"; }
wait_back() {
	say "waiting for the M1 to come back"
	local up=""
	for i in $(seq 1 120); do sleep 5; up=$(m1 'cut -d" " -f1 /proc/uptime' 2>/dev/null) && break; done
	[ -n "$up" ] || { say "M1 not back after 10 min; stopping"; return 1; }
	say "M1 back (uptime $up s); $(wc -l < "$out/todo.txt") words left"
}
while [ -s "$out/todo.txt" ]; do
	pass=$((pass + 1))
	raw="$out/stream-$pass.txt"
	if [ "$FAST" = 1 ] && [ $slow_left -eq 0 ]; then d=0; cp "$out/todo.txt" "$out/batch.txt"
	else d=$DELAY; if [ $slow_left -gt 0 ]; then head -n $slow_left "$out/todo.txt" > "$out/batch.txt"; else cp "$out/todo.txt" "$out/batch.txt"; fi; fi
	n_before=$(wc -l < "$out/todo.txt")
	m1 "cat > /root/scan-list.txt && sync" < "$out/batch.txt" || { say "could not send the list"; sleep 10; continue; }
	m1 "DELAY_US=$d /var/tmp/m1power/mrd-stream /root/scan-list.txt" > "$raw" 2>&1
	rc=$?
	grep -E '^0x[0-9a-f]+ [48] ((0x)?[0-9a-f]+|REFUSED|MMAP-FAILED)$' "$raw" >> "$out/reads.txt"
	last=$(grep -E '^reading ' "$raw" | tail -1 | awk '{print $2}')
	done_last=$(grep -E '^0x[0-9a-f]+ [48] ' "$raw" | tail -1 | awk '{print $1}')
	[ -n "$done_last" ] && drop_through "$done_last"
	consumed=$((n_before - $(wc -l < "$out/todo.txt")))
	if [ $rc -eq 0 ]; then
		if [ $slow_left -gt 0 ]; then slow_left=0; say "slow window done"; continue; fi
		say "pass $pass finished"; break
	fi
	if [ -n "$last" ] && [ "$last" != "$done_last" ]; then
		if [ "$d" = 0 ]; then
			say "M1 went away in fast mode near $last (last word completed ${done_last:-none}); stepping slowly from the next word"
			slow_left=$SLOW_WINDOW
		else
			w=$(grep -E "^$last " "$out/todo.txt" | head -1 | awk '{print $2}')
			lab=$(grep -E "^$last " "$out/todo.txt" | head -1 | sed -n 's/.*# *//p')
			say "M1 went away reading $last ($w bytes${lab:+, $lab}); ssh rc $rc"
			echo "$last $w $lab" >> "$out/faults.txt"
			python3 -I "$here/hwdb.py" "$DB" fault "$last" "${w:-4}" "$kernel" "scan $LABEL pass $pass: the M1 went down reading this word${lab:+ ($lab)}" > /dev/null
			drop_through "$last"
			# A gap that faults usually faults throughout. Skip to the next SKIP_ALIGN boundary
			# (default 0x1000, a page); if the previous fault was in the same block (the label before
			# '+') at the start of the page before, skip the rest of that block. Skips are logged.
			al=$(( ${SKIP_ALIGN:-0x1000} )); nb=$(( (last | (al - 1)) + 1 ))
			blk=${lab%%+*}
			if [ -n "$blk" ] && [ "$blk" = "${prev_blk:-}" ] && [ $(( last - ${prev_fault:-0} )) -le $al ]; then
				sk=$(grep -c "# $blk+" "$out/todo.txt")
				grep -v "# $blk+" "$out/todo.txt" > "$out/todo.next"; mv "$out/todo.next" "$out/todo.txt"
				printf '%s.. rest of %s skipped (%d words) after two page faults\n' "$last" "$blk" $sk >> "$out/skipped.txt"
				say "skipped the rest of $blk ($sk words) after two page faults in a row"
			else
				sk=$(awk -v nb=$nb 'strtonum($1) < nb' "$out/todo.txt" | wc -l)
				if [ $sk -gt 0 ]; then
					awk -v nb=$nb 'strtonum($1) >= nb' "$out/todo.txt" > "$out/todo.next" && mv "$out/todo.next" "$out/todo.txt"
					printf '%s..%#x skipped %d words after the fault\n' "$last" $((nb - 1)) $sk >> "$out/skipped.txt"
					say "skipped $sk words up to $(printf %#x $((nb - 1))) after the fault"
				fi
			fi
			prev_blk=$blk; prev_fault=$nb
			[ $slow_left -gt 0 ] && slow_left=$(( slow_left > consumed + 1 ? slow_left - consumed - 1 : 0 ))
		fi
		wait_back || break
	else
		[ $slow_left -gt 0 ] && slow_left=$(( slow_left > consumed ? slow_left - consumed : 0 ))
		say "stream ended (rc $rc) without a fault; retrying the rest"; sleep 5
	fi
done
python3 -I "$here/hwdb.py" "$DB" regs "$sid" "$out/reads.txt" "$LIST" | sed "s/^/$(date +%T) db: /" | tee -a "$out/scan.log"
say "done: $(grep -c . "$out/reads.txt") reads, $(grep -c . "$out/faults.txt") faults"
