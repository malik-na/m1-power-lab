from __future__ import annotations

import json
from math import isclose
from typing import Iterable, Protocol

from pydantic import TypeAdapter

from m1lab.core import ArtifactRecord, ProcedureDraft, SessionRecord, SessionSnapshot

from .models import (
    ClaimEvidence,
    DecisionRecord,
    DerivedResultRecord,
    EvidenceBrief,
    EvidenceManifest,
    EvidenceManifestEntry,
    Exclusion,
    ExperimentProtocol,
    HypothesisRecord,
    ObservationRecord,
    OutcomeCategory,
    PairedObservationBlock,
    ProtocolAdherence,
    PublishedScientificRecord,
    RegressionCheck,
    RedesignCheckpointRecord,
    ScientificArtifactEnvelope,
    ScientificRecord,
    StudyMode,
)
from .power import evaluate_ten_percent_threshold


class ScientificCore(Protocol):
    """The complete public core surface needed by this module."""

    def session(self, session_id: str) -> SessionRecord: ...

    def snapshot(self, session_id: str) -> SessionSnapshot: ...

    def publish_artifact(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        provenance: dict[str, object] | None = None,
    ) -> ArtifactRecord: ...

    def artifact(self, artifact_id: str) -> ArtifactRecord: ...

    def read_artifact(
        self, session_id: str, artifact_id: str, *, max_bytes: int = 4_000_000
    ) -> bytes: ...

    def session_artifact(self, session_id: str, artifact_id: str) -> ArtifactRecord: ...

    def artifacts(
        self, session_id: str, *, record_type: str | None = None
    ) -> list[ArtifactRecord]: ...


