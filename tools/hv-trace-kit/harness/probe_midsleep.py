# hv script: define probe_midsleep() for the hypervisor shell. Reads the display power domains
# (PMGR PS words: bits 3:0 target, 7:4 actual) and, for each coprocessor IRQ line, the AIC mask,
# raw hardware state and software-set bits. Never touches AIC_EVENT (read-to-ack).
PS_WORDS = {0x23b700360: "disp0_fe", 0x23b700368: "dispext_fe", 0x23b700378: "dispext_cpu0",
            0x23b710018: "disp0_cpu0", 0x23b700350: "rmx", 0x23b700258: "spi3"}
IRQS = {"dcp": [427, 428, 429, 430], "dcpext": [466, 467, 468, 469], "smc": [400, 401, 402, 403],
        "sep": [253, 254, 255, 256], "ans": [583, 584, 585, 586, 590], "aop": [285, 286, 287, 288]}
AIC = 0x23b100000

def probe_midsleep(tag=""):
    print(f"[probe] {tag}")
    for a, n in PS_WORDS.items():
        v = p.read32(a)
        print(f"[probe] PS {n:13s} {a:#x} = {v:#010x}  target {v & 0xf:#x} actual {(v >> 4) & 0xf:#x}")
    for name, lines in IRQS.items():
        out = []
        for irq in lines:
            w, b = irq >> 5, 1 << (irq & 31)
            masked = bool(p.read32(AIC + 0x4100 + 4 * w) & b)
            hw = bool(p.read32(AIC + 0x4200 + 4 * w) & b)
            sw = bool(p.read32(AIC + 0x4000 + 4 * w) & b)
            out.append(f"{irq}:{'M' if masked else 'u'}{'H' if hw else '-'}{'S' if sw else '-'}")
        print(f"[probe] AIC {name:6s} " + " ".join(out) + "   (M=masked u=unmasked H=hw pending S=sw set)")
print("[probe] probe_midsleep() defined")
