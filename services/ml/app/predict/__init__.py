"""Prediction dispatch boundary (Phase 14, sections F + G).

This package is the Catalyst-side contract for the external AWS custom-model
plane. It never loads model weights in-process. It:

  * defines the versioned request/response ENVELOPE exchanged with the protected
    AWS adapter (SageMaker / AWS Batch) — see ``envelope.py``;
  * enforces the input-to-model ROUTING contract (G.1) so drafts and raw-file
    uploads never invoke a model — see ``routing.py``;
  * exposes a narrow AWS ADAPTER interface with an in-memory fake for tests and
    a signed-HTTPS implementation for deployment — see ``adapter.py``.

The heavy GPU/foundation packages (torch/tabfm/timesfm/...) live ONLY in
services/gpu-worker and run on AWS. Nothing here imports them.
"""
