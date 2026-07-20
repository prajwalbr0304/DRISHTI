"""FastAPI router for FIR/case structured intake (Phase 2).

Endpoints (prefix /intake):
  GET    /intake/status                         — hackathon flags (drives UI submit gate)
  GET    /intake/lookups                         — reference/options for the wizard
  GET    /intake/workflow                         — kinds + statuses + transition metadata
  POST   /intake/geo/resolve                       — jurisdiction/containment for a point
  GET    /intake/drafts                             — intake inbox (filter/paginate)
  POST   /intake/drafts                             — create draft (idempotent)
  GET    /intake/drafts/{key}                        — get draft
  PUT    /intake/drafts/{key}                        — update/autosave draft
  POST   /intake/drafts/{key}/validate               — validate (errors vs warnings)
  POST   /intake/drafts/{key}/duplicate-check         — duplicate/source-key candidates
  GET    /intake/drafts/{key}/activity                — draft activity/review trail
  POST   /intake/drafts/{key}/parties                 — add case-party role
  PUT    /intake/drafts/{key}/parties/{party_id}       — update party
  DELETE /intake/drafts/{key}/parties/{party_id}       — remove party
  POST   /intake/drafts/{key}/submit                   — submit for review  (submit-gated)
  POST   /intake/drafts/{key}/review                    — approve/reject/return (submit-gated)
  POST   /intake/cases/{case_id}/events                  — workflow-gated case event (submit-gated)

Writes are localhost + synthetic-DB guarded; the canonical case-creating
transitions (submit/review/events) are additionally behind the submit gate until
Prompt 3 finalises hackathon mode.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import guards, lookups, service
from .schemas import (ApprovalResult, CaseEventRequest, CaseEventResponse,
                      CasePartyListResponse, CreateDraftRequest, DataQualityListResponse,
                      DraftActivity, DraftListResponse, DraftResponse,
                      DuplicateCheckResponse, IntakeStatusResponse, JurisdictionInfo,
                      LookupsResponse, PartyInput, ReviewRequest, SubmitRequest,
                      UpdateDraftRequest, ValidationResponse, WorkflowMetaResponse)
from .service import IntakeConflict, IntakeNotFound, IntakeValidationError

router = APIRouter(prefix="/intake", tags=["intake"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, IntakeNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, IntakeValidationError):
        detail = {"message": str(exc), "validation": exc.validation} if exc.validation else str(exc)
        return HTTPException(status_code=422, detail=detail)
    if isinstance(exc, IntakeConflict):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (IntakeNotFound, IntakeConflict, IntakeValidationError) as exc:
        raise _translate(exc)


class GeoResolveRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    assigned_district_id: Optional[int] = None


class DuplicateCheckBody(BaseModel):
    external_source_id: Optional[str] = None


# --- status + reference -----------------------------------------------------
@router.get("/status", response_model=IntakeStatusResponse)
def intake_status(_role: str = Depends(guards.require_intake_read)):
    return guards.hackathon_status()


@router.get("/lookups", response_model=LookupsResponse)
def intake_lookups(unit_id: Optional[int] = Query(None, ge=1),
                   _role: str = Depends(guards.require_intake_read)):
    return lookups.reference_lookups(unit_id=unit_id)


@router.get("/workflow", response_model=WorkflowMetaResponse)
def intake_workflow(_role: str = Depends(guards.require_intake_read)):
    return lookups.workflow_metadata()


@router.get("/quality/issues", response_model=DataQualityListResponse)
def quality_issues(status: Optional[str] = Query(None), severity: Optional[str] = Query(None),
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   _role: str = Depends(guards.require_intake_read)):
    return service.list_quality_issues(status, severity, page, page_size)


@router.post("/geo/resolve", response_model=JurisdictionInfo)
def geo_resolve(body: GeoResolveRequest, _role: str = Depends(guards.require_intake_read)):
    return service.resolve_jurisdiction(body.latitude, body.longitude, body.assigned_district_id)


# --- drafts -----------------------------------------------------------------
@router.get("/drafts", response_model=DraftListResponse)
def list_drafts(status: Optional[str] = Query(None), case_kind: Optional[str] = Query(None),
                page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                _role: str = Depends(guards.require_intake_read)):
    return service.list_drafts(status, case_kind, page, page_size)


@router.post("/drafts", response_model=DraftResponse, status_code=201)
def create_draft(body: CreateDraftRequest,
                 _role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.create_draft, body)


@router.get("/drafts/{draft_key}", response_model=DraftResponse)
def get_draft(draft_key: str, _role: str = Depends(guards.require_intake_read)):
    return _call(service.get_draft, draft_key)


@router.put("/drafts/{draft_key}", response_model=DraftResponse)
def update_draft(draft_key: str, body: UpdateDraftRequest,
                 _role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.update_draft, draft_key, body)


@router.post("/drafts/{draft_key}/validate", response_model=ValidationResponse)
def validate_draft(draft_key: str,
                   _role: str = Depends(guards.require_intake_write),
                   _w=Depends(guards.require_write_allowed)):
    return _call(service.validate_draft, draft_key)


@router.post("/drafts/{draft_key}/duplicate-check", response_model=DuplicateCheckResponse)
def duplicate_check(draft_key: str, body: DuplicateCheckBody | None = None,
                    _role: str = Depends(guards.require_intake_read)):
    return _call(service.duplicate_check, (body.external_source_id if body else None), draft_key)


@router.get("/drafts/{draft_key}/activity", response_model=list[DraftActivity])
def draft_activity(draft_key: str, _role: str = Depends(guards.require_intake_read)):
    return _call(service.draft_activity, draft_key)


# --- parties ----------------------------------------------------------------
@router.post("/drafts/{draft_key}/parties", response_model=DraftResponse, status_code=201)
def add_party(draft_key: str, body: PartyInput,
              role: str = Depends(guards.require_intake_write),
              _w=Depends(guards.require_write_allowed)):
    return _call(service.add_party, draft_key, body, role)


@router.put("/drafts/{draft_key}/parties/{party_id}", response_model=DraftResponse)
def update_party(draft_key: str, party_id: int, body: PartyInput,
                 role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.update_party, draft_key, party_id, body, role)


@router.delete("/drafts/{draft_key}/parties/{party_id}", response_model=DraftResponse)
def remove_party(draft_key: str, party_id: int,
                 role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.remove_party, draft_key, party_id, role)


# --- submit / review / events (submit-gated) --------------------------------
@router.post("/drafts/{draft_key}/submit", response_model=DraftResponse)
def submit_draft(draft_key: str, body: SubmitRequest | None = None,
                 role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed),
                 _g=Depends(guards.require_submit_enabled)):
    actor = body.actor if body else None
    return _call(service.submit_draft, draft_key, actor)


@router.post("/drafts/{draft_key}/review")
def review_draft(draft_key: str, action: str = Query(..., pattern="^(approve|reject|return)$"),
                 body: ReviewRequest | None = None,
                 role: str = Depends(guards.require_intake_review),
                 _w=Depends(guards.require_write_allowed),
                 _g=Depends(guards.require_submit_enabled)):
    actor = body.actor if body else None
    note = body.note if body else None
    result = _call(service.review_draft, draft_key, action, actor, note)
    # approve returns ApprovalResult; reject/return return DraftResponse
    if isinstance(result, ApprovalResult):
        # Prompt 20 §E — the approved canonical write is committed; emit the
        # committed-FIR event so the Live Command Center projections refresh.
        # Best-effort: a flow failure must never break the approval response.
        try:
            import datetime as _dt
            from ..livefeed import flow as _livefeed
            _livefeed.on_fir_committed(
                result.case_master_id,
                source_ts=_dt.datetime.now(_dt.timezone.utc).isoformat())
        except Exception:  # noqa: BLE001
            pass
        return result
    return {"draft": result}


@router.get("/cases/{case_id}/parties", response_model=CasePartyListResponse)
def case_parties(case_id: int, _role: str = Depends(guards.require_intake_read)):
    return service.list_case_parties(case_id)


@router.post("/cases/{case_id}/events", response_model=CaseEventResponse)
def create_case_event(case_id: int, body: CaseEventRequest,
                      role: str = Depends(guards.require_intake_write),
                      _w=Depends(guards.require_write_allowed),
                      _g=Depends(guards.require_submit_enabled)):
    return _call(service.add_case_event, case_id, body.event_type,
                 body.occurred_at, body.actor_role or role, body.payload)
