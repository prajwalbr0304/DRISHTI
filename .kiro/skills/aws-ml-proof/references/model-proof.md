# AWS model proof requirements

## TabFM

- Real TabFM package/weights and licence record;
- immutable image and artifact digests;
- actual CUDA device/runtime evidence;
- approved aggregate schema and context digest;
- request/result IDs, probabilities, confidence/abstention, latency, memory, cost;
- missing-CUDA/weight/schema failure that cannot masquerade as TabFM.

## TimesFM

- Version-pinned real TimesFM runtime;
- frequency, horizon, cutoff, gap handling, covariates, input digest;
- intervals/quantiles, freshness, backend/device, latency, warnings;
- same held-out split/baseline comparison used for enabled alternatives.

## Boundary and lifecycle

- No browser AWS access;
- no invocation for draft, unapproved, or raw-evidence events;
- idempotent retries produce one logical request/result;
- corrections stale/supersede prior results without deleting history;
- temporary GPU resources are stopped and verified after proof.
