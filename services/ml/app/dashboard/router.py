"""GET /dashboard/summary — count KPIs from the mv_case_daily rollup.

The fast path for the cards that dominate every board. Falls back to reporting WHY
the rollup was declined rather than silently serving stale figures, so the client
can retry the live path knowingly.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..org.deps import GeoScope, geo_scope
from . import service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class AgeBucket(BaseModel):
    bucket: str
    count: int


class DashboardSummary(BaseModel):
    scope: dict[str, Any] = Field(default_factory=dict)
    #: Always "mv_case_daily" here. Named so a caller comparing this with
    #: /performance/overview can see the two read different sources.
    source: str = "mv_case_daily"
    as_of: Optional[str] = None
    data_age_days: Optional[int] = None
    stale: bool = False
    empty: bool = True
    window_days: int
    window_start: Optional[str] = None
    #: Warnings about the data itself, as opposed to the standing `limitations`.
    #: Populated when the window opens inside a sparse tail, which makes the
    #: window figure unrepresentative while leaving the totals sound.
    data_notes: list[str] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    ageing: list[AgeBucket] = Field(default_factory=list)
    #: Refresh time and policy attestation of the rollup these figures came from.
    rollup: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    dataset: str = "synthetic"


@router.get("/summary", response_model=DashboardSummary)
def summary(window_days: int = Query(90, ge=1, le=365),
            geo: GeoScope = Depends(geo_scope)):
    """Case counts and open-case ageing for the caller's scope, from the rollup.

    One query over a table about a tenth the size of CaseMaster, replacing four
    sequential full scans. Officer load and chargesheet throughput are deliberately
    absent — the rollup carries no officer or chargesheet linkage, so those stay on
    /performance/overview rather than being approximated here.

    A 503 means the rollup was declined, not that the service is broken: the body
    says which of never-refreshed, no-attestation or policy-superseded applied, and
    the same figures remain available live from /performance/overview.
    """
    try:
        return service.dashboard_summary(
            district_ids=geo.effective_district_ids(),
            unit_id=geo.unit_id,
            crime_head_ids=geo.crime_head_ids,
            window_days=window_days)
    except service.RollupUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "reason": exc.reason,
                "message": exc.detail,
                "fallback": "/performance/overview serves the same counts live.",
            }) from exc
