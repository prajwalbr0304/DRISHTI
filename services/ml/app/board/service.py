"""Investigation Board service (Prompt 16 §C).

Business logic over the Data Store board repo. Every mutating operation:
  * checks per-board authorization (owner/editor/viewer + policymaker denial);
  * rejects edits to a locked board (branch instead);
  * supports an idempotency key (safe retry) and optimistic concurrency
    (board Version / expected_version) for semantic edits;
  * writes the domain record FIRST, then an APPEND-ONLY BoardActivity row that
    references the committed change, then bumps the board Version — so activity
    can never claim an uncommitted change (compensation/replay safe);
  * publishes a data-minimised ``board.activity`` signal AFTER the commit;
  * returns the new BoardActivityID + board Version.

Design mirrors app/casework/service.py (internal helpers + typed serialisers +
explicit error classes mapped to HTTP status in the router).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..cache import SEG_IDEMPOTENCY
from ..contracts import AiResult
from ..request_context import current_context
from ..signals import EVENT_BOARD_ACTIVITY, get_signals
from ..datastore import board_schema
from . import references, searcharound
from .repo import BoardRepo, board_cache, board_repo
from .schemas import (ANNOTATION_KINDS, BOARD_STATUSES, BOARD_VISIBILITY,
                      EDGE_CLASSES, ActivityResponse, AnnotationCreate,
                      AnnotationPatch, BoardActivityOut, BoardAnnotationOut,
                      BoardCollaboratorOut, BoardCreate, BoardDetail, BoardEdgeOut,
                      BoardListResponse, BoardNodeOut, BoardPatch, BoardSummary,
                      CollaboratorAdd, EdgeCreate, EdgePatch, MutationResult,
                      NodeCreate, NodeDiffOut, NodePatch, ReferenceOut,
                      SearchAroundNeighbor, SearchAroundRequest, SearchAroundResult,
                      BoardPathResult, PathRequest, SeedRequest, SeedResult,
                      TableResponse, TableRow, TimelineEvent, TimelineResponse)

# graph entity_type -> board NodeKind
_ENTITY_KIND = {"person": "entity", "gang": "entity", "organisation": "entity",
                "vehicle": "vehicle", "phone": "phone", "device": "phone",
                "location": "location", "account": "account",
                "bank_account": "account"}

_MODEL = "drishti-board@1.0.0"


# ---------------------------------------------------------------------------
# Errors (mapped to HTTP in router)
# ---------------------------------------------------------------------------
class BoardError(Exception):
    pass


class BoardNotFound(BoardError):
    pass


class BoardForbidden(BoardError):
    pass


class BoardValidationError(BoardError):
    pass


class BoardConflict(BoardError):
    pass


class BoardLocked(BoardError):
    pass


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _req_id() -> Optional[str]:
    ctx = current_context()
    return ctx.request_id if ctx else None


def _json(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def _check_json_size(obj: dict, limit: int, field: str) -> dict:
    raw = json.dumps(obj or {}, default=str)
    if len(raw.encode("utf-8")) > limit:
        raise BoardValidationError(
            f"{field} exceeds the {limit}-byte limit ({len(raw)} bytes).")
    return obj or {}


def _require_enum(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise BoardValidationError(f"invalid {field} '{value}'; expected {allowed}")
    return value


def _int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# access control (per board)
# ---------------------------------------------------------------------------
def _load_board(repo: BoardRepo, board_id: int) -> dict:
    b = repo.get("InvestigationBoard", board_id)
    if b is None:
        raise BoardNotFound(f"Board {board_id} not found.")
    return b


def _effective_role(repo: BoardRepo, board: dict, actor: str, role: str) -> Optional[str]:
    """owner|editor|viewer|None for this actor on this board."""
    if role == "super_admin":
        return "owner"
    if actor and actor == board.get("OwnerActor"):
        return "owner"
    if role == "supervisor":
        return "editor"     # supervisory oversight within demo scope
    for c in repo.list_by_board("BoardCollaborator", int(board["BoardID"])):
        if c.get("Actor") == actor:
            return c.get("Role")
    if board.get("Visibility") == "unit":
        return "viewer"     # unit-visible boards are readable by unit members
    return None


def _require_access(repo: BoardRepo, board: dict, actor: str, role: str,
                    *, write: bool) -> str:
    eff = _effective_role(repo, board, actor, role)
    if eff is None:
        raise BoardForbidden(
            f"You do not have access to board {board['BoardID']}.")
    if write and eff not in ("owner", "editor"):
        raise BoardForbidden(
            f"Role '{role}' has view-only access to board {board['BoardID']}.")
    return eff


def _is_locked(board: dict) -> bool:
    return bool(board.get("IsLocked")) or board.get("Status") == "locked"


def _ensure_not_locked(board: dict) -> None:
    if _is_locked(board):
        raise BoardLocked(
            f"Board {board['BoardID']} is locked. Branch a copy to keep editing; "
            "the locked version is never modified.")


# ---------------------------------------------------------------------------
# idempotency + signal
# ---------------------------------------------------------------------------
def _idempotent(idem_key: Optional[str], produce: Callable[[], MutationResult]) -> MutationResult:
    if not idem_key:
        return produce()
    cache = board_cache()
    key = f"board:idem:{idem_key}"
    try:
        existing = cache.get(SEG_IDEMPOTENCY, key)
    except Exception:  # noqa: BLE001
        existing = None
    if existing:
        try:
            data = json.loads(existing)
            data["idempotent_replay"] = True
            return MutationResult(**data)
        except Exception:  # noqa: BLE001
            pass
    result = produce()
    try:
        cache.put(SEG_IDEMPOTENCY, key, json.dumps(result.model_dump()))
    except Exception:  # noqa: BLE001
        pass
    return result


def _publish(board_id: int, activity_id: int, version: int, kind: str,
             target_type: Optional[str], target_id: Optional[Any], actor: str) -> None:
    """Broadcast AFTER the Data Store commit; minimal, never a full snapshot."""
    try:
        get_signals().publish(EVENT_BOARD_ACTIVITY, {
            "board_id": board_id, "board_activity_id": activity_id,
            "version": version, "kind": kind, "target_type": target_type,
            "target_id": (str(target_id) if target_id is not None else None),
            "actor": actor,
        })
    except Exception:  # noqa: BLE001 — a signal failure must never break the write
        pass


def _mutate(repo: BoardRepo, board: dict, actor: str, role: str, *, action: str,
            apply: Callable[[dict], tuple[Optional[str], Optional[Any], dict]],
            write: bool = True, allow_locked: bool = False,
            idem_key: Optional[str] = None, expected_version: Optional[int] = None,
            enforce_version: bool = False) -> MutationResult:
    _require_access(repo, board, actor, role, write=write)
    if write and not allow_locked:
        _ensure_not_locked(board)

    def produce() -> MutationResult:
        if enforce_version and expected_version is not None:
            if int(board.get("Version") or 0) != int(expected_version):
                raise BoardConflict(
                    f"Version conflict: board is at v{board.get('Version')}, "
                    f"you edited v{expected_version}. Reload and retry.")
        target_type, target_id, diff = apply(board)
        act = repo.append_activity(int(board["BoardID"]), actor, action,
                                   target_type=target_type, target_id=target_id,
                                   diff=diff, request_id=_req_id())
        new_version = int(board.get("Version") or 0) + 1
        repo.update("InvestigationBoard", int(board["BoardID"]),
                    {"Version": new_version})
        board["Version"] = new_version
        _publish(int(board["BoardID"]), int(act["BoardActivityID"]), new_version,
                 action, target_type, target_id, actor)
        return MutationResult(board_id=int(board["BoardID"]),
                              board_activity_id=int(act["BoardActivityID"]),
                              version=new_version, target_type=target_type,
                              target_id=(str(target_id) if target_id is not None else None))

    return _idempotent(idem_key, produce)


# ---------------------------------------------------------------------------
# serialisers
# ---------------------------------------------------------------------------
def _board_summary(repo: BoardRepo, b: dict, *, actor: str, role: str,
                   with_counts: bool = True) -> BoardSummary:
    bid = int(b["BoardID"])
    nc = ec = 0
    if with_counts:
        nc = len(repo.list_by_board("BoardNode", bid))
        ec = len(repo.list_by_board("BoardEdge", bid))
    return BoardSummary(
        board_id=bid, title=b.get("Title", ""), description=b.get("Description"),
        owner_actor=b.get("OwnerActor", ""), case_master_id=_int(b.get("CaseMasterID")),
        status=b.get("Status", "active"), visibility=b.get("Visibility", "private"),
        is_locked=bool(b.get("IsLocked")), version=int(b.get("Version") or 1),
        parent_board_id=_int(b.get("ParentBoardID")), node_count=nc, edge_count=ec,
        my_role=_effective_role(repo, b, actor, role),
        created_at=b.get("CreatedAt"), updated_at=b.get("UpdatedAt"))


def _node_out(n: dict) -> BoardNodeOut:
    snap = _json(n.get("SnapshotJSON"))
    ref_table = n.get("RefTable")
    ref_id = n.get("RefID")
    open_src = None
    spec = references.spec_for(ref_table) if ref_table else None
    if spec and spec.open_in_source and ref_id is not None:
        open_src = spec.open_in_source.format(id=ref_id)
    return BoardNodeOut(
        board_node_id=int(n["BoardNodeID"]), board_id=int(n["BoardID"]),
        node_kind=n.get("NodeKind", "note"), ref_table=ref_table, ref_id=ref_id,
        canonical_entity_id=_int(n.get("CanonicalEntityID")), label=n.get("Label"),
        pos_x=float(n.get("PosX") or 0.0), pos_y=float(n.get("PosY") or 0.0),
        width=(float(n["Width"]) if n.get("Width") is not None else None),
        height=(float(n["Height"]) if n.get("Height") is not None else None),
        style=_json(n.get("StyleJSON")), snapshot=snap,
        source_version=n.get("SourceVersion"), source_hash=n.get("SourceHash"),
        open_in_source=open_src, created_by=n.get("CreatedBy"),
        created_at=n.get("CreatedAt"))


def _edge_out(e: dict) -> BoardEdgeOut:
    return BoardEdgeOut(
        board_edge_id=int(e["BoardEdgeID"]), board_id=int(e["BoardID"]),
        source_node_id=int(e["SourceNodeID"]), target_node_id=int(e["TargetNodeID"]),
        edge_class=e.get("EdgeClass", "hypothesis"), label=e.get("Label"),
        relationship_type=e.get("RelationshipType"), directed=bool(e.get("Directed")),
        confidence=(float(e["Confidence"]) if e.get("Confidence") is not None else None),
        rationale=e.get("Rationale"), evidence_case_id=_int(e.get("EvidenceCaseID")),
        source_record_id=e.get("SourceRecordID"), style=_json(e.get("StyleJSON")),
        promoted_status=e.get("PromotedStatus"), promoted_ref=e.get("PromotedRef"),
        created_by=e.get("CreatedBy"), created_at=e.get("CreatedAt"))


def _annotation_out(a: dict) -> BoardAnnotationOut:
    return BoardAnnotationOut(
        board_annotation_id=int(a["BoardAnnotationID"]), board_id=int(a["BoardID"]),
        kind=a.get("Kind", "sticky"), content=a.get("Content"),
        geometry=_json(a.get("GeometryJSON")), style=_json(a.get("StyleJSON")),
        created_by=a.get("CreatedBy"), created_at=a.get("CreatedAt"))


def _collab_out(c: dict) -> BoardCollaboratorOut:
    return BoardCollaboratorOut(
        board_collaborator_id=int(c["BoardCollaboratorID"]), board_id=int(c["BoardID"]),
        actor=c.get("Actor", ""), employee_id=_int(c.get("EmployeeID")),
        role=c.get("Role", "viewer"), added_by=c.get("AddedBy"),
        added_at=c.get("AddedAt"))


def _activity_out(a: dict) -> BoardActivityOut:
    return BoardActivityOut(
        board_activity_id=int(a["BoardActivityID"]), board_id=int(a["BoardID"]),
        actor=a.get("Actor", ""), action=a.get("Action", ""),
        target_type=a.get("TargetType"), target_id=a.get("TargetID"),
        diff=_json(a.get("DiffJSON")), request_id=a.get("RequestID"),
        created_at=a.get("CreatedAt"))


# ---------------------------------------------------------------------------
# boards
# ---------------------------------------------------------------------------
def create_board(req: BoardCreate, actor: str, role: str) -> BoardDetail:
    _require_enum(req.visibility, BOARD_VISIBILITY, "visibility")
    repo = board_repo()
    row = {
        "Title": req.title.strip(), "Description": (req.description or "").strip() or None,
        "OwnerActor": actor, "OwnerEmployeeID": None,
        "CaseMasterID": req.case_master_id, "UnitID": req.unit_id,
        "DistrictID": req.district_id, "Status": "active",
        "Visibility": req.visibility, "IsLocked": False, "Version": 1,
        "ParentBoardID": None,
    }
    board = repo.create("InvestigationBoard", row)
    bid = int(board["BoardID"])
    repo.append_activity(bid, actor, "board.create", target_type="board",
                         target_id=bid, diff={"title": row["Title"],
                                              "case_master_id": req.case_master_id,
                                              "visibility": req.visibility},
                         request_id=_req_id())
    # optional "from network selection" seed (evidence subgraph)
    if req.seed_entity_id:
        try:
            from .schemas import SearchAroundRequest
            search_around(bid, SearchAroundRequest(
                entity_id=req.seed_entity_id, hops=req.seed_hops,
                max_neighbors=req.seed_max_neighbors, preview=False), actor, role)
        except Exception:  # noqa: BLE001 — seeding is best-effort
            pass
    return get_board(bid, actor, role)


def list_boards(actor: str, role: str) -> BoardListResponse:
    repo = board_repo()
    seen: dict[int, dict] = {}
    for b in repo.all_boards():
        if str(b.get("Status") or "").lower() == "archived":
            continue  # archived boards are hidden from the active list + picker
        bid = int(b["BoardID"])
        if _effective_role(repo, b, actor, role) is not None:
            seen[bid] = b
    items = [_board_summary(repo, b, actor=actor, role=role) for b in seen.values()]
    items.sort(key=lambda s: s.board_id, reverse=True)
    return BoardListResponse(count=len(items), items=items)


def get_board(board_id: int, actor: str, role: str) -> BoardDetail:
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    nodes = [_node_out(n) for n in repo.list_by_board("BoardNode", board_id)]
    edges = [_edge_out(e) for e in repo.list_by_board("BoardEdge", board_id)]
    annotations = [_annotation_out(a) for a in repo.list_by_board("BoardAnnotation", board_id)]
    collaborators = [_collab_out(c) for c in repo.list_by_board("BoardCollaborator", board_id)]
    return BoardDetail(
        board=_board_summary(repo, board, actor=actor, role=role),
        nodes=nodes, edges=edges, annotations=annotations, collaborators=collaborators,
        latest_activity_id=repo.latest_activity_id(board_id))


def patch_board(board_id: int, req: BoardPatch, actor: str, role: str, *,
                idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    patch: dict[str, Any] = {}
    if req.title is not None:
        patch["Title"] = req.title.strip()
    if req.description is not None:
        patch["Description"] = req.description.strip() or None
    if req.status is not None:
        patch["Status"] = _require_enum(req.status, BOARD_STATUSES, "status")
    if req.visibility is not None:
        patch["Visibility"] = _require_enum(req.visibility, BOARD_VISIBILITY, "visibility")
    if not patch:
        raise BoardValidationError("no board fields to update")

    def apply(b: dict):
        repo.update("InvestigationBoard", board_id, patch)
        return "board", board_id, {"fields": list(patch.keys())}

    return _mutate(repo, board, actor, role, action="board.update", apply=apply,
                   idem_key=idem_key, expected_version=req.expected_version,
                   enforce_version=req.expected_version is not None)


def archive_board(board_id: int, actor: str, role: str, *,
                  idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)

    def apply(b: dict):
        repo.update("InvestigationBoard", board_id, {"Status": "archived"})
        return "board", board_id, {"status": "archived"}

    return _mutate(repo, board, actor, role, action="board.archive", apply=apply,
                   allow_locked=True, idem_key=idem_key)


def lock_board(board_id: int, actor: str, role: str, *,
               idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    if _is_locked(board):
        raise BoardConflict(f"Board {board_id} is already locked.")

    def apply(b: dict):
        repo.update("InvestigationBoard", board_id, {"Status": "locked", "IsLocked": True})
        return "board", board_id, {"locked": True}

    return _mutate(repo, board, actor, role, action="board.lock", apply=apply,
                   allow_locked=True, idem_key=idem_key)


def branch_board(board_id: int, actor: str, role: str, *,
                 title: Optional[str] = None) -> BoardDetail:
    """Create an editable copy linked to a (typically locked) parent."""
    repo = board_repo()
    parent = _load_board(repo, board_id)
    _require_access(repo, parent, actor, role, write=False)
    new = repo.create("InvestigationBoard", {
        "Title": (title or f"{parent.get('Title', 'Board')} (branch)").strip(),
        "Description": parent.get("Description"), "OwnerActor": actor,
        "OwnerEmployeeID": None, "CaseMasterID": parent.get("CaseMasterID"),
        "UnitID": parent.get("UnitID"), "DistrictID": parent.get("DistrictID"),
        "Status": "active", "Visibility": parent.get("Visibility", "private"),
        "IsLocked": False, "Version": 1, "ParentBoardID": board_id,
    })
    new_id = int(new["BoardID"])
    # copy nodes (remap ids), edges (remap endpoints), annotations
    id_map: dict[int, int] = {}
    for n in repo.list_by_board("BoardNode", board_id):
        copy = {k: v for k, v in n.items()
                if k not in ("BoardNodeID", "BoardID", "ExternalID", "ROWID",
                             "CreatedAt", "UpdatedAt", "DeletedAt")}
        copy["BoardID"] = new_id
        copy.setdefault("CreatedBy", actor)
        created = repo.create("BoardNode", copy)
        id_map[int(n["BoardNodeID"])] = int(created["BoardNodeID"])
    for e in repo.list_by_board("BoardEdge", board_id):
        s, t = id_map.get(int(e["SourceNodeID"])), id_map.get(int(e["TargetNodeID"]))
        if s is None or t is None:
            continue
        copy = {k: v for k, v in e.items()
                if k not in ("BoardEdgeID", "BoardID", "ExternalID", "ROWID",
                             "CreatedAt", "UpdatedAt", "DeletedAt", "SourceNodeID",
                             "TargetNodeID")}
        copy.update({"BoardID": new_id, "SourceNodeID": s, "TargetNodeID": t})
        copy.setdefault("CreatedBy", actor)
        repo.create("BoardEdge", copy)
    for a in repo.list_by_board("BoardAnnotation", board_id):
        copy = {k: v for k, v in a.items()
                if k not in ("BoardAnnotationID", "BoardID", "ExternalID", "ROWID",
                             "CreatedAt", "UpdatedAt", "DeletedAt")}
        copy["BoardID"] = new_id
        copy.setdefault("CreatedBy", actor)
        repo.create("BoardAnnotation", copy)
    repo.append_activity(new_id, actor, "board.branch", target_type="board",
                         target_id=new_id, diff={"parent_board_id": board_id},
                         request_id=_req_id())
    repo.append_activity(board_id, actor, "board.branched", target_type="board",
                         target_id=new_id, diff={"child_board_id": new_id},
                         request_id=_req_id())
    return get_board(new_id, actor, role)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------
def add_node(board_id: int, req: NodeCreate, actor: str, role: str, *,
             idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    if req.node_kind not in references.NODE_KINDS:
        raise BoardValidationError(f"unknown node_kind '{req.node_kind}'")
    style = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")

    ref_table = req.ref_table
    ref_id = req.ref_id
    label = (req.label or "").strip()
    snapshot: dict[str, Any] = {}
    source_version = source_hash = None
    canonical_entity_id = None

    if ref_table:
        if not references.is_whitelisted(ref_table):
            raise BoardValidationError(
                f"ref_table '{ref_table}' is not a supported object type")
        hy = references.hydrate(ref_table, ref_id, requested_kind=req.node_kind)
        if hy.exists is False:
            raise BoardValidationError(
                f"referenced object {ref_table}:{ref_id} was not found")
        label = label or hy.label
        snapshot = hy.snapshot
        source_version, source_hash = hy.source_version, hy.source_hash
        canonical_entity_id = hy.canonical_entity_id
        node_kind = hy.node_kind
    else:
        # content node (note/map_extract/etc.): client carries a bounded snapshot
        node_kind = req.node_kind
        snapshot = _check_json_size(req.snapshot, board_schema.MAX_SNAPSHOT_BYTES, "snapshot")

    def apply(b: dict):
        row = {
            "BoardID": board_id, "NodeKind": node_kind, "RefTable": ref_table,
            "RefID": (str(ref_id) if ref_id is not None else None),
            "CanonicalEntityID": canonical_entity_id,
            "Label": label[:board_schema.MAX_LABEL_LEN] or None,
            "PosX": float(req.pos_x), "PosY": float(req.pos_y),
            "Width": req.width, "Height": req.height, "StyleJSON": style,
            "SnapshotJSON": snapshot, "SourceVersion": source_version,
            "SourceHash": source_hash, "CreatedBy": actor,
        }
        node = repo.create("BoardNode", row)
        return "node", int(node["BoardNodeID"]), {"node_kind": node_kind,
                                                  "ref_table": ref_table, "ref_id": ref_id}

    return _mutate(repo, board, actor, role, action="node.add", apply=apply,
                   idem_key=idem_key)


def patch_node(board_id: int, node_id: int, req: NodePatch, actor: str, role: str, *,
               idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    node = repo.get("BoardNode", node_id)
    if node is None or int(node.get("BoardID", -1)) != board_id or node.get("DeletedAt"):
        raise BoardNotFound(f"Node {node_id} not found on board {board_id}.")
    patch: dict[str, Any] = {}
    for field, col in (("pos_x", "PosX"), ("pos_y", "PosY"),
                       ("width", "Width"), ("height", "Height")):
        val = getattr(req, field)
        if val is not None:
            patch[col] = float(val)
    if req.label is not None:
        patch["Label"] = req.label.strip()[:board_schema.MAX_LABEL_LEN] or None
    if req.style is not None:
        patch["StyleJSON"] = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")
    if req.refresh_snapshot and node.get("RefTable"):
        hy = references.hydrate(node["RefTable"], node.get("RefID"))
        if hy.exists:
            patch.update({"SnapshotJSON": hy.snapshot, "SourceVersion": hy.source_version,
                          "SourceHash": hy.source_hash, "Label": hy.label})
    if not patch:
        raise BoardValidationError("no node fields to update")

    def apply(b: dict):
        repo.update("BoardNode", node_id, patch)
        return "node", node_id, {"fields": list(patch.keys())}

    # a pure move is last-writer-wins (no conflict); semantic edits use versions
    enforce = (not req.is_move_only) and req.expected_version is not None
    return _mutate(repo, board, actor, role, action="node.update", apply=apply,
                   idem_key=idem_key, expected_version=req.expected_version,
                   enforce_version=enforce)


def delete_node(board_id: int, node_id: int, actor: str, role: str, *,
                idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    node = repo.get("BoardNode", node_id)
    if node is None or int(node.get("BoardID", -1)) != board_id or node.get("DeletedAt"):
        raise BoardNotFound(f"Node {node_id} not found on board {board_id}.")

    def apply(b: dict):
        repo.soft_delete("BoardNode", node_id)
        # cascade: soft-delete edges touching this node
        removed = 0
        for e in repo.list_by_board("BoardEdge", board_id):
            if int(e["SourceNodeID"]) == node_id or int(e["TargetNodeID"]) == node_id:
                repo.soft_delete("BoardEdge", int(e["BoardEdgeID"]))
                removed += 1
        return "node", node_id, {"cascaded_edges": removed}

    return _mutate(repo, board, actor, role, action="node.delete", apply=apply,
                   idem_key=idem_key)


# ---------------------------------------------------------------------------
# edges
# ---------------------------------------------------------------------------
def _node_on_board(repo: BoardRepo, board_id: int, node_id: int) -> dict:
    n = repo.get("BoardNode", node_id)
    if n is None or int(n.get("BoardID", -1)) != board_id or n.get("DeletedAt"):
        raise BoardValidationError(f"node {node_id} is not on board {board_id}")
    return n


def add_edge(board_id: int, req: EdgeCreate, actor: str, role: str, *,
             idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    edge_class = _require_enum(req.edge_class, EDGE_CLASSES, "edge_class")
    if edge_class == "evidence":
        raise BoardValidationError(
            "Evidence edges are imported from verified source data (Search Around / "
            "subgraph import), never drawn by hand. Draw a hypothesis edge instead.")
    # hypothesis edge: rationale is mandatory (the officer's 'why')
    rationale = (req.rationale or "").strip()
    if not rationale:
        raise BoardValidationError(
            "A hypothesis edge requires a rationale (the reasoning behind the link).")
    _node_on_board(repo, board_id, req.source_node_id)
    _node_on_board(repo, board_id, req.target_node_id)
    if req.source_node_id == req.target_node_id:
        raise BoardValidationError("an edge cannot connect a node to itself")
    style = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")

    def apply(b: dict):
        row = {
            "BoardID": board_id, "SourceNodeID": req.source_node_id,
            "TargetNodeID": req.target_node_id, "EdgeClass": "hypothesis",
            "Label": (req.label or "").strip() or None,
            "RelationshipType": (req.relationship_type or "").strip() or None,
            "Directed": bool(req.directed), "Confidence": req.confidence,
            "Rationale": rationale, "EvidenceCaseID": None, "SourceRecordID": None,
            "StyleJSON": style, "PromotedStatus": None, "PromotedRef": None,
            "CreatedBy": actor,
        }
        edge = repo.create("BoardEdge", row)
        return "edge", int(edge["BoardEdgeID"]), {"edge_class": "hypothesis",
                                                  "source": req.source_node_id,
                                                  "target": req.target_node_id}

    return _mutate(repo, board, actor, role, action="edge.add", apply=apply,
                   idem_key=idem_key)


def patch_edge(board_id: int, edge_id: int, req: EdgePatch, actor: str, role: str, *,
               idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    edge = repo.get("BoardEdge", edge_id)
    if edge is None or int(edge.get("BoardID", -1)) != board_id or edge.get("DeletedAt"):
        raise BoardNotFound(f"Edge {edge_id} not found on board {board_id}.")
    if edge.get("EdgeClass") == "evidence":
        raise BoardConflict(
            "Evidence edges are read-only (imported from verified source data). "
            "They cannot be edited; add or edit a hypothesis edge instead.")
    patch: dict[str, Any] = {}
    if req.label is not None:
        patch["Label"] = req.label.strip() or None
    if req.relationship_type is not None:
        patch["RelationshipType"] = req.relationship_type.strip() or None
    if req.directed is not None:
        patch["Directed"] = bool(req.directed)
    if req.confidence is not None:
        patch["Confidence"] = req.confidence
    if req.rationale is not None:
        r = req.rationale.strip()
        if not r:
            raise BoardValidationError("rationale cannot be blanked on a hypothesis edge")
        patch["Rationale"] = r
    if req.style is not None:
        patch["StyleJSON"] = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")
    if not patch:
        raise BoardValidationError("no edge fields to update")

    def apply(b: dict):
        repo.update("BoardEdge", edge_id, patch)
        return "edge", edge_id, {"fields": list(patch.keys())}

    return _mutate(repo, board, actor, role, action="edge.update", apply=apply,
                   idem_key=idem_key, expected_version=req.expected_version,
                   enforce_version=req.expected_version is not None)


def delete_edge(board_id: int, edge_id: int, actor: str, role: str, *,
                idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    edge = repo.get("BoardEdge", edge_id)
    if edge is None or int(edge.get("BoardID", -1)) != board_id or edge.get("DeletedAt"):
        raise BoardNotFound(f"Edge {edge_id} not found on board {board_id}.")

    def apply(b: dict):
        repo.soft_delete("BoardEdge", edge_id)
        return "edge", edge_id, {"edge_class": edge.get("EdgeClass")}

    return _mutate(repo, board, actor, role, action="edge.delete", apply=apply,
                   idem_key=idem_key)


# ---------------------------------------------------------------------------
# annotations
# ---------------------------------------------------------------------------
def add_annotation(board_id: int, req: AnnotationCreate, actor: str, role: str, *,
                   idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    kind = _require_enum(req.kind, ANNOTATION_KINDS, "kind")
    geometry = _check_json_size(req.geometry, board_schema.MAX_JSON_BYTES, "geometry")
    style = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")
    content = (req.content or "")[:board_schema.MAX_CONTENT_LEN] or None

    def apply(b: dict):
        row = {"BoardID": board_id, "Kind": kind, "Content": content,
               "GeometryJSON": geometry, "StyleJSON": style, "CreatedBy": actor}
        ann = repo.create("BoardAnnotation", row)
        return "annotation", int(ann["BoardAnnotationID"]), {"kind": kind}

    return _mutate(repo, board, actor, role, action="annotation.add", apply=apply,
                   idem_key=idem_key)


def patch_annotation(board_id: int, annotation_id: int, req: AnnotationPatch,
                     actor: str, role: str, *, idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    ann = repo.get("BoardAnnotation", annotation_id)
    if ann is None or int(ann.get("BoardID", -1)) != board_id or ann.get("DeletedAt"):
        raise BoardNotFound(f"Annotation {annotation_id} not found on board {board_id}.")
    patch: dict[str, Any] = {}
    if req.content is not None:
        patch["Content"] = req.content[:board_schema.MAX_CONTENT_LEN] or None
    if req.geometry is not None:
        patch["GeometryJSON"] = _check_json_size(req.geometry, board_schema.MAX_JSON_BYTES, "geometry")
    if req.style is not None:
        patch["StyleJSON"] = _check_json_size(req.style, board_schema.MAX_JSON_BYTES, "style")
    if not patch:
        raise BoardValidationError("no annotation fields to update")

    def apply(b: dict):
        repo.update("BoardAnnotation", annotation_id, patch)
        return "annotation", annotation_id, {"fields": list(patch.keys())}

    return _mutate(repo, board, actor, role, action="annotation.update", apply=apply,
                   idem_key=idem_key, expected_version=req.expected_version,
                   enforce_version=req.expected_version is not None)


def delete_annotation(board_id: int, annotation_id: int, actor: str, role: str, *,
                      idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    ann = repo.get("BoardAnnotation", annotation_id)
    if ann is None or int(ann.get("BoardID", -1)) != board_id or ann.get("DeletedAt"):
        raise BoardNotFound(f"Annotation {annotation_id} not found on board {board_id}.")

    def apply(b: dict):
        repo.soft_delete("BoardAnnotation", annotation_id)
        return "annotation", annotation_id, {}

    return _mutate(repo, board, actor, role, action="annotation.delete", apply=apply,
                   idem_key=idem_key)


# ---------------------------------------------------------------------------
# collaborators (board_share)
# ---------------------------------------------------------------------------
def list_collaborators(board_id: int, actor: str, role: str) -> list[BoardCollaboratorOut]:
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    return [_collab_out(c) for c in repo.list_by_board("BoardCollaborator", board_id)]


def add_collaborator(board_id: int, req: CollaboratorAdd, actor: str, role: str, *,
                     idem_key: Optional[str] = None) -> MutationResult:
    from .schemas import COLLAB_ROLES
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_enum(req.role, COLLAB_ROLES, "role")
    # out-of-scope share check: warn/block sharing beyond the case/unit scope
    board_unit = _int(board.get("UnitID"))
    board_dist = _int(board.get("DistrictID"))
    out_of_scope = False
    if board_unit is not None and req.unit_id is not None and req.unit_id != board_unit:
        out_of_scope = True
    if board_dist is not None and req.district_id is not None and req.district_id != board_dist:
        out_of_scope = True
    if out_of_scope and not req.acknowledge_out_of_scope:
        raise BoardConflict(
            "This share is beyond the board's case/unit scope. Re-submit with "
            "acknowledge_out_of_scope=true to proceed (the wider share is audited).")

    existing = next((c for c in repo.list_by_board("BoardCollaborator", board_id,
                                                    include_deleted=True)
                     if c.get("Actor") == req.actor), None)

    def apply(b: dict):
        if existing:
            repo.update("BoardCollaborator", int(existing["BoardCollaboratorID"]),
                        {"Role": req.role, "EmployeeID": req.employee_id,
                         "DeletedAt": None, "AddedBy": actor})
            cid = int(existing["BoardCollaboratorID"])
        else:
            row = {"BoardID": board_id, "Actor": req.actor, "EmployeeID": req.employee_id,
                   "Role": req.role, "AddedBy": actor}
            c = repo.create("BoardCollaborator", row)
            cid = int(c["BoardCollaboratorID"])
        return "collaborator", cid, {"actor": req.actor, "role": req.role,
                                     "out_of_scope": out_of_scope}

    return _mutate(repo, board, actor, role, action="collaborator.add", apply=apply,
                   idem_key=idem_key)


def remove_collaborator(board_id: int, collaborator_id: int, actor: str, role: str, *,
                        idem_key: Optional[str] = None) -> MutationResult:
    repo = board_repo()
    board = _load_board(repo, board_id)
    c = repo.get("BoardCollaborator", collaborator_id)
    if c is None or int(c.get("BoardID", -1)) != board_id or c.get("DeletedAt"):
        raise BoardNotFound(f"Collaborator {collaborator_id} not found on board {board_id}.")

    def apply(b: dict):
        repo.soft_delete("BoardCollaborator", collaborator_id)
        return "collaborator", collaborator_id, {"actor": c.get("Actor")}

    return _mutate(repo, board, actor, role, action="collaborator.remove", apply=apply,
                   idem_key=idem_key)


# ---------------------------------------------------------------------------
# activity / table / timeline / references
# ---------------------------------------------------------------------------
def activity(board_id: int, after_id: int, actor: str, role: str, *,
             limit: int = 500) -> ActivityResponse:
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    rows = repo.activity_after(board_id, after_id, limit=limit)
    return ActivityResponse(
        board_id=board_id, after_id=after_id,
        latest_activity_id=repo.latest_activity_id(board_id),
        count=len(rows), items=[_activity_out(a) for a in rows])


def table(board_id: int, actor: str, role: str) -> TableResponse:
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    node_rows: list[TableRow] = []
    for n in repo.list_by_board("BoardNode", board_id):
        node_rows.append(TableRow(
            kind=n.get("NodeKind", "note"), id=int(n["BoardNodeID"]), label=n.get("Label"),
            detail={"ref_table": n.get("RefTable"), "ref_id": n.get("RefID"),
                    "source_version": n.get("SourceVersion")}))
    edge_rows: list[TableRow] = []
    ev = hy = 0
    for e in repo.list_by_board("BoardEdge", board_id):
        cls = e.get("EdgeClass", "hypothesis")
        ev += cls == "evidence"
        hy += cls == "hypothesis"
        edge_rows.append(TableRow(
            kind=cls, id=int(e["BoardEdgeID"]), label=e.get("Label"),
            detail={"source": int(e["SourceNodeID"]), "target": int(e["TargetNodeID"]),
                    "relationship_type": e.get("RelationshipType"),
                    "confidence": e.get("Confidence"), "rationale": e.get("Rationale"),
                    "source_record_id": e.get("SourceRecordID")}))
    return TableResponse(board_id=board_id, nodes=node_rows, edges=edge_rows,
                         node_count=len(node_rows), edge_count=len(edge_rows),
                         evidence_edge_count=ev, hypothesis_edge_count=hy)


def timeline(board_id: int, actor: str, role: str, *,
             window_start: Optional[str] = None,
             window_end: Optional[str] = None) -> TimelineResponse:
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    events: list[TimelineEvent] = []
    for a in repo.activity_after(board_id, 0, limit=5000):
        at = a.get("CreatedAt")
        if window_start and at and at < window_start:
            continue
        if window_end and at and at > window_end:
            continue
        events.append(TimelineEvent(
            board_activity_id=int(a["BoardActivityID"]), at=at,
            actor=a.get("Actor", ""), action=a.get("Action", ""),
            target_type=a.get("TargetType"), target_id=a.get("TargetID"),
            summary=f"{a.get('Actor','?')} {a.get('Action','?')} "
                    f"{a.get('TargetType') or ''} {a.get('TargetID') or ''}".strip()))
    return TimelineResponse(board_id=board_id, count=len(events),
                            window_start=window_start, window_end=window_end,
                            events=events)


def node_diffs(board_id: int, actor: str, role: str) -> list[NodeDiffOut]:
    """Live-vs-snapshot difference for each object-backed node."""
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=False)
    out: list[NodeDiffOut] = []
    for n in repo.list_by_board("BoardNode", board_id):
        if not n.get("RefTable"):
            continue
        pinned = _json(n.get("SnapshotJSON"))
        d = references.diff_reference(pinned, n.get("SourceHash"),
                                      n.get("RefTable"), n.get("RefID"))
        out.append(NodeDiffOut(
            board_node_id=int(n["BoardNodeID"]), status=d["status"],
            changed_fields=d.get("changed_fields", []), pinned_snapshot=pinned,
            live_snapshot=d.get("live_snapshot", {}), detail=d.get("detail")))
    return out


def get_reference(ref_table: str, ref_id: str) -> ReferenceOut:
    """Hydrate a whitelisted reference + reverse lookup of referencing boards."""
    if not references.is_whitelisted(ref_table):
        raise BoardValidationError(
            f"ref_table '{ref_table}' is not a supported object type")
    hy = references.hydrate(ref_table, ref_id)
    repo = board_repo()
    board_ids = sorted({int(r["BoardID"]) for r in repo.references_to(ref_table, ref_id)})
    return ReferenceOut(**hy.as_dict(), referencing_board_ids=board_ids)


# ---------------------------------------------------------------------------
# Search Around / subgraph import (Prompt 16 §F)
# ---------------------------------------------------------------------------
def _entitygraph_for_canonical(canonical_entity_id: int) -> Optional[int]:
    from .. import db
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT "EntityID" FROM "EntityGraph" '
                            'WHERE "CanonicalEntityID"=%s LIMIT 1', (canonical_entity_id,))
                r = cur.fetchone()
        return int(r[0]) if r else None
    except Exception:  # noqa: BLE001
        return None


def _create_evidence_node(repo: BoardRepo, board_id: int, entity_id: int,
                          label: Optional[str], entity_type: Optional[str],
                          pos_x: float, pos_y: float, actor: str) -> int:
    hy = references.hydrate("EntityGraph", str(entity_id), requested_kind="entity")
    node_kind = _ENTITY_KIND.get((entity_type or "").lower(), hy.node_kind or "entity")
    row = {
        "BoardID": board_id, "NodeKind": node_kind, "RefTable": "EntityGraph",
        "RefID": str(entity_id),
        "CanonicalEntityID": hy.canonical_entity_id,
        "Label": (label or hy.label or f"Entity {entity_id}")[:board_schema.MAX_LABEL_LEN],
        "PosX": float(pos_x), "PosY": float(pos_y), "Width": None, "Height": None,
        "StyleJSON": {"imported": True, "entity_type": entity_type},
        "SnapshotJSON": hy.snapshot, "SourceVersion": hy.source_version,
        "SourceHash": hy.source_hash, "CreatedBy": actor,
    }
    return int(repo.create("BoardNode", row)["BoardNodeID"])


def _create_evidence_edge(repo: BoardRepo, board_id: int, source_node: int,
                          target_node: int, e: dict, actor: str) -> int:
    row = {
        "BoardID": board_id, "SourceNodeID": source_node, "TargetNodeID": target_node,
        "EdgeClass": "evidence",           # imported, read-only
        "Label": e.get("relationship_type"),
        "RelationshipType": e.get("relationship_type"), "Directed": False,
        "Confidence": e.get("confidence"), "Rationale": None, "EvidenceCaseID": None,
        "SourceRecordID": f"NetworkEdge:{e.get('edge_id')}",
        "StyleJSON": {"verified": True, "weight": e.get("weight")},
        "PromotedStatus": None, "PromotedRef": None, "CreatedBy": actor,
    }
    return int(repo.create("BoardEdge", row)["BoardEdgeID"])


def search_around(board_id: int, req: SearchAroundRequest, actor: str, role: str, *,
                  idem_key: Optional[str] = None) -> SearchAroundResult:
    import math
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=not req.preview)

    center = (0.0, 0.0)
    focal_entity = req.entity_id
    if req.node_id:
        fn = repo.get("BoardNode", req.node_id)
        if fn is None or int(fn.get("BoardID", -1)) != board_id or fn.get("DeletedAt"):
            raise BoardValidationError(f"focal node {req.node_id} is not on this board")
        center = (float(fn.get("PosX") or 0.0), float(fn.get("PosY") or 0.0))
        if fn.get("RefTable") == "EntityGraph" and fn.get("RefID"):
            focal_entity = _int(fn.get("RefID"))
        elif fn.get("CanonicalEntityID"):
            focal_entity = _entitygraph_for_canonical(int(fn["CanonicalEntityID"])) or focal_entity
    if not focal_entity:
        raise BoardValidationError(
            "Provide node_id (an EntityGraph-backed node) or entity_id to expand around.")

    data = searcharound.expand(int(focal_entity), req.hops, req.max_neighbors,
                               types=req.types, time_from=req.time_from,
                               time_to=req.time_to)

    existing_by_entity: dict[int, int] = {}
    for n in repo.list_by_board("BoardNode", board_id):
        if n.get("RefTable") == "EntityGraph" and n.get("RefID"):
            eid = _int(n.get("RefID"))
            if eid is not None:
                existing_by_entity[eid] = int(n["BoardNodeID"])

    neighbors = [SearchAroundNeighbor(
        entity_id=nb["entity_id"], label=nb.get("label"),
        entity_type=nb.get("entity_type"), distance=nb.get("distance"),
        relationship_type=nb.get("relationship_type"), weight=nb.get("weight", 0.0),
        verified=nb.get("verified", True),
        already_on_board=nb["entity_id"] in existing_by_entity)
        for nb in data["neighbors"]]

    ai = AiResult(
        answer=data["answer"], confidence=1.0 if data.get("exists") else 0.0,
        source_record_ids=[f"EntityGraph:{focal_entity}"]
        + [f"EntityGraph:{nb['entity_id']}" for nb in data["neighbors"][:50]],
        reasoning_summary=data["reasoning"], model_version=data["model"])
    result = SearchAroundResult(
        result=ai, focal_entity=int(focal_entity), hops=data["hops"],
        max_neighbors=data["max_neighbors"], node_count=data["node_count"],
        edge_count=data["edge_count"], neighbors=neighbors,
        latency_ms=data["latency_ms"], cached=data["cached"])

    if req.preview:
        return result

    def apply(b: dict):
        entity_to_node = dict(existing_by_entity)
        if int(focal_entity) not in entity_to_node:
            entity_to_node[int(focal_entity)] = _create_evidence_node(
                repo, board_id, int(focal_entity), data.get("focal_label"), None,
                center[0], center[1], actor)
        added_nodes = added_edges = 0
        n_nb = max(1, len(data["neighbors"]))
        for i, nb in enumerate(data["neighbors"]):
            eid = int(nb["entity_id"])
            if eid in entity_to_node:
                continue
            angle = (2 * math.pi * i) / n_nb
            px = center[0] + 240.0 * math.cos(angle)
            py = center[1] + 240.0 * math.sin(angle)
            entity_to_node[eid] = _create_evidence_node(
                repo, board_id, eid, nb.get("label"), nb.get("entity_type"), px, py, actor)
            added_nodes += 1
        existing_edges = {(int(e["SourceNodeID"]), int(e["TargetNodeID"]))
                          for e in repo.list_by_board("BoardEdge", board_id)}
        for e in data["edges"]:
            sn = entity_to_node.get(int(e["source"]))
            tn = entity_to_node.get(int(e["target"]))
            if sn is None or tn is None:
                continue
            if (sn, tn) in existing_edges or (tn, sn) in existing_edges:
                continue
            _create_evidence_edge(repo, board_id, sn, tn, e, actor)
            existing_edges.add((sn, tn))
            added_edges += 1
        return "subgraph", int(focal_entity), {
            "nodes_added": added_nodes, "edges_added": added_edges,
            "hops": data["hops"], "focal_entity": int(focal_entity)}

    result.imported = _mutate(repo, board, actor, role, action="subgraph.import",
                              apply=apply, idem_key=idem_key)
    return result


# ---------------------------------------------------------------------------
# Seed-a-subgraph (send-to-board UX): pin an object AND populate its network
# ---------------------------------------------------------------------------
def _resolve_node_entity(repo: BoardRepo, board_id: int, node_id: int) -> Optional[int]:
    """Best-effort map a board node to its canonical EntityGraph id (or None)."""
    n = repo.get("BoardNode", node_id)
    if n is None or int(n.get("BoardID", -1)) != board_id or n.get("DeletedAt"):
        return None
    if n.get("RefTable") == "EntityGraph" and n.get("RefID") is not None:
        return _int(n.get("RefID"))
    if n.get("CanonicalEntityID"):
        return _entitygraph_for_canonical(int(n["CanonicalEntityID"]))
    return None


def _create_case_party_edge(repo: BoardRepo, board_id: int, case_node: int,
                            entity_node: int, role: Optional[str],
                            case_master_id: Optional[int], actor: str) -> int:
    rel = (role or "party").strip().lower().replace(" ", "_") or "party"
    row = {
        "BoardID": board_id, "SourceNodeID": case_node, "TargetNodeID": entity_node,
        "EdgeClass": "evidence",                     # structural fact from the FIR
        "Label": (role or "party"), "RelationshipType": rel, "Directed": True,
        "Confidence": None, "Rationale": None,
        "EvidenceCaseID": case_master_id, "SourceRecordID": f"CaseParty:{case_master_id}",
        "StyleJSON": {"verified": True, "case_seed": True}, "PromotedStatus": None,
        "PromotedRef": None, "CreatedBy": actor,
    }
    return int(repo.create("BoardEdge", row)["BoardEdgeID"])


def seed_reference(board_id: int, req: SeedRequest, actor: str, role: str, *,
                   idem_key: Optional[str] = None) -> SeedResult:
    """Pin the primary object, then populate its immediate network.

    * CaseMaster -> add the case node + an evidence node per involved party
      (accused/victim/...) with an evidence edge, then expand the strongest party.
    * Entity/canonical-backed -> add the node + Search-Around its neighbourhood.
    * Anything else (or nothing resolvable) -> just the primary node (graceful).
    """
    import math
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=True)
    _ensure_not_locked(board)

    center = (480.0, 320.0)
    primary = add_node(board_id, NodeCreate(
        node_kind=req.node_kind or "entity", ref_table=req.ref_table,
        ref_id=req.ref_id, label=req.label, pos_x=center[0], pos_y=center[1]),
        actor, role, idem_key=(f"{idem_key}:primary" if idem_key else None))
    primary_node_id = int(primary.target_id) if primary.target_id else None
    board = _load_board(repo, board_id)                 # refresh Version

    nodes_added = edges_added = 0
    focal_entity: Optional[int] = None
    detail = "Pinned reference."

    if req.ref_table == "CaseMaster" and primary_node_id is not None:
        try:
            parties = searcharound.entities_for_case(_int(req.ref_id) or 0,
                                                      limit=req.max_neighbors)
        except Exception:  # noqa: BLE001 — party lookup is best-effort
            parties = []
        if parties:
            existing = {_int(n.get("RefID")): int(n["BoardNodeID"])
                        for n in repo.list_by_board("BoardNode", board_id)
                        if n.get("RefTable") == "EntityGraph" and n.get("RefID")}

            def apply(b: dict):
                nonlocal nodes_added, edges_added, focal_entity
                n_p = max(1, len(parties))
                for i, pt in enumerate(parties):
                    eid = int(pt["entity_id"])
                    if eid in existing:
                        pnode = existing[eid]
                    else:
                        ang = (2 * math.pi * i) / n_p
                        px = center[0] + 260.0 * math.cos(ang)
                        py = center[1] + 260.0 * math.sin(ang)
                        pnode = _create_evidence_node(repo, board_id, eid,
                                                      pt.get("label"), pt.get("entity_type"),
                                                      px, py, actor)
                        existing[eid] = pnode
                        nodes_added += 1
                    _create_case_party_edge(repo, board_id, primary_node_id, pnode,
                                            pt.get("role"), _int(req.ref_id), actor)
                    edges_added += 1
                    if focal_entity is None:
                        focal_entity = eid
                return "subgraph", _int(req.ref_id), {
                    "case_master_id": _int(req.ref_id), "parties_added": nodes_added,
                    "party_edges": edges_added}

            try:
                _mutate(repo, board, actor, role, action="subgraph.seed", apply=apply,
                        idem_key=(f"{idem_key}:parties" if idem_key else None))
                detail = f"Seeded {nodes_added} involved parties from the FIR."
            except Exception:  # noqa: BLE001 — enrichment best-effort; the case node stands
                detail = "Pinned the case (party enrichment unavailable)."
    elif primary_node_id is not None:
        try:
            focal_entity = _resolve_node_entity(repo, board_id, primary_node_id)
        except Exception:  # noqa: BLE001 — resolution best-effort
            focal_entity = None

    expanded = False
    if req.expand and focal_entity:
        try:
            sa = search_around(board_id, SearchAroundRequest(
                entity_id=int(focal_entity), hops=req.hops,
                max_neighbors=req.max_neighbors, preview=False), actor, role)
            if sa.imported is not None:
                expanded = True
                nodes_added += sa.node_count and 0  # counts tracked in the import
                detail += f" Expanded {len(sa.neighbors)} verified neighbour(s)."
        except Exception:  # noqa: BLE001 — expansion is best-effort; the pinned network stands
            pass

    return SeedResult(board_id=board_id, primary_node_id=primary_node_id,
                      focal_entity=focal_entity, nodes_added=nodes_added,
                      edges_added=edges_added, expanded=expanded, detail=detail)


# ---------------------------------------------------------------------------
# Path Finder: shortest associative path between two board nodes (as evidence)
# ---------------------------------------------------------------------------
def find_path(board_id: int, req: PathRequest, actor: str, role: str, *,
              idem_key: Optional[str] = None) -> BoardPathResult:
    import math
    repo = board_repo()
    board = _load_board(repo, board_id)
    _require_access(repo, board, actor, role, write=True)
    _ensure_not_locked(board)

    src = _resolve_node_entity(repo, board_id, req.source_node_id)
    tgt = _resolve_node_entity(repo, board_id, req.target_node_id)
    if not src or not tgt:
        raise BoardValidationError(
            "Path Finder needs two entity-backed nodes (person/vehicle/phone/"
            "account/location). One of the selected nodes has no graph entity.")
    if int(src) == int(tgt):
        raise BoardValidationError("Pick two different nodes to find a path.")

    from ..graph import service as graph_service
    pr = graph_service.path(int(src), int(tgt))
    entity_path = [n.entity_id for n in pr.nodes] if pr.found else []
    edge_lookup = {(int(e.source), int(e.target)): e for e in pr.edges}
    edge_lookup.update({(int(e.target), int(e.source)): e for e in pr.edges})
    label_by_entity = {n.entity_id: (n.label, n.entity_type) for n in pr.nodes}

    nodes_added = edges_added = 0
    node_ids: list[int] = []
    imported: Optional[MutationResult] = None

    if pr.found and entity_path:
        existing = {_int(n.get("RefID")): int(n["BoardNodeID"])
                    for n in repo.list_by_board("BoardNode", board_id)
                    if n.get("RefTable") == "EntityGraph" and n.get("RefID")}

        def apply(b: dict):
            nonlocal nodes_added, edges_added, node_ids
            base_x, base_y = 200.0, 200.0
            for i, eid in enumerate(entity_path):
                if eid in existing:
                    nid = existing[eid]
                else:
                    lbl, etype = label_by_entity.get(eid, (None, None))
                    nid = _create_evidence_node(repo, board_id, int(eid), lbl, etype,
                                                base_x + i * 240.0, base_y, actor)
                    existing[eid] = nid
                    nodes_added += 1
                node_ids.append(nid)
            present = {(int(e["SourceNodeID"]), int(e["TargetNodeID"]))
                       for e in repo.list_by_board("BoardEdge", board_id)}
            for a, c in zip(entity_path, entity_path[1:]):
                sn, tn = existing.get(a), existing.get(c)
                if sn is None or tn is None:
                    continue
                if (sn, tn) in present or (tn, sn) in present:
                    continue
                ge = edge_lookup.get((int(a), int(c)))
                _create_evidence_edge(repo, board_id, sn, tn, {
                    "relationship_type": (ge.relationship_type if ge else "path"),
                    "weight": (ge.weight if ge else None),
                    "confidence": None, "edge_id": (ge.edge_id if ge else None),
                }, actor)
                present.add((sn, tn))
                edges_added += 1
            return "path", int(src), {"source_entity": int(src),
                                      "target_entity": int(tgt),
                                      "hops": pr.hops, "nodes_added": nodes_added,
                                      "edges_added": edges_added}

        imported = _mutate(repo, board, actor, role, action="path.import",
                           apply=apply, idem_key=idem_key)

    return BoardPathResult(result=pr.result, found=pr.found, method=pr.method,
                           hops=pr.hops, entity_path=entity_path, node_ids=node_ids,
                           nodes_added=nodes_added, edges_added=edges_added,
                           imported=imported)
