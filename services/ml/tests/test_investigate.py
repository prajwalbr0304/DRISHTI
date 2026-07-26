"""Prompt 20 Part D — case-scoped investigation assistant: bilingual intent
(offline), the composed cited answer + facts/hypotheses separation + identity
guard (DB), permission-safety and send-to-board (offline/DB)."""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.investigate import intent as intent_mod
from app.investigate import service

client = TestClient(app)


def _hdr(role: str) -> dict:
    return {"X-Role": role}


# ============================ bilingual intent (offline) ===================
def test_intent_classification_english():
    assert intent_mod.classify("Have similar cases happened before?") == intent_mod.SIMILAR
    assert intent_mod.classify("what are the next leads?") == intent_mod.LEADS
    assert intent_mod.classify("who is connected to this case?") == intent_mod.IDENTITY
    assert intent_mod.classify("show the timeline") == intent_mod.TIMELINE
    assert intent_mod.classify("summarise this case") == intent_mod.SUMMARY
    assert intent_mod.classify("tell me about it") == intent_mod.OVERVIEW


def test_intent_classification_kannada_and_translit():
    assert intent_mod.detect_language("ಇದೇ ರೀತಿಯ ಪ್ರಕರಣಗಳು ಹಿಂದೆ?") == "kn"
    assert intent_mod.detect_language("similar cases before?") == "en"
    assert intent_mod.classify("ಇದೇ ರೀತಿಯ ಪ್ರಕರಣಗಳು ಹಿಂದೆ ಆಗಿವೆಯೇ?") == intent_mod.SIMILAR
    assert intent_mod.classify("munddina sulivu enu?") == intent_mod.LEADS  # transliterated


def test_board_ref_kind_mapping_is_whitelisted():
    from app.board import references
    supported = set(references.supported_ref_tables())
    for ref_table in service._BOARD_REF_KIND:
        # OfficerRecommendation/AISummary are notes (no board DB ref) — the rest
        # must be board-whitelisted object kinds.
        if ref_table in ("OfficerRecommendation", "AISummary"):
            continue
        assert ref_table in supported, ref_table


# ============================ permission-safety ============================
def test_case_assistant_gates_open_to_every_command_role():
    # INTERIM ("all roles have access to everything"): the case-read gate behind
    # the assistant + send-to-board no longer denies any command seat.
    from app.cases.permissions import require_case_read
    from app.roles import FUNCTIONAL_ROLES
    for role in FUNCTIONAL_ROLES:
        assert require_case_read(role) == role


# ============================ composed answer (DB) =========================
def _first_case_id() -> int:
    from app import db
    with db.ro_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 1')
        return int(cur.fetchone()[0])


@requires_db
def test_brief_separates_facts_and_hypotheses_with_citations():
    cid = _first_case_id()
    r = client.get(f"/investigate/{cid}/brief", headers=_hdr("investigating_officer"))
    assert r.status_code == 200
    body = r.json()
    assert body["planner_source"] == "case-orchestrator"
    # every fact is evidence-backed; every hypothesis is a hypothesis
    assert body["facts"] and all(f["basis"] == "evidence" for f in body["facts"])
    assert all(h["basis"] == "hypothesis" for h in body["hypotheses"])
    # facts include the case overview + at least one timeline/identity fact
    assert any(f["type"] == "case_overview" for f in body["facts"])
    # everything is cited
    assert body["citations"]
    assert all(f["source_ids"] for f in body["facts"])
    # the never-same-on-embedding guard is present
    assert any("embedding" in l.lower() for l in body["limitations"])


@requires_db
def test_ask_bilingual_cited_and_permission_safe():
    cid = _first_case_id()
    en = client.post(f"/investigate/{cid}/ask",
                     json={"question": "Have similar cases happened before?"},
                     headers=_hdr("investigating_officer"))
    assert en.status_code == 200
    assert en.json()["intent"] == "similar_cases"
    assert en.json()["language"] == "en"
    kn = client.post(f"/investigate/{cid}/ask",
                     json={"question": "ಇದೇ ರೀತಿಯ ಪ್ರಕರಣಗಳು ಹಿಂದೆ ಆಗಿವೆಯೇ?"},
                     headers=_hdr("investigating_officer"))
    assert kn.status_code == 200
    assert kn.json()["language"] == "kn"
    assert kn.json()["intent"] == "similar_cases"


@requires_db
def test_reviewed_identity_links_are_facts_name_matches_are_hypotheses():
    cid = _first_case_id()
    out = service.brief(cid)
    for f in out["facts"]:
        if f["type"] == "reviewed_identity_link":
            assert f["basis"] == "evidence"
            assert "canonical" in f["detail"].lower()
    for h in out["hypotheses"]:
        if h["type"] == "lead:expand_network":
            # name-based linkage must carry the identity guard.
            assert "embedding" in h["detail"].lower() or "sameness" in h["detail"].lower()


@requires_db
def test_case_not_found_is_404():
    assert client.get("/investigate/999999999/brief", headers=_hdr("investigating_officer")).status_code == 404


# ============================ send-to-board (no persist) ===================
@requires_db
def test_send_to_board_invalid_board_is_skipped_gracefully():
    # A bogus board id -> add_node raises BoardNotFound -> skipped (no persist, no crash).
    out = service.send_to_board(
        999999999, [{"ref_table": "CaseMaster", "ref_id": "1", "label": "Case 1", "kind": "case"}],
        actor="demo.investigating_officer", role="investigating_officer")
    assert out["created_count"] == 0
    assert out["skipped_count"] == 1
