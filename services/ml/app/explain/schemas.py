"""Typed models for the Phase-13 explainability endpoints."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class FactorBar(BaseModel):
    """One signed contribution for the gauge + factor-bars widget."""
    feature: str
    label: str
    value: Optional[float] = None
    contribution: float          # signed SHAP-style magnitude
    direction: str               # increases / decreases


class GaugeBars(BaseModel):
    """The risk gauge + signed factor bars payload (doc 02 §10)."""
    score: float                 # 0..1 gauge value
    level: str                   # DB enum: low/medium/high/critical
    band: Optional[str] = None   # Low..Severe
    class_probabilities: dict[str, float] = {}
    factors: list[FactorBar] = []


class ModelInfo(BaseModel):
    model_version_id: int
    model_name: str
    version: str
    model_type: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[str] = None
    hyperparameters: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    trained_at: Optional[str] = None
    deployed_at: Optional[str] = None


class InferenceAudit(BaseModel):
    inference_id: int
    matched_by: str              # exact | case+model | model_version
    input_snapshot: dict[str, Any] = {}
    output: dict[str, Any] = {}
    confidence: Optional[float] = None
    latency_ms: Optional[int] = None
    inferred_at: Optional[str] = None


class ExplainResponse(BaseModel):
    result: AiResult
    table: str
    record_id: str
    subject: dict[str, Any]
    model: Optional[ModelInfo] = None
    inference: Optional[InferenceAudit] = None
    gauge_bars: Optional[GaugeBars] = None      # populated for CrimeRiskScore
    source_record_ids: list[str] = []
    reproducible: bool = False
    reproducibility_note: str = ""


class ModelCard(BaseModel):
    model_version_id: int
    model_name: str
    version: str
    model_type: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[str] = None
    calibration: dict[str, Any] = {}            # ModelVersion.Metrics
    inferences: int = 0
    mean_confidence: Optional[float] = None
    first_inference: Optional[str] = None
    last_inference: Optional[str] = None


class ModelsResponse(BaseModel):
    result: AiResult
    count: int
    models: list[ModelCard]


class DriftPoint(BaseModel):
    period: str                  # YYYY-MM
    count: int
    mean_confidence: Optional[float] = None


class ModelDetailResponse(BaseModel):
    result: AiResult
    model: ModelCard
    calibration: dict[str, Any]
    drift: list[DriftPoint]
    drift_flag: str              # stable | rising_confidence | falling_confidence | insufficient
    notes: str


class ContractRoute(BaseModel):
    path: str
    methods: str
    response_model: Optional[str] = None
    conforms: bool
    via: str


class ContractAuditResponse(BaseModel):
    result: AiResult
    total: int
    conforming: int
    non_conforming: int
    routes: list[ContractRoute]
