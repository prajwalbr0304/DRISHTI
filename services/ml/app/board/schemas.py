"""Typed request/response models for the Investigation Board API (Prompt 16).

Field naming is snake_case at the API boundary (as elsewhere in the service);
the service layer maps to the PascalCase Data Store columns. JSON blobs are
size-limited at this boundary (board_schema limits) before anything is stored.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts import AiResult

# ---------------------------------------------------------------------------
# Enums (validated as literals server-side against these tuples)
# ---------------------------------------------------------------------------
BOARD_STATUSES = ("active", "archived", "locked")
BOARD_VISIBILITY = ("private", "shared", "unit")
EDGE_CLASSES = ("evidence", "hypothesis")
ANNOTATION_KINDS = ("sticky", "text", "frame", "freehand")
COLLAB_ROLES = ("owner", "editor", "viewer")


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------
class BoardCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    case_master_id: Optional[int] = Field(None, ge=1)
    visibility: str = "private"
    unit_id: Optional[int] = Field(None, ge=1)
    district_id: Optional[int] = Field(None, ge=1)
    # optional template seed: pin a subgraph from a network selection on create
    seed_entity_id: Optional[int] = Field(None, ge=1)
    seed_hops: int = Field(1, ge=1, le=3)
    seed_max_neighbors: int = Field(10, ge=1, le=50)


class BoardPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    status: Optional[str] = None
    visibility: Optional[str] = None
    expected_version: Optional[int] = Field(None, ge=1)


class BoardSummary(BaseModel):
    board_id: int
    title: str
    description: Optional[str] = None
    owner_actor: str
    case_master_id: Optional[int] = None
    status: str
    visibility: str
    is_locked: bool
    version: int
    parent_board_id: Optional[int] = None
    node_count: int = 0
    edge_count: int = 0
    my_role: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BoardNodeOut(BaseModel):
    board_node_id: int
    board_id: int
    node_kind: str
    ref_table: Optional[str] = None
    ref_id: Optional[str] = None
    canonical_entity_id: Optional[int] = None
    label: Optional[str] = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    width: Optional[float] = None
    height: Optional[float] = None
    style: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    open_in_source: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class BoardEdgeOut(BaseModel):
    board_edge_id: int
    board_id: int
    source_node_id: int
    target_node_id: int
    edge_class: str
    label: Optional[str] = None
    relationship_type: Optional[str] = None
    directed: bool = False
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    evidence_case_id: Optional[int] = None
    source_record_id: Optional[str] = None
    style: dict[str, Any] = Field(default_factory=dict)
    promoted_status: Optional[str] = None
    promoted_ref: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class BoardAnnotationOut(BaseModel):
    board_annotation_id: int
    board_id: int
    kind: str
    content: Optional[str] = None
    geometry: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class BoardCollaboratorOut(BaseModel):
    board_collaborator_id: int
    board_id: int
    actor: str
    employee_id: Optional[int] = None
    role: str
    added_by: Optional[str] = None
    added_at: Optional[str] = None


class BoardActivityOut(BaseModel):
    board_activity_id: int
    board_id: int
    actor: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    diff: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
    created_at: Optional[str] = None


class BoardDetail(BaseModel):
    board: BoardSummary
    nodes: list[BoardNodeOut] = Field(default_factory=list)
    edges: list[BoardEdgeOut] = Field(default_factory=list)
    annotations: list[BoardAnnotationOut] = Field(default_factory=list)
    collaborators: list[BoardCollaboratorOut] = Field(default_factory=list)
    latest_activity_id: int = 0


class BoardListResponse(BaseModel):
    count: int
    items: list[BoardSummary] = Field(default_factory=list)


class MutationResult(BaseModel):
    """Standard envelope every mutating call returns (Prompt 16 §C)."""
    board_id: int
    board_activity_id: int
    version: int
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    idempotent_replay: bool = False


# ---------------------------------------------------------------------------
# Nodes / edges / annotations
# ---------------------------------------------------------------------------
class NodeCreate(BaseModel):
    node_kind: str
    ref_table: Optional[str] = None
    ref_id: Optional[str] = None
    label: Optional[str] = Field(None, max_length=255)
    pos_x: float = 0.0
    pos_y: float = 0.0
    width: Optional[float] = None
    height: Optional[float] = None
    style: dict[str, Any] = Field(default_factory=dict)
    # For content kinds (note/map_extract) the client carries a bounded snapshot
    # (e.g. a sticky text, a map bbox). NEVER file bytes.
    snapshot: dict[str, Any] = Field(default_factory=dict)


class NodePatch(BaseModel):
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    label: Optional[str] = Field(None, max_length=255)
    style: Optional[dict[str, Any]] = None
    refresh_snapshot: bool = False        # re-pin the live object's snapshot
    expected_version: Optional[int] = None
    is_move_only: bool = False            # last-writer-wins (skip version check)


class EdgeCreate(BaseModel):
    source_node_id: int = Field(..., ge=1)
    target_node_id: int = Field(..., ge=1)
    edge_class: str = "hypothesis"        # evidence edges are import-only
    label: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[str] = Field(None, max_length=120)
    directed: bool = False
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    rationale: Optional[str] = Field(None, max_length=4000)
    style: dict[str, Any] = Field(default_factory=dict)


class EdgePatch(BaseModel):
    label: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[str] = Field(None, max_length=120)
    directed: Optional[bool] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    rationale: Optional[str] = Field(None, max_length=4000)
    style: Optional[dict[str, Any]] = None
    expected_version: Optional[int] = None


class AnnotationCreate(BaseModel):
    kind: str
    content: Optional[str] = Field(None, max_length=4000)
    geometry: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)


class AnnotationPatch(BaseModel):
    content: Optional[str] = Field(None, max_length=4000)
    geometry: Optional[dict[str, Any]] = None
    style: Optional[dict[str, Any]] = None
    expected_version: Optional[int] = None


class CollaboratorAdd(BaseModel):
    actor: str = Field(..., min_length=1, max_length=120)
    role: str = "viewer"
    employee_id: Optional[int] = Field(None, ge=1)
    unit_id: Optional[int] = Field(None, ge=1)      # for out-of-scope share checks
    district_id: Optional[int] = Field(None, ge=1)
    acknowledge_out_of_scope: bool = False          # required to force a wider share


# ---------------------------------------------------------------------------
# Search Around / subgraph import
# ---------------------------------------------------------------------------
class SearchAroundRequest(BaseModel):
    node_id: Optional[int] = Field(None, ge=1)      # expand around an existing node
    entity_id: Optional[int] = Field(None, ge=1)    # or a raw graph entity id
    hops: int = Field(1, ge=1, le=3)                # hard-capped at 3
    max_neighbors: int = Field(15, ge=1, le=50)     # required fan-out cap
    types: Optional[list[str]] = None               # optional entity-type filter
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    preview: bool = True                            # preview-before-add (default)


class SeedRequest(BaseModel):
    """Pin an object AND auto-populate its immediate network on send.

    A CaseMaster seeds its governed parties, legal records, evidence,
    statements, property, digital/financial links and lifecycle/court records
    (read-only evidence edges); an entity seeds its verified neighbourhood.
    Fully graceful: if nothing resolves, only the primary reference node is
    created (never worse than a plain pin)."""
    ref_table: str
    ref_id: str
    node_kind: Optional[str] = None
    label: Optional[str] = Field(None, max_length=255)
    expand: bool = True                             # auto-expand the seeded subgraph
    hops: int = Field(1, ge=1, le=3)
    max_neighbors: int = Field(12, ge=1, le=50)


class SeedResult(BaseModel):
    board_id: int
    primary_node_id: Optional[int] = None
    focal_entity: Optional[int] = None
    nodes_added: int = 0
    edges_added: int = 0
    expanded: bool = False
    detail: str = ""


class PathRequest(BaseModel):
    """Find (and import as evidence) the shortest associative path between two
    entity-backed board nodes."""
    source_node_id: int = Field(..., ge=1)
    target_node_id: int = Field(..., ge=1)


class BoardPathResult(BaseModel):
    result: AiResult
    found: bool
    method: Optional[str] = None
    hops: Optional[int] = None
    entity_path: list[int] = Field(default_factory=list)
    node_ids: list[int] = Field(default_factory=list)
    nodes_added: int = 0
    edges_added: int = 0
    imported: Optional[MutationResult] = None


class SearchAroundNeighbor(BaseModel):
    entity_id: int
    label: Optional[str] = None
    entity_type: Optional[str] = None
    distance: Optional[int] = None
    relationship_type: Optional[str] = None
    weight: float = 0.0
    verified: bool = True                            # verified vs candidate/unverified
    already_on_board: bool = False


class SearchAroundResult(BaseModel):
    result: AiResult
    focal_entity: Optional[int] = None
    hops: int
    max_neighbors: int
    node_count: int
    edge_count: int
    neighbors: list[SearchAroundNeighbor] = Field(default_factory=list)
    latency_ms: int = 0
    cached: bool = False
    # populated only when preview=false (the import committed)
    imported: Optional[MutationResult] = None


# ---------------------------------------------------------------------------
# Promotion / export / helpers
# ---------------------------------------------------------------------------
class PromoteEdgeRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=2000)
    confirm: bool = False                            # fresh-confirmation gate


class ExportRequest(BaseModel):
    format: str = "json"                             # json | pdf
    confirm: bool = False                            # fresh-confirmation gate
    include_activity: bool = True


class ExportOut(BaseModel):
    export_id: str
    board_id: int
    format: str
    object_key: str
    download_url: str
    expires_in_s: int
    sha256: str
    watermark: str
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None


class ReferenceOut(BaseModel):
    ref_table: Optional[str] = None
    ref_id: Optional[str] = None
    node_kind: str
    exists: Optional[bool] = None
    label: str = ""
    canonical_entity_id: Optional[int] = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    source_version: Optional[str] = None
    source_hash: Optional[str] = None
    open_in_source: Optional[str] = None
    detail: Optional[str] = None
    referencing_board_ids: list[int] = Field(default_factory=list)


class NodeDiffOut(BaseModel):
    board_node_id: int
    status: str                                      # live | changed | broken | unavailable
    changed_fields: list[str] = Field(default_factory=list)
    pinned_snapshot: dict[str, Any] = Field(default_factory=dict)
    live_snapshot: dict[str, Any] = Field(default_factory=dict)
    detail: Optional[str] = None


class ActivityResponse(BaseModel):
    board_id: int
    after_id: int
    latest_activity_id: int
    count: int
    items: list[BoardActivityOut] = Field(default_factory=list)


class TableRow(BaseModel):
    kind: str
    id: int
    label: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TableResponse(BaseModel):
    board_id: int
    nodes: list[TableRow] = Field(default_factory=list)
    edges: list[TableRow] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    evidence_edge_count: int = 0
    hypothesis_edge_count: int = 0


class TimelineEvent(BaseModel):
    board_activity_id: int
    at: Optional[str] = None
    actor: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    summary: str = ""


class TimelineResponse(BaseModel):
    board_id: int
    count: int
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    events: list[TimelineEvent] = Field(default_factory=list)
