#!/usr/bin/env python3
"""Serve one explicitly owned native candidate helper; never auto-started."""

from __future__ import annotations

import argparse
from functools import partial
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event

from m1lab.adapters.helper_supervisor import HelperSupervisor, HelperSupervisorError
from m1lab.adapters.native_candidate import NativeCandidateBackend


_CONFIG_KEYS = frozenset({
    "artifact_root", "usb_topology", "expected_proxy_serial_sha256",
    "python_path", "python_sha256", "boot_script_path",
    "boot_script_sha256", "proxyclient_path", "proxyclient_sha256",
})
_OPTIONAL_CONFIG_KEYS = frozenset({"optical_calibration"})
_PATH_KEYS = frozenset({
    "artifact_root", "python_path", "boot_script_path", "proxyclient_path",
})


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate native helper config key: {key}")
        result[key] = value
    return result


def _read_config(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as source:
        config = json.load(source, object_pairs_hook=_unique_object)
    if (not isinstance(config, dict) or not _CONFIG_KEYS <= set(config)
            or not set(config) <= _CONFIG_KEYS | _OPTIONAL_CONFIG_KEYS):
        raise ValueError("native helper config has missing or unknown keys")
    if any(not isinstance(config[key], str) or not config[key] for key in _CONFIG_KEYS):
        raise ValueError("native helper config values must be nonempty strings")
    if ("optical_calibration" in config
            and type(config["optical_calibration"]) is not bool):
        raise ValueError("native helper optical_calibration must be a boolean")
    for key in _PATH_KEYS:
        value = Path(config[key])
        if not value.is_absolute():
            raise ValueError(f"native helper {key} must be absolute")
        config[key] = value
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--owner-pid", type=int, required=True)
    args = parser.parse_args(argv)
    if args.owner_pid <= 0 or args.owner_pid != os.getppid():
        print("native helper: owner PID must be the invoking parent", file=sys.stderr)
        return 1

    owner_pidfd = None
    try:
        owner_pidfd = os.pidfd_open(args.owner_pid)
        if os.getppid() != args.owner_pid:
            raise HelperSupervisorError("qualification owner changed during startup")
        config = _read_config(args.config)
        config["diagnostic_dir"] = args.state_dir.absolute() / "boot-logs"
        # Construction validates fixed parameters but never enters a backend.
        NativeCandidateBackend(**config)
        backend_factory = partial(NativeCandidateBackend, **config)
        supervisor = HelperSupervisor(
            args.state_dir, backend_factory,
            startup_seconds=12, request_seconds=480, cleanup_seconds=3,
        )
        stopped = Event()

        def request_stop(_signum: int, _frame: object) -> None:
            stopped.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        supervisor.run(stopped, owner_pidfd=owner_pidfd)
    except (OSError, ValueError, HelperSupervisorError) as exc:
        print(f"native helper: {exc}", file=sys.stderr)
        return 1
    finally:
        if owner_pidfd is not None:
            os.close(owner_pidfd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
