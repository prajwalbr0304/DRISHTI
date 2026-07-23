"""Versioned request/response envelope for the external AWS model plane.

This is the ONLY payload shape crossing the Catalyst -> AWS boundary (Prompt 14
G.5 / G.6). It is deliberately minimal and safety-reviewed:

  * NEVER carries a full FIR JSON, narrative text, evidence bytes, or any DB
    secret / DATABASE_URL.
  * Carries only ids, versions, content hashes, the observation cutoff, ordered
    column definitions, labelled context (or an S3 context-snapshot URI) and
    unlabelled query rows.
  * The response envelope is signed/versioned and reports the ACTUAL backend and
    ACTUAL device, so a fallback can never be silently mislabelled as TabFM.

Both the AppSail service (this repo) and the AWS gpu-worker validate against this
contract. The worker keeps a mirror copy (services/gpu-worker/schema.py) because
it is a separate deployment image; the two must be kept in sync by version.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

ENVELOPE_VERSION = "1.0.0"


class ModelTask(str, Enum):
    """Approved, typed tasks. There is no generic "score everything" task."""
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


class DeviceKind(str, Enum):
    CUDA = "cuda"
    CPU = "cpu"


class DispatchMode(str, Enum):
    """How the AWS adapter should run the job."""
    SAGEMAKER_ASYNC = "sagemaker_async"       # small app-triggered, seconds/minutes
    SAGEMAKER_REALTIME = "sagemaker_realtime"  # only after a latency benchmark
    BATCH_TRANSFORM = "batch_transform"        # scheduled multi-area / backfill
    AWS_BATCH = "aws_batch"                     # GPU/CPU batch, scale-to-zero


class ColumnDef(BaseModel):
    name: str
    dtype: str = Field("float", description="float|int|categorical")
    role: str = Field("feature", description="feature|id|target")


class PredictionRequestEnvelope(BaseModel):
    """Catalyst -> AWS. Contains only versioned, hashed, non-sensitive inputs."""
    envelope_version: str = ENVELOPE_VERSION

    # Identity + idempotency.
    request_id: str = Field(..., description="unique per logical request")
    idempotency_key: str = Field(
        ...,
        description="<task>:<subject>:<cutoff>:<feature-schema-version>:"
                    "<model-version>:<source-version-hash>",
    )
    task: ModelTask
    requested_backend: BackendKind

    # Versions + content digests (never raw data).
    feature_schema_version: str
    model_version: str
    context_version: Optional[str] = None
    feature_schema_digest: str
    context_digest: Optional[str] = None
    # Expected model-weights digest — the GPU worker verifies loaded weights
    # against this and reports the actual digest back (fail closed on mismatch).
    model_artifact_digest: Optional[str] = None

    # Subject scoping + observation cutoff (leakage guard).
    subject_kind: str = Field(..., description="e.g. station|district|beat|area")
    subject_ids: list[str] = Field(default_factory=list)
    observation_cutoff: str = Field(..., description="ISO timestamp; no post-cutoff data")
    source_version_hash: str

    # Ordered columns + data.
    columns: list[ColumnDef]
    context_x: Optional[list[list[float]]] = Field(
        None, description="labelled in-context examples X (or use context_s3_uri)")
    context_y: Optional[list[int]] = Field(None, description="labels for context_x")
    context_s3_uri: Optional[str] = Field(
        None, description="approved S3 snapshot URI when context is not inlined")
    query_rows: list[list[float]] = Field(..., description="unlabelled rows to predict")

    # Output contract + limits.
    output_schema: dict[str, Any] = Field(default_factory=dict)
    dispatch_mode: DispatchMode = DispatchMode.SAGEMAKER_ASYNC
    timeout_s: int = Field(900, ge=1, le=86_400)
    max_rows: int = Field(5000, ge=1)

    def validate_shapes(self) -> None:
        """Reject mismatched row/column/context shapes before dispatch."""
        n_feat = sum(1 for c in self.columns if c.role == "feature")
        for i, row in enumerate(self.query_rows):
            if len(row) != n_feat:
                raise ValueError(
                    f"query row {i} has {len(row)} values, expected {n_feat} features")
        if self.context_x is not None:
            if self.context_y is None or len(self.context_x) != len(self.context_y):
                raise ValueError("context_x and context_y must be equal length")
            for i, row in enumerate(self.context_x):
                if len(row) != n_feat:
                    raise ValueError(
                        f"context row {i} has {len(row)} values, expected {n_feat}")
        # TimesFM forecasts a univariate series in query_rows and needs no labelled
        # in-context examples; classification tasks still require context.
        needs_context = self.task not in (ModelTask.TIMESFM_COUNT_FORECAST,)
        if needs_context and self.context_x is None and self.context_s3_uri is None:
            raise ValueError("either context_x/y or context_s3_uri is required")
        if len(self.query_rows) > self.max_rows:
            raise ValueError(f"{len(self.query_rows)} query rows exceeds max_rows={self.max_rows}")


class JobState(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class PredictionResultEnvelope(BaseModel):
    """AWS -> Catalyst. Signed/versioned. AppSail validates before persisting."""
    envelope_version: str = ENVELOPE_VERSION
    request_id: str
    idempotency_key: str
    task: ModelTask
    state: JobState

    # Truth about what actually ran — cannot be a fallback masquerading as TabFM.
    actual_backend: Optional[BackendKind] = None
    actual_device: Optional[DeviceKind] = None
    model_artifact_digest: Optional[str] = None
    feature_schema_digest: Optional[str] = None
    context_digest: Optional[str] = None
    # Echoed observation cutoff so the UI can show the data freshness of the result.
    observation_cutoff: Optional[str] = None

    # Predictions (shape depends on task; probabilities/quantiles/intervals).
    predictions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = None
    abstained: Optional[bool] = None

    # Observability.
    runtime_ms: Optional[int] = None
    cold_start_ms: Optional[int] = None
    peak_gpu_mem_mb: Optional[float] = None
    gpu_name: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_detail: Optional[str] = None

    # Signature (HMAC/JWS) over the canonical envelope, verified by AppSail.
    signature: Optional[str] = None
    signed_at: Optional[str] = None

    def is_authentic_backend(self, requested: BackendKind) -> bool:
        """True only if the job actually ran the requested backend. Used to
        FAIL-CLOSED: a tabfm request that came back as tabpfn/incontext is a
        contract violation, not a success."""
        return self.state == JobState.COMPLETED and self.actual_backend == requested
