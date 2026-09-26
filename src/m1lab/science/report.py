"""Render a reviewable Markdown report from validated scientific records."""

from __future__ import annotations

import json
from typing import Iterable

from .models import (
    ClaimEvidence,
    DecisionRecord,
    DerivedResultRecord,
    ExperimentProtocol,
    HypothesisRecord,
    ObservationRecord,
    PublishedScientificRecord,
    RedesignCheckpointRecord,
)


def render_scientific_report(
    session_id: str, published: Iterable[PublishedScientificRecord]
) -> str:
    """Render all records for one session without adding model interpretation."""

    entries = tuple(published)
    records = [entry.record for entry in entries]
    if any(record.session_id != session_id for record in records):
        raise ValueError("scientific report cannot mix sessions")
    lines = [
        f"# M1 Power Lab research report — `{session_id}`",
        "",
        "## Scope and qualification",
        "",
        "This report is a rendering of the session's validated immutable scientific records. It does not independently verify the underlying measurements, qualify the target transport or instrument, or establish an M1 power improvement. Check each observation's provenance and the project's qualification status before using a conclusion.",
        "",
        f"Published scientific records: **{len(entries)}**.",
        "",
        "## Decision history",
        "",
    ]

    decisions = sorted(
        (record for record in records if isinstance(record, DecisionRecord)),
        key=lambda item: item.decided_at,
    )
    if not decisions:
        lines.append("No scientific decision has been recorded.")
    for decision in decisions:
        lines.extend(
            [
                f"### {decision.id} — {decision.outcome.value}",
                "",
                f"- Hypothesis: `{decision.hypothesis_id}`",
                f"- Protocol: `{decision.protocol_id}`",
                f"- Derived result: `{decision.derived_result_id}`",
                f"- Conclusion: {decision.conclusion}",
                f"- Decision change: {decision.decision_delta}",
                f"- Next action: {decision.next_action}",
            ]
        )
        if decision.unresolved_uncertainties:
            lines.extend(["- Unresolved uncertainties:", *_bullets(decision.unresolved_uncertainties)])
        lines.append("")

    lines.extend(["## Hypotheses", ""])
    hypotheses = sorted(
        (record for record in records if isinstance(record, HypothesisRecord)),
        key=lambda item: item.created_at,
    )
    if not hypotheses:
        lines.append("No hypotheses have been published.")
    for hypothesis in hypotheses:
        lines.extend(
            [
                f"### {hypothesis.id} — {hypothesis.mode.value}",
                "",
                hypothesis.statement,
                "",
                f"- Proposed mechanism: {hypothesis.proposed_mechanism}",
                f"- Predicted effect: {hypothesis.predicted_effect}",
                f"- Primary metric: {hypothesis.primary_metric}",
                f"- Prior evidence: {_refs(hypothesis.prior_evidence_refs)}",
            ]
        )
        lines.extend(["- Falsifiers:", *_bullets(hypothesis.falsifiers)])
        lines.append("")

    lines.extend(["## Reproducible protocols", ""])
    protocols = sorted(
        (record for record in records if isinstance(record, ExperimentProtocol)),
        key=lambda item: item.created_at,
    )
    if not protocols:
        lines.append("No scientific protocols have been published.")
    for protocol in protocols:
        lines.extend(
            [
                f"### {protocol.id} — {protocol.title}",
                "",
                f"- Hypothesis: `{protocol.hypothesis_id}`; mode: {protocol.mode.value}",
                f"- Frozen at: {protocol.frozen_at or 'not frozen'}",
                f"- Workload: {protocol.workload}",
                f"- Baseline configuration digest: `{protocol.baseline_configuration_digest}`",
                f"- Changed configuration digest: `{protocol.changed_configuration_digest}`",
                f"- Block order: {protocol.block_order}",
                f"- Independent restart: {protocol.independent_restart}",
                f"- Warmup: {protocol.warmup}",
                f"- Sampling: {protocol.sampling}",
                f"- Stopping rule: {protocol.stopping_rule}",
                f"- Redesign checkpoint: {_refs((protocol.redesign_checkpoint_id,) if protocol.redesign_checkpoint_id else ())}",
                "",
                "Baseline configuration:",
                "```json",
                json.dumps(protocol.baseline_configuration, indent=2, sort_keys=True, ensure_ascii=False),
                "```",
                "",
                "Changed configuration:",
                "```json",
                json.dumps(protocol.changed_configuration, indent=2, sort_keys=True, ensure_ascii=False),
                "```",
                "",
                "Controlled conditions:",
                *_bullets(protocol.controlled_conditions),
                "",
                f"Decision rule: `{protocol.decision_rule.rule_id}` — {protocol.decision_rule.contrast}; 95% paired Student-t interval; systematic allowance {protocol.decision_rule.systematic_allowance_watts:g} W.",
                "",
                "Planned exclusions:",
                *_bullets(protocol.planned_exclusions),
                "",
                "Regression checks:",
                *_bullets(protocol.regression_checks),
                "",
            ]
        )

    lines.extend(["## Results and observations", ""])
    results = sorted(
        (record for record in records if isinstance(record, DerivedResultRecord)),
        key=lambda item: item.derived_at,
    )
    if not results:
        lines.append("No derived results have been published.")
    for result in results:
        lines.extend(
            [
                f"### {result.id} — {result.outcome.value}",
                "",
                f"- Hypothesis: `{result.hypothesis_id}`; protocol: `{result.protocol_id}`; mode: {result.mode.value}",
                f"- Adherence: {result.adherence.model_dump_json()}",
                f"- Analysis code references: {_refs(result.analysis_code_refs)}",
                f"- Systematic allowance: {result.systematic_allowance_watts:g} W",
            ]
        )
        if result.threshold:
            threshold = result.threshold
            lines.extend(
                [
                    f"- Estimate: {threshold.estimated_reduction_percent:.3f}% reduction across {threshold.block_count} paired blocks",
                    f"- 95% contrast interval: [{_number(threshold.lower_contrast_watts)}, {_number(threshold.upper_contrast_watts)}] W",
                    f"- Rule status: {threshold.status} — {threshold.explanation}",
                ]
            )
        lines.extend(["", "Paired blocks:", ""])
        for block in result.paired_blocks:
            lines.append(
                f"- `{block.baseline_observation_id}` → `{block.changed_observation_id}`: {block.baseline_watts:g} W → {block.changed_watts:g} W"
            )
        lines.extend(["", "Regressions:"])
        for check in result.regressions:
            lines.append(
                f"- {'PASS' if check.passed else 'FAIL'} — {check.name}: {check.observed}; criterion: {check.acceptance_criterion}; evidence: {_refs(check.evidence_refs)}"
            )
        if not result.regressions:
            lines.append("- None recorded.")
        lines.extend(["", "Exclusions:"])
        for exclusion in result.exclusions:
            lines.append(
                f"- {exclusion.subject}: {exclusion.reason} (prespecified={str(exclusion.prespecified).lower()}; evidence: {_refs(exclusion.evidence_refs)})"
            )
        if not result.exclusions:
            lines.append("- None recorded.")
        lines.append("")

    observations = sorted(
        (record for record in records if isinstance(record, ObservationRecord)),
        key=lambda item: item.observed_at,
    )
    if observations:
        lines.extend(["### Observation provenance", ""])
    for observation in observations:
        provenance = observation.provenance
        lines.extend(
            [
                f"#### {observation.id} — {observation.arm}, block `{observation.independent_block_id}`",
                "",
                f"- Hypothesis: `{observation.hypothesis_id}`; protocol: `{observation.protocol_id}`; mode: {observation.mode.value}",
                f"- Description: {observation.description}",
                f"- Measurements: `{json.dumps(observation.measurements, sort_keys=True)}`; units: `{json.dumps(provenance.units, sort_keys=True)}`",
                f"- Conditions: `{json.dumps(observation.conditions, sort_keys=True, ensure_ascii=False)}`",
                f"- Source: {provenance.source} ({provenance.source_version or 'version not recorded'})",
                f"- Target: {provenance.target_identity}; boot epoch `{provenance.target_boot_epoch}`; configuration `{provenance.target_configuration_digest}`",
                f"- Collector: {provenance.collector_host}; clock: {provenance.clock}; calibration: {provenance.calibration or 'not recorded'}",
                f"- Operation: {_refs((provenance.operation_id,) if provenance.operation_id else ())}",
                "- Raw artifacts:",
            ]
        )
        for artifact_id, digest in zip(
            provenance.raw_artifact_ids, provenance.raw_artifact_digests, strict=True
        ):
            lines.append(f"  - `{artifact_id}` — SHA-256 `{digest}`")
        lines.append("")

    lines.extend(["## Claims and counterevidence", ""])
    claims = sorted(
        (record for record in records if isinstance(record, ClaimEvidence)),
        key=lambda item: item.created_at,
    )
    if not claims:
        lines.append("No claim evidence has been published.")
    for claim in claims:
        lines.extend(
            [
                f"### {claim.direction.value} — {claim.strength}",
                "",
                claim.claim,
                "",
                f"- Hypothesis: `{claim.hypothesis_id}`; mode: {claim.mode.value}",
                f"- Rationale: {claim.rationale}",
                f"- Record references: {_refs(claim.record_refs)}",
                f"- Artifact references: {_refs(claim.artifact_refs)}",
            ]
        )
        lines.extend(["- Limitations:", *_bullets(claim.limitations), ""])

    checkpoints = sorted(
        (record for record in records if isinstance(record, RedesignCheckpointRecord)),
        key=lambda item: item.created_at,
    )
    if checkpoints:
        lines.extend(["## Redesign history", ""])
        for checkpoint in checkpoints:
            lines.extend(
                [
                    f"### {checkpoint.id} — `{checkpoint.hypothesis_id}`",
                    "",
                    f"- Triggering results: {_refs(checkpoint.triggering_result_ids)}",
                    f"- Findings: {checkpoint.findings}",
                    f"- Redesign: {checkpoint.redesign}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Record manifest",
            "",
            "Each record below is an immutable session artifact. Use `m1lab artifact-read ARTIFACT_ID` to retrieve its complete validated record.",
            "",
        ]
    )
    for entry in sorted(entries, key=lambda item: item.created_at):
        lines.append(
            f"- `{entry.record.id}` ({entry.record.record_type}) — artifact `{entry.artifact_id}`, SHA-256 `{entry.sha256}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def _bullets(values: Iterable[str]) -> list[str]:
    items = tuple(values)
    return [f"- {item}" for item in items] if items else ["- None recorded."]


def _refs(values: Iterable[str]) -> str:
    refs = tuple(values)
    return ", ".join(f"`{item}`" for item in refs) if refs else "None recorded"


def _number(value: float | None) -> str:
    return "not available" if value is None else f"{value:.6g}"
