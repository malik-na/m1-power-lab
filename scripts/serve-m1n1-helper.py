#!/usr/bin/env python3
"""Serve a persistent inspect-only M1 helper in a separate process tree."""

from __future__ import annotations

import argparse
from functools import partial
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from threading import Event

from m1lab.adapters.helper_supervisor import HelperSupervisor, HelperSupervisorError
from m1lab.adapters.m1n1_observer import M1N1Observer


_COORDINATOR_SERVICE = "m1-power-lab.service"
_SYSTEMCTL_SHOW = (
    "systemctl", "show", _COORDINATOR_SERVICE,
    "--property=ActiveState", "--property=MainPID", "--property=InvocationID",
    "--no-pager",
)


def _coordinator_generation() -> tuple[int, str]:
    """Read the fixed coordinator unit's active process generation."""

    try:
        result = subprocess.run(
            _SYSTEMCTL_SHOW, check=True, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise HelperSupervisorError("coordinator service generation query failed") from exc
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, separator, value = line.partition("=")
        if not separator or name in fields or name not in {"ActiveState", "MainPID", "InvocationID"}:
            raise HelperSupervisorError("coordinator service generation is invalid")
        fields[name] = value
    if set(fields) != {"ActiveState", "MainPID", "InvocationID"}:
        raise HelperSupervisorError("coordinator service generation is incomplete")
    if (fields["ActiveState"] != "active" or not fields["MainPID"].isdigit()
            or not re.fullmatch(r"[0-9a-fA-F]{32}", fields["InvocationID"])):
        raise HelperSupervisorError("coordinator service is not an active process generation")
    pid = int(fields["MainPID"])
    if pid <= 0:
        raise HelperSupervisorError("coordinator service has no main process")
    return pid, fields["InvocationID"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--device", type=Path, required=True)
    parser.add_argument("--usb-topology", required=True)
    parser.add_argument("--expected-serial-sha256", required=True)
    parser.add_argument("--require-coordinator-service", action="store_true")
    args = parser.parse_args(argv)

    # Only the fixed, in-package observer can be constructed by this command.
    M1N1Observer(
        args.device,
        expected_usb_topology=args.usb_topology,
        expected_serial_sha256=args.expected_serial_sha256,
    )
    backend_factory = partial(
        M1N1Observer,
        args.device,
        expected_usb_topology=args.usb_topology,
        expected_serial_sha256=args.expected_serial_sha256,
    )
    supervisor = HelperSupervisor(args.state_dir, backend_factory)
    stopped = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    owner_pidfd = None
    try:
        if args.require_coordinator_service:
            generation = _coordinator_generation()
            try:
                owner_pidfd = os.pidfd_open(generation[0])
            except (AttributeError, OSError) as exc:
                raise HelperSupervisorError("could not open coordinator process lease") from exc
            if _coordinator_generation() != generation:
                raise HelperSupervisorError("coordinator service generation changed during startup")
        supervisor.run(stopped, owner_pidfd=owner_pidfd)
    except HelperSupervisorError as exc:
        print(f"helper supervisor failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if owner_pidfd is not None:
            os.close(owner_pidfd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
