# Scientific records

Scientific claims form an immutable, validated lineage:

```text
hypothesis -> frozen protocol -> raw artifacts -> observations
           -> paired observation blocks -> derived result
           -> published claim evidence -> decision
```

Use `m1lab science publish RECORD.json` to publish hypotheses, protocols,
observations, claim evidence and decisions. The selected session must match the
record. Parent records and raw artifacts must already be published in that
session. Record IDs cannot be reused.

Each observation identifies its protocol arm and independent block. Its raw
artifact IDs and SHA-256 digests are required. The target identity,
configuration digest and declared primary metric unit are checked against the
session and protocol. Confirmation observations must follow the protocol freeze
time.

## Deterministic derivation

Create a derivation specification after publishing all observations:

```json
{
  "hypothesis_id": "hypothesis_...",
  "protocol_id": "protocol_...",
  "observation_pairs": [
    ["observation_baseline_block_1", "observation_changed_block_1"],
    ["observation_baseline_block_2", "observation_changed_block_2"]
  ],
  "adherence": {
    "protocol_id": "protocol_...",
    "protocol_frozen_before_collection": true,
    "independently_restarted_blocks": 2,
    "workload_matched": true,
    "configuration_matched": true,
    "sampling_complete": true,
    "violations": []
  },
  "regressions": [],
  "exclusions": [],
  "analysis_code_refs": []
}
```

Run:

```bash
m1lab --session SESSION_ID science derive derivation.json
m1lab --session SESSION_ID science list
m1lab --session SESSION_ID science brief
```

Derivation reads the primary metric from the cited observations. It does not
accept caller supplied power values. Every pair must contain one baseline and
one changed observation from the same unique independent block. The frozen
Student-t rule produces the outcome.

A decision must cite a previously published derived result through previously
published `claim_evidence`. Its session, hypothesis, protocol, mode and outcome
must match that result. A positive decision therefore cannot be published from
an inconclusive, negative, below-target or invalid result.

Validated scientific records and the latest compact brief appear in Codex's
evidence manifest, the operator evidence view and full JSON exports.

## Codex decision loop

The bounded Codex brief includes all recent competing hypotheses and their
predictions, strongest support and counterevidence, inconclusive or invalid
attempts, current resource limits, and whether a redesign checkpoint is due.
Codex must compare the selected experiment's decision value and total cost
(tokens, elapsed time, target-active time, and owner time) with a cheaper
alternative. These estimates are advisory; coordinator budget and operation
checks remain authoritative.

New or materially revised hypothesis proposals include the complete fields of a
`HypothesisRecord`, including a primary metric, falsifiers and references to
already published evidence. They are not added to the durable graph
automatically. After reviewing a completed turn, publish them explicitly with
stable IDs derived from that immutable job:

```bash
m1lab --session SESSION_ID science hypotheses --job-id JOB_ID
```

The command validates the prior evidence references against the selected
session. Repeating the command for the same completed job returns the same
records rather than duplicating them.

When a derived result exists, Codex also returns a typed `scientific_decision`
bound to its exact hypothesis, protocol, and result IDs. It must cite the result
in supporting or counterevidence, explain `decision_delta`, and propose a
`next_action`; the CLI takes the outcome only from the deterministic result.
The next evidence brief includes the recorded decision and its delta. Publish
the decision and its linked claim evidence from the completed output:

```bash
m1lab --session SESSION_ID science decision codex-output.json
```

Or publish directly from a completed Codex job without copying its output:

```bash
m1lab --session SESSION_ID science decision --job-id JOB_ID
```

This reads only the selected session's verified runtime event artifacts and
requires that job to be completed.

The command validates same-session scientific lineage and citations, then
publishes immutable claim evidence followed by the decision. If there is no
published derived result, Codex must set `scientific_decision` to `null`.
Publication IDs are stable for the selected completed job (or canonical output
file), so retrying after an interrupted CLI call reuses existing records and
does not duplicate the decision.

Codex also returns a typed procedure draft candidate. To validate the candidate
and freeze it as a content-digested procedure revision, copy the
`procedure_draft_candidate` object to a JSON file and run:

```bash
m1lab --session SESSION_ID procedure-register procedure-candidate.json
```

Completed job records list their runtime event artifact IDs; inspect the
completed job with `m1lab jobs --state completed`, then use
`m1lab artifact-read ARTIFACT_ID` to read the full event payload before copying
the structured object.

Registration performs `ProcedureDraft` validation and enters the separate
review phase. Run a new Codex turn against the exact registered procedure ID;
the coordinator binds its review manifest to the current revision and digest:

```bash
m1lab --session SESSION_ID investigate \
  --kind review --procedure-id PROCEDURE_ID \
  "Independently review this exact procedure for safety, discriminating value, controls, and recovery."
```

After that review job is complete, copy its `procedure_review` object to a JSON
file and record it against that completed review job:

```bash
m1lab --session SESSION_ID procedure-review \
  --reviewer-job REVIEW_JOB_ID procedure-review.json
```

The coordinator checks that the review job is complete, is a review job in the
same session, and that its procedure ID, revision, and digest match exactly.
Neither registration nor review approves execution; owner approval and the
existing target and recovery gates still apply.

When a redesign checkpoint is due, a registered scientific procedure must
identify its hypothesis, protocol, and matching checkpoint. This keeps a new
procedure from bypassing the protocol-level checkpoint gate.

## Redesign checkpoints

Two most recent inconclusive derived results for the same hypothesis block
publication of another protocol for that hypothesis until a redesign
checkpoint cites those exact result IDs. An invalid result does not count as
inconclusive. The Codex brief sets `redesign_checkpoint_required` and returns
the triggering results and required redesign. Record the checkpoint from the
Codex output with:

```bash
m1lab --session SESSION_ID science checkpoint codex-output.json \
  --hypothesis-id HYPOTHESIS_ID
```

The store rejects stale, mismatched, or incomplete checkpoint references. A
checkpoint records a design review; it does not authorize an experiment. The
next Codex brief uses the resulting observations, deterministic outcome,
decision, and checkpoint to revise the next recommendation.
