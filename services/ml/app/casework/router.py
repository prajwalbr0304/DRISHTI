"""FastAPI router for casework (Phase 7): statements, property/seizure, lab
results, court events/bail/disposition/outcome, event-backed lifecycle, timeline.

Reuses the intake hackathon guards: reads deny policymaker; writes need an
investigating/registering role + localhost + synthetic-DB; statement/lab review
needs a supervisory role. Restricted statement/lab text is redacted server-side
for roles without sensitive access. Uploaded files are linked by id only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..intake import guards
from . import schemas as S, service
from .service import CaseworkConflict, CaseworkNotFound, CaseworkValidationError

router = APIRouter(prefix="/casework", tags=["casework"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CaseworkNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CaseworkValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except CaseworkConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# --- lookups + timeline -----------------------------------------------------
@router.get("/lookups", response_model=S.CaseworkLookups)
def lookups(_role: str = Depends(guards.require_intake_read)):
    return service.lookups()


@router.get("/cases/{cid}/timeline", response_model=S.TimelineResponse)
def timeline(cid: int, _role: str = Depends(guards.require_intake_read)):
    return _call(service.timeline, cid)


# --- statements -------------------------------------------------------------
@router.get("/cases/{cid}/statements", response_model=S.StatementListResponse)
def list_statements(cid: int, role: str = Depends(guards.require_intake_read)):
    return _call(service.list_statements, cid, role)


@router.post("/cases/{cid}/statements", response_model=S.StatementOut, status_code=201)
def create_statement(cid: int, body: S.StatementCreate,
                     role: str = Depends(guards.require_intake_write),
                     _w=Depends(guards.require_write_allowed)):
    return _call(service.create_statement, cid, body, role)


@router.get("/statements/{sid}", response_model=S.StatementOut)
def get_statement(sid: int, role: str = Depends(guards.require_intake_read)):
    return _call(service.get_statement, sid, role)


@router.put("/statements/{sid}", response_model=S.StatementOut)
def correct_statement(sid: int, body: S.StatementCorrection,
                      role: str = Depends(guards.require_intake_write),
                      _w=Depends(guards.require_write_allowed)):
    return _call(service.correct_statement, sid, body, role)


@router.post("/statements/{sid}/review", response_model=S.StatementOut)
def review_statement(sid: int, body: S.StatementReview | None = None,
                     role: str = Depends(guards.require_intake_review),
                     _w=Depends(guards.require_write_allowed)):
    return _call(service.review_statement, sid, body or S.StatementReview(), role)


# --- property / seizure -----------------------------------------------------
@router.get("/cases/{cid}/seizures", response_model=S.SeizureListResponse)
def list_seizures(cid: int, _role: str = Depends(guards.require_intake_read)):
    return _call(service.list_seizures, cid)


@router.post("/cases/{cid}/seizures", response_model=S.SeizureListResponse, status_code=201)
def create_seizure(cid: int, body: S.SeizureCreate,
                   role: str = Depends(guards.require_intake_write),
                   _w=Depends(guards.require_write_allowed)):
    return _call(service.create_seizure, cid, body, role)


@router.post("/cases/{cid}/property-items", response_model=S.PropertyItemOut, status_code=201)
def add_property_item(cid: int, body: S.PropertyItemInput,
                      seizure_id: int | None = Query(None, ge=1),
                      role: str = Depends(guards.require_intake_write),
                      _w=Depends(guards.require_write_allowed)):
    return _call(service.add_property_item, cid, seizure_id, body, role)


@router.put("/property-items/{pid}/status", response_model=S.PropertyItemOut)
def change_property_status(pid: int, body: S.PropertyStatusChange,
                           role: str = Depends(guards.require_intake_write),
                           _w=Depends(guards.require_write_allowed)):
    return _call(service.change_property_status, pid, body)


# --- lab results ------------------------------------------------------------
@router.get("/cases/{cid}/lab-results", response_model=S.LabResultListResponse)
def list_labs(cid: int, role: str = Depends(guards.require_intake_read)):
    return _call(service.list_labs, cid, role)


@router.post("/cases/{cid}/lab-results", response_model=S.LabResultOut, status_code=201)
def create_lab(cid: int, body: S.LabResultInput,
               role: str = Depends(guards.require_intake_write),
               _w=Depends(guards.require_write_allowed)):
    return _call(service.create_lab, cid, body, role)


@router.put("/lab-results/{lid}", response_model=S.LabResultOut)
def update_lab(lid: int, body: S.LabResultUpdate,
               role: str = Depends(guards.require_intake_write),
               _w=Depends(guards.require_write_allowed)):
    return _call(service.update_lab, lid, body, role)


# --- court / bail / disposition / outcome / lifecycle -----------------------
@router.get("/cases/{cid}/court", response_model=S.CourtLifecycleView)
def court_lifecycle(cid: int, _role: str = Depends(guards.require_intake_read)):
    return _call(service.court_lifecycle, cid)


@router.post("/cases/{cid}/court-events", response_model=S.CourtLifecycleView, status_code=201)
def add_court_event(cid: int, body: S.CourtEventInput,
                    role: str = Depends(guards.require_intake_write),
                    _w=Depends(guards.require_write_allowed)):
    return _call(service.add_court_event, cid, body, role)


@router.post("/cases/{cid}/bail", response_model=S.CourtLifecycleView, status_code=201)
def add_bail(cid: int, body: S.BailInput,
             role: str = Depends(guards.require_intake_write),
             _w=Depends(guards.require_write_allowed)):
    return _call(service.add_bail, cid, body, role)


@router.post("/cases/{cid}/disposition", response_model=S.CourtLifecycleView, status_code=201)
def add_disposition(cid: int, body: S.DispositionInput,
                    role: str = Depends(guards.require_intake_review),
                    _w=Depends(guards.require_write_allowed)):
    return _call(service.add_disposition, cid, body, role)


@router.post("/cases/{cid}/outcome", response_model=S.CourtLifecycleView, status_code=201)
def add_outcome(cid: int, body: S.OutcomeInput,
                role: str = Depends(guards.require_intake_review),
                _w=Depends(guards.require_write_allowed)):
    return _call(service.add_outcome, cid, body, role)


@router.post("/cases/{cid}/lifecycle-events", response_model=S.LifecycleEventResult, status_code=201)
def add_lifecycle_event(cid: int, body: S.LifecycleEventInput,
                        role: str = Depends(guards.require_intake_write),
                        _w=Depends(guards.require_write_allowed),
                        _g=Depends(guards.require_submit_enabled)):
    return _call(service.add_lifecycle_event, cid, body, role)
