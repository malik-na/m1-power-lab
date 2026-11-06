import sys; sys.path.insert(0, "/home/naeem/m1n1/proxyclient")
from m1n1.setup import *
from m1n1.hw.spmi import SPMI
s = SPMI(u, "/arm-io/nub-spmi")
b = [s.read8(0xf, 0x9f00 + i) for i in range(16)]
print("PMU 0x9f00..0f:", " ".join("%02x" % x for x in b))
st = chr(b[10]) if 32 <= b[10] < 127 else b[10]
if b[4] == ord('H'):
    names = ["AOP.GPIO.IRQ4","AOP.GPIO.IRQ6","AOP.OutboxNotEmpty","AOP.CPUWakeupAP","NUB.WakeupAP","NUB.GPIO.IRQ6","NUB.APWatchdog","NUB.APWakeupTime","NUB.SPMI0Sw3IRQ","AOP.SPMI0Sw3IRQ","SMC.CPUWakeupAP","SMC.OutboxNotEmpty","ATC0.CIOWakeup","ATC1.CIOWakeup","ATC0.USBWakeup","ATC1.USBWakeup"]
    m = b[5] | (b[9] << 8)
    print("  handler ran: wake sources set = %s (map %#06x); +0x2c low byte %#04x; actual PS: ATC0_USB %x ATC0_USB_AON %x ATC0_COMMON %x; WD2 CTRL %x; trampoline +0x20>>16 = %#04x, +0x24 = %#04x" % ([n for k, n in enumerate(names) if m >> k & 1] or ["none"], m, b[6], b[7] & 0xf, b[7] >> 4, b[8] & 0xf, b[8] >> 4, b[11], b[12]))
print("  0x9f04:", chr(b[4]) if 32 <= b[4] < 127 else b[4], " stage 0x9f0a:", st, " 0x9f0b:", b[11], " 0x9f0c: %#04x" % b[12], " (0x9f0d is iBoot's)")
r = [s.read8(0xf, 0xd000 + i) for i in range(12)]
rtc = r[4] | r[5] << 8 | r[6] << 16 | r[7] << 24; al = r[8] | r[9] << 8 | r[10] << 16 | r[11] << 24
print("  RTC now %#x (low byte %#04x), alarm %#x (low byte %#04x), alarm_ctrl %#04x; RTC-alarm = %d s" % (rtc, rtc & 0xff, al, al & 0xff, r[0], rtc - al))
print("base", hex(p.get_base()), "RVBAR", hex(p.read64(0x210050000)))
