"""Synthetic socket checks for the attended native qualification dispatch."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread

import pytest

from m1lab.adapters.hardware import (
    HardwareCapability, HardwareDispatch, HardwareError, HardwareResult,
    HardwareResultStatus, InspectRegister, RunNativeCandidate, TargetSnapshot,
)
from m1lab.adapters.helper_server import (
    HelperHardwareAdapter, close_exclusive_helper, start_exclusive_helper,
)


PAYLOAD, IMAGE, LAUNCH = "a" * 64, "b" * 64, "c" * 64
CONFIGURATION = "d" * 64
OLD_EPOCH, RETURN_EPOCH = "proxy-epoch-1", "proxy-epoch-2"


def _dispatch(**changes):
    now = datetime.now(timezone.utc)
    values = dict(
        operation_id="native-operation", coordinator_operation_id="coordinator-operation",
        session_id="session", target_identity="synthetic-target",
        target_snapshot_id="snapshot", configuration_digest=CONFIGURATION,
        procedure_id="procedure", procedure_revision=1, review_id="review",
        approval_id="approval", approval_scope={
            "target_identity": "synthetic-target", "boot_epoch": OLD_EPOCH,
            "configuration_digest": CONFIGURATION, "repeat_limit": 1,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "physical_attendance_confirmed": True,
        },
        boot_epoch=OLD_EPOCH, procedure_digest="e" * 64,
        artifact_digests=(PAYLOAD, IMAGE, LAUNCH), operation_index=0,
        operation=RunNativeCandidate(PAYLOAD, IMAGE, LAUNCH),
        deadline=now + timedelta(seconds=10),
    )
    values.update(changes)
    return HardwareDispatch(**values)


class SyntheticBackend:
    def __init__(self, *, post_epoch=RETURN_EPOCH, post_target="synthetic-target",
                 post_mode="proxy", result_epoch=RETURN_EPOCH, post_inspect_error=False):
        self.calls = []
        self.inspect_count = 0
        self.post_epoch = post_epoch
        self.post_target = post_target
        self.post_mode = post_mode
        self.result_epoch = result_epoch
        self.post_inspect_error = post_inspect_error
        self.snapshot = TargetSnapshot(
            adapter="synthetic-native", available=True, qualified=False,
            mode="proxy", target_id="synthetic-target", boot_epoch=OLD_EPOCH,
            configuration_digest=CONFIGURATION,
            capabilities=(HardwareCapability("run_native_candidate", 1, True, 4096),),
            observed_at=datetime.now(timezone.utc),
        )

    def inspect(self):
        self.inspect_count += 1
        if self.calls:
            if self.post_inspect_error:
                raise OSError("synthetic postflight inspection failed")
            return replace(self.snapshot, target_id=self.post_target,
                           mode=self.post_mode, boot_epoch=self.post_epoch)
        return self.snapshot

    def execute(self, dispatch):
        self.calls.append(dispatch)
        now = datetime.now(timezone.utc)
        return HardwareResult(
            operation_id=dispatch.operation_id, status=HardwareResultStatus.COMPLETED,
            started_at=now, finished_at=now, boot_epoch=dispatch.boot_epoch,
            values={"return_boot_epoch": self.result_epoch},
            payload=b"synthetic native result bytes", message="Synthetic only.",
        )


@contextmanager
def _helper(root: Path, backend: SyntheticBackend):
    owner, server = start_exclusive_helper(
        root / "owner.lock", root / "helper.sock", lambda: backend,
    )
    stopped = Event()
    errors = []
    thread = Thread(target=server.serve_forever, args=(stopped,),
                    kwargs={"poll_interval_seconds": 0.05, "on_error": errors.append},
                    daemon=True)
    thread.start()
    try:
        yield HelperHardwareAdapter(root / "helper.sock"), errors
    finally:
        stopped.set()
        thread.join(timeout=6)
        close_exclusive_helper(owner, server)
        assert not thread.is_alive()


@pytest.fixture
def root():
    with TemporaryDirectory(prefix="m1-native-help-", dir="/tmp") as directory:
        yield Path(directory)


def test_attended_unqualified_proxy_candidate_round_trips_and_reserves_intent(root):
    backend = SyntheticBackend()
    dispatch = _dispatch()
    with _helper(root, backend) as (client, errors):
        result = client.execute(dispatch)
        assert result.status is HardwareResultStatus.COMPLETED
        assert result.boot_epoch == OLD_EPOCH
        assert result.values["return_boot_epoch"] == RETURN_EPOCH
        assert result.payload == b"synthetic native result bytes"
        assert backend.calls == [dispatch]
        assert errors == []
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch)
        assert backend.calls == [dispatch]


@pytest.mark.parametrize("backend_changes", [
    {"post_epoch": OLD_EPOCH},
    {"post_target": "other-target"},
    {"post_mode": "native"},
    {"result_epoch": "unobserved-epoch"},
    {"post_inspect_error": True},
])
def test_uncertain_native_return_is_unknown_with_payload_preserved(root, backend_changes):
    backend = SyntheticBackend(**backend_changes)
    with _helper(root, backend) as (client, errors):
        result = client.execute(_dispatch())
    assert result.status is HardwareResultStatus.UNKNOWN
    assert result.boot_epoch == OLD_EPOCH
    assert result.payload == b"synthetic native result bytes"
    assert "Native return could not be verified" in result.message
    assert errors == []


def test_result_over_advertised_bound_is_unknown_with_payload_preserved(root):
    backend = SyntheticBackend()
    backend.snapshot = replace(
        backend.snapshot,
        capabilities=(HardwareCapability("run_native_candidate", 1, True, 8),),
    )
    with _helper(root, backend) as (client, errors):
        result = client.execute(_dispatch())
    assert result.status is HardwareResultStatus.UNKNOWN
    assert result.payload == b"synthetic native result bytes"
    assert errors == []


@pytest.mark.parametrize("changes", [
    {"mode": "native"},
    {"available": False},
    {"boot_epoch": "stale"},
    {"configuration_digest": "f" * 64},
    {"capabilities": (HardwareCapability("run_native_candidate", 1, False, 4096),)},
])
def test_native_preflight_refuses_invalid_proxy_or_capability(root, changes):
    backend = SyntheticBackend()
    backend.snapshot = replace(backend.snapshot, **changes)
    with _helper(root, backend) as (client, errors):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(_dispatch())
    assert backend.calls == []
    assert len(errors) == 1


def test_native_preflight_requires_three_operation_artifacts_and_single_attendance(root):
    backend = SyntheticBackend()
    approval = dict(_dispatch().approval_scope)
    approval["repeat_limit"] = 2
    with pytest.raises(ValueError, match="artifacts must be in the dispatch envelope"):
        _dispatch(artifact_digests=(PAYLOAD, IMAGE, "f" * 64))
    with _helper(root, backend) as (client, errors):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(_dispatch(approval_scope=approval))
    assert backend.calls == []
    assert len(errors) == 1


def test_native_preflight_accepts_extra_reviewed_artifact_digest(root):
    backend = SyntheticBackend()
    dispatch = _dispatch(artifact_digests=(PAYLOAD, IMAGE, LAUNCH, "f" * 64))
    with _helper(root, backend) as (client, errors):
        result = client.execute(dispatch)
    assert result.status is HardwareResultStatus.COMPLETED
    assert backend.calls == [dispatch]
    assert errors == []


def test_unqualified_proxy_does_not_relax_old_register_operation(root):
    backend = SyntheticBackend()
    dispatch = _dispatch(
        operation=InspectRegister(0x1000, 4), approval_id=None,
        approval_scope=None, artifact_digests=(),
    )
    with _helper(root, backend) as (client, errors):
        with pytest.raises(HardwareError, match="operation outcome is unknown"):
            client.execute(dispatch)
    assert backend.calls == []
    assert len(errors) == 1
