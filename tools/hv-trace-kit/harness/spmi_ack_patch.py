# hv script (run_guest -m, before the guest starts): stop our own hypervisor from waking the guest
# out of a real sleep.
#
# macOS's last act on the power chip's bus controller before its sleep is to leave one interrupt
# enabled (0x23d0d9338 = 1: "a reply has arrived", status 0x23d0d9378 bit 0) with that status
# acknowledged. m1n1's commit path then sends up to nine commands of its own (stage markers, the
# wake handler's address, the alarm) and never acknowledges their status: the controller's
# interrupt line (wake source 54) is up when the SoC goes down, and it wakes at once (135full1,
# 2026-11-17: asleep for 1 s; 2026-11-16: 0.65 s).
#
# The patch, in the running image (the wake lands in this image, so it survives the sleep):
#   - the last power-chip write of the commit path, the sub-stage marker 4 (a debug breadcrumb),
#     at +0x3f57c, calls a stub instead;
#   - the stub, in the body of the unused standalone s2r_sub at +0x3eae0, writes 1 to
#     0x23d0d9378 (acknowledges the status) and returns.
# Offsets are of ~/m1n1/build/m1n1.bin of 2026-11-16 13:27; the words there are compared with
# the running image first and nothing is written if they differ.
import struct
_B = p.get_base()
_STUB, _CALL = 0x3eae0, 0x3f57c
_img = open("/home/naeem/m1n1/build/m1n1.bin", "rb").read()
_old_stub = list(struct.unpack_from("<13I", _img, _STUB))
_old_call = struct.unpack_from("<I", _img, _CALL)[0]
_new_stub = [0xD2926F01,    # movz x1, #0x9378
             0xF2A7A1A1,    # movk x1, #0x3d0d, lsl #16
             0xF2C00041,    # movk x1, #0x2, lsl #32      -> 0x23d0d9378
             0x52800022,    # movz w2, #1
             0xB9000022,    # str  w2, [x1]
             0xD65F03C0]    # ret
_new_call = 0x94000000 | (((_STUB - _CALL) // 4) & 0x3ffffff)
_run_stub = [p.read32(_B + _STUB + 4 * i) for i in range(13)]
_run_call = p.read32(_B + _CALL)
_done = lambda: [p.read32(_B + _STUB + 4 * i) for i in range(6)] == _new_stub and p.read32(_B + _CALL) == _new_call
# m1n1 maps its own code read-only (a plain write is dropped: first try, 03:44), and the proxy
# does not survive running with the MMU off (second try, 03:45: the Mac reset itself). So the
# words are written by a routine that runs on the Mac: MMU off, six words and the call word
# stored, MMU on again, no call and no stack in between.
#   x0 = stub address, x1 = call address, x2 = new call word, x3 = the six stub words
_BLOB = [0xD53C1009,    # mrs  x9, sctlr_el2
         0x927FF92A,    # and  x10, x9, #~1
         0xD51C100A,    # msr  sctlr_el2, x10        MMU off
         0xD5033FDF,    # isb
         0x528000CC,    # mov  w12, #6
         0xB840446B,    # ldr  w11, [x3], #4
         0xB800440B,    # str  w11, [x0], #4
         0x7100058C,    # subs w12, w12, #1
         0x54FFFFA1,    # b.ne -3
         0xB9000022,    # str  w2, [x1]
         0xD51C1009,    # msr  sctlr_el2, x9         MMU as it was
         0xD5033FDF,    # isb
         0xD65F03C0]    # ret
if _done():
    print("[ack-patch] already applied (stub at %#x)" % (_B + _STUB))
elif _old_call != 0x97FFCEC1:
    print("[ack-patch] NOT APPLIED: the build's call word is %#x, not the bl to spmi_ext_write_long" % _old_call)
elif _run_stub != _old_stub or _run_call != _old_call:
    print("[ack-patch] NOT APPLIED: the running image differs from the build at the patch sites (call %#x)" % _run_call)
elif (u.mrs((3, 0, 4, 2, 2)) >> 2) & 3 != 2:
    print("[ack-patch] NOT APPLIED: m1n1 is not running at EL2")
else:
    _mem = u.malloc(0x100)
    for i, w in enumerate(_BLOB):
        p.write32(_mem + 4 * i, w)
    for i, w in enumerate(_new_stub):
        p.write32(_mem + 0x80 + 4 * i, w)
    p.dc_cvau(_mem, 0x100); p.ic_ivau(_mem, 0x100)
    p.dc_civac(_B + _STUB, 24); p.dc_civac(_B + _CALL, 4)
    p.call(_mem, _B + _STUB, _B + _CALL, _new_call, _mem + 0x80)
    p.ic_ivau(_B + _STUB, 24); p.ic_ivau(_B + _CALL, 4)
    print("[ack-patch] %s: stub at %#x, call at %#x = %#x" % ("APPLIED" if _done() else "WRITE DID NOT READ BACK", _B + _STUB, _B + _CALL, p.read32(_B + _CALL)))
