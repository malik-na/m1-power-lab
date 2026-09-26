"""The narrow boundary between the operator UI and the coordinator.

The web package deliberately knows nothing about journal storage, model jobs, or
target devices.  The coordinator supplies this facade and remains authoritative
for identity-independent policy, idempotency, revision checks, and execution.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


ViewName = Literal["overview", "evidence", "approvals", "conversation"]
CommandStatus = Literal["received", "applied", "rejected"]


@dataclass(frozen=True, slots=True)
class Owner:
    login: str
    display_name: str
    source: Literal["local", "tailscale"]


@dataclass(frozen=True, slots=True)
class OperatorCommand:
    command_id: str
    kind: str
    expected_revision: str
    target_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: str
    status: CommandStatus
    revision: str
    message: str
    event_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class UIEvent:
    cursor: str
    kind: str
    revision: str
    payload: Mapping[str, Any] = field(default_factory=dict)


class OperatorFacade(Protocol):
    """Coordinator operations needed by the browser interface.

    ``get_view`` returns JSON-like data shaped for the selected template.  Every
    result should include ``revision`` and may include the common ``session``,
    ``target``, ``budgets``, and ``alerts`` mappings.

    ``submit`` must durably deduplicate ``command_id`` and validate
    ``expected_revision`` before applying a state change.  A receipt only
    reports coordinator state; it never implies that a target operation ran.

    ``stream_events`` replays durable events strictly after ``after_cursor``.
    If replay is impossible it yields a ``snapshot_required`` event.  The
    iterator may also yield ``heartbeat`` events during quiet periods.
    """

    async def get_view(self, view: ViewName, owner: Owner) -> Mapping[str, Any]: ...

    async def submit(self, command: OperatorCommand, owner: Owner) -> CommandReceipt: ...

    def stream_events(
        self, after_cursor: str | None, owner: Owner
    ) -> AsyncIterator[UIEvent]: ...


class UnavailableFacade:
    """Safe placeholder used when the coordinator has not been wired yet."""

    async def get_view(self, view: ViewName, owner: Owner) -> Mapping[str, Any]:
        return {
            "revision": "unavailable",
            "session": {
                "id": "not-connected",
                "state": "offline",
                "objective": "Coordinator facade is not connected.",
                "updated_at": None,
            },
            "target": {
                "name": "M1 target",
                "mode": "unknown",
                "freshness": "unknown",
                "recovery": "unqualified",
            },
            "budgets": {
                "tokens_used": 0,
                "tokens_limit": 0,
                "active_seconds": 0,
                "active_seconds_limit": 0,
                "usage_state": "unknown",
            },
            "alerts": [
                {
                    "level": "warning",
                    "title": "Coordinator unavailable",
                    "detail": "Start the coordinator with an OperatorFacade to use this interface.",
                }
            ],
            "experiments": [],
            "evidence": [],
            "approvals": [],
            "recovery_actions": [],
            "messages": [],
            "jobs": [],
        }

    async def submit(self, command: OperatorCommand, owner: Owner) -> CommandReceipt:
        return CommandReceipt(
            command_id=command.command_id,
            status="rejected",
            revision="unavailable",
            message="Coordinator facade is not connected.",
        )

    async def stream_events(
        self, after_cursor: str | None, owner: Owner
    ) -> AsyncIterator[UIEvent]:
        if False:  # Keep this an async generator without inventing live state.
            yield UIEvent(cursor="", kind="heartbeat", revision="unavailable")
