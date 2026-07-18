"""Deployed metadata search endpoint (Prompt 14 Part E, item 6).

`GET /search` runs case / FIR / person / evidence metadata search over Catalyst
Data Store full-text search (never an external service). It is additive: the
existing rich per-domain list endpoints are unchanged. Locally the in-memory
Data Store fake backs it (empty unless seeded); in deployment the Catalyst Data
Store FTS component backs it. Results are ExternalID-keyed hits.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..cases.permissions import require_case_read
from ..datastore.search import get_metadata_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def metadata_search(
    q: str = Query(..., min_length=1, description="free text over case/person/evidence metadata"),
    kind: str = Query("all", pattern="^(all|case|person|evidence)$"),
    limit: int = Query(25, ge=1, le=100),
    _role: str = Depends(require_case_read),
):
    svc = get_metadata_search()
    hits = svc.search(q, kind=kind, limit=limit)
    return {
        "query": q,
        "kind": kind,
        "search_backend": svc.backend_name,   # observable: Data Store FTS in deployment
        "count": len(hits),
        "hits": [h.as_dict() for h in hits],
    }
