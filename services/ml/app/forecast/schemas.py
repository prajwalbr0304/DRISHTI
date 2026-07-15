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
