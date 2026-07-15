"""Explainability & evidence trails (Phase 13 / doc 02 §10) — cross-cutting.

Makes the provenance contract real and uniform across every AI surface:

  * /explain/{table}/{id} — reconstruct the evidence chain for any
    CrimeRiskScore / CrimePrediction / AISummary / AlertHistory row: the typed
    row, its ModelInference INPUT SNAPSHOT (reproducibility), the ModelVersion,
    the source records, and (for risk) the gauge + signed factor-bars widget data.
  * /explain/models[/id] — Model Explainability: calibration/reliability from
    ModelVersion.Metrics + drift (confidence/volume over time) from the inference
    audit log, for the Analytics -> Model Explainability sub-page.
  * /explain/contract — a live audit that every AI route conforms to the AiResult
    contract.

Shared honesty guards (k-anonymity + causation disclaimer) live in app.guards.
"""
