"""Versioned, bounded JSON codec for coordinator-to-hardware-helper messages.

This module opens no device and starts no process. A future helper transport
can use this codec after physical interface ownership and recovery are
qualified. Unknown versions, operations, fields, and mismatched replies fail
closed; callers must treat failures after dispatch as unknown effects.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
import math
import struct
from typing import Any, BinaryIO

from .hardware import (
    MAX_CAPTURE_BYTES,
    MAX_REPLAY_WAIT_MS,
    CaptureMemory,
    HardwareDispatch,
    HardwareOperation,
    HardwareResult,
    HardwareResultStatus,
    InspectRegister,
    SimulateBoot,
    WaitForReplay,
)


HELPER_PROTOCOL_VERSION = 1
MAX_HELPER_REQUEST_BYTES = 64 * 1024
MAX_HELPER_RESPONSE_BYTES = 1_500_000
HELPER_FRAME_HEADER_BYTES = 4

_REQUEST_FIELDS = frozenset(
    {
        "operation_id",
        "coordinator_operation_id",
        "session_id",
        "target_identity",
        "target_snapshot_id",
        "configuration_digest",
        "procedure_id",
        "procedure_revision",
        "review_id",
        "approval_id",
        "approval_scope",
        "boot_epoch",
        "procedure_digest",
        "artifact_digests",
        "operation_index",
        "operation",
        "deadline",
        "artifact_digest",
        "scope",
    }
)


class HelperProtocolError(ValueError):
    """A helper request or result violates the versioned wire contract."""


def add_length_prefix(payload: bytes, *, maximum: int) -> bytes:
    """Wrap one encoded message in a four-byte big-endian length prefix."""

    if not isinstance(payload, bytes) or not payload or len(payload) > maximum:
        raise HelperProtocolError("helper payload is empty, not bytes, or exceeds its bound")
    return struct.pack("!I", len(payload)) + payload


def remove_length_prefix(frame: bytes, *, maximum: int) -> bytes:
    """Extract exactly one complete message; reject truncation and trailing bytes."""

    if not isinstance(frame, bytes) or len(frame) < HELPER_FRAME_HEADER_BYTES:
        raise HelperProtocolError("helper frame is missing its complete length prefix")
    (length,) = struct.unpack("!I", frame[:HELPER_FRAME_HEADER_BYTES])
    if length == 0 or length > maximum:
        raise HelperProtocolError("helper frame length is empty or exceeds its bound")
    if len(frame) != HELPER_FRAME_HEADER_BYTES + length:
        raise HelperProtocolError("helper frame is truncated or contains trailing bytes")
    return frame[HELPER_FRAME_HEADER_BYTES:]


def read_helper_frame(stream: BinaryIO, *, maximum: int) -> bytes:
    """Read one complete bounded frame from a blocking binary stream.

    Callers must enforce their own deadline and classify any failure after
    dispatch as an unknown effect. This helper never retries an operation.
    """

    header = _read_exact(stream, HELPER_FRAME_HEADER_BYTES)
    (length,) = struct.unpack("!I", header)
    if length == 0 or length > maximum:
        raise HelperProtocolError("helper frame length is empty or exceeds its bound")
    return header + _read_exact(stream, length)


def write_helper_frame(stream: BinaryIO, payload: bytes, *, maximum: int) -> None:
    """Write one bounded frame fully, handling short writes on blocking streams."""

    frame = add_length_prefix(payload, maximum=maximum)
    remaining = memoryview(frame)
    while remaining:
        written = stream.write(remaining)
        if not isinstance(written, int) or written <= 0:
            raise HelperProtocolError("helper stream closed or refused a frame write")
        remaining = remaining[written:]
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not isinstance(chunk, bytes) or not chunk:
            raise HelperProtocolError("helper stream ended before the frame was complete")
        chunks.extend(chunk)
    return bytes(chunks)


def encode_request_frame(dispatch: HardwareDispatch) -> bytes:
    return add_length_prefix(encode_request(dispatch), maximum=MAX_HELPER_REQUEST_BYTES)


def decode_request_frame(frame: bytes) -> HardwareDispatch:
    payload = remove_length_prefix(frame, maximum=MAX_HELPER_REQUEST_BYTES)
    return decode_request(payload)


def encode_result_frame(result: HardwareResult) -> bytes:
    return add_length_prefix(encode_result(result), maximum=MAX_HELPER_RESPONSE_BYTES)


def decode_result_frame(frame: bytes, *, expected_operation_id: str) -> HardwareResult:
    payload = remove_length_prefix(frame, maximum=MAX_HELPER_RESPONSE_BYTES)
    return decode_result(payload, expected_operation_id=expected_operation_id)


def write_request(stream: BinaryIO, dispatch: HardwareDispatch) -> None:
    write_helper_frame(stream, encode_request(dispatch), maximum=MAX_HELPER_REQUEST_BYTES)


def read_request(stream: BinaryIO) -> HardwareDispatch:
    return decode_request_frame(
        read_helper_frame(stream, maximum=MAX_HELPER_REQUEST_BYTES)
    )


def write_result(stream: BinaryIO, result: HardwareResult) -> None:
    write_helper_frame(stream, encode_result(result), maximum=MAX_HELPER_RESPONSE_BYTES)


def read_result(stream: BinaryIO, *, expected_operation_id: str) -> HardwareResult:
    return decode_result_frame(
        read_helper_frame(stream, maximum=MAX_HELPER_RESPONSE_BYTES),
        expected_operation_id=expected_operation_id,
    )


def encode_request(dispatch: HardwareDispatch) -> bytes:
    """Encode one already-authorized typed operation as a bounded JSON frame."""

    document = {
        "protocol_version": HELPER_PROTOCOL_VERSION,
        "request": {
            "operation_id": dispatch.operation_id,
            "coordinator_operation_id": dispatch.coordinator_operation_id,
            "session_id": dispatch.session_id,
            "target_identity": dispatch.target_identity,
            "target_snapshot_id": dispatch.target_snapshot_id,
            "configuration_digest": dispatch.configuration_digest,
            "procedure_id": dispatch.procedure_id,
            "procedure_revision": dispatch.procedure_revision,
            "review_id": dispatch.review_id,
            "approval_id": dispatch.approval_id,
            "approval_scope": dict(dispatch.approval_scope) if dispatch.approval_scope else None,
            "boot_epoch": dispatch.boot_epoch,
            "procedure_digest": dispatch.procedure_digest,
            "artifact_digests": list(dispatch.artifact_digests),
            "operation_index": dispatch.operation_index,
            "operation": _operation_document(dispatch.operation),
            "deadline": dispatch.deadline.isoformat(),
            "artifact_digest": dispatch.artifact_digest,
            "scope": dict(dispatch.scope),
        },
    }
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(encoded) > MAX_HELPER_REQUEST_BYTES:
        raise HelperProtocolError("helper request exceeds its frame bound")
    return encoded


def decode_request(frame: bytes) -> HardwareDispatch:
    """Decode a request, accepting only the exact version-one typed schema."""

    document = _decode_json(frame, MAX_HELPER_REQUEST_BYTES, "request")
    if not isinstance(document, dict) or set(document) != {"protocol_version", "request"}:
        raise HelperProtocolError("helper request envelope has unknown or missing fields")
    if type(document["protocol_version"]) is not int or document["protocol_version"] != HELPER_PROTOCOL_VERSION:
        raise HelperProtocolError("unsupported helper protocol version")
    request = document["request"]
    if not isinstance(request, dict) or set(request) != _REQUEST_FIELDS:
        raise HelperProtocolError("helper request has unknown or missing fields")
    operation = _decode_operation(request["operation"])
    artifact_digests = request["artifact_digests"]
    if not isinstance(artifact_digests, list) or any(not isinstance(item, str) for item in artifact_digests):
        raise HelperProtocolError("artifact_digests must be a string array")
    scope = request["scope"]
    if not isinstance(scope, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in scope.items()
    ):
        raise HelperProtocolError("scope must be a string-to-string object")
    approval_scope = request["approval_scope"]
    if approval_scope is not None and not isinstance(approval_scope, dict):
        raise HelperProtocolError("approval_scope must be an object or null")
    if isinstance(approval_scope, dict) and any(
        not isinstance(key, str) for key in approval_scope
    ):
        raise HelperProtocolError("approval_scope keys must be strings")
    try:
        deadline = datetime.fromisoformat(_expect_string(request["deadline"], "deadline"))
        return HardwareDispatch(
            operation_id=_expect_string(request["operation_id"], "operation_id"),
            coordinator_operation_id=_expect_string(
                request["coordinator_operation_id"], "coordinator_operation_id"
            ),
            session_id=_expect_string(request["session_id"], "session_id"),
            target_identity=_expect_string(request["target_identity"], "target_identity"),
            target_snapshot_id=_expect_string(request["target_snapshot_id"], "target_snapshot_id"),
            configuration_digest=_expect_string(
                request["configuration_digest"], "configuration_digest"
            ),
            procedure_id=_expect_string(request["procedure_id"], "procedure_id"),
            procedure_revision=_expect_int(request["procedure_revision"], "procedure_revision"),
            review_id=_expect_string(request["review_id"], "review_id"),
            approval_id=(
                None if request["approval_id"] is None else _expect_string(request["approval_id"], "approval_id")
            ),
            approval_scope=approval_scope,
            boot_epoch=_expect_string(request["boot_epoch"], "boot_epoch"),
            procedure_digest=_expect_string(request["procedure_digest"], "procedure_digest"),
            artifact_digests=tuple(artifact_digests),
            operation_index=_expect_int(request["operation_index"], "operation_index"),
            operation=operation,
            deadline=deadline,
            artifact_digest=(
                None
                if request["artifact_digest"] is None
                else _expect_string(request["artifact_digest"], "artifact_digest")
            ),
            scope=scope,
        )
    except (TypeError, ValueError) as exc:
        raise HelperProtocolError(f"invalid helper request: {exc}") from exc


def encode_result(result: HardwareResult) -> bytes:
    """Encode one bounded helper result."""

    if len(result.values) > 256 or any(
        not isinstance(key, str) or len(key) > 160 or not _is_scalar(value)
        for key, value in result.values.items()
    ):
        raise HelperProtocolError("helper result values exceed their typed bound")

    document = {
        "protocol_version": HELPER_PROTOCOL_VERSION,
        "result": {
            "operation_id": result.operation_id,
            "status": result.status.value,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "boot_epoch": result.boot_epoch,
            "values": dict(result.values),
            "payload_base64": base64.b64encode(result.payload).decode("ascii"),
            "message": result.message,
        },
    }
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(encoded) > MAX_HELPER_RESPONSE_BYTES:
        raise HelperProtocolError("helper result exceeds its frame bound")
    return encoded


def decode_result(frame: bytes, *, expected_operation_id: str) -> HardwareResult:
    """Decode a result and bind it to the requested helper operation ID."""

    document = _decode_json(frame, MAX_HELPER_RESPONSE_BYTES, "result")
    if not isinstance(document, dict) or set(document) != {"protocol_version", "result"}:
        raise HelperProtocolError("helper result envelope has unknown or missing fields")
    if type(document["protocol_version"]) is not int or document["protocol_version"] != HELPER_PROTOCOL_VERSION:
        raise HelperProtocolError("unsupported helper protocol version")
    result = document["result"]
    fields = {
        "operation_id",
        "status",
        "started_at",
        "finished_at",
        "boot_epoch",
        "values",
        "payload_base64",
        "message",
    }
    if not isinstance(result, dict) or set(result) != fields:
        raise HelperProtocolError("helper result has unknown or missing fields")
    operation_id = _expect_string(result["operation_id"], "operation_id")
    if operation_id != expected_operation_id:
        raise HelperProtocolError("helper result operation ID does not match the request")
    values = result["values"]
    if not isinstance(values, dict) or len(values) > 256 or any(
        not isinstance(key, str) or len(key) > 160 or not _is_scalar(value)
        for key, value in values.items()
    ):
        raise HelperProtocolError("helper result values must contain only scalar JSON values")
    encoded_payload = _expect_string(result["payload_base64"], "payload_base64")
    try:
        payload = base64.b64decode(encoded_payload, validate=True)
        started_at = datetime.fromisoformat(_expect_string(result["started_at"], "started_at"))
        finished_at = datetime.fromisoformat(_expect_string(result["finished_at"], "finished_at"))
        status = HardwareResultStatus(_expect_string(result["status"], "status"))
        return HardwareResult(
            operation_id=operation_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            boot_epoch=_expect_string(result["boot_epoch"], "boot_epoch"),
            values=values,
            payload=payload,
            message=_expect_string(result["message"], "message"),
        )
    except (TypeError, ValueError, binascii.Error) as exc:
        raise HelperProtocolError(f"invalid helper result: {exc}") from exc


def _operation_document(operation: HardwareOperation) -> dict[str, Any]:
    if isinstance(operation, InspectRegister):
        return {"kind": operation.kind, "parameters": {"address": operation.address, "width_bytes": operation.width_bytes}}
    if isinstance(operation, CaptureMemory):
        return {"kind": operation.kind, "parameters": {"address": operation.address, "length": operation.length}}
    if isinstance(operation, WaitForReplay):
        return {"kind": operation.kind, "parameters": {"duration_ms": operation.duration_ms}}
    if isinstance(operation, SimulateBoot):
        return {"kind": operation.kind, "parameters": {"next_boot_epoch": operation.next_boot_epoch}}
    raise HelperProtocolError(f"unsupported typed operation {type(operation).__name__}")


def _decode_operation(document: Any) -> HardwareOperation:
    if not isinstance(document, dict) or set(document) != {"kind", "parameters"}:
        raise HelperProtocolError("operation must contain only kind and parameters")
    kind = _expect_string(document["kind"], "operation.kind")
    parameters = document["parameters"]
    if not isinstance(parameters, dict):
        raise HelperProtocolError("operation parameters must be an object")
    try:
        if kind == "inspect_register" and set(parameters) == {"address", "width_bytes"}:
            return InspectRegister(
                _expect_int(parameters["address"], "address"),
                _expect_int(parameters["width_bytes"], "width_bytes"),
            )
        if kind == "capture_memory" and set(parameters) == {"address", "length"}:
            address = _expect_int(parameters["address"], "address")
            length = _expect_int(parameters["length"], "length")
            if length > MAX_CAPTURE_BYTES:
                raise ValueError("capture length exceeds the helper bound")
            return CaptureMemory(address, length)
        if kind == "wait" and set(parameters) == {"duration_ms"}:
            duration = _expect_int(parameters["duration_ms"], "duration_ms")
            if duration > MAX_REPLAY_WAIT_MS:
                raise ValueError("wait exceeds the helper bound")
            return WaitForReplay(duration)
        if kind == "simulate_boot" and set(parameters) == {"next_boot_epoch"}:
            return SimulateBoot(_expect_string(parameters["next_boot_epoch"], "next_boot_epoch"))
    except (TypeError, ValueError) as exc:
        raise HelperProtocolError(f"invalid operation parameters: {exc}") from exc
    raise HelperProtocolError(f"unsupported operation or parameters for {kind!r}")


def _decode_json(frame: bytes, maximum: int, label: str) -> Any:
    if not isinstance(frame, bytes) or len(frame) > maximum:
        raise HelperProtocolError(f"helper {label} frame exceeds its bound or is not bytes")
    try:
        return json.loads(
            frame.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise HelperProtocolError(f"helper {label} is not valid bounded JSON") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _expect_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value


def _is_scalar(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str):
        return len(value) <= 4_096
    if type(value) is int:
        return -(1 << 63) <= value < (1 << 63)
    return isinstance(value, float) and math.isfinite(value)
