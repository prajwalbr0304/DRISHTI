"""GET /outcomes/overview — aggregate court outcomes, confined to the caller's seat.

Unblocks the conviction-rate card, which existed on the state board in an honest
`pending` state because the data was reachable only per case and an aggregate-only
seat must not read case rows.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..org.deps import GeoScope, geo_scope
from . import service
from .schemas import OutcomesOverview

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.get("/overview", response_model=OutcomesOverview)
def overview(
    window_days: Optional[int] = Query(
        None, ge=1, le=3650,
        description="trailing window measured from the data's latest disposition"),
    geo: GeoScope = Depends(geo_scope),
):
    """Conviction rate and disposal mix for the caller's jurisdiction.

    Counts only, so it is available to every seat including the aggregate-only
    ones — which are the seats that most need it and were previously the reason it
    could not be built.
    """
    return service.outcomes_overview(
        district_ids=geo.effective_district_ids(), unit_id=geo.unit_id,
        crime_head_ids=geo.crime_head_ids, window_days=window_days)
