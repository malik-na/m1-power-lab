"""The hypervisor run scripts refuse a run with stale processes on the Mac's ports.

Runs tools/hv-trace-kit/harness/test-lib.sh, which reproduces the 2026-11-16 mistakes (a process
left on the port, a second console reader) and checks that each is refused.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools/hv-trace-kit/harness/test-lib.sh"


def test_harness_refuses_stale_port_holders_and_second_reader():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("ok ") == 3, r.stdout
