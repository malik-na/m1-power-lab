#!/usr/bin/env python3
"""Serve a persistent inspect-only M1 helper in a separate process tree."""

from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path
import signal
import sys
from threading import Event

from m1lab.adapters.helper_supervisor import HelperSupervisor, HelperSupervisorError
from m1lab.adapters.m1n1_observer import M1N1Observer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--device", type=Path, required=True)
    parser.add_argument("--usb-topology", required=True)
    parser.add_argument("--expected-serial-sha256", required=True)
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
    try:
        supervisor.run(stopped)
    except HelperSupervisorError as exc:
        print(f"helper supervisor failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
