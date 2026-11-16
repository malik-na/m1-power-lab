#!/usr/bin/env python3
"""Add one alias to one machine's device tree inside an m1n1 second stage (boot.bin).

    dt-alias.py IN OUT --compat apple,j313 --alias sio --path /soc/sio@236400000

boot.bin is the m1n1 image followed by payloads that m1n1 walks in order from --payload-start:
raw device trees (each advanced by its totalsize) and gzip payloads. Only the tree whose root
compatible list holds --compat changes: one property goes into /aliases, its name is appended to
the strings block, and the tree is padded so the payloads after it keep their 8-byte alignment.
Everything else is copied byte for byte, and the result is re-parsed and compared before it is
written. Refuses if the alias exists, the path is not a node of that tree, or the chain does not
end exactly at the end of the file.
"""
import argparse, struct, sys, zlib

FDT_MAGIC = b"\xd0\x0d\xfe\xed"
BEGIN, END, PROP, NOP, FEND = 1, 2, 3, 4, 9


def payloads(b, start):
    """[(offset, kind, length)] in m1n1's walk order; the chain must end at len(b)."""
    out, p = [], start
    while p < len(b):
        if b[p:p + 4] == FDT_MAGIC:
            n = struct.unpack(">I", b[p + 4:p + 8])[0]
            out.append((p, "fdt", n))
        elif b[p:p + 2] == b"\x1f\x8b":
            d = zlib.decompressobj(16 + 15)
            d.decompress(b[p:])
            n = len(b) - p - len(d.unused_data)
            out.append((p, "gzip", n))
        else:
            sys.exit("STOP: unknown payload at %#x (%s); wrong --payload-start?" % (p, b[p:p + 8].hex()))
        p += n
    if p != len(b):
        sys.exit("STOP: payload chain ends at %#x, file is %#x" % (p, len(b)))
    return out


class Fdt:
    def __init__(self, blob):
        h = struct.unpack(">10I", blob[:40])
        assert h[0] == 0xd00dfeed and h[5] == 17, "not a v17 device tree"
        self.blob, self.h = blob, list(h)
        self.off_struct, self.off_strings, self.size_strings, self.size_struct = h[2], h[3], h[8], h[9]

    def name(self, off):
        s = self.blob[self.off_strings + off:]
        return s[:s.index(b"\0")].decode()

    def walk(self):
        """Yield (token, offset, path tuple, prop name, value) over the struct block."""
        b, p, path = self.blob, self.off_struct, []
        while True:
            t = struct.unpack(">I", b[p:p + 4])[0]
            at = p
            p += 4
            if t == BEGIN:
                e = b.index(b"\0", p)
                path.append(b[p:e].decode())
                p = (e + 1 + 3) & ~3
                yield BEGIN, at, tuple(path), None, None
            elif t == END:
                yield END, at, tuple(path), None, None
                path.pop()
            elif t == PROP:
                ln, no = struct.unpack(">II", b[p:p + 8])
                p += 8
                yield PROP, at, tuple(path), self.name(no), b[p:p + ln]
                p = (p + ln + 3) & ~3
            elif t == NOP:
                continue
            elif t == FEND:
                return
            else:
                raise ValueError("bad token %d at %#x" % (t, at))

    def props(self):
        return {(path, n): v for t, _, path, n, v in self.walk() if t == PROP}

    def nodes(self):
        return {"/" + "/".join(path[1:]) for t, _, path, _, _ in self.walk() if t == BEGIN}


def add_alias(blob, alias, value):
    f = Fdt(blob)
    props = f.props()
    root_compat = props[(("",), "compatible")]
    if (("", "aliases"), alias) in props:
        sys.exit("STOP: alias %r already present" % alias)
    if value not in f.nodes():
        sys.exit("STOP: %s is not a node of this tree" % value)
    after_name = next(at for t, at, path, _, _ in f.walk() if t == BEGIN and path == ("", "aliases"))
    after_name += 4 + ((len(b"aliases\0") + 3) & ~3)
    val = value.encode() + b"\0"
    tok = struct.pack(">III", PROP, len(val), f.size_strings) + val + b"\0" * (-len(val) % 4)
    s0, s1 = f.off_struct, f.off_struct + f.size_struct
    assert s1 <= f.off_strings and f.off_strings + f.size_strings <= f.h[1], "unexpected block order"
    struct_new = blob[s0:after_name] + tok + blob[after_name:s1]
    strings_new = blob[f.off_strings:f.off_strings + f.size_strings] + alias.encode() + b"\0"
    head = blob[40:s0]
    used = 40 + len(head) + len(struct_new) + (f.off_strings - s1) + len(strings_new)
    total = f.h[1] + ((used - f.h[1] + 7) & ~7) if used > f.h[1] else f.h[1]
    h = list(f.h)
    h[1], h[3], h[8], h[9] = total, f.off_strings + len(tok), len(strings_new), len(struct_new)
    out = struct.pack(">10I", *h) + head + struct_new + blob[s1:f.off_strings] + strings_new
    out += b"\0" * (total - len(out))
    return out, root_compat


def main():
    a = argparse.ArgumentParser()
    a.add_argument("inp"), a.add_argument("out")
    a.add_argument("--compat", required=True)
    a.add_argument("--alias", required=True)
    a.add_argument("--path", required=True)
    a.add_argument("--payload-start", type=lambda s: int(s, 0), default=0x400000)
    o = a.parse_args()
    b = open(o.inp, "rb").read()
    chain = payloads(b, o.payload_start)
    want = o.compat.encode()
    hits = [(p, n) for p, k, n in chain
            if k == "fdt" and want in Fdt(b[p:p + n]).props()[(("",), "compatible")].split(b"\0")]
    if len(hits) != 1:
        sys.exit("STOP: %d trees with root compatible %s" % (len(hits), o.compat))
    p, n = hits[0]
    new, _ = add_alias(b[p:p + n], o.alias, o.path)
    out = b[:p] + new + b[p + n:]
    delta = len(new) - n

    chain2 = payloads(out, o.payload_start)
    assert len(chain2) == len(chain) and delta % 8 == 0
    for (p1, k1, n1), (p2, k2, n2) in zip(chain, chain2):
        if p1 == p:
            continue
        assert k1 == k2 and n1 == n2 and b[p1:p1 + n1] == out[p2:p2 + n2], "payload at %#x changed" % p1
    before, after = Fdt(b[p:p + n]).props(), Fdt(new).props()
    extra = set(after) - set(before)
    assert extra == {(("", "aliases"), o.alias)}, extra
    assert all(after[k] == v for k, v in before.items()), "an existing property changed"
    assert after[(("", "aliases"), o.alias)] == o.path.encode() + b"\0"
    assert out[:p] == b[:p]

    open(o.out, "wb").write(out)
    print("tree %s at %#x: %d -> %d bytes (+%d); %d payloads after it shifted by %d, unchanged"
          % (o.compat, p, n, len(new), delta, sum(1 for q, _, _ in chain if q > p), delta))
    print("added /aliases/%s = %s; %d existing properties identical" % (o.alias, o.path, len(before)))


if __name__ == "__main__":
    main()
