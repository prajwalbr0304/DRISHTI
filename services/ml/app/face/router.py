"""FastAPI router for facial recognition (prefix /face).

Authorization posture matches the rest of the service: the X-Role / X-Demo-Actor
headers are presentation/audit inputs, NOT authentication (the API Gateway strips
them and derives the real identity), so every gate below is enforced server-side
as defence in depth.

Note that SEARCH is a write-guarded endpoint even though it reads. A biometric
query writes its own audit row (``FaceSearchProbe``) in the same transaction, and
"who searched for whom" is exactly the record that must exist for this capability
to be defensible. Enrolment and probe decisions are additionally review-gated.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..intake import guards
from ..request_context import current_context
from . import schemas as S, service
from .service import (FaceDisabled, FaceEngineUnavailable, FaceGalleryUnavailable,
                      FaceInputError, FaceNotFound, FaceServiceError)

router = APIRouter(prefix="/face", tags=["face"])


def _call(fn, *args, **kwargs):
    """Map typed service failures onto honest HTTP codes."""
    try:
        return fn(*args, **kwargs)
    except FaceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FaceInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except FaceGalleryUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (FaceDisabled, FaceEngineUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FaceServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _actor(explicit: Optional[str], header: Optional[str], role: str) -> str:
    """Demo actor for the audit trail (display/audit only, never authentication)."""
    ctx = current_context()
    return (explicit or header or (ctx.actor if ctx else None) or f"demo.{role}")


def _request_id() -> Optional[str]:
    ctx = current_context()
    return getattr(ctx, "request_id", None) if ctx else None


# --- status -----------------------------------------------------------------
@router.get("/status", response_model=S.FaceStatusResponse)
def face_status(_role: str = Depends(guards.require_intake_read)):
    """Engine, model-weight presence, gallery size and probe counts.

    Never fails on a missing engine — the UI needs a truthful "not ready, and
    here is why" so it can disable the scan button with a reason instead of
    presenting a control that errors.
    """
    return service.status()


# --- search -----------------------------------------------------------------
@router.post("/search", response_model=S.FaceSearchResponse)
def face_search(body: S.FaceSearchRequest, _request: Request,
                x_demo_actor: Optional[str] = Header(default=None),
                role: str = Depends(guards.require_intake_read),
                _w=Depends(guards.require_write_allowed)):
    """1:N search of a probe photo against the enrolled person gallery.

    Returns a ranked shortlist with each hit's record dossier. ``matched`` is true
    only when the top hit clears the model's threshold, and even then the result is
    a lead for human confirmation — never an identification.
    """
    return _call(service.search, body,
                 actor=_actor(body.actor, x_demo_actor, role), role=role,
                 request_id=_request_id())


# --- gallery ----------------------------------------------------------------
@router.post("/enrol", response_model=S.FaceEnrolResponse, status_code=201)
def face_enrol(body: S.FaceEnrolRequest,
               x_demo_actor: Optional[str] = Header(default=None),
               role: str = Depends(guards.require_intake_write),
               _w=Depends(guards.require_write_allowed)):
    """Add a reference photo to a canonical person's gallery.

    Rejects a photo with no detectable face or with quality below the encoder's
    enrolment floor: a weak reference image degrades matching for every subsequent
    search, not just this person's.
    """
    return _call(service.enrol, body,
                 actor=_actor(body.actor, x_demo_actor, role), role=role)


@router.get("/persons/{cpid}/faces", response_model=S.FaceListResponse)
def list_faces(cpid: int, _role: str = Depends(guards.require_intake_read)):
    """Reference photos enrolled for one person (metadata only, never vectors)."""
    return _call(service.person_faces, cpid)


@router.delete("/faces/{face_id}", response_model=S.FaceDeleteResponse)
def delete_face(face_id: int, reason: Optional[str] = Query(None, max_length=200),
                x_demo_actor: Optional[str] = Header(default=None),
                role: str = Depends(guards.require_intake_write),
                _w=Depends(guards.require_write_allowed)):
    """Retire a reference photo. Archived rather than deleted: a descriptor that
    was once searchable stays reconstructible for audit."""
    return _call(service.remove_face, face_id,
                 actor=_actor(None, x_demo_actor, role), reason=reason)


# --- probe decision + trail -------------------------------------------------
@router.post("/probes/{probe_ref}/decision", response_model=S.FaceDecisionResponse)
def decide_probe(probe_ref: str, body: S.FaceDecisionRequest,
                 x_demo_actor: Optional[str] = Header(default=None),
                 role: str = Depends(guards.require_intake_review),
                 _w=Depends(guards.require_write_allowed)):
    """Record the officer's disposition of a shortlist.

    Confirming links nothing by force: when the record already carries a different
    identity, a face-method EntityResolutionCandidate is raised for review and both
    records are left intact.
    """
    return _call(service.decide, probe_ref, body,
                 actor=_actor(body.actor, x_demo_actor, role))


@router.get("/probes", response_model=S.FaceProbeTrailResponse)
def probe_trail(limit: int = Query(25, ge=1, le=200),
                intake_draft_key: Optional[str] = Query(None, max_length=120),
                _role: str = Depends(guards.require_intake_read)):
    """The biometric-search audit trail: who searched, what matched, what was decided."""
    return _call(service.probe_trail, limit=limit, intake_draft_key=intake_draft_key)
