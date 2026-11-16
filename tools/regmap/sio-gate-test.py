#!/usr/bin/env python3
"""Awake test of the SIO island's power gate (#45), run ON THE M1 as root, cable out.

Copies the chip's own sleep program for the SIO island (decoded engine program, var/recfg,
t8103-recfg-decoded.txt lines 268-351): arm the gate records #44 (0x23b71c0a8 = 0xc0080860) and
#45 (0x23b71c090 = 0x80080860), switch the island off in the program's order (sio_cpu with its
RESET bit, the 32 children, uart_p/spi_p/audio_p/sio_adma, sio, sio_busif), waiting for each
power word's bit 11 to clear, then watch bit 30 of #44 and #45. Restores every original value,
parents first. The question: does #45 report ready with the SIO coprocessor stopped?

Every access is one 32-bit load or store to /dev/mem opened O_SYNC (device memory). Every line is
flushed as it happens, so a crash still leaves the last step on the M3 Max. Expect the keyboard,
trackpad, audio and i2c0 (type-C controllers) to be dead until the M1 is rebooted afterwards.
"""
import ctypes, mmap, os, sys, time

PMGR = 0x23b700000
PS = lambda off: PMGR + off
G44, G45 = 0x23b71c0a8, 0x23b71c090
ASC_SIO = 0x236400000
# The program's order and values (wr32 lines 273-349).
CHILDREN = [0x1d8, 0x1e0, 0x1e8, 0x1f0, 0x1f8, 0x200, 0x208, 0x210, 0x238, 0x240, 0x248, 0x250,
            0x258, 0x260, 0x268, 0x270, 0x278, 0x280, 0x288, 0x290, 0x298, 0x2a0, 0x2a8, 0x2b0,
            0x2b8, 0x2c0, 0x2c8, 0x2d0, 0x2d8, 0x2e0, 0x2e8, 0x2f0]
MIDDLE = [0x220, 0x218, 0x228, 0x230]          # uart_p, spi_p, audio_p, sio_adma
NAMES = {0x1c0: "sio_busif", 0x1c8: "sio", 0x1d0: "sio_cpu", 0x1d8: "fpwm0", 0x1e0: "fpwm1",
         0x1e8: "fpwm2", 0x218: "spi_p", 0x220: "uart_p", 0x228: "audio_p", 0x230: "sio_adma"}

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
maps = {}
def word(a):
    page = a & ~0x3fff
    if page not in maps:
        maps[page] = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
    return ctypes.c_uint32.from_buffer(maps[page], a - page)
def rd(a): return word(a).value
def wr(a, v): word(a).value = v
def say(*x):
    print("%.6f" % time.monotonic(), *x); sys.stdout.flush()
def poll(a, mask, want, us):
    t = time.monotonic()
    while time.monotonic() - t < us / 1e6:
        v = rd(a)
        if v & mask == want: return True, v, (time.monotonic() - t) * 1e6
    return False, rd(a), us
name = lambda off: NAMES.get(off, hex(PS(off)))

island = [0x1d0] + CHILDREN + MIDDLE + [0x1c8, 0x1c0]
orig = {off: rd(PS(off)) for off in island}
orig[G44], orig[G45] = rd(G44), rd(G45)
say("before: G44 %#010x G45 %#010x  sio asc run %#x status %#x" % (orig[G44], orig[G45], rd(ASC_SIO + 0x44), rd(ASC_SIO + 0x48)))
say("before: " + " ".join("%s=%#x" % (name(o), orig[o]) for o in [0x1c0, 0x1c8, 0x1d0, 0x1d8, 0x1e0, 0x1e8, 0x218, 0x220, 0x228, 0x230]))

stuck = []
try:
    say("arm G44=0xc0080860 G45=0x80080860"); wr(G44, 0xc0080860); wr(G45, 0x80080860)
    say("after arm: G44 %#010x G45 %#010x" % (rd(G44), rd(G45)))
    say("sio_cpu = 0x80000000 (off + RESET)"); wr(PS(0x1d0), 0x80000000)
    for off in CHILDREN: wr(PS(off), 0)
    say("children written 0")
    for off in CHILDREN + [0x1d0]:
        ok, v, us = poll(PS(off), 0x800, 0, 50_000)
        if not ok: stuck.append((name(off), v))
    say("children settled; bit 11 still set on: %s" % (stuck or "none"))
    for off in MIDDLE: wr(PS(off), 0)
    for off in MIDDLE:
        ok, v, us = poll(PS(off), 0x800, 0, 50_000)
        if not ok: stuck.append((name(off), v))
    for off in (0x1c8, 0x1c0):
        wr(PS(off), 0); ok, v, us = poll(PS(off), 0x800, 0, 50_000)
        say("%s = 0 -> %#010x (bit 11 %s after %d us)" % (name(off), v, "clear" if ok else "STILL SET", us))
        if not ok: stuck.append((name(off), v))
    say("island off: " + " ".join("%s=%#x" % (name(o), rd(PS(o))) for o in [0x1c0, 0x1c8, 0x1d0, 0x1d8, 0x1e0, 0x1e8, 0x228, 0x230]))
    t0 = time.monotonic(); last = None; first_ready = {}
    while time.monotonic() - t0 < 2.0:
        g44, g45 = rd(G44), rd(G45)
        cur = (g44 >> 30 & 1, g45 >> 30 & 1)
        if cur != last:
            say("t=%.4f s  G44 %#010x (b30=%d)  G45 %#010x (b30=%d)" % (time.monotonic() - t0, g44, cur[0], g45, cur[1]))
            last = cur
        for k, b in (("G44", cur[0]), ("G45", cur[1])):
            if b and k not in first_ready: first_ready[k] = time.monotonic() - t0
        if "G45" in first_ready: break
        time.sleep(0.001)
    say("RESULT: G44 ready %s, G45 ready %s; stuck bit 11: %s" % (
        "at %.4f s" % first_ready["G44"] if "G44" in first_ready else "NO (2 s)",
        "at %.4f s" % first_ready["G45"] if "G45" in first_ready else "NO (2 s)", stuck or "none"))
    say("sio asc run %#x status %#x" % (rd(ASC_SIO + 0x44), rd(ASC_SIO + 0x48)))
finally:
    wr(G45, orig[G45]); wr(G44, orig[G44])
    for off in [0x1c0, 0x1c8] + MIDDLE + CHILDREN + [0x1d0]:
        wr(PS(off), orig[off] & 0xffffffff)
    time.sleep(0.05)
    say("restored: " + " ".join("%s=%#x" % (name(o), rd(PS(o))) for o in [0x1c0, 0x1c8, 0x1d0, 0x1e0, 0x228]))
    say("restored: G44 %#010x G45 %#010x" % (rd(G44), rd(G45)))
