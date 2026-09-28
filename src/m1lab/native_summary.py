"""Summarize retained native evidence without accessing or qualifying hardware."""

from __future__ import annotations

import base64
import json
from statistics import median

from m1lab.adapters.native_harness import NativeHarnessError
from m1lab.core import CoreApp
from m1lab.native_runs import (
    CAPTURE_MEDIA_TYPE, CAPTURE_STREAM_MEDIA_TYPE, MAX_CAPTURE_STREAM_BYTES,
    MAX_NATIVE_OUTPUT_BYTES, _capture_manifests, _parse_saved_capture,
    _screen_capture_payload,
)


def summarize_native_capture(
    core: CoreApp, session_id: str, capture_artifact_id: str,
) -> dict:
    """Recheck raw framing/lineage and describe screened samples, read-only.

    Replaying a stored stream can verify consistency, never physical origin,
    receipt timing, sensor calibration, target recovery, or a power improvement.
    """
    artifacts = {item.id: item for item in core.artifacts(session_id)}
    record = artifacts.get(capture_artifact_id)
    if (record is None or not record.available or record.media_type != CAPTURE_MEDIA_TYPE
            or record.provenance.get("record_type") != "native_capture"):
        raise NativeHarnessError("native capture is unavailable in the selected session")
    document = json.loads(core.read_session_artifact(
        session_id, record.id, max_bytes=2 * MAX_NATIVE_OUTPUT_BYTES,
    ))
    provenance = record.provenance
    raw_id = provenance.get("raw_stream_artifact_id")
    raw = artifacts.get(raw_id) if isinstance(raw_id, str) else None
    if (not isinstance(document, dict) or raw is None or not raw.available
            or raw.media_type != CAPTURE_STREAM_MEDIA_TYPE
            or raw.provenance.get("record_type") != "native_result_stream"
            or document.get("raw_stream_artifact_id") != raw_id):
        raise NativeHarnessError("native capture has no matching retained raw stream")
    for name in ("launch_artifact_id", "image_manifest_artifact_id"):
        if (not isinstance(provenance.get(name), str)
                or raw.provenance.get(name) != provenance[name]):
            raise NativeHarnessError("native capture and raw stream lineage differ")
    launch, image = _capture_manifests(
        core, session_id, provenance["launch_artifact_id"],
        provenance["image_manifest_artifact_id"], require_current_deadline=False,
    )
    stream = core.read_session_artifact(session_id, raw.id, max_bytes=MAX_CAPTURE_STREAM_BYTES)
    capture = _parse_saved_capture(stream, launch, image)
    expected = launch.parameters["sample_count"]
    payload, screening = _screen_capture_payload(
        capture.payload, expected_sample_count=expected, protocol_status=capture.status,
    )
    status = "unknown" if screening.startswith("omitted_") else capture.status
    if (document.get("payload") != base64.b64encode(payload).decode("ascii")
            or document.get("status") != status
            or document.get("protocol_status") != capture.status
            or document.get("payload_screening") != screening):
        raise NativeHarnessError("normalized capture differs from its retained raw evidence")
    samples = [json.loads(line) for line in payload.splitlines()]
    times = [sample["monotonic_ns"] for sample in samples]
    intervals = [(right - left) / 1_000_000 for left, right in zip(times, times[1:])]
    requested_period = launch.parameters["sample_period_ms"]
    sensor_fields: dict[tuple[str, str, str], dict] = {}
    duplicate_sensor_names = False
    for sample in samples:
        for category in ("power_supplies", "thermal_zones"):
            seen = set()
            for sensor in sample["sources"][category]:
                if sensor["name"] in seen:
                    duplicate_sensor_names = True
                    continue
                seen.add(sensor["name"])
                for field, value in sensor["attributes"].items():
                    key = category, sensor["name"], field
                    item = sensor_fields.setdefault(key, {
                        "source": category, "name": sensor["name"], "field": field,
                        "samples_present": 0, "first_raw_value": value,
                        "last_raw_value": value,
                    })
                    item["samples_present"] += 1
                    item["last_raw_value"] = value
    fields = []
    for key in sorted(sensor_fields):
        item = sensor_fields[key]
        item["samples_missing"] = len(samples) - item["samples_present"]
        fields.append(item)
    gaps = []
    if status != "complete":
        gaps.append("Capture is partial or unknown; retain it as incomplete evidence.")
    if not samples:
        gaps.append("No recognized samples are available.")
    if not any(item["source"] == "power_supplies" for item in fields):
        gaps.append("No power-supply attributes were captured; check native driver availability.")
    if duplicate_sensor_names:
        gaps.append("Duplicate sensor names prevent unambiguous sensor attribution.")
    gaps.extend([
        "Verify sensor units, calibration, energy boundary and USB/charging power paths.",
        "Record display/workload, warmup and a stable native measurement fixture.",
        "Measure drift, noise, missing readings and collector overhead in longer paired pilots.",
        "Establish physical source, capture timing and recovery from independent evidence.",
    ])
    return {
        "schema_version": "m1lab.native-summary.v1",
        "session_id": session_id,
        "capture_artifact_id": record.id,
        "capture_sha256": record.sha256,
        "raw_stream_artifact_id": raw.id,
        "raw_stream_sha256": raw.sha256,
        "launch_artifact_id": provenance["launch_artifact_id"],
        "image_manifest_artifact_id": provenance["image_manifest_artifact_id"],
        "run_id": launch.run_id,
        "status": status,
        "protocol_status": capture.status,
        "payload_screening": screening,
        "launch_binding_verified": capture.launch_binding_verified,
        "physical_source_verified": False,
        "capture_timing_verified": False,
        "measurement_qualified": False,
        "expected_samples": expected,
        "recognized_samples": len(samples),
        "missing_samples": expected - len(samples),
        "device_tree_models": sorted({s["sources"]["device_tree_model"] for s in samples
                                      if s["sources"]["device_tree_model"] is not None}),
        "timing": {
            "source": "collector-reported monotonic clock; not independently verified",
            "requested_period_ms": requested_period,
            "interval_count": len(intervals),
            "minimum_interval_ms": min(intervals) if intervals else None,
            "median_interval_ms": median(intervals) if intervals else None,
            "maximum_interval_ms": max(intervals) if intervals else None,
            "elapsed_ms": (times[-1] - times[0]) / 1_000_000 if len(times) > 1 else None,
            "maximum_absolute_period_error_ms": max(
                (abs(value - requested_period) for value in intervals), default=None,
            ),
        },
        "sensor_fields": fields,
        "interpretation": "Raw values only; no conversion to watts or whole-device power claim.",
        "qualification_gaps": gaps,
    }