def derive_power_result(
    *,
    session_id: str,
    hypothesis_id: str,
    protocol: ExperimentProtocol,
    hypothesis: HypothesisRecord,
    observations: Iterable[ObservationRecord],
    observation_pairs: Iterable[tuple[str, str]],
    adherence: ProtocolAdherence,
    regressions: Iterable[RegressionCheck] = (),
    exclusions: Iterable[Exclusion] = (),
    analysis_code_refs: Iterable[str] = (),
) -> DerivedResultRecord:
    """Apply the frozen rule and classify the result without model judgment."""

    if hypothesis.session_id != session_id or hypothesis.id != hypothesis_id:
        raise ValueError("hypothesis provenance does not match the result")
    if protocol.session_id != session_id or protocol.hypothesis_id != hypothesis_id:
        raise ValueError("protocol provenance does not match the result")
    if protocol.mode != hypothesis.mode:
        raise ValueError("protocol and hypothesis study modes differ")
    if adherence.protocol_id != protocol.id:
        raise ValueError("adherence report does not reference this protocol")

    observed = tuple(observations)
    observations_by_id = {item.id: item for item in observed}
    if len(observations_by_id) != len(observed):
        raise ValueError("observations must have unique IDs")
    pairs = tuple(observation_pairs)
    referenced = tuple(item for pair in pairs for item in pair)
    if len(set(referenced)) != len(referenced):
        raise ValueError("an observation cannot be reused across paired blocks")
    if set(referenced) != set(observations_by_id):
        raise ValueError("observation pairs must reference exactly the supplied observations")
    for observation in observed:
        if (
            observation.session_id != session_id
            or observation.hypothesis_id != hypothesis_id
            or observation.protocol_id != protocol.id
            or observation.mode != protocol.mode
        ):
            raise ValueError(f"observation {observation.id} is outside the result lineage")
        if hypothesis.primary_metric not in observation.measurements:
            raise ValueError(
                f"observation {observation.id} lacks primary metric {hypothesis.primary_metric!r}"
            )
        unit = observation.provenance.units.get(hypothesis.primary_metric, "").strip().lower()
        if unit not in {"w", "watt", "watts"}:
            raise ValueError(
                f"observation {observation.id} primary metric must declare watts in provenance units"
            )
    block_ids: set[str] = set()
    for baseline_id, changed_id in pairs:
        baseline = observations_by_id[baseline_id]
        changed = observations_by_id[changed_id]
        if baseline.arm != "baseline" or changed.arm != "changed":
            raise ValueError("each pair must order a baseline observation before a changed observation")
        if baseline.independent_block_id != changed.independent_block_id:
            raise ValueError("paired observations must belong to the same independent block")
        if baseline.independent_block_id in block_ids:
            raise ValueError("independent block IDs cannot be reused")
        block_ids.add(baseline.independent_block_id)
    if adherence.independently_restarted_blocks != len(block_ids):
        raise ValueError("protocol adherence block count does not match the recorded independent blocks")
    paired = tuple(
        PairedObservationBlock(
            baseline_observation_id=baseline_id,
            changed_observation_id=changed_id,
            baseline_watts=observations_by_id[baseline_id].measurements[hypothesis.primary_metric],
            changed_watts=observations_by_id[changed_id].measurements[hypothesis.primary_metric],
        )
        for baseline_id, changed_id in pairs
    )
    checks = tuple(regressions)
    excluded = tuple(exclusions)
    rule = protocol.decision_rule
    if len({check.name for check in checks}) != len(checks):
        raise ValueError("regression check names must be unique")
    if {check.name for check in checks} != set(protocol.regression_checks):
        raise ValueError("recorded regression checks must exactly match the protocol plan")
    invalid = (
        not adherence.valid_for(protocol.mode)
        or adherence.independently_restarted_blocks < rule.minimum_independently_restarted_blocks
        or len(paired) < rule.minimum_independently_restarted_blocks
        or len(paired) > rule.maximum_paired_blocks
        or (protocol.mode == StudyMode.CONFIRMATION and protocol.frozen_at is None)
        or (
            protocol.mode == StudyMode.CONFIRMATION
            and any(not exclusion.prespecified for exclusion in excluded)
        )
    )
    threshold = (
        evaluate_ten_percent_threshold(
            tuple(block.power for block in paired),
            systematic_allowance_watts=rule.systematic_allowance_watts,
        )
        if 2 <= len(paired) <= rule.maximum_paired_blocks
        else None
    )
    failed_regression = any(not check.passed for check in checks)
    if invalid:
        outcome = OutcomeCategory.INVALID
    elif failed_regression:
        outcome = OutcomeCategory.NEGATIVE
    elif threshold is not None and threshold.lower_contrast_watts is not None and threshold.lower_contrast_watts > 0:
        outcome = OutcomeCategory.POSITIVE
    elif threshold is not None and threshold.upper_contrast_watts is not None and threshold.upper_contrast_watts < 0:
        outcome = OutcomeCategory.BELOW_TARGET
    else:
        outcome = OutcomeCategory.INCONCLUSIVE

    return DerivedResultRecord(
        session_id=session_id,
        hypothesis_id=hypothesis_id,
        protocol_id=protocol.id,
        mode=protocol.mode,
        observation_ids=referenced,
        paired_blocks=paired,
        systematic_allowance_watts=rule.systematic_allowance_watts,
        adherence=adherence,
        regressions=checks,
        exclusions=excluded,
        threshold=threshold,
        outcome=outcome,
        analysis_code_refs=tuple(analysis_code_refs),
    )


