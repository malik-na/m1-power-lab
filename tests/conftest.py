from __future__ import annotations

import pytest

from m1lab.core.coordinator import CoreApp
from m1lab.paths import AppPaths


@pytest.fixture
def core(tmp_path):
    app = CoreApp.open(AppPaths(tmp_path / "data"))
    try:
        yield app
    finally:
        app.close()
