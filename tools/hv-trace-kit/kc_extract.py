#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Unwrap a macOS kernelcache (IMG4 or IM4P) into the Mach-O that run_guest.py loads.

Replaces the two img4tool steps in the Asahi docs (docs/sw/m1n1-hypervisor.md
"Production Kernel"): IMG4 -> IM4P -> payload -> decompress. Uses only the
standard library plus the `lzfse` command (Arch: pacman -S lzfse) for LZFSE
payloads ("bvx2"); "complzss" payloads are decompressed in Python.

    python3 -I kc_extract.py kernelcache kernelcache.macho
    python3 -I kc_extract.py --selftest

Do not share the input or output: they are Apple binaries.
"""

import os
import shutil
import subprocess
import sys
import tempfile


def der(buf, pos):
    """Parse one DER TLV at pos -> (tag, value_start, value_end)."""
    tag = buf[pos]
    pos += 1
    ln = buf[pos]
    pos += 1
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(buf[pos:pos + n], "big")
        pos += n
    return tag, pos, pos + ln


def der_children(buf, start, end):
    out = []
    pos = start
    while pos < end:
        tag, vs, ve = der(buf, pos)
        out.append((tag, vs, ve))
        pos = ve
    return out


def im4p_payload(buf):
    tag, vs, ve = der(buf, 0)
    if tag != 0x30:
        raise ValueError("not a DER SEQUENCE: is this already a Mach-O?")
    kids = der_children(buf, vs, ve)
    magic = bytes(buf[kids[0][1]:kids[0][2]])
    if magic == b"IMG4":
        # IMG4 ::= SEQUENCE { "IMG4", IM4P, [0] IM4M, [1] IM4R? }
        return im4p_payload(buf[_tlv_start(buf, kids[1]):kids[1][2]])
    if magic != b"IM4P":
        raise ValueError(f"unexpected magic {magic!r}")
    # IM4P ::= SEQUENCE { "IM4P", type, description, OCTET STRING data, ... }
    typ = bytes(buf[kids[1][1]:kids[1][2]]).decode("ascii", "replace")
    tag, s, e = kids[3]
    if tag != 0x04:
        raise ValueError("IM4P data is not an OCTET STRING")
    return typ, bytes(buf[s:e])


def _tlv_start(buf, kid):
    # Re-derive the TLV header start for a child so it can be parsed standalone.
    tag, vs, ve = kid
    # header is 2 bytes + n length bytes; search back at most 6 bytes
    for back in range(2, 8):
        st = vs - back
        try:
            t, a, b = der(buf, st)
        except Exception:
            continue
        if t == tag and a == vs and b == ve:
            return st
    raise ValueError("cannot locate TLV header")


def lzss_decompress(src, out_len):
    # Apple's lzss.c: N=4096, F=18, THRESHOLD=2, ring buffer pre-filled with spaces.
    N, F, TH = 4096, 18, 2
    ring = bytearray(b" " * (N - F)) + bytearray(F)
    r = N - F
    out = bytearray()
    i = 0
    flags = 0
    while i < len(src) and len(out) < out_len:
        flags >>= 1
        if not flags & 0x100:
            flags = src[i] | 0xff00
            i += 1
            if i >= len(src):
                break
        if flags & 1:
            c = src[i]
            i += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & (N - 1)
        else:
            if i + 1 >= len(src):
                break
            a, b = src[i], src[i + 1]
            i += 2
            pos = a | ((b & 0xf0) << 4)
            ln = (b & 0x0f) + TH
            for k in range(ln + 1):
                c = ring[(pos + k) & (N - 1)]
                out.append(c)
                ring[r] = c
                r = (r + 1) & (N - 1)
    return bytes(out[:out_len])


def decompress(payload):
    if payload[:4] in (b"bvx2", b"bvx1", b"bvxn", b"bvx-"):
        tool = shutil.which("lzfse")
        if not tool:
            raise SystemExit("LZFSE payload: install the lzfse command (pacman -S lzfse)")
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in"), os.path.join(d, "out")
            with open(src, "wb") as f:
                f.write(payload)
            subprocess.run([tool, "-decode", "-i", src, "-o", dst], check=True)
            with open(dst, "rb") as f:
                return f.read()
    if payload[:8] == b"complzss":
        out_len = int.from_bytes(payload[12:16], "big")
        comp_len = int.from_bytes(payload[16:20], "big")
        return lzss_decompress(payload[0x180:0x180 + comp_len], out_len)
    return payload


def describe(macho):
    magic = int.from_bytes(macho[:4], "little")
    if magic != 0xfeedfacf:
        return f"NOT a 64-bit Mach-O (magic {magic:#x})"
    cpu = int.from_bytes(macho[4:8], "little")
    ftype = int.from_bytes(macho[12:16], "little")
    names = {2: "EXECUTE", 0xb: "KEXT_BUNDLE", 0xc: "FILESET"}
    return f"Mach-O 64, cputype {cpu:#x}, filetype {names.get(ftype, hex(ftype))}"


def extract(inp, outp):
    buf = open(inp, "rb").read()
    if int.from_bytes(buf[:4], "little") == 0xfeedfacf:
        print("input is already a Mach-O; copying")
        open(outp, "wb").write(buf)
        return
    typ, payload = im4p_payload(buf)
    print(f"IM4P type {typ!r}, payload {len(payload)} bytes, header {payload[:8]!r}")
    macho = decompress(payload)
    open(outp, "wb").write(macho)
    print(f"wrote {outp}: {len(macho)} bytes, {describe(macho)}")


def _der_tlv(tag, value):
    n = len(value)
    if n < 0x80:
        hdr = bytes([tag, n])
    else:
        lb = n.to_bytes((n.bit_length() + 7) // 8, "big")
        hdr = bytes([tag, 0x80 | len(lb)]) + lb
    return hdr + value


def selftest():
    fake = (0xfeedfacf).to_bytes(4, "little") + (0x0100000c).to_bytes(4, "little") + \
        b"\0" * 4 + (0xc).to_bytes(4, "little") + bytes(range(256)) * 600
    # 1) literal-only complzss stream
    lit = bytearray()
    for i in range(0, len(fake), 8):
        lit.append(0xff)
        lit += fake[i:i + 8]
    hdr = b"complzss" + b"\0" * 4 + len(fake).to_bytes(4, "big") + len(lit).to_bytes(4, "big")
    hdr = hdr.ljust(0x180, b"\0")
    for name, payload in (("plain", fake), ("lzss", hdr + bytes(lit))):
        im4p = _der_tlv(0x30, _der_tlv(0x16, b"IM4P") + _der_tlv(0x16, b"krnl") +
                        _der_tlv(0x16, b"KernelCacheBuilder") + _der_tlv(0x04, payload))
        img4 = _der_tlv(0x30, _der_tlv(0x16, b"IMG4") + im4p + _der_tlv(0xa0, b"\x30\x00"))
        for blob in (im4p, img4):
            typ, pl = im4p_payload(blob)
            assert typ == "krnl", typ
            assert decompress(pl) == fake, name
    # 2) LZFSE via the lzfse command, if present
    tool = shutil.which("lzfse")
    if tool:
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a"), os.path.join(d, "b")
            open(a, "wb").write(fake)
            subprocess.run([tool, "-encode", "-i", a, "-o", b], check=True)
            enc = open(b, "rb").read()
            blob = _der_tlv(0x30, _der_tlv(0x16, b"IM4P") + _der_tlv(0x16, b"krnl") +
                            _der_tlv(0x16, b"x") + _der_tlv(0x04, enc))
            assert decompress(im4p_payload(blob)[1]) == fake
            print("selftest: lzfse path ok")
    # 3) an LZSS back-reference: literal 'A' then a 3+ byte match at N-F -> "AAAA"
    assert lzss_decompress(bytes([0b01, ord("A"), 0xee, 0xf0]), 4) == b"AAAA"
    assert describe(fake).endswith("FILESET")
    print("selftest: IMG4/IM4P unwrap, LZSS and plain payloads ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
    elif len(sys.argv) == 3:
        extract(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
