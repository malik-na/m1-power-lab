#!/bin/bash
# Install the wake-breadcrumb second stage on the M1's EFI partition, over Thunderbolt.
#   M1_CLAIM=<who> tools/m1n1/install-breadcrumb.sh
#
# What it does on the M1, in /boot/efi/m1n1/ only, and only with files named boot.bin* and
# restore-pre-breadcrumb.sh:
#   1. checks /boot/efi is mounted, boot.bin is the expected one (0a1e47f3, mb2 + SIO alias), and
#      there is room for two more copies;
#   2. keeps it as boot.bin.pre-breadcrumb-<sha8> (checked by hash);
#   3. writes restore-pre-breadcrumb.sh beside it (no arguments, macOS or Linux, puts the kept
#      file back over boot.bin);
#   4. uploads the new file as boot.bin.breadcrumb-new, checks its hash, renames it over boot.bin,
#      syncs and checks boot.bin's hash as read back from the partition.
# It does not reboot the M1, change the boot volume or touch anything else. Re-running it after a
# full install does nothing. Nothing is undone automatically when a step fails; the message says
# what stands.
#
# The new file: var/bootloader/boot.bin.breadcrumb = the installed boot.bin with only its first
# 4 MiB (the m1n1 loader) replaced by the breadcrumb build (~/Work/m1n1-mb2-breadcrumb, branch
# m1power/wake-breadcrumb, 91d54c2, built with RELEASE=1 CHAINLOADING=1 ESP_STAGE2=1); the device trees, the SIO alias and u-boot after 0x400000 are the same
# bytes. Read the result with tools/m1n1/read-breadcrumb.sh.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
tb="$repo/tools/tb"
NEWF="$repo/var/bootloader/boot.bin.breadcrumb"
NEW=396dd5df4584b21217700f8c07fae2ba49c5e69fcdd45130d41ad58c7def981a
OLD=0a1e47f3c02b7731c87eb8f37ea9b4781f376ef695c9078195b5f4d40900b20a
KEEP=boot.bin.pre-breadcrumb-${OLD:0:8}
D=/boot/efi/m1n1

"$tb/m1-claim" check || exit 1
[ -f "$NEWF" ] || { echo "STOP: no $NEWF"; exit 1; }
[ "$(sha256sum "$NEWF" | cut -c1-64)" = "$NEW" ] || { echo "STOP: $NEWF does not have the expected hash"; exit 1; }
size=$(stat -c %s "$NEWF")
m1() { "$tb/m1tb" -o BatchMode=yes "$@"; }

echo "== 1-3: check, keep the present boot.bin, write the restore script"
rc=0
m1 "bash -s" <<EOF || rc=$?
set -eu
D=$D; NEW=$NEW; OLD=$OLD; KEEP=$KEEP; SIZE=$size
findmnt -n /boot/efi >/dev/null || { echo "STOP: /boot/efi is not mounted. Nothing changed."; exit 1; }
cd "\$D"
# hash as read from the partition (O_DIRECT, past the page cache); a cached read where the kernel refuses
dsum() { b=\$(dd if="\$1" iflag=direct bs=1M status=none 2>/dev/null | sha256sum | cut -c1-64); if [ -n "\$b" ] && [ "\$b" != "\$(printf '' | sha256sum | cut -c1-64)" ]; then echo "\$b"; else sha256sum "\$1" | cut -c1-64; fi; }
cur=\$(sha256sum boot.bin | cut -c1-64)
if [ "\$cur" = "\$NEW" ]; then echo "boot.bin is already the breadcrumb build. Nothing to do."; exit 3; fi
[ "\$cur" = "\$OLD" ] || { echo "STOP: boot.bin is \$cur, not the expected \$OLD. Nothing changed."; exit 1; }
if [ -f "\$KEEP" ] && [ "\$(sha256sum "\$KEEP" | cut -c1-64)" = "\$OLD" ]; then
	need=\$((SIZE + 1048576))
else
	need=\$((SIZE * 2 + 1048576))
fi
avail=\$(df -B1 --output=avail /boot/efi | tail -1 | tr -d ' ')
[ "\$avail" -ge "\$need" ] || { echo "STOP: /boot/efi has \$avail bytes free, needs \$need. Nothing changed."; exit 1; }
if ! { [ -f "\$KEEP" ] && [ "\$(sha256sum "\$KEEP" | cut -c1-64)" = "\$OLD" ]; }; then
	cp -p boot.bin "\$KEEP"
	sync
	[ "\$(dsum "\$KEEP")" = "\$OLD" ] || { echo "STOP: the kept copy \$KEEP does not read back from the partition with its hash. boot.bin unchanged."; exit 1; }
