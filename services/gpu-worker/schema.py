"""Wire-contract mirror for the GPU worker (Prompt 14 G.5/G.6).

This is a SELF-CONTAINED copy of the request/response envelope. The worker is a
separate deployment image and must not import the FastAPI app. Keep this in sync
with services/ml/app/predict/envelope.py by ``ENVELOPE_VERSION`` — the version is
carried on the wire and both sides reject a mismatch.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

ENVELOPE_VERSION = "1.0.0"


class ModelTask(str, Enum):
    STATION_WORKLOAD_BAND = "station_workload_band"
    AREA_INCIDENT_FORECAST_TABFM = "area_incident_forecast_tabfm"
    TIMESFM_COUNT_FORECAST = "timesfm_count_forecast"
    STGNN_AREA_FORECAST = "stgnn_area_forecast"
    NEAR_REPEAT_INTENSITY = "near_repeat_intensity"
    HOTSPOT_CLUSTERS = "hotspot_clusters"
    FORECAST_FUSION = "forecast_fusion"


class BackendKind(str, Enum):
    TABFM = "tabfm"
    TABPFN = "tabpfn"
    INCONTEXT = "incontext"
    TIMESFM = "timesfm"
    STGNN = "stgnn"
    HAWKES = "hawkes"
    KDE = "kde"
    BASELINE = "baseline"


class JobState(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ColumnDef(BaseModel):
    name: str
    dtype: str = "float"
    role: str = "feature"


class PredictionRequestEnvelope(BaseModel):
    envelope_version: str = ENVELOPE_VERSION
    request_id: str
    idempotency_key: str
    task: ModelTask
    requested_backend: BackendKind
    feature_schema_version: str = ""
    model_version: str = ""
    context_version: Optional[str] = None
    feature_schema_digest: str = ""
    context_digest: Optional[str] = None
    # Expected weights digest — the worker verifies loaded weights against this.
    model_artifact_digest: Optional[str] = None
    subject_kind: str = "station"
    subject_ids: list[str] = Field(default_factory=list)
    observation_cutoff: str = ""
    source_version_hash: str = ""
    columns: list[ColumnDef] = Field(default_factory=list)
    context_x: Optional[list[list[float]]] = None
    context_y: Optional[list[int]] = None
    context_s3_uri: Optional[str] = None
    query_rows: list[list[float]] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    timeout_s: int = 900
    max_rows: int = 5000

    def validate_shapes(self) -> None:
        n_feat = sum(1 for c in self.columns if c.role == "feature")
        for i, row in enumerate(self.query_rows):
            if len(row) != n_feat:
                raise ValueError(f"query row {i}: {len(row)} != {n_feat} features")
        if self.context_x is not None:
            if self.context_y is None or len(self.context_x) != len(self.context_y):
                raise ValueError("context_x and context_y must be equal length")
        # TimesFM forecasts a univariate series carried in query_rows and needs no
        # labelled in-context examples; all other (classification) tasks require context.
        needs_context = self.task not in (ModelTask.TIMESFM_COUNT_FORECAST,)
        if needs_context and self.context_x is None and self.context_s3_uri is None:
            raise ValueError("context_x/y or context_s3_uri required")
        if len(self.query_rows) > self.max_rows:
            raise ValueError(f"{len(self.query_rows)} query rows > max_rows={self.max_rows}")

    def model_artifact_digest_expected(self) -> str:
        """The weights digest the worker must verify (empty => load default + report)."""
        return self.model_artifact_digest or ""


class PredictionResultEnvelope(BaseModel):
    envelope_version: str = ENVELOPE_VERSION
    request_id: str
    idempotency_key: str
    task: ModelTask
    state: JobState
    actual_backend: Optional[BackendKind] = None
    actual_device: Optional[str] = None
    model_artifact_digest: Optional[str] = None
    feature_schema_digest: Optional[str] = None
    context_digest: Optional[str] = None
    # Echoed observation cutoff so the UI can show data freshness of the result.
    observation_cutoff: Optional[str] = None
    predictions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = None
    abstained: Optional[bool] = None
    runtime_ms: Optional[int] = None
    cold_start_ms: Optional[int] = None
    peak_gpu_mem_mb: Optional[float] = None
    gpu_name: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    signature: Optional[str] = None
    signed_at: Optional[str] = None
