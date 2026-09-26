from __future__ import annotations

from datetime import datetime, timezone
import time

from .errors import ConflictError, NotFoundError, ValidationError
from .journal import Journal, iso
from .models import (
    ACTIVE_PHASES,
    BudgetSnapshot,
    ReservationRecord,
    ReservationRequest,
    SessionPhase,
    UsageResult,
    UsageUpdate,
    new_id,
    utc_now,
)


def current_boot_id() -> str:
    try:
        return open("/proc/sys/kernel/random/boot_id", encoding="ascii").read().strip()
    except OSError:
        return "boot-id-unavailable"


class BudgetLedger:
    """Accounts active time, tokens, reservations and history-preserving grants."""

    def __init__(self, journal: Journal):
        self.journal = journal

    def initialize(self, session_id: str, *, tokens: int, active_seconds: int) -> None:
        with self.journal.transaction() as tx:
            now = iso()
            tx.execute(
                "INSERT INTO allowance_epochs(session_id, kind, token_delta, active_seconds_value, created_at, note) "
                "VALUES (?, 'initial', ?, ?, ?, 'default allowance')",
                (session_id, tokens, active_seconds, now),
            )
            self._open_segment(tx, session_id)

    def transition(self, session_id: str, old_phase: SessionPhase, new_phase: SessionPhase) -> None:
        was_active = old_phase in ACTIVE_PHASES
        is_active = new_phase in ACTIVE_PHASES
        if was_active == is_active:
            return
        with self.journal.transaction() as tx:
            if is_active:
                self._open_segment(tx, session_id)
            else:
                self._close_segment(tx, session_id)

    def grant_tokens(self, session_id: str, amount: int, command_id: str, note: str = "") -> None:
        if amount <= 0:
            raise ValidationError("token increment must be positive")
        with self.journal.transaction() as tx:
            tx.execute(
                "INSERT INTO allowance_epochs(session_id, kind, token_delta, active_seconds_value, created_at, command_id, note) "
                "VALUES (?, 'token_grant', ?, 0, ?, ?, ?)",
                (session_id, amount, iso(), command_id, note),
            )

    def extend_time(self, session_id: str, seconds: int, command_id: str, note: str = "") -> None:
        if seconds <= 0:
            raise ValidationError("time extension must be positive")
        with self.journal.transaction() as tx:
            tx.execute(
                "INSERT INTO allowance_epochs(session_id, kind, token_delta, active_seconds_value, created_at, command_id, note) "
                "VALUES (?, 'time_extension', 0, ?, ?, ?, ?)",
                (session_id, seconds, iso(), command_id, note),
            )

    def reset_remaining_time(self, session_id: str, seconds: int, command_id: str, note: str = "") -> None:
        if seconds <= 0:
            raise ValidationError("reset duration must be positive")
        snapshot = self.snapshot(session_id)
        new_total = snapshot.active_seconds_used + seconds
        with self.journal.transaction() as tx:
            tx.execute(
                "INSERT INTO allowance_epochs(session_id, kind, token_delta, active_seconds_value, created_at, command_id, note) "
                "VALUES (?, 'time_reset', 0, ?, ?, ?, ?)",
                (session_id, new_total, iso(), command_id, note),
            )

    def report_usage(self, update: UsageUpdate) -> UsageResult:
        reported = update.input_tokens + update.output_tokens
        with self.journal.transaction() as tx:
            duplicate = tx.execute(
                "SELECT token_delta FROM usage_reports WHERE report_id = ?", (update.report_id,)
            ).fetchone()
            if duplicate is not None:
                row = tx.execute("SELECT lifetime_tokens FROM sessions WHERE id = ?", (update.session_id,)).fetchone()
                if row is None:
                    raise NotFoundError(f"session {update.session_id} does not exist")
                return UsageResult(accepted=False, token_delta=0, lifetime_tokens=row["lifetime_tokens"])

            source = tx.execute(
                "SELECT * FROM usage_sources WHERE session_id = ? AND source_id = ?",
                (update.session_id, update.source_id),
            ).fetchone()
            prior = 0 if source is None else source["cumulative_tokens"]
            if update.cumulative:
                delta = max(0, reported - prior)
                cumulative = max(prior, reported)
            else:
                delta = reported
                cumulative = prior + reported
            tx.execute(
                "INSERT INTO usage_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    update.report_id,
                    update.session_id,
                    update.source_id,
                    update.input_tokens,
                    update.output_tokens,
                    int(update.cumulative),
                    delta,
                    int(update.terminal),
                    iso(update.reported_at),
                ),
            )
            tx.execute(
                "INSERT INTO usage_sources VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, source_id) DO UPDATE SET cumulative_tokens=excluded.cumulative_tokens, "
                "accounted_tokens=usage_sources.accounted_tokens + ?, terminal=excluded.terminal, updated_at=excluded.updated_at",
                (
                    update.session_id,
                    update.source_id,
                    cumulative,
                    delta,
                    int(update.terminal),
                    iso(update.reported_at),
                    delta,
                ),
            )
            changed = tx.execute(
                "UPDATE sessions SET lifetime_tokens=lifetime_tokens + ?, updated_at=? WHERE id=?",
                (delta, iso(), update.session_id),
            )
            if not changed.rowcount:
                raise NotFoundError(f"session {update.session_id} does not exist")
            row = tx.execute("SELECT lifetime_tokens FROM sessions WHERE id = ?", (update.session_id,)).fetchone()
            assert row is not None
            self.journal.append_event(
                tx,
                kind="budget.usage_reported",
                session_id=update.session_id,
                subject_id=update.source_id,
                data={"report_id": update.report_id, "token_delta": delta, "terminal": update.terminal},
            )
            return UsageResult(accepted=True, token_delta=delta, lifetime_tokens=row["lifetime_tokens"])

    def mark_usage_uncertain(self, session_id: str, source_id: str, reason: str) -> None:
        with self.journal.transaction() as tx:
            changed = tx.execute(
                "UPDATE sessions SET usage_uncertain=1, updated_at=? WHERE id=?", (iso(), session_id)
            )
            if not changed.rowcount:
                raise NotFoundError(f"session {session_id} does not exist")
            self.journal.append_event(
                tx,
                kind="budget.usage_uncertain",
                session_id=session_id,
                subject_id=source_id,
                data={"reason": reason},
            )

    def resolve_usage_uncertainty(
        self, session_id: str, *, upper_bound_tokens: int, evidence: str, owner_decision: bool = False
    ) -> None:
        if upper_bound_tokens < 0 or not evidence.strip():
            raise ValidationError("a nonnegative upper bound and evidence are required")
        with self.journal.transaction() as tx:
            changed = tx.execute(
                "UPDATE sessions SET lifetime_tokens=lifetime_tokens + ?, usage_uncertain=0, updated_at=? WHERE id=?",
                (upper_bound_tokens, iso(), session_id),
            )
            if not changed.rowcount:
                raise NotFoundError(f"session {session_id} does not exist")
            self.journal.append_event(
                tx,
                kind="budget.usage_uncertainty_resolved",
                session_id=session_id,
                subject_id=None,
                data={
                    "upper_bound_tokens": upper_bound_tokens,
                    "evidence": evidence,
                    "owner_decision": owner_decision,
                },
            )

    def reserve(self, request: ReservationRequest) -> ReservationRecord:
        if request.expires_at <= utc_now():
            raise ValidationError("reservation expiry must be in the future")
        record = ReservationRecord(
            id=new_id("reservation"), created_at=utc_now(), released_at=None, **request.model_dump()
        )
        with self.journal.transaction() as tx:
            snapshot = self.snapshot(request.session_id)
            if not snapshot.admission_open:
                raise ConflictError("budget admission is closed: " + "; ".join(snapshot.blockers))
            if (
                request.tokens > snapshot.tokens_remaining
                or request.active_seconds > snapshot.active_seconds_remaining
            ):
                raise ConflictError("reservation exceeds the remaining allowance")
            tx.execute(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    record.id,
                    record.session_id,
                    record.purpose,
                    record.tokens,
                    record.active_seconds,
                    iso(record.expires_at),
                    iso(record.created_at),
                ),
            )
        return record

    def release_reservation(self, reservation_id: str) -> None:
        with self.journal.transaction() as tx:
            changed = tx.execute(
                "UPDATE reservations SET released_at=? WHERE id=? AND released_at IS NULL",
                (iso(), reservation_id),
            )
            if not changed.rowcount:
                raise NotFoundError(f"active reservation {reservation_id} does not exist")

    def snapshot(self, session_id: str) -> BudgetSnapshot:
        session = self.journal.one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if session is None:
            raise NotFoundError(f"session {session_id} does not exist")
        epochs = self.journal.all(
            "SELECT kind, token_delta, active_seconds_value FROM allowance_epochs WHERE session_id=? ORDER BY id",
            (session_id,),
        )
        token_limit = sum(row["token_delta"] for row in epochs)
        active_limit = 0.0
        for row in epochs:
            if row["kind"] == "time_reset":
                active_limit = row["active_seconds_value"]
            else:
                active_limit += row["active_seconds_value"]
        used_seconds = float(session["lifetime_active_seconds"]) + self._open_elapsed(session_id)
        now = iso()
        reserved = self.journal.one(
            "SELECT COALESCE(SUM(tokens), 0) AS tokens, COALESCE(SUM(active_seconds), 0) AS seconds "
            "FROM reservations WHERE session_id=? AND released_at IS NULL AND expires_at > ?",
            (session_id, now),
        )
        assert reserved is not None
        token_remaining = max(0, token_limit - session["lifetime_tokens"] - reserved["tokens"])
        seconds_remaining = max(0.0, active_limit - used_seconds - reserved["seconds"])
        blockers: list[str] = []
        if session["usage_uncertain"]:
            blockers.append("Codex usage is uncertain")
        if token_remaining <= 0:
            blockers.append("token allowance is exhausted")
        if seconds_remaining <= 0:
            blockers.append("active-time allowance is exhausted")
        return BudgetSnapshot(
            token_limit=token_limit,
            tokens_used=session["lifetime_tokens"],
            tokens_reserved=reserved["tokens"],
            tokens_remaining=token_remaining,
            active_seconds_limit=active_limit,
            active_seconds_used=used_seconds,
            active_seconds_reserved=reserved["seconds"],
            active_seconds_remaining=seconds_remaining,
            usage_uncertain=bool(session["usage_uncertain"]),
            admission_open=not blockers,
            blockers=blockers,
        )

    def reconcile_clock(self) -> list[str]:
        uncertain: list[str] = []
        boot_id = current_boot_id()
        rows = self.journal.all("SELECT * FROM active_segments WHERE ended_utc IS NULL")
        for row in rows:
            if row["boot_id"] == boot_id:
                continue
            started = datetime.fromisoformat(row["started_utc"])
            elapsed = max(0.0, (utc_now() - started).total_seconds())
            with self.journal.transaction() as tx:
                tx.execute(
                    "UPDATE active_segments SET ended_utc=?, elapsed_seconds=?, uncertain=1 WHERE id=?",
                    (iso(), elapsed, row["id"]),
                )
                tx.execute(
                    "UPDATE sessions SET lifetime_active_seconds=lifetime_active_seconds + ?, updated_at=? WHERE id=?",
                    (elapsed, iso(), row["session_id"]),
                )
                self.journal.append_event(
                    tx,
                    kind="budget.active_time_reconciled",
                    session_id=row["session_id"],
                    subject_id=None,
                    data={"charged_seconds": elapsed, "uncertain": True},
                )
            uncertain.append(row["session_id"])
        return uncertain

    def _open_segment(self, tx, session_id: str) -> None:
        existing = tx.execute(
            "SELECT id FROM active_segments WHERE session_id=? AND ended_utc IS NULL", (session_id,)
        ).fetchone()
        if existing is None:
            tx.execute(
                "INSERT INTO active_segments(session_id, boot_id, started_utc, started_monotonic) VALUES (?, ?, ?, ?)",
                (session_id, current_boot_id(), iso(), time.monotonic()),
            )

    def _close_segment(self, tx, session_id: str) -> None:
        row = tx.execute(
            "SELECT * FROM active_segments WHERE session_id=? AND ended_utc IS NULL", (session_id,)
        ).fetchone()
        if row is None:
            return
        now_mono = time.monotonic()
        if row["boot_id"] == current_boot_id():
            elapsed = max(0.0, now_mono - row["started_monotonic"])
            uncertain = 0
        else:
            elapsed = max(0.0, (utc_now() - datetime.fromisoformat(row["started_utc"])).total_seconds())
            uncertain = 1
        tx.execute(
            "UPDATE active_segments SET ended_utc=?, ended_monotonic=?, elapsed_seconds=?, uncertain=? WHERE id=?",
            (iso(), now_mono, elapsed, uncertain, row["id"]),
        )
        tx.execute(
            "UPDATE sessions SET lifetime_active_seconds=lifetime_active_seconds + ?, updated_at=? WHERE id=?",
            (elapsed, iso(), session_id),
        )

    def _open_elapsed(self, session_id: str) -> float:
        row = self.journal.one(
            "SELECT * FROM active_segments WHERE session_id=? AND ended_utc IS NULL", (session_id,)
        )
        if row is None:
            return 0.0
        if row["boot_id"] == current_boot_id():
            return max(0.0, time.monotonic() - row["started_monotonic"])
        return max(0.0, (utc_now() - datetime.fromisoformat(row["started_utc"])).total_seconds())
