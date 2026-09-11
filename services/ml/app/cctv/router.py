"""FastAPI router for CCTV monitoring (the live watch wall).

Reads: any authenticated role (the wall is a situational view).
Writes: the ``cctv_review`` / ``cctv_dispatch`` / ``cctv_admin`` permissions,
scoped to the operator's assigned district.

Two separate confirmations are enforced, because they are two different human
judgements and collapsing them would be the whole safety story gone:

  * ``POST /cctv/alerts/{id}/confirm?confirm=true``   — "this detection is real"
  * ``POST /cctv/dispatch/{id}/transition?status=dispatched`` with
    ``{"confirm": true}``                             — "send this unit"

Either without its confirmation returns **428**. Errors are mapped to HTTP
without leaking internals, and every mutating route runs the synthetic
write-posture guard.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from . import guards, seed as seed_mod, service
from .repo import CctvRepoError
from .schemas import (AlertConfirmRequest, AlertDismissRequest, AnalyticsRunRequest,
                      CameraCreate, CameraPatch, DetectionIngestRequest,
                      DispatchProposeRequest, DispatchTransitionRequest,
                      PatrolUnitCreate)

router = APIRouter(prefix="/cctv", tags=["cctv-monitoring"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.CctvNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except service.CctvForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except service.CctvValidation as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except service.CctvConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except CctvRepoError as exc:
        # A persistence-layer refusal (append-only violation, missing row) is a
        # real answer, not a crash — 409 keeps it distinguishable from the bare
        # 500 that an unmapped exception used to produce.
        raise HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# capability + lookups — read by any authenticated role
# ---------------------------------------------------------------------------
@router.get("/capability")
def cctv_capability(_role: str = Depends(guards.require_cctv_read)):
    """What this deployment can actually do. The UI renders this verbatim so a
    viewer is never left assuming real frame inference is running."""
    return service.capability()


@router.get("/detection-types")
def detection_types(_role: str = Depends(guards.require_cctv_read)):
    return {"detection_types": service.detection_types(),
            "dismiss_reasons": service.dismiss_reasons()}


@router.get("/overview")
def overview(district_id: Optional[int] = Query(None, ge=1),
             _role: str = Depends(guards.require_cctv_read)):
    return _call(service.overview, district_id=district_id)


# ---------------------------------------------------------------------------
# cameras
# ---------------------------------------------------------------------------
@router.get("/cameras")
def list_cameras(district_id: Optional[int] = Query(None, ge=1),
                 status: Optional[str] = Query(None),
                 with_alerts_only: bool = Query(False),
                 _role: str = Depends(guards.require_cctv_read)):
    return {"cameras": _call(service.list_cameras, district_id=district_id,
                             status=status, with_alerts_only=with_alerts_only)}


@router.get("/cameras/{camera_id}")
def get_camera(camera_id: int, _role: str = Depends(guards.require_cctv_read)):
    return _call(service.get_camera, camera_id)


@router.post("/cameras", status_code=201)
def create_camera(req: CameraCreate, request: Request,
                  role: str = Depends(guards.require_cctv_admin)):
    guards.require_cctv_write_allowed(request)
    return _call(service.create_camera, req.model_dump(), guards.resolve_scope(request))


@router.patch("/cameras/{camera_id}")
def patch_camera(camera_id: int, req: CameraPatch, request: Request,
                 role: str = Depends(guards.require_cctv_admin)):
    guards.require_cctv_write_allowed(request)
    return _call(service.patch_camera, camera_id,
                 req.model_dump(exclude_unset=True), guards.resolve_scope(request))


@router.delete("/cameras/{camera_id}")
def retire_camera(camera_id: int, request: Request,
                  role: str = Depends(guards.require_cctv_admin)):
    guards.require_cctv_write_allowed(request)
    return _call(service.retire_camera, camera_id, guards.resolve_scope(request))


# ---------------------------------------------------------------------------
# responders
# ---------------------------------------------------------------------------
@router.get("/responders")
def list_responders(district_id: Optional[int] = Query(None, ge=1),
                    status: Optional[str] = Query(None),
                    _role: str = Depends(guards.require_cctv_read)):
    return {"responders": _call(service.list_patrol_units, district_id=district_id,
                                status=status)}


@router.post("/responders", status_code=201)
def create_responder(req: PatrolUnitCreate, request: Request,
                     role: str = Depends(guards.require_cctv_admin)):
    guards.require_cctv_write_allowed(request)
    return _call(service.create_patrol_unit, req.model_dump(), guards.resolve_scope(request))


@router.get("/responders/nearest")
def nearest_responders(lon: float = Query(..., ge=-180.0, le=180.0),
                       lat: float = Query(..., ge=-90.0, le=90.0),
                       district_id: Optional[int] = Query(None, ge=1),
                       max_distance_km: Optional[float] = Query(None, gt=0.0, le=200.0),
                       limit: int = Query(5, ge=1, le=25),
                       _role: str = Depends(guards.require_cctv_read)):
    """Preview the nearest-responder ranking. Persists nothing."""
    return _call(service.responder_candidates, lon, lat, district_id=district_id,
                 max_distance_km=max_distance_km, limit=limit)


# ---------------------------------------------------------------------------
# detections
# ---------------------------------------------------------------------------
@router.get("/detections")
def list_detections(camera_id: Optional[int] = Query(None, ge=1),
                    detection_type: Optional[str] = Query(None),
                    district_id: Optional[int] = Query(None, ge=1),
                    limit: int = Query(100, ge=1, le=1000),
                    _role: str = Depends(guards.require_cctv_read)):
    return {"detections": _call(
        service.list_detections, camera_id=camera_id, detection_type=detection_type,
        district_id=district_id, limit=limit)}


@router.post("/analytics/run")
def run_analytics(req: AnalyticsRunRequest, request: Request,
                  role: str = Depends(guards.require_cctv_review),
                  x_idempotency_key: Optional[str] = Header(default=None)):
    """Run one analysis pass over the selected cameras and PROPOSE alerts.

    Never confirms and never dispatches. Re-running inside the same analysis
    window is a no-op (each detection is idempotent on its window key).
    """
    guards.require_cctv_write_allowed(request)
    return _call(service.run_analytics, req.model_dump(), guards.resolve_scope(request),
                 idem_key=(x_idempotency_key or None))


@router.post("/detections/ingest")
def ingest_detections(req: DetectionIngestRequest,
                      _auth: None = Depends(guards.require_ingest_token)):
    """Detection sink for an external/edge video-analytics service.

    Authenticated by the ``X-CCTV-Ingest-Token`` shared secret and DISABLED when
    no secret is configured. Idempotent on ``source_record_id``. An external
    producer can only ever create a PROPOSED alert — never a confirmation and
    never a dispatch.
    """
    return _call(service.ingest_detections, req.model_dump())


# ---------------------------------------------------------------------------
# alert review — confirmation requires a fresh authenticated confirmation
# ---------------------------------------------------------------------------
@router.get("/alerts")
def list_alerts(status: Optional[str] = Query(None),
                district_id: Optional[int] = Query(None, ge=1),
                camera_id: Optional[int] = Query(None, ge=1),
                detection_type: Optional[str] = Query(None),
                min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
                limit: int = Query(200, ge=1, le=1000),
                _role: str = Depends(guards.require_cctv_read)):
    return {"alerts": _call(
        service.list_alerts, status=status, district_id=district_id,
        camera_id=camera_id, detection_type=detection_type,
        min_confidence=min_confidence, limit=limit)}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, _role: str = Depends(guards.require_cctv_read)):
    return _call(service.get_alert, alert_id)


@router.post("/alerts/{alert_id}/confirm")
def confirm_alert(alert_id: int, req: AlertConfirmRequest, request: Request,
                  confirm: bool = Query(False, description="fresh authenticated confirmation"),
                  role: str = Depends(guards.require_cctv_review)):
    """Human confirmation that the detection is real. 428 without a fresh confirm.

    Accepts the flag as either a query param or a body field so the client can use
    whichever is natural; both must agree to a positive confirmation.
    """
    guards.require_cctv_write_allowed(request)
    confirmed = bool(confirm or req.confirm)
    guards.require_fresh_confirmation(confirmed, "confirm CCTV alert")
    return _call(service.confirm_alert, alert_id, guards.resolve_scope(request),
                 confirmed=confirmed, note=req.note,
                 propose_dispatch=req.propose_dispatch,
                 max_distance_km=req.max_distance_km)


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: int, req: AlertDismissRequest, request: Request,
                  role: str = Depends(guards.require_cctv_review)):
    """Record a dismissal with a reason. No fresh-confirmation gate: dismissing is
    the SAFE direction (it sends nobody), and adding friction to it would push
    analysts toward confirming just to clear the queue."""
    guards.require_cctv_write_allowed(request)
    return _call(service.dismiss_alert, alert_id, guards.resolve_scope(request),
                 reason=req.reason, note=req.note)


# ---------------------------------------------------------------------------
# dispatch — 'dispatched' requires its own fresh confirmation
# ---------------------------------------------------------------------------
@router.get("/dispatch")
def list_dispatches(alert_id: Optional[int] = Query(None, ge=1),
                    status: Optional[str] = Query(None),
                    district_id: Optional[int] = Query(None, ge=1),
                    limit: int = Query(200, ge=1, le=1000),
                    _role: str = Depends(guards.require_cctv_read)):
    return {"dispatches": _call(
        service.list_dispatches, alert_id=alert_id, status=status,
        district_id=district_id, limit=limit)}


@router.post("/alerts/{alert_id}/dispatch/propose")
def propose_dispatch(alert_id: int, req: DispatchProposeRequest, request: Request,
                     role: str = Depends(guards.require_cctv_dispatch)):
    """Rank the nearest responders and persist the best as a PROPOSED dispatch.
    Only a confirmed alert may reach here."""
    guards.require_cctv_write_allowed(request)
    return _call(service.propose_dispatch_for_alert, alert_id,
                 guards.resolve_scope(request),
                 max_distance_km=req.max_distance_km,
                 patrol_unit_id=req.patrol_unit_id)


@router.post("/dispatch/{dispatch_id}/transition")
def transition_dispatch(dispatch_id: int, req: DispatchTransitionRequest, request: Request,
                        status: str = Query(...),
                        role: str = Depends(guards.require_cctv_dispatch)):
    guards.require_cctv_write_allowed(request)
    # Sending a unit is the consequential transition -> fresh confirmation.
    if status in service.DISPATCH_CONFIRM_REQUIRED:
        guards.require_fresh_confirmation(req.confirm, f"dispatch {status}")
    return _call(service.transition_dispatch, dispatch_id, status,
                 guards.resolve_scope(request),
                 expected_version=req.expected_version, notes=req.notes)


# ---------------------------------------------------------------------------
# audit + demo estate
# ---------------------------------------------------------------------------
@router.get("/activity")
def activity(limit: int = Query(100, ge=1, le=500),
             _role: str = Depends(guards.require_cctv_read)):
    return {"activity": _call(service.recent_activity, limit=limit)}


@router.post("/demo/seed")
def seed_demo(request: Request, role: str = Depends(guards.require_cctv_admin)):
    """Load the deterministic synthetic camera estate + responders. Idempotent."""
    guards.require_cctv_write_allowed(request)
    return {"seeded": seed_mod.seed_demo_estate(actor=guards.resolve_actor(request))}
