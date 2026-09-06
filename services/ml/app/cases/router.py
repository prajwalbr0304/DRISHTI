"""FastAPI router for the Cases destination.

Phase 10 (AI decision-support):
  GET  /cases/{id}/similar  — live semantic similar-case search (read-only)
  POST /cases/{id}/summary  — generate + WRITE a fully-cited AISummary
  POST /cases/{id}/leads    — generate + WRITE ranked OfficerRecommendation leads

Phase 15c (Case Explorer + Case file, raw operational reads):
  GET  /cases               — filterable, paginated case index
  GET  /cases/filters       — reference values for the filter rail
  GET  /cases/{id}/detail   — full case (overview, people, sections, timeline)
  GET  /cases/{id}/network  — case-centric mini graph (co-accused + linked cases)
  GET  /cases/{id}/evidence — evidence feed
  POST /cases/{id}/evidence — add evidence (IO only)

Individual case files pass the cases role gate (see cases/permissions.py).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..org.deps import GeoScope, geo_scope, require_case_level
from ..org.scope import ScopeContext
from . import explorer, service
from .permissions import require_case_read, require_case_write
from .schemas import (CaseDetailResponse, CaseListResponse, CaseloadResponse,
                      CaseNetworkResponse, EvidenceCreateRequest, EvidenceCreateResponse,
                      EvidenceListResponse, FilterOptionsResponse, LeadsResponse,
                      SimilarResponse, SummaryResponse)

router = APIRouter(prefix="/cases", tags=["cases"])


# --- Explorer (list + filters) ---------------------------------------------
@router.get("", response_model=CaseListResponse)
def list_cases(
    q: Optional[str] = Query(None, description="free text over CrimeNo / CaseNo / brief facts"),
    major_head_id: Optional[int] = Query(None, ge=1),
    minor_head_id: Optional[int] = Query(None, ge=1),
    status_id: Optional[int] = Query(None, ge=1),
    gravity_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    has_arrest: bool = False,
    has_chargesheet: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _role: str = Depends(require_case_read),
    _seat: ScopeContext = Depends(require_case_level),
    geo: GeoScope = Depends(geo_scope),
):
    """Filterable, paginated case index, CONFINED to the caller's jurisdiction.

    `district_id` / `station_id` come from the `geo_scope` dependency rather than
    being accepted raw: they can only narrow within the seat's own scope, and an
    out-of-scope value is a 403. Omitting them narrows to the seat's jurisdiction
    rather than returning every case in the state.
    """
    filters = {
        "q": q,
        "district_id": geo.district_id, "station_id": geo.unit_id,
        "district_ids": geo.district_ids,
        "major_head_id": major_head_id, "minor_head_id": minor_head_id,
        "status_id": status_id, "gravity_id": gravity_id,
        "date_from": date_from, "date_to": date_to,
        "has_arrest": has_arrest, "has_chargesheet": has_chargesheet,
    }
    return explorer.list_cases(filters, page, page_size)


@router.get("/filters", response_model=FilterOptionsResponse)
def case_filters(_role: str = Depends(require_case_read)):
    return explorer.filter_options()


@router.get("/caseload", response_model=CaseloadResponse)
def caseload(
    major_head_id: Optional[int] = Query(None, ge=1),
    minor_head_id: Optional[int] = Query(None, ge=1),
    gravity_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _role: str = Depends(require_case_read),
    geo: GeoScope = Depends(geo_scope),
):
    """Per-stage caseload counts for the Command Center 'My caseload' pipeline.

    A present-state snapshot: each case falls into exactly one lifecycle stage,
    so the stage counts sum to the total. CONFINED to the caller's jurisdiction by
    the geo_scope dependency.

    Unlike the case index this is an AGGREGATE, so it is available to state and
    wing seats — counts by stage disclose no individual record.
    """
    filters = {
        "district_id": geo.district_id, "station_id": geo.unit_id,
        "district_ids": geo.district_ids,
        "major_head_id": major_head_id, "minor_head_id": minor_head_id,
        "gravity_id": gravity_id, "date_from": date_from, "date_to": date_to,
    }
    return explorer.caseload_summary(filters)


# --- AI decision-support (Phase 10) -----------------------------------------
@router.get("/{case_id}/similar", response_model=SimilarResponse)
def similar(case_id: int, k: int = Query(5, ge=1, le=20, description="neighbours to return"),
            scope: str = Query("district", pattern="^(district|all)$",
                               description="demo case/unit context filter applied before ANN"),
            district_id: Optional[int] = Query(None, ge=1, description="override the demo-context district"),
            _role: str = Depends(require_case_read)):
    resp = service.similar_cases(case_id, k=k, scope=scope, district_id=district_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    if resp is service.NO_CORPUS:
        raise HTTPException(
            status_code=409,
            detail="Case-embedding corpus is empty. Run `python -m app.batch embed-cases` first.")
    return resp


@router.post("/{case_id}/summary", response_model=SummaryResponse)
def summary(case_id: int, _role: str = Depends(require_case_read)):
    resp = service.case_summary(case_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return resp


@router.post("/{case_id}/leads", response_model=LeadsResponse)
def leads(case_id: int, _role: str = Depends(require_case_read)):
    resp = service.case_leads(case_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return resp


# --- Case file (Phase 15c raw reads) ----------------------------------------
@router.get("/{case_id}/detail", response_model=CaseDetailResponse)
def case_detail(case_id: int, _role: str = Depends(require_case_read)):
    resp = explorer.case_detail(case_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return resp


@router.get("/{case_id}/network", response_model=CaseNetworkResponse)
def case_network(case_id: int, _role: str = Depends(require_case_read)):
    resp = explorer.case_network(case_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return resp


@router.get("/{case_id}/evidence", response_model=EvidenceListResponse)
def case_evidence(case_id: int, _role: str = Depends(require_case_read)):
    return explorer.list_evidence(case_id)


@router.post("/{case_id}/evidence", response_model=EvidenceCreateResponse, status_code=201)
def add_case_evidence(case_id: int, body: EvidenceCreateRequest,
                      role: str = Depends(require_case_write)):
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=422, detail="Evidence title is required.")
    try:
        res = explorer.add_evidence(
            case_id, body.evidence_type, body.title.strip(),
            body.description, body.reference, role)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if res is explorer.NO_TABLE:
        raise HTTPException(
            status_code=503,
            detail=("Case evidence store is not provisioned yet. Apply migration "
                    "services/ml/sql/004_case_evidence.sql."))
    if res is explorer.NO_CASE:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"evidence": res}
