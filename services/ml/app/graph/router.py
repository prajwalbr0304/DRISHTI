"""FastAPI router for the Phase-6 graph-analysis engine + Phase-15d entity explorer.

Graph endpoints return the AiResult contract embedded in a typed envelope.
Entity explorer endpoints are plain reads (not AI-derived) with policymaker gating.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..intake.guards import require_write_allowed
from . import explorer, service
from .schemas import (ArchiveStatusResponse, CentralityResponse, CommunitiesResponse,
                      HiddenFeedResponse, PathResponse, ProofPathResponse, RebuildResponse,
                      ReviewResponse, SubgraphResponse)

router = APIRouter(prefix="/graph", tags=["graph"])

# Graph rebuild / archival / edge review are analyst+ governance actions.
_GRAPH_WRITE_ROLES = {"analyst", "investigator", "supervisor", "super_admin"}


def require_graph_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role not in _GRAPH_WRITE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot rebuild/curate the intelligence graph.")
    return role


# --- Policymaker gate (individual profiles = de-anonymisation risk) ----------
_DENY_INDIVIDUAL = {"policymaker"}


def _resolve_role(x_role: Optional[str] = Header(default=None)) -> str:
    from ..config import get_settings
    return (x_role or get_settings().default_role or "investigator").strip()


def require_entity_read(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role in _DENY_INDIVIDUAL:
        raise HTTPException(
            status_code=403,
            detail="Individual entity profiles are not available to the policymaker role (aggregate-only).")
    return role


# --- Entity Explorer (Phase 15d) -------------------------------------------
@router.get("/entities")
def list_entities(
    q: Optional[str] = Query(None, description="full-text search over label"),
    entity_type: Optional[str] = Query(None),
    has_risk: bool = Query(False),
    gang_affiliated: bool = Query(False),
    district_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    _role: str = Depends(require_entity_read),
):
    return explorer.list_entities(
        q=q, entity_type=entity_type, has_risk=has_risk or None,
        gang_affiliated=gang_affiliated or None, district_id=district_id,
        page=page, page_size=page_size,
    )


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: int, _role: str = Depends(require_entity_read)):
    resp = explorer.entity_detail(entity_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return resp


@router.get("/communities/list")
def communities_list(limit: int = Query(40, ge=1, le=200), _role: str = Depends(require_entity_read)):
    """Communities ranked by size + known-gang cross-reference (side list)."""
    return explorer.list_communities(limit)


@router.get("/communities/{community_id}/subgraph")
def community_subgraph(community_id: int, limit: int = Query(60, ge=1, le=150),
                       _role: str = Depends(require_entity_read)):
    """Top members of a community + induced edges, for the canvas."""
    return explorer.community_subgraph(community_id, limit)


@router.get("/neighbourhood", response_model=SubgraphResponse)
def neighbourhood(
    entity_id: int = Query(..., ge=1),
    max_hops: int = Query(2, ge=1, le=3, description="hard-capped at 3"),
    top_n: int = Query(15, ge=1, le=50, description="fan-out cap by edge weight"),
):
    return service.neighbourhood(entity_id, max_hops, top_n)


@router.get("/path", response_model=PathResponse)
def path(source: int = Query(..., ge=1), target: int = Query(..., ge=1)):
    if source == target:
        raise HTTPException(status_code=400, detail="source and target must differ")
    return service.path(source, target)


@router.post("/communities", response_model=CommunitiesResponse)
def communities():
    """Run Louvain, write community labels, report gang precision/recall."""
    return service.run_communities()


@router.get("/centrality", response_model=CentralityResponse)
def centrality(
    top: int = Query(20, ge=1, le=200),
    entity_type: str = Query("person"),
):
    return service.centrality(top, entity_type)


@router.post("/hidden-associations", response_model=HiddenFeedResponse)
def hidden_associations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_links: int = Query(2, ge=2, le=5),
    refresh: bool = Query(False, description="re-materialize before reading"),
):
    return service.hidden_feed(page, page_size, min_links, refresh)


@router.get("/proof-path", response_model=ProofPathResponse)
def proof_path(association_id: int = Query(..., ge=1)):
    resp = service.proof_path(association_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"association {association_id} not found")
    return resp


# --- Phase 11: canonical-space isolation, rebuild, reviewer disposition -----
@router.get("/archive-status", response_model=ArchiveStatusResponse)
def archive_status(_role: str = Depends(require_entity_read)):
    """Old-vs-new graph-space isolation: archived/live counts + a 'clean' flag."""
    return service.archive_status()


@router.post("/archive-legacy", response_model=ArchiveStatusResponse)
def archive_legacy(request: Request, role: str = Depends(require_graph_write)):
    """Isolate (archive, never delete) legacy non-canonical/unprovenanced rows."""
    require_write_allowed(request)
    return service.archive_legacy(f"demo.{role}")


@router.post("/rebuild", response_model=RebuildResponse)
def rebuild(request: Request, role: str = Depends(require_graph_write),
            communities: bool = Query(True), centrality: bool = Query(True),
            hidden: bool = Query(True)):
    """Rebuild communities/centrality/hidden-associations from the CANONICAL graph."""
    require_write_allowed(request)
    return service.rebuild(f"demo.{role}", run_communities=communities,
                           run_centrality=centrality, run_hidden=hidden)


@router.post("/edges/{edge_id}/review", response_model=ReviewResponse)
def review_edge(edge_id: int, request: Request, decision: str = Query(..., pattern="^(confirm|reject|reset)$"),
                reason: Optional[str] = Query(None), role: str = Depends(require_graph_write)):
    """Reviewer disposition on a graph edge (candidate -> confirmed/rejected)."""
    require_write_allowed(request)
    return service.review_edge(edge_id, decision, actor=f"demo.{role}", reason=reason)


@router.post("/hidden-associations/{association_id}/review", response_model=ReviewResponse)
def review_hidden(association_id: int, request: Request,
                  decision: str = Query(..., pattern="^(confirm|reject|reset)$"),
                  reason: Optional[str] = Query(None), role: str = Depends(require_graph_write)):
    """Reviewer disposition on a hidden association (preserved across re-materialise)."""
    require_write_allowed(request)
    return service.review_hidden(association_id, decision, actor=f"demo.{role}", reason=reason)
