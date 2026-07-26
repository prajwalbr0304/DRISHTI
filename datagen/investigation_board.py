#!/usr/bin/env python3
"""Deterministic golden fixture for the Investigation Board (Prompt 16 §J).

The board is Data Store-NATIVE (created directly in Catalyst Data Store and
populated by the AppSail board service at runtime), so it is not part of the
PostgreSQL datagen COPY build. This module instead emits a DETERMINISTIC board
document set (the DRISHTI board export schema) that:

  * a demo can load through ``POST /boards/import`` (reference-validated), and
  * the backend tests load to assert board behaviour.

Determinism: fixed content + positions + a locally-computed SHA-256 over each
pinned snapshot (mirrors app.board.references.snapshot_hash) so re-generation is
byte-identical. No ``app`` import (keeps this loadable by path, like ds mapping).

Covered scenarios (Prompt 16 §J):
  * a case board with case / people / phone / vehicle / account / location nodes;
  * imported evidence links (read-only, with provenance);
  * two hypothesis links with rationale;
  * annotations and a frame;
  * collaborator / demo-actor activity;
  * a LOCKED board and its BRANCHED copy;
  * a changed / SUPERSEDED source snapshot (a node whose pinned hash differs from
    the live object) to exercise the live-vs-snapshot difference display.

Run:  python datagen/investigation_board.py   (writes fixtures/golden-001/…)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

GOLDEN_SEED = 42
EXPORT_SCHEMA_VERSION = "1.0"
WATERMARK = "SYNTHETIC DEMO — DRISHTI Investigation Board — not real investigative data"
_T0 = datetime(2025, 3, 1, 9, 0, tzinfo=timezone.utc)


def _ts(minutes: int) -> str:
    return (_T0 + timedelta(minutes=minutes)).isoformat()


def _hash(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _node(nid, kind, ref_table, ref_id, label, x, y, snapshot, *, version="1",
          created="demo.investigating_officer", at=0, superseded=False):
    """A board node. ``superseded`` writes a hash that no longer matches the
    (recomputed) snapshot, so the live-vs-snapshot diff reports 'changed'."""
    src_hash = _hash(snapshot)
    if superseded:
        src_hash = _hash({**snapshot, "_superseded_at_pin": True})
    return {
        "board_node_id": nid, "node_kind": kind, "ref_table": ref_table,
        "ref_id": (str(ref_id) if ref_id is not None else None),
        "canonical_entity_id": None, "label": label, "pos_x": x, "pos_y": y,
        "width": None, "height": None, "style": {}, "snapshot": snapshot,
        "source_version": version, "source_hash": src_hash,
        "created_by": created, "created_at": _ts(at),
    }


def _evidence_edge(eid, s, t, rel, source_record, at=0):
    return {
        "board_edge_id": eid, "source_node_id": s, "target_node_id": t,
        "edge_class": "evidence", "label": rel, "relationship_type": rel,
        "directed": False, "confidence": 1.0, "rationale": None,
        "evidence_case_id": 1024, "source_record_id": source_record,
        "style": {"verified": True}, "promoted_status": None, "promoted_ref": None,
        "created_by": "demo.investigating_officer", "created_at": _ts(at),
    }


def _hypothesis_edge(eid, s, t, rel, rationale, conf, *, directed=True, at=0,
                     author="demo.investigating_officer"):
    return {
        "board_edge_id": eid, "source_node_id": s, "target_node_id": t,
        "edge_class": "hypothesis", "label": rel, "relationship_type": rel,
        "directed": directed, "confidence": conf, "rationale": rationale,
        "evidence_case_id": None, "source_record_id": None,
        "style": {}, "promoted_status": None, "promoted_ref": None,
        "created_by": author, "created_at": _ts(at),
    }


def _primary_board_doc() -> dict:
    # ---- nodes: case + people + phone + vehicle + account + location --------
    nodes = [
        _node(1, "case", "CaseMaster", 1024, "CRIME-2025-1024",
              120, 60, {"CrimeNo": "CRIME-2025-1024", "CaseStatusID": 3,
                        "PoliceStationID": 12}, at=1),
        _node(2, "accused", "EntityGraph", 5001, "Accused A (SYN-PERSON-000123)",
              -160, 220, {"PublicRef": "SYN-PERSON-000123", "EntityType": "person",
                          "Label": "Accused A"}, at=2),
        _node(3, "victim", "EntityGraph", 5002, "Victim B (SYN-PERSON-000155)",
              360, 220, {"PublicRef": "SYN-PERSON-000155", "EntityType": "person",
                         "Label": "Victim B"}, at=3),
        _node(4, "phone", "EntityGraph", 5003, "Phone SYN-DEV-0042",
              -320, 400, {"PublicRef": "SYN-DEV-0042", "EntityType": "phone"}, at=4),
        _node(5, "vehicle", "EntityGraph", 5004, "Vehicle SYN-VEH-0007",
              40, 420, {"PublicRef": "SYN-VEH-0007", "EntityType": "vehicle"}, at=5),
        # account node is intentionally SUPERSEDED (its pinned hash won't match live)
        _node(6, "account", "FinancialAccount", 7001, "Account SYN-ACC-9001",
              360, 420, {"SyntheticReference": "SYN-ACC-9001", "Currency": "INR",
                         "OwnerReviewStatus": "candidate"}, at=6, superseded=True),
        _node(7, "hotspot", "CrimeHotspot", 3001, "Hotspot: Market Rd cluster",
              600, 220, {"Name": "Market Rd cluster", "DistrictID": 5,
                         "Method": "kde"}, at=7),
    ]

    # ---- evidence links (imported, read-only, with provenance) --------------
    edges = [
        _evidence_edge(1, 2, 1, "co_accused", "NetworkEdge:88001", at=8),
        _evidence_edge(2, 2, 4, "uses_device", "NetworkEdge:88002", at=9),
        _evidence_edge(3, 3, 1, "victim_of", "NetworkEdge:88003", at=10),
        # ---- two hypothesis links with rationale ----------------------------
        _hypothesis_edge(4, 2, 6, "funnels_proceeds",
                         "Accused A is the sole signatory when the mule account "
                         "receives the extortion transfers (same login window).",
                         0.65, at=11),
        _hypothesis_edge(5, 2, 5, "controls_vehicle",
                         "The vehicle was seen at three drop points on days the "
                         "accused's phone pinged the same towers.",
                         0.55, at=12, author="demo.crime_analyst"),
    ]

    annotations = [
        {"board_annotation_id": 1, "kind": "sticky",
         "content": "Working theory: A runs the operation; B is a victim-witness.",
         "geometry": {"x": -160, "y": -40}, "style": {"color": "#fef3c7"},
         "created_by": "demo.investigating_officer", "created_at": _ts(13)},
        {"board_annotation_id": 2, "kind": "frame",
         "content": "Financial cluster",
         "geometry": {"x": 320, "y": 380, "w": 380, "h": 220}, "style": {},
         "created_by": "demo.investigating_officer", "created_at": _ts(14)},
    ]

    collaborators = [
        {"board_collaborator_id": 1, "actor": "demo.crime_analyst", "employee_id": None,
         "role": "editor", "added_by": "demo.investigating_officer", "added_at": _ts(15)},
    ]

    activity = [
        {"board_activity_id": i + 1, "actor": a, "action": act,
         "target_type": tt, "target_id": str(ti), "created_at": _ts(i + 1)}
        for i, (a, act, tt, ti) in enumerate([
            ("demo.investigating_officer", "board.create", "board", 1),
            ("demo.investigating_officer", "node.add", "node", 1),
            ("demo.investigating_officer", "node.add", "node", 2),
            ("demo.investigating_officer", "node.add", "node", 3),
            ("demo.investigating_officer", "subgraph.import", "subgraph", 5001),
            ("demo.investigating_officer", "edge.add", "edge", 4),
            ("demo.crime_analyst", "edge.add", "edge", 5),
            ("demo.investigating_officer", "annotation.add", "annotation", 1),
            ("demo.investigating_officer", "collaborator.add", "collaborator", 1),
        ])
    ]

    board = {
        "board_id": 1, "title": "Operation Nightfall — CRIME-2025-1024",
        "description": "Golden fixture case board (synthetic).",
        "owner_actor": "demo.investigating_officer", "case_master_id": 1024,
        "status": "active", "visibility": "shared", "is_locked": False,
        "version": len(activity), "parent_board_id": None,
        "node_count": len(nodes), "edge_count": len(edges),
        "created_at": _ts(1), "updated_at": _ts(len(activity)),
    }
    return {
        "drishti_board_export": {
            "schema_version": EXPORT_SCHEMA_VERSION, "watermark": WATERMARK,
            "generated_at": _ts(len(activity)), "board": board, "nodes": nodes,
            "edges": {"evidence": [e for e in edges if e["edge_class"] == "evidence"],
                      "hypothesis": [e for e in edges if e["edge_class"] == "hypothesis"]},
            "annotations": annotations, "collaborators": collaborators,
            "source_version_trail": [
                {"board_node_id": n["board_node_id"], "ref_table": n["ref_table"],
                 "ref_id": n["ref_id"], "source_version": n["source_version"],
                 "source_hash": n["source_hash"], "label": n["label"]}
                for n in nodes if n["ref_table"]],
            "activity_digest": {"count": len(activity),
                                "first_activity_id": 1,
                                "last_activity_id": len(activity)},
            "activity": activity,
        }
    }


def _locked_and_branch() -> dict:
    """A locked board (filed) + its editable branch (ParentBoardID set)."""
    locked = {
        "board_id": 2, "title": "CRIME-2025-1024 — filed exhibit",
        "description": "Locked for the chargesheet (synthetic).",
        "owner_actor": "demo.sho", "case_master_id": 1024,
        "status": "locked", "visibility": "unit", "is_locked": True,
        "version": 5, "parent_board_id": None,
        "created_at": _ts(20), "updated_at": _ts(30),
    }
    branch = {
        "board_id": 3, "title": "CRIME-2025-1024 — filed exhibit (branch)",
        "description": "Editable branch of the locked exhibit.",
        "owner_actor": "demo.sho", "case_master_id": 1024,
        "status": "active", "visibility": "unit", "is_locked": False,
        "version": 1, "parent_board_id": 2,
        "created_at": _ts(31), "updated_at": _ts(31),
    }
    return {"locked_board": locked, "branch_board": branch,
            "note": "Editing the locked board requires a branch; the locked "
                    "version is never modified."}


def build_board_fixture(seed: int = GOLDEN_SEED) -> dict:
    """The full deterministic golden board fixture object."""
    return {
        "fixture": "investigation-board-golden-001",
        "seed": seed,
        "schema_version": EXPORT_SCHEMA_VERSION,
        "watermark": WATERMARK,
        "primary_board": _primary_board_doc(),
        "locked_and_branch": _locked_and_branch(),
        "scenarios": [
            "case board with case/people/phone/vehicle/account/location nodes",
            "imported evidence links with provenance",
            "two hypothesis links with rationale",
            "annotations and a frame",
            "collaborator + demo-actor activity",
            "locked board + branched copy",
            "changed/superseded source snapshot (node 6)",
        ],
    }


def write_fixture(out_dir: str | Path = None) -> Path:
    root = Path(__file__).resolve().parent
    out = Path(out_dir) if out_dir else root / "fixtures" / "golden-001"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / "investigation_board.json"
    dst.write_text(json.dumps(build_board_fixture(), indent=2) + "\n", encoding="utf-8")
    return dst


if __name__ == "__main__":
    path = write_fixture()
    fx = build_board_fixture()
    root = fx["primary_board"]["drishti_board_export"]
    print(f"wrote {path}")
    print(f"  primary board: {len(root['nodes'])} nodes, "
          f"{len(root['edges']['evidence'])} evidence + "
          f"{len(root['edges']['hypothesis'])} hypothesis edges, "
          f"{len(root['annotations'])} annotations, "
          f"{len(root['collaborators'])} collaborator(s)")
    print(f"  + locked board + branch; superseded snapshot on node 6")
