#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Clear the Sera PMU boot-error / panic counters after the post-mortem is saved.

This is the ONE write in this kit. It is the same single SPMI write that
upstream m1n1 makes on every run_guest.py / m1n1.setup session
(PMU(u).reset_panic_counter(): write8(slave, leg_scrpad + 2, 0),
proxyclient/m1n1/hw/pmu.py:28-31 at 70757dc). The kit avoids that path during
the experiment so the counters survive for pmu_postmortem.py; run this at the
very end so iBoot does not keep counting the forced reboots as boot failures.

    M1N1DEVICE=/dev/ttyACM0 python3 pmu_clear_counters.py --m1n1 ~/m1n1 --out RUN/ --yes

Without --yes it only prints the current value.
"""

import argparse
import pathlib
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--m1n1", required=True, type=pathlib.Path, help="m1n1 checkout (same commit as the target)")
ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("."))
ap.add_argument("--yes", action="store_true", help="really write 0 to leg_scrpad+2")
args = ap.parse_args()

sys.path.insert(0, str(args.m1n1 / "proxyclient"))
from m1n1.proxy import UartInterface, M1N1Proxy          # noqa: E402
from m1n1.proxyutils import ProxyUtils, bootstrap_port   # noqa: E402
from m1n1.hw.pmu import PMU                              # noqa: E402

iface = UartInterface()
p = M1N1Proxy(iface, debug=False)
bootstrap_port(iface, p)
u = ProxyUtils(p)

chip = u.adt["/chosen"].chip_id
if chip != 0x8103:
    sys.exit(f"chip id {chip:#x} is not t8103; refusing")

pmu = PMU(u)
if not (pmu.primary and pmu.bus_type == "spmi"):
    sys.exit(f"primary PMU at {pmu.adt_path} is not an SPMI PMU; refusing")
leg = pmu.node.info_leg__scrpad[0]
slave = pmu.reg


def show(tag):
    v = pmu.spmi.read8(slave, leg + 2)
    s = f"{tag}: leg_scrpad {leg:#06x}+2 = {v:#04x} (boot_error_count {v & 0xf}, panic_count {v >> 4})"
    print(s)
    return s


lines = [time.strftime("%Y-%m-%d %H:%M:%S"), show("before")]
if args.yes:
    pmu.reset_panic_counter()
    lines.append("wrote 0 via PMU.reset_panic_counter()")
    lines.append(show("after"))
else:
    lines.append("dry run: nothing written (add --yes to clear)")
    print(lines[-1])
args.out.mkdir(parents=True, exist_ok=True)
f = args.out / f"clear-counters-{time.strftime('%H%M%S')}.txt"
f.write_text("\n".join(lines) + "\n")
print(f"saved {f}")
