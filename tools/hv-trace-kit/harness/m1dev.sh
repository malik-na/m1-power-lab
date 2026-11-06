# m1n1 proxy tty = USB 1209:316d interface 00
m1dev() {
  for t in /sys/class/tty/ttyACM*; do
    [ -e "$t/device" ] || continue
    d=$(readlink -f "$t/device"); u=$(dirname "$d")
    [ "$(cat $d/bInterfaceNumber 2>/dev/null)" = 00 ] && [ "$(cat $u/idVendor 2>/dev/null)" = 1209 ] && { echo /dev/$(basename $t); return 0; }
  done; return 1
}
