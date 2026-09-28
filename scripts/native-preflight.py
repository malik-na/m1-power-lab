#!/usr/bin/env python3
"""Check native helper prerequisites without opening a target or changing state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import stat

from m1lab.adapters.native_candidate import (
    NativeCandidateBackend, NativeCandidateError, _TOPOLOGY, _TTY,
)


# Use the launcher's exact JSON contract, including duplicate-key rejection.
_read_config = runpy.run_path(str(Path(__file__).with_name("serve-native-helper.py")))["_read_config"]


def _access(path: Path, mode: int) -> bool:
    return os.access(path, mode, effective_ids=True)


def _device_status(path: Path) -> dict[str, object]:
    result: dict[str, object] = {"path": str(path), "accessible": False}
    try:
        info = path.lstat()
    except OSError:
        result["present"] = False
        return result
    result.update({
        "present": True,
        "character_device": stat.S_ISCHR(info.st_mode),
        "symlink": stat.S_ISLNK(info.st_mode),
        "mode": stat.filemode(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
        "readable": _access(path, os.R_OK), "writable": _access(path, os.W_OK),
    })
    result["accessible"] = bool(
        result["character_device"] and not result["symlink"]
        and result["readable"] and result["writable"]
    )
    return result


def preflight(
    config_path: Path, *, sysfs_root: Path = Path("/sys/class/tty"),
    device_root: Path = Path("/dev"), helper_socket: Path | None = None,
) -> dict[str, object]:
    """Inspect local metadata and pinned files; never enter a hardware backend."""
    blockers: list[dict[str, str]] = []
    report: dict[str, object] = {
        "schema": "m1lab.native-preflight.v1", "status": "blocked",
        "config": {"path": str(config_path), "valid": False},
        "blockers": blockers,
        "limitations": [
            "No target serial device is opened and no helper request is sent.",
            "Access checks do not establish exclusive ownership or proxy RPC readiness.",
            "This does not validate a launch bundle, approve a run, or qualify hardware.",
        ],
    }

    def block(code: str, message: str, action: str) -> None:
        blockers.append({"code": code, "message": message, "action": action})

    if helper_socket is not None:
        socket_report: dict[str, object] = {
            "path": str(helper_socket), "listening": "not_probed",
        }
        try:
            info = helper_socket.lstat()
            socket_report.update({
                "present": True, "socket": stat.S_ISSOCK(info.st_mode),
                "owned_by_current_user": info.st_uid == os.geteuid(),
                "writable": _access(helper_socket, os.W_OK),
            })
        except OSError:
            socket_report["present"] = False
        report["helper_socket"] = socket_report

    try:
        config = _read_config(config_path)
        backend = NativeCandidateBackend(
            **config, diagnostic_dir=config_path.absolute().parent / "boot-logs",
            sysfs_root=sysfs_root, device_root=device_root,
        )
    except (OSError, ValueError, UnicodeError):
        block(
            "config_invalid", "Native helper configuration is missing, unreadable, or invalid.",
            "Provide --config with the private JSON accepted by serve-native-helper.py; "
            "check its nine required string fields, absolute paths and lowercase SHA-256 pins.",
        )
        return report
    report["config"]["valid"] = True

    tools = {
        name: {"path": str(config[name]), "present": config[name].exists()}
        for name in ("python_path", "boot_script_path", "proxyclient_path")
    }
    tools["pins_match"] = False
    try:
        # Exactly the validation performed by the real backend before serial open.
        backend._verify_tools()
        tools["pins_match"] = True
    except (OSError, NativeCandidateError):
        block(
            "tool_pins_invalid", "A fixed boot tool or proxyclient tree is unavailable or differs from its pin.",
            "Restore the reviewed interpreter, linux.py and proxyclient tree, or review and "
            "explicitly update their private configuration pins; symlinks are refused.",
        )
    tools["python_executable"] = _access(backend.python_path, os.X_OK)
    if not tools["python_executable"]:
        block("python_not_executable", "The configured interpreter is not executable by this process.",
              "Select the reviewed executable interpreter file and check its execute permission.")
    report["tools"] = tools

    root = backend.artifact_root
    try:
        real_directory = stat.S_ISDIR(root.lstat().st_mode)
    except OSError:
        real_directory = False
    accessible = real_directory and _access(root, os.R_OK | os.X_OK)
    report["artifact_root"] = {
        "path": str(root), "real_directory": real_directory, "accessible": accessible,
        "bundle_validated": False,
    }
    if not accessible:
        block("artifact_root_unavailable", "The artifact root is not an accessible real directory.",
              "Point artifact_root at the existing coordinator artifact store and check directory access.")

    usb: dict[str, object] = {
        "configured_topology": backend.usb_topology,
        "expected_serial_sha256": backend.expected_proxy_serial_sha256,
        "vendor_id": "1209", "product_id": "316d", "interface_number": "00",
        "matches": [],
    }
    report["usb"] = usb
    try:
        # Discover port names only. The backend remains the authority for interface,
        # VID/PID, serial hash, device existence, bounds and per-port uniqueness.
        entries = list(sysfs_root.glob("ttyACM*"))
        if len(entries) > 64:
            raise NativeCandidateError("too many candidate tty entries")
        topologies: set[str] = set()
        for entry in entries:
            if not _TTY.fullmatch(entry.name):
                continue
            try:
                topology = (entry / "device").resolve(strict=True).parent.name
            except OSError:
                continue
            if _TOPOLOGY.fullmatch(topology):
                topologies.add(topology)
        for topology in sorted(topologies):
            candidate = NativeCandidateBackend(
                **{**config, "usb_topology": topology},
                diagnostic_dir=backend.diagnostic_dir,
                sysfs_root=sysfs_root, device_root=device_root,
            )
            match = candidate._proxy_presence()
            if match is not None:
                usb["matches"].append({
                    "topology": topology, "interface_number": "00",
                    "serial_sha256": backend.expected_proxy_serial_sha256,
                    "device": _device_status(match[0]),
                })
    except (OSError, UnicodeError, NativeCandidateError):
        block("usb_scan_invalid", "USB metadata is unreadable, over its bound, or ambiguous at one port.",
              "Check the ttyACM sysfs entries and keep one matching proxy interface 00 per port.")
    matches = usb["matches"]
    if not matches:
        block("proxy_not_found", "No matching m1n1 proxy interface 00 with a device node was found.",
              "Check the target's proxy mode, cable and ttyACM device-node creation; verify the private serial pin.")
    elif len(matches) != 1:
        block("proxy_ambiguous", "More than one port matches the pinned proxy identity.",
              "Resolve duplicate matching USB identities before selecting a target; no device was selected.")
    else:
        match = matches[0]
        if match["topology"] != backend.usb_topology:
            block("topology_mismatch", "The pinned proxy is attached at a different USB topology.",
                  f"Reconnect it at {backend.usb_topology}, or review and set usb_topology "
                  f"to {match['topology']} in the private configuration before starting a helper.")
        if not match["device"]["accessible"]:
            block("device_inaccessible", "The matching tty is not a readable and writable character device for this process.",
                  "Check the reported device owner/group and udev access policy with the device administrator; "
                  "start a fresh login/session after any group change, then rerun this preflight.")
    report["status"] = "blocked" if blockers else "ready"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--helper-socket", type=Path, help="Optional socket metadata only; no connection or request")
    args = parser.parse_args(argv)
    report = preflight(args.config, helper_socket=args.helper_socket)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
