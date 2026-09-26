"""Public records returned by the bounded experiment executor."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from m1lab.core import OperationState


class StepEvidence(BaseModel):
    """Immutable evidence references for one typed hardware operation."""

    index: int = Field(ge=0)
    kind: str
    dispatch_id: str
    status: str
    result_artifact_id: str
    payload_artifact_id: str | None = None
    started_at: datetime
    finished_at: datetime
    boot_epoch: str


class ExecutionReport(BaseModel):
    """Caller-facing result of executing one authorized envelope."""

    operation_id: str
    state: OperationState
    message: str = ""
    steps: list[StepEvidence] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    target_condition: str | None = None
    core_state_recorded: bool = True
    details: dict[str, Any] = Field(default_factory=dict)

