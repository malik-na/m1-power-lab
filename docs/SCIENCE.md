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
