"""Typed response models for supervisor station/officer performance (Prompt 20 C)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AgeBucket(BaseModel):
    bucket: str
    count: int


class StationRow(BaseModel):
    unit_id: int
    unit_name: Optional[str] = None
    district_name: Optional[str] = None
    total: int
    open_cases: int
    new_cases: int
    overdue: int


class PerformanceResponse(BaseModel):
    scope: dict[str, Any]
    as_of: Optional[str] = None
    data_age_days: Optional[int] = None
    stale: bool = False
    empty: bool = False
    window_days: int
    totals: dict[str, Any] = Field(default_factory=dict)
    ageing: list[AgeBucket] = Field(default_factory=list)
    chargesheet: dict[str, Any] = Field(default_factory=dict)
    officers: dict[str, Any] = Field(default_factory=dict)
    workload_balance: dict[str, Any] = Field(default_factory=dict)
    stations: list[StationRow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    dataset: str = "synthetic"
