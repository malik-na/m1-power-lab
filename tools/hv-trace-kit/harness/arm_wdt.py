# hv script: arm the M1's hardware watchdog so a hung guest reboots the Mac back into m1n1.
WDT_SECONDS = 150
base = u.adt["/arm-io/wdt"].get_reg(0)[0]
p.write32(base + 0x1c, 0)
p.write32(base + 0x10, 0)
p.write32(base + 0x14, WDT_SECONDS * 24_000_000)
p.write32(base + 0x1c, 4)
print(f"WDT armed: {WDT_SECONDS}s at {base:#x}")
