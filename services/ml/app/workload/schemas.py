"""Typed request/response models for the aggregate workload task API (Phase 13)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkloadTaskResponse(BaseModel):
    task: str
    schema_name: str
    schema_version: str
    schema_approved: bool
    subject_kind: str
    bands: list[str]
    label_definition: str
    label_horizon_months: int
    aggregate_only: bool = True
    not_person_level: bool = True
    features: list[dict[str, Any]]
    limitations: str
    model_card: dict[str, Any]
    environment_label: str = "Synthetic Hackathon Demo"


class WorkloadModelInfo(BaseModel):
    model_version_id: int
    model_name: str
    version: str
    model_type: str
    approval_status: Optional[str] = None
    status: Optional[str] = None
    environment: Optional[str] = None
    feature_schema_version_id: Optional[int] = None
    training_dataset_snapshot_id: Optional[int] = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class WorkloadModelListResponse(BaseModel):
    models: list[WorkloadModelInfo]
    served_model_version_id: Optional[int] = None


class WorkloadPredictionRow(BaseModel):
    prediction_result_id: int
    prediction_request_id: Optional[int] = None
    unit_id: str
    unit_name: Optional[str] = None
    district_id: Optional[int] = None
    observation_cutoff: Optional[str] = None
    workload_band: Optional[str] = None
    band_ordinal: Optional[int] = None
    band_probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: Optional[float] = None
    abstained: Optional[bool] = None
    recent_case_volume: Optional[float] = None
    is_stale: bool = False
    model_version: Optional[str] = None
    created_at: Optional[str] = None
    # Real-backend/device provenance (populated when served via the AWS SageMaker
    # TabFM path; null for the CPU/in-context fallback) — surfaced so the UI can
    # show "computed on <GPU>" honestly.
    actual_backend: Optional[str] = None
    actual_device: Optional[str] = None
    gpu_name: Optional[str] = None
    served_via: Optional[str] = None
    model_artifact_digest: Optional[str] = None


class WorkloadPredictionListResponse(BaseModel):
    predictions: list[WorkloadPredictionRow]
    total: int
    page: int
    page_size: int
    cutoff_period: Optional[str] = None
    aggregate_only: bool = True
    limitations: str


class WorkloadEvaluationResponse(BaseModel):
    task: str
    schema_: str = Field(alias="schema")
    bands: list[str]
    band_thresholds: list[float]
    model: dict[str, Any]
    baselines: dict[str, Any]
    skill_vs_baselines: dict[str, Any]
    beats_all_baselines: bool
    abstention: dict[str, Any]
    metrics_by_time: dict[str, Any]
    metrics_by_geography: dict[str, Any]
    metrics_by_data_completeness: dict[str, Any]
    geo_holdout: dict[str, Any]
    leakage: dict[str, Any]
    splits: dict[str, Any]
    dataset: dict[str, Any]

    model_config = {"populate_by_name": True}


class WorkloadBenchmarkRow(BaseModel):
    model_name: str
    family: Optional[str] = None
    scale_label: Optional[str] = None
    row_scale: int
    device: Optional[str] = None
    fit_seconds: Optional[float] = None
    predict_seconds: Optional[float] = None
    total_seconds: Optional[float] = None
    latency_ms_per_row: Optional[float] = None
    throughput_rows_per_sec: Optional[float] = None
    peak_rss_mb: Optional[float] = None
    gpu_mem_mb: Optional[float] = None
    accuracy: Optional[float] = None
    macro_f1: Optional[float] = None
    qwk: Optional[float] = None
    ece: Optional[float] = None
    cost_estimate: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    note: Optional[str] = None
    created_at: Optional[str] = None


class WorkloadBenchmarkListResponse(BaseModel):
    benchmarks: list[WorkloadBenchmarkRow]
    assumptions: dict[str, Any] = Field(default_factory=dict)


class WorkloadRunRequest(BaseModel):
    foundation_kind: str = Field("tabpfn", description="incontext|tabpfn|tabfm|auto")
    limit: Optional[int] = Field(None, ge=1, le=2000, description="cap stations persisted")
    lifecycle: str = Field("staged", description="staged|shadow|active|retired")
    actor: Optional[str] = None


class WorkloadRunResponse(BaseModel):
    model_version_id: int
    feature_schema_version_id: int
    training_dataset_snapshot_id: int
    backend: str
    cutoff: str
    stations: int
    snapshots_new: int
    snapshots_reused: int
    requests_new: int
    results_new: int
    superseded_prior: int
    metrics: dict[str, Any]


class WorkloadLifecycleRequest(BaseModel):
    stage: str = Field(..., description="staged|shadow|active|retired")
    actor: Optional[str] = None


class WorkloadLifecycleResponse(BaseModel):
    model_version_id: int
    status: str
    approval_status: str
