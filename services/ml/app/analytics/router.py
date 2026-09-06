"""FastAPI router for Phase-8 socio-economic correlation analytics."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..org.deps import GeoScope, geo_scope
from . import service
from .schemas import CrimePatternsResponse, SocioEconomicResponse

router = APIRouter(prefix="/analytics", tags=["analytics"])

# valid pattern_type_enum values (police_fir_intelligence.sql)
_PATTERN_TYPES = "serial|spree|modus_operandi|temporal|spatial|network|repeat_offender"


@router.get("/socioeconomic", response_model=SocioEconomicResponse)
def socioeconomic(
    start: Optional[dt.date] = None,
    end: Optional[dt.date] = None,
    k_threshold: int = Query(25, ge=1, le=1000, description="small-N suppression threshold"),
    focus_indicator: Optional[str] = Query(
        None, description="indicator for the scatter series (auto if omitted)"),
):
    return service.socioeconomic_report(start, end, k_threshold, focus_indicator)


@router.get("/patterns", response_model=CrimePatternsResponse)
def patterns(
    pattern_type: Optional[str] = Query(None, pattern=f"^({_PATTERN_TYPES})$"),
    crime_head_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(60, ge=1, le=200),
    geo: GeoScope = Depends(geo_scope),
):
    """Detected crime patterns (serial/MO/temporal/spatial/network/…) + linked cases.

    A wing seat's crime-head confinement is applied. GEOGRAPHIC confinement is
    deliberately NOT applied: a pattern is a link between cases that may span
    districts by construction — a serial offender crossing a district boundary is
    precisely what the detection exists to surface, and filtering by the viewer's
    district would hide the cross-boundary patterns that matter most. The linked
    cases a viewer may then OPEN are confined by /cases.
    """
    head = crime_head_id
    if geo.crime_head_ids:
        head = head if head in geo.crime_head_ids else None
    return service.crime_patterns_report(pattern_type, head, limit,
                                         crime_head_ids=geo.crime_head_ids)
