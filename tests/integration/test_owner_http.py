"""Host-only HTTP acceptance checks for the owner interface."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import socket
from threading import Thread
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

import pytest
import uvicorn

from m1lab.application import CoordinatorFacade
from m1lab.core.coordinator import CoreApp
from m1lab.core.models import SessionCreate
from m1lab.host import HostSnapshot
from m1lab.paths import AppPaths
from m1lab.web.app import WebSettings, create_app


OWNER_LOGIN = "owner@example.test"


class FixedHostMonitor:
    def sample(self) -> HostSnapshot:
        return HostSnapshot(
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            power_source="ac",
            battery_percent=None,
            maximum_temperature_c=40.0,
            thermal_state="normal",
            disk_free_bytes=20 * 1024**3,
            disk_total_bytes=40 * 1024**3,
        )


@contextmanager
def owner_server(tmp_path):
    core = CoreApp.open(AppPaths(tmp_path / "http-state"))
    listener = None
    thread = None
    server = None
    try:
        session = core.create_session(
            SessionCreate(
                objective="Isolated host-only HTTP acceptance",
                owner=OWNER_LOGIN,
                host_identity="synthetic-host",
            )
        )
        facade = CoordinatorFacade(
            core, session.id, host_monitor=FixedHostMonitor(), workspace=tmp_path
        )
        app = create_app(
            facade,
            WebSettings(
                trust_tailscale_headers=True,
                owner_login=OWNER_LOGIN,
                csrf_secret="test-only-http-acceptance-secret",
            ),
        )
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        listener.settimeout(0.2)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
        )
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = monotonic() + 5
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.01)
        if not server.started:
            raise RuntimeError("temporary owner HTTP server did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if listener is not None:
            listener.close()
        core.close()
        if thread is not None and thread.is_alive():
            raise RuntimeError("temporary owner HTTP server did not stop")


@pytest.fixture
def browser(tmp_path):
    with owner_server(tmp_path) as base_url:
        cookies = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookies))

        def request(path, *, method="GET", identity=OWNER_LOGIN, body=None, headers=None):
            request_headers = dict(headers or {})
            if identity is not None:
                request_headers["Tailscale-User-Login"] = identity
            data = None if body is None else json.dumps(body).encode()
            if data is not None:
                request_headers["Content-Type"] = "application/json"
            req = Request(base_url + path, data=data, headers=request_headers, method=method)
            try:
                response = opener.open(req, timeout=3)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read().decode()

        def csrf_token():
            return next(cookie.value for cookie in cookies if cookie.name == "m1lab_csrf")

        yield base_url, request, csrf_token


def read_stream_events(base_url, *, count, cursor="0", last_event_id=None):
    """Read a known finite replay, then close the otherwise unbounded response."""
    assert 0 < count <= 100
    headers = {"Tailscale-User-Login": OWNER_LOGIN, "Accept": "text/event-stream"}
    if last_event_id is not None:
        headers["Last-Event-ID"] = str(last_event_id)
    request = Request(f"{base_url}/api/events?cursor={cursor}", headers=headers)
    events = []
    fields = {}
    with build_opener().open(request, timeout=3) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-store"
        # Account for the initial retry directive and bound malformed framing.
        for _ in range(count * 8 + 10):
            line = response.readline(65_537)
            assert line, "SSE stream ended before the expected replay was complete"
            assert len(line) <= 65_536, "SSE frame line exceeded the fixture bound"
            text = line.decode().rstrip("\r\n")
            if not text:
                if "data" in fields:
                    events.append({"cursor": fields["id"], **json.loads(fields["data"])})
                    if len(events) == count:
                        return events
                fields = {}
            elif not text.startswith(":"):
                name, _, value = text.partition(":")
                fields[name] = value.removeprefix(" ")
    raise AssertionError("SSE replay exceeded the bounded frame count")


def test_exact_tailscale_owner_identity_is_required(browser):
    _, request, _ = browser
    for identity in (None, "other@example.test", "Owner@example.test"):
        status, headers, body = request("/overview", identity=identity)
        assert status == 403
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body)["detail"] == "Owner access required."


def test_all_owner_views_render_without_caching(browser):
    _, request, _ = browser
    for view, title in (
        ("overview", "Overview"),
        ("evidence", "Evidence"),
        ("approvals", "Approvals"),
        ("conversation", "Conversation"),
    ):
        status, headers, body = request(f"/{view}")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert headers.get_content_type() == "text/html"
        assert f"<title>{title}" in body
        assert 'name="m1lab-revision" content="1"' in body


def test_csrf_and_wrong_origin_reject_commands_without_state_change(browser):
    base_url, request, csrf_token = browser
    assert request("/overview")[0] == 200
    command = {
        "command_id": str(uuid4()),
        "kind": "session.start",
        "expected_revision": "1",
        "payload": {},
    }
    for headers in (
        {"Origin": base_url},
        {"Origin": "http://wrong.example.test", "X-CSRF-Token": csrf_token()},
        {"Origin": base_url, "X-CSRF-Token": "wrong-token"},
    ):
        status, _, body = request("/api/commands", method="POST", body=command, headers=headers)
        assert status == 403
        assert "CSRF token required" in json.loads(body)["detail"]
    status, _, body = request("/overview")
    assert status == 200
    assert 'name="m1lab-revision" content="1"' in body


def test_lifecycle_command_retries_and_conflicts_are_side_effect_free(browser):
    base_url, request, csrf_token = browser
    assert request("/overview")[0] == 200
    headers = {"Origin": base_url, "X-CSRF-Token": csrf_token()}
    command = {
        "command_id": str(uuid4()),
        "kind": "session.start",
        "expected_revision": "1",
        "payload": {},
    }
    status, _, body = request("/api/commands", method="POST", body=command, headers=headers)
    accepted = json.loads(body)
    assert status == 202
    assert accepted["status"] == "applied"
    assert accepted["revision"] == "2"
    status, _, export_after_start = request("/api/export")
    assert status == 200
    before = json.loads(export_after_start)

    status, _, body = request("/api/commands", method="POST", body=command, headers=headers)
    assert status == 202
    assert json.loads(body) == accepted

    mismatch = {**command, "kind": "session.pause"}
    status, _, body = request("/api/commands", method="POST", body=mismatch, headers=headers)
    assert status == 409
    assert json.loads(body)["status"] == "rejected"

    stale = {**command, "command_id": str(uuid4())}
    status, _, body = request("/api/commands", method="POST", body=stale, headers=headers)
    assert status == 409
    assert json.loads(body)["status"] == "rejected"
    assert json.loads(body)["revision"] == "2"

    status, _, exported = request("/api/export")
    assert status == 200
    after = json.loads(exported)
    assert after["session"]["revision"] == before["session"]["revision"] == 2
    assert after["session"]["phase"] == before["session"]["phase"] == "investigating"
    for kind in ("jobs", "operations", "approvals"):
        assert after["records"][kind] == before["records"][kind] == []


def test_sse_last_event_id_overrides_query_and_replays_strictly_after(browser):
    base_url, request, csrf_token = browser
    assert request("/overview")[0] == 200
    status, _, body = request(
        "/api/commands", method="POST",
        body={
            "command_id": str(uuid4()), "kind": "session.start",
            "expected_revision": "1", "payload": {},
        },
        headers={"Origin": base_url, "X-CSRF-Token": csrf_token()},
    )
    assert status == 202
    assert json.loads(body)["status"] == "applied"
    status, _, body = request("/api/export")
    assert status == 200
    exported = json.loads(body)
    recorded = exported["events"]
    assert len(recorded) >= 3
    resume_cursor = recorded[1]["cursor"]
    expected = [event for event in recorded if event["cursor"] > resume_cursor]

    replay = read_stream_events(
        base_url, count=len(expected), cursor="0", last_event_id=resume_cursor,
    )

    assert [int(event["cursor"]) for event in replay] == [event["cursor"] for event in expected]
    assert all(int(event["cursor"]) > resume_cursor for event in replay)
    assert [event["kind"] for event in replay] == [event["kind"] for event in expected]
    for actual, durable in zip(replay, expected, strict=True):
        assert actual["revision"] == str(exported["session"]["revision"])
        assert all(actual["payload"][key] == value for key, value in durable["data"].items())


def test_sse_reconnect_returns_authoritative_phase_change_while_disconnected(browser):
    base_url, request, csrf_token = browser
    assert request("/overview")[0] == 200
    status, _, body = request("/api/export")
    assert status == 200
    initial = json.loads(body)
    first_stream = read_stream_events(base_url, count=len(initial["events"]))
    last_cursor = int(first_stream[-1]["cursor"])
    assert last_cursor == initial["events"][-1]["cursor"]

    # The first response is closed before the owner changes authoritative state.
    status, _, body = request(
        "/api/commands", method="POST",
        body={
            "command_id": str(uuid4()), "kind": "session.start",
            "expected_revision": str(initial["session"]["revision"]), "payload": {},
        },
        headers={"Origin": base_url, "X-CSRF-Token": csrf_token()},
    )
    assert status == 202
    receipt = json.loads(body)
    assert receipt["status"] == "applied"
    status, _, body = request("/api/export")
    assert status == 200
    current = json.loads(body)
    missed = [event for event in current["events"] if event["cursor"] > last_cursor]
    assert missed

    replay = read_stream_events(base_url, count=len(missed), last_event_id=last_cursor)

    assert [int(event["cursor"]) for event in replay] == [event["cursor"] for event in missed]
    phase_changes = [event for event in replay if event["kind"] == "session.phase_changed"]
    assert len(phase_changes) == 1
    assert phase_changes[0]["payload"]["phase"] == current["session"]["phase"] == "investigating"
    assert phase_changes[0]["revision"] == receipt["revision"] == str(current["session"]["revision"])


@pytest.mark.parametrize("invalid_cursor", ["malformed", "ahead"])
def test_sse_invalid_cursor_requests_current_snapshot(browser, invalid_cursor):
    base_url, request, _ = browser
    status, _, body = request("/api/export")
    assert status == 200
    exported = json.loads(body)
    latest_cursor = exported["events"][-1]["cursor"]
    supplied = "not-a-cursor" if invalid_cursor == "malformed" else str(latest_cursor + 100)

    event, = read_stream_events(base_url, count=1, last_event_id=supplied)

    assert event["kind"] == "snapshot_required"
    assert event["revision"] == str(exported["session"]["revision"])
    if invalid_cursor == "ahead":
        assert event["cursor"] == str(latest_cursor)
        assert event["payload"]["reason"] == "event cursor is ahead of this session"
    else:
        assert event["cursor"] == ""
