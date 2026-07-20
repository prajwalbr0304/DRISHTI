"""Typed models for the Live Command Center committed-FIR flow (Prompt 20 E)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class FirCommittedRequest(BaseModel):
    case_id: int = Field(..., ge=1)
    source_ts: Optional[str] = None


class ProcessedFirResponse(BaseModel):
    case_id: int
    dedup_key: str
    source_ts: Optional[str] = None
    processed_ts: str
    status: str
    district_id: Optional[int] = None
    projections: dict[str, Any] = Field(default_factory=dict)
    signal_published: bool = False
    detail: Optional[str] = None
    idempotent_replay: bool = False


class ProjectFirRequest(BaseModel):
    district_id: int = Field(..., ge=1)
    crime_head_id: Optional[int] = Field(None, ge=1)
    station_id: Optional[int] = Field(None, ge=1)


class FreshnessResponse(BaseModel):
    transport: str
    event_type: str
    processed_count: int
    duplicate_suppressed: int
    projections: dict[str, Any] = Field(default_factory=dict)
    recent: list[dict[str, Any]] = Field(default_factory=list)
    guarantees: dict[str, bool] = Field(default_factory=dict)