class ScientificRecordStore:
    """Publishes content-addressed records and creates bounded Codex context."""

    def __init__(self, core: ScientificCore):
        self._core = core

    def validate_procedure_binding(self, draft: ProcedureDraft) -> None:
        """Validate optional scientific lineage and any required redesign gate."""

        hypothesis_id = draft.hypothesis_id
        protocol_id = draft.protocol_id
        checkpoint_id = draft.redesign_checkpoint_id
        if not any((hypothesis_id, protocol_id, checkpoint_id)):
            return
        if not hypothesis_id or not protocol_id:
            raise ValueError("scientific procedure binding requires both hypothesis_id and protocol_id")
        index = self._record_index(draft.session_id)
        hypothesis = _require_record(index, hypothesis_id, HypothesisRecord)
        protocol = _require_record(index, protocol_id, ExperimentProtocol)
        _match_parent(protocol, hypothesis)
        if protocol.hypothesis_id != hypothesis_id:
            raise ValueError("procedure protocol belongs to a different hypothesis")
        required_pair = _latest_inconclusive_pair(index, hypothesis_id)
        if required_pair is not None:
            if checkpoint_id is None:
                raise ValueError("procedure requires a redesign checkpoint after two inconclusive results")
            checkpoint = _require_record(index, checkpoint_id, RedesignCheckpointRecord)
            if (
                checkpoint.hypothesis_id != hypothesis_id
                or checkpoint.triggering_result_ids != required_pair
                or protocol.redesign_checkpoint_id != checkpoint_id
            ):
                raise ValueError("procedure redesign checkpoint does not match its hypothesis, protocol, and results")
        elif checkpoint_id is not None:
            checkpoint = _require_record(index, checkpoint_id, RedesignCheckpointRecord)
            if (
                checkpoint.hypothesis_id != hypothesis_id
                or protocol.redesign_checkpoint_id != checkpoint_id
            ):
                raise ValueError("procedure checkpoint does not match its hypothesis and protocol")

    def publish(self, record: ScientificRecord) -> PublishedScientificRecord:
        session = self._core.session(record.session_id)
        if session.id != record.session_id:
            raise ValueError("core returned a different session")
        self._validate_lineage(record)
        envelope = ScientificArtifactEnvelope(
            session_id=record.session_id,
            record_id=record.id,
            record_type=record.record_type,
            record=record.model_dump(mode="json"),
        )
        content = json.dumps(
            envelope.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        artifact = self._core.publish_artifact(
            content,
            media_type="application/vnd.m1lab.scientific-record+json;version=1",
            provenance={
                "session_id": record.session_id,
                "record_id": record.id,
                "record_type": record.record_type,
                "schema": envelope.schema_version,
            },
        )
        return PublishedScientificRecord(
            record=record,
            artifact_id=artifact.id,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            created_at=artifact.created_at,
        )

    def publish_many(self, records: Iterable[ScientificRecord]) -> tuple[PublishedScientificRecord, ...]:
        return tuple(self.publish(record) for record in records)

    def derive_and_publish(
        self,
        *,
        session_id: str,
        hypothesis_id: str,
        protocol_id: str,
        observation_pairs: Iterable[tuple[str, str]],
        adherence: ProtocolAdherence,
        regressions: Iterable[RegressionCheck] = (),
        exclusions: Iterable[Exclusion] = (),
        analysis_code_refs: Iterable[str] = (),
    ) -> PublishedScientificRecord:
        """Derive from already published observations, then validate and publish."""

        index = self._record_index(session_id)
        hypothesis = _require_record(index, hypothesis_id, HypothesisRecord)
        protocol = _require_record(index, protocol_id, ExperimentProtocol)
        pairs = tuple(observation_pairs)
        observation_ids = tuple(item for pair in pairs for item in pair)
        observations = tuple(
            _require_record(index, observation_id, ObservationRecord)
            for observation_id in observation_ids
        )
        result = derive_power_result(
            session_id=session_id,
            hypothesis_id=hypothesis_id,
            hypothesis=hypothesis,
            protocol=protocol,
            observations=observations,
            observation_pairs=pairs,
            adherence=adherence,
            regressions=regressions,
            exclusions=exclusions,
            analysis_code_refs=analysis_code_refs,
        )
        return self.publish(result)

    def load(self, session_id: str, artifact_id: str) -> PublishedScientificRecord:
        artifact = self._core.session_artifact(session_id, artifact_id)
        if not artifact.media_type.startswith("application/vnd.m1lab.scientific-record+json"):
            raise ValueError(f"artifact {artifact_id} is not a scientific record")
        try:
            document = json.loads(
                self._core.read_artifact(session_id, artifact_id).decode("utf-8")
            )
            envelope = ScientificArtifactEnvelope.model_validate(document)
            record = TypeAdapter(ScientificRecord).validate_python(envelope.record)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"scientific artifact {artifact_id} is invalid") from exc
        if (
            envelope.session_id != record.session_id
            or envelope.record_id != record.id
            or envelope.record_type != record.record_type
            or artifact.provenance.get("session_id") != record.session_id
        ):
            raise ValueError("scientific artifact envelope or provenance does not match its record")
        return PublishedScientificRecord(
            record=record,
            artifact_id=artifact.id,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            created_at=artifact.created_at,
        )

    def list(self, session_id: str) -> tuple[PublishedScientificRecord, ...]:
        self._core.session(session_id)
        return tuple(
            self.load(session_id, artifact.id)
            for artifact in self._core.artifacts(session_id)
            if artifact.provenance.get("record_type")
            and artifact.media_type.startswith("application/vnd.m1lab.scientific-record+json")
        )

    def _record_index(self, session_id: str) -> dict[str, ScientificRecord]:
        index: dict[str, ScientificRecord] = {}
        for published in self.list(session_id):
            record = published.record
            if record.id in index:
                raise ValueError(f"scientific record ID {record.id} is published more than once")
            index[record.id] = record
        return index

    def _validate_lineage(self, record: ScientificRecord) -> None:
        index = self._record_index(record.session_id)
        if record.id in index:
            raise ValueError(f"scientific record ID {record.id} is already published")
        artifacts = {item.id: item for item in self._core.artifacts(record.session_id)}

        if isinstance(record, HypothesisRecord):
            _validate_refs(record.prior_evidence_refs, index, artifacts, "prior evidence")
            return

        if isinstance(record, ExperimentProtocol):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            _match_parent(record, hypothesis)
            if record.created_at < hypothesis.created_at:
                raise ValueError("protocol predates its hypothesis")
            required_pair = _latest_inconclusive_pair(index, record.hypothesis_id)
            if required_pair is not None and record.redesign_checkpoint_id is None:
                raise ValueError(
                    "two consecutive inconclusive results require a redesign checkpoint before another protocol"
                )
            if record.redesign_checkpoint_id is not None:
                checkpoint = _require_record(
                    index, record.redesign_checkpoint_id, RedesignCheckpointRecord
                )
                if checkpoint.hypothesis_id != record.hypothesis_id:
                    raise ValueError("redesign checkpoint belongs to a different hypothesis")
                if record.created_at < checkpoint.created_at:
                    raise ValueError("protocol predates its referenced redesign checkpoint")
                if required_pair is not None and checkpoint.triggering_result_ids != required_pair:
                    raise ValueError("redesign checkpoint does not cover the current inconclusive result pair")
            return

        if isinstance(record, RedesignCheckpointRecord):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            _match_parent(record, hypothesis)
            required_pair = _latest_inconclusive_pair(index, record.hypothesis_id)
            if required_pair is None or record.triggering_result_ids != required_pair:
                raise ValueError(
                    "redesign checkpoint must cite the two latest inconclusive results for its hypothesis"
                )
            triggering = tuple(
                _require_record(index, result_id, DerivedResultRecord)
                for result_id in record.triggering_result_ids
            )
            if record.created_at < max(item.derived_at for item in triggering):
                raise ValueError("redesign checkpoint predates one of its triggering results")
            return

        if isinstance(record, ObservationRecord):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            protocol = _require_record(index, record.protocol_id, ExperimentProtocol)
            _match_parent(record, hypothesis)
            _match_protocol(record, protocol)
            session = self._core.session(record.session_id)
            if (
                session.target_identity is not None
                and record.provenance.target_identity != session.target_identity
            ):
                raise ValueError("observation target identity differs from the session target")
            expected_configuration = (
                protocol.baseline_configuration_digest
                if record.arm == "baseline"
                else protocol.changed_configuration_digest
            )
            if record.provenance.target_configuration_digest != expected_configuration:
                raise ValueError("observation target configuration does not match its protocol arm")
            if record.provenance.captured_at > record.observed_at:
                raise ValueError("measurement capture time is after observation time")
            if record.provenance.captured_at < protocol.created_at:
                raise ValueError("observation was collected before protocol creation")
            if protocol.mode == StudyMode.CONFIRMATION and (
                protocol.frozen_at is None or protocol.frozen_at > record.provenance.captured_at
            ):
                raise ValueError("confirmation observation was collected before protocol freeze")
            for artifact_id, digest in zip(
                record.provenance.raw_artifact_ids,
                record.provenance.raw_artifact_digests,
                strict=True,
            ):
                artifact = artifacts.get(artifact_id)
                if artifact is None:
                    raise ValueError(f"raw artifact {artifact_id} is unknown or belongs to another session")
                if not artifact.available or artifact.sha256 != digest:
                    raise ValueError(f"raw artifact {artifact_id} is unavailable or has a different digest")
                try:
                    self._core.read_artifact(
                        record.session_id,
                        artifact_id,
                        max_bytes=max(1, artifact.size_bytes),
                    )
                except (OSError, ValueError) as exc:
                    raise ValueError(f"raw artifact {artifact_id} failed integrity verification") from exc
            _validate_refs(
                tuple(ref for exclusion in record.exclusions for ref in exclusion.evidence_refs),
                index,
                artifacts,
                "exclusion evidence",
            )
            return

        if isinstance(record, DerivedResultRecord):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            protocol = _require_record(index, record.protocol_id, ExperimentProtocol)
            _match_parent(record, hypothesis)
            _match_protocol(record, protocol)
            observations = tuple(
                _require_record(index, observation_id, ObservationRecord)
                for observation_id in record.observation_ids
            )
            if observations and record.derived_at < max(item.observed_at for item in observations):
                raise ValueError("derived result predates one or more source observations")
            expected = derive_power_result(
                session_id=record.session_id,
                hypothesis_id=record.hypothesis_id,
                hypothesis=hypothesis,
                protocol=protocol,
                observations=observations,
                observation_pairs=tuple(
                    (block.baseline_observation_id, block.changed_observation_id)
                    for block in record.paired_blocks
                ),
                adherence=record.adherence,
                regressions=record.regressions,
                exclusions=record.exclusions,
                analysis_code_refs=record.analysis_code_refs,
            )
            for actual_block, expected_block in zip(
                record.paired_blocks, expected.paired_blocks, strict=True
            ):
                if not (
                    isclose(actual_block.baseline_watts, expected_block.baseline_watts)
                    and isclose(actual_block.changed_watts, expected_block.changed_watts)
                ):
                    raise ValueError("paired block values do not match their observations")
            comparable = {"threshold", "outcome", "systematic_allowance_watts", "observation_ids"}
            actual = record.model_dump(include=comparable, mode="json")
            calculated = expected.model_dump(include=comparable, mode="json")
            if actual != calculated:
                raise ValueError("derived result does not match the frozen deterministic calculation")
            _validate_artifact_refs(record.analysis_code_refs, artifacts, "analysis code")
            _validate_refs(
                tuple(ref for check in record.regressions for ref in check.evidence_refs),
                index,
                artifacts,
                "regression evidence",
            )
            _validate_refs(
                tuple(ref for exclusion in record.exclusions for ref in exclusion.evidence_refs),
                index,
                artifacts,
                "result exclusion evidence",
            )
            return

        if isinstance(record, ClaimEvidence):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            _match_parent(record, hypothesis)
            _validate_record_refs(record.record_refs, index, "claim record")
            _validate_artifact_refs(record.artifact_refs, artifacts, "claim artifact")
            return

        if isinstance(record, DecisionRecord):
            hypothesis = _require_record(index, record.hypothesis_id, HypothesisRecord)
            protocol = _require_record(index, record.protocol_id, ExperimentProtocol)
            result = _require_record(index, record.derived_result_id, DerivedResultRecord)
            _match_parent(record, hypothesis)
            _match_protocol(record, protocol)
            if (
                result.session_id != record.session_id
                or result.hypothesis_id != record.hypothesis_id
                or result.protocol_id != record.protocol_id
                or result.mode != record.mode
            ):
                raise ValueError("decision does not match its derived result lineage")
            if record.outcome != result.outcome:
                raise ValueError("decision outcome must match its derived result outcome")
            if record.decided_at < result.derived_at:
                raise ValueError("decision predates its derived result")
            if record.outcome == OutcomeCategory.POSITIVE and result.outcome != OutcomeCategory.POSITIVE:
                raise ValueError("a positive decision requires a matching positive derived result")
            cited_records = {
                ref
                for evidence in (*record.evidence, *record.counterevidence)
                for ref in evidence.record_refs
            }
            if record.derived_result_id not in cited_records:
                raise ValueError("decision evidence must cite its derived result")
            for evidence in (*record.evidence, *record.counterevidence):
                _validate_embedded_evidence(evidence, record, index, artifacts)
            return

        raise TypeError(f"unsupported scientific record {type(record).__name__}")

    def manifest(self, published: Iterable[PublishedScientificRecord]) -> EvidenceManifest:
        records = tuple(published)
        if not records:
            raise ValueError("an evidence manifest requires at least one record")
        if len(records) > 64:
            raise ValueError("a compact evidence manifest is limited to 64 records")
        session_id = records[0].record.session_id
        if any(item.record.session_id != session_id for item in records):
            raise ValueError("a manifest cannot mix sessions")
        entries = tuple(
            EvidenceManifestEntry(
                record_id=item.record.id,
                record_type=item.record.record_type,
                artifact_id=item.artifact_id,
                sha256=item.sha256,
                summary=_summary(item.record),
                outcome=_outcome(item.record),
                mode=item.record.mode,
            )
            for item in records
        )
        decisions = [item.record for item in records if isinstance(item.record, DecisionRecord)]
        counterevidence_ids = {
            item.record.id
            for item in records
            if isinstance(item.record, ClaimEvidence) and item.record.direction.value == "counters"
        }
        counterevidence_ids.update(
            evidence.id for decision in decisions for evidence in decision.counterevidence
        )
        return EvidenceManifest(
            session_id=session_id,
            entries=entries,
            positive_count=sum(entry.outcome == OutcomeCategory.POSITIVE for entry in entries),
            counterevidence_count=len(counterevidence_ids),
            invalid_count=sum(entry.outcome == OutcomeCategory.INVALID for entry in entries),
        )

    def brief(self, published: Iterable[PublishedScientificRecord]) -> EvidenceBrief:
        records = tuple(sorted(published, key=lambda item: item.created_at))
        manifest = self.manifest(records)
        resource_limits = self._core.snapshot(manifest.session_id).budget.model_dump(mode="json")
        hypotheses = [item.record for item in records if isinstance(item.record, HypothesisRecord)]
        results = [item.record for item in records if isinstance(item.record, DerivedResultRecord)]
        decisions = [item.record for item in records if isinstance(item.record, DecisionRecord)]
        claim_records = [item.record for item in records if isinstance(item.record, ClaimEvidence)]
        decision = decisions[-1] if decisions else None
        result = results[-1] if results else None
        hypothesis = hypotheses[-1] if hypotheses else None
        counter = (
            tuple(_compact(evidence.rationale) for evidence in decision.counterevidence[:12])
            if decision
            else ()
        )
        limitations = (
            tuple(_compact(item) for item in decision.unresolved_uncertainties[:12])
            if decision
            else _result_limitations(result)
        )
        claims_by_id = {item.id: item for item in claim_records}
        for item in decisions:
            claims_by_id.update(
                (evidence.id, evidence)
                for evidence in (*item.evidence, *item.counterevidence)
            )
        claims = list(claims_by_id.values())
        support = sorted(
            (item for item in claims if item.direction.value == "supports"),
            key=lambda item: {"strong": 0, "moderate": 1, "weak": 2}[item.strength],
        )
        counters = sorted(
            (item for item in claims if item.direction.value == "counters"),
            key=lambda item: {"strong": 0, "moderate": 1, "weak": 2}[item.strength],
        )
        competing = tuple(
            {
                "hypothesis_id": item.id,
                "statement": _compact(item.statement),
                "prediction": _compact(item.predicted_effect),
            }
            for item in reversed(hypotheses[-12:])
        )
        failed = tuple(
            _compact(f"{item.id}: {item.outcome.value}; hypothesis {item.hypothesis_id}")
            for item in results[-24:]
            if item.outcome in {OutcomeCategory.INCONCLUSIVE, OutcomeCategory.INVALID}
        )
        streaks = _uninformative_streaks(results)
        redesign_hypotheses = tuple(
            hypothesis_id for hypothesis_id, streak in streaks.items() if streak >= 2
        )
        streak = max(streaks.values(), default=0)
        finding = (
            _compact(decision.conclusion)
            if decision
            else _summary(result) if result else "Evidence collected; no derived result is recorded."
        )
        return EvidenceBrief(
            session_id=manifest.session_id,
            hypothesis=_compact(hypothesis.statement) if hypothesis else None,
            mode=(decision or result or hypothesis).mode if (decision or result or hypothesis) else None,
            finding=finding,
            outcome=decision.outcome if decision else result.outcome if result else None,
            evidence_refs=tuple(entry.artifact_id for entry in manifest.entries),
            counterevidence=tuple(
                _compact(item.rationale) for item in counters[:12]
            ) or counter,
            limitations=limitations,
            next_action=_compact(decision.next_action) if decision else None,
            competing_hypotheses=competing,
            strongest_support=tuple(
                _compact(
                    f"{item.strength}: {item.claim} — {item.rationale}; refs={','.join((*item.record_refs, *item.artifact_refs))}"
                )
                for item in support[:8]
            ),
            strongest_counterevidence=tuple(
                _compact(
                    f"{item.strength}: {item.claim} — {item.rationale}; refs={','.join((*item.record_refs, *item.artifact_refs))}"
                )
                for item in counters[:8]
            ),
            failed_attempts=failed,
            uninformative_streak=streak,
            redesign_checkpoint_required=bool(redesign_hypotheses),
            redesign_hypothesis_ids=redesign_hypotheses,
            resource_limits=resource_limits,
        )


