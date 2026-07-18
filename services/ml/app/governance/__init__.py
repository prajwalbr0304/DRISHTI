"""Phase 10 — governed feature & prediction contracts.

The safe bridge between verified inputs and any model:
FeatureDefinition -> FeatureSchemaVersion -> immutable FeatureSnapshot ->
PredictionRequest -> PredictionResult -> PredictionReview, with leakage-safe
OutcomeLabels and a governed ModelVersion. Nothing here operationalises the
synthetic offender-risk labels; predictions are aggregate decision-support only.
"""
