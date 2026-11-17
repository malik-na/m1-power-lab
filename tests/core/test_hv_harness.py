"""The hypervisor run scripts refuse the states that produced wrong readings.

Runs tools/hv-trace-kit/harness/test-lib.sh, which reproduces each mistake against stubs and
checks the scripts' answer: a process left on the port, a second console reader, a strict-mode
caller ended silently (2026-11-16/17); a used proxy handed out as fresh, a failed m1-hvboot
reported as success, a second probe not waited for, a probe's first line dropped, a reused tag
judged on the earlier run's file (2026-11-17).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools/hv-trace-kit/harness/test-lib.sh"


def test_harness_checks_all_pass():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert [line.split()[1] for line in r.stdout.splitlines() if line.startswith("ok ")] == [str(n) for n in range(1, 10)], r.stdout
