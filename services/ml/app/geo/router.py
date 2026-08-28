"""FastAPI router for Phase-7 geospatial analytics. GET endpoints the map UI
consumes; all aggregate server-side and return the AiResult contract."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from .. import db
from ..config import get_settings
from ..intake import guards
from ..roles import DEFAULT_ROLE
from . import boundaries as boundaries_mod
from . import jurisdiction
from . import service
from .schemas import (AlertResponse, CaseLinksResponse, ContainmentIssuesResponse,
                      ContainmentScanResponse, HotspotResponse, JurisdictionFreshnessResponse,
                      PointsResponse, ReassignRequest, ReassignResponse, StationsResponse,
                      TrendResponse)

router = APIRouter(prefix="/geo", tags=["geo"])

BOUNDARY_LEVELS = ("state", "districts", "taluks")
DB_BOUNDARY_LEVELS = ("state", "district", "taluk", "unit", "sho")

# Roles capped to district aggregates (no point-level incidents/pins/case links).
# INTERIM ("all roles have access to everything"): none. Add a role id here to
# re-impose the privacy cap; the check itself stays in one place.
POINT_LEVEL_DENY: frozenset[str] = frozenset()


def _require_point_level(x_role: Optional[str], what: str) -> str:
    """Enforce the point-level privacy cap for the resolved caller role."""
    role = (x_role or get_settings().default_role or DEFAULT_ROLE).strip()
    if role in POINT_LEVEL_DENY:
        raise HTTPException(
            status_code=403,
            detail=f"{what} is not available to the '{role}' role "
                   "(district-aggregate views only).")
    return role


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
    from ..cases import analytics_policy

    try:
        return service.hotspots(_parse_bbox(bbox), start, end, crime_head_id, limit)
    except analytics_policy.DerivedArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
    """Point-level incidents for the Live Map (privacy cap; see _require_point_level)."""
    _require_point_level(x_role, "Point-level incident data")
    return service.points(_parse_bbox(bbox), start, end, crime_head_id, limit)


@router.get("/stations", response_model=StationsResponse)
def stations(
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(1500, ge=1, le=2000),
    x_role: Optional[str] = Header(default=None),
):
    """Police stations for the map (point-level pins)."""
    _require_point_level(x_role, "Station pins")
    return service.stations(_parse_bbox(bbox), limit)


@router.get("/case-links", response_model=CaseLinksResponse)
def case_links(
    case_id: int = Query(..., ge=1),
    limit: int = Query(60, ge=1, le=200),
    x_role: Optional[str] = Header(default=None),
):
    """Geo-located cases linked to a case by shared accused (case-scoped)."""
    _require_point_level(x_role, "Linked-case geography")
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
    from ..cases import analytics_policy

    try:
        return service.active_alerts(_parse_bbox(bbox), severity, alert_type, limit)
    except analytics_policy.DerivedArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/coverage")
def coverage():
    """Date coverage of the operational dataset (min/max CrimeRegisteredDate + total).
    The UI anchors its time window to ``max_date`` so windows land on real data
    instead of the wall clock (the synthetic dataset is historical). Harmless
    aggregate metadata — available to every role."""
    from ..cases import casedata

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT MIN(cm."CrimeRegisteredDate")::text, '
                'MAX(cm."CrimeRegisteredDate")::text, COUNT(*) FROM "CaseMaster" cm '
                f'WHERE {casedata.analytics_eligible_sql("cm")}')
            mn, mx, n = cur.fetchone()
    return {"min_date": mn, "max_date": mx, "total": int(n)}


@router.get("/boundaries/{level}")
def boundaries(level: str):
    """Administrative boundary overlay as GeoJSON for the map — one of
    ``state | districts | taluks``. Public reference geography (real KGIS
    polygons), so available to every role (no point-level cap)."""
    if level not in BOUNDARY_LEVELS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown boundary level {level!r}; use one of {BOUNDARY_LEVELS}")
    try:
        text = boundaries_mod.load_boundary_text(level)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="boundary data not bundled with the service")
    # Served verbatim; cache aggressively (static reference geography).
    return Response(content=text, media_type="application/json",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/sho-regions")
def sho_regions(
    limit: int = Query(1500, ge=1, le=2000),
    x_role: Optional[str] = Header(default=None),
):
    """SHO (police-station jurisdiction) regions as GeoJSON: the Voronoi
    tessellation of station points clipped to each district, so the cells tile
    the district and follow the real data. Station-derived (point-level)."""
    _require_point_level(x_role, "SHO regions")
    resp = service.stations(None, limit)
    stations = [{
        "station_id": s.station_id, "name": s.name, "district": s.district,
        "lon": s.lon, "lat": s.lat, "case_count": s.case_count,
    } for s in resp.stations]
    return boundaries_mod.sho_regions_geojson(stations)


# =============================================================================
# Phase 9: DB-backed (persisted, versioned) boundaries + containment workflow.
# The map and the database share the SAME source of truth via these endpoints.
# =============================================================================
@router.get("/db-boundaries/{level}")
def db_boundaries(level: str):
    """Persisted, versioned jurisdiction boundary as GeoJSON straight from
    ``JurisdictionBoundary`` (state | district | taluk | unit/sho). This is the
    same geometry the database enforces containment against, so the UI and DB
    share one source of truth. Public reference geography."""
    if level not in DB_BOUNDARY_LEVELS:
        raise HTTPException(status_code=404,
                            detail=f"unknown level {level!r}; use one of {DB_BOUNDARY_LEVELS}")
    try:
        return jurisdiction.db_boundaries(level)
    except jurisdiction.JurisdictionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/jurisdiction/freshness", response_model=JurisdictionFreshnessResponse)
def jurisdiction_freshness():
    """Boundary versions/counts/as-of + the last containment scan (data freshness)."""
    return jurisdiction.freshness()


@router.get("/jurisdiction/issues", response_model=ContainmentIssuesResponse)
def jurisdiction_issues(status: str = Query("open", pattern="^(open|resolved|quarantined|accepted)$"),
                        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                        x_role: Optional[str] = Header(default=None)):
    """Reviewed-reassignment queue: canonical rows flagged for a jurisdiction
    mismatch (case-scoped)."""
    _require_point_level(x_role, "The jurisdiction review queue")
    return jurisdiction.containment_issues(status=status, page=page, page_size=page_size)


@router.post("/jurisdiction/scan", response_model=ContainmentScanResponse)
def jurisdiction_scan(scope: str = Query("all", pattern="^(caseversion|location_observation|all)$"),
                      role: str = Depends(guards.require_intake_review),
                      _w=Depends(guards.require_write_allowed)):
    """Scan canonical geography for containment failures and STAGE them as
    DataQualityIssues (never a silent move). Supervisory + synthetic-DB gated."""
    return jurisdiction.scan(scope=scope, actor=role)


@router.post("/jurisdiction/reassign", response_model=ReassignResponse)
def jurisdiction_reassign(body: ReassignRequest,
                          role: str = Depends(guards.require_intake_review),
                          _w=Depends(guards.require_write_allowed)):
    """Reviewed reassignment/override/quarantine of a case's jurisdiction.
    Supersedes the current CaseVersion, audits it, and resolves the issue."""
    try:
        return jurisdiction.reassign(
            body.case_master_id, body.to_district_id, body.actor or role, body.reason,
            body.action, body.data_quality_issue_id)
    except jurisdiction.JurisdictionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except jurisdiction.JurisdictionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
