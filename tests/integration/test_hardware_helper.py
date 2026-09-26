"""Real local IPC with a fixed synthetic backend; no devices or live qualification."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import struct
from tempfile import TemporaryDirectory
from threading import Event, Thread

import pytest

from m1lab.adapters.hardware import (
    MAX_CAPTURE_BYTES,
    HardwareCapability,
    HardwareDispatch,
    HardwareError,
    HardwareResult,
    HardwareResultStatus,
    InspectRegister,
    TargetSnapshot,
)
from m1lab.adapters.helper_protocol import MAX_HELPER_REQUEST_BYTES, encode_request
from m1lab.adapters.helper_server import (
    HelperHardwareAdapter,
    HelperOwnerError,
    close_exclusive_helper,
    start_exclusive_helper,
)


class SyntheticBackend:
    """Fixed register fixture, with one explicit post-entry failure switch."""

    def __init__(self):
        self.calls = []
        self.fail_after_entry = False
        self.snapshot = TargetSnapshot(
            adapter="synthetic-test-only",
            available=True,
            # Exercise the gate's accepted branch, not a physical qualification claim.
            qualified=True,
            mode="synthetic",
            target_id="synthetic-target",
            boot_epoch="synthetic-boot-1",
            configuration_digest="a" * 64,
            capabilities=(HardwareCapability("inspect_register", 1, False, 4),),
            observed_at=datetime.now(timezone.utc),
            message="Synthetic test data only; no device exists.",
        )

    def inspect(self):
        return self.snapshot

    def execute(self, dispatch):
        self.calls.append(dispatch)
        if self.fail_after_entry:
            raise OSError("synthetic backend disconnected after accepting operation")
        now = datetime.now(timezone.utc)
        return HardwareResult(
            operation_id=dispatch.operation_id,
            status=HardwareResultStatus.COMPLETED,
            started_at=now,
            finished_at=now,
            boot_epoch=self.snapshot.boot_epoch,
            values={"value": 42, "synthetic": True},
            payload=b"\x2a\x00\x00\x00",
            message="Synthetic fixture; not physical M1 evidence.",
        )


def _dispatch(operation_id="synthetic-operation"):
    return HardwareDispatch(
        operation_id=operation_id,
        coordinator_operation_id="synthetic-coordinator-operation",
        session_id="synthetic-session",
        target_identity="synthetic-target",
        target_snapshot_id="synthetic-snapshot",
        configuration_digest="a" * 64,
        procedure_id="synthetic-procedure",
        procedure_revision=1,
        review_id="synthetic-review",
        approval_id=None,
        approval_scope=None,
        boot_epoch="synthetic-boot-1",
        procedure_digest="b" * 64,
        artifact_digests=(),
        operation_index=0,
        operation=InspectRegister(0x1000, 4),
        deadline=datetime.now(timezone.utc) + timedelta(seconds=5),
    )


@pytest.fixture
def helper():
    # Pytest node directories can exceed the helper's sockaddr_un path bound.
    with TemporaryDirectory(prefix="m1-helper-", dir="/tmp") as directory:
        root = Path(directory)
        backend = SyntheticBackend()
        lock, server = start_exclusive_helper(
            root / "owner.lock", root / "helper.sock", lambda: backend,
        )
        stopped = Event()
        failed = Event()
        errors = []

        def record_error(error):
            errors.append(error)
            failed.set()

        thread = Thread(
            target=server.serve_forever,
            args=(stopped,),
            kwargs={"poll_interval_seconds": 0.05, "on_error": record_error},
            daemon=True,
        )
        thread.start()
        try:
            yield root, backend, HelperHardwareAdapter(root / "helper.sock"), errors, failed
        finally:
            stopped.set()
            thread.join(timeout=6)
            close_exclusive_helper(lock, server)
            assert not thread.is_alive(), "synthetic helper did not stop"


def test_typed_register_operation_crosses_real_socket_with_exact_lineage(helper):
    _, backend, client, errors, _ = helper
    dispatch = _dispatch()

    result = client.execute(dispatch)

    assert result.status is HardwareResultStatus.COMPLETED
    assert result.operation_id == dispatch.operation_id
    assert result.boot_epoch == dispatch.boot_epoch
    assert result.values == {"value": 42, "synthetic": True}
    assert result.payload == b"\x2a\x00\x00\x00"
    assert backend.calls == [dispatch]
    assert errors == []
    # No identity-query or physical qualification claim is inferred from IPC success.
    assert client.inspect().available is False
    assert client.inspect().qualified is False


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("target_id", "another-target", "different target identity"),
        ("boot_epoch", "another-boot", "stale target boot epoch"),
        ("configuration_digest", "c" * 64, "stale target configuration"),
        ("qualified", False, "not physically qualified"),
        ("capabilities", (), "does not advertise"),
        ("capabilities", (HardwareCapability("inspect_register", 2, False, 4),), "does not advertise"),
        ("capabilities", (HardwareCapability("inspect_register", 1, True, 4),), "does not advertise"),
        ("capabilities", (HardwareCapability("inspect_register", 1, False, 2),), "capability bound"),
    ],
    ids=["identity", "boot", "configuration-hash", "unqualified", "missing-capability",
         "capability-version", "mutating-capability", "capability-bound"],
)
def test_helper_rejects_stale_or_unsupported_target_before_backend_entry(helper, field, replacement, reason):
    _, backend, client, errors, failed = helper
    backend.snapshot = replace(backend.snapshot, **{field: replacement})

    # No wire error reply proves nonexecution to the client, so it stays conservative.
    with pytest.raises(HardwareError, match="operation outcome is unknown"):
        client.execute(_dispatch())

    assert failed.wait(timeout=1)
    assert len(errors) == 1
    assert reason in str(errors[0])
    assert backend.calls == []


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("version", "unsupported helper protocol version"),
        ("hash", "procedure_digest must be a lowercase SHA-256"),
        ("capture-bound", "capture length exceeds the helper bound"),
        ("frame-bound", "frame length is empty or exceeds its bound"),
        ("unknown-operation", "unsupported operation"),
    ],
)
def test_wire_contract_rejects_invalid_requests_without_backend_entry(helper, fault, reason):
    root, backend, _, errors, failed = helper
    document = json.loads(encode_request(_dispatch()))
    if fault == "version":
        document["protocol_version"] = 2
    elif fault == "hash":
        document["request"]["procedure_digest"] = "not-a-digest"
    elif fault == "capture-bound":
        document["request"]["operation"] = {
            "kind": "capture_memory", "parameters": {"address": 0x1000, "length": MAX_CAPTURE_BYTES + 1},
        }
    elif fault == "unknown-operation":
        document["request"]["operation"] = {"kind": "shell", "parameters": {"command": "unused"}}
    payload = json.dumps(document).encode()
    frame = (
        struct.pack("!I", MAX_HELPER_REQUEST_BYTES + 1)
        if fault == "frame-bound"
        else struct.pack("!I", len(payload)) + payload
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(root / "helper.sock"))
        connection.sendall(frame)
        assert connection.recv(1) == b""

    assert failed.wait(timeout=1)
    assert len(errors) == 1
    assert reason in str(errors[0])
    assert backend.calls == []


def test_exclusive_owner_prevents_second_backend_construction(helper):
    root, _, _, _, _ = helper
    constructed = []

    def second_backend():
        constructed.append(True)
        return SyntheticBackend()

    with pytest.raises(HelperOwnerError, match="another helper owns the target lock"):
        start_exclusive_helper(root / "owner.lock", root / "second.sock", second_backend)
    assert constructed == []
    assert not (root / "second.sock").exists()


def test_disconnect_after_backend_entry_is_unknown_and_never_automatically_replayed(helper):
    _, backend, client, errors, failed = helper
    backend.fail_after_entry = True
    uncertain = _dispatch("ambiguous-operation")

    with pytest.raises(HardwareError, match="operation outcome is unknown"):
        client.execute(uncertain)

    assert failed.wait(timeout=1)
    assert len(errors) == 1
    assert "disconnected after accepting" in str(errors[0])
    assert backend.calls == [uncertain]
    # The owner remains available; only a distinct explicit request runs next.
    backend.fail_after_entry = False
    following = _dispatch("separate-explicit-operation")
    assert client.execute(following).status is HardwareResultStatus.COMPLETED
    assert backend.calls == [uncertain, following]
