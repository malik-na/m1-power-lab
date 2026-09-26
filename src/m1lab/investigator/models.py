"""Public request and result types for bounded investigation turns."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvidenceExcerpt(BaseModel):
    """Technical evidence supplied by the coordinator or operator.

    Content is persisted as an immutable artifact before a model turn starts.
    The orchestrator removes common credential forms and bounds each item.
    """

    label: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=1_000_000)
    media_type: str = Field(default="text/plain", min_length=1, max_length=160)


class InvestigationRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=40_000)
    cwd: Path
    model: str = Field(min_length=1, max_length=128)
    kind: Literal["investigate", "implement", "analyze", "review", "conclude", "chat"] = "investigate"
    estimated_tokens: int = Field(default=100_000, gt=0, le=100_000_000)
    estimated_active_seconds: int = Field(default=900, gt=0, le=86_400)
    deadline_seconds: int = Field(default=900, gt=0, le=86_400)
    evidence: list[EvidenceExcerpt] = Field(default_factory=list, max_length=32)
    artifact_ids: list[str] = Field(default_factory=list, max_length=128)
    reasoning_effort: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_cwd_and_evidence(self) -> "InvestigationRequest":
        if not self.cwd.is_absolute():
            raise ValueError("investigation cwd must be absolute")
        total = sum(len(item.content) for item in self.evidence)
        if total > 4_000_000:
            raise ValueError("combined evidence exceeds 4,000,000 characters")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("artifact_ids must not contain duplicates")
        return self


class JobLaunch(BaseModel):
    """Durable and provider identities returned after admission."""

    job_id: str
    runtime_id: str
    thread_id: str | None
    state: str


class JobInterruption(BaseModel):
    job_id: str
    runtime_id: str
    requested: bool
