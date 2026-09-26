"""Host-side contracts for finite native runs; this module opens no device."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from typing import Any, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)

from .helper_protocol import (
    HelperProtocolError,
    add_length_prefix,
    read_helper_frame_until,
    remove_length_prefix,
    write_helper_frame_until,
)


NATIVE_RESULT_PROTOCOL = "m1lab.native-result.v1"
MAX_NATIVE_FRAME_BYTES = 1_500_000
MAX_NATIVE_CHUNK_BYTES = 1_048_576
MAX_NATIVE_OUTPUT_BYTES = 16 * 1_048_576
MAX_NATIVE_RESULT_FRAMES = 4_096
MAX_NATIVE_MANIFEST_BYTES = 256 * 1024
_SHA256_LENGTH = 64
_UNSEALED_SHA256 = "0" * _SHA256_LENGTH
_NativeModelT = TypeVar("_NativeModelT", bound="NativeModel")


class NativeHarnessError(ValueError):
    """A build, launch, or result message violates the finite-run contract."""


class NativeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @field_validator("*")
    @classmethod
    def datetimes_are_aware(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.utcoffset() is None:
            raise ValueError("native harness timestamps must be timezone-aware")
        return value

    def canonical_json(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json()).hexdigest()


class ManifestArtifact(NativeModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=80)
    sha256: str
    size_bytes: int = Field(strict=True, ge=0)

    @field_validator("sha256")
    @classmethod
    def digest_is_sha256(cls, value: str) -> str:
        if not _is_sha256(value):
            raise ValueError("artifact digest must be lowercase SHA-256")
        return value


class NativeImageManifest(NativeModel):
    schema_version: Literal["m1lab.native-image.v1"] = "m1lab.native-image.v1"
    architecture: str = Field(min_length=1, max_length=80)
    source_commit: str = Field(min_length=40, max_length=64)
    source_tree_clean: bool
    source_diff_sha256: str | None = None
    toolchain: str = Field(min_length=1, max_length=160)
    toolchain_version: str = Field(min_length=1, max_length=160)
    configuration_sha256: str
    firmware_references: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    inputs: tuple[ManifestArtifact, ...] = ()
    outputs: tuple[ManifestArtifact, ...]
    collector_sha256: str
    maximum_runtime_seconds: int = Field(strict=True, ge=1, le=3600)
    maximum_output_bytes: int = Field(strict=True, ge=1, le=MAX_NATIVE_OUTPUT_BYTES)
    result_protocol: Literal["m1lab.native-result.v1"] = NATIVE_RESULT_PROTOCOL
    return_behavior: str = Field(min_length=1, max_length=512)

    @field_validator("source_commit")
    @classmethod
    def commit_is_hex(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("source commit must be lowercase hexadecimal")
        return value

    @field_validator("source_diff_sha256", "configuration_sha256", "collector_sha256")
    @classmethod
    def optional_digests_are_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _is_sha256(value):
            raise ValueError("manifest digest must be lowercase SHA-256")
        return value

    @field_validator("firmware_references", "dependencies")
    @classmethod
    def bounded_string_lists(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > 128 or any(not value or len(value) > 512 for value in values):
            raise ValueError("manifest string list is empty or exceeds its bound")
        return values

    @model_validator(mode="after")
    def artifact_names_are_unique(self) -> "NativeImageManifest":
        for artifacts in (self.inputs, self.outputs):
            names = [artifact.name for artifact in artifacts]
            if len(names) != len(set(names)):
                raise ValueError("artifact names must be unique within each manifest list")
        if not self.outputs:
            raise ValueError("image manifest requires at least one output artifact")
        if self.source_tree_clean != (self.source_diff_sha256 is None):
            raise ValueError("dirty source trees require a diff digest; clean trees must omit it")
        return self


class NativeLaunchManifest(NativeModel):
    schema_version: Literal["m1lab.native-launch.v1"] = "m1lab.native-launch.v1"
    run_id: str = Field(min_length=1, max_length=128)
    image_manifest_sha256: str
    image_sha256: str
    target_identity: str = Field(min_length=1, max_length=160)
    boot_epoch: str = Field(min_length=1, max_length=128)
    configuration_sha256: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime
    output_limit_bytes: int = Field(strict=True, ge=1, le=MAX_NATIVE_OUTPUT_BYTES)
    recovery_expectation: str = Field(min_length=1, max_length=512)

    @field_validator("image_manifest_sha256", "image_sha256", "configuration_sha256")
    @classmethod
    def launch_digests_are_sha256(cls, value: str) -> str:
        if not _is_sha256(value):
            raise ValueError("launch digest must be lowercase SHA-256")
        return value

    @field_validator("deadline")
    @classmethod
    def deadline_is_future_and_bounded(cls, value: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if value <= now:
            raise ValueError("launch deadline must be in the future")
        if (value - now).total_seconds() > 3600:
            raise ValueError("launch deadline may be at most one hour away")
        return value

    @field_validator("parameters")
    @classmethod
    def launch_parameters_are_bounded(cls, values: dict[str, Any]) -> dict[str, Any]:
        if len(values) > 64:
            raise ValueError("launch contains too many parameters")
        for key, value in values.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValueError("launch parameter name is invalid")
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, str) and len(value) <= 1024:
                continue
            if type(value) is int and -(1 << 63) <= value < (1 << 63):
                continue
            if type(value) is float and math.isfinite(value):
                continue
            raise ValueError("launch parameters must be bounded scalar values")
        return values

    def validate_against_image(self, image: NativeImageManifest) -> None:
        """Bind this launch to a specific immutable image manifest."""

        remaining_runtime = (self.deadline - datetime.now(timezone.utc)).total_seconds()
        if remaining_runtime <= 0:
            raise NativeHarnessError("launch deadline has expired")
        if self.image_manifest_sha256 != image.digest():
            raise NativeHarnessError("launch image manifest digest does not match its manifest")
        if self.configuration_sha256 != image.configuration_sha256:
            raise NativeHarnessError("launch configuration does not match the image manifest")
        if self.output_limit_bytes > image.maximum_output_bytes:
            raise NativeHarnessError("launch output limit exceeds the image manifest bound")
        if (self.deadline - datetime.now(timezone.utc)).total_seconds() > image.maximum_runtime_seconds:
            raise NativeHarnessError("launch deadline exceeds the image runtime bound")
        if self.image_sha256 not in {artifact.sha256 for artifact in image.outputs}:
            raise NativeHarnessError("launch image digest is not an output of its image manifest")


class NativeResultFrame(NativeModel):
    schema_version: Literal["m1lab.native-result.v1"] = NATIVE_RESULT_PROTOCOL
    frame_kind: Literal["identity", "data", "end"]
    run_id: str = Field(min_length=1, max_length=128)
    image_sha256: str
    target_identity: str = Field(min_length=1, max_length=160)
    boot_epoch: str = Field(min_length=1, max_length=128)
    configuration_sha256: str
    sequence: int = Field(strict=True, ge=0, le=MAX_NATIVE_RESULT_FRAMES)
    payload_base64: str = ""
    payload_sha256: str | None = None
    terminal_status: Literal["complete", "partial"] | None = None
    frame_sha256: str = _UNSEALED_SHA256

    @field_validator("image_sha256", "configuration_sha256", "frame_sha256")
    @classmethod
    def frame_digests_are_sha256(cls, value: str) -> str:
        if not _is_sha256(value):
            raise ValueError("result frame digest must be lowercase SHA-256")
        return value

    @field_validator("payload_sha256")
    @classmethod
    def payload_digest_is_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _is_sha256(value):
            raise ValueError("payload digest must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_frame_content(self) -> "NativeResultFrame":
        if self.frame_kind == "data":
            if not self.payload_base64 or self.payload_sha256 is None or self.terminal_status:
                raise ValueError("data frame requires payload and forbids terminal status")
            try:
                payload = base64.b64decode(self.payload_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("data frame payload is invalid base64") from exc
            if not 0 < len(payload) <= MAX_NATIVE_CHUNK_BYTES:
                raise ValueError("data frame payload is empty or exceeds its bound")
            if hashlib.sha256(payload).hexdigest() != self.payload_sha256:
                raise ValueError("data frame payload digest does not match")
        elif self.payload_base64 or self.payload_sha256 is not None:
            raise ValueError("identity and end frames cannot contain payload data")
        if self.frame_kind == "identity":
            if self.sequence != 0 or self.terminal_status is not None:
                raise ValueError("identity frame must be sequence zero without terminal status")
        elif self.frame_kind == "end":
            if self.terminal_status is None:
                raise ValueError("end frame requires a complete or partial status")
        elif self.terminal_status is not None:
            raise ValueError("data frame cannot contain terminal status")
        return self


class NativeCapture(NativeModel):
    status: Literal["complete", "partial", "unknown"]
    identity_verified: bool
    payload: bytes = Field(max_length=MAX_NATIVE_OUTPUT_BYTES)
    frame_count: int = Field(ge=0, le=MAX_NATIVE_RESULT_FRAMES)
    message: str = Field(max_length=1024)

    @field_serializer("payload")
    def serialize_payload(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @computed_field
    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


class NativeResultAssembler:
    """Validate result lineage and retain received bytes without inferring loss."""

    def __init__(self, launch: NativeLaunchManifest, image: NativeImageManifest):
        launch.validate_against_image(image)
        self.launch = launch
        self._identity_verified = False
        self._expected_sequence = 0
        self._payload = bytearray()
        self._frame_count = 0
        self._terminal_status: Literal["complete", "partial"] | None = None
        self._invalid_message = ""

    def accept(self, frame_bytes: bytes) -> None:
        try:
            self._accept(decode_native_result_frame(frame_bytes))
        except Exception as exc:
            self._invalid_message = f"result stream is invalid: {type(exc).__name__}: {exc}"[:1024]
            raise

    def _accept(self, frame: NativeResultFrame) -> None:
        if self._invalid_message:
            raise NativeHarnessError("result stream is already invalid")
        if self._terminal_status is not None:
            raise NativeHarnessError("result stream contains frames after its terminal frame")
        if datetime.now(timezone.utc) > self.launch.deadline:
            raise NativeHarnessError("result frame arrived after the launch deadline")
        if frame.run_id != self.launch.run_id:
            raise NativeHarnessError("result frame belongs to a different run")
        if frame.image_sha256 != self.launch.image_sha256:
            raise NativeHarnessError("result frame image digest does not match the launch")
        if frame.configuration_sha256 != self.launch.configuration_sha256:
            raise NativeHarnessError("result frame configuration does not match the launch")
        if frame.target_identity != self.launch.target_identity:
            raise NativeHarnessError("result frame target identity does not match the launch")
        if not self._identity_verified:
            if frame.frame_kind != "identity" or frame.sequence != 0:
                raise NativeHarnessError("target identity frame must arrive first")
            if frame.boot_epoch != self.launch.boot_epoch:
                raise NativeHarnessError("result boot epoch does not match the launch")
            self._identity_verified = True
            self._expected_sequence = 1
            self._frame_count += 1
            return
        if frame.boot_epoch != self.launch.boot_epoch:
            raise NativeHarnessError("result boot epoch changed during the run")
        if frame.frame_kind == "identity":
            raise NativeHarnessError("result stream contains a duplicate identity frame")
        if frame.sequence != self._expected_sequence:
            raise NativeHarnessError("result frame sequence is missing, duplicated, or out of order")
        if self._frame_count >= MAX_NATIVE_RESULT_FRAMES:
            raise NativeHarnessError("result stream exceeds its frame-count bound")
        if frame.frame_kind == "data":
            payload = base64.b64decode(frame.payload_base64, validate=True)
            total = len(self._payload) + len(payload)
            if total > self.launch.output_limit_bytes:
                raise NativeHarnessError("result stream exceeds its launch output limit")
            self._payload.extend(payload)
        else:
            if frame.terminal_status == "complete" and not self._payload:
                raise NativeHarnessError("complete result contains no result payload")
            self._terminal_status = frame.terminal_status
        self._expected_sequence += 1
        self._frame_count += 1

    def capture(self, message: str = "") -> NativeCapture:
        if self._invalid_message:
            return NativeCapture(
                status="unknown",
                identity_verified=self._identity_verified,
                payload=bytes(self._payload),
                frame_count=self._frame_count,
                message=self._invalid_message,
            )
        return NativeCapture(
            status=self._terminal_status or "unknown",
            identity_verified=self._identity_verified,
            payload=bytes(self._payload),
            frame_count=self._frame_count,
            message=(
                message
                or (
                    "result stream ended without a terminal frame"
                    if self._terminal_status is None
                    else ""
                )
            )[:1024],
        )


def encode_native_result_frame(frame: NativeResultFrame) -> bytes:
    document = frame.model_dump(mode="json")
    unsigned = {key: value for key, value in document.items() if key != "frame_sha256"}
    digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    document["frame_sha256"] = digest
    payload = _canonical_json(document)
    return add_length_prefix(payload, maximum=MAX_NATIVE_FRAME_BYTES)


def encode_native_manifest(manifest: NativeImageManifest | NativeLaunchManifest) -> bytes:
    payload = manifest.canonical_json()
    if len(payload) > MAX_NATIVE_MANIFEST_BYTES:
        raise NativeHarnessError("native manifest exceeds its size bound")
    return payload


def decode_native_image_manifest(payload: bytes) -> NativeImageManifest:
    return _decode_native_manifest(payload, NativeImageManifest)


def decode_native_launch_manifest(payload: bytes) -> NativeLaunchManifest:
    return _decode_native_manifest(payload, NativeLaunchManifest)


def make_native_result_frame(
    *,
    frame_kind: Literal["identity", "data", "end"],
    run_id: str,
    image_sha256: str,
    target_identity: str,
    boot_epoch: str,
    configuration_sha256: str,
    sequence: int,
    payload: bytes = b"",
    terminal_status: Literal["complete", "partial"] | None = None,
) -> NativeResultFrame:
    """Create a checksummable identity, data, or terminal result frame."""

    if not isinstance(payload, bytes):
        raise NativeHarnessError("result payload must be bytes")
    if len(payload) > MAX_NATIVE_CHUNK_BYTES:
        raise NativeHarnessError("result chunk exceeds its bound")
    return NativeResultFrame(
        frame_kind=frame_kind,
        run_id=run_id,
        image_sha256=image_sha256,
        target_identity=target_identity,
        boot_epoch=boot_epoch,
        configuration_sha256=configuration_sha256,
        sequence=sequence,
        payload_base64=base64.b64encode(payload).decode("ascii") if payload else "",
        payload_sha256=hashlib.sha256(payload).hexdigest() if payload else None,
        terminal_status=terminal_status,
    )


def decode_native_result_frame(frame: bytes) -> NativeResultFrame:
    try:
        payload = remove_length_prefix(frame, maximum=MAX_NATIVE_FRAME_BYTES)
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(document, dict):
            raise NativeHarnessError("result frame must be a JSON object")
        supplied_digest = document.get("frame_sha256")
        unsigned = {key: value for key, value in document.items() if key != "frame_sha256"}
        expected_digest = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
        if not isinstance(supplied_digest, str) or not hmac.compare_digest(
            supplied_digest, expected_digest
        ):
            raise NativeHarnessError("result frame checksum does not match")
        return NativeResultFrame.model_validate(document)
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, NativeHarnessError):
            raise
        raise NativeHarnessError(f"invalid native result frame: {exc}") from exc


def read_native_result_frame_until(fd: int, *, deadline_monotonic: float) -> bytes:
    """Read one framed result from a caller-owned descriptor before its deadline."""

    try:
        return read_helper_frame_until(
            fd, maximum=MAX_NATIVE_FRAME_BYTES, deadline_monotonic=deadline_monotonic
        )
    except (HelperProtocolError, TimeoutError) as exc:
        raise NativeHarnessError(f"native result transport failed: {exc}") from exc


def write_native_result_frame_until(
    fd: int, frame: NativeResultFrame, *, deadline_monotonic: float
) -> None:
    """Write one result frame to a caller-owned descriptor before its deadline."""

    try:
        encoded = encode_native_result_frame(frame)
        payload = remove_length_prefix(encoded, maximum=MAX_NATIVE_FRAME_BYTES)
        write_helper_frame_until(
            fd,
            payload,
            maximum=MAX_NATIVE_FRAME_BYTES,
            deadline_monotonic=deadline_monotonic,
        )
    except (HelperProtocolError, TimeoutError) as exc:
        raise NativeHarnessError(f"native result transport failed: {exc}") from exc


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _decode_native_manifest(
    payload: bytes, model: type[_NativeModelT]
) -> _NativeModelT:
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_NATIVE_MANIFEST_BYTES:
        raise NativeHarnessError("native manifest is empty or exceeds its size bound")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(document, dict):
            raise NativeHarnessError("native manifest must be a JSON object")
        return model.model_validate(document)
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, NativeHarnessError):
            raise
        raise NativeHarnessError(f"invalid native manifest: {exc}") from exc


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NativeHarnessError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise NativeHarnessError(f"invalid JSON constant {value}")
