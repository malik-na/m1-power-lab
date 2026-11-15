#!/bin/sh
# Run ON THE M1 AIR, as root, once after a reinstall:
#   curl -fsSL https://raw.githubusercontent.com/malik-na/m1-power-lab/omarchy-live-power/tools/tb/authorize-m3-max.sh | sudo sh
# Lets the M3 Max's lab key log in as root (over the Thunderbolt link or
# Tailscale). Only appends one public key; changes nothing else.
set -eu
key='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILQm2or6sp1IDbxg8AacMx5rUxtH7BeHqqgBihusWPsA naeems-m3-max -> m1 air (thunderbolt lab link)'
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
grep -qxF "$key" /root/.ssh/authorized_keys || printf '%s\n' "$key" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "m3-max key authorized for root on $(hostname)"
