"""Typed request/response models for the Phase-10 governance API.

The governed bridge between verified inputs and any model: feature definitions ->
approved schema versions -> immutable feature snapshots -> prediction requests ->
results -> mandatory human review. Predictions are aggregate decision-support
only; no protected attribute enters a prediction schema; every result ties to an
immutable snapshot with an observation cutoff and content hash.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts import AiResult


# ---------------------------------------------------------------------------
# Registry — feature definitions / schema versions
# ---------------------------------------------------------------------------
class FeatureDefinitionOut(BaseModel):
    feature_definition_id: int
    name: str
    value_type: str
    description: Optional[str] = None
    source_table: Optional[str] = None
    source_field: Optional[str] = None
    source_event: Optional[str] = None
    transformation: Optional[str] = None
    window_spec: Optional[str] = None
    observation_cutoff_behavior: str
    sensitivity: str
    allowed_tasks: list[str] = Field(default_factory=list)
    missing_policy: str
    stale_policy: str
    owner: Optional[str] = None
    approval_status: str


class FeatureDefinitionListResponse(BaseModel):
    total: int
    items: list[FeatureDefinitionOut] = Field(default_factory=list)


class FeatureSchemaVersionOut(BaseModel):
    feature_schema_version_id: int
    schema_name: str
    version: str
    feature_definition_ids: list[int] = Field(default_factory=list)
    task: Optional[str] = None
    status: str
    approved_by_actor: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    features: list[FeatureDefinitionOut] = Field(default_factory=list)
    has_protected_feature: bool = False


class FeatureSchemaListResponse(BaseModel):
    total: int
    items: list[FeatureSchemaVersionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Feature snapshots
# ---------------------------------------------------------------------------
class FeatureSnapshotOut(BaseModel):
    feature_snapshot_id: int
    feature_schema_version_id: Optional[int] = None
    subject_kind: str
    subject_ref_id: str
    observation_cutoff: Optional[str] = None
    values: dict[str, Any] = Field(default_factory=dict)
    source_versions: dict[str, Any] = Field(default_factory=dict)
    quality_status: str
    content_hash: str
    is_immutable: bool = True
    superseded_by_feature_snapshot_id: Optional[int] = None
    stale_reason: Optional[str] = None
    superseded_at: Optional[str] = None
    built_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class FeatureSnapshotListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FeatureSnapshotOut] = Field(default_factory=list)


class BuildSnapshotRequest(BaseModel):
    feature_schema_version_id: int = Field(..., ge=1)
    subject_kind: str = Field("area_district", pattern="^(area_district|area_unit|beat_window|case|aggregate)$")
    subject_ref_id: str = Field(..., description="e.g. the DistrictID as text.")
    observation_cutoff: Optional[str] = Field(None, description="ISO datetime; defaults to latest-registration minus 180d.")
    actor: Optional[str] = None


class BuildSnapshotResult(BaseModel):
    feature_snapshot_id: int
    feature_schema_version_id: int
    subject_kind: str
    subject_ref_id: str
    observation_cutoff: Optional[str] = None
    values: dict[str, Any] = Field(default_factory=dict)
    source_versions: dict[str, Any] = Field(default_factory=dict)
    quality_status: str
    content_hash: str
    is_immutable: bool = True
    unknown_features: list[str] = Field(default_factory=list)
    built_by_actor: Optional[str] = None
    created_at: Optional[str] = None
    reused: bool = False


class InvalidateSnapshotRequest(BaseModel):
    subject_kind: str = Field(..., pattern="^(area_district|area_unit|beat_window|case|aggregate)$")
    subject_ref_id: str
    reason: str = Field(..., min_length=3, description="Why the snapshot(s) are now stale (audited).")
    actor: Optional[str] = None


class InvalidateSnapshotResult(BaseModel):
    subject_kind: str
    subject_ref_id: str
    snapshots_marked_stale: int
    results_marked_stale: int
    requests_marked_stale: int


# ---------------------------------------------------------------------------
# Model versions (governance view)
# ---------------------------------------------------------------------------
class ModelVersionOut(BaseModel):
    model_version_id: int
    model_name: str
    model_type: Optional[str] = None
    version: str
    framework: Optional[str] = None
    artifact_uri: Optional[str] = None
    artifact_digest: Optional[str] = None
    image_digest: Optional[str] = None
    feature_schema_version_id: Optional[int] = None
    training_dataset_snapshot_id: Optional[int] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    environment: Optional[str] = None
    evaluation_report: dict[str, Any] = Field(default_factory=dict)
    status: Optional[str] = None
    is_rollback_target: bool = False
    rollback_to_model_version_id: Optional[int] = None


class ModelVersionListResponse(BaseModel):
    total: int
    items: list[ModelVersionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------
class PredictionReviewOut(BaseModel):
    prediction_review_id: int
    reviewer_actor: Optional[str] = None
    decision: str
    override_reason: Optional[str] = None
    reviewed_at: Optional[str] = None


class PredictionResultOut(BaseModel):
    prediction_result_id: int
    model_version_id: Optional[int] = None
    feature_snapshot_id: Optional[int] = None
    output: dict[str, Any] = Field(default_factory=dict)
    explanation: dict[str, Any] = Field(default_factory=dict)
    limitations: Optional[str] = None
    confidence: Optional[float] = None
    lower_interval: Optional[float] = None
    upper_interval: Optional[float] = None
    expires_at: Optional[str] = None
    is_stale: bool = False
    stale_reason: Optional[str] = None
    superseded_by_result_id: Optional[int] = None
    created_at: Optional[str] = None


class PredictionRequestOut(BaseModel):
    prediction_request_id: int
    model_version_id: Optional[int] = None
    model_version_label: Optional[str] = None
    feature_snapshot_id: Optional[int] = None
    request_kind: str
    idempotency_key: Optional[str] = None
    status: str
    requested_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class PredictionRequestListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PredictionRequestOut] = Field(default_factory=list)


class PredictionDetail(BaseModel):
    request: PredictionRequestOut
    result: Optional[PredictionResultOut] = None
    reviews: list[PredictionReviewOut] = Field(default_factory=list)
    feature_snapshot: Optional[FeatureSnapshotOut] = None
    model_version: Optional[ModelVersionOut] = None
    is_current: bool = True
    answer: Optional[AiResult] = None


class CreatePredictionRequest(BaseModel):
    model_version_id: int = Field(..., ge=1)
    feature_snapshot_id: int = Field(..., ge=1)
    request_kind: str = Field("batch", pattern="^(batch|adhoc|shadow)$")
    idempotency_key: Optional[str] = None
    actor: Optional[str] = None


class RunPredictionRequest(BaseModel):
    actor: Optional[str] = None


class ReviewPredictionRequest(BaseModel):
    decision: str = Field(..., pattern="^(accept|override|reject)$")
    override_reason: Optional[str] = None
    actor: Optional[str] = None


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
class OutcomeLabelOut(BaseModel):
    outcome_label_id: int
    case_master_id: Optional[int] = None
    subject_kind: str
    subject_ref_id: Optional[str] = None
    label_name: str
    label_value: Optional[str] = None
    outcome_observation_id: Optional[int] = None
    observation_cutoff: Optional[str] = None
    label_window_start: Optional[str] = None
    label_window_end: Optional[str] = None
    split_tag: Optional[str] = None


class OutcomeLabelListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    leakage_safe: bool = True
    splits: dict[str, int] = Field(default_factory=dict)
    items: list[OutcomeLabelOut] = Field(default_factory=list)
