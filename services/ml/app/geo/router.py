"""FastAPI router for Phase-7 geospatial analytics. GET endpoints the map UI
consumes; all aggregate server-side and return the AiResult contract."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from ..config import get_settings
from . import service
from .schemas import (AlertResponse, CaseLinksResponse, HotspotResponse, PointsResponse,
                      StationsResponse, TrendResponse)

router = APIRouter(prefix="/geo", tags=["geo"])


def _parse_bbox(bbox: Optional[str]):
    if not bbox:
        return None
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError
        return tuple(parts)  # minlon, minlat, maxlon, maxlat
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")


@router.get("/hotspots", response_model=HotspotResponse)
def hotspots(
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    start: Optional[dt.date] = None,
    end: Optional[dt.date] = None,
    crime_head_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(500, ge=1, le=2000),
):
    return service.hotspots(_parse_bbox(bbox), start, end, crime_head_id, limit)


@router.get("/trends", response_model=TrendResponse)
def trends(
    district_id: Optional[int] = Query(None, ge=1),
    crime_head_id: Optional[int] = Query(None, ge=1),
    sub_head_id: Optional[int] = Query(None, ge=1),
    start: Optional[dt.date] = None,
    end: Optional[dt.date] = None,
    window: int = Query(6, ge=2, le=24),
    k: float = Query(2.0, ge=0.5, le=5.0),
    decompose: bool = Query(True),
):
    return service.trends_series(district_id, crime_head_id, sub_head_id, start, end,
                                 window, k, decompose)


@router.get("/points", response_model=PointsResponse)
def points(
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    start: Optional[dt.date] = None,
    end: Optional[dt.date] = None,
    crime_head_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(5000, ge=1, le=20000),
    x_role: Optional[str] = Header(default=None),
):
    """Point-level incidents for the Live Map — blocked for policymaker (privacy cap)."""
    role = (x_role or get_settings().default_role or "investigator").strip()
    if role == "policymaker":
        raise HTTPException(
            status_code=403,
            detail="Point-level incident data is not available to the policymaker role "
                   "(district-aggregate views only).")
    return service.points(_parse_bbox(bbox), start, end, crime_head_id, limit)


@router.get("/stations", response_model=StationsResponse)
def stations(
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(1500, ge=1, le=2000),
    x_role: Optional[str] = Header(default=None),
):
    """Police stations for the map — blocked for policymaker (point-level pins)."""
    role = (x_role or get_settings().default_role or "investigator").strip()
    if role == "policymaker":
        raise HTTPException(
            status_code=403,
            detail="Station pins are not available to the policymaker role "
                   "(district-aggregate views only).")
    return service.stations(_parse_bbox(bbox), limit)


@router.get("/case-links", response_model=CaseLinksResponse)
def case_links(
    case_id: int = Query(..., ge=1),
    limit: int = Query(60, ge=1, le=200),
    x_role: Optional[str] = Header(default=None),
):
    """Geo-located cases linked to a case by shared accused — blocked for policymaker."""
    role = (x_role or get_settings().default_role or "investigator").strip()
    if role == "policymaker":
        raise HTTPException(status_code=403, detail="Not available to the policymaker role.")
    resp = service.case_links(case_id, limit)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return resp


@router.get("/alerts", response_model=AlertResponse)
def alerts(
    severity: Optional[str] = Query(None, pattern="^(info|low|medium|high|critical)$"),
    alert_type: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(200, ge=1, le=1000),
):
    return service.active_alerts(_parse_bbox(bbox), severity, alert_type, limit)
