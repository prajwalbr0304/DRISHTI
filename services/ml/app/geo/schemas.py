"""Typed response models for the geospatial endpoints. Each envelope carries
the shared AiResult contract plus the typed payload."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class HotspotFeature(BaseModel):
    hotspot_id: int
    name: Optional[str] = None
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    crime_head_id: Optional[int] = None
    crime_group: Optional[str] = None
    intensity: Optional[float] = None
    case_count: Optional[int] = None
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    geometry: Optional[dict[str, Any]] = None  # GeoJSON polygon
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class HotspotResponse(BaseModel):
    result: AiResult
    count: int
    hotspots: list[HotspotFeature]


class TrendPoint(BaseModel):
    period: str            # 'YYYY-MM'
    count: int
    rolling_mean: Optional[float] = None
    rolling_upper: Optional[float] = None   # anomaly band upper (mean + k*std)
    rolling_lower: Optional[float] = None
    is_anomaly: bool = False


class TrendDecomposition(BaseModel):
    periods: list[str]
    trend: list[Optional[float]]
    seasonal: list[Optional[float]]
    residual: list[Optional[float]]


class TrendResponse(BaseModel):
    result: AiResult
    scope: dict[str, Any]
    total: int
    latest_period: Optional[str] = None
    mom_delta: Optional[int] = None
    mom_pct: Optional[float] = None
    yoy_delta: Optional[int] = None
    yoy_pct: Optional[float] = None
    series: list[TrendPoint]
    decomposition: Optional[TrendDecomposition] = None


class AlertFeature(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    title: str
    message: Optional[str] = None
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    crime_head_id: Optional[int] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    status: str
    payload: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None


class AlertResponse(BaseModel):
    result: AiResult
    count: int
    alerts: list[AlertFeature]


# ---- Phase 15f: raw incident points for the Live Map (authorised roles) -----

class PointFeature(BaseModel):
    case_id: int
    lon: float
    lat: float
    crime_head_id: Optional[int] = None
    crime_group: Optional[str] = None
    date: Optional[str] = None
    hour: Optional[int] = None          # incident hour (0-23) for time-of-day filtering


class PointsResponse(BaseModel):
    count: int
    capped: bool                       # True if the limit was hit (zoom/filter to refine)
    points: list[PointFeature]


# ---- Phase 15f: police stations (derived centroids of their geo-cases) ------

class StationFeature(BaseModel):
    station_id: int
    name: Optional[str] = None
    district: Optional[str] = None
    lon: float
    lat: float
    case_count: int
    top_crime: Optional[str] = None


class StationsResponse(BaseModel):
    count: int
    stations: list[StationFeature]


# ---- Phase 15f: geo-located linked cases (arc view) -------------------------

class CaseLinkNode(BaseModel):
    case_id: int
    lon: float
    lat: float
    crime_no: Optional[str] = None
    crime_group: Optional[str] = None
    via: Optional[str] = None            # the shared accused name


class CaseLinksResponse(BaseModel):
    source_case_id: int
    source_lon: Optional[float] = None
    source_lat: Optional[float] = None
    source_crime_no: Optional[str] = None
    count: int
    links: list[CaseLinkNode]


# ---- Phase 9: jurisdiction freshness / containment scan / reassignment ------

class JurisdictionFreshnessResponse(BaseModel):
    boundaries: dict[str, Any]           # level -> {count, version, as_of, source}
    unit_locations: int
    last_scan: Optional[dict[str, Any]] = None
    open_jurisdiction_issues: int = 0
    environment_label: str


class ContainmentScanResponse(BaseModel):
    run_id: int
    run_key: str
    scope: str
    checked: int
    out_of_state: int
    out_of_district: int
    issues_raised: int


class ContainmentIssue(BaseModel):
    data_quality_issue_id: int
    issue_type: str
    severity: str
    status: str
    case_master_id: Optional[int] = None
    crime_no: Optional[str] = None
    assigned_district_id: Optional[int] = None
    assigned_district_name: Optional[str] = None
    resolved_district_id: Optional[int] = None
    resolved_district_name: Optional[str] = None
    detail: dict[str, Any] = {}
    created_at: Optional[str] = None


class ContainmentIssuesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    status: str
    items: list[ContainmentIssue] = []


class ReassignRequest(BaseModel):
    case_master_id: int
    to_district_id: Optional[int] = None
    action: str = "reassign"             # reassign|override|quarantine
    reason: str
    data_quality_issue_id: Optional[int] = None
    actor: Optional[str] = None


class ReassignResponse(BaseModel):
    jurisdiction_reassignment_id: int
    case_master_id: int
    action: str
    from_district_id: Optional[int] = None
    to_district_id: Optional[int] = None
    new_case_version_id: int
    issues_resolved: int
    source_record_id: Optional[int] = None
