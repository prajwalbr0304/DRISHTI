"""FastAPI router for the Emergency Response context (Prompt 17 §A/§F/§G/§H).

Reads: any authenticated role (crime roles are read-only situational view).
Writes: the synthetic ``disaster_coordinator`` (or super_admin) with the
``disaster_forecast`` / ``resource_allocation`` / ``evacuation_plan`` permission,
scoped to the assigned district. Warning approval, dispatch and evacuation-plan
approval require a fresh authenticated confirmation (confirm=true -> else 428).

Errors are mapped to HTTP without leaking internals. Every mutating route runs
the synthetic write-posture guard.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from . import guards, seed as seed_mod, service
from .schemas import (AlertProposeRequest, AllocationPlanRequest,
                      AllocationTransitionRequest, EvacRouteRequest,
                      ForecastRunRequest, HazardEventCreate, ResourceCreate,
                      ResponsePlanCreate, ShelterCreate, TaskPatch)

router = APIRouter(prefix="/disaster", tags=["emergency-response"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.DisasterNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except service.DisasterForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except service.DisasterValidation as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except service.DisasterConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ---------------------------------------------------------------------------
# reads (situational view) — any authenticated role
# ---------------------------------------------------------------------------
@router.get("/hazard-types")
def hazard_types(_role: str = Depends(guards.require_disaster_read)):
    return {"hazard_types": service.list_hazard_types()}


@router.get("/overview")
def overview(district_id: Optional[int] = Query(None, ge=1),
             _role: str = Depends(guards.require_disaster_read)):
    return service.situation_overview(district_id=district_id)


@router.get("/events")
def events(status: Optional[str] = Query(None), district_id: Optional[int] = Query(None, ge=1),
           _role: str = Depends(guards.require_disaster_read)):
    return {"events": service.list_events(status=status, district_id=district_id)}


@router.get("/events/{event_id}")
def event(event_id: int, _role: str = Depends(guards.require_disaster_read)):
    return _call(service.get_event, event_id)


@router.get("/zones")
def zones(hazard_code: Optional[str] = Query(None), district_id: Optional[int] = Query(None, ge=1),
          _role: str = Depends(guards.require_disaster_read)):
    return {"zones": service.list_zones(hazard_code=hazard_code, district_id=district_id)}


@router.get("/predictions")
def predictions(hazard_code: Optional[str] = Query(None), district_id: Optional[int] = Query(None, ge=1),
                _role: str = Depends(guards.require_disaster_read)):
    return {"predictions": service.list_predictions(hazard_code=hazard_code, district_id=district_id)}


@router.get("/readings")
def readings(district_id: Optional[int] = Query(None, ge=1), metric: Optional[str] = Query(None),
             _role: str = Depends(guards.require_disaster_read)):
    return {"readings": service.list_readings(district_id=district_id, metric=metric)}


@router.get("/feeds/freshness")
def feeds_freshness(_role: str = Depends(guards.require_disaster_read)):
    return {"feeds": service.feed_freshness()}


@router.get("/resources")
def resources(district_id: Optional[int] = Query(None, ge=1), status: Optional[str] = Query(None),
              _role: str = Depends(guards.require_disaster_read)):
    return {"resources": service.list_resources(district_id=district_id, status=status)}


@router.get("/shelters")
def shelters(district_id: Optional[int] = Query(None, ge=1),
             _role: str = Depends(guards.require_disaster_read)):
    return {"shelters": service.list_shelters(district_id=district_id)}


@router.get("/allocations")
def allocations(event_id: Optional[int] = Query(None, ge=1), district_id: Optional[int] = Query(None, ge=1),
                _role: str = Depends(guards.require_disaster_read)):
    return {"allocations": service.list_allocations(event_id=event_id, district_id=district_id)}


@router.get("/routes")
def routes(event_id: Optional[int] = Query(None, ge=1),
           _role: str = Depends(guards.require_disaster_read)):
    return {"routes": service.list_routes(event_id=event_id)}


@router.get("/alerts")
def alerts(district_id: Optional[int] = Query(None, ge=1),
           _role: str = Depends(guards.require_disaster_read)):
    return {"alerts": service.list_alerts(district_id=district_id)}


@router.get("/plans")
def plans(district_id: Optional[int] = Query(None, ge=1),
          _role: str = Depends(guards.require_disaster_read)):
    return {"plans": service.list_plans(district_id=district_id)}


@router.get("/plans/{plan_id}")
def plan(plan_id: int, _role: str = Depends(guards.require_disaster_read)):
    return _call(service.get_plan, plan_id)


@router.get("/forecast/validate")
def forecast_validate(hazard_code: str = Query("flood"),
                      n_origins: int = Query(120, ge=20, le=1000),
                      _role: str = Depends(guards.require_disaster_read)):
    return _call(service.validate_forecast, hazard_code, n_origins=n_origins)


# ---------------------------------------------------------------------------
# demo seed
# ---------------------------------------------------------------------------
@router.post("/demo/seed")
def demo_seed(request: Request, role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    return {"seeded": seed_mod.seed_from_fixture()}


# ---------------------------------------------------------------------------
# feeds
# ---------------------------------------------------------------------------
@router.post("/feeds/{feed_code}/ingest")
def feed_ingest(feed_code: str, request: Request, body: Optional[dict] = None,
                role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    readings = (body or {}).get("readings") if isinstance(body, dict) else None
    return _call(service.ingest_feed, feed_code, readings=readings,
                 actor=guards.resolve_actor(request))


# ---------------------------------------------------------------------------
# hazard events
# ---------------------------------------------------------------------------
@router.post("/events", status_code=201)
def create_event(req: HazardEventCreate, request: Request,
                 role: str = Depends(guards.require_disaster_forecast),
                 x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_disaster_write_allowed(request)
    return _call(service.create_event, req.model_dump(), guards.resolve_scope(request),
                 idem_key=(x_idempotency_key or None))


@router.post("/events/{event_id}/transition")
def transition_event(event_id: int, request: Request, status: str = Query(...),
                     expected_version: Optional[int] = Query(None),
                     role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    return _call(service.transition_event, event_id, status, guards.resolve_scope(request),
                 expected_version=expected_version)


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------
@router.post("/forecast/run")
def forecast_run(req: ForecastRunRequest, request: Request,
                 role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    return _call(service.run_forecast, req.hazard_code, req.district_id,
                 horizon_hours=req.horizon_hours, data_as_of=req.data_as_of,
                 create_event_proposal=req.create_event_proposal,
                 scope=guards.resolve_scope(request), actor=guards.resolve_actor(request))


# ---------------------------------------------------------------------------
# alerts (reuse AlertHistory) — approval requires fresh confirmation
# ---------------------------------------------------------------------------
@router.post("/alerts/propose", status_code=201)
def alert_propose(req: AlertProposeRequest, request: Request,
                  role: str = Depends(guards.require_disaster_forecast),
                  x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_disaster_write_allowed(request)
    return _call(service.propose_alert, req.model_dump(), guards.resolve_scope(request),
                 idem_key=(x_idempotency_key or None))


@router.post("/alerts/{alert_id}/approve")
def alert_approve(alert_id: int, request: Request,
                  confirm: bool = Query(False, description="fresh authenticated confirmation"),
                  role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    guards.require_fresh_confirmation(confirm, "approve warning")
    return _call(service.approve_alert, alert_id, guards.resolve_scope(request), confirmed=confirm)


# ---------------------------------------------------------------------------
# resources + shelters
# ---------------------------------------------------------------------------
@router.post("/resources", status_code=201)
def create_resource(req: ResourceCreate, request: Request,
                    role: str = Depends(guards.require_resource_allocation)):
    guards.require_disaster_write_allowed(request)
    return _call(service.create_resource, req.model_dump(), guards.resolve_scope(request))


@router.post("/shelters", status_code=201)
def create_shelter(req: ShelterCreate, request: Request,
                   role: str = Depends(guards.require_resource_allocation)):
    guards.require_disaster_write_allowed(request)
    return _call(service.create_shelter, req.model_dump(), guards.resolve_scope(request))


# ---------------------------------------------------------------------------
# allocation
# ---------------------------------------------------------------------------
@router.post("/allocations/propose")
def allocation_propose(req: AllocationPlanRequest, request: Request,
                       role: str = Depends(guards.require_resource_allocation)):
    guards.require_disaster_write_allowed(request)
    return _call(service.propose_allocation, req.hazard_event_id, req.required,
                 guards.resolve_scope(request), max_distance_km=req.max_distance_km,
                 optimizer=req.optimizer)


@router.post("/allocations/{alloc_id}/transition")
def allocation_transition(alloc_id: int, req: AllocationTransitionRequest, request: Request,
                          status: str = Query(...),
                          role: str = Depends(guards.require_resource_allocation)):
    guards.require_disaster_write_allowed(request)
    # dispatch + approve are the sensitive transitions -> fresh confirmation.
    if status in ("approved", "dispatched"):
        guards.require_fresh_confirmation(req.confirm, f"allocation {status}")
    return _call(service.transition_allocation, alloc_id, status,
                 guards.resolve_scope(request), expected_version=req.expected_version)


# ---------------------------------------------------------------------------
# evacuation routing — plan approval requires fresh confirmation
# ---------------------------------------------------------------------------
@router.post("/routes/propose")
def route_propose(req: EvacRouteRequest, request: Request,
                  role: str = Depends(guards.require_evacuation_plan)):
    guards.require_disaster_write_allowed(request)
    return _call(service.propose_route, req.hazard_event_id, guards.resolve_scope(request),
                 from_zone_id=req.from_zone_id, to_shelter_id=req.to_shelter_id)


@router.post("/routes/{route_id}/select")
def route_select(route_id: int, request: Request,
                 confirm: bool = Query(False, description="fresh authenticated confirmation"),
                 role: str = Depends(guards.require_evacuation_plan)):
    guards.require_disaster_write_allowed(request)
    guards.require_fresh_confirmation(confirm, "approve evacuation plan")
    return _call(service.select_route, route_id, guards.resolve_scope(request), confirmed=confirm)


# ---------------------------------------------------------------------------
# response plans + tasks
# ---------------------------------------------------------------------------
@router.post("/plans", status_code=201)
def create_plan(req: ResponsePlanCreate, request: Request,
                role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    return _call(service.create_plan, req.model_dump(), guards.resolve_scope(request))


@router.patch("/tasks/{task_id}")
def patch_task(task_id: int, req: TaskPatch, request: Request,
               role: str = Depends(guards.require_disaster_forecast)):
    guards.require_disaster_write_allowed(request)
    return _call(service.patch_task, task_id, req.model_dump(), guards.resolve_scope(request))
