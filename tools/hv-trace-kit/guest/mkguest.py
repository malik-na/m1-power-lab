#!/usr/bin/env python3
"""Assemble a Linux guest image for the m1n1 hypervisor (run_guest.py -r).

    mkguest.py --m1n1 m1n1.bin --dtb j313-hv.dtb --initramfs initramfs.img --kernel vmlinuz \
               --bootargs bootargs.txt --out guest.bin

Layout, in the order the guest m1n1 parses its payloads: m1n1, "chosen.bootargs=<line>\n",
the device tree, a filler variable that puts the initramfs data on a 4 KiB boundary (m1n1 hands
the kernel the initramfs in place), the initramfs behind m1n1's own header, and the kernel last
(an in-line kernel ends payload parsing). The guest m1n1 must be built with MAX_VAR_SIZE 4096
(~/m1n1-guest): the command line is longer than the stock 1024 bytes.
"""
import argparse
import struct


def build(m1n1: bytes, bootargs: str, dtb: bytes, initramfs: bytes, kernel: bytes) -> bytes:
    if len(bootargs) > 4000:
        raise SystemExit(f"bootargs are {len(bootargs)} bytes; the guest m1n1 takes 4096 per variable")
    var = ("chosen.bootargs=" + bootargs).encode()
    var += b" " * ((-(len(m1n1) + len(var) + 1)) % 8) + b"\n"
    out = m1n1 + var + dtb
    hdr = len(b"m1n1_initramfs") + 4
    pad = (-(len(out) + len(b"chosen.pad=") + 1 + hdr)) % 4096 or 4096
    out += b"chosen.pad=" + b"x" * pad + b"\n"
    assert (len(out) + hdr) % 4096 == 0
    return out + b"m1n1_initramfs" + struct.pack("<I", len(initramfs)) + initramfs + kernel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("m1n1", "dtb", "initramfs", "kernel", "bootargs", "out"):
        ap.add_argument("--" + name, required=True)
    a = ap.parse_args()
    rd = lambda p: open(p, "rb").read()
    img = build(rd(a.m1n1), open(a.bootargs).read().strip(), rd(a.dtb), rd(a.initramfs), rd(a.kernel))
    open(a.out, "wb").write(img)
    print(f"{a.out}: {len(img)} bytes")


if __name__ == "__main__":
    main()
