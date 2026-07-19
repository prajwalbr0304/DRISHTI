"""Typed request/response models for the Emergency Response API (Prompt 17).

Field naming is snake_case at the API boundary (as elsewhere); the service maps
to the PascalCase Data Store columns. Enum values are validated as literals
server-side against the ``disaster_schema`` tuples. GeoJSON is validated +
size-limited before anything is stored.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts import AiResult
from ..datastore import disaster_schema as ds

HAZARD_CODES = ds.HAZARD_CODES
HAZARD_STATUSES = ds.HAZARD_STATUSES
HAZARD_SEVERITIES = ds.HAZARD_SEVERITIES
HYDROMET_METRICS = ds.HYDROMET_METRICS
RESOURCE_TYPES = ds.RESOURCE_TYPES
RESOURCE_STATUSES = ds.RESOURCE_STATUSES
ALLOCATION_STATUSES = ds.ALLOCATION_STATUSES


# ---------------------------------------------------------------------------
# generic
# ---------------------------------------------------------------------------
class MutationResult(BaseModel):
    ok: bool = True
    id: Optional[int] = None
    kind: str = ""
    status: Optional[str] = None
    version: Optional[int] = None
    activity_id: Optional[int] = None
    idempotent_replay: bool = False
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------
class HazardTypeOut(BaseModel):
    hazard_type_id: int
    code: str
    name: str
    category: Optional[str] = None
    default_lead_time_hours: Optional[int] = None
    active: bool = True


# ---------------------------------------------------------------------------
# hazard events
# ---------------------------------------------------------------------------
class HazardEventCreate(BaseModel):
    hazard_code: str
    status: str = "predicted"
    severity: str = "moderate"
    district_id: Optional[int] = Field(None, ge=1)
    unit_id: Optional[int] = Field(None, ge=1)
    geojson: dict[str, Any] = Field(default_factory=dict)
    onset_at: Optional[str] = None
    predicted_peak_at: Optional[str] = None
    source: Optional[str] = Field(None, max_length=200)
    source_version: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=4000)


class HazardEventPatch(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = Field(None, max_length=4000)
    predicted_peak_at: Optional[str] = None
    expected_version: Optional[int] = None


class HazardEventOut(BaseModel):
    hazard_event_id: int
    hazard_code: str
    status: str
    severity: str
    district_id: Optional[int] = None
    unit_id: Optional[int] = None
    geojson: dict[str, Any] = Field(default_factory=dict)
    centroid: Optional[list[float]] = None
    onset_at: Optional[str] = None
    predicted_peak_at: Optional[str] = None
    source: Optional[str] = None
    source_version: Optional[str] = None
    description: Optional[str] = None
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# risk zones + predictions
# ---------------------------------------------------------------------------
class HazardRiskZoneOut(BaseModel):
    hazard_risk_zone_id: int
    hazard_code: str
    zone_kind: str
    name: Optional[str] = None
    district_id: Optional[int] = None
    geojson: dict[str, Any] = Field(default_factory=dict)
    centroid: Optional[list[float]] = None
    risk_level: str
    score: Optional[float] = None
    factors: dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    source: Optional[str] = None
    is_active: bool = True


class HazardPredictionOut(BaseModel):
    hazard_prediction_id: int
    hazard_code: str
    hazard_event_id: Optional[int] = None
    model_version_label: Optional[str] = None
    feature_snapshot_id: Optional[str] = None
    district_id: Optional[int] = None
    geojson: dict[str, Any] = Field(default_factory=dict)
    forecast_start: Optional[str] = None
    forecast_end: Optional[str] = None
    horizon_hours: Optional[int] = None
    data_as_of: Optional[str] = None
    probability: Optional[float] = None
    predicted_severity: Optional[str] = None
    expected_impact: dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    factors: dict[str, Any] = Field(default_factory=dict)
    baseline_comparison: dict[str, Any] = Field(default_factory=dict)
    quality_state: str = "ok"
    superseded_by_id: Optional[int] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# hydro-met readings + feeds
# ---------------------------------------------------------------------------
class FeedIngestRequest(BaseModel):
    feed_code: str = Field("synthetic_replay", max_length=80)
    # optional inline batch of reading candidates (else the connector replays its
    # bundled deterministic sample)
    readings: Optional[list[dict[str, Any]]] = None


class FeedRunOut(BaseModel):
    feed_ingestion_run_id: int
    feed_code: str
    status: str
    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    last_observed_at: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class FeedFreshnessOut(BaseModel):
    feed_code: str
    provider: Optional[str] = None
    connector_kind: str
    external_access_required: bool = False
    freshness_sla_minutes: Optional[int] = None
    last_observed_at: Optional[str] = None
    last_run_at: Optional[str] = None
    age_minutes: Optional[float] = None
    status: str = "unknown"     # fresh | stale | failed | never
    licence: Optional[str] = None
    attribution: Optional[str] = None


class HydroMetReadingOut(BaseModel):
    hydromet_reading_id: int
    station_code: str
    source_agency: Optional[str] = None
    metric_type: str
    value: Optional[float] = None
    unit: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    district_id: Optional[int] = None
    observed_at: Optional[str] = None
    received_at: Optional[str] = None
    quality_flag: str = "valid"
    superseded_by_id: Optional[int] = None


# ---------------------------------------------------------------------------
# resources + shelters
# ---------------------------------------------------------------------------
class ResourceCreate(BaseModel):
    resource_type: str
    name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(1, ge=0)
    unit: Optional[str] = Field(None, max_length=40)
    home_unit_id: Optional[int] = Field(None, ge=1)
    employee_id: Optional[int] = Field(None, ge=1)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    district_id: Optional[int] = Field(None, ge=1)
    capacity: Optional[int] = Field(None, ge=0)
    capabilities: list[str] = Field(default_factory=list)
    status: str = "available"


class ResourcePatch(BaseModel):
    status: Optional[str] = None
    quantity: Optional[int] = Field(None, ge=0)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    capacity: Optional[int] = Field(None, ge=0)
    expected_version: Optional[int] = None


class ResourceOut(BaseModel):
    resource_id: int
    resource_type: str
    name: str
    quantity: int
    unit: Optional[str] = None
    home_unit_id: Optional[int] = None
    employee_id: Optional[int] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    district_id: Optional[int] = None
    capacity: Optional[int] = None
    capabilities: list[str] = Field(default_factory=list)
    status: str
    version: int = 1
    last_updated_at: Optional[str] = None


class ShelterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    district_id: Optional[int] = Field(None, ge=1)
    capacity: int = Field(0, ge=0)
    current_occupancy: int = Field(0, ge=0)
    facilities: list[str] = Field(default_factory=list)
    status: str = "open"


class ShelterPatch(BaseModel):
    current_occupancy: Optional[int] = Field(None, ge=0)
    capacity: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    expected_version: Optional[int] = None


class ShelterOut(BaseModel):
    relief_shelter_id: int
    name: str
    lon: Optional[float] = None
    lat: Optional[float] = None
    district_id: Optional[int] = None
    capacity: int = 0
    current_occupancy: int = 0
    facilities: list[str] = Field(default_factory=list)
    status: str = "open"
    version: int = 1


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------
class ForecastRunRequest(BaseModel):
    hazard_code: str
    district_id: int = Field(..., ge=1)
    horizon_hours: int = Field(48, ge=1, le=240)
    data_as_of: Optional[str] = None       # observation cutoff; default = now
    create_event_proposal: bool = False    # propose a watch/warning (never auto)


class ForecastRunResponse(BaseModel):
    result: AiResult
    prediction: HazardPredictionOut
    baseline_comparison: dict[str, Any] = Field(default_factory=dict)
    escalation: Optional[str] = None       # set when stale/low-confidence -> human
    event_proposal_id: Optional[int] = None


class ForecastValidationResponse(BaseModel):
    hazard_code: str
    model_version_label: str
    n_origins: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    baselines: dict[str, Any] = Field(default_factory=dict)
    skill_vs_baseline: dict[str, Any] = Field(default_factory=dict)
    holdout: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# alerts (reuse AlertHistory) — proposal requires human confirmation
# ---------------------------------------------------------------------------
class AlertProposeRequest(BaseModel):
    hazard_event_id: int = Field(..., ge=1)
    alert_type: str = Field(..., max_length=60)   # e.g. flood_warning
    severity: str = "warning"
    title: str = Field(..., min_length=1, max_length=200)
    message: Optional[str] = Field(None, max_length=2000)


class AlertOut(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    title: str
    message: Optional[str] = None
    hazard_event_id: Optional[int] = None
    district_id: Optional[int] = None
    status: str = "proposed"
    confidence: Optional[float] = None
    freshness: Optional[str] = None
    synthetic: bool = True
    acknowledged_by: Optional[str] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# allocation
# ---------------------------------------------------------------------------
class AllocationPlanRequest(BaseModel):
    hazard_event_id: int = Field(..., ge=1)
    required: dict[str, int] = Field(default_factory=dict,
                                     description="resource_type -> required quantity")
    max_distance_km: float = Field(120.0, gt=0, le=1000)
    optimizer: str = Field("greedy", description="greedy | ortools")


class AllocationProposalOut(BaseModel):
    hazard_event_id: int
    optimizer: str
    proposals: list["AllocationOut"] = Field(default_factory=list)
    unmet: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    comparison: dict[str, Any] = Field(default_factory=dict)


class AllocationOut(BaseModel):
    resource_allocation_id: Optional[int] = None
    hazard_event_id: Optional[int] = None
    resource_id: Optional[int] = None
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    target_zone_id: Optional[int] = None
    quantity_allocated: int = 0
    status: str = "proposed"
    score: Optional[float] = None
    reason: dict[str, Any] = Field(default_factory=dict)
    district_id: Optional[int] = None
    proposed_at: Optional[str] = None
    approved_at: Optional[str] = None
    dispatched_at: Optional[str] = None
    enroute_at: Optional[str] = None
    onsite_at: Optional[str] = None
    released_at: Optional[str] = None


class AllocationTransitionRequest(BaseModel):
    confirm: bool = False
    note: Optional[str] = Field(None, max_length=1000)
    expected_version: Optional[int] = None


# ---------------------------------------------------------------------------
# evacuation routing
# ---------------------------------------------------------------------------
class EvacRouteRequest(BaseModel):
    hazard_event_id: int = Field(..., ge=1)
    from_zone_id: Optional[int] = Field(None, ge=1)
    to_shelter_id: Optional[int] = Field(None, ge=1)


class EvacRouteOut(BaseModel):
    evacuation_route_id: Optional[int] = None
    hazard_event_id: Optional[int] = None
    from_zone_id: Optional[int] = None
    to_shelter_id: Optional[int] = None
    geojson: dict[str, Any] = Field(default_factory=dict)
    distance_km: Optional[float] = None
    est_minutes: Optional[float] = None
    road_graph_version: Optional[str] = None
    hazard_exclusion_version: Optional[str] = None
    status: str = "proposed"       # proposed | selected | no_route
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# response plans + tasks
# ---------------------------------------------------------------------------
class ResponsePlanCreate(BaseModel):
    hazard_event_id: Optional[int] = Field(None, ge=1)
    hazard_code: str
    title: str = Field(..., min_length=1, max_length=200)
    template_code: Optional[str] = None
    district_id: Optional[int] = Field(None, ge=1)


class ResponseTaskOut(BaseModel):
    response_task_id: int
    response_plan_id: int
    title: str
    sequence: int
    assigned_to_actor: Optional[str] = None
    status: str = "open"
    due_at: Optional[str] = None
    completed_at: Optional[str] = None


class ResponsePlanOut(BaseModel):
    response_plan_id: int
    hazard_event_id: Optional[int] = None
    hazard_code: str
    title: str
    template_code: Optional[str] = None
    status: str = "active"
    district_id: Optional[int] = None
    tasks: list[ResponseTaskOut] = Field(default_factory=list)


class TaskPatch(BaseModel):
    status: Optional[str] = None
    assigned_to_actor: Optional[str] = Field(None, max_length=120)
    due_at: Optional[str] = None
    expected_version: Optional[int] = None


# ---------------------------------------------------------------------------
# situation overview
# ---------------------------------------------------------------------------
class SituationOverviewOut(BaseModel):
    generated_at: str
    active_hazards: int = 0
    open_alerts: int = 0
    low_confidence_warnings: int = 0
    readiness: dict[str, Any] = Field(default_factory=dict)
    unavailable_resources: int = 0
    open_tasks: int = 0
    feed_freshness: list[FeedFreshnessOut] = Field(default_factory=list)
    stale_feeds: int = 0
    hazards: list[HazardEventOut] = Field(default_factory=list)


AllocationProposalOut.model_rebuild()
