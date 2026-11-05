import pytest

from m1lab.live import agent


@pytest.fixture(autouse=True)
def lab_idle(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> None:
    """Keep the host's own /proc, /sys and maclab state out of agent tests:
    by default the lab is idle. Tests that exercise lab detection override it."""
    empty = tmp_path_factory.mktemp("maclab")
    monkeypatch.setattr(agent, "MACLAB_DIR", empty)
    monkeypatch.setattr(agent, "LAB_AGENT_CGROUP", empty / "no-cgroup")
    real_read = agent.read
    idle = {"/proc/cmdline": "root=/dev/test", "/sys/power/pm_test": "[none] core processors platform devices freezer"}
    monkeypatch.setattr(agent, "read", lambda path, default=None: idle.get(str(path), real_read(path, default)))
