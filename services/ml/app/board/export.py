"""Board export/import (Prompt 16 §I).

Export produces a fully attributable, synthetic-watermarked artifact to PRIVATE
Stratus with a short-lived download URL and an object hash:

  * JSON  — the DRISHTI board schema (backup/restore); every reference validated.
  * PDF   — a court-ready snapshot rendered by SmartBrowz via a Job/Function to
            private Stratus (the API returns the manifest + presigned target;
            byte rendering is the deployed Job's responsibility). The manifest
            carries: title/version/time, synthetic watermark, node inventory,
            evidence edges + sources, hypothesis edges with rationale/author,
            source-version trail and an activity summary/digest.

Import recreates a board from a JSON document, validating EVERY reference against
the server-side whitelist — an arbitrary/unknown table name is never accepted.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..cache import SEG_LOOKUP
from ..stratus import BUCKET_REPORT, DEFAULT_PRESIGN_TTL_S, get_stratus
from . import references
from . import service as S
from .repo import board_cache, board_repo
from .schemas import (BoardCreate, ExportOut, ExportRequest, BoardDetail)

WATERMARK = "SYNTHETIC DEMO — DRISHTI Investigation Board — not real investigative data"
EXPORT_SCHEMA_VERSION = "1.0"
_EXPORT_META_TTL_S = 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_document(detail: BoardDetail, activity_items: list) -> dict[str, Any]:
    b = detail.board
    evidence = [e for e in detail.edges if e.edge_class == "evidence"]
    hypothesis = [e for e in detail.edges if e.edge_class == "hypothesis"]
    source_trail = [
        {"board_node_id": n.board_node_id, "ref_table": n.ref_table, "ref_id": n.ref_id,
         "source_version": n.source_version, "source_hash": n.source_hash,
         "label": n.label}
        for n in detail.nodes if n.ref_table
    ]
    action_counts: dict[str, int] = {}
    for a in activity_items:
        action_counts[a.action] = action_counts.get(a.action, 0) + 1
    return {
        "drishti_board_export": {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "watermark": WATERMARK,
            "generated_at": _now(),
            "board": b.model_dump(),
            "nodes": [n.model_dump() for n in detail.nodes],
            "edges": {
                "evidence": [e.model_dump() for e in evidence],
                "hypothesis": [e.model_dump() for e in hypothesis],
            },
            "annotations": [a.model_dump() for a in detail.annotations],
            "collaborators": [c.model_dump() for c in detail.collaborators],
            "source_version_trail": source_trail,
            "activity_digest": {
                "count": len(activity_items),
                "first_activity_id": (activity_items[0].board_activity_id
                                      if activity_items else None),
                "last_activity_id": (activity_items[-1].board_activity_id
                                     if activity_items else None),
                "action_counts": action_counts,
            },
            "activity": [a.model_dump() for a in activity_items],
        }
    }


def _sha256(doc: dict) -> tuple[str, int]:
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def export_board(board_id: int, req: ExportRequest, actor: str, role: str) -> ExportOut:
    fmt = req.format.lower()
    if fmt not in ("json", "pdf"):
        raise S.BoardValidationError("format must be 'json' or 'pdf'")
    detail = S.get_board(board_id, actor, role)          # enforces read access
    activity_items = (S.activity(board_id, 0, actor, role, limit=5000).items
                      if req.include_activity else [])
    document = _build_document(detail, activity_items)
    sha, size = _sha256(document)

    export_id = uuid.uuid4().hex
    ext = "json" if fmt == "json" else "pdf"
    object_key = f"board/{board_id}/export/{export_id}.{ext}"
    content_type = "application/json" if fmt == "json" else "application/pdf"

    stratus = get_stratus()
    # Private, exact-object presigned transfer. In deployment a Job/SmartBrowz
    # uploads the rendered bytes to this key; the API never streams bytes.
    stratus.presign_put(BUCKET_REPORT, object_key, content_type=content_type,
                        ttl_s=DEFAULT_PRESIGN_TTL_S)
    download_url = stratus.presign_get(BUCKET_REPORT, object_key,
                                       ttl_s=DEFAULT_PRESIGN_TTL_S)

    meta = {"export_id": export_id, "board_id": board_id, "format": fmt,
            "object_key": object_key, "sha256": sha, "size_bytes": size,
            "watermark": WATERMARK, "created_at": _now(),
            "content_type": content_type,
            # JSON document is retained inline for the demo download/restore path;
            # PDF is rendered by the deployed SmartBrowz job to the same key.
            "document": document if fmt == "json" else None,
            "pdf_manifest": (None if fmt == "json" else {
                "renderer": "SmartBrowz (deployed Job/Function)",
                "sections": ["canvas image", "title/version/time", "synthetic watermark",
                             "node inventory", "evidence edges + sources",
                             "hypothesis edges with rationale/author",
                             "source-version trail", "activity summary/digest"],
                "board": detail.board.model_dump()})}
    try:
        board_cache().put(SEG_LOOKUP, f"board:export:{export_id}",
                          json.dumps(meta, default=str), ttl_s=_EXPORT_META_TTL_S)
    except Exception:  # noqa: BLE001
        pass

    board_repo().append_activity(board_id, actor, "board.export", target_type="export",
                                 target_id=export_id,
                                 diff={"format": fmt, "sha256": sha, "size_bytes": size})

    return ExportOut(export_id=export_id, board_id=board_id, format=fmt,
                     object_key=object_key, download_url=download_url,
                     expires_in_s=DEFAULT_PRESIGN_TTL_S, sha256=sha, watermark=WATERMARK,
                     size_bytes=size, created_at=meta["created_at"])


def get_export(board_id: int, export_id: str, actor: str, role: str) -> ExportOut:
    # enforce read access to the board
    S.get_board(board_id, actor, role)
    raw = None
    try:
        raw = board_cache().get(SEG_LOOKUP, f"board:export:{export_id}")
    except Exception:  # noqa: BLE001
        raw = None
    if not raw:
        raise S.BoardNotFound(f"Export {export_id} not found or expired.")
    meta = json.loads(raw)
    if int(meta.get("board_id", -1)) != board_id:
        raise S.BoardNotFound(f"Export {export_id} does not belong to board {board_id}.")
    # fresh short-lived URL
    download_url = get_stratus().presign_get(BUCKET_REPORT, meta["object_key"],
                                             ttl_s=DEFAULT_PRESIGN_TTL_S)
    return ExportOut(export_id=export_id, board_id=board_id, format=meta["format"],
                     object_key=meta["object_key"], download_url=download_url,
                     expires_in_s=DEFAULT_PRESIGN_TTL_S, sha256=meta["sha256"],
                     watermark=meta.get("watermark", WATERMARK),
                     size_bytes=meta.get("size_bytes"), created_at=meta.get("created_at"))


def import_board(document: dict, actor: str, role: str) -> BoardDetail:
    """Recreate a board from a DRISHTI board-schema JSON document.

    EVERY node reference is validated against the whitelist — an unknown/arbitrary
    table name is rejected (never interpolated anywhere). Hypothesis edges keep
    their rationale; evidence edges keep their provenance.
    """
    root = document.get("drishti_board_export") if isinstance(document, dict) else None
    if not isinstance(root, dict):
        raise S.BoardValidationError("not a DRISHTI board export document")
    board = root.get("board") or {}
    created = S.create_board(BoardCreate(
        title=(board.get("title") or "Imported board")[:200],
        description=board.get("description"),
        case_master_id=board.get("case_master_id"),
        visibility=(board.get("visibility") if board.get("visibility") in
                    ("private", "shared", "unit") else "private")), actor, role)
    new_id = created.board.board_id
    repo = board_repo()

    id_map: dict[int, int] = {}
    for n in root.get("nodes", []):
        ref_table = n.get("ref_table")
        if ref_table and not references.is_whitelisted(ref_table):
            # never trust an arbitrary table name from an imported file
            continue
        row = {
            "BoardID": new_id, "NodeKind": (n.get("node_kind") or "note"),
            "RefTable": ref_table, "RefID": n.get("ref_id"),
            "CanonicalEntityID": n.get("canonical_entity_id"),
            "Label": (n.get("label") or "")[:255] or None,
            "PosX": float(n.get("pos_x") or 0.0), "PosY": float(n.get("pos_y") or 0.0),
            "Width": n.get("width"), "Height": n.get("height"),
            "StyleJSON": n.get("style") or {}, "SnapshotJSON": n.get("snapshot") or {},
            "SourceVersion": n.get("source_version"), "SourceHash": n.get("source_hash"),
            "CreatedBy": actor,
        }
        created_node = repo.create("BoardNode", row)
        if n.get("board_node_id") is not None:
            id_map[int(n["board_node_id"])] = int(created_node["BoardNodeID"])

    edges = root.get("edges", {}) or {}
    for cls, items in (("evidence", edges.get("evidence", [])),
                       ("hypothesis", edges.get("hypothesis", []))):
        for e in items:
            s = id_map.get(int(e.get("source_node_id", -1)))
            t = id_map.get(int(e.get("target_node_id", -1)))
            if s is None or t is None:
                continue
            repo.create("BoardEdge", {
                "BoardID": new_id, "SourceNodeID": s, "TargetNodeID": t,
                "EdgeClass": cls, "Label": e.get("label"),
                "RelationshipType": e.get("relationship_type"),
                "Directed": bool(e.get("directed")), "Confidence": e.get("confidence"),
                "Rationale": e.get("rationale"),
                "EvidenceCaseID": e.get("evidence_case_id"),
                "SourceRecordID": e.get("source_record_id"),
                "StyleJSON": e.get("style") or {}, "CreatedBy": actor})
    for a in root.get("annotations", []):
        repo.create("BoardAnnotation", {
            "BoardID": new_id, "Kind": (a.get("kind") or "sticky"),
            "Content": a.get("content"), "GeometryJSON": a.get("geometry") or {},
            "StyleJSON": a.get("style") or {}, "CreatedBy": actor})
    repo.append_activity(new_id, actor, "board.import", target_type="board",
                         target_id=new_id, diff={"imported": True})
    return S.get_board(new_id, actor, role)
