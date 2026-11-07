#!/bin/bash
# Install the Wi-Fi watchdog on the M1 through maclab exec (host side).
# Undo on the M1: systemctl disable --now m1power-wifi-heal.timer;
#   rm /usr/local/bin/m1power-wifi-heal /etc/systemd/system/m1power-wifi-heal.{service,timer}
set -eu
cd "$(dirname "$0")"; DEV=${1:-naeems-m1-airr}
put() { lab exec "$DEV" "echo $(base64 -w0 "$1") | base64 -d > $2 && chmod $3 $2" >/dev/null; }
put m1power-wifi-heal /usr/local/bin/m1power-wifi-heal 755
put m1power-wifi-heal.service /etc/systemd/system/m1power-wifi-heal.service 644
put m1power-wifi-heal.timer /etc/systemd/system/m1power-wifi-heal.timer 644
lab exec "$DEV" 'systemctl daemon-reload && systemctl enable --now m1power-wifi-heal.timer && systemctl start m1power-wifi-heal.service; systemctl is-enabled m1power-wifi-heal.timer; systemctl list-timers m1power-wifi-heal.timer --no-pager | sed -n 2p; journalctl -t m1power-wifi-heal --no-pager | tail -3; iw dev wlan0 get power_save'