def _require_record(
    index: dict[str, ScientificRecord],
    record_id: str,
    expected_type: type[ScientificRecord],
) -> ScientificRecord:
    record = index.get(record_id)
    if record is None:
        raise ValueError(f"referenced scientific record {record_id} is not published")
    if not isinstance(record, expected_type):
        raise ValueError(
            f"scientific record {record_id} is {record.record_type}, expected {expected_type.__name__}"
        )
    return record


def _latest_inconclusive_pair(
    records: dict[str, ScientificRecord], hypothesis_id: str
) -> tuple[str, str] | None:
    results = sorted(
        (
            record
            for record in records.values()
            if isinstance(record, DerivedResultRecord)
            and record.hypothesis_id == hypothesis_id
        ),
        key=lambda item: item.derived_at,
    )
    if len(results) < 2 or any(
        item.outcome != OutcomeCategory.INCONCLUSIVE for item in results[-2:]
    ):
        return None
    return (results[-2].id, results[-1].id)


def _uninformative_streaks(results: list[DerivedResultRecord]) -> dict[str, int]:
    grouped: dict[str, list[DerivedResultRecord]] = {}
    for result in results:
        grouped.setdefault(result.hypothesis_id, []).append(result)
    streaks: dict[str, int] = {}
    for hypothesis_id, values in grouped.items():
        streak = 0
        for result in sorted(values, key=lambda item: item.derived_at, reverse=True):
            if result.outcome != OutcomeCategory.INCONCLUSIVE:
                break
            streak += 1
        streaks[hypothesis_id] = streak
    return streaks


