#!/usr/bin/env python3
"""One bounded physical m1n1 observation through the local helper IPC.

This is an inspect-only harness probe. It performs no coordinator, model,
dispatch, boot transition, recovery, or scientific investigation action.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

from m1lab.adapters.helper_server import (
    HelperHardwareAdapter,
    start_exclusive_helper,
)
from m1lab.adapters.m1n1_observer import M1N1Observer


def _serve_one(
    connection,
    lock_path: str,
    socket_path: str,
    device: str,
    topology: str,
    serial_digest: str,
) -> None:
    observer = None
    owner = server = None
    try:
        def backend_factory():
            nonlocal observer
            observer = M1N1Observer(
                Path(device), expected_usb_topology=topology,
                expected_serial_sha256=serial_digest,
            )
            return observer.__enter__()

        owner, server = start_exclusive_helper(
            Path(lock_path), Path(socket_path), backend_factory,
        )
        connection.send({"event": "ready"})
        server.serve_once()
        identity = observer.last_identity if observer is not None else None
        connection.send({
            "event": "done",
            "proxy_identity": None if identity is None else {
                "chip_id": identity.chip_id,
                "base": identity.base,
                "bootargs_address": identity.bootargs_address,
            },
        })
    except Exception as exc:
        connection.send({"event": "error", "error_type": type(exc).__name__})
    finally:
        try:
            try:
                if server is not None:
                    server.close()
            finally:
                try:
                    if observer is not None:
                        observer.__exit__(None, None, None)
                finally:
                    if owner is not None:
                        owner.__exit__(None, None, None)
        finally:
            connection.close()


def _receive(connection, deadline: float) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not connection.poll(remaining):
        raise TimeoutError("probe total deadline expired")
    try:
        return connection.recv()
    except EOFError as exc:
        raise RuntimeError("helper process ended without evidence") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=Path, required=True)
    parser.add_argument("--usb-topology", default="1-1")
    parser.add_argument("--expected-serial-sha256", required=True)
    parser.add_argument("--max-total-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    if not 6.0 <= args.max_total_seconds <= 15.0:
        parser.error("--max-total-seconds must be between 6 and 15")
    # Validate typed identity arguments before constructing a subprocess.
    M1N1Observer(
        args.device, expected_usb_topology=args.usb_topology,
        expected_serial_sha256=args.expected_serial_sha256,
    )

    deadline = time.monotonic() + args.max_total_seconds
    output = {
        "schema_version": 1,
        "source": "m1n1-v1.6.1-fixed-read-only-proxy-observation",
        "device": str(args.device),
        "usb_topology": args.usb_topology,
        "usb_vid_pid": "1209:316d",
        "usb_interface": "00",
        "serial_sha256": args.expected_serial_sha256,
        "available": False,
        "qualified": False,
        "mode": "disconnected",
        "boot_epoch": None,
        "capabilities": [],
        "proxy_identity": None,
        "limitations": ["no dispatch qualification", "no native-result qualification", "no boot-epoch qualification", "no recovery qualification"],
    }
    with TemporaryDirectory(prefix="m1n1-probe-") as directory:
        lock_path = str(Path(directory) / "owner.lock")
        socket_path = str(Path(directory) / "helper.sock")
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(
            target=_serve_one,
            args=(child, lock_path, socket_path, str(args.device), args.usb_topology, args.expected_serial_sha256),
        )
        process.start()
        child.close()
        try:
            ready = _receive(parent, deadline)
            if ready.get("event") != "ready":
                raise RuntimeError(f"helper startup failed: {ready.get('error_type', 'unknown')}")
            snapshot = HelperHardwareAdapter(Path(socket_path)).inspect()
            output.update(
                available=snapshot.available,
                qualified=snapshot.qualified,
                mode=snapshot.mode,
                boot_epoch=snapshot.boot_epoch,
                capabilities=[capability.name for capability in snapshot.capabilities],
                observed_at=snapshot.observed_at.isoformat(),
                message=snapshot.message,
            )
            done = _receive(parent, deadline)
            if done.get("event") != "done":
                raise RuntimeError(f"helper observation failed: {done.get('error_type', 'unknown')}")
            if snapshot.available:
                output["proxy_identity"] = done["proxy_identity"]
        except (RuntimeError, TimeoutError) as exc:
            output["error"] = str(exc)
        finally:
            parent.close()
            process.join(timeout=max(0.0, deadline - time.monotonic()))
            forced_termination = process.is_alive()
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=1.0)
            if forced_termination or process.exitcode != 0:
                output.update(
                    available=False,
                    qualified=False,
                    mode="disconnected",
                    boot_epoch=None,
                    capabilities=[],
                    proxy_identity=None,
                    error="helper cleanup did not exit normally",
                )
    print(json.dumps(output, sort_keys=True))
    return 0 if output["available"] and output["proxy_identity"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
