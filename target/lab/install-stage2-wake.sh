#!/bin/bash
# Install a modified ESP stage-2 m1n1 (omacom bc79acc4 + the m1power S2R wake note) on the M1,
# through maclab exec. Only the m1n1 image at the front of the ESP's m1n1/boot.bin is replaced; the
# payloads after it (device trees, U-Boot, config) are kept byte for byte. The current file is kept
# as boot.bin.pre-s2r-wake next to it (boot.bin.old, if update-m1n1 left one, is not touched).
#
# Usage: install-stage2-wake.sh <new m1n1.bin> [device]     (host side)
# Undo on the M1 (root):  cp <esp>/m1n1/boot.bin.pre-s2r-wake <esp>/m1n1/boot.bin && sync
set -eu
NEW=${1:?new m1n1.bin}; DEV=${2:-naeems-m1-airr}
SHA=$(sha256sum "$NEW" | cut -c1-64)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
gzip -9c "$NEW" | base64 -w0 > "$TMP/b64"
split -b 120000 "$TMP/b64" "$TMP/part."
lab exec "$DEV" 'rm -f /run/m1power-stage2.b64' >/dev/null
for p in "$TMP"/part.*; do
	lab exec "$DEV" "printf '%s' '$(cat "$p")' >> /run/m1power-stage2.b64" >/dev/null
done
lab exec "$DEV" "set -e
base64 -d /run/m1power-stage2.b64 | gunzip > /run/m1power-stage2.bin
got=\$(sha256sum /run/m1power-stage2.bin | cut -c1-64)
[ \"\$got\" = $SHA ] || { echo \"transfer sha mismatch: \$got\"; exit 1; }
ESP=\$(for d in /boot/efi /efi /boot; do [ -f \$d/m1n1/boot.bin ] && echo \$d && break; done)
[ -n \"\$ESP\" ] || { echo 'no m1n1/boot.bin on the ESP'; exit 1; }
B=\$ESP/m1n1/boot.bin
PKG=/usr/lib/asahi-boot/m1n1.bin
[ -f \$PKG ] || { echo \"no \$PKG\"; exit 1; }
OLD=\$(stat -c %s \$PKG)
# The original stays in boot.bin.pre-s2r-wake; later installs rebuild from it.
[ -f \$B.pre-s2r-wake ] || cp -p \$B \$B.pre-s2r-wake
cmp -n \$OLD \$PKG \$B.pre-s2r-wake || { echo 'boot.bin.pre-s2r-wake does not start with the packaged m1n1.bin: not touching boot.bin'; exit 1; }
{ cat /run/m1power-stage2.bin; tail -c +\$((OLD + 1)) \$B.pre-s2r-wake; } > \$B.new
echo \"old boot.bin \$(stat -c %s \$B.pre-s2r-wake) bytes (m1n1 part \$OLD), new \$(stat -c %s \$B.new) bytes (m1n1 part \$(stat -c %s /run/m1power-stage2.bin))\"
mv \$B.new \$B
sync
ls -l \$ESP/m1n1/
cmp -n \$(stat -c %s /run/m1power-stage2.bin) /run/m1power-stage2.bin \$B && echo 'installed image matches'
"
