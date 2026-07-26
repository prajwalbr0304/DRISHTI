"""FastAPI router for the Investigation Board (Prompt 16 §C).

Every mutating route: coarse role gate (canonical command roles) + write guard
+ resolved demo actor + optional idempotency key + optional If-Match version.
Lock / promotion / export additionally require a fresh authenticated confirmation.
Per-board authorization (owner/editor/viewer, out-of-scope share) is enforced in
the service. Errors are mapped to HTTP status without leaking internals.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from pydantic import BaseModel

from . import export as export_mod
from . import presence as presence_mod
from . import promote as promote_mod
from . import references, searcharound, service
from . import guards
from .schemas import (AnnotationCreate, AnnotationPatch, BoardCreate, BoardDetail,
                      BoardListResponse, BoardPatch, BoardPathResult, CollaboratorAdd,
                      EdgeCreate, EdgePatch, ExportOut, ExportRequest, MutationResult,
                      NodeCreate, NodePatch, PathRequest, PromoteEdgeRequest,
                      SearchAroundRequest, SearchAroundResult, SeedRequest, SeedResult)

router = APIRouter(prefix="/boards", tags=["investigation-board"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.BoardNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except service.BoardForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except service.BoardValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except service.BoardLocked as exc:
        raise HTTPException(status_code=423, detail=str(exc))     # 423 Locked
    except service.BoardConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _idem(x_idempotency_key: Optional[str]) -> Optional[str]:
    return (x_idempotency_key or "").strip() or None


def _version_from(if_match: Optional[str], body_version: Optional[int]) -> Optional[int]:
    """Prefer the body expected_version; else parse an If-Match header integer."""
    if body_version is not None:
        return body_version
    if if_match:
        try:
            return int(if_match.strip().strip('"'))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# metadata helpers (UI palette)
# ---------------------------------------------------------------------------
@router.get("/meta/object-kinds")
def object_kinds(_role: str = Depends(guards.require_board_role)):
    return {"node_kinds": references.supported_kinds(),
            "ref_tables": references.supported_ref_tables()}


# ---------------------------------------------------------------------------
# boards
# ---------------------------------------------------------------------------
@router.post("", response_model=BoardDetail, status_code=201)
def create_board(req: BoardCreate, request: Request,
                 role: str = Depends(guards.require_board_create),
                 x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    if req.visibility != "private" and role not in guards.BOARD_SHARE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' can only create private boards (board_share required to share).")
    return _call(service.create_board, req, guards.resolve_actor(request), role)


@router.get("", response_model=BoardListResponse)
def list_boards(request: Request, role: str = Depends(guards.require_board_role)):
    return _call(service.list_boards, guards.resolve_actor(request), role)


@router.get("/{board_id}", response_model=BoardDetail)
def get_board(board_id: int, request: Request, role: str = Depends(guards.require_board_role)):
    return _call(service.get_board, board_id, guards.resolve_actor(request), role)


@router.patch("/{board_id}", response_model=MutationResult)
def patch_board(board_id: int, req: BoardPatch, request: Request,
                role: str = Depends(guards.require_board_role),
                if_match: Optional[str] = Header(default=None),
                x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    # a visibility change is a share action (board_share).
    if req.visibility is not None and role not in guards.BOARD_SHARE_ROLES:
        raise HTTPException(status_code=403,
                            detail="Changing visibility requires board_share (supervisor).")
    req.expected_version = _version_from(if_match, req.expected_version)
    return _call(service.patch_board, board_id, req, guards.resolve_actor(request), role,
                 idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/archive", response_model=MutationResult)
def archive_board(board_id: int, request: Request,
                  role: str = Depends(guards.require_board_role),
                  x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.archive_board, board_id, guards.resolve_actor(request), role,
                 idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/lock", response_model=MutationResult)
def lock_board(board_id: int, request: Request,
               confirm: bool = Query(False, description="fresh authenticated confirmation"),
               role: str = Depends(guards.require_board_lock),
               x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    guards.require_fresh_confirmation(confirm, "lock")
    return _call(service.lock_board, board_id, guards.resolve_actor(request), role,
                 idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/branch", response_model=BoardDetail, status_code=201)
def branch_board(board_id: int, request: Request,
                 title: Optional[str] = Query(None),
                 role: str = Depends(guards.require_board_lock)):
    guards.require_board_write_allowed(request)
    return _call(service.branch_board, board_id, guards.resolve_actor(request), role,
                 title=title)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------
@router.post("/{board_id}/nodes", response_model=MutationResult, status_code=201)
def add_node(board_id: int, req: NodeCreate, request: Request,
             role: str = Depends(guards.require_board_role),
             x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.add_node, board_id, req, guards.resolve_actor(request), role,
                 idem_key=_idem(x_idempotency_key))


@router.patch("/{board_id}/nodes/{node_id}", response_model=MutationResult)
def patch_node(board_id: int, node_id: int, req: NodePatch, request: Request,
               role: str = Depends(guards.require_board_role),
               if_match: Optional[str] = Header(default=None),
               x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    req.expected_version = _version_from(if_match, req.expected_version)
    return _call(service.patch_node, board_id, node_id, req,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


@router.delete("/{board_id}/nodes/{node_id}", response_model=MutationResult)
def delete_node(board_id: int, node_id: int, request: Request,
                role: str = Depends(guards.require_board_role),
                x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.delete_node, board_id, node_id, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# edges
# ---------------------------------------------------------------------------
@router.post("/{board_id}/edges", response_model=MutationResult, status_code=201)
def add_edge(board_id: int, req: EdgeCreate, request: Request,
             role: str = Depends(guards.require_board_role),
             x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.add_edge, board_id, req, guards.resolve_actor(request), role,
                 idem_key=_idem(x_idempotency_key))


@router.patch("/{board_id}/edges/{edge_id}", response_model=MutationResult)
def patch_edge(board_id: int, edge_id: int, req: EdgePatch, request: Request,
               role: str = Depends(guards.require_board_role),
               if_match: Optional[str] = Header(default=None),
               x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    req.expected_version = _version_from(if_match, req.expected_version)
    return _call(service.patch_edge, board_id, edge_id, req,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


@router.delete("/{board_id}/edges/{edge_id}", response_model=MutationResult)
def delete_edge(board_id: int, edge_id: int, request: Request,
                role: str = Depends(guards.require_board_role),
                x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.delete_edge, board_id, edge_id, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# annotations
# ---------------------------------------------------------------------------
@router.post("/{board_id}/annotations", response_model=MutationResult, status_code=201)
def add_annotation(board_id: int, req: AnnotationCreate, request: Request,
                   role: str = Depends(guards.require_board_role),
                   x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.add_annotation, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


@router.patch("/{board_id}/annotations/{annotation_id}", response_model=MutationResult)
def patch_annotation(board_id: int, annotation_id: int, req: AnnotationPatch,
                     request: Request, role: str = Depends(guards.require_board_role),
                     if_match: Optional[str] = Header(default=None),
                     x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    req.expected_version = _version_from(if_match, req.expected_version)
    return _call(service.patch_annotation, board_id, annotation_id, req,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


@router.delete("/{board_id}/annotations/{annotation_id}", response_model=MutationResult)
def delete_annotation(board_id: int, annotation_id: int, request: Request,
                      role: str = Depends(guards.require_board_role),
                      x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.delete_annotation, board_id, annotation_id,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# collaborators (board_share)
# ---------------------------------------------------------------------------
@router.get("/{board_id}/collaborators")
def list_collaborators(board_id: int, request: Request,
                       role: str = Depends(guards.require_board_role)):
    return _call(service.list_collaborators, board_id, guards.resolve_actor(request), role)


@router.post("/{board_id}/collaborators", response_model=MutationResult, status_code=201)
def add_collaborator(board_id: int, req: CollaboratorAdd, request: Request,
                     role: str = Depends(guards.require_board_share),
                     x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.add_collaborator, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


@router.delete("/{board_id}/collaborators/{collaborator_id}", response_model=MutationResult)
def remove_collaborator(board_id: int, collaborator_id: int, request: Request,
                        role: str = Depends(guards.require_board_share),
                        x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    return _call(service.remove_collaborator, board_id, collaborator_id,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# search around / subgraph import
# ---------------------------------------------------------------------------
@router.post("/{board_id}/search-around", response_model=SearchAroundResult)
def search_around(board_id: int, req: SearchAroundRequest, request: Request,
                  role: str = Depends(guards.require_board_role),
                  x_idempotency_key: Optional[str] = Header(default=None)):
    # preview is a read; a commit (preview=false) is a write.
    if not req.preview:
        guards.require_board_write_allowed(request)
    return _call(service.search_around, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/import/subgraph", response_model=SearchAroundResult)
def import_subgraph(board_id: int, req: SearchAroundRequest, request: Request,
                    role: str = Depends(guards.require_board_role),
                    x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    req.preview = False
    return _call(service.search_around, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/seed", response_model=SeedResult, status_code=201)
def seed_reference(board_id: int, req: SeedRequest, request: Request,
                   role: str = Depends(guards.require_board_role),
                   x_idempotency_key: Optional[str] = Header(default=None)):
    """Pin an object and auto-populate its governed case records or verified
    entity neighbourhood. Graceful: degrades to a single pin."""
    guards.require_board_write_allowed(request)
    return _call(service.seed_reference, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


@router.post("/{board_id}/path", response_model=BoardPathResult)
def find_path(board_id: int, req: PathRequest, request: Request,
              role: str = Depends(guards.require_board_role),
              x_idempotency_key: Optional[str] = Header(default=None)):
    """Shortest associative path between two entity-backed nodes, imported as
    read-only evidence nodes/edges (reuses the canonical graph path finder)."""
    guards.require_board_write_allowed(request)
    return _call(service.find_path, board_id, req, guards.resolve_actor(request),
                 role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# promotion (board_promote + fresh confirmation)
# ---------------------------------------------------------------------------
@router.post("/{board_id}/promote-edge/{edge_id}", response_model=MutationResult)
def promote_edge(board_id: int, edge_id: int, req: PromoteEdgeRequest, request: Request,
                 role: str = Depends(guards.require_board_promote),
                 x_idempotency_key: Optional[str] = Header(default=None)):
    guards.require_board_write_allowed(request)
    guards.require_fresh_confirmation(req.confirm, "promotion")
    return _call(promote_mod.promote_edge, board_id, edge_id, req,
                 guards.resolve_actor(request), role, idem_key=_idem(x_idempotency_key))


# ---------------------------------------------------------------------------
# helpers: activity / table / timeline / diffs / references
# ---------------------------------------------------------------------------
@router.get("/{board_id}/activity")
def activity(board_id: int, request: Request, after_id: int = Query(0, ge=0),
             limit: int = Query(500, ge=1, le=2000),
             role: str = Depends(guards.require_board_role)):
    return _call(service.activity, board_id, after_id, guards.resolve_actor(request),
                 role, limit=limit)


@router.get("/{board_id}/table")
def table(board_id: int, request: Request, role: str = Depends(guards.require_board_role)):
    return _call(service.table, board_id, guards.resolve_actor(request), role)


@router.get("/{board_id}/timeline")
def timeline(board_id: int, request: Request,
             window_start: Optional[str] = Query(None),
             window_end: Optional[str] = Query(None),
             role: str = Depends(guards.require_board_role)):
    return _call(service.timeline, board_id, guards.resolve_actor(request), role,
                 window_start=window_start, window_end=window_end)


@router.get("/{board_id}/diffs")
def diffs(board_id: int, request: Request, role: str = Depends(guards.require_board_role)):
    return _call(service.node_diffs, board_id, guards.resolve_actor(request), role)


@router.get("/{board_id}/benchmark/search-around")
def benchmark_search_around(board_id: int, request: Request,
                            entity_id: int = Query(..., ge=1),
                            max_neighbors: int = Query(15, ge=1, le=50),
                            role: str = Depends(guards.require_board_role)):
    # read-only board access is enough; the benchmark is a graph read.
    _call(service.get_board, board_id, guards.resolve_actor(request), role)
    return searcharound.benchmark_two_hop(entity_id, max_neighbors)


@router.get("/references/{ref_table}/{ref_id}")
def get_reference(ref_table: str, ref_id: str, _role: str = Depends(guards.require_board_role)):
    return _call(service.get_reference, ref_table, ref_id)


# ---------------------------------------------------------------------------
# presence (ephemeral, throttled, NoSQL/TTL — never in BoardActivity)
# ---------------------------------------------------------------------------
class PresenceBeat(BaseModel):
    cursor: Optional[dict] = None
    selection: Optional[dict] = None


@router.post("/{board_id}/presence")
def presence_heartbeat(board_id: int, body: PresenceBeat, request: Request,
                       role: str = Depends(guards.require_board_role)):
    actor = guards.resolve_actor(request)
    # confirm the caller can see the board before recording presence
    _call(service.get_board, board_id, actor, role)
    return presence_mod.heartbeat(board_id, actor, cursor=body.cursor, selection=body.selection)


@router.get("/{board_id}/presence")
def presence_roster(board_id: int, request: Request,
                    role: str = Depends(guards.require_board_role)):
    _call(service.get_board, board_id, guards.resolve_actor(request), role)
    return presence_mod.roster(board_id)


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------
@router.post("/{board_id}/export", response_model=ExportOut, status_code=201)
def export_board(board_id: int, req: ExportRequest, request: Request,
                 role: str = Depends(guards.require_board_role)):
    guards.require_board_write_allowed(request)
    guards.require_fresh_confirmation(req.confirm, "export")
    return _call(export_mod.export_board, board_id, req, guards.resolve_actor(request), role)


@router.get("/{board_id}/export/{export_id}", response_model=ExportOut)
def get_export(board_id: int, export_id: str, request: Request,
               role: str = Depends(guards.require_board_role)):
    return _call(export_mod.get_export, board_id, export_id,
                 guards.resolve_actor(request), role)


@router.post("/import", response_model=BoardDetail, status_code=201)
def import_board(document: dict, request: Request,
                 role: str = Depends(guards.require_board_create)):
    guards.require_board_write_allowed(request)
    return _call(export_mod.import_board, document, guards.resolve_actor(request), role)