def _match_parent(record: ScientificRecord, hypothesis: HypothesisRecord) -> None:
    if record.session_id != hypothesis.session_id or record.mode != hypothesis.mode:
        raise ValueError("record and hypothesis session or study mode differ")


def _match_protocol(record: ScientificRecord, protocol: ExperimentProtocol) -> None:
    if (
        record.session_id != protocol.session_id
        or getattr(record, "hypothesis_id", None) != protocol.hypothesis_id
        or record.mode != protocol.mode
    ):
        raise ValueError("record and protocol lineage differ")


def _validate_refs(
    refs: Iterable[str],
    records: dict[str, ScientificRecord],
    artifacts: dict[str, ArtifactRecord],
    label: str,
) -> None:
    for ref in refs:
        if ref not in records and ref not in artifacts:
            raise ValueError(f"{label} reference {ref} is unknown or belongs to another session")


def _validate_record_refs(
    refs: Iterable[str], records: dict[str, ScientificRecord], label: str
) -> None:
    for ref in refs:
        if ref not in records:
            raise ValueError(f"{label} reference {ref} is not a published scientific record")


def _validate_artifact_refs(
    refs: Iterable[str], artifacts: dict[str, ArtifactRecord], label: str
) -> None:
    for ref in refs:
        artifact = artifacts.get(ref)
        if artifact is None or not artifact.available:
            raise ValueError(f"{label} reference {ref} is not an available session artifact")


