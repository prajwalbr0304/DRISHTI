"""Typed request/response models for the CCTV monitoring API.

Field naming is snake_case at the API boundary (as elsewhere); the service maps
to the PascalCase Data Store columns. Enum values are validated against the
``cctv_schema`` tuples server-side, and every free-text field is length-capped so
a detection producer cannot push unbounded strings into the review queue.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..datastore import cctv_schema as cs

DETECTION_TYPES = cs.DETECTION_TYPES
DETECTION_SEVERITIES = cs.DETECTION_SEVERITIES
ALERT_STATUSES = cs.ALERT_STATUSES
DISPATCH_STATUSES = cs.DISPATCH_STATUSES
CAMERA_STATUSES = cs.CAMERA_STATUSES
STREAM_KINDS = cs.STREAM_KINDS


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
# cameras
# ---------------------------------------------------------------------------
class CameraCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    location_label: Optional[str] = Field(None, max_length=200)
    bearing_degrees: Optional[float] = Field(None, ge=0.0, le=360.0)
    fov_degrees: Optional[float] = Field(None, ge=1.0, le=360.0)
    district_id: Optional[int] = Field(None, ge=1)
    unit_id: Optional[int] = Field(None, ge=1)
    stream_kind: str = "none"
    stream_url: Optional[str] = Field(None, max_length=2000)
    poster_url: Optional[str] = Field(None, max_length=2000)
    status: str = "online"
    analytics_enabled: bool = True
    detector_profile: Optional[str] = Field(
        None, max_length=400,
        description="comma-separated detection types this camera is watched for")
    notes: Optional[str] = Field(None, max_length=2000)


class CameraPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    location_label: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = None
    stream_kind: Optional[str] = None
    stream_url: Optional[str] = Field(None, max_length=2000)
    poster_url: Optional[str] = Field(None, max_length=2000)
    analytics_enabled: Optional[bool] = None
    detector_profile: Optional[str] = Field(None, max_length=400)
    bearing_degrees: Optional[float] = Field(None, ge=0.0, le=360.0)
    fov_degrees: Optional[float] = Field(None, ge=1.0, le=360.0)
    notes: Optional[str] = Field(None, max_length=2000)
    expected_version: Optional[int] = None


class CameraOut(BaseModel):
    camera_id: int
    code: str
    name: str
    location_label: Optional[str] = None
    lon: float
    lat: float
    bearing_degrees: Optional[float] = None
    fov_degrees: Optional[float] = None
    district_id: Optional[int] = None
    unit_id: Optional[int] = None
    stream_kind: str = "none"
    stream_url: Optional[str] = None
    poster_url: Optional[str] = None
    status: str = "online"
    analytics_enabled: bool = True
    detector_profile: Optional[str] = None
    last_heartbeat_at: Optional[str] = None
    last_analysed_at: Optional[str] = None
    notes: Optional[str] = None
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # rolled-up review state so the wall can colour a marker without N+1 reads
    open_alert_count: int = 0
    top_open_severity: Optional[str] = None


# ---------------------------------------------------------------------------
# responders
# ---------------------------------------------------------------------------
class PatrolUnitCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    kind: str = "station"
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    unit_id: Optional[int] = Field(None, ge=1)
    district_id: Optional[int] = Field(None, ge=1)
    status: str = "available"
    contact_label: Optional[str] = Field(None, max_length=120)
    capabilities: list[str] = Field(default_factory=list)


class PatrolUnitOut(BaseModel):
    patrol_unit_id: int
    code: str
    name: str
    kind: str
    unit_id: Optional[int] = None
    district_id: Optional[int] = None
    lon: float
    lat: float
    status: str
    contact_label: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    version: int = 1


# ---------------------------------------------------------------------------
# detections
# ---------------------------------------------------------------------------
class BoundingBox(BaseModel):
    """Normalised to the frame ([0,1]) so the overlay is resolution-independent."""
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)
    label: Optional[str] = Field(None, max_length=40)
    score: Optional[float] = Field(None, ge=0.0, le=1.0)


class DetectionIngestItem(BaseModel):
    """One detection pushed by an external video-analytics service."""
    camera_code: Optional[str] = Field(None, max_length=64)
    camera_id: Optional[int] = Field(None, ge=1)
    detection_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    severity: Optional[str] = None
    detected_at: Optional[str] = Field(None, max_length=40, description="ISO-8601 UTC")
    window_seconds: Optional[float] = Field(None, gt=0.0, le=3600.0)
    object_count: Optional[int] = Field(None, ge=0, le=10_000)
    boxes: list[BoundingBox] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    frame_object_key: Optional[str] = Field(None, max_length=1024)
    clip_object_key: Optional[str] = Field(None, max_length=1024)
    source_record_id: Optional[str] = Field(
        None, max_length=200,
        description="producer-side idempotency key; derived when omitted")
    detector_label: Optional[str] = Field(None, max_length=120)


class DetectionIngestRequest(BaseModel):
    detections: list[DetectionIngestItem] = Field(..., min_length=1, max_length=200)


class DetectionOut(BaseModel):
    cctv_detection_id: int
    camera_id: int
    camera_name: Optional[str] = None
    detection_type: str
    detection_label: Optional[str] = None
    confidence: float
    severity: str
    object_count: Optional[int] = None
    boxes: list[dict[str, Any]] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    detector_kind: str
    detector_label: str
    frame_object_key: Optional[str] = None
    clip_object_key: Optional[str] = None
    detected_at: Optional[str] = None
    received_at: Optional[str] = None
    window_seconds: Optional[float] = None
    quality_flag: str = "valid"
    district_id: Optional[int] = None
    lon: Optional[float] = None
    lat: Optional[float] = None


class AnalyticsRunRequest(BaseModel):
    camera_ids: Optional[list[int]] = Field(
        None, max_length=500, description="omit to sweep every analytics-enabled camera")
    district_id: Optional[int] = Field(None, ge=1)


class AnalyticsRunResponse(BaseModel):
    cameras_analysed: int
    detections_created: int
    detections_suppressed: int = Field(
        0, description="idempotent duplicates inside the same analysis window")
    alerts_proposed: int
    below_alert_threshold: int = Field(
        0, description="recorded as detections but too weak to raise an alert")
    detector_kind: str
    detector_label: str
    alerts: list["AlertOut"] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# alerts
# ---------------------------------------------------------------------------
class AlertOut(BaseModel):
    cctv_alert_id: int
    cctv_detection_id: int
    camera_id: int
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    stream_kind: Optional[str] = None
    stream_url: Optional[str] = None
    poster_url: Optional[str] = None
    alert_type: str
    alert_label: Optional[str] = None
    severity: str
    title: str
    message: Optional[str] = None
    confidence: float
    status: str
    reviewed_by_actor: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    dismiss_reason: Optional[str] = None
    district_id: Optional[int] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    location_label: Optional[str] = None
    nearest_unit_id: Optional[int] = None
    detector_kind: Optional[str] = None
    detector_label: Optional[str] = None
    quality_flag: Optional[str] = None
    object_count: Optional[int] = None
    synthetic: bool = True
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    age_seconds: Optional[float] = None
    dispatch_count: int = 0
    active_dispatch_status: Optional[str] = None


class AlertConfirmRequest(BaseModel):
    confirm: bool = Field(False, description="fresh authenticated confirmation")
    note: Optional[str] = Field(None, max_length=2000)
    # Confirming is the analyst's judgement that the detection is real. Proposing
    # the nearest responder immediately afterwards is a convenience, NOT a
    # dispatch: the returned proposal still needs its own confirmation.
    propose_dispatch: bool = True
    max_distance_km: Optional[float] = Field(None, gt=0.0, le=200.0)


class AlertDismissRequest(BaseModel):
    reason: str = Field(..., description="one of the closed dismissal reasons")
    note: Optional[str] = Field(None, max_length=2000)


class AlertDetail(BaseModel):
    alert: AlertOut
    detection: Optional[DetectionOut] = None
    camera: Optional[CameraOut] = None
    dispatches: list["DispatchOut"] = Field(default_factory=list)
    activity: list[dict[str, Any]] = Field(default_factory=list)
    nearby_cameras: list[CameraOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
class DispatchProposeRequest(BaseModel):
    max_distance_km: Optional[float] = Field(None, gt=0.0, le=200.0)
    patrol_unit_id: Optional[int] = Field(
        None, ge=1, description="override the ranked pick with a specific responder")


class DispatchTransitionRequest(BaseModel):
    confirm: bool = Field(False, description="fresh authenticated confirmation")
    expected_version: Optional[int] = None
    notes: Optional[str] = Field(None, max_length=2000)


class DispatchOut(BaseModel):
    cctv_dispatch_id: int
    cctv_alert_id: int
    patrol_unit_id: Optional[int] = None
    unit_id: Optional[int] = None
    unit_name: str
    unit_kind: Optional[str] = None
    distance_km: float
    eta_minutes: Optional[float] = None
    score: Optional[float] = None
    reason: dict[str, Any] = Field(default_factory=dict)
    status: str
    proposed_by_actor: Optional[str] = None
    approved_by_actor: Optional[str] = None
    district_id: Optional[int] = None
    proposed_at: Optional[str] = None
    dispatched_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    enroute_at: Optional[str] = None
    onsite_at: Optional[str] = None
    closed_at: Optional[str] = None
    notes: Optional[str] = None
    version: int = 1


class DispatchProposal(BaseModel):
    cctv_alert_id: int
    dispatch: Optional[DispatchOut] = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    geometry_source: str
    considered: int = 0
    max_distance_km: float
    eta_assumptions_version: str
    fallback_reason: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------
class CameraHealth(BaseModel):
    total: int = 0
    online: int = 0
    degraded: int = 0
    offline: int = 0
    maintenance: int = 0
    analytics_enabled: int = 0


class WallOverview(BaseModel):
    cameras: CameraHealth
    pending_review: int = 0
    confirmed_awaiting_dispatch: int = 0
    dispatched_active: int = 0
    dismissed_today: int = 0
    low_confidence_pending: int = 0
    alerts_last_hour: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    capability: dict[str, Any] = Field(default_factory=dict)
    district_id: Optional[int] = None


# Forward refs used above.
AnalyticsRunResponse.model_rebuild()
AlertDetail.model_rebuild()
