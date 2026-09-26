from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .power import PairedBlock, ThresholdDecision


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ScientificModel(BaseModel):
    """Strict, immutable value object used in the scientific record."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def datetimes_are_timezone_aware(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.utcoffset() is None:
            raise ValueError("scientific record datetimes must be timezone-aware")
        return value


class StudyMode(StrEnum):
    EXPLORATION = "exploration"
    CONFIRMATION = "confirmation"


class OutcomeCategory(StrEnum):
    POSITIVE = "positive"
    BELOW_TARGET = "below_target"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"


class EvidenceDirection(StrEnum):
    SUPPORTS = "supports"
    COUNTERS = "counters"


class MeasurementProvenance(ScientificModel):
    source: str = Field(min_length=1, description="Instrument or collection pipeline")
    source_version: str | None = None
    target_identity: str = Field(min_length=1)
    target_boot_epoch: str = Field(min_length=1)
    target_configuration_digest: str = Field(min_length=1)
    operation_id: str | None = None
    collector_host: str = Field(min_length=1)
    clock: str = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)
    calibration: str | None = None
    raw_artifact_ids: tuple[str, ...] = ()
    raw_artifact_digests: tuple[str, ...] = ()
    captured_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def raw_artifacts_have_digests(self) -> "MeasurementProvenance":
        if not self.raw_artifact_ids:
            raise ValueError("measurement provenance requires at least one raw artifact")
        if len(self.raw_artifact_ids) != len(self.raw_artifact_digests):
            raise ValueError("every raw artifact requires its recorded sha256 digest")
        if len(set(self.raw_artifact_ids)) != len(self.raw_artifact_ids):
            raise ValueError("raw artifact references must be unique")
        return self


class Exclusion(ScientificModel):
    subject: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    prespecified: bool
    evidence_refs: tuple[str, ...] = ()


class RegressionCheck(ScientificModel):
    name: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    acceptance_criterion: str = Field(min_length=1)
    observed: str = Field(min_length=1)
    passed: bool
    evidence_refs: tuple[str, ...] = ()


class FrozenTenPercentRule(ScientificModel):
    """The versioned confirmation rule; changing a field creates a new rule."""

    rule_id: Literal["paired-power-reduction-10pct-v1"] = "paired-power-reduction-10pct-v1"
    estimand: Literal["1 - mean(changed_watts) / mean(baseline_watts)"] = (
        "1 - mean(changed_watts) / mean(baseline_watts)"
    )
    contrast: Literal["0.90 * baseline_watts - changed_watts"] = (
        "0.90 * baseline_watts - changed_watts"
    )
    target_reduction_percent: Literal[10.0] = 10.0
    confidence_level: Literal[0.95] = 0.95
    interval: Literal["two-sided Student-t interval on paired block contrasts"] = (
        "two-sided Student-t interval on paired block contrasts"
    )
    positive_condition: Literal[
        "lower confidence bound minus systematic allowance is greater than zero"
    ] = "lower confidence bound minus systematic allowance is greater than zero"
    below_target_condition: Literal[
        "upper confidence bound plus systematic allowance is less than zero"
    ] = "upper confidence bound plus systematic allowance is less than zero"
    minimum_independently_restarted_blocks: int = Field(default=2, ge=2)
    maximum_paired_blocks: Literal[31] = 31
    systematic_allowance_watts: float = Field(default=0.0, ge=0)
    requires_no_failed_regressions: Literal[True] = True
    requires_protocol_adherence: Literal[True] = True


class ExperimentProtocol(ScientificModel):
    record_type: Literal["experiment_protocol"] = "experiment_protocol"
    id: str = Field(default_factory=lambda: _id("protocol"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    mode: StudyMode
    title: str = Field(min_length=1)
    workload: str = Field(min_length=1)
    baseline_configuration: dict[str, Any]
    changed_configuration: dict[str, Any]
    baseline_configuration_digest: str = Field(min_length=1)
    changed_configuration_digest: str = Field(min_length=1)
    controlled_conditions: tuple[str, ...]
    block_order: str = Field(min_length=1)
    independent_restart: str = Field(min_length=1)
    warmup: str = Field(min_length=1)
    sampling: str = Field(min_length=1)
    stopping_rule: str = Field(min_length=1)
    planned_exclusions: tuple[str, ...] = ()
    regression_checks: tuple[str, ...] = ()
    decision_rule: FrozenTenPercentRule = Field(default_factory=FrozenTenPercentRule)
    frozen_at: datetime | None = None
    redesign_checkpoint_id: str | None = None
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def confirmation_is_frozen(self) -> "ExperimentProtocol":
        if self.mode == StudyMode.CONFIRMATION and self.frozen_at is None:
            raise ValueError("a confirmation protocol must be frozen before data collection")
        if self.baseline_configuration_digest == self.changed_configuration_digest:
            raise ValueError("baseline and changed target configurations must differ")
        return self


class HypothesisRecord(ScientificModel):
    record_type: Literal["hypothesis"] = "hypothesis"
    id: str = Field(default_factory=lambda: _id("hypothesis"))
    session_id: str = Field(min_length=1)
    mode: StudyMode
    statement: str = Field(min_length=1)
    proposed_mechanism: str = Field(min_length=1)
    predicted_effect: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1)
    falsifiers: tuple[str, ...] = ()
    prior_evidence_refs: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=_now)


class ObservationRecord(ScientificModel):
    record_type: Literal["observation"] = "observation"
    id: str = Field(default_factory=lambda: _id("observation"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    mode: StudyMode
    arm: Literal["baseline", "changed"]
    independent_block_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    measurements: dict[str, float] = Field(default_factory=dict)
    conditions: dict[str, str] = Field(default_factory=dict)
    provenance: MeasurementProvenance
    exclusions: tuple[Exclusion, ...] = ()
    observed_at: datetime = Field(default_factory=_now)


class ProtocolAdherence(ScientificModel):
    protocol_id: str = Field(min_length=1)
    protocol_frozen_before_collection: bool
    independently_restarted_blocks: int = Field(ge=0)
    workload_matched: bool
    configuration_matched: bool
    sampling_complete: bool
    violations: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        """Conservative validity suitable for a confirmation claim."""
        return self.valid_for(StudyMode.CONFIRMATION)

    def valid_for(self, mode: StudyMode) -> bool:
        return (
            (mode == StudyMode.EXPLORATION or self.protocol_frozen_before_collection)
            and self.independently_restarted_blocks >= 2
            and self.workload_matched
            and self.configuration_matched
            and self.sampling_complete
            and not self.violations
        )


class PairedObservationBlock(ScientificModel):
    """One paired contrast whose values are anchored to two observations."""

    baseline_observation_id: str = Field(min_length=1)
    changed_observation_id: str = Field(min_length=1)
    baseline_watts: float = Field(gt=0)
    changed_watts: float = Field(ge=0)

    @property
    def power(self) -> PairedBlock:
        return PairedBlock(
            baseline_watts=self.baseline_watts,
            changed_watts=self.changed_watts,
        )


class DerivedResultRecord(ScientificModel):
    record_type: Literal["derived_result"] = "derived_result"
    id: str = Field(default_factory=lambda: _id("result"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    mode: StudyMode
    observation_ids: tuple[str, ...]
    paired_blocks: tuple[PairedObservationBlock, ...]
    systematic_allowance_watts: float = Field(ge=0)
    adherence: ProtocolAdherence
    regressions: tuple[RegressionCheck, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()
    threshold: ThresholdDecision | None
    outcome: OutcomeCategory
    analysis_code_refs: tuple[str, ...] = ()
    derived_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def observation_set_matches_blocks(self) -> "DerivedResultRecord":
        referenced = tuple(
            item
            for block in self.paired_blocks
            for item in (block.baseline_observation_id, block.changed_observation_id)
        )
        if len(set(referenced)) != len(referenced):
            raise ValueError("a result cannot reuse an observation across paired blocks")
        if set(self.observation_ids) != set(referenced) or len(self.observation_ids) != len(referenced):
            raise ValueError("observation_ids must exactly match the paired block observations")
        return self


class RedesignCheckpointRecord(ScientificModel):
    record_type: Literal["redesign_checkpoint"] = "redesign_checkpoint"
    id: str = Field(default_factory=lambda: _id("redesign"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    mode: StudyMode
    triggering_result_ids: tuple[str, str]
    findings: str = Field(min_length=1)
    redesign: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_now)


class ClaimEvidence(ScientificModel):
    record_type: Literal["claim_evidence"] = "claim_evidence"
    id: str = Field(default_factory=lambda: _id("evidence"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    mode: StudyMode
    claim: str = Field(min_length=1)
    direction: EvidenceDirection
    strength: Literal["weak", "moderate", "strong"]
    rationale: str = Field(min_length=1)
    record_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=_now)


class DecisionRecord(ScientificModel):
    record_type: Literal["decision"] = "decision"
    id: str = Field(default_factory=lambda: _id("decision"))
    session_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    derived_result_id: str = Field(min_length=1)
    mode: StudyMode
    outcome: OutcomeCategory
    conclusion: str = Field(min_length=1)
    decision_delta: str = Field(default="No prior-decision delta recorded", min_length=1)
    next_action: str = Field(min_length=1)
    evidence: tuple[ClaimEvidence, ...] = ()
    counterevidence: tuple[ClaimEvidence, ...] = ()
    unresolved_uncertainties: tuple[str, ...] = ()
    decided_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def directions_match_collections(self) -> "DecisionRecord":
        if any(item.direction != EvidenceDirection.SUPPORTS for item in self.evidence):
            raise ValueError("evidence entries must have direction=supports")
        if any(item.direction != EvidenceDirection.COUNTERS for item in self.counterevidence):
            raise ValueError("counterevidence entries must have direction=counters")
        related = (*self.evidence, *self.counterevidence)
        if any(item.session_id != self.session_id for item in related):
            raise ValueError("decision evidence cannot mix sessions")
        if any(item.hypothesis_id != self.hypothesis_id for item in related):
            raise ValueError("decision evidence cannot mix hypotheses")
        if any(item.mode != self.mode for item in related):
            raise ValueError("decision evidence must use the decision's study mode")
        return self


ScientificRecord: TypeAlias = Annotated[
    HypothesisRecord
    | ExperimentProtocol
    | ObservationRecord
    | DerivedResultRecord
    | RedesignCheckpointRecord
    | ClaimEvidence
    | DecisionRecord,
    Field(discriminator="record_type"),
]


class ScientificArtifactEnvelope(ScientificModel):
    schema_version: Literal["m1lab.scientific-record.v1"] = "m1lab.scientific-record.v1"
    session_id: str
    record_id: str
    record_type: str
    record: dict[str, Any]


class EvidenceManifestEntry(ScientificModel):
    record_id: str
    record_type: str
    artifact_id: str
    sha256: str
    summary: str
    outcome: OutcomeCategory | None = None
    mode: StudyMode


class EvidenceManifest(ScientificModel):
    schema_version: Literal["m1lab.evidence-manifest.v1"] = "m1lab.evidence-manifest.v1"
    session_id: str
    entries: tuple[EvidenceManifestEntry, ...]
    positive_count: int = Field(ge=0)
    counterevidence_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)


class EvidenceBrief(ScientificModel):
    session_id: str
    hypothesis: str | None
    mode: StudyMode | None
    finding: str
    outcome: OutcomeCategory | None
    evidence_refs: tuple[str, ...]
    counterevidence: tuple[str, ...]
    limitations: tuple[str, ...]
    next_action: str | None
    decision_delta: str | None = None
    competing_hypotheses: tuple[dict[str, str], ...] = ()
    strongest_support: tuple[str, ...] = ()
    strongest_counterevidence: tuple[str, ...] = ()
    failed_attempts: tuple[str, ...] = ()
    uninformative_streak: int = Field(default=0, ge=0)
    redesign_checkpoint_required: bool = False
    redesign_hypothesis_ids: tuple[str, ...] = ()
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class PublishedScientificRecord(ScientificModel):
    record: ScientificRecord
    artifact_id: str
    sha256: str
    size_bytes: int
    created_at: datetime
