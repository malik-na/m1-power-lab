#!/usr/bin/env python3
"""Collect a redacted, read-only Linux lab-host inventory as JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


SYS = Path("/sys")
DEV = Path("/dev")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return None


def command_version(command: str, args: list[str]) -> dict[str, object]:
    executable = shutil.which(command)
    if executable is None:
        return {"available": False, "version": None}
    try:
        result = subprocess.run(
            [executable, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
        output = (result.stdout or result.stderr).splitlines()
        return {"available": True, "version": output[0].strip() if output else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version": None}


def distro() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (read_text(Path("/etc/os-release")) or "").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"NAME", "ID", "VERSION_ID", "PRETTY_NAME"}:
            values[key.lower()] = value.strip('"')
    return values


def cpu_model() -> str | None:
    for line in (read_text(Path("/proc/cpuinfo")) or "").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in {"model name", "hardware", "model"}:
            if value.strip():
                return value.strip()
    return None


def dmi_facts() -> dict[str, str | None]:
    root = SYS / "class/dmi/id"
    return {
        "manufacturer": read_text(root / "sys_vendor"),
        "product_name": read_text(root / "product_name"),
        "product_version": read_text(root / "product_version"),
        "board_name": read_text(root / "board_name"),
        "bios_vendor": read_text(root / "bios_vendor"),
        "bios_version": read_text(root / "bios_version"),
        "bios_date": read_text(root / "bios_date"),
    }


def usb_devices() -> list[dict[str, object]]:
    devices: list[dict[str, object]] = []
    root = SYS / "bus/usb/devices"
    try:
        entries = sorted(root.iterdir()) if root.is_dir() else []
    except OSError:
        entries = []
    for entry in entries:
        # USB interface names contain a colon and are not physical devices.
        if ":" in entry.name:
            continue
        vendor = read_text(entry / "idVendor")
        product_id = read_text(entry / "idProduct")
        bus = read_text(entry / "busnum")
        device_number = read_text(entry / "devnum")
        if vendor is None or product_id is None:
            continue
        device_path = None
        permissions = None
        if bus and device_number and bus.isdigit() and device_number.isdigit():
            candidate = DEV / "bus/usb" / f"{int(bus):03d}" / f"{int(device_number):03d}"
            device_path = str(candidate)
            try:
                info = candidate.stat()
                permissions = {
                    "mode_octal": oct(info.st_mode & 0o777),
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                }
            except OSError:
                pass
        driver_path = entry / "driver"
        try:
            driver = driver_path.resolve(strict=True).name
        except OSError:
            driver = None
        devices.append(
            {
                "sysfs_port_path": entry.name,
                "vendor_id": vendor,
                "product_id": product_id,
                "manufacturer": read_text(entry / "manufacturer"),
                "product": read_text(entry / "product"),
                "bus_number": int(bus) if bus and bus.isdigit() else None,
                "device_number": int(device_number)
                if device_number and device_number.isdigit()
                else None,
                "speed_mbps": read_text(entry / "speed"),
                "authorized": read_text(entry / "authorized"),
                "driver": driver,
                "device_node": device_path,
                "device_permissions": permissions,
                "serial_number": "omitted",
            }
        )
    return devices


def m1n1_repository(path: Path | None) -> dict[str, str | None]:
    if path is None:
        return {"commit": None, "state": "not supplied"}
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
        return {
            "commit": result.stdout.strip(),
            "state": "commit recorded; working tree not inspected",
        }
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "state": "unavailable"}


def collect(repo: Path | None) -> dict[str, object]:
    model = read_text(SYS / "firmware/devicetree/base/model")
    try:
        memory = next(
            int(line.split()[1]) * 1024
            for line in (read_text(Path("/proc/meminfo")) or "").splitlines()
            if line.startswith("MemTotal:")
        )
    except (StopIteration, ValueError, IndexError):
        memory = None
    return {
        "format": "m1lab-host-inventory-v1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "collection": {
            "read_only": True,
            "usb_devices_opened": False,
            "serial_numbers_collected": False,
            "limitations": [
                "Does not establish cable identity, physical port mapping, recovery, or target mode qualification.",
                "USB device and permission observations apply only to this Linux host at collection time.",
            ],
        },
        "host": {
            "device_tree_model": model,
            "dmi": dmi_facts(),
            "cpu_model": cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "memory_total_bytes": memory,
            "distribution": distro(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "tools": {
                "git": command_version("git", ["--version"]),
                "gcc": command_version("gcc", ["--version"]),
                "clang": command_version("clang", ["--version"]),
                "lsusb": {"available": shutil.which("lsusb") is not None},
                "m1n1_executable_available": shutil.which("m1n1") is not None,
            },
            "m1n1_repository": m1n1_repository(repo),
        },
        "usb_devices": usb_devices(),
        "target_qualification": {
            "proxy": "unqualified",
            "hypervisor": "unqualified",
            "native": "unqualified",
            "physical_recovery": "unqualified",
            "owner_attendance": "required for physical connection and recovery work",
        },
        "manual_observations_required": [
            "ThinkPad-to-Mac cable and adapter identity",
            "Physical host and target port mapping",
            "Host and target m1n1 versions and compatibility",
            "Software reboot, independent reset, and firmware recovery path",
            "Per-mode capability and owner-attendance matrix",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m1n1-repo", type=Path, help="optional host m1n1 source checkout")
    parser.add_argument("--output", type=Path, help="write JSON to this path (mode 0600)")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        raise SystemExit("host inventory collection requires Linux")
    document = json.dumps(collect(args.m1n1_repo), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(document, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(document)


if __name__ == "__main__":
    main()
