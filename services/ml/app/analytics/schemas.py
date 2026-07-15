"""Typed models for the socio-economic correlation endpoint."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..contracts import AiResult
# The causation disclaimer is a mandatory part of the PAYLOAD (doc 03 §2.10,
# principle: never imply causation), not optional UI chrome. Canonical text lives
# in app.guards (shared honesty guards, Phase 13); re-exported here for callers.
from ..guards import CAUSATION_DISCLAIMER  # noqa: F401


class CorrelationCell(BaseModel):
    crime_category: str
    indicator: str
    r: Optional[float] = None       # Pearson correlation coefficient
    p_value: Optional[float] = None
    n: int                          # districts contributing (after suppression)
    strength: Optional[str] = None  # negligible/weak/moderate/strong
    direction: Optional[str] = None # positive/negative


class ScatterPoint(BaseModel):
    district_id: int
    district_name: str
    x: float                        # indicator value
    y: float                        # crime rate per 100k
    crime_count: int
    population: int


class ScatterSeries(BaseModel):
    crime_category: str
    indicator: str
    r: Optional[float] = None
    fit_slope: Optional[float] = None
    fit_intercept: Optional[float] = None
    points: list[ScatterPoint]


class NarrativeCard(BaseModel):
    headline: str
    detail: str
    disclaimer: str                 # always populated with CAUSATION_DISCLAIMER
    indicator: Optional[str] = None
    crime_category: Optional[str] = None
    r: Optional[float] = None
    threshold_value: Optional[float] = None
    pct_difference: Optional[float] = None


class SocioEconomicResponse(BaseModel):
    result: AiResult
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    indicators: list[str]
    crime_categories: list[str]
    districts_analysed: int
    k_threshold: int
    suppressed_cells: int
    focus_indicator: str
    correlation_matrix: list[CorrelationCell]
    scatter: list[ScatterSeries]
    narrative: NarrativeCard


# --- Crime Patterns (doc 01 §4.6) -------------------------------------------
class PatternLinkedCase(BaseModel):
    """One FIR that evidences a detected pattern."""
    case_id: int
    relevance: Optional[float] = None      # CrimePatternCase.Relevance in [0,1]
    crime_no: Optional[str] = None
    registered_date: Optional[str] = None
    crime_group: Optional[str] = None
    status: Optional[str] = None
    district: Optional[str] = None


class CrimePatternCard(BaseModel):
    pattern_id: int
    pattern_type: str                      # serial/spree/modus_operandi/temporal/...
    name: str
    description: Optional[str] = None
    crime_head_id: Optional[int] = None
    crime_group: Optional[str] = None
    model_version_id: Optional[int] = None
    model_version: Optional[str] = None    # ModelName@Version of the detector
    confidence: Optional[float] = None
    attributes: dict = {}
    detected_at: Optional[str] = None
    is_active: bool = True
    linked_case_count: int = 0             # total evidencing cases
    cases: list[PatternLinkedCase] = []    # a capped, top-relevance sample


class CrimePatternsResponse(BaseModel):
    result: AiResult
    total: int
    pattern_types: list[str]               # distinct types present (UI filter)
    by_type: dict[str, int]                # count per type
    items: list[CrimePatternCard]
