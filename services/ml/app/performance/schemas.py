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


class DistrictRow(BaseModel):
    """One district in the league table, carrying its own denominators.

    The denominators are part of the row on purpose: `open_cases` alone invites a
    ranking, and `stations` / `officers` / `new_cases` are what make the number
    readable as workload rather than as performance.
    """
    district_id: int
    district_name: Optional[str] = None
    total_cases: int
    open_cases: int
    new_cases: int
    overdue: int
    stations: int
    officers: int
    chargesheets_filed: int
    #: Filings over new cases in the same window. None — never 0 — when the window
    #: held no new cases, since a district with nothing registered has no rate.
    chargesheet_rate: Optional[float] = None
    open_per_station: Optional[float] = None


class DistrictPerformanceResponse(BaseModel):
    scope: dict[str, Any]
    as_of: Optional[str] = None
    data_age_days: Optional[int] = None
    stale: bool = False
    empty: bool = False
    window_days: int
    districts: list[DistrictRow] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    dataset: str = "synthetic"
