"""Typed models for the risk-scoring endpoints."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class RiskFactor(BaseModel):
    feature: str
    label: str
    value: float
    contribution: float          # signed SHAP-style contribution
    direction: str               # increases / decreases


class RiskResponse(BaseModel):
    result: AiResult
    entity_id: int
    accused_master_id: Optional[int] = None
    offender_name: Optional[str] = None
    district_id: Optional[int] = None
    risk_band: str               # Low / Guarded / Elevated / High / Severe
    risk_level: str              # DB enum: low/medium/high/critical
    risk_score: float            # 0..1
    class_probabilities: dict[str, float]
    factors: list[RiskFactor]
    model_version: str
    scored_at: Optional[str] = None
    rescored: bool = False


class CalibrationResponse(BaseModel):
    result: AiResult
    n_train: int
    n_test: int
    foundation: dict[str, Any]
    baseline: dict[str, Any]
    agreement: float