def _validate_embedded_evidence(
    evidence: ClaimEvidence,
    decision: DecisionRecord,
    records: dict[str, ScientificRecord],
    artifacts: dict[str, ArtifactRecord],
) -> None:
    if (
        evidence.session_id != decision.session_id
        or evidence.hypothesis_id != decision.hypothesis_id
        or evidence.mode != decision.mode
    ):
        raise ValueError("embedded decision evidence is outside the decision lineage")
    published = _require_record(records, evidence.id, ClaimEvidence)
    if published != evidence:
        raise ValueError("embedded decision evidence differs from its published record")
    _validate_record_refs(evidence.record_refs, records, "decision evidence record")
    _validate_artifact_refs(evidence.artifact_refs, artifacts, "decision evidence artifact")


def _outcome(record: ScientificRecord) -> OutcomeCategory | None:
    return record.outcome if isinstance(record, (DerivedResultRecord, DecisionRecord)) else None


def _summary(record: ScientificRecord | None) -> str:
    if record is None:
        return "No derived result is recorded."
    if isinstance(record, HypothesisRecord):
        return _compact(f"Hypothesis: {record.statement}")
    if isinstance(record, ExperimentProtocol):
        return _compact(f"{record.mode.value} protocol: {record.title}")
    if isinstance(record, ObservationRecord):
        keys = ", ".join(sorted(record.measurements)) or "no scalar measurements"
        return _compact(f"Observation: {record.description} ({keys})")
    if isinstance(record, DerivedResultRecord):
        if record.threshold is None:
            return f"{record.outcome.value}: no valid paired-block estimate"
        estimate = record.threshold.estimated_reduction_percent
        return (
            f"{record.outcome.value}: estimated power reduction {estimate:.2f}% "
            f"across {record.threshold.block_count} paired blocks"
        )
    if isinstance(record, ClaimEvidence):
        return _compact(f"{record.direction.value} claim: {record.claim} ({record.strength})")
    if isinstance(record, RedesignCheckpointRecord):
        return _compact(f"Redesign checkpoint for {record.hypothesis_id}: {record.redesign}")
    return _compact(f"Decision: {record.outcome.value}; {record.conclusion}")


def _result_limitations(result: DerivedResultRecord | None) -> tuple[str, ...]:
    if result is None:
        return ("No derived result is recorded.",)
    limitations = [_compact(item) for item in result.adherence.violations]
    limitations.extend(
        _compact(exclusion.reason) for exclusion in result.exclusions if not exclusion.prespecified
    )
    limitations.extend(
        _compact(f"failed regression: {check.name} ({check.observed})")
        for check in result.regressions
        if not check.passed
    )
    if result.outcome == OutcomeCategory.INCONCLUSIVE:
        limitations.append("The frozen 95% rule does not distinguish the target effect from uncertainty.")
    return tuple(limitations[:12])


def _compact(value: str, limit: int = 320) -> str:
    flattened = " ".join(value.split())
    return flattened if len(flattened) <= limit else flattened[: limit - 1] + "…"
