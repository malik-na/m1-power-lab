# hv script (run_guest.py -m): put a resume mailbox for apple_deepsleep into guest RAM before
# the guest starts. Under the hypervisor no boot loader publishes one (the guest m1n1 stage has
# no s2r-mailbox code), and without it the driver does not enable. The guest DTB names the
# address (/chosen/asahi,s2r-mailbox) and reserves the page (/reserved-memory/s2r-mailbox@...):
# var/hvlinux/ds12/j313-hv-ds.dts. Layout as the driver validates it at boot: magic "S2RMBOX1",
# version 1, 8 cores, armed 1, boot core MPIDR 0, one 0x40-byte slot per core (MPIDR at +0,
# entry +0x28 = 0, entries +0x30, state +0x38). No loader stands behind it: the reset vector
# field is 0, and nothing on the wake side reads the slots.
import os
import struct

DS_MAILBOX = int(os.environ.get("DS_MAILBOX", "0x9d0000000"), 0)
_SIZE = 0x840
_MPIDR = (0x0, 0x1, 0x2, 0x3, 0x10100, 0x10101, 0x10102, 0x10103)

_buf = bytearray(_SIZE)
struct.pack_into("<QIIQQQQ", _buf, 0, 0x31584F424D523253, 1, len(_MPIDR), 0, 1, 0, 0)
for _i, _m in enumerate(_MPIDR):
    struct.pack_into("<Q", _buf, 0x40 + 0x40 * _i, _m)
p.memset8(DS_MAILBOX, 0, 0x4000)
iface.writemem(DS_MAILBOX, bytes(_buf))
p.dc_civac(DS_MAILBOX, 0x4000)
_back = iface.readmem(DS_MAILBOX, _SIZE)
print(f"[ds-mailbox] {_SIZE:#x} bytes at {DS_MAILBOX:#x}, cleaned to PoC; read back "
      f"{'equal' if _back == bytes(_buf) else 'DIFFERENT'}; magic {_back[:8]!r}")
