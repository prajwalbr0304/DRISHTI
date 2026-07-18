"""Typed response models for the Phase-12 forecasting endpoints."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class LayerRun(BaseModel):
    layer: str
    model: Optional[str] = None
    model_version_id: Optional[int] = None
    written: int = 0


class FusedDistrict(BaseModel):
    district_id: int
    district: Optional[str] = None
    fused_count: float
    confidence: float
    risk_class: Optional[str] = None
    contributing_models: list[str] = []
    near_term_spike: bool = False


class ForecastRunResponse(BaseModel):
    result: AiResult
    head_id: Optional[int] = None
    horizon_days: int
    prediction_start: Optional[str] = None
    prediction_end: Optional[str] = None
    layers: list[LayerRun]
    alerts_written: int
    fused: list[FusedDistrict]
    governed: Optional["GovernedPersistence"] = None


class LayerInfo(BaseModel):
    layer: str
    model_name: str
    model_version_id: int
    predictions: int
    horizon_days: Optional[int] = None


class LayersResponse(BaseModel):
    result: AiResult
    layers: list[LayerInfo]


class LayerPrediction(BaseModel):
    layer: str
    model_name: Optional[str] = None
    predicted_count: Optional[float] = None
    probability: Optional[float] = None
    confidence: Optional[float] = None
    prediction_start: Optional[str] = None
    prediction_end: Optional[str] = None
    features: dict[str, Any] = {}


class DistrictForecastResponse(BaseModel):
    result: AiResult
    district_id: int
    district: Optional[str] = None
    head_id: Optional[int] = None
    layers: list[LayerPrediction]


class MapCell(BaseModel):
    prediction_id: int
    district_id: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    predicted_count: Optional[float] = None
    confidence: Optional[float] = None
    risk_class: Optional[str] = None


class ForecastMapResponse(BaseModel):
    result: AiResult
    layer: str
    head_id: Optional[int] = None
    count: int
    cells: list[MapCell]


class NearRepeatCell(BaseModel):
    lat: float
    lon: float
    intensity: float
    confidence: float
    contributing_events: int


class NearRepeatTriggerResponse(BaseModel):
    result: AiResult
    event: dict[str, Any]
    district_id: Optional[int] = None
    head_id: Optional[int] = None
    recent_events: int
    affected_cells: list[NearRepeatCell]


class ValidationResponse(BaseModel):
    result: AiResult
    cutoff: str
    horizon_months: int
    area_fraction: float
    overall: Optional[dict[str, Any]] = None
    per_crime_head: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Phase-12 backtest + data-freshness + governed-persistence responses
# ---------------------------------------------------------------------------
class BacktestResponse(BaseModel):
    """Rolling-origin backtest: model metrics vs baselines, coverage, geographic
    holdout and per-dimension error. Evidence a forecast is backtested and
    baseline-compared."""
    result: AiResult
    scope: dict[str, Any] = {}
    n_series: int = 0
    origins: list[str] = []
    scored_points: int = 0
    cells_considered: int = 0
    abstained_cells: int = 0
    abstention_rate: float = 0.0
    model: dict[str, Any] = {}
    baselines: dict[str, Any] = {}
    skill_vs_baselines: dict[str, Any] = {}
    beats_all_baselines: Optional[bool] = None
    error_by_district: list[dict[str, Any]] = []
    error_by_season: dict[str, Any] = {}
    error_by_head: dict[str, Any] = {}
    geo_holdout: dict[str, Any] = {}
    persisted_backtest_id: Optional[int] = None


class FreshnessResponse(BaseModel):
    """Data-as-of per source + approved external-context versions + the
    valid-geography scope applied to forecasts."""
    result: AiResult
    as_of: dict[str, Any] = {}
    case_data_stale_days: Optional[int] = None
    approved_sources: list[dict[str, Any]] = []
    valid_geography: dict[str, Any] = {}


class GovernedPersistence(BaseModel):
    """Summary of persisting the fused forecast through the governed
    FeatureSnapshot -> PredictionRequest -> PredictionResult contract."""
    model_version_id: Optional[int] = None
    feature_schema_version_id: Optional[int] = None
    snapshots_new: int = 0
    snapshots_reused: int = 0
    requests_new: int = 0
    results_new: int = 0
    superseded_prior: int = 0
    skipped: int = 0
    backtest_referenced: bool = False
    error: Optional[str] = None


# Resolve the forward reference to GovernedPersistence declared on ForecastRunResponse.
ForecastRunResponse.model_rebuild()
