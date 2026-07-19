"""Emergency Response service (Prompt 17 §F/§G/§I).

Business logic over the Data Store disaster repo. Mirrors app/board/service.py:
explicit error classes mapped to HTTP in the router; every mutating operation
writes the domain record then an APPEND-ONLY DisasterActivity row, and publishes
a data-minimised Signal AFTER the write. Idempotency keys give safe retries.

Safety enforced here (never in the model alone):
  * a forecast never auto-creates an alert — it can only PROPOSE a watch/warning;
  * an alert proposal requires a fresh human confirmation to become active;
  * stale/low-confidence forecasts escalate and never emit an all-clear;
  * a resource is never dispatched without human approval, never double-allocated
    beyond quantity, and only inside the coordinator's assigned district;
  * an evacuation route is never described as guaranteed safe; no_route is explicit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..cache import SEG_IDEMPOTENCY
from ..signals import (EVENT_ALERT_REVIEW_REQUIRED, EVENT_ALLOCATION_APPROVED,
                       EVENT_FEED_STALE, EVENT_FORECAST_COMPLETED, get_signals)
from . import allocation as alloc_mod
from . import feeds, models, routing
from .geometry import centroid as geo_centroid, validate_geojson
from .guards import DisasterScope, enforce_district_scope
from .repo import DisasterRepo, disaster_cache, disaster_repo


# ---------------------------------------------------------------------------
# errors (mapped to HTTP in router)
# ---------------------------------------------------------------------------
class DisasterError(Exception):
    pass


class DisasterNotFound(DisasterError):
    pass


class DisasterForbidden(DisasterError):
    pass


class DisasterValidation(DisasterError):
    pass


class DisasterConflict(DisasterError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo() -> DisasterRepo:
    return disaster_repo()


def _publish(event: str, payload: dict) -> None:
    try:
        get_signals().publish(event, payload)
    except Exception:  # noqa: BLE001 — a signal failure must never break a write
        pass


def _idempotent(idem_key: Optional[str], produce: Callable[[], dict]) -> dict:
    if not idem_key:
        return produce()
    cache = disaster_cache()
    seen = cache.get(SEG_IDEMPOTENCY, f"disaster:{idem_key}")
    if seen:
        import json
        try:
            out = json.loads(seen)
            out["idempotent_replay"] = True
            return out
        except Exception:  # noqa: BLE001
            pass
    out = produce()
    try:
        import json
        cache.put(SEG_IDEMPOTENCY, f"disaster:{idem_key}", json.dumps(out))
    except Exception:  # noqa: BLE001
        pass
    return out


def _check_version(row: dict, expected: Optional[int], label: str) -> None:
    if expected is None:
        return
    if int(row.get("Version") or 0) != int(expected):
        raise DisasterConflict(
            f"Version conflict: {label} is at v{row.get('Version')}, you edited "
            f"v{expected}. Reload and retry.")


# ---------------------------------------------------------------------------
# serialisers (PascalCase DS columns -> snake_case API)
# ---------------------------------------------------------------------------
def _f(v):
    return float(v) if v is not None else None


def _event_out(r: dict) -> dict:
    return {
        "hazard_event_id": int(r["HazardEventID"]), "hazard_code": r.get("HazardCode"),
        "status": r.get("Status"), "severity": r.get("Severity"),
        "district_id": r.get("DistrictID"), "unit_id": r.get("UnitID"),
        "geojson": r.get("GeoJSON") or {},
        "centroid": ([_f(r.get("CentroidLon")), _f(r.get("CentroidLat"))]
                     if r.get("CentroidLon") is not None else None),
        "onset_at": r.get("OnsetAt"), "predicted_peak_at": r.get("PredictedPeakAt"),
        "source": r.get("Source"), "source_version": r.get("SourceVersion"),
        "description": r.get("Description"), "version": int(r.get("Version") or 1),
        "created_at": r.get("CreatedAt"), "updated_at": r.get("UpdatedAt")}


def _zone_out(r: dict) -> dict:
    return {
        "hazard_risk_zone_id": int(r["HazardRiskZoneID"]), "hazard_code": r.get("HazardCode"),
        "zone_kind": r.get("ZoneKind"), "name": r.get("Name"), "district_id": r.get("DistrictID"),
        "geojson": r.get("GeoJSON") or {},
        "centroid": ([_f(r.get("CentroidLon")), _f(r.get("CentroidLat"))]
                     if r.get("CentroidLon") is not None else None),
        "risk_level": r.get("RiskLevel"), "score": _f(r.get("Score")),
        "factors": r.get("Factors") or {}, "valid_from": r.get("ValidFrom"),
        "valid_to": r.get("ValidTo"), "source": r.get("Source"),
        "is_active": bool(r.get("IsActive"))}


def _prediction_out(r: dict) -> dict:
    return {
        "hazard_prediction_id": int(r["HazardPredictionID"]), "hazard_code": r.get("HazardCode"),
        "hazard_event_id": r.get("HazardEventID"),
        "model_version_label": r.get("ModelVersionLabel"),
        "feature_snapshot_id": r.get("FeatureSnapshotID"), "district_id": r.get("DistrictID"),
        "geojson": r.get("GeoJSON") or {}, "forecast_start": r.get("ForecastStart"),
        "forecast_end": r.get("ForecastEnd"), "horizon_hours": r.get("HorizonHours"),
        "data_as_of": r.get("DataAsOf"), "probability": _f(r.get("Probability")),
        "predicted_severity": r.get("PredictedSeverity"),
        "expected_impact": r.get("ExpectedImpact") or {}, "confidence": _f(r.get("Confidence")),
        "factors": r.get("Factors") or {}, "baseline_comparison": r.get("BaselineComparison") or {},
        "quality_state": r.get("QualityState"), "superseded_by_id": r.get("SupersededByID"),
        "created_at": r.get("CreatedAt")}


def _resource_out(r: dict) -> dict:
    caps = r.get("Capabilities") or []
    return {
        "resource_id": int(r["ResourceID"]), "resource_type": r.get("ResourceType"),
        "name": r.get("Name"), "quantity": int(r.get("Quantity") or 0), "unit": r.get("Unit"),
        "home_unit_id": r.get("HomeUnitID"), "employee_id": r.get("EmployeeID"),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")), "district_id": r.get("DistrictID"),
        "capacity": r.get("Capacity"), "capabilities": caps if isinstance(caps, list) else [caps],
        "status": r.get("Status"), "version": int(r.get("Version") or 1),
        "last_updated_at": r.get("LastUpdatedAt")}


def _shelter_out(r: dict) -> dict:
    fac = r.get("Facilities") or []
    return {
        "relief_shelter_id": int(r["ReliefShelterID"]), "name": r.get("Name"),
        "lon": _f(r.get("Lon")), "lat": _f(r.get("Lat")), "district_id": r.get("DistrictID"),
        "capacity": int(r.get("Capacity") or 0), "current_occupancy": int(r.get("CurrentOccupancy") or 0),
        "facilities": fac if isinstance(fac, list) else [fac], "status": r.get("Status"),
        "version": int(r.get("Version") or 1)}


def _alloc_out(r: dict) -> dict:
    return {
        "resource_allocation_id": int(r["ResourceAllocationID"]),
        "hazard_event_id": r.get("HazardEventID"), "resource_id": r.get("ResourceID"),
        "target_zone_id": r.get("TargetZoneID"),
        "quantity_allocated": int(r.get("QuantityAllocated") or 0), "status": r.get("Status"),
        "score": _f(r.get("Score")), "reason": r.get("Reason") or {},
        "district_id": r.get("DistrictID"), "proposed_at": r.get("ProposedAt"),
        "approved_at": r.get("ApprovedAt"), "dispatched_at": r.get("DispatchedAt"),
        "enroute_at": r.get("EnrouteAt"), "onsite_at": r.get("OnsiteAt"),
        "released_at": r.get("ReleasedAt")}


def _route_out(r: dict) -> dict:
    return {
        "evacuation_route_id": int(r["EvacuationRouteID"]),
        "hazard_event_id": r.get("HazardEventID"), "from_zone_id": r.get("FromZoneID"),
        "to_shelter_id": r.get("ToShelterID"), "geojson": r.get("GeoJSON") or {},
        "distance_km": _f(r.get("DistanceKm")), "est_minutes": _f(r.get("EstMinutes")),
        "road_graph_version": r.get("RoadGraphVersion"),
        "hazard_exclusion_version": r.get("HazardExclusionVersion"),
        "status": r.get("Status"), "notes": r.get("Notes")}


def _task_out(r: dict) -> dict:
    return {"response_task_id": int(r["ResponseTaskID"]), "response_plan_id": r.get("ResponsePlanID"),
            "title": r.get("Title"), "sequence": int(r.get("Sequence") or 1),
            "assigned_to_actor": r.get("AssignedToActor"), "status": r.get("Status"),
            "due_at": r.get("DueAt"), "completed_at": r.get("CompletedAt")}


def _plan_out(r: dict, tasks: list[dict]) -> dict:
    return {"response_plan_id": int(r["ResponsePlanID"]), "hazard_event_id": r.get("HazardEventID"),
            "hazard_code": r.get("HazardCode"), "title": r.get("Title"),
            "template_code": r.get("TemplateCode"), "status": r.get("Status"),
            "district_id": r.get("DistrictID"), "tasks": [_task_out(t) for t in tasks]}


def _reading_out(r: dict) -> dict:
    return {"hydromet_reading_id": int(r["HydroMetReadingID"]), "station_code": r.get("StationCode"),
            "source_agency": r.get("SourceAgency"), "metric_type": r.get("MetricType"),
            "value": _f(r.get("Value")), "unit": r.get("Unit"), "lon": _f(r.get("Lon")),
            "lat": _f(r.get("Lat")), "district_id": r.get("DistrictID"),
            "observed_at": r.get("ObservedAt"), "received_at": r.get("ReceivedAt"),
            "quality_flag": r.get("QualityFlag"), "superseded_by_id": r.get("SupersededByID")}


# ---------------------------------------------------------------------------
# lookups + reads
# ---------------------------------------------------------------------------
def list_hazard_types() -> list[dict]:
    rows = _repo().list("HazardType")
    return [{"hazard_type_id": int(r["HazardTypeID"]), "code": r.get("Code"),
             "name": r.get("Name"), "category": r.get("Category"),
             "default_lead_time_hours": r.get("DefaultLeadTimeHours"),
             "active": bool(r.get("Active"))} for r in rows]


def list_events(*, status: Optional[str] = None, district_id: Optional[int] = None) -> list[dict]:
    where: dict = {}
    if status:
        where["Status"] = status
    if district_id:
        where["DistrictID"] = district_id
    return [_event_out(r) for r in _repo().list("HazardEvent", where=where or None)]


def get_event(event_id: int) -> dict:
    r = _repo().get("HazardEvent", event_id)
    if not r or r.get("DeletedAt"):
        raise DisasterNotFound(f"HazardEvent {event_id} not found")
    return _event_out(r)


def list_zones(*, hazard_code: Optional[str] = None, district_id: Optional[int] = None) -> list[dict]:
    where: dict = {}
    if hazard_code:
        where["HazardCode"] = hazard_code
    if district_id:
        where["DistrictID"] = district_id
    return [_zone_out(r) for r in _repo().list("HazardRiskZone", where=where or None)]


def list_predictions(*, hazard_code: Optional[str] = None, district_id: Optional[int] = None,
                     limit: int = 100) -> list[dict]:
    where: dict = {}
    if hazard_code:
        where["HazardCode"] = hazard_code
    if district_id:
        where["DistrictID"] = district_id
    rows = _repo().list("HazardPrediction", where=where or None)
    rows.sort(key=lambda r: int(r.get("HazardPredictionID") or 0), reverse=True)
    return [_prediction_out(r) for r in rows[:limit]]


def list_resources(*, district_id: Optional[int] = None,
                   status: Optional[str] = None) -> list[dict]:
    where: dict = {}
    if district_id:
        where["DistrictID"] = district_id
    if status:
        where["Status"] = status
    return [_resource_out(r) for r in _repo().list("Resource", where=where or None)]


def list_shelters(*, district_id: Optional[int] = None) -> list[dict]:
    where = {"DistrictID": district_id} if district_id else None
    return [_shelter_out(r) for r in _repo().list("ReliefShelter", where=where)]


def list_readings(*, district_id: Optional[int] = None, metric: Optional[str] = None,
                  limit: int = 500) -> list[dict]:
    where: dict = {}
    if district_id:
        where["DistrictID"] = district_id
    if metric:
        where["MetricType"] = metric
    rows = _repo().list("HydroMetReading", where=where or None)
    rows.sort(key=lambda r: str(r.get("ObservedAt") or ""), reverse=True)
    return [_reading_out(r) for r in rows[:limit]]


def list_allocations(*, event_id: Optional[int] = None,
                     district_id: Optional[int] = None) -> list[dict]:
    where: dict = {}
    if event_id:
        where["HazardEventID"] = event_id
    if district_id:
        where["DistrictID"] = district_id
    return [_alloc_out(r) for r in _repo().list("ResourceAllocation", where=where or None)]


def list_routes(*, event_id: Optional[int] = None) -> list[dict]:
    where = {"HazardEventID": event_id} if event_id else None
    return [_route_out(r) for r in _repo().list("EvacuationRoute", where=where)]


# ---------------------------------------------------------------------------
# feeds
# ---------------------------------------------------------------------------
def ingest_feed(feed_code: str, *, readings: Optional[list[dict]] = None,
                actor: str = "system") -> dict:
    repo = _repo()
    # Outbound live connectors are gated by an ops kill-switch (no credential is
    # ever required for the Open-Meteo live feed, but the switch lets a locked-down
    # environment disable outbound calls).
    if feed_code in feeds.LIVE_FEED_CODES and readings is None:
        from ..config import get_settings
        if not get_settings().live_feed_enabled:
            raise DisasterValidation(
                "Live feed ingestion is disabled (DRISHTI_LIVE_FEED_ENABLED=false). "
                "Use the synthetic replay connector for the offline demo.")
    conn = feeds.connector_for(feed_code)
    cands = None
    if readings is not None:
        cands = [feeds.SyntheticReplayConnector._to_candidate(r) for r in readings]
    run = feeds.ingest(feed_code, connector=conn, candidates=cands, actor=actor, repo=repo)
    if run.get("Status") in ("stale", "failed"):
        _publish(EVENT_FEED_STALE, {"feed_code": feed_code, "status": run.get("Status"),
                                    "run_id": run.get("FeedIngestionRunID")})
    return {"feed_ingestion_run_id": int(run["FeedIngestionRunID"]),
            "feed_code": run.get("FeedCode"), "status": run.get("Status"),
            "accepted_count": run.get("AcceptedCount"), "duplicate_count": run.get("DuplicateCount"),
            "rejected_count": run.get("RejectedCount"), "started_at": run.get("StartedAt"),
            "finished_at": run.get("FinishedAt"), "last_observed_at": run.get("LastObservedAt"),
            "detail": run.get("Detail") or {}}


def feed_freshness() -> list[dict]:
    return feeds.freshness(_repo())


# ---------------------------------------------------------------------------
# hazard event lifecycle
# ---------------------------------------------------------------------------
_EVENT_STATUS = ("predicted", "watch", "warning", "active", "recovery", "closed")


def create_event(payload: dict, scope: DisasterScope, *, idem_key: Optional[str] = None) -> dict:
    repo = _repo()
    hazard = payload.get("hazard_code")
    if hazard not in models.supported_hazards():
        raise DisasterValidation(f"unknown hazard_code {hazard!r}")
    if payload.get("status") not in _EVENT_STATUS:
        raise DisasterValidation(f"invalid status {payload.get('status')!r}")
    geojson = payload.get("geojson") or {}
    if geojson:
        ok, reason = validate_geojson(geojson)
        if not ok:
            raise DisasterValidation(f"invalid geometry: {reason}")
    enforce_district_scope(scope, payload.get("district_id"), "create hazard event")

    def produce() -> dict:
        cen = geo_centroid(geojson) if geojson else None
        row = repo.create("HazardEvent", {
            "HazardCode": hazard, "Status": payload["status"],
            "Severity": payload.get("severity", "moderate"),
            "DistrictID": payload.get("district_id"), "UnitID": payload.get("unit_id"),
            "GeoJSON": geojson, "CanonicalCRS": "EPSG:4326",
            "CentroidLon": (cen[0] if cen else None), "CentroidLat": (cen[1] if cen else None),
            "OnsetAt": payload.get("onset_at"), "PredictedPeakAt": payload.get("predicted_peak_at"),
            "Source": payload.get("source"), "SourceVersion": payload.get("source_version"),
            "Description": payload.get("description")})
        repo.append_activity("hazard_event", row["HazardEventID"], actor=scope.actor,
                             action="hazard_event.create",
                             diff={"hazard": hazard, "status": payload["status"]})
        return {"ok": True, "id": int(row["HazardEventID"]), "kind": "hazard_event",
                "status": row["Status"], "version": int(row.get("Version") or 1)}

    return _idempotent(idem_key, produce)


def transition_event(event_id: int, new_status: str, scope: DisasterScope, *,
                     expected_version: Optional[int] = None) -> dict:
    repo = _repo()
    if new_status not in _EVENT_STATUS:
        raise DisasterValidation(f"invalid status {new_status!r}")
    row = repo.get("HazardEvent", event_id)
    if not row or row.get("DeletedAt"):
        raise DisasterNotFound(f"HazardEvent {event_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "update hazard event")
    _check_version(row, expected_version, "hazard event")
    new_version = int(row.get("Version") or 1) + 1
    repo.update("HazardEvent", event_id, {"Status": new_status, "Version": new_version})
    repo.append_activity("hazard_event", event_id, actor=scope.actor,
                         action="hazard_event.transition",
                         diff={"from": row.get("Status"), "to": new_status})
    return {"ok": True, "id": event_id, "kind": "hazard_event", "status": new_status,
            "version": new_version}


# ---------------------------------------------------------------------------
# forecast pipeline
# ---------------------------------------------------------------------------
def run_forecast(hazard_code: str, district_id: int, *, horizon_hours: int = 48,
                 data_as_of: Optional[str] = None, create_event_proposal: bool = False,
                 scope: Optional[DisasterScope] = None, actor: str = "system") -> dict:
    """validated readings -> feature snapshot -> baseline model -> validate output
    -> HazardPrediction -> (optional) event watch/warning PROPOSAL. Never an alert."""
    repo = _repo()
    if hazard_code not in models.supported_hazards():
        raise DisasterValidation(f"unknown hazard_code {hazard_code!r}")
    as_of = None
    if data_as_of:
        as_of = models._parse(data_as_of)
        if as_of is None:
            raise DisasterValidation("invalid data_as_of timestamp")
    snap = models.build_feature_snapshot(repo, hazard_code, district_id, as_of)
    model_out = models.run_model(hazard_code, snap.features)
    quality = models.assess_quality(snap, model_out)

    # impact + fusion over active susceptibility zones (retain both layers)
    zones = [z for z in repo.list("HazardRiskZone", where={"HazardCode": hazard_code})
             if z.get("IsActive") and (z.get("DistrictID") == district_id)]
    cells = [{"cell_id": z.get("HazardRiskZoneID"), "geojson": z.get("GeoJSON"),
              "susceptibility": float((z.get("Factors") or {}).get("susceptibility",
                                      (z.get("Score") or 0.5)))} for z in zones]
    fusion = models.fuse(model_out["probability"], cells, quality["confidence"]) if cells else None

    # validation summary for the Evidence Trail (MVP path)
    baseline_cmp = models.validate(hazard_code) if hazard_code in ("flood", "urban_flood",
                                                                   "landslide") else {}

    geojson = None
    if zones:
        geojson = zones[0].get("GeoJSON")
    pred = models.persist_prediction(
        repo, hazard_code=hazard_code, district_id=district_id, snap=snap,
        model_out={**model_out, "expected_impact": {"fusion": fusion} if fusion else {}},
        quality=quality, horizon_hours=horizon_hours, geojson=geojson,
        baseline_comparison=baseline_cmp, actor=actor)

    _publish(EVENT_FORECAST_COMPLETED, {
        "hazard_prediction_id": pred.get("HazardPredictionID"), "hazard_code": hazard_code,
        "district_id": district_id, "quality": quality["quality_state"]})

    event_proposal_id = None
    if create_event_proposal and quality["quality_state"] == "ok" \
            and model_out["probability"] >= 0.5 and scope is not None:
        # a PROPOSAL only (status 'predicted'); a human must promote to watch/warning
        prop = create_event({
            "hazard_code": hazard_code, "status": "predicted",
            "severity": model_out["severity"], "district_id": district_id,
            "geojson": (geojson or {}), "source": "forecast",
            "source_version": pred.get("ModelVersionLabel"),
            "description": f"Forecast proposal (p={model_out['probability']}, "
                           f"confidence={quality['confidence']})"}, scope)
        event_proposal_id = prop.get("id")

    answer = (f"{hazard_code} area forecast for district {district_id}: "
              f"probability {model_out['probability']:.2f} "
              f"({model_out['severity']}), confidence {quality['confidence']:.2f}.")
    if quality["escalation"]:
        answer += " " + quality["escalation"]
    result = {
        "answer": answer, "confidence": quality["confidence"],
        "source_record_ids": [f"HazardPrediction:{pred.get('HazardPredictionID')}",
                              f"FeatureSnapshot:{snap.snapshot_id}",
                              f"District:{district_id}"],
        "reasoning_summary": (f"{model_out.get('rule')} on an immutable feature snapshot; "
                              "confidence reflects data freshness/coverage; "
                              "distinguishes observed vs model-predicted layers."),
        "model_version": pred.get("ModelVersionLabel")}
    return {"result": result, "prediction": _prediction_out(pred),
            "baseline_comparison": baseline_cmp,
            "escalation": quality["escalation"], "event_proposal_id": event_proposal_id}


def validate_forecast(hazard_code: str = "flood", *, n_origins: int = 120) -> dict:
    return models.validate(hazard_code, n_origins=n_origins)


# ---------------------------------------------------------------------------
# alerts (reuse AlertHistory; proposal requires human confirmation)
# ---------------------------------------------------------------------------
_ALERT_MAX_SCAN = 100_000


def _alert_next_id(repo: DisasterRepo) -> int:
    rows = repo.store.query("AlertHistory", limit=_ALERT_MAX_SCAN)
    return max((int(r.get("AlertID") or 0) for r in rows), default=0) + 1


def _alert_out(r: dict) -> dict:
    payload = r.get("Payload") or {}
    return {"alert_id": int(r["AlertID"]), "alert_type": r.get("AlertType"),
            "severity": r.get("Severity"), "title": r.get("Title"), "message": r.get("Message"),
            "hazard_event_id": r.get("HazardEventID"), "district_id": r.get("DistrictID"),
            "status": r.get("Status"), "confidence": payload.get("confidence"),
            "freshness": payload.get("freshness"), "synthetic": True,
            "acknowledged_by": r.get("AcknowledgedBy"), "created_at": r.get("CreatedAt")}


def list_alerts(*, hazard_only: bool = True, district_id: Optional[int] = None) -> list[dict]:
    repo = _repo()
    rows = repo.store.query("AlertHistory", limit=_ALERT_MAX_SCAN)
    out = []
    for r in rows:
        if hazard_only and not r.get("HazardEventID"):
            continue
        if district_id and r.get("DistrictID") != district_id:
            continue
        out.append(_alert_out(r))
    out.sort(key=lambda a: int(a["alert_id"]), reverse=True)
    return out


def propose_alert(payload: dict, scope: DisasterScope, *,
                  idem_key: Optional[str] = None) -> dict:
    """Create a REVIEWABLE hazard alert proposal (status 'proposed'). Never active
    until a human confirms (approve_alert). Carries confidence + freshness."""
    repo = _repo()
    event = repo.get("HazardEvent", payload["hazard_event_id"])
    if not event or event.get("DeletedAt"):
        raise DisasterNotFound(f"HazardEvent {payload['hazard_event_id']} not found")
    enforce_district_scope(scope, event.get("DistrictID"), "propose alert")
    # attach latest forecast confidence/quality for honesty in the alert card
    preds = [p for p in repo.list("HazardPrediction",
                                  where={"HazardCode": event.get("HazardCode"),
                                         "DistrictID": event.get("DistrictID")})]
    preds.sort(key=lambda p: int(p.get("HazardPredictionID") or 0), reverse=True)
    conf = preds[0].get("Confidence") if preds else None
    quality = preds[0].get("QualityState") if preds else "unknown"

    def produce() -> dict:
        aid = _alert_next_id(repo)
        row = {"AlertID": aid, "AlertType": payload["alert_type"],
               "Severity": payload.get("severity", "warning"), "Title": payload["title"],
               "Message": payload.get("message"), "HazardEventID": int(event["HazardEventID"]),
               "DistrictID": event.get("DistrictID"), "Status": "proposed",
               "Payload": {"confidence": conf, "freshness": quality, "synthetic": True,
                           "proposed_by": scope.actor}, "CreatedAt": _now()}
        repo.store.upsert("AlertHistory", f"alert:{aid}", row)
        repo.append_activity("alert", aid, actor=scope.actor, action="alert.proposed",
                             diff={"alert_type": payload["alert_type"], "confidence": conf,
                                   "quality": quality})
        _publish(EVENT_ALERT_REVIEW_REQUIRED, {"alert_id": aid, "hazard_event_id": int(event["HazardEventID"]),
                                               "severity": payload.get("severity", "warning"),
                                               "confidence": conf})
        return {"ok": True, "id": aid, "kind": "alert", "status": "proposed"}

    return _idempotent(idem_key, produce)


def approve_alert(alert_id: int, scope: DisasterScope, *, confirmed: bool) -> dict:
    """Human confirmation turns a proposal into an active warning. Requires a
    fresh confirmation (enforced at the router) + district scope."""
    repo = _repo()
    row = repo.store.get("AlertHistory", f"alert:{alert_id}")
    if not row:
        raise DisasterNotFound(f"Alert {alert_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), "approve warning")
    if row.get("Status") != "proposed":
        raise DisasterConflict(f"Alert {alert_id} is '{row.get('Status')}', not 'proposed'.")
    row = {**row, "Status": "open", "AcknowledgedBy": scope.actor, "UpdatedAt": _now()}
    repo.store.upsert("AlertHistory", f"alert:{alert_id}", row)
    repo.append_activity("alert", alert_id, actor=scope.actor, action="alert.approved",
                         diff={"status": "open"})
    return {"ok": True, "id": alert_id, "kind": "alert", "status": "open"}


# ---------------------------------------------------------------------------
# resources + shelters CRUD
# ---------------------------------------------------------------------------
def create_resource(payload: dict, scope: DisasterScope) -> dict:
    repo = _repo()
    if payload.get("resource_type") not in models.ds.RESOURCE_TYPES:
        raise DisasterValidation(f"invalid resource_type {payload.get('resource_type')!r}")
    enforce_district_scope(scope, payload.get("district_id"), "create resource")
    row = repo.create("Resource", {
        "ResourceType": payload["resource_type"], "Name": payload["name"],
        "Quantity": payload.get("quantity", 1), "Unit": payload.get("unit"),
        "HomeUnitID": payload.get("home_unit_id"), "EmployeeID": payload.get("employee_id"),
        "Lon": payload.get("lon"), "Lat": payload.get("lat"),
        "DistrictID": payload.get("district_id"), "Capacity": payload.get("capacity"),
        "Capabilities": payload.get("capabilities", []),
        "Status": payload.get("status", "available"), "LastUpdatedAt": _now()})
    repo.append_activity("resource", row["ResourceID"], actor=scope.actor,
                         action="resource.create", diff={"type": payload["resource_type"]})
    return {"ok": True, "id": int(row["ResourceID"]), "kind": "resource",
            "status": row["Status"], "version": int(row.get("Version") or 1)}


def create_shelter(payload: dict, scope: DisasterScope) -> dict:
    repo = _repo()
    enforce_district_scope(scope, payload.get("district_id"), "create shelter")
    row = repo.create("ReliefShelter", {
        "Name": payload["name"], "Lon": payload.get("lon"), "Lat": payload.get("lat"),
        "DistrictID": payload.get("district_id"), "Capacity": payload.get("capacity", 0),
        "CurrentOccupancy": payload.get("current_occupancy", 0),
        "Facilities": payload.get("facilities", []), "Status": payload.get("status", "open")})
    repo.append_activity("shelter", row["ReliefShelterID"], actor=scope.actor,
                         action="shelter.create", diff={"name": payload["name"]})
    return {"ok": True, "id": int(row["ReliefShelterID"]), "kind": "shelter",
            "status": row["Status"], "version": int(row.get("Version") or 1)}


# ---------------------------------------------------------------------------
# allocation
# ---------------------------------------------------------------------------
def propose_allocation(event_id: int, required: dict[str, int], scope: DisasterScope, *,
                       max_distance_km: float = 120.0, optimizer: str = "greedy") -> dict:
    """Produce PROPOSED allocations (never dispatched). A human must approve."""
    repo = _repo()
    event = repo.get("HazardEvent", event_id)
    if not event or event.get("DeletedAt"):
        raise DisasterNotFound(f"HazardEvent {event_id} not found")
    enforce_district_scope(scope, event.get("DistrictID"), "propose allocation")
    if optimizer == "ortools":
        plan = alloc_mod.ortools_plan(repo, event, required, max_distance_km=max_distance_km)
    else:
        plan = alloc_mod.greedy_plan(repo, event, required, max_distance_km=max_distance_km)
    comparison = alloc_mod.compare_optimizers(repo, event, required, max_distance_km=max_distance_km)

    persisted: list[dict] = []
    for p in plan["proposals"]:
        row = repo.create("ResourceAllocation", {
            "HazardEventID": event_id, "ResourceID": p["resource_id"],
            "QuantityAllocated": p["quantity_allocated"], "Status": "proposed",
            "Score": p.get("score"), "Reason": p.get("reason", {}),
            "ProposedByActor": scope.actor, "DistrictID": event.get("DistrictID"),
            "ProposedAt": _now()})
        repo.append_activity("allocation", row["ResourceAllocationID"], actor=scope.actor,
                             action="allocation.proposed",
                             diff={"resource_id": p["resource_id"], "qty": p["quantity_allocated"]})
        out = _alloc_out(row)
        out.update({"resource_name": p.get("resource_name"), "resource_type": p.get("resource_type")})
        persisted.append(out)
    return {"hazard_event_id": event_id, "optimizer": plan["optimizer"],
            "proposals": persisted, "unmet": plan.get("unmet", {}),
            "reasons": plan.get("reasons", []), "comparison": comparison}


_ALLOC_TRANSITIONS = {
    "approved": ("proposed",), "dispatched": ("approved",),
    "enroute": ("dispatched",), "onsite": ("enroute",),
    "released": ("onsite", "enroute", "dispatched"), "rejected": ("proposed",),
}
_ALLOC_TS = {"approved": "ApprovedAt", "dispatched": "DispatchedAt", "enroute": "EnrouteAt",
             "onsite": "OnsiteAt", "released": "ReleasedAt"}


def transition_allocation(alloc_id: int, new_status: str, scope: DisasterScope, *,
                          expected_version: Optional[int] = None) -> dict:
    repo = _repo()
    row = repo.get("ResourceAllocation", alloc_id)
    if not row or row.get("DeletedAt"):
        raise DisasterNotFound(f"ResourceAllocation {alloc_id} not found")
    enforce_district_scope(scope, row.get("DistrictID"), f"allocation {new_status}")
    allowed_from = _ALLOC_TRANSITIONS.get(new_status)
    if allowed_from is None:
        raise DisasterValidation(f"invalid allocation status {new_status!r}")
    if row.get("Status") not in allowed_from:
        raise DisasterConflict(
            f"cannot move allocation from '{row.get('Status')}' to '{new_status}' "
            f"(allowed from {allowed_from}).")
    _check_version(row, expected_version, "allocation")
    # no double-allocation beyond quantity at approve time (count only COMMITTED
    # allocations — a tentative proposal does not block another's approval).
    if new_status == "approved":
        resource = repo.get("Resource", row.get("ResourceID"))
        if resource is not None:
            other = alloc_mod.committed_quantity(repo, int(row["ResourceID"]),
                                                 exclude_alloc_id=alloc_id)
            if other + int(row.get("QuantityAllocated") or 0) > int(resource.get("Quantity") or 0):
                raise DisasterConflict(
                    "approving would double-allocate the resource beyond its quantity.")
    patch: dict = {"Status": new_status, "Version": int(row.get("Version") or 1) + 1}
    if new_status == "approved":
        patch["ApprovedByActor"] = scope.actor
    if new_status in _ALLOC_TS:
        patch[_ALLOC_TS[new_status]] = _now()
    if new_status == "dispatched":
        # mark the resource deployed on dispatch
        resource = repo.get("Resource", row.get("ResourceID"))
        if resource is not None:
            repo.update("Resource", int(row["ResourceID"]),
                        {"Status": "deployed", "Version": int(resource.get("Version") or 1) + 1})
    if new_status == "released":
        resource = repo.get("Resource", row.get("ResourceID"))
        if resource is not None:
            repo.update("Resource", int(row["ResourceID"]),
                        {"Status": "available", "Version": int(resource.get("Version") or 1) + 1})
    repo.update("ResourceAllocation", alloc_id, patch)
    repo.append_activity("allocation", alloc_id, actor=scope.actor,
                         action=f"allocation.{new_status}",
                         diff={"from": row.get("Status"), "to": new_status})
    if new_status == "approved":
        _publish(EVENT_ALLOCATION_APPROVED, {"allocation_id": alloc_id,
                                             "resource_id": row.get("ResourceID"),
                                             "hazard_event_id": row.get("HazardEventID")})
    return {"ok": True, "id": alloc_id, "kind": "allocation", "status": new_status,
            "version": patch["Version"]}


# ---------------------------------------------------------------------------
# evacuation routing
# ---------------------------------------------------------------------------
def propose_route(event_id: int, scope: DisasterScope, *,
                  from_zone_id: Optional[int] = None,
                  to_shelter_id: Optional[int] = None) -> dict:
    repo = _repo()
    event = repo.get("HazardEvent", event_id)
    if not event or event.get("DeletedAt"):
        raise DisasterNotFound(f"HazardEvent {event_id} not found")
    enforce_district_scope(scope, event.get("DistrictID"), "propose evacuation route")

    # from = risk zone centroid (or event centroid); to = a shelter
    zone = repo.get("HazardRiskZone", from_zone_id) if from_zone_id else None
    if zone is not None and zone.get("CentroidLon") is not None:
        frm = (float(zone["CentroidLon"]), float(zone["CentroidLat"]))
    else:
        cen = geo_centroid(event.get("GeoJSON") or {})
        frm = cen or (event.get("CentroidLon"), event.get("CentroidLat"))
    if not frm or frm[0] is None:
        raise DisasterValidation("no origin geometry for the route")

    shelters = repo.list("ReliefShelter", where={"DistrictID": event.get("DistrictID")})
    if to_shelter_id:
        shelters = [s for s in shelters if s.get("ReliefShelterID") == to_shelter_id]
    shelters = [s for s in shelters if s.get("Lon") is not None
                and s.get("Status") != "closed"]
    if not shelters:
        raise DisasterNotFound("no open shelter with a location for this district")

    hazard_geom = event.get("GeoJSON") or None
    # try shelters nearest-first; return the first with a safe route, else no_route
    from .geometry import haversine_km
    shelters.sort(key=lambda s: haversine_km(frm[0], frm[1], float(s["Lon"]), float(s["Lat"])))
    best_no_route = None
    for s in shelters:
        r = routing.route(frm[0], frm[1], float(s["Lon"]), float(s["Lat"]),
                          hazard_geom=hazard_geom)
        if r["status"] == "selected":
            row = repo.create("EvacuationRoute", {
                "HazardEventID": event_id, "FromZoneID": from_zone_id,
                "ToShelterID": int(s["ReliefShelterID"]), "GeoJSON": r["geojson"],
                "DistanceKm": r["distance_km"], "EstMinutes": r["est_minutes"],
                "RoadGraphVersion": r["road_graph_version"],
                "HazardExclusionVersion": r["hazard_exclusion_version"],
                "Status": "proposed", "Notes": r["notes"]})
            repo.append_activity("route", row["EvacuationRouteID"], actor=scope.actor,
                                 action="route.proposed",
                                 diff={"shelter": int(s["ReliefShelterID"]),
                                       "distance_km": r["distance_km"]})
            return _route_out(row)
        best_no_route = r
    # no safe route to any shelter — record it explicitly (never declare safe)
    row = repo.create("EvacuationRoute", {
        "HazardEventID": event_id, "FromZoneID": from_zone_id,
        "ToShelterID": (to_shelter_id or None), "GeoJSON": {},
        "RoadGraphVersion": (best_no_route or {}).get("road_graph_version"),
        "HazardExclusionVersion": (best_no_route or {}).get("hazard_exclusion_version"),
        "Status": "no_route", "Notes": (best_no_route or {}).get("notes",
                                        "No safe route to any open shelter.")})
    repo.append_activity("route", row["EvacuationRouteID"], actor=scope.actor,
                         action="route.no_route", diff={"event": event_id})
    return _route_out(row)


def select_route(route_id: int, scope: DisasterScope, *, confirmed: bool) -> dict:
    """Approve/select an evacuation route (fresh confirmation enforced at router)."""
    repo = _repo()
    row = repo.get("EvacuationRoute", route_id)
    if not row or row.get("DeletedAt"):
        raise DisasterNotFound(f"EvacuationRoute {route_id} not found")
    if row.get("Status") == "no_route":
        raise DisasterConflict("cannot select a route with no safe path.")
    event = repo.get("HazardEvent", row.get("HazardEventID"))
    enforce_district_scope(scope, (event or {}).get("DistrictID"), "approve evacuation plan")
    repo.update("EvacuationRoute", route_id,
                {"Status": "selected", "Version": int(row.get("Version") or 1) + 1})
    repo.append_activity("route", route_id, actor=scope.actor, action="route.selected",
                         diff={"status": "selected"})
    return {"ok": True, "id": route_id, "kind": "route", "status": "selected"}


# ---------------------------------------------------------------------------
# response plans + tasks (SOP templates)
# ---------------------------------------------------------------------------
SOP_TEMPLATES: dict[str, list[str]] = {
    "flood": ["Activate district EOC + confirm feed freshness",
              "Issue watch/warning after human confirmation",
              "Pre-position boats + rescue teams to at-risk zones",
              "Open relief shelters + verify capacity/occupancy",
              "Propose evacuation routes avoiding the hazard polygon",
              "After-action review + export"],
    "urban_flood": ["Confirm rainfall/drainage readings",
                    "Alert traffic + low-lying ward teams",
                    "Deploy pumps + barricades",
                    "Open nearest shelters", "After-action review"],
    "landslide": ["Confirm slope + antecedent-rainfall readings",
                  "Warn Ghats belt residents after confirmation",
                  "Close vulnerable road segments",
                  "Pre-position rescue + medical", "After-action review"],
    "cyclone": ["Ingest official track/cone", "Confirm coastal warning",
                "Evacuate low-lying coastal zones", "Stock relief material",
                "After-action review"],
    "drought": ["Confirm rainfall deficit + reservoir trend",
                "Plan water tanker allocation", "Monitor at-risk taluks",
                "After-action review"],
    "heatwave": ["Confirm temperature threshold breach",
                 "Issue heat advisory after confirmation",
                 "Open cooling centres", "After-action review"],
    "forest_fire": ["Confirm detection + dryness", "Deploy fire teams",
                    "Establish firebreaks", "After-action review"],
    "dam_breach": ["Confirm reservoir level", "Warn downstream zones",
                   "Evacuate downstream", "After-action review"],
    "lightning": ["Confirm thunderstorm instability", "Issue advisory",
                  "Move outdoor crews to safety", "After-action review"],
}


def create_plan(payload: dict, scope: DisasterScope) -> dict:
    repo = _repo()
    hazard = payload.get("hazard_code")
    if hazard not in models.supported_hazards():
        raise DisasterValidation(f"unknown hazard_code {hazard!r}")
    enforce_district_scope(scope, payload.get("district_id"), "create response plan")
    plan = repo.create("ResponsePlan", {
        "HazardEventID": payload.get("hazard_event_id"), "HazardCode": hazard,
        "Title": payload["title"], "TemplateCode": payload.get("template_code", hazard),
        "Status": "active", "DistrictID": payload.get("district_id")})
    for i, title in enumerate(SOP_TEMPLATES.get(hazard, ["Assess", "Respond", "After-action review"]), 1):
        repo.create("ResponseTask", {
            "ResponsePlanID": int(plan["ResponsePlanID"]), "Title": title, "Sequence": i,
            "Status": "open"})
    repo.append_activity("plan", plan["ResponsePlanID"], actor=scope.actor,
                         action="plan.create", diff={"hazard": hazard})
    return get_plan(int(plan["ResponsePlanID"]))


def get_plan(plan_id: int) -> dict:
    repo = _repo()
    plan = repo.get("ResponsePlan", plan_id)
    if not plan or plan.get("DeletedAt"):
        raise DisasterNotFound(f"ResponsePlan {plan_id} not found")
    tasks = sorted(repo.list("ResponseTask", where={"ResponsePlanID": plan_id}),
                   key=lambda t: int(t.get("Sequence") or 0))
    return _plan_out(plan, tasks)


def list_plans(*, district_id: Optional[int] = None) -> list[dict]:
    repo = _repo()
    where = {"DistrictID": district_id} if district_id else None
    return [get_plan(int(p["ResponsePlanID"])) for p in repo.list("ResponsePlan", where=where)]


def patch_task(task_id: int, payload: dict, scope: DisasterScope) -> dict:
    repo = _repo()
    row = repo.get("ResponseTask", task_id)
    if not row or row.get("DeletedAt"):
        raise DisasterNotFound(f"ResponseTask {task_id} not found")
    _check_version(row, payload.get("expected_version"), "task")
    patch: dict = {"Version": int(row.get("Version") or 1) + 1}
    if payload.get("status"):
        if payload["status"] not in ("open", "in_progress", "done", "overdue"):
            raise DisasterValidation("invalid task status")
        patch["Status"] = payload["status"]
        if payload["status"] == "done":
            patch["CompletedAt"] = _now()
    if payload.get("assigned_to_actor") is not None:
        patch["AssignedToActor"] = payload["assigned_to_actor"]
    if payload.get("due_at") is not None:
        patch["DueAt"] = payload["due_at"]
    repo.update("ResponseTask", task_id, patch)
    repo.append_activity("task", task_id, actor=scope.actor, action="task.update",
                         diff={k: v for k, v in patch.items() if k != "Version"})
    return {"ok": True, "id": task_id, "kind": "task", "status": patch.get("Status", row.get("Status")),
            "version": patch["Version"]}


# ---------------------------------------------------------------------------
# situation overview
# ---------------------------------------------------------------------------
def situation_overview(*, district_id: Optional[int] = None) -> dict:
    repo = _repo()
    events = [e for e in repo.list("HazardEvent")
              if (district_id is None or e.get("DistrictID") == district_id)]
    active = [e for e in events if e.get("Status") in ("watch", "warning", "active")]
    alerts = list_alerts(district_id=district_id)
    open_alerts = [a for a in alerts if a.get("status") in ("proposed", "open")]
    preds = repo.list("HazardPrediction")
    low_conf = [p for p in preds if p.get("QualityState") in ("low_confidence", "stale")]
    resources = repo.list("Resource")
    unavailable = [r for r in resources if r.get("Status") in ("deployed", "maintenance")]
    tasks = [t for t in repo.list("ResponseTask") if t.get("Status") in ("open", "in_progress")]
    fresh = feeds.freshness(repo)
    stale = [f for f in fresh if f.get("status") in ("stale", "failed")]

    # readiness KPI: allocated vs required (bullet-chart friendly)
    active_allocs = [a for a in repo.list("ResourceAllocation")
                     if a.get("Status") in ("approved", "dispatched", "enroute", "onsite")]
    readiness = {"available_resources": sum(1 for r in resources if r.get("Status") == "available"),
                 "deployed_resources": sum(1 for r in resources if r.get("Status") == "deployed"),
                 "shelters_open": sum(1 for s in repo.list("ReliefShelter")
                                      if s.get("Status") == "open"),
                 "active_allocations": len(active_allocs)}
    return {"generated_at": _now(), "active_hazards": len(active),
            "open_alerts": len(open_alerts), "low_confidence_warnings": len(low_conf),
            "readiness": readiness, "unavailable_resources": len(unavailable),
            "open_tasks": len(tasks), "feed_freshness": fresh, "stale_feeds": len(stale),
            "hazards": [_event_out(e) for e in active]}
