"""Phase 16 — Investigation Board API behaviour (TestClient).

These run WITHOUT a database (board records are Data Store-native / in-memory).
Tests that need the operational PG (reference hydration, graph Search Around) are
marked @requires_db. The synthetic write guard is forced true so board writes do
not depend on live DB reachability (its DB behaviour is covered elsewhere)."""
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.board import guards
from app.board import repo as board_repo_mod
from conftest import requires_db

client = TestClient(app)

IO = {"X-Role": "investigator", "X-Demo-Actor": "demo.io"}
ANALYST = {"X-Role": "analyst", "X-Demo-Actor": "demo.analyst"}
SUP = {"X-Role": "supervisor", "X-Demo-Actor": "demo.sup"}
POLICY = {"X-Role": "policymaker", "X-Demo-Actor": "demo.pol"}


@pytest.fixture(autouse=True)
def _board_env(monkeypatch):
    board_repo_mod.reset_board_repo()
    # board writes must not depend on live DB reachability in unit tests
    monkeypatch.setattr(guards, "synthetic_db_ok", lambda: True)
    yield
    board_repo_mod.reset_board_repo()


def _new_board(headers=IO, **body):
    body.setdefault("title", "Test Board")
    body.setdefault("visibility", "private")
    r = client.post("/boards", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["board"]["board_id"]


def _content_node(bid, label, headers=IO):
    r = client.post(f"/boards/{bid}/nodes", headers=headers,
                    json={"node_kind": "note", "label": label, "pos_x": 0, "pos_y": 0})
    assert r.status_code == 201, r.text
    return int(r.json()["target_id"])


# --- RBAC / policymaker ------------------------------------------------------
def test_policymaker_denied_everywhere():
    assert client.get("/boards", headers=POLICY).status_code == 403
    assert client.post("/boards", headers=POLICY, json={"title": "x"}).status_code == 403


def test_io_creates_and_reads_own_board():
    bid = _new_board()
    r = client.get(f"/boards/{bid}", headers=IO)
    assert r.status_code == 200
    assert r.json()["board"]["owner_actor"] == "demo.io"


def test_analyst_cannot_read_unshared_board_but_can_when_shared():
    bid = _new_board(headers=IO)
    assert client.get(f"/boards/{bid}", headers=ANALYST).status_code == 403
    # supervisor shares with the analyst (board_share)
    r = client.post(f"/boards/{bid}/collaborators", headers=SUP,
                    json={"actor": "demo.analyst", "role": "editor"})
    assert r.status_code == 201, r.text
    assert client.get(f"/boards/{bid}", headers=ANALYST).status_code == 200


def test_analyst_cannot_share():
    bid = _new_board(headers=IO)
    r = client.post(f"/boards/{bid}/collaborators", headers=ANALYST,
                    json={"actor": "x", "role": "viewer"})
    assert r.status_code == 403


# --- edges: rationale + evidence/hypothesis distinction ----------------------
def test_hypothesis_requires_rationale():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    r = client.post(f"/boards/{bid}/edges", headers=IO,
                    json={"source_node_id": a, "target_node_id": b})
    assert r.status_code == 422


def test_evidence_edge_cannot_be_hand_drawn():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    r = client.post(f"/boards/{bid}/edges", headers=IO,
                    json={"source_node_id": a, "target_node_id": b,
                          "edge_class": "evidence", "rationale": "x"})
    assert r.status_code == 422


def test_evidence_edge_immutable_but_hypothesis_editable():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    # inject an evidence edge directly (as Search Around import would)
    repo = board_repo_mod.board_repo()
    ev = repo.create("BoardEdge", {
        "BoardID": bid, "SourceNodeID": a, "TargetNodeID": b, "EdgeClass": "evidence",
        "RelationshipType": "co_accused", "Directed": False,
        "SourceRecordID": "NetworkEdge:1", "CreatedBy": "demo.io"})
    eid = int(ev["BoardEdgeID"])
    # cannot edit an evidence edge
    assert client.patch(f"/boards/{bid}/edges/{eid}", headers=IO,
                        json={"label": "nope"}).status_code == 409
    # but a hypothesis edge is editable
    hy = client.post(f"/boards/{bid}/edges", headers=IO,
                     json={"source_node_id": a, "target_node_id": b,
                           "rationale": "same handler"}).json()
    hid = int(hy["target_id"])
    assert client.patch(f"/boards/{bid}/edges/{hid}", headers=IO,
                        json={"confidence": 0.8}).status_code == 200


# --- promotion ---------------------------------------------------------------
def test_promote_requires_supervisor_and_confirmation_and_rationale():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    hid = int(client.post(f"/boards/{bid}/edges", headers=IO,
                          json={"source_node_id": a, "target_node_id": b,
                                "rationale": "same device"}).json()["target_id"])
    # IO cannot promote
    assert client.post(f"/boards/{bid}/promote-edge/{hid}", headers=IO,
                       json={"confirm": True}).status_code == 403
    # supervisor without confirm -> 428
    assert client.post(f"/boards/{bid}/promote-edge/{hid}", headers=SUP,
                       json={"confirm": False}).status_code == 428
    # supervisor with confirm -> ok
    ok = client.post(f"/boards/{bid}/promote-edge/{hid}", headers=SUP, json={"confirm": True})
    assert ok.status_code == 200
    # re-promoting -> conflict
    assert client.post(f"/boards/{bid}/promote-edge/{hid}", headers=SUP,
                       json={"confirm": True}).status_code == 409


def test_promotion_blocked_without_rationale():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    # inject a hypothesis edge with an EMPTY rationale (bypass the create guard)
    repo = board_repo_mod.board_repo()
    e = repo.create("BoardEdge", {"BoardID": bid, "SourceNodeID": a, "TargetNodeID": b,
                                  "EdgeClass": "hypothesis", "Rationale": "",
                                  "Directed": False, "CreatedBy": "demo.io"})
    eid = int(e["BoardEdgeID"])
    r = client.post(f"/boards/{bid}/promote-edge/{eid}", headers=SUP, json={"confirm": True})
    assert r.status_code == 422


# --- concurrency + idempotency ----------------------------------------------
def test_optimistic_concurrency_conflict():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    hid = int(client.post(f"/boards/{bid}/edges", headers=IO,
                          json={"source_node_id": a, "target_node_id": b,
                                "rationale": "r"}).json()["target_id"])
    # stale If-Match version -> 409
    r = client.patch(f"/boards/{bid}/edges/{hid}", headers={**IO, "If-Match": "1"},
                     json={"label": "x"})
    assert r.status_code == 409


def test_idempotent_replay_same_activity():
    bid = _new_board()
    key = "k-1"
    a = client.post(f"/boards/{bid}/nodes", headers={**IO, "X-Idempotency-Key": key},
                    json={"node_kind": "note", "label": "C"})
    b = client.post(f"/boards/{bid}/nodes", headers={**IO, "X-Idempotency-Key": key},
                    json={"node_kind": "note", "label": "C"})
    assert a.json()["board_activity_id"] == b.json()["board_activity_id"]
    assert b.json()["idempotent_replay"] is True


# --- locking / branching -----------------------------------------------------
def test_lock_rejects_writes_and_branch_succeeds():
    bid = _new_board(headers=SUP, visibility="unit")
    _content_node(bid, "A", headers=SUP)
    assert client.post(f"/boards/{bid}/lock?confirm=true", headers=SUP).status_code == 200
    # locked board rejects writes
    assert client.post(f"/boards/{bid}/nodes", headers=SUP,
                       json={"node_kind": "note", "label": "late"}).status_code == 423
    # branch succeeds and links the parent, unlocked
    r = client.post(f"/boards/{bid}/branch", headers=SUP)
    assert r.status_code == 201
    child = r.json()["board"]
    assert child["parent_board_id"] == bid and child["is_locked"] is False
    assert len(r.json()["nodes"]) == 1        # nodes copied to the branch


def test_lock_requires_confirmation():
    bid = _new_board(headers=SUP)
    assert client.post(f"/boards/{bid}/lock", headers=SUP, json={}).status_code == 428


# --- out-of-scope share ------------------------------------------------------
def test_out_of_scope_share_blocked_then_acknowledged():
    bid = _new_board(headers=SUP, visibility="unit", unit_id=10)
    blocked = client.post(f"/boards/{bid}/collaborators", headers=SUP,
                          json={"actor": "demo.other", "role": "viewer", "unit_id": 99})
    assert blocked.status_code == 409
    ok = client.post(f"/boards/{bid}/collaborators", headers=SUP,
                     json={"actor": "demo.other", "role": "viewer", "unit_id": 99,
                           "acknowledge_out_of_scope": True})
    assert ok.status_code == 201


# --- activity append-only ----------------------------------------------------
def test_activity_is_recorded_and_append_only():
    bid = _new_board()
    _content_node(bid, "A")
    _content_node(bid, "B")
    act = client.get(f"/boards/{bid}/activity", headers=IO).json()
    assert act["count"] >= 3
    actions = [a["action"] for a in act["items"]]
    assert actions[0] == "board.create"
    # activity ids strictly increasing (replay ordering)
    ids = [a["board_activity_id"] for a in act["items"]]
    assert ids == sorted(ids)
    # repository refuses to mutate/delete an append-only activity row
    repo = board_repo_mod.board_repo()
    import pytest as _pytest
    with _pytest.raises(Exception):
        repo.update("BoardActivity", ids[0], {"Action": "tamper"})
    with _pytest.raises(Exception):
        repo.soft_delete("BoardActivity", ids[0])


def test_after_id_replay_returns_only_new_events():
    bid = _new_board()
    _content_node(bid, "A")
    full = client.get(f"/boards/{bid}/activity", headers=IO).json()
    latest = full["latest_activity_id"]
    _content_node(bid, "B")
    delta = client.get(f"/boards/{bid}/activity", headers=IO, params={"after_id": latest}).json()
    assert delta["count"] == 1
    assert delta["items"][0]["board_activity_id"] > latest


# --- table / timeline helpers ------------------------------------------------
def test_table_and_timeline_helpers():
    bid = _new_board()
    a, b = _content_node(bid, "A"), _content_node(bid, "B")
    client.post(f"/boards/{bid}/edges", headers=IO,
                json={"source_node_id": a, "target_node_id": b, "rationale": "r"})
    t = client.get(f"/boards/{bid}/table", headers=IO).json()
    assert t["node_count"] == 2 and t["hypothesis_edge_count"] == 1 and t["evidence_edge_count"] == 0
    tl = client.get(f"/boards/{bid}/timeline", headers=IO).json()
    assert tl["count"] >= 3


# --- references: whitelist + injection rejection + reverse lookup ------------
def test_arbitrary_ref_table_rejected():
    # injection / unknown table is never accepted
    assert client.get("/boards/references/DROP TABLE users/1", headers=IO).status_code in (404, 422)
    assert client.get("/boards/references/NotAThing/5", headers=IO).status_code in (404, 422)


def test_pinning_unknown_ref_table_rejected():
    bid = _new_board()
    r = client.post(f"/boards/{bid}/nodes", headers=IO,
                    json={"node_kind": "entity", "ref_table": "secret_table", "ref_id": "1"})
    assert r.status_code == 422


def test_reverse_reference_lookup_lists_boards():
    bid = _new_board()
    # pin a whitelisted ref (hydration may be unavailable without a DB, but the
    # node still records the reference)
    r = client.post(f"/boards/{bid}/nodes", headers=IO,
                    json={"node_kind": "case", "ref_table": "CaseMaster", "ref_id": "1024",
                          "label": "CRIME-1024"})
    assert r.status_code == 201, r.text
    ref = client.get("/boards/references/CaseMaster/1024", headers=IO).json()
    assert bid in ref["referencing_board_ids"]


# --- object kinds meta -------------------------------------------------------
def test_object_kinds_meta_excludes_news_event_ref():
    r = client.get("/boards/meta/object-kinds", headers=IO).json()
    assert "case" in r["node_kinds"] and "chat_answer" in r["node_kinds"]
    # news_event is a node kind but NOT a whitelisted ref table (OSINT deferred)
    assert "news_event" not in r["ref_tables"]
    assert "CaseMaster" in r["ref_tables"] and "EntityGraph" in r["ref_tables"]


# --- export ------------------------------------------------------------------
def test_export_requires_confirmation():
    bid = _new_board()
    assert client.post(f"/boards/{bid}/export", headers=IO, json={"format": "json"}).status_code == 428


def test_export_produces_hash_watermark_and_retrievable_url():
    bid = _new_board()
    _content_node(bid, "A")
    r = client.post(f"/boards/{bid}/export", headers=IO, json={"format": "json", "confirm": True})
    assert r.status_code == 201, r.text
    exp = r.json()
    assert len(exp["sha256"]) == 64 and "SYNTHETIC" in exp["watermark"]
    assert exp["expires_in_s"] > 0
    # retrievable via a fresh short-lived URL
    got = client.get(f"/boards/{bid}/export/{exp['export_id']}", headers=IO)
    assert got.status_code == 200 and got.json()["sha256"] == exp["sha256"]


# --- JSON import (reference-validated) ---------------------------------------
def _load_golden_fixture():
    root = Path(__file__).resolve().parents[3]
    mod_path = root / "datagen" / "investigation_board.py"
    spec = importlib.util.spec_from_file_location("drishti_board_fixture", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.build_board_fixture()


def test_import_golden_fixture_recreates_board():
    fx = _load_golden_fixture()
    doc = fx["primary_board"]
    r = client.post("/boards/import", headers=IO, json=doc)
    assert r.status_code == 201, r.text
    detail = r.json()
    # 7 nodes + 5 edges (3 evidence + 2 hypothesis) recreated
    assert len(detail["nodes"]) == 7
    assert len(detail["edges"]) == 5
    ev = [e for e in detail["edges"] if e["edge_class"] == "evidence"]
    hy = [e for e in detail["edges"] if e["edge_class"] == "hypothesis"]
    assert len(ev) == 3 and len(hy) == 2
    assert all(e["rationale"] for e in hy)          # hypotheses keep their rationale


def test_import_rejects_arbitrary_table_in_document():
    fx = _load_golden_fixture()
    doc = {"drishti_board_export": dict(fx["primary_board"]["drishti_board_export"])}
    # tamper: add a node referencing a non-whitelisted table
    inner = doc["drishti_board_export"]
    inner["nodes"] = list(inner["nodes"]) + [{
        "board_node_id": 999, "node_kind": "entity", "ref_table": "pg_user",
        "ref_id": "1", "label": "evil", "pos_x": 0, "pos_y": 0, "snapshot": {}}]
    r = client.post("/boards/import", headers=IO, json=doc)
    assert r.status_code == 201
    # the arbitrary-table node was dropped (never trusted)
    labels = [n["label"] for n in r.json()["nodes"]]
    assert "evil" not in labels


# --- Search Around (needs the operational graph) -----------------------------
@requires_db
def test_search_around_capped_and_id_based():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "MemberEntityID" FROM "GangMembership" '
                        'WHERE "MemberEntityID" IS NOT NULL LIMIT 1')
            row = cur.fetchone()
    if not row:
        pytest.skip("no graph entities in this DB")
    entity_id = int(row[0])
    bid = _new_board()
    # the hop cap is enforced at the request boundary (>3 rejected outright)
    over = client.post(f"/boards/{bid}/search-around", headers=IO,
                       json={"entity_id": entity_id, "hops": 9, "max_neighbors": 10})
    assert over.status_code == 422
    # a valid capped expansion returns a bounded neighbour set
    r = client.post(f"/boards/{bid}/search-around", headers=IO,
                    json={"entity_id": entity_id, "hops": 2, "max_neighbors": 10, "preview": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hops"] <= 3
    assert len(body["neighbors"]) <= 10          # fan-out cap honoured
    # importing produces read-only evidence edges with NetworkEdge provenance
    imp = client.post(f"/boards/{bid}/import/subgraph", headers=IO,
                      json={"entity_id": entity_id, "hops": 1, "max_neighbors": 5})
    assert imp.status_code == 200
    detail = client.get(f"/boards/{bid}", headers=IO).json()
    ev = [e for e in detail["edges"] if e["edge_class"] == "evidence"]
    for e in ev:
        assert str(e["source_record_id"]).startswith("NetworkEdge:")  # id-based, no name match
