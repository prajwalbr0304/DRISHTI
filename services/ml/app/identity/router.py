"""FastAPI router for canonical identity + entity resolution (Phase 4).

Endpoints (prefix /identity). Reads use the read-only role; writes are localhost
+ synthetic-DB guarded (Phase 3 hackathon access mode). The X-Role/X-Demo-Actor
headers are presentation/audit only, NOT authentication.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..intake import guards
from . import schemas as S, service
from .service import IdentityConflict, IdentityNotFound, IdentityValidationError

router = APIRouter(prefix="/identity", tags=["identity"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except IdentityNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IdentityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except IdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# --- stats ------------------------------------------------------------------
@router.get("/stats")
def identity_stats(_role: str = Depends(guards.require_intake_read)):
    return service.link_stats()


# --- persons ----------------------------------------------------------------
@router.get("/persons", response_model=S.PersonSearchResponse)
def search_persons(q: Optional[str] = Query(None), gender_id: Optional[int] = Query(None),
                   juvenile: Optional[bool] = Query(None), status: Optional[str] = Query(None),
                   page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                   _role: str = Depends(guards.require_intake_read)):
    return service.search_persons(q, gender_id, juvenile, status, page, page_size)


@router.get("/persons/{cpid}", response_model=S.PersonDetail)
def get_person(cpid: int, _role: str = Depends(guards.require_intake_read)):
    return _call(service.get_person, cpid)


@router.post("/persons", response_model=S.PersonDetail, status_code=201)
def create_person(body: S.CreatePersonRequest,
                  _role: str = Depends(guards.require_intake_write),
                  _w=Depends(guards.require_write_allowed)):
    return _call(service.create_person, body)


@router.patch("/persons/{cpid}", response_model=S.PersonDetail)
def update_person(cpid: int, body: S.UpdatePersonRequest,
                  _role: str = Depends(guards.require_intake_write),
                  _w=Depends(guards.require_write_allowed)):
    return _call(service.update_person, cpid, body)


# --- person attributes (with sensitivity) -----------------------------------
@router.post("/persons/{cpid}/aliases", response_model=S.PersonDetail, status_code=201)
def add_alias(cpid: int, body: S.AliasInput,
              _role: str = Depends(guards.require_intake_write),
              _w=Depends(guards.require_write_allowed)):
    return _call(service.add_alias, cpid, body)


@router.delete("/persons/{cpid}/aliases/{row_id}", response_model=S.PersonDetail)
def delete_alias(cpid: int, row_id: int,
                 _role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.delete_alias, cpid, row_id)


@router.post("/persons/{cpid}/identifiers", response_model=S.PersonDetail, status_code=201)
def add_identifier(cpid: int, body: S.IdentifierInput,
                   _role: str = Depends(guards.require_intake_write),
                   _w=Depends(guards.require_write_allowed)):
    return _call(service.add_identifier, cpid, body)


@router.delete("/persons/{cpid}/identifiers/{row_id}", response_model=S.PersonDetail)
def delete_identifier(cpid: int, row_id: int,
                      _role: str = Depends(guards.require_intake_write),
                      _w=Depends(guards.require_write_allowed)):
    return _call(service.delete_identifier, cpid, row_id)


@router.post("/persons/{cpid}/contacts", response_model=S.PersonDetail, status_code=201)
def add_contact(cpid: int, body: S.ContactInput,
                _role: str = Depends(guards.require_intake_write),
                _w=Depends(guards.require_write_allowed)):
    return _call(service.add_contact, cpid, body)


@router.delete("/persons/{cpid}/contacts/{row_id}", response_model=S.PersonDetail)
def delete_contact(cpid: int, row_id: int,
                   _role: str = Depends(guards.require_intake_write),
                   _w=Depends(guards.require_write_allowed)):
    return _call(service.delete_contact, cpid, row_id)


@router.post("/persons/{cpid}/addresses", response_model=S.PersonDetail, status_code=201)
def add_address(cpid: int, body: S.AddressInput,
                _role: str = Depends(guards.require_intake_write),
                _w=Depends(guards.require_write_allowed)):
    return _call(service.add_address, cpid, body)


@router.delete("/persons/{cpid}/addresses/{row_id}", response_model=S.PersonDetail)
def delete_address(cpid: int, row_id: int,
                   _role: str = Depends(guards.require_intake_write),
                   _w=Depends(guards.require_write_allowed)):
    return _call(service.delete_address, cpid, row_id)


# --- organisations ----------------------------------------------------------
@router.get("/organisations", response_model=S.OrgSearchResponse)
def search_orgs(q: Optional[str] = Query(None), page: int = Query(1, ge=1),
                page_size: int = Query(25, ge=1, le=100),
                _role: str = Depends(guards.require_intake_read)):
    return service.search_orgs(q, page, page_size)


@router.post("/organisations", response_model=S.OrgSummary, status_code=201)
def create_org(body: S.CreateOrgRequest,
               _role: str = Depends(guards.require_intake_write),
               _w=Depends(guards.require_write_allowed)):
    return _call(service.create_org, body)


# --- case-party roles -------------------------------------------------------
@router.post("/cases/{case_id}/parties", response_model=S.PartyMutationResponse, status_code=201)
def add_party(case_id: int, body: S.AddPartyRequest,
              _role: str = Depends(guards.require_intake_write),
              _w=Depends(guards.require_write_allowed)):
    return _call(service.add_party, case_id, body)


@router.patch("/parties/{role_id}", response_model=S.PartyMutationResponse)
def update_party(role_id: int, body: S.UpdatePartyRequest,
                 _role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.update_party, role_id, body)


@router.delete("/parties/{role_id}")
def remove_party(role_id: int, _role: str = Depends(guards.require_intake_write),
                 _w=Depends(guards.require_write_allowed)):
    return _call(service.remove_party, role_id)


# --- entity resolution ------------------------------------------------------
@router.get("/resolution/candidates", response_model=S.CandidateListResponse)
def list_candidates(status: Optional[str] = Query("pending"),
                    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                    _role: str = Depends(guards.require_intake_read)):
    return service.list_candidates(status, page, page_size)


@router.post("/resolution/generate", response_model=S.GenerateCandidatesResponse)
def generate_candidates(body: S.GenerateCandidatesRequest,
                        _role: str = Depends(guards.require_intake_write),
                        _w=Depends(guards.require_write_allowed)):
    return _call(service.generate_candidates, body)


@router.post("/resolution/candidates/{cand_id}/review")
def review_candidate(cand_id: int, body: S.ReviewCandidateRequest,
                     _role: str = Depends(guards.require_intake_review),
                     _w=Depends(guards.require_write_allowed)):
    return _call(service.review_candidate, cand_id, body)


# --- merge / unmerge --------------------------------------------------------
@router.post("/persons/{cpid}/merge", response_model=S.MergeResult)
def merge_persons(cpid: int, body: S.MergeRequest,
                  _role: str = Depends(guards.require_intake_review),
                  _w=Depends(guards.require_write_allowed)):
    return _call(service.merge_persons, cpid, body)


@router.post("/persons/{cpid}/unmerge", response_model=S.MergeResult)
def unmerge_persons(cpid: int, body: S.UnmergeRequest,
                    _role: str = Depends(guards.require_intake_review),
                    _w=Depends(guards.require_write_allowed)):
    return _call(service.unmerge_persons, cpid, body)
