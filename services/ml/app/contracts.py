"""Shared AI response contract used by every intelligence endpoint.

Mirrors doc 02 §10 / doc 01 §8.5 provenance chip:
    { answer, confidence, source_record_ids[], reasoning_summary, model_version }
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AiResult(BaseModel):
    """The single response shape every AI/analytics endpoint returns."""

    answer: str = Field(..., description="Human-readable result / decision-support statement.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence in [0,1].")
    source_record_ids: list[str] = Field(
        default_factory=list,
        description="Provenance: the DB record IDs backing this answer (e.g. 'CaseMaster:123').",
    )
    reasoning_summary: str = Field(
        default="", description="Short plain-language rationale (never chain-of-thought)."
    )
    model_version: str = Field(..., description="ModelName@Version of the model that produced this.")


class HealthReport(BaseModel):
    status: str  # "ok" | "degraded"
    app: str
    version: str
    database: bool
    extensions: dict[str, bool]
    detail: str = ""
