"""Read-only Linux host availability observations.

The sampler reports what the host exposes through sysfs and the filesystem.
It deliberately does not infer that sleep inhibition, lid behaviour, or AC-loss
handling have been qualified merely because a value can be read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from typing import Iterable


@dataclass(frozen=True, slots=True)
class HostSnapshot:
    observed_at: datetime
    power_source: str
    battery_percent: float | None
    maximum_temperature_c: float | None
    thermal_state: str
    disk_free_bytes: int
    disk_total_bytes: int
    lab_mode: str = "unqualified"

    def as_view(self) -> dict[str, str]:
        if self.battery_percent is None:
            battery = ""
        else:
            battery = f" · battery {self.battery_percent:.0f}%"
        temperature = (
            "unknown"
            if self.maximum_temperature_c is None
            else f"{self.maximum_temperature_c:.1f} °C ({self.thermal_state})"
        )
        return {
            "state": self.thermal_state if self.thermal_state != "unknown" else "observed",
            "power": f"{self.power_source}{battery}",
            "thermal": temperature,
            "lab_mode": self.lab_mode,
            "disk": f"{_human_bytes(self.disk_free_bytes)} free",
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class HostAdmissionPolicy:
    require_ac: bool = True
    minimum_free_bytes: int = 5 * 1024**3
    maximum_temperature_c: float = 90.0

    def blockers(self, snapshot: HostSnapshot) -> list[str]:
        blockers: list[str] = []
        if self.require_ac and snapshot.power_source != "ac":
            blockers.append("host AC power is not confirmed")
        if snapshot.disk_free_bytes < self.minimum_free_bytes:
            blockers.append(
                f"host disk has less than {_human_bytes(self.minimum_free_bytes)} free"
            )
        if snapshot.maximum_temperature_c is None:
            blockers.append("host thermal state is unavailable")
        elif snapshot.maximum_temperature_c >= self.maximum_temperature_c:
            blockers.append(
                f"host temperature is at least {self.maximum_temperature_c:.0f} °C"
            )
        if snapshot.lab_mode == "sleep/lid inhibitor requested but not confirmed":
            blockers.append("configured sleep/lid inhibitor is not confirmed")
        return blockers


class LinuxHostMonitor:
    def __init__(
        self,
        data_path: Path,
        *,
        power_supply_root: Path = Path("/sys/class/power_supply"),
        thermal_root: Path = Path("/sys/class/thermal"),
    ) -> None:
        self._data_path = data_path
        self._power_supply_root = power_supply_root
        self._thermal_root = thermal_root

    def sample(self) -> HostSnapshot:
        power_source, battery_percent = _power(self._power_supply_root)
        maximum_temperature = _maximum_temperature(self._thermal_root)
        disk = shutil.disk_usage(self._data_path)
        return HostSnapshot(
            observed_at=datetime.now(timezone.utc),
            power_source=power_source,
            battery_percent=battery_percent,
            maximum_temperature_c=maximum_temperature,
            thermal_state=_thermal_state(maximum_temperature),
            disk_free_bytes=disk.free,
            disk_total_bytes=disk.total,
            lab_mode=_lab_mode(),
        )


def _lab_mode() -> str:
    configured = os.environ.get("M1LAB_INHIBIT_SLEEP", "0")
    held = os.environ.get("M1LAB_SLEEP_LID_INHIBITOR_HELD") == "1"
    if configured == "1" and held:
        return "sleep/lid inhibitor held; host behavior unqualified"
    if configured == "1":
        return "sleep/lid inhibitor requested but not confirmed"
    return "sleep/lid inhibitor not requested"


def _power(root: Path) -> tuple[str, float | None]:
    mains_online: list[bool] = []
    battery_percentages: list[float] = []
    for supply in _directories(root):
        supply_type = _read(supply / "type").lower()
        if supply_type in {"mains", "usb", "usb_c", "usb_pd"}:
            value = _read(supply / "online")
            if value in {"0", "1"}:
                mains_online.append(value == "1")
        elif supply_type == "battery":
            value = _float(_read(supply / "capacity"))
            if value is not None:
                battery_percentages.append(value)
    battery = (
        sum(battery_percentages) / len(battery_percentages)
        if battery_percentages
        else None
    )
    if any(mains_online):
        return "ac", battery
    if mains_online or battery_percentages:
        return "battery", battery
    return "unknown", battery


def _maximum_temperature(root: Path) -> float | None:
    values: list[float] = []
    for zone in _directories(root, "thermal_zone*"):
        raw = _float(_read(zone / "temp"))
        if raw is None:
            continue
        temperature = raw / 1000.0 if abs(raw) >= 1000 else raw
        if -40 <= temperature <= 200:
            values.append(temperature)
    return max(values) if values else None


def _thermal_state(temperature: float | None) -> str:
    if temperature is None:
        return "unknown"
    if temperature >= 90:
        return "critical"
    if temperature >= 80:
        return "hot"
    if temperature >= 70:
        return "warm"
    return "normal"


def _directories(root: Path, pattern: str = "*") -> Iterable[Path]:
    try:
        return tuple(path for path in root.glob(pattern) if path.is_dir())
    except OSError:
        return ()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _human_bytes(value: int) -> str:
    amount = float(max(0, value))
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or suffix == "TiB":
            return f"{amount:.1f} {suffix}"
        amount /= 1024
    raise AssertionError("unreachable")