fi
echo "kept: \$D/\$KEEP"
cat > restore-pre-breadcrumb.sh <<'RESTORE'
#!/bin/sh
# restore-pre-breadcrumb.sh: lives beside boot.bin on the M1's EFI partition. NO ARGUMENTS.
# For Naeem, from macOS (or Linux), with sudo, if the M1 does not start Linux after the wake
# breadcrumb loader of 2026-11-20: it puts the second stage from before that change
# ($KEEP, mb2 + SIO alias) back over boot.bin.
# It touches nothing but boot.bin in its own folder. The breadcrumb build is not kept here (it is
# on the M3, var/bootloader/boot.bin.breadcrumb).
#
# From macOS, by hand:
#   1. If the M1 is dark or hung: hold the power button until it is off, then hold it again until
#      the startup options appear.
#   2. Choose the macOS volume and log in.
#   3. Terminal: diskutil list. Find Omarchy's FAT32 EFI partition (Linux nvme0n1p4, most likely
#      disk0s4; it holds a folder m1n1 with this script in it), then
#        sudo diskutil mount disk0sN
#   4. sudo sh "/Volumes/<EFI name>/m1n1/restore-pre-breadcrumb.sh"
#      It must print DONE.
#   5. Restart, hold the power button for the startup options, choose Omarchy.
# If the macOS volume starts the m1n1 proxy instead of macOS: the M3 can chainload the kept file
# over USB (proxyclient tools/chainload.py -r); if Omarchy comes up on it (not tried), this script can be
# run over Thunderbolt (sudo sh /boot/efi/m1n1/restore-pre-breadcrumb.sh).
d=\$(cd "\$(dirname "\$0")" && pwd)
OLD=$OLD
if command -v shasum >/dev/null 2>&1; then H="shasum -a 256"
elif command -v sha256sum >/dev/null 2>&1; then H=sha256sum
else echo "STOP: neither shasum nor sha256sum is on this system (recoveryOS may have neither). Run this from a full macOS or from Linux. Nothing changed."; exit 1; fi
sum() { \$H "\$1" | cut -c1-64; }
[ -f "\$d/$KEEP" ] || { echo "STOP: no $KEEP beside this script (\$d). Nothing changed."; exit 1; }
[ "\$(sum "\$d/$KEEP")" = "\$OLD" ] || { echo "STOP: the kept file does not have its hash. Nothing changed."; exit 1; }
if [ "\$(sum "\$d/boot.bin")" = "\$OLD" ]; then echo "boot.bin is already the pre-breadcrumb one. Nothing to do."; exit 0; fi
cp -f "\$d/$KEEP" "\$d/boot.bin" && sync
if [ "\$(sum "\$d/boot.bin")" = "\$OLD" ]; then echo "DONE: the pre-breadcrumb second stage is back. Restart and choose Omarchy."
else echo "STOP: boot.bin does not read back as the pre-breadcrumb one. Run this script once more."; exit 1; fi
RESTORE
chmod 755 restore-pre-breadcrumb.sh 2>/dev/null || true
sync
echo "restore script: \$D/restore-pre-breadcrumb.sh"
EOF
if [ "$rc" = 3 ]; then exit 0; fi
[ "$rc" = 0 ] || exit "$rc"

echo "== 4: upload, check, install"
m1 "cat > $D/boot.bin.breadcrumb-new && sync" < "$NEWF"
m1 "bash -s" <<EOF
set -eu
cd $D
dsum() { b=\$(dd if="\$1" iflag=direct bs=1M status=none 2>/dev/null | sha256sum | cut -c1-64); if [ -n "\$b" ] && [ "\$b" != "\$(printf '' | sha256sum | cut -c1-64)" ]; then echo "\$b"; else sha256sum "\$1" | cut -c1-64; fi; }
[ "\$(dsum boot.bin.breadcrumb-new)" = "$NEW" ] || { echo "STOP: the uploaded boot.bin.breadcrumb-new does not have the expected hash. boot.bin unchanged."; exit 1; }
[ "\$(sha256sum boot.bin | cut -c1-64)" = "$OLD" ] || { echo "STOP: boot.bin changed while this ran. Not installed; boot.bin.breadcrumb-new left beside it."; exit 1; }
mv -f boot.bin.breadcrumb-new boot.bin
sync
# read back from the partition, not the page cache, where the kernel allows it
if back=\$(dd if=boot.bin iflag=direct bs=1M status=none 2>/dev/null | sha256sum | cut -c1-64) && [ "\$back" != "\$(printf '' | sha256sum | cut -c1-64)" ]; then how="direct read"; else back=\$(sha256sum boot.bin | cut -c1-64); how="cached read"; fi
if [ "\$back" = "$NEW" ]; then echo "INSTALLED: $D/boot.bin = $NEW (\$how)"
else echo "STOP: boot.bin reads back as \$back (\$how), not $NEW. Put the old one back with $D/restore-pre-breadcrumb.sh"; exit 1; fi
ls -l $D/boot.bin $D/$KEEP $D/restore-pre-breadcrumb.sh
EOF
echo "Not rebooted. The next boot of Omarchy runs the breadcrumb loader."
echo "While it is installed: no package upgrade on the M1 (an update-m1n1 run, e.g. from an aura"
echo "upgrade, rebuilds boot.bin from aura's m1n1 and drops both mb2 and the breadcrumb)."
