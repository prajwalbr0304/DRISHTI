"""Prediction dispatch boundary (Phase 14, sections F + G).

This package is the Catalyst-side contract for the external AWS custom-model
plane. It never loads model weights in-process. It:

  * defines the versioned request/response ENVELOPE exchanged with the protected
    AWS adapter (SageMaker / AWS Batch) — see ``envelope.py``;
  * enforces the input-to-model ROUTING contract (G.1) so drafts and raw-file
    uploads never invoke a model — see ``routing.py``;
  * exposes a narrow AWS ADAPTER interface with an in-memory fake for tests and
    a signed-HTTPS implementation for deployment — see ``adapter.py``.

Part G (ML/RAG placement + prediction runtime) adds, on top of the above:

  * ``placement.py`` — WHERE each model/assistant runs (QuickML RAG + no-code on
    Catalyst; TabFM/TimesFM/ST-GNN external AWS GPU; near-repeat/KDE/fusion on
    Catalyst CPU) + the verified Zia AutoML IN-DC unavailability;
  * ``dispatch_policy.py`` — HOW a job runs (AWS Batch scale-to-zero for offline;
    SageMaker async for measured near-real-time; real-time only after a benchmark;
    never Serverless for a GPU workload);
  * ``validation.py`` — fail-closed validation of the AWS result envelope;
  * ``lineage.py`` — model/version/feature lineage -> Data Store rows;
  * ``runtime.py`` — the governed end-to-end orchestrator (routing gate ->
    Data Store persist -> adapter -> validate -> Data Store result -> notice);
  * ``comparison.py`` — QuickML/no-code baseline vs the custom AWS model on the
    same split with leakage guardrails;
  * ``enablement.py`` — the demo-scoping source of truth (G.1/G.2): which routes +
    models are ENABLED vs documented-but-deferred; ``routing.py`` filters to the
    enabled tasks and ``placement.py`` records each engine's enablement;
  * ``capability_gaps.py`` — the per-AWS-path capability-gap justification (Part F).

The heavy GPU/foundation packages (torch/tabfm/timesfm/...) live ONLY in
services/gpu-worker and run on AWS. Nothing here imports them.
"""
