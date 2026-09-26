"""Best-effort generic Web Push delivery, separate from authoritative workflow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from m1lab.core import CoreApp
from m1lab.core.journal import iso
from m1lab.core.models import EventRecord
from pywebpush import WebPushException, webpush


_LOG = logging.getLogger(__name__)
_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_PUSH_HOSTS = frozenset(
    {
        "web.push.apple.com",
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
    }
)
_PUSH_HOST_SUFFIXES = (".push.apple.com", ".fcm.googleapis.com", ".push.services.mozilla.com")
_RECOVERY_EVENTS = frozenset(
    {
        "operation.reconciled",
        "job.unknown",
        "job.usage_uncertain",
        "budget.usage_uncertain",
        "budget.active_time_reconciled",
        "artifact.unavailable",
        "host.readiness_blocked",
    }
)


@dataclass(frozen=True, slots=True)
class PushConfig:
    public_key: str = ""
    private_key: str = ""
    subject: str = ""

    @property
    def enabled(self) -> bool:
        key_file = Path(self.private_key) if self.private_key else None
        return bool(
            80 <= len(self.public_key) <= 256
            and _KEY.fullmatch(self.public_key)
            and key_file is not None
            and key_file.is_absolute()
            and key_file.is_file()
            and os.access(key_file, os.R_OK)
            and self.subject.startswith(("mailto:", "https://"))
        )


class PushNotifications:
    """Persist private subscriptions and send deduplicated generic alerts."""

    def __init__(
        self,
        core: CoreApp,
        session_id: str,
        config: PushConfig,
        *,
        owner_login: str,
    ) -> None:
        self._core = core
        self._session_id = session_id
        self._config = config
        self._owner_login = owner_login

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def public_key(self) -> str:
        return self._config.public_key if self.enabled else ""

    def enrolled(self) -> bool:
        return bool(
            self._core.journal.one(
                "SELECT 1 FROM push_subscriptions WHERE session_id=? AND owner_login=? "
                "AND revoked_at IS NULL LIMIT 1",
                (self._session_id, self._owner_login),
            )
        )

    def subscribe(self, *, endpoint: str, p256dh: str, auth: str) -> None:
        _validate_subscription(endpoint, p256dh, auth)
        subscription_id = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        now = iso()
        with self._core.journal.transaction() as tx:
            session = tx.execute(
                "SELECT owner FROM sessions WHERE id=?", (self._session_id,)
            ).fetchone()
            if session is None or session["owner"] != self._owner_login:
                raise PermissionError("push subscription owner does not match this session")
            existing = tx.execute(
                "SELECT owner_login FROM push_subscriptions WHERE endpoint=?", (endpoint,)
            ).fetchone()
            if existing is not None and existing["owner_login"] != self._owner_login:
                raise PermissionError("push endpoint is already enrolled by another owner")
            cursor_row = tx.execute(
                "SELECT cursor FROM push_cursors WHERE session_id=?", (self._session_id,)
            ).fetchone()
            event_cursor = tx.execute(
                "SELECT COALESCE(MAX(cursor), 0) AS cursor FROM events WHERE session_id=?",
                (self._session_id,),
            ).fetchone()["cursor"]
            if cursor_row is None:
                tx.execute(
                    "INSERT INTO push_cursors(session_id,cursor,updated_at) VALUES (?,?,?)",
                    (self._session_id, event_cursor, now),
                )
            tx.execute(
                "INSERT INTO push_subscriptions(id,session_id,owner_login,endpoint,p256dh,auth_secret,"
                "enrolled_after_cursor,created_at,updated_at,revoked_at) VALUES (?,?,?,?,?,?,?,?,?,NULL) "
                "ON CONFLICT(id) DO UPDATE SET session_id=excluded.session_id,owner_login=excluded.owner_login,"
                "p256dh=excluded.p256dh,auth_secret=excluded.auth_secret,"
                "enrolled_after_cursor=excluded.enrolled_after_cursor,updated_at=excluded.updated_at,revoked_at=NULL",
                (
                    subscription_id,
                    self._session_id,
                    self._owner_login,
                    endpoint,
                    p256dh,
                    auth,
                    event_cursor,
                    now,
                    now,
                ),
            )

    def unsubscribe(self, *, endpoint: str) -> bool:
        subscription_id = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        with self._core.journal.transaction() as tx:
            changed = tx.execute(
                "UPDATE push_subscriptions SET revoked_at=?,updated_at=? WHERE id=? AND session_id=? "
                "AND owner_login=? AND revoked_at IS NULL",
                (iso(), iso(), subscription_id, self._session_id, self._owner_login),
            )
            return bool(changed.rowcount)

    async def run(self) -> None:
        if not self.enabled:
            return
        while True:
            dispatch_task = asyncio.create_task(asyncio.to_thread(self.dispatch_pending))
            try:
                await asyncio.shield(dispatch_task)
            except asyncio.CancelledError:
                try:
                    await dispatch_task
                except Exception:
                    _LOG.warning("push delivery did not finish cleanly during shutdown")
                raise
            except Exception:
                _LOG.warning("push delivery cycle failed; coordinator state is unchanged")
            await asyncio.sleep(10)

    def dispatch_pending(self) -> None:
        if not self.enabled:
            return
        cursor_row = self._core.journal.one(
            "SELECT cursor FROM push_cursors WHERE session_id=?", (self._session_id,)
        )
        if cursor_row is None:
            latest = self._core.snapshot(self._session_id).last_event_cursor
            with self._core.journal.transaction() as tx:
                tx.execute(
                    "INSERT OR IGNORE INTO push_cursors(session_id,cursor,updated_at) VALUES (?,?,?)",
                    (self._session_id, latest, iso()),
                )
            return

        cursor = int(cursor_row["cursor"])
        while True:
            events = self._core.events(self._session_id, after=cursor, limit=200)
            if not events:
                break
            for event in events:
                alert = _event_alert(event)
                if event.kind == "budget.usage_reported":
                    alert = self._budget_alert()
                if alert is not None:
                    self._deliver_to_enrolled(event.cursor, *alert)
                cursor = event.cursor
                with self._core.journal.transaction() as tx:
                    tx.execute(
                        "UPDATE push_cursors SET cursor=?,updated_at=? WHERE session_id=?",
                        (cursor, iso(), self._session_id),
                    )

        budget_alert = self._budget_alert()
        if budget_alert is not None:
            self._deliver_to_enrolled(cursor, *budget_alert, include_current=True)

    def _budget_alert(self) -> tuple[str, str, str, str] | None:
        budget = self._core.snapshot(self._session_id).budget
        if budget.tokens_remaining <= 0 or budget.active_seconds_remaining <= 0:
            return (
                "budget",
                "Work allowance reached",
                "Review the current allowance in M1 Power Lab.",
                "/overview",
            )
        return None

    def _deliver_to_enrolled(
        self,
        cursor: int,
        category: str,
        title: str,
        body: str,
        path: str,
        *,
        include_current: bool = False,
    ) -> None:
        enrollment_filter = "enrolled_after_cursor <= ?" if include_current else "enrolled_after_cursor < ?"
        subscriptions = self._core.journal.all(
            "SELECT * FROM push_subscriptions WHERE session_id=? AND owner_login=? "
            f"AND revoked_at IS NULL AND {enrollment_filter}",
            (self._session_id, self._owner_login, cursor),
        )
        for subscription in subscriptions:
            if not self._claim_delivery(cursor, subscription["id"], category):
                continue
            status = "sent"
            expired = False
            try:
                webpush(
                    subscription_info={
                        "endpoint": subscription["endpoint"],
                        "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth_secret"]},
                    },
                    data=json.dumps(
                        {
                            "category": category,
                            "title": title,
                            "body": body,
                            "path": path,
                            "tag": f"m1lab-{category}-{cursor}",
                        },
                        separators=(",", ":"),
                    ),
                    vapid_private_key=self._config.private_key,
                    vapid_claims={"sub": self._config.subject},
                    timeout=8,
                    ttl=300,
                )
            except WebPushException as exc:
                response = getattr(exc, "response", None)
                expired = getattr(response, "status_code", None) in {404, 410}
                status = "expired" if expired else "failed"
            except Exception:
                status = "failed"
            self._finish_delivery(cursor, subscription["id"], category, status)
            if expired:
                with self._core.journal.transaction() as tx:
                    tx.execute(
                        "UPDATE push_subscriptions SET revoked_at=?,updated_at=? WHERE id=?",
                        (iso(), iso(), subscription["id"]),
                    )

    def _claim_delivery(self, cursor: int, subscription_id: str, category: str) -> bool:
        now = iso()
        with self._core.journal.transaction() as tx:
            row = tx.execute(
                "SELECT 1 FROM push_deliveries WHERE session_id=? "
                "AND event_cursor=? AND subscription_id=? AND category=?",
                (self._session_id, cursor, subscription_id, category),
            ).fetchone()
            if row is not None:
                return False
            tx.execute(
                "INSERT INTO push_deliveries(session_id,event_cursor,subscription_id,category,status,"
                "attempts,attempted_at) VALUES (?,?,?,?,'pending',1,?)",
                (self._session_id, cursor, subscription_id, category, now),
            )
            return True

    def _finish_delivery(
        self, cursor: int, subscription_id: str, category: str, status: str
    ) -> None:
        now = iso()
        with self._core.journal.transaction() as tx:
            tx.execute(
                "UPDATE push_deliveries SET status=?,completed_at=? WHERE session_id=? AND event_cursor=? "
                "AND subscription_id=? AND category=?",
                (status, now, self._session_id, cursor, subscription_id, category),
            )


def _validate_subscription(endpoint: str, p256dh: str, auth: str) -> None:
    if len(endpoint) > 2_048:
        raise ValueError("push endpoint exceeds its length bound")
    parsed = urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("push endpoint has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("push endpoint must be an HTTPS URL on the standard port")
    host = parsed.hostname.lower().rstrip(".")
    if host not in _PUSH_HOSTS and not host.endswith(_PUSH_HOST_SUFFIXES):
        raise ValueError("push endpoint host is not an approved browser push service")
    if not 32 <= len(p256dh) <= 256 or not _KEY.fullmatch(p256dh):
        raise ValueError("push p256dh key is malformed")
    if not 16 <= len(auth) <= 128 or not _KEY.fullmatch(auth):
        raise ValueError("push auth secret is malformed")


def _event_alert(event: EventRecord) -> tuple[str, str, str, str] | None:
    if event.kind == "session.phase_changed":
        phase = event.data.get("phase")
        if phase == "awaiting_approval":
            return (
                "approval",
                "Approval requested",
                "Review a pending request in M1 Power Lab.",
                "/approvals",
            )
        if phase == "recovering":
            return (
                "recovery",
                "Recovery needs attention",
                "Review the current recovery state in M1 Power Lab.",
                "/overview",
            )
        if phase == "budget_exhausted":
            return (
                "budget",
                "Work allowance reached",
                "Review the current allowance in M1 Power Lab.",
                "/overview",
            )
        if phase in {"completed", "stopped"}:
            return (
                "completion",
                "Investigation complete" if phase == "completed" else "Investigation stopped",
                "Review the current status in M1 Power Lab.",
                "/overview",
            )
    if event.kind == "operation.finished" and event.data.get("state") == "unknown_effect":
        return (
            "recovery",
            "Recovery needs attention",
            "Review the current recovery state in M1 Power Lab.",
            "/overview",
        )
    if event.kind in _RECOVERY_EVENTS:
        return (
            "recovery",
            "Recovery needs attention",
            "Review the current recovery state in M1 Power Lab.",
            "/overview",
        )
    return None
