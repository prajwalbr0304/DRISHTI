"""CCTV monitoring service.

Business logic over the Data Store CCTV repo. Mirrors ``app/disaster/service.py``:
explicit error classes mapped to HTTP in the router; every mutating operation
writes the domain record then an APPEND-ONLY ``CctvActivity`` row, and publishes a
data-minimised Signal AFTER the write. Idempotency keys give safe retries.

Safety enforced HERE, never in the detector alone:

  * a detection never becomes an active alert — it can only PROPOSE one, and a
    detection below ``cctv_min_alert_confidence`` raises nothing at all;
  * a proposed alert needs a fresh human confirmation to become ``confirmed``;
  * confirming an alert may PROPOSE the nearest responder but never dispatches —
    ``dispatch`` is a second, separately-confirmed transition;
  * a dismissal is a first-class recorded outcome with a reason, because the
    false-positive trail is the only honest way to judge the detector;
  * an alert/dispatch is only actionable inside the operator's assigned district;
  * ``CctvDetection`` is append-only, so a detection can never be rewritten after
    review to agree with the decision that was made about it.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..cache import SEG_IDEMPOTENCY
from ..config import get_settings
from ..datastore import cctv_schema as cs
from ..disaster.geometry import haversine_km
from ..signals import (EVENT_CCTV_ALERT_REVIEWED, EVENT_CCTV_ALERT_REVIEW_REQUIRED,
                       EVENT_CCTV_DISPATCH_CONFIRMED, get_signals)
from . import detectors, dispatch as dispatch_mod
from .guards import DISMISS_REASONS, CctvScope, enforce_district_scope
from .repo import CctvRepo, cctv_cache, cctv_repo


# ---------------------------------------------------------------------------
# errors (mapped to HTTP in the router)
# ---------------------------------------------------------------------------
class CctvError(Exception):
    pass


class CctvNotFound(CctvError):
    pass


class CctvForbidden(CctvError):
    pass


class CctvValidation(CctvError):
    pass


class CctvConflict(CctvError):
    pass


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    """Data Store datetime format ('yyyy-MM-dd HH:mm:ss', naive UTC)."""
    return _now_dt().strftime("%Y-%m-%d %H:%M:%S")


def _repo() -> CctvRepo:
    return cctv_repo()


def _publish(event: str, payload: dict) -> None:
    try:
        get_signals().publish(event, payload)
    except Exception:  # noqa: BLE001 — a signal failure must never break a write
        pass


def _idempotent(idem_key: Optional[str], produce: Callable[[], dict]) -> dict:
    if not idem_key:
        return produce()
    cache = cctv_cache()
    seen = cache.get(SEG_IDEMPOTENCY, f"cctv:{idem_key}")
    if seen:
        try:
            out = json.loads(seen)
            out["idempotent_replay"] = True
            return out
        except Exception:  # noqa: BLE001
            pass
    out = produce()
    try:
        cache.put(SEG_IDEMPOTENCY, f"cctv:{idem_key}", json.dumps(out, default=str))
    except Exception:  # noqa: BLE001
        pass
    return out


def _check_version(row: dict, expected: Optional[int], label: str) -> None:
    if expected is None:
        return
    if int(row.get("Version") or 0) != int(expected):
        raise CctvConflict(
            f"Version conflict: {label} is at v{row.get('Version')}, you acted on "
            f"v{expected}. Reload and retry.")


def _f(v):
    return float(v) if v is not None else None


def _i(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_dt(v) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if not v:
        return None
    raw = str(v).strip().replace("Z", "+00:00")
    for attempt in (raw, raw.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(attempt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _json_field(v) -> Any:
    """Data Store JSON columns round-trip as strings; decode defensively."""
    if v is None or isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return None
    return None


def _guard_json_size(value: Any, field: str) -> Any:
    if value is None:
        return None
    try:
        raw = json.dumps(value, default=str)
    except (TypeError, ValueError) as exc:
        raise CctvValidation(f"{field} is not JSON-serialisable ({exc})")
    if len(raw.encode("utf-8")) > cs.MAX_JSON_BYTES:
        raise CctvValidation(
            f"{field} exceeds the {cs.MAX_JSON_BYTES}-byte limit for this field.")
    return value


def _clip(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    t = str(text).strip()
    return t[:limit] if t else None


# ---------------------------------------------------------------------------
# serialisers (PascalCase DS columns -> snake_case API)
# ---------------------------------------------------------------------------
def _camera_out(r: dict, *, open_alerts: int = 0,
                top_severity: Optional[str] = None) -> dict:
    return {
        "camera_id": int(r["CameraID"]), "code": r.get("Code"), "name": r.get("Name"),
        "location_label": r.get("LocationLabel"),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")),
        "bearing_degrees": _f(r.get("BearingDegrees")),
        "fov_degrees": _f(r.get("FovDegrees")),
        "district_id": _i(r.get("DistrictID")), "unit_id": _i(r.get("UnitID")),
        "stream_kind": r.get("StreamKind") or "none", "stream_url": r.get("StreamURL"),
        "poster_url": r.get("PosterURL"), "status": r.get("Status") or "online",
        "analytics_enabled": bool(r.get("AnalyticsEnabled")),
        "detector_profile": r.get("DetectorProfile"),
        "last_heartbeat_at": r.get("LastHeartbeatAt"),
        "last_analysed_at": r.get("LastAnalysedAt"),
        "notes": r.get("Notes"), "version": int(r.get("Version") or 1),
        "created_at": r.get("CreatedAt"), "updated_at": r.get("UpdatedAt"),
        "open_alert_count": open_alerts, "top_open_severity": top_severity,
    }


def _patrol_out(r: dict) -> dict:
    caps = _json_field(r.get("Capabilities")) or []
    return {
        "patrol_unit_id": int(r["PatrolUnitID"]), "code": r.get("Code"),
        "name": r.get("Name"), "kind": r.get("Kind") or "station",
        "unit_id": _i(r.get("UnitID")), "district_id": _i(r.get("DistrictID")),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")),
        "status": r.get("Status") or "available",
        "contact_label": r.get("ContactLabel"),
        "capabilities": caps if isinstance(caps, list) else [],
        "version": int(r.get("Version") or 1),
    }


def _detection_out(r: dict, *, camera_name: Optional[str] = None) -> dict:
    return {
        "cctv_detection_id": int(r["CctvDetectionID"]), "camera_id": int(r["CameraID"]),
        "camera_name": camera_name,
        "detection_type": r.get("DetectionType"),
        "detection_label": cs.detection_label(r.get("DetectionType") or ""),
        "confidence": _f(r.get("Confidence")) or 0.0,
        "severity": r.get("Severity") or "moderate",
        "object_count": _i(r.get("ObjectCount")),
        "boxes": _json_field(r.get("BBoxJSON")) or [],
        "attributes": _json_field(r.get("Attributes")) or {},
        "detector_kind": r.get("DetectorKind") or "synthetic_replay",
        "detector_label": r.get("DetectorLabel") or "",
        "frame_object_key": r.get("FrameObjectKey"),
        "clip_object_key": r.get("ClipObjectKey"),
        "detected_at": r.get("DetectedAt"), "received_at": r.get("ReceivedAt"),
        "window_seconds": _f(r.get("WindowSeconds")),
        "quality_flag": r.get("QualityFlag") or "valid",
        "district_id": _i(r.get("DistrictID")),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")),
    }


def _alert_out(r: dict, *, camera: Optional[dict] = None,
               detection: Optional[dict] = None,
               dispatches: Optional[list[dict]] = None,
               now: Optional[datetime] = None) -> dict:
    payload = _json_field(r.get("Payload")) or {}
    created = _parse_dt(r.get("CreatedAt"))
    ref = now or _now_dt()
    age = round((ref - created).total_seconds(), 1) if created else None
    disp = dispatches or []
    active = next((d for d in disp
                   if d.get("Status") in ("proposed", "dispatched", "acknowledged",
                                          "enroute", "onsite")), None)
    return {
        "cctv_alert_id": int(r["CctvAlertID"]),
        "cctv_detection_id": int(r["CctvDetectionID"]),
        "camera_id": int(r["CameraID"]),
        "camera_code": (camera or {}).get("Code"),
        "camera_name": (camera or {}).get("Name"),
        "stream_kind": (camera or {}).get("StreamKind"),
        "stream_url": (camera or {}).get("StreamURL"),
        "poster_url": (camera or {}).get("PosterURL"),
        "alert_type": r.get("AlertType"),
        "alert_label": cs.detection_label(r.get("AlertType") or ""),
        "severity": r.get("Severity") or "moderate",
        "title": r.get("Title") or "", "message": r.get("Message"),
        "confidence": _f(r.get("Confidence")) or 0.0,
        "status": r.get("Status") or "proposed",
        "reviewed_by_actor": r.get("ReviewedByActor"),
        "reviewed_at": r.get("ReviewedAt"), "review_note": r.get("ReviewNote"),
        "dismiss_reason": r.get("DismissReason"),
        "district_id": _i(r.get("DistrictID")),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")),
        "location_label": r.get("LocationLabel"),
        "nearest_unit_id": _i(r.get("NearestUnitID")),
        "detector_kind": payload.get("detector_kind") or (detection or {}).get("DetectorKind"),
        "detector_label": payload.get("detector_label") or (detection or {}).get("DetectorLabel"),
        "quality_flag": payload.get("quality_flag") or (detection or {}).get("QualityFlag"),
        "object_count": _i(payload.get("object_count")
                           if payload.get("object_count") is not None
                           else (detection or {}).get("ObjectCount")),
        "synthetic": bool(payload.get("synthetic", True)),
        "version": int(r.get("Version") or 1),
        "created_at": r.get("CreatedAt"), "updated_at": r.get("UpdatedAt"),
        "age_seconds": age,
        "dispatch_count": len(disp),
        "active_dispatch_status": (active or {}).get("Status"),
    }


def _dispatch_out(r: dict) -> dict:
    return {
        "cctv_dispatch_id": int(r["CctvDispatchID"]),
        "cctv_alert_id": int(r["CctvAlertID"]),
        "patrol_unit_id": _i(r.get("PatrolUnitID")), "unit_id": _i(r.get("UnitID")),
        "unit_name": r.get("UnitName") or "", "unit_kind": r.get("UnitKind"),
        "distance_km": _f(r.get("DistanceKm")) or 0.0,
        "eta_minutes": _f(r.get("EtaMinutes")), "score": _f(r.get("Score")),
        "reason": _json_field(r.get("Reason")) or {},
        "status": r.get("Status") or "proposed",
        "proposed_by_actor": r.get("ProposedByActor"),
        "approved_by_actor": r.get("ApprovedByActor"),
        "district_id": _i(r.get("DistrictID")),
        "proposed_at": r.get("ProposedAt"), "dispatched_at": r.get("DispatchedAt"),
        "acknowledged_at": r.get("AcknowledgedAt"), "enroute_at": r.get("EnrouteAt"),
        "onsite_at": r.get("OnsiteAt"), "closed_at": r.get("ClosedAt"),
        "notes": r.get("Notes"), "version": int(r.get("Version") or 1),
    }


def _activity_out(r: dict) -> dict:
    return {
        "cctv_activity_id": int(r["CctvActivityID"]),
        "subject_type": r.get("SubjectType"), "subject_id": r.get("SubjectID"),
        "actor": r.get("Actor"), "action": r.get("Action"),
        "diff": _json_field(r.get("DiffJSON")) or {},
        "created_at": r.get("CreatedAt"),
    }


# ---------------------------------------------------------------------------
# capability
# ---------------------------------------------------------------------------
def capability() -> dict:
    return detectors.capability_report()


def detection_types() -> list[dict]:
    return [{"code": t, "label": cs.detection_label(t),
             "default_severity": cs.default_severity(t)} for t in cs.DETECTION_TYPES]


def dismiss_reasons() -> list[str]:
    return list(DISMISS_REASONS)


# ---------------------------------------------------------------------------
# cameras
# ---------------------------------------------------------------------------
def _open_alert_rollup(repo: CctvRepo) -> dict[int, tuple[int, Optional[str]]]:
    """camera_id -> (open alert count, worst severity) in one pass."""
    order = list(cs.DETECTION_SEVERITIES)
    out: dict[int, tuple[int, Optional[str]]] = {}
    for a in repo.list("CctvAlert"):
        if a.get("Status") not in ("proposed", "confirmed", "dispatched"):
            continue
        cid = _i(a.get("CameraID"))
        if cid is None:
            continue
        count, worst = out.get(cid, (0, None))
        sev = a.get("Severity") or "moderate"
        if worst is None or (sev in order and order.index(sev) > order.index(worst)):
            worst = sev
        out[cid] = (count + 1, worst)
    return out


def list_cameras(*, district_id: Optional[int] = None, status: Optional[str] = None,
                 with_alerts_only: bool = False) -> list[dict]:
    repo = _repo()
    rollup = _open_alert_rollup(repo)
    out = []
    for r in repo.list("Camera"):
        if district_id is not None and _i(r.get("DistrictID")) != int(district_id):
            continue
        if status and r.get("Status") != status:
            continue
        count, worst = rollup.get(int(r["CameraID"]), (0, None))
        if with_alerts_only and count == 0:
            continue
        out.append(_camera_out(r, open_alerts=count, top_severity=worst))
    return out


def get_camera(camera_id: int) -> dict:
    repo = _repo()
    r = repo.get("Camera", camera_id)
    if not r or r.get("DeletedAt"):
        raise CctvNotFound(f"Camera {camera_id} not found")
    count, worst = _open_alert_rollup(repo).get(int(camera_id), (0, None))
    return _camera_out(r, open_alerts=count, top_severity=worst)


def _validate_camera_payload(payload: dict) -> None:
    if payload.get("stream_kind") not in cs.STREAM_KINDS:
        raise CctvValidation(
            f"invalid stream_kind {payload.get('stream_kind')!r}; "
            f"expected one of {cs.STREAM_KINDS}")
    if payload.get("status") not in cs.CAMERA_STATUSES:
        raise CctvValidation(
            f"invalid status {payload.get('status')!r}; expected one of {cs.CAMERA_STATUSES}")
    kind = payload.get("stream_kind")
    if kind and kind != "none" and not (payload.get("stream_url") or "").strip():
        raise CctvValidation(
            f"stream_kind {kind!r} requires a stream_url (use 'none' for a camera "
            "registered without imagery).")
    profile = (payload.get("detector_profile") or "").strip()
    if profile:
        unknown = {p.strip() for p in profile.split(",") if p.strip()} - set(cs.DETECTION_TYPES)
        if unknown:
            raise CctvValidation(
                f"detector_profile contains unknown detection types: {sorted(unknown)}")


def create_camera(payload: dict, scope: CctvScope) -> dict:
    repo = _repo()
    _validate_camera_payload(payload)
    enforce_district_scope(scope, payload.get("district_id"), "register camera")
    if repo.find_one("Camera", {"Code": payload["code"]}):
        raise CctvConflict(f"A camera with code {payload['code']!r} already exists.")
    row = repo.create("Camera", {
        "Code": payload["code"], "Name": payload["name"],
        "LocationLabel": _clip(payload.get("location_label"), 200),
        "Lon": float(payload["lon"]), "Lat": float(payload["lat"]),
        "BearingDegrees": payload.get("bearing_degrees"),
        "FovDegrees": payload.get("fov_degrees"),
        "DistrictID": payload.get("district_id"), "UnitID": payload.get("unit_id"),
        "StreamKind": payload.get("stream_kind") or "none",
        "StreamURL": payload.get("stream_url"), "PosterURL": payload.get("poster_url"),
        "Status": payload.get("status") or "online",
        "AnalyticsEnabled": bool(payload.get("analytics_enabled", True)),
        "DetectorProfile": _clip(payload.get("detector_profile"), 400),
        "LastHeartbeatAt": _now(), "Notes": _clip(payload.get("notes"), cs.MAX_NOTES_LEN),
    })
    repo.append_activity("camera", row["CameraID"], actor=scope.actor,
                         action="camera.registered",
                         diff={"code": payload["code"], "status": row["Status"]})
    return {"ok": True, "id": int(row["CameraID"]), "kind": "camera",
            "status": row["Status"], "version": int(row.get("Version") or 1)}


def patch_camera(camera_id: int, payload: dict, scope: CctvScope) -> dict:
    repo = _repo()
    row = repo.get("Camera", camera_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"Camera {camera_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "update camera")
    _check_version(row, payload.get("expected_version"), "camera")
    merged_kind = payload.get("stream_kind") or row.get("StreamKind")
    merged_url = payload.get("stream_url") if "stream_url" in payload else row.get("StreamURL")
    _validate_camera_payload({
        "stream_kind": merged_kind,
        "status": payload.get("status") or row.get("Status"),
        "stream_url": merged_url,
        "detector_profile": (payload.get("detector_profile")
                             if payload.get("detector_profile") is not None
                             else row.get("DetectorProfile")),
    })
    field_map = {
        "name": "Name", "location_label": "LocationLabel", "status": "Status",
        "stream_kind": "StreamKind", "stream_url": "StreamURL",
        "poster_url": "PosterURL", "analytics_enabled": "AnalyticsEnabled",
        "detector_profile": "DetectorProfile", "bearing_degrees": "BearingDegrees",
        "fov_degrees": "FovDegrees", "notes": "Notes",
    }
    patch: dict = {}
    for api_key, col in field_map.items():
        if payload.get(api_key) is not None:
            patch[col] = payload[api_key]
    if not patch:
        raise CctvValidation("no updatable fields supplied")
    patch["Version"] = int(row.get("Version") or 1) + 1
    repo.update("Camera", camera_id, patch)
    repo.append_activity("camera", camera_id, actor=scope.actor, action="camera.updated",
                         diff={k: v for k, v in patch.items() if k != "Version"})
    return {"ok": True, "id": int(camera_id), "kind": "camera",
            "status": patch.get("Status") or row.get("Status"),
            "version": patch["Version"]}


def retire_camera(camera_id: int, scope: CctvScope) -> dict:
    repo = _repo()
    row = repo.get("Camera", camera_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"Camera {camera_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "retire camera")
    repo.soft_delete("Camera", camera_id)
    repo.append_activity("camera", camera_id, actor=scope.actor, action="camera.retired",
                         diff={"code": row.get("Code")})
    return {"ok": True, "id": int(camera_id), "kind": "camera", "status": "retired"}


# ---------------------------------------------------------------------------
# responders
# ---------------------------------------------------------------------------
def list_patrol_units(*, district_id: Optional[int] = None,
                      status: Optional[str] = None) -> list[dict]:
    repo = _repo()
    out = []
    for r in repo.list("PatrolUnit"):
        if district_id is not None and _i(r.get("DistrictID")) != int(district_id):
            continue
        if status and r.get("Status") != status:
            continue
        out.append(_patrol_out(r))
    return out


def create_patrol_unit(payload: dict, scope: CctvScope) -> dict:
    repo = _repo()
    if payload.get("kind") not in cs.PATROL_UNIT_KINDS:
        raise CctvValidation(f"invalid kind {payload.get('kind')!r}; "
                             f"expected one of {cs.PATROL_UNIT_KINDS}")
    if payload.get("status") not in cs.PATROL_UNIT_STATUSES:
        raise CctvValidation(f"invalid status {payload.get('status')!r}; "
                             f"expected one of {cs.PATROL_UNIT_STATUSES}")
    enforce_district_scope(scope, payload.get("district_id"), "register responder")
    if repo.find_one("PatrolUnit", {"Code": payload["code"]}):
        raise CctvConflict(f"A responder with code {payload['code']!r} already exists.")
    row = repo.create("PatrolUnit", {
        "Code": payload["code"], "Name": payload["name"], "Kind": payload["kind"],
        "UnitID": payload.get("unit_id"), "DistrictID": payload.get("district_id"),
        "Lon": float(payload["lon"]), "Lat": float(payload["lat"]),
        "Status": payload.get("status") or "available",
        "ContactLabel": _clip(payload.get("contact_label"), 120),
        "Capabilities": _guard_json_size(payload.get("capabilities") or [], "capabilities"),
        "LastUpdatedAt": _now(),
    })
    repo.append_activity("patrol_unit", row["PatrolUnitID"], actor=scope.actor,
                         action="patrol_unit.registered",
                         diff={"code": payload["code"], "kind": payload["kind"]})
    return {"ok": True, "id": int(row["PatrolUnitID"]), "kind": "patrol_unit",
            "status": row["Status"], "version": int(row.get("Version") or 1)}


# ---------------------------------------------------------------------------
# detections + alert proposal
# ---------------------------------------------------------------------------
def _alert_title(detection_type: str, object_count: Optional[int]) -> str:
    """'Fight (5 people)' / 'Traffic block (14 vehicles)'.

    The count is only included when the detector actually counted, so a title
    never implies a precision the detection does not have.
    """
    label = cs.detection_label(detection_type)
    if not object_count or object_count <= 0:
        return label
    noun_map = {
        "traffic_block": "vehicles", "vehicle_accident": "vehicles",
        "abandoned_object": "objects", "fire_smoke": "sources",
    }
    noun = noun_map.get(detection_type, "people")
    if object_count == 1:
        noun = {"vehicles": "vehicle", "objects": "object",
                "sources": "source", "people": "person"}[noun]
    return f"{label} ({object_count} {noun})"


def _alert_message(camera: dict, candidate_attrs: dict) -> str:
    where = camera.get("LocationLabel") or camera.get("Name") or "monitored camera"
    return f"Detected on {camera.get('Name')} — near {where}."


def _persist_detection(repo: CctvRepo, camera: dict,
                       cand: detectors.DetectionCandidate) -> tuple[Optional[dict], bool]:
    """Append one detection row. Returns (row, created).

    Idempotent on ``SourceRecordID``: re-running the same analysis window, or a
    producer retrying a POST, updates nothing and creates nothing. The table is
    append-only, so suppression is the only correct behaviour for a duplicate.
    """
    existing = repo.find_one("CctvDetection", {"SourceRecordID": cand.source_record_id})
    if existing:
        return existing, False
    boxes = _guard_json_size(cand.boxes[: get_settings().cctv_max_boxes], "boxes")
    row = repo.create("CctvDetection", {
        "CameraID": int(camera["CameraID"]),
        "DetectionType": cand.detection_type,
        "Confidence": round(float(cand.confidence), 4),
        "Severity": cand.severity,
        "ObjectCount": cand.object_count,
        "BBoxJSON": boxes,
        "Attributes": _guard_json_size(cand.attributes, "attributes"),
        "DetectorKind": cand.detector_kind,
        "DetectorLabel": cand.detector_label,
        "FrameObjectKey": cand.frame_object_key,
        "ClipObjectKey": cand.clip_object_key,
        "DetectedAt": cand.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
        "ReceivedAt": _now(),
        "WindowSeconds": cand.window_seconds,
        "QualityFlag": cand.quality_flag(),
        "SourceRecordID": cand.source_record_id,
        "DistrictID": camera.get("DistrictID"),
        "Lon": camera.get("Lon"), "Lat": camera.get("Lat"),
    })
    return row, True


def _propose_alert_for(repo: CctvRepo, camera: dict, detection: dict,
                       *, actor: str) -> Optional[dict]:
    """Raise a REVIEWABLE alert (status 'proposed') for a detection.

    Returns ``None`` when the detection is too weak to be worth a human's time, or
    when this detection already has an alert (the unique index on
    ``CctvDetectionID`` is the contract; this is the guard in front of it).
    """
    s = get_settings()
    conf = float(detection.get("Confidence") or 0.0)
    if conf < s.cctv_min_alert_confidence:
        return None
    if repo.find_one("CctvAlert", {"CctvDetectionID": int(detection["CctvDetectionID"])}):
        return None

    dtype = detection.get("DetectionType")
    # De-duplicate an ONGOING incident. A fight that lasts three minutes is six
    # analysis windows, and raising a fresh reviewable alert for each one would
    # bury the queue in copies of the same event and make the pending count
    # meaningless. While a camera still has an UNREVIEWED alert of this class,
    # further detections are recorded (append-only, so the evidence of duration
    # survives) but do not re-raise. Once a human has confirmed or dismissed it,
    # the next detection is a genuinely new event and does raise.
    for open_alert in repo.list("CctvAlert", where={"CameraID": int(camera["CameraID"])}):
        if open_alert.get("Status") == "proposed" and open_alert.get("AlertType") == dtype:
            return None

    count = _i(detection.get("ObjectCount"))
    row = repo.create("CctvAlert", {
        "CctvDetectionID": int(detection["CctvDetectionID"]),
        "CameraID": int(camera["CameraID"]),
        "AlertType": dtype,
        "Severity": detection.get("Severity") or cs.default_severity(dtype or ""),
        "Title": _alert_title(dtype or "", count),
        "Message": _alert_message(camera, _json_field(detection.get("Attributes")) or {}),
        "Confidence": round(conf, 4),
        "Status": "proposed",
        "DistrictID": camera.get("DistrictID"),
        "Lon": camera.get("Lon"), "Lat": camera.get("Lat"),
        "LocationLabel": camera.get("LocationLabel"),
        "NearestUnitID": camera.get("UnitID"),
        # Data-minimised card context. Carries provenance + quality so the review
        # card can show WHO produced this and how much to trust it.
        "Payload": {
            "detector_kind": detection.get("DetectorKind"),
            "detector_label": detection.get("DetectorLabel"),
            "quality_flag": detection.get("QualityFlag"),
            "object_count": count,
            "synthetic": detection.get("DetectorKind") == "synthetic_replay",
            "proposed_by": actor,
        },
    })
    repo.append_activity("alert", row["CctvAlertID"], actor=actor,
                         action="alert.proposed",
                         diff={"alert_type": dtype, "confidence": round(conf, 4),
                               "camera_id": int(camera["CameraID"]),
                               "quality": detection.get("QualityFlag")})
    _publish(EVENT_CCTV_ALERT_REVIEW_REQUIRED, {
        "cctv_alert_id": int(row["CctvAlertID"]),
        "camera_id": int(camera["CameraID"]),
        "alert_type": dtype,
        "severity": row.get("Severity"),
        "confidence": round(conf, 4),
        "district_id": _i(camera.get("DistrictID")),
    })
    return row


def run_analytics(payload: dict, scope: CctvScope, *,
                  now: Optional[datetime] = None,
                  idem_key: Optional[str] = None) -> dict:
    """Run one analytics pass and PROPOSE alerts for anything found.

    Never confirms, never dispatches. Re-running inside the same analysis window
    is a no-op thanks to the per-window idempotency key on each detection.
    """
    repo = _repo()
    s = get_settings()
    detector = detectors.get_detector()
    ref = now or _now_dt()

    wanted_ids = set(payload.get("camera_ids") or [])
    district_id = payload.get("district_id")
    cameras = []
    for c in repo.list("Camera"):
        if wanted_ids and int(c["CameraID"]) not in wanted_ids:
            continue
        if district_id is not None and _i(c.get("DistrictID")) != int(district_id):
            continue
        if not c.get("AnalyticsEnabled"):
            continue
        cameras.append(c)

    def produce() -> dict:
        created = suppressed = proposed = below = 0
        alerts: list[dict] = []
        for cam in cameras:
            enforce_district_scope(scope, cam.get("DistrictID"), "run cctv analytics")
            try:
                candidates = detector.analyse(cam, now=ref,
                                              window_seconds=detectors.ANALYSIS_WINDOW_SECONDS)
            except Exception:  # noqa: BLE001 — one bad camera must not fail the sweep
                candidates = []
            for cand in candidates:
                det, was_created = _persist_detection(repo, cam, cand)
                if det is None:
                    continue
                if not was_created:
                    suppressed += 1
                    continue
                created += 1
                if float(det.get("Confidence") or 0.0) < s.cctv_min_alert_confidence:
                    below += 1
                    continue
                if proposed >= s.cctv_max_alerts_per_run:
                    continue
                alert = _propose_alert_for(repo, cam, det, actor=scope.actor)
                if alert is not None:
                    proposed += 1
                    dispatches = repo.list("CctvDispatch",
                                           where={"CctvAlertID": int(alert["CctvAlertID"])})
                    alerts.append(_alert_out(alert, camera=cam, detection=det,
                                             dispatches=dispatches, now=ref))
            try:
                repo.update("Camera", int(cam["CameraID"]), {"LastAnalysedAt": _now()})
            except Exception:  # noqa: BLE001 — bookkeeping only
                pass

        note = ("Detections are proposals only. Every alert needs a human "
                "confirmation before it is actionable, and dispatch is a separate "
                "confirmed step.")
        if detector.kind == "synthetic_replay":
            note = ("Synthetic scene replay — these detections are generated by a "
                    "deterministic in-repo generator, not by video frame inference. "
                    + note)
        elif not s.cctv_ingest_configured():
            note = ("External analytics selected but CCTV_INGEST_TOKEN is unset, so "
                    "no detection source is active. " + note)
        return {
            "cameras_analysed": len(cameras), "detections_created": created,
            "detections_suppressed": suppressed, "alerts_proposed": proposed,
            "below_alert_threshold": below,
            "detector_kind": detector.kind, "detector_label": detector.label,
            "alerts": alerts, "note": note,
        }

    return _idempotent(idem_key, produce)


def ingest_detections(payload: dict, *, actor: str = "external.analytics") -> dict:
    """Accept detections pushed by an external video-analytics service.

    Authenticated by the shared-secret header at the router. Idempotent on
    ``source_record_id`` so a producer may retry safely. Each accepted detection
    goes through the SAME alert-proposal path as the internal detector — an
    external producer cannot create a confirmed alert or a dispatch.
    """
    repo = _repo()
    s = get_settings()
    items = payload.get("detections") or []
    accepted = duplicate = rejected = proposed = below = 0
    errors: list[dict] = []
    alerts: list[dict] = []

    for idx, item in enumerate(items):
        dtype = item.get("detection_type")
        if dtype not in cs.DETECTION_TYPES:
            rejected += 1
            errors.append({"index": idx, "error": f"unknown detection_type {dtype!r}"})
            continue
        cam = None
        if item.get("camera_id") is not None:
            cam = repo.get("Camera", int(item["camera_id"]))
        elif item.get("camera_code"):
            cam = repo.find_one("Camera", {"Code": str(item["camera_code"])})
        if not cam or cam.get("DeletedAt"):
            rejected += 1
            errors.append({"index": idx, "error": "camera not found"})
            continue
        severity = item.get("severity") or cs.default_severity(dtype)
        if severity not in cs.DETECTION_SEVERITIES:
            rejected += 1
            errors.append({"index": idx, "error": f"invalid severity {severity!r}"})
            continue
        detected_at = _parse_dt(item.get("detected_at")) or _now_dt()
        window = float(item.get("window_seconds") or detectors.ANALYSIS_WINDOW_SECONDS)
        srid = _clip(item.get("source_record_id"), 200) or (
            f"{cam.get('Code')}:{dtype}:{detectors.window_index(detected_at, int(window) or 30)}")
        cand = detectors.DetectionCandidate(
            camera_id=int(cam["CameraID"]), detection_type=dtype,
            confidence=float(item.get("confidence") or 0.0), severity=severity,
            detected_at=detected_at, window_seconds=window,
            object_count=item.get("object_count"),
            boxes=[b if isinstance(b, dict) else b.model_dump()
                   for b in (item.get("boxes") or [])],
            attributes={**(item.get("attributes") or {}), "synthetic": False},
            frame_object_key=_clip(item.get("frame_object_key"), 1024),
            clip_object_key=_clip(item.get("clip_object_key"), 1024),
            source_record_id=srid,
            detector_kind="external_analytics",
            detector_label=_clip(item.get("detector_label"), 120)
            or detectors.EXTERNAL_DETECTOR_LABEL,
        )
        try:
            det, was_created = _persist_detection(repo, cam, cand)
        except CctvValidation as exc:
            rejected += 1
            errors.append({"index": idx, "error": str(exc)})
            continue
        if not was_created:
            duplicate += 1
            continue
        accepted += 1
        if float(det.get("Confidence") or 0.0) < s.cctv_min_alert_confidence:
            below += 1
            continue
        alert = _propose_alert_for(repo, cam, det, actor=actor)
        if alert is not None:
            proposed += 1
            alerts.append(_alert_out(alert, camera=cam, detection=det, dispatches=[]))

    return {"accepted": accepted, "duplicate_suppressed": duplicate,
            "rejected": rejected, "alerts_proposed": proposed,
            "below_alert_threshold": below, "errors": errors[:20], "alerts": alerts}


def list_detections(*, camera_id: Optional[int] = None,
                    detection_type: Optional[str] = None,
                    district_id: Optional[int] = None,
                    limit: int = 100) -> list[dict]:
    repo = _repo()
    names = {int(c["CameraID"]): c.get("Name") for c in repo.list("Camera")}
    rows = repo.list("CctvDetection")
    out = []
    for r in rows:
        if camera_id is not None and _i(r.get("CameraID")) != int(camera_id):
            continue
        if detection_type and r.get("DetectionType") != detection_type:
            continue
        if district_id is not None and _i(r.get("DistrictID")) != int(district_id):
            continue
        out.append(_detection_out(r, camera_name=names.get(int(r["CameraID"]))))
    out.sort(key=lambda d: d["cctv_detection_id"], reverse=True)
    return out[: max(1, min(limit, 1000))]


# ---------------------------------------------------------------------------
# alert review
# ---------------------------------------------------------------------------
_SEV_ORDER = {s: i for i, s in enumerate(cs.DETECTION_SEVERITIES)}


def list_alerts(*, status: Optional[str] = None, district_id: Optional[int] = None,
                camera_id: Optional[int] = None, detection_type: Optional[str] = None,
                min_confidence: Optional[float] = None,
                limit: int = 200) -> list[dict]:
    """The review queue. Ordered worst-and-newest first, which is the order an
    analyst actually wants to work: severity, then confidence, then recency."""
    repo = _repo()
    cameras = {int(c["CameraID"]): c for c in repo.list("Camera")}
    detections = {int(d["CctvDetectionID"]): d for d in repo.list("CctvDetection")}
    dispatch_by_alert: dict[int, list[dict]] = {}
    for d in repo.list("CctvDispatch"):
        dispatch_by_alert.setdefault(int(d["CctvAlertID"]), []).append(d)

    ref = _now_dt()
    out = []
    for r in repo.list("CctvAlert"):
        if status and r.get("Status") != status:
            continue
        if district_id is not None and _i(r.get("DistrictID")) != int(district_id):
            continue
        if camera_id is not None and _i(r.get("CameraID")) != int(camera_id):
            continue
        if detection_type and r.get("AlertType") != detection_type:
            continue
        if min_confidence is not None and float(r.get("Confidence") or 0.0) < min_confidence:
            continue
        out.append(_alert_out(
            r, camera=cameras.get(int(r["CameraID"])),
            detection=detections.get(int(r["CctvDetectionID"])),
            dispatches=dispatch_by_alert.get(int(r["CctvAlertID"]), []), now=ref))
    out.sort(key=lambda a: (-_SEV_ORDER.get(a["severity"], 0),
                            -(a["confidence"] or 0.0),
                            -a["cctv_alert_id"]))
    return out[: max(1, min(limit, 1000))]


def get_alert(alert_id: int) -> dict:
    """Full review card: the alert, its detection (with boxes), the camera, every
    dispatch, the audit timeline, and nearby cameras that could corroborate."""
    repo = _repo()
    row = repo.get("CctvAlert", alert_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"CCTV alert {alert_id} not found")
    camera = repo.get("Camera", int(row["CameraID"]))
    detection = repo.get("CctvDetection", int(row["CctvDetectionID"]))
    dispatches = repo.list("CctvDispatch", where={"CctvAlertID": int(alert_id)})
    rollup = _open_alert_rollup(repo)

    nearby: list[dict] = []
    if camera and camera.get("Lon") is not None:
        for c in repo.list("Camera"):
            if int(c["CameraID"]) == int(camera["CameraID"]):
                continue
            if c.get("Lon") is None or c.get("Lat") is None:
                continue
            dist = haversine_km(float(camera["Lon"]), float(camera["Lat"]),
                                float(c["Lon"]), float(c["Lat"]))
            if dist <= 1.5:
                count, worst = rollup.get(int(c["CameraID"]), (0, None))
                nearby.append(_camera_out(c, open_alerts=count, top_severity=worst))
        nearby.sort(key=lambda c: haversine_km(float(camera["Lon"]), float(camera["Lat"]),
                                               c["lon"], c["lat"]))

    return {
        "alert": _alert_out(row, camera=camera, detection=detection, dispatches=dispatches),
        "detection": (_detection_out(detection, camera_name=(camera or {}).get("Name"))
                      if detection else None),
        "camera": _camera_out(
            camera,
            open_alerts=rollup.get(int(camera["CameraID"]), (0, None))[0],
            top_severity=rollup.get(int(camera["CameraID"]), (0, None))[1],
        ) if camera else None,
        "dispatches": [_dispatch_out(d) for d in dispatches],
        "activity": [_activity_out(a) for a in repo.activity_for("alert", alert_id)],
        "nearby_cameras": nearby[:4],
    }


def confirm_alert(alert_id: int, scope: CctvScope, *, confirmed: bool,
                  note: Optional[str] = None, propose_dispatch: bool = True,
                  max_distance_km: Optional[float] = None) -> dict:
    """Human confirmation turns a detector proposal into a real, actionable alert.

    Requires a fresh confirmation (enforced at the router) + district scope. On
    success it may also PROPOSE the nearest responder, but that proposal is not a
    dispatch — it still has to be confirmed on its own.
    """
    repo = _repo()
    row = repo.get("CctvAlert", alert_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"CCTV alert {alert_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "confirm cctv alert")
    if row.get("Status") != "proposed":
        raise CctvConflict(
            f"Alert {alert_id} is '{row.get('Status')}', not 'proposed'. Only a "
            "proposed alert can be confirmed.")
    patch = {
        "Status": "confirmed", "ReviewedByActor": scope.actor, "ReviewedAt": _now(),
        "ReviewNote": _clip(note, cs.MAX_NOTES_LEN),
        "Version": int(row.get("Version") or 1) + 1,
    }
    repo.update("CctvAlert", alert_id, patch)
    repo.append_activity("alert", alert_id, actor=scope.actor, action="alert.confirmed",
                         diff={"status": "confirmed",
                               "confidence": _f(row.get("Confidence")),
                               "alert_type": row.get("AlertType")})
    _publish(EVENT_CCTV_ALERT_REVIEWED, {
        "cctv_alert_id": int(alert_id), "decision": "confirmed",
        "alert_type": row.get("AlertType"), "district_id": _i(row.get("DistrictID"))})

    out = {"ok": True, "id": int(alert_id), "kind": "cctv_alert", "status": "confirmed",
           "version": patch["Version"]}
    if propose_dispatch:
        try:
            out["dispatch_proposal"] = propose_dispatch_for_alert(
                alert_id, scope, max_distance_km=max_distance_km)
        except CctvError as exc:
            # A confirmation must stand on its own even if no responder is in
            # range — the analyst has still validated the incident.
            out["dispatch_proposal"] = {
                "cctv_alert_id": int(alert_id), "dispatch": None, "alternatives": [],
                "geometry_source": "unavailable", "considered": 0,
                "max_distance_km": float(max_distance_km
                                         or get_settings().cctv_dispatch_max_km),
                "eta_assumptions_version": dispatch_mod.ETA_ASSUMPTIONS_VERSION,
                "fallback_reason": None, "detail": str(exc)}
    return out


def dismiss_alert(alert_id: int, scope: CctvScope, *, reason: str,
                  note: Optional[str] = None) -> dict:
    """Record a dismissal WITH a reason. This is the detector's feedback signal, so
    the reason is required and comes from a closed list."""
    repo = _repo()
    if reason not in DISMISS_REASONS:
        raise CctvValidation(
            f"invalid dismissal reason {reason!r}; expected one of {DISMISS_REASONS}")
    row = repo.get("CctvAlert", alert_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"CCTV alert {alert_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "dismiss cctv alert")
    if row.get("Status") not in ("proposed", "confirmed"):
        raise CctvConflict(
            f"Alert {alert_id} is '{row.get('Status')}' and can no longer be dismissed.")
    active = [d for d in repo.list("CctvDispatch", where={"CctvAlertID": int(alert_id)})
              if d.get("Status") in ("dispatched", "acknowledged", "enroute", "onsite")]
    if active:
        raise CctvConflict(
            "A responder is already dispatched for this alert. Close or cancel the "
            "dispatch before dismissing it.")
    patch = {
        "Status": "dismissed", "ReviewedByActor": scope.actor, "ReviewedAt": _now(),
        "DismissReason": reason, "ReviewNote": _clip(note, cs.MAX_NOTES_LEN),
        "Version": int(row.get("Version") or 1) + 1,
    }
    repo.update("CctvAlert", alert_id, patch)
    # Cancel any outstanding proposal so a dismissed alert leaves nothing dangling.
    for d in repo.list("CctvDispatch", where={"CctvAlertID": int(alert_id)}):
        if d.get("Status") == "proposed":
            repo.update("CctvDispatch", int(d["CctvDispatchID"]), {
                "Status": "cancelled", "CancelledAt": _now(),
                "Version": int(d.get("Version") or 1) + 1})
            repo.append_activity("dispatch", int(d["CctvDispatchID"]), actor=scope.actor,
                                 action="dispatch.cancelled",
                                 diff={"cause": "alert dismissed"})
    repo.append_activity("alert", alert_id, actor=scope.actor, action="alert.dismissed",
                         diff={"status": "dismissed", "reason": reason,
                               "alert_type": row.get("AlertType"),
                               "confidence": _f(row.get("Confidence"))})
    _publish(EVENT_CCTV_ALERT_REVIEWED, {
        "cctv_alert_id": int(alert_id), "decision": "dismissed", "reason": reason,
        "alert_type": row.get("AlertType"), "district_id": _i(row.get("DistrictID"))})
    return {"ok": True, "id": int(alert_id), "kind": "cctv_alert", "status": "dismissed",
            "version": patch["Version"]}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
def propose_dispatch_for_alert(alert_id: int, scope: CctvScope, *,
                               max_distance_km: Optional[float] = None,
                               patrol_unit_id: Optional[int] = None) -> dict:
    """Rank the nearest responders and persist the best as a PROPOSED dispatch.

    Only a confirmed alert may reach here: proposing a unit for an unreviewed
    detection would make the human confirmation decorative.
    """
    repo = _repo()
    alert = repo.get("CctvAlert", alert_id)
    if not alert or alert.get("DeletedAt"):
        raise CctvNotFound(f"CCTV alert {alert_id} not found")
    enforce_district_scope(scope, alert.get("DistrictID"), "propose cctv dispatch")
    if alert.get("Status") not in ("confirmed", "dispatched"):
        raise CctvConflict(
            f"Alert {alert_id} is '{alert.get('Status')}'. Confirm the alert before "
            "proposing a responder.")
    if alert.get("Lon") is None or alert.get("Lat") is None:
        raise CctvValidation("this alert has no camera position to dispatch against")

    existing = [d for d in repo.list("CctvDispatch", where={"CctvAlertID": int(alert_id)})
                if d.get("Status") in ("proposed", "dispatched", "acknowledged",
                                       "enroute", "onsite")]
    if existing:
        raise CctvConflict(
            f"Alert {alert_id} already has an active dispatch "
            f"(#{existing[0]['CctvDispatchID']}, {existing[0].get('Status')}).")

    lon, lat = float(alert["Lon"]), float(alert["Lat"])
    plan = dispatch_mod.rank_responders(
        repo, lon, lat, district_id=_i(alert.get("DistrictID")),
        limit=5, max_km=max_distance_km)
    candidates = plan["candidates"]

    chosen = None
    if patrol_unit_id is not None:
        chosen = next((c for c in candidates
                       if c.get("patrol_unit_id") == int(patrol_unit_id)), None)
        if chosen is None:
            # An explicit override outside the ranked set is a validation error
            # rather than a silent fall-back to the nearest unit.
            raise CctvValidation(
                f"responder {patrol_unit_id} is not among the candidates within "
                f"{plan['max_distance_km']} km of this camera")
    elif candidates:
        chosen = candidates[0]

    if chosen is None:
        return {
            "cctv_alert_id": int(alert_id), "dispatch": None, "alternatives": [],
            "geometry_source": plan["geometry_source"], "considered": plan["considered"],
            "max_distance_km": plan["max_distance_km"],
            "eta_assumptions_version": plan["eta_assumptions_version"],
            "fallback_reason": plan.get("fallback_reason"),
            "detail": (f"No responder within {plan['max_distance_km']} km of this "
                       f"camera ({plan['considered']} considered). Widen the search "
                       "radius or escalate to the control room."),
        }

    row = repo.create("CctvDispatch", {
        "CctvAlertID": int(alert_id),
        "PatrolUnitID": chosen.get("patrol_unit_id"),
        "UnitID": chosen.get("unit_id"),
        "UnitName": chosen.get("unit_name") or "unnamed responder",
        "UnitKind": chosen.get("unit_kind"),
        "DistanceKm": round(float(chosen["distance_km"]), 3),
        "EtaMinutes": chosen.get("eta_minutes"),
        "Score": chosen.get("score"),
        "Reason": _guard_json_size(chosen.get("reason") or {}, "reason"),
        "Status": "proposed",
        "ProposedByActor": scope.actor,
        "DistrictID": _i(alert.get("DistrictID")),
        "ProposedAt": _now(),
    })
    repo.update("CctvAlert", alert_id, {
        "NearestUnitID": chosen.get("unit_id") or alert.get("NearestUnitID")})
    repo.append_activity("dispatch", row["CctvDispatchID"], actor=scope.actor,
                         action="dispatch.proposed",
                         diff={"alert_id": int(alert_id),
                               "unit_name": chosen.get("unit_name"),
                               "distance_km": chosen.get("distance_km"),
                               "geometry_source": plan["geometry_source"]})
    return {
        "cctv_alert_id": int(alert_id), "dispatch": _dispatch_out(row),
        "alternatives": [
            {k: c.get(k) for k in ("unit_id", "patrol_unit_id", "unit_name", "unit_kind",
                                   "distance_km", "eta_minutes", "score", "status")}
            for c in candidates[1:]],
        "geometry_source": plan["geometry_source"], "considered": plan["considered"],
        "max_distance_km": plan["max_distance_km"],
        "eta_assumptions_version": plan["eta_assumptions_version"],
        "fallback_reason": plan.get("fallback_reason"), "detail": None,
    }


_DISPATCH_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "dispatched": ("proposed",),
    "acknowledged": ("dispatched",),
    "enroute": ("dispatched", "acknowledged"),
    "onsite": ("enroute", "acknowledged"),
    "closed": ("onsite", "enroute", "acknowledged", "dispatched"),
    "cancelled": ("proposed", "dispatched", "acknowledged", "enroute"),
}
_DISPATCH_TS = {
    "dispatched": "DispatchedAt", "acknowledged": "AcknowledgedAt",
    "enroute": "EnrouteAt", "onsite": "OnsiteAt", "closed": "ClosedAt",
    "cancelled": "CancelledAt",
}
# Only these transitions need a fresh authenticated confirmation. Sending a unit
# is the consequential one; logging that it arrived is not.
DISPATCH_CONFIRM_REQUIRED = ("dispatched",)


def transition_dispatch(dispatch_id: int, new_status: str, scope: CctvScope, *,
                        expected_version: Optional[int] = None,
                        notes: Optional[str] = None) -> dict:
    repo = _repo()
    row = repo.get("CctvDispatch", dispatch_id)
    if not row or row.get("DeletedAt"):
        raise CctvNotFound(f"CCTV dispatch {dispatch_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), f"cctv dispatch {new_status}")
    allowed_from = _DISPATCH_TRANSITIONS.get(new_status)
    if allowed_from is None:
        raise CctvValidation(f"invalid dispatch status {new_status!r}")
    if row.get("Status") not in allowed_from:
        raise CctvConflict(
            f"cannot move dispatch from '{row.get('Status')}' to '{new_status}' "
            f"(allowed from {allowed_from}).")
    _check_version(row, expected_version, "dispatch")

    patch: dict = {"Status": new_status, "Version": int(row.get("Version") or 1) + 1}
    if notes:
        patch["Notes"] = _clip(notes, cs.MAX_NOTES_LEN)
    if new_status in _DISPATCH_TS:
        patch[_DISPATCH_TS[new_status]] = _now()
    if new_status == "dispatched":
        patch["ApprovedByActor"] = scope.actor
    repo.update("CctvDispatch", dispatch_id, patch)

    # Keep the parent alert's state honest about what is happening on the ground.
    alert_id = int(row["CctvAlertID"])
    alert = repo.get("CctvAlert", alert_id)
    if alert and not alert.get("DeletedAt"):
        if new_status == "dispatched" and alert.get("Status") == "confirmed":
            repo.update("CctvAlert", alert_id, {
                "Status": "dispatched", "Version": int(alert.get("Version") or 1) + 1})
        elif new_status == "closed" and alert.get("Status") == "dispatched":
            repo.update("CctvAlert", alert_id, {
                "Status": "resolved", "Version": int(alert.get("Version") or 1) + 1})

    # A responder that has been sent is no longer free.
    pu_id = _i(row.get("PatrolUnitID"))
    if pu_id is not None:
        unit = repo.get("PatrolUnit", pu_id)
        if unit:
            if new_status == "dispatched":
                repo.update("PatrolUnit", pu_id, {
                    "Status": "engaged", "LastUpdatedAt": _now(),
                    "Version": int(unit.get("Version") or 1) + 1})
            elif new_status in ("closed", "cancelled"):
                repo.update("PatrolUnit", pu_id, {
                    "Status": "available", "LastUpdatedAt": _now(),
                    "Version": int(unit.get("Version") or 1) + 1})

    repo.append_activity("dispatch", dispatch_id, actor=scope.actor,
                         action=f"dispatch.{new_status}",
                         diff={"from": row.get("Status"), "to": new_status,
                               "alert_id": alert_id,
                               "unit_name": row.get("UnitName")})
    if new_status == "dispatched":
        _publish(EVENT_CCTV_DISPATCH_CONFIRMED, {
            "cctv_dispatch_id": int(dispatch_id), "cctv_alert_id": alert_id,
            "unit_id": _i(row.get("UnitID")),
            "distance_km": _f(row.get("DistanceKm")),
            "district_id": _i(row.get("DistrictID"))})
    return {"ok": True, "id": int(dispatch_id), "kind": "cctv_dispatch",
            "status": new_status, "version": patch["Version"]}


def list_dispatches(*, alert_id: Optional[int] = None, status: Optional[str] = None,
                    district_id: Optional[int] = None, limit: int = 200) -> list[dict]:
    repo = _repo()
    out = []
    for r in repo.list("CctvDispatch"):
        if alert_id is not None and _i(r.get("CctvAlertID")) != int(alert_id):
            continue
        if status and r.get("Status") != status:
            continue
        if district_id is not None and _i(r.get("DistrictID")) != int(district_id):
            continue
        out.append(_dispatch_out(r))
    out.sort(key=lambda d: d["cctv_dispatch_id"], reverse=True)
    return out[: max(1, min(limit, 1000))]


def responder_candidates(lon: float, lat: float, *, district_id: Optional[int] = None,
                         max_distance_km: Optional[float] = None,
                         limit: int = 5) -> dict:
    """Preview the nearest-responder ranking without persisting anything."""
    return dispatch_mod.rank_responders(_repo(), lon, lat, district_id=district_id,
                                        limit=limit, max_km=max_distance_km)


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------
def overview(*, district_id: Optional[int] = None) -> dict:
    repo = _repo()
    ref = _now_dt()
    s = get_settings()

    health = {"total": 0, "online": 0, "degraded": 0, "offline": 0,
              "maintenance": 0, "analytics_enabled": 0}
    for c in repo.list("Camera"):
        if district_id is not None and _i(c.get("DistrictID")) != int(district_id):
            continue
        health["total"] += 1
        st = c.get("Status") or "online"
        if st in health:
            health[st] += 1
        if c.get("AnalyticsEnabled"):
            health["analytics_enabled"] += 1

    pending = confirmed = dispatched = dismissed_today = low_conf = last_hour = 0
    by_type: dict[str, int] = {}
    day_start = ref - timedelta(hours=24)
    hour_start = ref - timedelta(hours=1)
    for a in repo.list("CctvAlert"):
        if district_id is not None and _i(a.get("DistrictID")) != int(district_id):
            continue
        status = a.get("Status")
        created = _parse_dt(a.get("CreatedAt"))
        reviewed = _parse_dt(a.get("ReviewedAt"))
        if status == "proposed":
            pending += 1
            if float(a.get("Confidence") or 0.0) < s.cctv_low_confidence_threshold:
                low_conf += 1
        elif status == "confirmed":
            confirmed += 1
        elif status == "dispatched":
            dispatched += 1
        elif status == "dismissed" and reviewed and reviewed >= day_start:
            dismissed_today += 1
        if created and created >= hour_start:
            last_hour += 1
        t = a.get("AlertType") or "unknown"
        if status in ("proposed", "confirmed", "dispatched"):
            by_type[t] = by_type.get(t, 0) + 1

    return {
        "cameras": health, "pending_review": pending,
        "confirmed_awaiting_dispatch": confirmed, "dispatched_active": dispatched,
        "dismissed_today": dismissed_today, "low_confidence_pending": low_conf,
        "alerts_last_hour": last_hour,
        "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "capability": capability(), "district_id": district_id,
    }


def recent_activity(*, limit: int = 100) -> list[dict]:
    return [_activity_out(a) for a in _repo().recent_activity(limit=limit)]
