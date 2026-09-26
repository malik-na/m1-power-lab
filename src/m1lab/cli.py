"""Local operator CLI and application entry point."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Iterator
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
import zipfile

import uvicorn
from pydantic import TypeAdapter

from m1lab.application import CoordinatorFacade, latest_session_id
from m1lab.config import Settings
from m1lab.adapters import (
    AppServerCodexAdapter,
    InspectRegister,
    ReplayHardwareAdapter,
    ReplayStep,
    SimulateBoot,
    WaitForReplay,
)
from m1lab.core import (
    CommandKind,
    CoreApp,
    DispatchRequest,
    JobCreate,
    OwnerCommand,
    ProcedureDraft,
    ProcedureRecord,
    ReviewDisposition,
    ReviewRecord,
    SessionCreate,
    SessionPhase,
    TargetMode,
    TypedOperation,
)
from m1lab.core.errors import CoreError
from m1lab.core.journal import JOURNAL_DISK_RESERVE_BYTES
from m1lab.core.models import new_id, utc_now
from m1lab.experiment import ExperimentService
from m1lab.investigator import EvidenceExcerpt, InvestigationOrchestrator, InvestigationRequest
from m1lab.host import HostAdmissionPolicy, LinuxHostMonitor
from m1lab.notifications import PushConfig
from m1lab.science import (
    ClaimEvidence,
    DecisionRecord,
    DerivedResultRecord,
    EvidenceDirection,
    Exclusion,
    HypothesisRecord,
    ProtocolAdherence,
    RedesignCheckpointRecord,
    RegressionCheck,
    ScientificRecord,
    ScientificRecordStore,
    StudyMode,
)
from m1lab.web import WebSettings, create_app


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="m1lab", description="M1 Power Lab coordinator")
    root.add_argument("--json", action="store_true", help="print machine-readable JSON")
    root.add_argument("--session", help="session id; defaults to the newest session")
    commands = root.add_subparsers(dest="action", required=True)

    init = commands.add_parser("init", help="create a local investigation session")
    init.add_argument("--objective", default="Investigate and improve Apple M1 power management")
    init.add_argument("--owner")
    init.add_argument("--host-identity", default=socket.gethostname())
    init.add_argument("--target-identity")
    init.add_argument("--hours", type=float, default=3.0)
    init.add_argument("--tokens", type=int, default=100_000_000)

    commands.add_parser("sessions", help="list sessions")
    commands.add_parser("status", help="show authoritative session state")

    serve = commands.add_parser("serve", help="run the owner web interface")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    control = commands.add_parser("control", help="change session lifecycle")
    control.add_argument("command", choices=("start", "pause", "resume", "stop", "complete"))
    control.add_argument("--expected-revision", type=int)

    steer = commands.add_parser("steer", help="record owner steering")
    steer.add_argument("message")
    steer.add_argument("--expected-revision", type=int)

    budget = commands.add_parser("budget", help="change a session allowance")
    budget.add_argument("command", choices=("add-tokens", "extend-time", "reset-time"))
    budget.add_argument("amount", type=int, help="tokens, or minutes for a time command")
    budget.add_argument("--expected-revision", type=int)

    approve = commands.add_parser("approve", help="approve an exact procedure revision")
    approve.add_argument("procedure_id")
    approve.add_argument("procedure_revision", type=int)
    approve.add_argument("--minutes", type=int, default=15)
    approve.add_argument("--repeat", type=int, default=1)
    approve.add_argument("--physical-attendance", action="store_true")
    approve.add_argument("--expected-revision", type=int)

    deny = commands.add_parser("deny", help="deny a pending procedure")
    deny.add_argument("procedure_id")
    deny.add_argument("procedure_revision", type=int)
    deny.add_argument("--expected-revision", type=int)

    revoke = commands.add_parser("revoke", help="revoke an active approval")
    revoke.add_argument("approval_id")
    revoke.add_argument("--expected-revision", type=int)

    events = commands.add_parser("events", help="show durable events")
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--limit", type=int, default=200)

    artifacts = commands.add_parser("artifacts", help="list immutable artifacts linked to the session")
    artifacts.add_argument("--record-type", help="only show this provenance record type")

    artifact_read = commands.add_parser("artifact-read", help="read one verified session artifact")
    artifact_read.add_argument("artifact_id")
    artifact_read.add_argument("--output", type=Path, help="write bytes to this path")
    artifact_read.add_argument("--max-bytes", type=int, default=4_000_000)

    jobs = commands.add_parser("jobs", help="list durable Codex jobs")
    jobs.add_argument("--state", choices=("admitted", "running", "interrupted", "completed", "failed", "unknown"))

    job_interrupt = commands.add_parser("job-interrupt", help="request interruption from the live coordinator")
    job_interrupt.add_argument("job_id")
    job_interrupt.add_argument(
        "--coordinator-url",
        default="http://127.0.0.1:8765",
        help="loopback or private Tailscale HTTPS coordinator URL",
    )

    operation_reconcile = commands.add_parser(
        "operation-reconcile", help="resolve an unknown-effect operation from evidence"
    )
    operation_reconcile.add_argument("operation_id")
    operation_reconcile.add_argument(
        "resolved_state", choices=("succeeded", "failed", "no_effect")
    )
    operation_reconcile.add_argument("--evidence", action="append", required=True, dest="evidence_ids")
    operation_reconcile.add_argument("--note", required=True)

    usage_resolve = commands.add_parser(
        "usage-resolve", help="close uncertain Codex usage with a conservative token charge"
    )
    usage_resolve.add_argument("upper_bound_tokens", type=int)
    usage_resolve.add_argument("--evidence", required=True)
    usage_resolve.add_argument(
        "--owner-decision",
        action="store_true",
        help="record that the bound is an explicit owner decision",
    )

    export = commands.add_parser("export", help="write a JSON evidence export")
    export.add_argument("path", type=Path)

    backup = commands.add_parser("backup", help="write a consistent SQLite backup")
    backup.add_argument("path", type=Path)

    bundle = commands.add_parser("backup-bundle", help="write a verified database and artifact archive")
    bundle.add_argument("path", type=Path)

    commands.add_parser("reconcile", help="reconcile incomplete durable state")
    commands.add_parser("diagnostics", help="show host and adapter readiness")
    commands.add_parser("replay-demo", help="run a complete deterministic replay cycle")

    procedure_register = commands.add_parser(
        "procedure-register", help="validate and freeze an explicit typed procedure draft"
    )
    procedure_register.add_argument("path", type=Path, help="Codex procedure_draft_candidate JSON")
    procedure_review = commands.add_parser(
        "procedure-review", help="record a separate completed review against an exact procedure revision"
    )
    procedure_review.add_argument("path", type=Path, help="Codex procedure_review JSON")
    procedure_review.add_argument("--reviewer-job", required=True, help="completed job created with --kind review")

    science = commands.add_parser("science", help="publish and inspect validated scientific records")
    science_commands = science.add_subparsers(dest="science_action", required=True)
    science_publish = science_commands.add_parser("publish", help="validate and publish one record JSON file")
    science_publish.add_argument("path", type=Path)
    science_decision = science_commands.add_parser(
        "decision", help="validate and publish the scientific_decision from Codex output"
    )
    decision_source = science_decision.add_mutually_exclusive_group(required=True)
    decision_source.add_argument("path", nargs="?", type=Path, help="completed Codex output JSON")
    decision_source.add_argument("--job-id", help="read the completed Codex output from this durable job")
    science_commands.add_parser("list", help="list validated scientific records")
    science_commands.add_parser("brief", help="build a compact evidence brief")
    science_derive = science_commands.add_parser(
        "derive", help="derive and publish a power result from published observations"
    )
    science_derive.add_argument("path", type=Path, help="JSON derivation specification")
    science_checkpoint = science_commands.add_parser(
        "checkpoint", help="record the required redesign checkpoint from a Codex output JSON"
    )
    science_checkpoint.add_argument("path", type=Path)
    science_checkpoint.add_argument("--hypothesis-id", required=True)

    investigate = commands.add_parser("investigate", help="run one bounded Codex evidence turn")
    investigate.add_argument("instruction")
    investigate.add_argument("--evidence", action="append", type=Path, default=[])
    investigate.add_argument("--kind", choices=("investigate", "analyze", "review", "conclude"), default="investigate")
    investigate.add_argument("--procedure-id", help="exact procedure ID to review; required with --kind review")
    investigate.add_argument("--estimated-tokens", type=int, default=100_000)
    investigate.add_argument("--estimated-minutes", type=int, default=15)
    investigate.add_argument("--deadline-minutes", type=int, default=15)
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    settings = Settings.from_env()
    core = CoreApp.open(settings.paths)
    try:
        result = _dispatch(args, settings, core)
        if result is not None:
            _print(result, args.json)
    except (CoreError, ValueError, OSError) as exc:
        print(f"m1lab: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    finally:
        core.close()


def _dispatch(args: argparse.Namespace, settings: Settings, core: CoreApp) -> Any:
    if args.action == "init":
        if args.hours <= 0 or args.tokens <= 0:
            raise ValueError("hours and tokens must be positive")
        record = core.create_session(
            SessionCreate(
                objective=args.objective,
                owner=args.owner or settings.owner_login or "local-dev",
                host_identity=args.host_identity,
                target_identity=args.target_identity,
                active_seconds=round(args.hours * 3600),
                token_limit=args.tokens,
                policy={"hardware_adapter": settings.hardware_adapter, "model": settings.model},
            )
        )
        return record.model_dump(mode="json")
    if args.action == "sessions":
        return [item.model_dump(mode="json") for item in core.list_sessions()]

    session_id = args.session or latest_session_id(core)
    if session_id is None:
        raise ValueError("no session exists; run 'm1lab init' first")
    session = core.session(session_id)

    if args.action == "status":
        return core.snapshot(session_id).model_dump(mode="json")
    if args.action == "serve":
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("serve must bind to loopback; use Tailscale Serve for remote access")
        investigator = None
        if settings.codex_runtime == "app-server":
            _prepare_workspace(settings.workspace)
            investigator = InvestigationOrchestrator(
                core,
                _codex_adapter(settings),
                workspace=settings.workspace,
                host_blockers=_host_blocker_reader(settings),
            )
        elif settings.codex_runtime != "disabled":
            raise ValueError("M1LAB_CODEX_RUNTIME must be 'disabled' or 'app-server'")
        facade = CoordinatorFacade(
            core,
            session_id,
            investigator=investigator,
            model=settings.model,
            workspace=settings.workspace,
            push_config=PushConfig(
                public_key=settings.vapid_public_key,
                private_key=settings.vapid_private_key,
                subject=settings.vapid_subject,
            ),
        )
        web_settings = WebSettings(
            trust_tailscale_headers=settings.trust_tailscale_headers,
            owner_login=settings.owner_login,
            csrf_secret=settings.csrf_secret,
            vapid_public_key=settings.vapid_public_key,
            vapid_private_key=settings.vapid_private_key,
            vapid_subject=settings.vapid_subject,
        )
        with _coordinator_lease(settings.paths.root / "coordinator.lock"):
            core.reconcile()
            uvicorn.run(create_app(facade, web_settings), host=args.host, port=args.port)
        return None
    if args.action == "control":
        return _submit(core, session, CommandKind(args.command), {}, args.expected_revision)
    if args.action == "steer":
        return _submit(core, session, CommandKind.STEER, {"message": args.message}, args.expected_revision)
    if args.action == "budget":
        if args.amount <= 0:
            raise ValueError("amount must be positive")
        if args.command == "add-tokens":
            kind, payload = CommandKind.GRANT_TOKENS, {"tokens": args.amount}
        elif args.command == "extend-time":
            kind, payload = CommandKind.EXTEND_TIME, {"seconds": args.amount * 60}
        else:
            kind, payload = CommandKind.RESET_TIME, {"seconds": args.amount * 60}
        return _submit(core, session, kind, payload, args.expected_revision)
    if args.action == "approve":
        procedure = _procedure(core, session_id, args.procedure_id, args.procedure_revision)
        target = core.snapshot(session_id).latest_target
        if target is None:
            raise ValueError("approval requires a current target snapshot")
        from datetime import timedelta
        from m1lab.core.models import utc_now

        payload = {
            "procedure_id": procedure["procedure_id"],
            "procedure_revision": procedure["revision"],
            "scope": {
                "target_identity": target.identity,
                "boot_epoch": target.boot_epoch,
                "configuration_digest": target.configuration_digest,
                "repeat_limit": args.repeat,
                "expires_at": (utc_now() + timedelta(minutes=args.minutes)).isoformat(),
                "physical_attendance_confirmed": args.physical_attendance,
            },
        }
        return _submit(core, session, CommandKind.APPROVE, payload, args.expected_revision)
    if args.action == "deny":
        procedure = _procedure(core, session_id, args.procedure_id, args.procedure_revision)
        return _submit(
            core,
            session,
            CommandKind.DENY,
            {
                "procedure_id": procedure["procedure_id"],
                "procedure_revision": procedure["revision"],
                "procedure_digest": procedure["digest"],
            },
            args.expected_revision,
        )
    if args.action == "revoke":
        return _submit(core, session, CommandKind.REVOKE, {"approval_id": args.approval_id}, args.expected_revision)
    if args.action == "events":
        return [item.model_dump(mode="json") for item in core.events(session_id, after=args.after, limit=args.limit)]
    if args.action == "artifacts":
        return [
            item.model_dump(mode="json")
            for item in core.artifacts(session_id, record_type=args.record_type)
        ]
    if args.action == "artifact-read":
        linked = {item.id: item for item in core.artifacts(session_id)}
        record = linked.get(args.artifact_id)
        if record is None:
            raise ValueError("artifact is not linked to the selected session")
        content = core.read_session_artifact(
            session_id, args.artifact_id, max_bytes=args.max_bytes
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(content)
            return {
                "path": str(args.output),
                "artifact_id": record.id,
                "sha256": record.sha256,
                "size_bytes": len(content),
            }
        if not record.media_type.startswith(("text/", "application/json", "application/vnd.m1lab.")):
            raise ValueError("binary artifact requires --output PATH")
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("artifact is not UTF-8 text; use --output PATH") from exc
        return {"artifact": record.model_dump(mode="json"), "text": text_content}
    if args.action == "jobs":
        records = core.list_records(session_id, "jobs")
        if args.state:
            records = [item for item in records if item.state == args.state]
        return [item.model_dump(mode="json") for item in records]
    if args.action == "job-interrupt":
        job = core.job(args.job_id)
        if job.session_id != session_id:
            raise ValueError("job does not belong to the selected session")
        return _request_job_interrupt(args.coordinator_url, args.job_id)
    if args.action == "operation-reconcile":
        operation = next(
            (item for item in core.list_records(session_id, "operations") if item.id == args.operation_id),
            None,
        )
        if operation is None:
            raise ValueError("operation does not belong to the selected session")
        linked_ids = {item.id for item in core.artifacts(session_id)}
        missing = sorted(set(args.evidence_ids) - linked_ids)
        if missing:
            raise ValueError("evidence artifacts are not linked to the session: " + ", ".join(missing))
        from m1lab.core import OperationState

        core.reconcile_operation(
            args.operation_id,
            resolved_state=OperationState(args.resolved_state),
            evidence_artifact_ids=args.evidence_ids,
            note=args.note,
        )
        return next(
            item.model_dump(mode="json")
            for item in core.list_records(session_id, "operations")
            if item.id == args.operation_id
        )
    if args.action == "usage-resolve":
        if args.upper_bound_tokens < 0:
            raise ValueError("upper_bound_tokens must be nonnegative")
        if not core.session(session_id).usage_uncertain:
            raise ValueError("session usage is not uncertain")
        core.resolve_usage_uncertainty(
            session_id,
            upper_bound_tokens=args.upper_bound_tokens,
            evidence=args.evidence,
            owner_decision=args.owner_decision,
        )
        return core.snapshot(session_id).model_dump(mode="json")
    if args.action == "export":
        payload = CoordinatorFacade(core, session_id).export()
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return {"path": str(args.path), "events": len(payload["events"])}
    if args.action == "backup":
        core.journal.backup_database(args.path)
        return {"path": str(args.path)}
    if args.action == "backup-bundle":
        return _backup_bundle(core, args.path)
    if args.action == "reconcile":
        return core.reconcile().model_dump(mode="json")
    if args.action == "diagnostics":
        codex_tool = _tool_version(settings.codex_executable)
        codex_path = codex_tool.get("path")
        codex_sha256_actual = None
        codex_pin_matches = False
        if codex_path:
            try:
                codex_sha256_actual = _file_sha256_path(Path(codex_path))
                codex_pin_matches = bool(settings.codex_sha256) and (
                    codex_sha256_actual.lower() == settings.codex_sha256.lower()
                )
            except OSError:
                pass
        if settings.codex_runtime == "disabled":
            codex_readiness = "disabled"
        elif not codex_tool.get("available"):
            codex_readiness = "executable_unavailable"
        elif not settings.codex_sha256:
            codex_readiness = "executable_pin_missing"
        elif not codex_pin_matches:
            codex_readiness = "executable_pin_mismatch"
        else:
            codex_readiness = "executable_pinned_live_turn_unqualified"
        return {
            "app_version": "0.1.0",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "data_root": str(settings.paths.root),
            "database": str(settings.paths.database),
            "session_id": session_id,
            "configured_hardware": settings.hardware_adapter,
            "live_hardware_qualified": False,
            "unqualified_hardware_gates": [
                "ThinkPad-to-Mac transport and target identity",
                "proxy, hypervisor, and native mode recovery",
                "native result channel and power measurement",
            ],
            "codex_model": settings.model,
            "codex_runtime": settings.codex_runtime,
            "codex_readiness": codex_readiness,
            "codex_cli": codex_tool,
            "codex_executable": settings.codex_executable,
            "codex_sha256": settings.codex_sha256 or None,
            "codex_sha256_actual": codex_sha256_actual,
            "codex_sha256_matches": codex_pin_matches,
            "workspace": str(settings.workspace),
            "tailscale_cli": _tool_version("tailscale"),
            "tailscale_headers": settings.trust_tailscale_headers,
            "owner_login": settings.owner_login,
        }
    if args.action == "replay-demo":
        return _replay_demo(core, session_id)
    if args.action == "procedure-register":
        document = json.loads(args.path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("procedure draft must be a JSON object")
        candidate = document.get("procedure_draft_candidate", document)
        if not isinstance(candidate, dict):
            raise ValueError("procedure_draft_candidate must be a JSON object")
        if "session_id" in candidate and candidate["session_id"] != session_id:
            raise ValueError("procedure draft belongs to a different session")
        candidate = dict(candidate)
        for field in ("operations", "cleanup"):
            normalized_operations = []
            for operation in candidate.get(field, []):
                if not isinstance(operation, dict):
                    raise ValueError(f"procedure {field} entries must be objects")
                normalized_operations.append(
                    {
                        **operation,
                        "parameters": _key_value_entries(
                            operation.get("parameters", []), f"{field} parameters"
                        ),
                    }
                )
            if field in candidate:
                candidate[field] = normalized_operations
        if "limits" in candidate:
            candidate["limits"] = _key_value_entries(candidate["limits"], "procedure limits")
        draft = ProcedureDraft.model_validate({**candidate, "session_id": session_id})
        return core.register_procedure(draft).model_dump(mode="json")
    if args.action == "procedure-review":
        document = json.loads(args.path.read_text(encoding="utf-8"))
        review_document = document.get("procedure_review", document) if isinstance(document, dict) else None
        if not isinstance(review_document, dict):
            raise ValueError("procedure review must be a JSON object")
        review = ReviewRecord.model_validate(
            {**review_document, "session_id": session_id, "reviewer_job_id": args.reviewer_job}
        )
        return core.record_review(review).model_dump(mode="json")
    if args.action == "science":
        store = ScientificRecordStore(core)
        if args.science_action == "list":
            return [item.model_dump(mode="json") for item in store.list(session_id)]
        if args.science_action == "brief":
            published = store.list(session_id)
            if not published:
                raise ValueError("no scientific records are published for this session")
            return store.brief(published[:64]).model_dump(mode="json")
        document = (
            _completed_codex_output(core, session_id, args.job_id)
            if args.science_action == "decision" and args.job_id
            else json.loads(args.path.read_text(encoding="utf-8"))
        )
        if args.science_action == "publish":
            payload = document.get("record", document) if isinstance(document, dict) else document
            record = TypeAdapter(ScientificRecord).validate_python(payload)
            if record.session_id != session_id:
                raise ValueError("scientific record belongs to a different session")
            return store.publish(record).model_dump(mode="json")
        if args.science_action == "derive":
            return _derive_scientific_result(store, session_id, document)
        if args.science_action == "decision":
            return _publish_codex_decision(store, session_id, document)
        if args.science_action == "checkpoint":
            checkpoint = document.get("redesign_checkpoint") if isinstance(document, dict) else None
            if not isinstance(checkpoint, dict) or checkpoint.get("required") is not True:
                raise ValueError("Codex output does not require a redesign checkpoint")
            hypothesis = next(
                (
                    item.record
                    for item in store.list(session_id)
                    if isinstance(item.record, HypothesisRecord)
                    and item.record.id == args.hypothesis_id
                ),
                None,
            )
            if hypothesis is None:
                raise ValueError("hypothesis is not published in this session")
            record = RedesignCheckpointRecord(
                session_id=session_id,
                hypothesis_id=hypothesis.id,
                mode=hypothesis.mode,
                triggering_result_ids=tuple(checkpoint.get("result_refs", ())),
                findings=str(checkpoint.get("findings", "")),
                redesign=str(checkpoint.get("redesign", "")),
            )
            return store.publish(record).model_dump(mode="json")
        raise AssertionError(args.science_action)
    if args.action == "investigate":
        if settings.codex_runtime != "app-server":
            raise ValueError("set M1LAB_CODEX_RUNTIME=app-server to admit Codex jobs")
        _prepare_workspace(settings.workspace)
        evidence = []
        for path in args.evidence:
            content = path.read_text(encoding="utf-8")
            evidence.append(EvidenceExcerpt(label=path.name, content=content))
        request = InvestigationRequest(
            session_id=session_id,
            instruction=args.instruction,
            cwd=settings.workspace,
            model=settings.model,
            kind=args.kind,
            review_procedure_id=args.procedure_id,
            estimated_tokens=args.estimated_tokens,
            estimated_active_seconds=args.estimated_minutes * 60,
            deadline_seconds=args.deadline_minutes * 60,
            evidence=evidence,
        )
        return asyncio.run(_run_investigation(core, request, settings))
    raise AssertionError(args.action)


def _key_value_entries(values: Any, label: str) -> dict[str, Any]:
    if isinstance(values, dict):
        return values
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of name/value entries")
    result: dict[str, Any] = {}
    for entry in values:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or "value" not in entry:
            raise ValueError(f"{label} entries require a string name and a value")
        if entry["name"] in result:
            raise ValueError(f"{label} contains duplicate name {entry['name']!r}")
        result[entry["name"]] = entry["value"]
    return result


def _derive_scientific_result(
    store: ScientificRecordStore, session_id: str, document: Any
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("derivation specification must be a JSON object")
    pairs = document.get("observation_pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("derivation requires a non-empty observation_pairs array")
    normalized_pairs: list[tuple[str, str]] = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) for item in pair):
            raise ValueError("each observation pair must be [baseline_id, changed_id]")
        normalized_pairs.append((pair[0], pair[1]))
    published = store.derive_and_publish(
        session_id=session_id,
        hypothesis_id=str(document.get("hypothesis_id", "")),
        protocol_id=str(document.get("protocol_id", "")),
        observation_pairs=normalized_pairs,
        adherence=ProtocolAdherence.model_validate(document.get("adherence", {})),
        regressions=tuple(
            RegressionCheck.model_validate(item) for item in document.get("regressions", [])
        ),
        exclusions=tuple(Exclusion.model_validate(item) for item in document.get("exclusions", [])),
        analysis_code_refs=tuple(document.get("analysis_code_refs", [])),
    )
    return published.model_dump(mode="json")


def _completed_codex_output(core: CoreApp, session_id: str, job_id: str) -> dict[str, Any]:
    job = core.job(job_id)
    if job.session_id != session_id:
        raise ValueError("Codex job does not belong to the selected session")
    if job.state != "completed":
        raise ValueError("scientific decisions can only be published from a completed Codex job")
    artifact_ids = job.result.get("event_artifact_ids", [])
    if not isinstance(artifact_ids, list) or any(not isinstance(item, str) for item in artifact_ids):
        raise ValueError("completed Codex job has no valid runtime event artifact list")

    for artifact_id in reversed(artifact_ids):
        try:
            raw = core.read_session_artifact(session_id, artifact_id, max_bytes=4_000_000)
            envelope = json.loads(raw.decode("utf-8"))
            if not isinstance(envelope, dict) or envelope.get("method") != "item/completed":
                continue
            payload = json.loads(envelope.get("payload_json", "null"))
        except (CoreError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            continue
        for candidate in reversed(_structured_output_candidates(payload)):
            if isinstance(candidate.get("scientific_decision"), dict):
                return candidate
    raise ValueError("completed Codex job contains no structured scientific_decision output")


def _structured_output_candidates(value: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "scientific_decision" in current:
                candidates.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str):
            try:
                stack.append(json.loads(current))
            except (json.JSONDecodeError, RecursionError):
                continue
    return candidates


def _publish_codex_decision(
    store: ScientificRecordStore, session_id: str, document: Any
) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("scientific_decision"), dict):
        raise ValueError("Codex output must contain a non-null scientific_decision object")
    payload = document["scientific_decision"]
    decision_fields = {
        "hypothesis_id", "protocol_id", "derived_result_id", "conclusion", "decision_delta",
        "next_action", "evidence", "counterevidence", "unresolved_uncertainties",
    }
    if set(payload) != decision_fields:
        raise ValueError("scientific_decision has unknown or missing fields")
    for name in (
        "hypothesis_id", "protocol_id", "derived_result_id", "conclusion", "decision_delta", "next_action"
    ):
        if not isinstance(payload[name], str):
            raise ValueError(f"scientific_decision.{name} must be a string")
    uncertainties = payload["unresolved_uncertainties"]
    if not isinstance(uncertainties, list) or any(not isinstance(item, str) for item in uncertainties):
        raise ValueError("scientific_decision.unresolved_uncertainties must be a string array")
    records = {item.record.id: item.record for item in store.list(session_id)}
    hypothesis_id = payload["hypothesis_id"]
    protocol_id = payload["protocol_id"]
    result_id = payload["derived_result_id"]
    result = records.get(result_id)
    if not isinstance(result, DerivedResultRecord):
        raise ValueError("scientific_decision must cite a published derived_result in this session")
    if result.hypothesis_id != hypothesis_id or result.protocol_id != protocol_id:
        raise ValueError("scientific_decision hypothesis and protocol must match the derived result")

    claims: dict[str, list[ClaimEvidence]] = {"evidence": [], "counterevidence": []}
    for collection, direction in (
        ("evidence", EvidenceDirection.SUPPORTS),
        ("counterevidence", EvidenceDirection.COUNTERS),
    ):
        entries = payload.get(collection, [])
        if not isinstance(entries, list):
            raise ValueError(f"scientific_decision.{collection} must be an array")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"scientific_decision.{collection} entries must be objects")
            claim_fields = {
                "claim", "strength", "rationale", "record_refs", "artifact_refs", "limitations"
            }
            if set(entry) != claim_fields:
                raise ValueError(f"scientific_decision.{collection} claim has unknown or missing fields")
            claims[collection].append(
                ClaimEvidence.model_validate(
                    {
                        **entry,
                        "session_id": session_id,
                        "hypothesis_id": hypothesis_id,
                        "mode": result.mode,
                        "direction": direction,
                    }
                )
            )
    all_claims = (*claims["evidence"], *claims["counterevidence"])
    if not any(result_id in claim.record_refs for claim in all_claims):
        raise ValueError("at least one decision claim must cite the exact derived_result_id")

    decision = DecisionRecord(
        session_id=session_id,
        hypothesis_id=hypothesis_id,
        protocol_id=protocol_id,
        derived_result_id=result_id,
        mode=result.mode,
        outcome=result.outcome,
        conclusion=payload["conclusion"],
        decision_delta=payload["decision_delta"],
        next_action=payload["next_action"],
        evidence=tuple(claims["evidence"]),
        counterevidence=tuple(claims["counterevidence"]),
        unresolved_uncertainties=tuple(uncertainties),
    )
    published_claims = store.publish_many(all_claims)
    published_decision = store.publish(decision)
    return {
        "decision": published_decision.model_dump(mode="json"),
        "claim_evidence": [item.model_dump(mode="json") for item in published_claims],
    }


def _submit(core: CoreApp, session: Any, kind: CommandKind, payload: dict[str, Any], revision: int | None) -> dict[str, Any]:
    result = core.submit(
        OwnerCommand(
            id=new_id("cmd"),
            session_id=session.id,
            owner=session.owner,
            kind=kind,
            expected_revision=revision if revision is not None else core.session(session.id).revision,
            payload=payload,
        )
    )
    return result.model_dump(mode="json")


def _procedure(core: CoreApp, session_id: str, procedure_id: str, revision: int) -> dict[str, Any]:
    rows = core.list_records(session_id, "procedures")
    for record in rows:
        if record.procedure_id == procedure_id and record.revision == revision:
            return record.model_dump(mode="json")
    raise ValueError(f"procedure {procedure_id} revision {revision} does not exist")


def _record_replay_review(
    core: CoreApp,
    procedure: ProcedureRecord,
    *,
    scope: str,
    concerns: list[str],
) -> ReviewRecord:
    now = utc_now()
    reviewer = core.create_job(
        JobCreate(
            session_id=procedure.session_id,
            kind="review",
            evidence_manifest={
                "procedure_id": procedure.procedure_id,
                "procedure_revision": procedure.revision,
                "procedure_digest": procedure.digest,
                "review_target": {
                    "procedure_id": procedure.procedure_id,
                    "procedure_revision": procedure.revision,
                    "procedure_digest": procedure.digest,
                },
                "mode": "deterministic-host-review",
            },
            lease_expires_at=now + timedelta(minutes=1),
            deadline_at=now + timedelta(minutes=2),
        )
    )
    core.update_job(
        reviewer.id,
        state="running",
        runtime_id="host-review",
        result={"scope": scope},
    )
    core.update_job(
        reviewer.id,
        state="completed",
        runtime_id="host-review",
        result={"disposition": "accepted", "scope": scope},
    )
    return core.record_review(
        ReviewRecord(
            session_id=procedure.session_id,
            procedure_id=procedure.procedure_id,
            procedure_revision=procedure.revision,
            procedure_digest=procedure.digest,
            reviewer_job_id=reviewer.id,
            disposition=ReviewDisposition.ACCEPTED,
            concerns=concerns,
        )
    )


def _replay_demo(core: CoreApp, session_id: str) -> dict[str, Any]:
    """Exercise observe, review, authorization, execution and evidence storage."""

    session = core.session(session_id)
    if session.phase is SessionPhase.PREPARING:
        _submit(core, session, CommandKind.START, {}, session.revision)
    elif session.phase not in {SessionPhase.INVESTIGATING, SessionPhase.INTERPRETING}:
        raise ValueError(f"replay demo requires an active session, not {session.phase.value}")

    read = InspectRegister(address=0x1000, width_bytes=4)
    wait = WaitForReplay(duration_ms=5)
    reboot = SimulateBoot(next_boot_epoch="replay-demo-2")
    adapter = ReplayHardwareAdapter(
        [
            ReplayStep(read, values={"address": "0x1000", "value": 0xA1B2C3D4}),
            ReplayStep(wait, values={"elapsed_ms": 5}),
            ReplayStep(reboot, values={"boot_epoch": reboot.next_boot_epoch}),
        ],
        target_id="replay-m1",
        boot_epoch="replay-demo-1",
    )
    experiments = ExperimentService(core, adapter)
    target = experiments.inspect_and_record(session_id, fresh_for_seconds=300)

    procedure = core.register_procedure(
        ProcedureDraft(
            session_id=session_id,
            title="Replay register observation",
            operations=[
                TypedOperation(
                    kind="inspect_register",
                    parameters={"address": read.address, "width_bytes": read.width_bytes},
                    mutates_target=False,
                    timeout_seconds=5,
                ),
                TypedOperation(
                    kind="wait",
                    parameters={"duration_ms": wait.duration_ms},
                    mutates_target=False,
                    timeout_seconds=5,
                ),
            ],
            prerequisites={"inspect_register", "wait"},
            limits={"steps": 2, "mode": "replay"},
            abort_conditions=["target identity or boot epoch changes"],
            recovery={"summary": "No physical target is involved."},
            expected_benefit="Prove the durable replay evidence cycle without claiming M1 behavior.",
            failure_severity="low",
        )
    )
    review = _record_replay_review(
        core,
        procedure,
        scope="replay-only structural review",
        concerns=["Replay results cannot establish physical power behavior."],
    )
    report = experiments.authorize_and_run(
        DispatchRequest(
            session_id=session_id,
            procedure_id=procedure.procedure_id,
            procedure_revision=procedure.revision,
            target_snapshot_id=target.id,
            adapter_mode=TargetMode.REPLAY,
            estimated_active_seconds=10,
        )
    )
    mutating = core.register_procedure(
        ProcedureDraft(
            session_id=session_id,
            title="Replay boot transition",
            operations=[
                TypedOperation(
                    kind="simulate_boot",
                    parameters={"next_boot_epoch": reboot.next_boot_epoch},
                    mutates_target=True,
                    timeout_seconds=10,
                )
            ],
            prerequisites={"simulate_boot"},
            limits={"steps": 1, "mode": "replay"},
            abort_conditions=["target identity or boot epoch changes before dispatch"],
            recovery={"summary": "Replay state can be recreated from the trace."},
            expected_benefit="Exercise exact approval and mutating dispatch without physical hardware.",
            failure_severity="low",
        )
    )
    mutating_review = _record_replay_review(
        core,
        mutating,
        scope="replay-only mutation review",
        concerns=["The simulated boot is host replay and cannot establish M1 behavior."],
    )
    approval_target = core.snapshot(session_id).latest_target
    if approval_target is None:
        raise ValueError("replay target disappeared before approval")
    approval = _submit(
        core,
        core.session(session_id),
        CommandKind.APPROVE,
        {
            "procedure_id": mutating.procedure_id,
            "procedure_revision": mutating.revision,
            "procedure_digest": mutating.digest,
            "scope": {
                "target_identity": approval_target.identity,
                "boot_epoch": approval_target.boot_epoch,
                "configuration_digest": approval_target.configuration_digest,
                "repeat_limit": 1,
                "expires_at": (utc_now() + timedelta(minutes=15)).isoformat(),
                "physical_attendance_confirmed": False,
            },
        },
        None,
    )
    if approval["status"] != "applied":
        raise ValueError(f"replay approval failed: {approval['outcome']}")
    mutating_report = experiments.authorize_and_run(
        DispatchRequest(
            session_id=session_id,
            procedure_id=mutating.procedure_id,
            procedure_revision=mutating.revision,
            target_snapshot_id=approval_target.id,
            adapter_mode=TargetMode.REPLAY,
            estimated_active_seconds=10,
        )
    )
    scientific = ScientificRecordStore(core).publish(
        HypothesisRecord(
            session_id=session_id,
            mode=StudyMode.EXPLORATION,
            statement=(
                "Host replay only: the workflow preserves exact review, approval, execution, "
                "and evidence lineage but cannot establish physical M1 behavior."
            ),
            proposed_mechanism="Deterministic typed replay exercises coordinator boundaries without a physical target.",
            predicted_effect="Both replay procedures finish with durable evidence and consistent operator readback.",
            primary_metric="workflow completion",
            falsifiers=("Any result is represented as evidence about physical M1 power behavior.",),
        )
    )
    final_phase = core.session(session_id).phase
    return {
        "session_id": session_id,
        "target_snapshot_id": target.id,
        "procedure_id": procedure.procedure_id,
        "procedure_revision": procedure.revision,
        "review_id": review.id,
        "execution": report.model_dump(mode="json"),
        "read_only": {
            "procedure_id": procedure.procedure_id,
            "review_id": review.id,
            "operation_id": report.operation_id,
            "state": report.state,
        },
        "mutating": {
            "procedure_id": mutating.procedure_id,
            "review_id": mutating_review.id,
            "operation_id": mutating_report.operation_id,
            "state": mutating_report.state,
        },
        "scientific_evidence": {
            "record_id": scientific.record.id,
            "artifact_id": scientific.artifact_id,
            "limitation": "Replay evidence validates the host workflow only and cannot establish M1 behavior.",
        },
        "final_phase": final_phase,
        "qualification": "host replay only; cannot establish behavior on a physical M1 target",
    }


async def _run_investigation(
    core: CoreApp, request: InvestigationRequest, settings: Settings
) -> dict[str, Any]:
    orchestrator = InvestigationOrchestrator(
        core,
        _codex_adapter(settings),
        workspace=settings.workspace,
        host_blockers=_host_blocker_reader(settings),
    )
    try:
        launch = await orchestrator.start(request)
        record = await orchestrator.wait(launch.job_id)
        return record.model_dump(mode="json")
    finally:
        await orchestrator.close()


def _host_blocker_reader(settings: Settings):
    monitor = LinuxHostMonitor(settings.paths.root)
    policy = HostAdmissionPolicy()
    return lambda: policy.blockers(monitor.sample())


def _codex_adapter(settings: Settings) -> AppServerCodexAdapter:
    return AppServerCodexAdapter(
        executable=settings.codex_executable,
        expected_sha256=settings.codex_sha256,
    )


def _prepare_workspace(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"Codex workspace is not a directory: {path}")


def _request_job_interrupt(base_url: str, job_id: str) -> dict[str, Any]:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("coordinator URL must be an http(s) origin without query or fragment")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    try:
        with opener.open(origin + "/overview", timeout=5) as response:
            response.read(1)
        csrf = next((cookie.value for cookie in cookies if cookie.name == "m1lab_csrf"), None)
        if csrf is None:
            raise ValueError("coordinator did not issue a CSRF token")
        request = Request(
            origin + f"/api/jobs/{job_id}/interrupt",
            data=b"",
            method="POST",
            headers={"Origin": origin, "X-CSRF-Token": csrf},
        )
        with opener.open(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise ValueError(f"coordinator rejected interruption ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise ValueError(f"could not reach live coordinator: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ValueError("coordinator returned an invalid interruption response")
    return payload


def _backup_bundle(core: CoreApp, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="m1lab-backup-", dir=destination.parent
        ) as temporary:
            database = Path(temporary) / "m1lab.sqlite3"
            core.journal.backup_database(database)
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            try:
                artifacts = connection.execute(
                    "SELECT id, sha256, size_bytes, relative_path, available FROM artifacts ORDER BY id"
                ).fetchall()
                dangling = connection.execute(
                    "SELECT COUNT(*) FROM artifact_links l LEFT JOIN artifacts a "
                    "ON a.id=l.artifact_id WHERE a.id IS NULL"
                ).fetchone()[0]
            finally:
                connection.close()
            if dangling:
                raise ValueError("backup database has artifact links without artifact metadata")
            unavailable = [row["id"] for row in artifacts if not row["available"]]
            if unavailable:
                raise ValueError(
                    "backup cannot omit unavailable referenced artifacts: "
                    + ", ".join(unavailable[:8])
                )
            required_bytes = 2 * database.stat().st_size + sum(
                int(row["size_bytes"]) for row in artifacts
            ) + 1024 * 1024
            free_bytes = shutil.disk_usage(destination.parent).free
            if free_bytes - required_bytes < JOURNAL_DISK_RESERVE_BYTES:
                raise ValueError(
                    "backup admission stopped to preserve the disk reserve "
                    f"({free_bytes} bytes free; "
                    f"{required_bytes + JOURNAL_DISK_RESERVE_BYTES} bytes required)"
                )
            handle, partial_name = tempfile.mkstemp(
                prefix=".m1lab-backup-", suffix=".partial", dir=destination.parent
            )
            os.close(handle)
            partial = Path(partial_name)
            manifest = {"format": "m1lab-backup-v1", "artifacts": []}
            try:
                with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(database, "m1lab.sqlite3")
                    for row in artifacts:
                        source = core.journal.paths.artifacts / row["relative_path"]
                        if (
                            not source.is_file()
                            or source.stat().st_size != row["size_bytes"]
                            or _file_sha256_path(source) != row["sha256"]
                        ):
                            raise ValueError(
                                f"artifact {row['id']} failed backup integrity validation"
                            )
                        archive.write(source, f"artifacts/{row['relative_path']}")
                        manifest["artifacts"].append(
                            {
                                "id": row["id"],
                                "sha256": row["sha256"],
                                "size_bytes": row["size_bytes"],
                                "relative_path": row["relative_path"],
                            }
                        )
                    archive.writestr(
                        "manifest.json", json.dumps(manifest, indent=2, sort_keys=True)
                    )
                    for row in artifacts:
                        member = f"artifacts/{row['relative_path']}"
                        with archive.open(member) as stream:
                            digest = hashlib.sha256()
                            size = 0
                            for block in iter(lambda: stream.read(1024 * 1024), b""):
                                digest.update(block)
                                size += len(block)
                        if size != row["size_bytes"] or digest.hexdigest() != row["sha256"]:
                            raise ValueError(
                                f"artifact {row['id']} changed while the backup was written"
                            )
                with partial.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(partial, destination)
                directory_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                partial.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(f"backup could not be completed safely: {exc}") from exc
    return {"path": str(destination), "artifacts": len(manifest["artifacts"])}


def _file_sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tool_version(command: str) -> dict[str, Any]:
    executable = shutil.which(command)
    if executable is None:
        return {"available": False}
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "path": executable, "error": str(exc)}
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return {
        "available": completed.returncode == 0,
        "path": executable,
        "version": output[0][:300] if output else "unknown",
    }


@contextmanager
def _coordinator_lease(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another coordinator process owns this data directory") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _print(value: Any, json_mode: bool) -> None:
    if json_mode or isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        print(value)
