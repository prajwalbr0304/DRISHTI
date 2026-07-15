"""Phase-10 case decision-support tests.

Unit: embedder (deterministic, normalised, semantically meaningful), the canonical
case text, and the OAG summary's "no uncited claim" guarantee — all without a DB.
Integration (@requires_db): live similar-case ranking, the cited AISummary write,
and leads written to OfficerRecommendation.
"""
import numpy as np
import pytest

from app.cases import casedata, summary as summ
from app.cases.embeddings import (EMBED_DIM, HashingEmbedder, get_embedder,
                                   to_pgvector)
from app.cases.schemas import LeadsResponse, SimilarResponse, SummaryResponse
from app.contracts import AiResult
from conftest import requires_db


# ---- embedder (no DB) ------------------------------------------------------
def test_hashing_embedder_deterministic_normalised_dim():
    emb = HashingEmbedder()
    a = emb.embed(["Public Order. Rioting. Charges: IPC-143, IPC-147."])
    b = emb.embed(["Public Order. Rioting. Charges: IPC-143, IPC-147."])
    assert a.shape == (1, EMBED_DIM)
    assert np.array_equal(a, b)                        # deterministic
    assert abs(float(np.linalg.norm(a[0])) - 1.0) < 1e-5   # L2-normalised


def test_hashing_embedder_semantic_similarity():
    emb = HashingEmbedder()
    riot1 = "Public Order. Rioting. Charges: IPC-143, IPC-147. District: Davanagere."
    riot2 = "Public Order. Rioting. Charges: IPC-143, IPC-148. District: Ballari."
    cyber = "Economic & Cyber Crime. OTP Scam. Charges: IT-66C. District: Bengaluru City."
    v = emb.embed([riot1, riot2, cyber])
    sim_same = float(v[0] @ v[1])       # two rioting cases
    sim_diff = float(v[0] @ v[2])       # rioting vs cyber
    assert sim_same > sim_diff          # meaningful cosine similarity
    assert sim_same > 0.3


def test_to_pgvector_shape():
    lit = to_pgvector(np.zeros(EMBED_DIM))
    assert lit.startswith("[") and lit.endswith("]")
    assert lit.count(",") == EMBED_DIM - 1


def test_get_embedder_env_override(monkeypatch):
    monkeypatch.setenv("DRISHTI_EMBEDDER", "hashing")
    assert get_embedder().name == HashingEmbedder.name


# ---- canonical case text (no DB) -------------------------------------------
def test_canonical_text_is_mo_forward():
    core = {"crime_group": "Crimes Against Body", "crime_subhead": "Murder",
            "gravity": "Heinous", "district": "Mysuru", "registered_date": "2023-05-01",
            "brief_facts": "A body was found near the lake."}
    txt = casedata.canonical_text(core, ["IPC-302"], 1, 2)
    assert "Murder" in txt and "IPC-302" in txt and "Heinous" in txt
    assert txt.index("Crimes Against Body") < txt.index("A body was found")  # MO first


# ---- OAG summary: no uncited claim (no DB) ---------------------------------
def _synthetic_case(with_arrest: bool):
    core = {"case_id": 7, "crime_no": "X7", "registered_date": "2023-01-02",
            "incident_from": "2023-01-01", "incident_to": "2023-01-01",
            "station": "PS-1", "district": "Mysuru", "crime_group": "Crimes Against Property",
            "crime_subhead": "Burglary", "gravity": "Serious", "status": "Under Investigation",
            "brief_facts": "A house was broken into overnight."}
    ch = {
        "sections": [{"act": "IPC", "section": "IPC-457", "description": "lurking", "act_name": "IPC"}],
        "victims": [{"id": 11, "name": "A. Rao", "age": 40, "gender": 1}],
        "accused": [{"id": 21, "name": "B. Khan", "age": 25, "person_id": "A1"}],
        "complainants": [{"id": 31, "name": "A. Rao", "age": 40}],
        "arrests": ([{"id": 41, "accused_id": 21, "date": "2023-02-01", "io_id": 5, "type": 1}]
                    if with_arrest else []),
        "chargesheets": [],
    }
    return core, ch


@pytest.mark.parametrize("with_arrest", [True, False])
def test_summary_every_claim_is_cited(with_arrest):
    core, ch = _synthetic_case(with_arrest)
    claims = summ._build_claims(core, ch)
    assert claims
    for c in claims:
        assert c.citations, f"uncited claim: {c.text!r}"
    # the negative 'no arrest' claim is still grounded in the CaseMaster row
    if not with_arrest:
        neg = [c for c in claims if "No arrest" in c.text]
        assert neg and neg[0].citations == ["CaseMaster:7"]
    summ.assert_all_cited(claims)   # must not raise


def test_assert_all_cited_rejects_uncited():
    bad = [summ._Claim("an unsupported assertion", [])]
    with pytest.raises(ValueError):
        summ.assert_all_cited(bad)


def test_summary_timeline_sorted_and_cited():
    core, ch = _synthetic_case(with_arrest=True)
    tl = summ._build_timeline(core, ch)
    assert tl and all(e["citations"] for e in tl)
    dates = [str(e["date"]) for e in tl]
    assert dates == sorted(dates)


# ---- integration -----------------------------------------------------------
def _assert_airesult(r: AiResult):
    assert isinstance(r.answer, str) and r.answer
    assert 0.0 <= r.confidence <= 1.0
    assert isinstance(r.source_record_ids, list)
    assert isinstance(r.model_version, str) and "@" in r.model_version


def _case_with_accused_no_arrest():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                '''SELECT cm."CaseMasterID" FROM "CaseMaster" cm
                   WHERE EXISTS (SELECT 1 FROM "Accused" a WHERE a."CaseMasterID"=cm."CaseMasterID")
                     AND NOT EXISTS (SELECT 1 FROM "ArrestSurrender" ar WHERE ar."CaseMasterID"=cm."CaseMasterID")
                   ORDER BY cm."CaseMasterID" LIMIT 1''')
            r = cur.fetchone()
    return int(r[0]) if r else None


@requires_db
def test_similar_returns_ranked_live_results():
    from app.cases import service
    resp = service.similar_cases(82412, k=5)
    if resp is service.NO_CORPUS:
        pytest.skip("corpus not embedded; run `python -m app.batch embed-cases`")
    assert isinstance(resp, SimilarResponse)
    _assert_airesult(resp.result)
    sims = [c.similarity for c in resp.results]
    assert sims == sorted(sims, reverse=True)          # ranked
    assert all(0.0 <= s <= 1.0 for s in sims)
    assert resp.corpus_size > 0
    assert all(c.case_id != 82412 for c in resp.results)   # query excluded


@requires_db
def test_summary_writes_fully_cited_row():
    from app import db
    from app.cases import service
    resp = service.case_summary(82412)
    assert isinstance(resp, SummaryResponse)
    _assert_airesult(resp.result)
    assert resp.fully_cited and resp.cited_claim_count == resp.claim_count
    assert all(s.citations for s in resp.sentences)     # no uncited claim
    assert resp.summary_id is not None
    # the AISummary row persisted with SummaryText carrying inline citations
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "SummaryText" FROM "AISummary" WHERE "SummaryID"=%s', (resp.summary_id,))
            row = cur.fetchone()
    assert row and "[CaseMaster:82412]" in row[0]


@requires_db
def test_leads_written_to_officer_recommendation():
    from app import db
    from app.cases import service
    case_id = _case_with_accused_no_arrest()
    if case_id is None:
        pytest.skip("no suitable case found")
    resp = service.case_leads(case_id)
    assert isinstance(resp, LeadsResponse)
    _assert_airesult(resp.result)
    assert resp.leads and resp.io_employee_id is not None
    # ranks are 1..n contiguous and scores descending
    assert [l.rank for l in resp.leads] == list(range(1, len(resp.leads) + 1))
    assert all(l.evidence for l in resp.leads)          # evidence behind each lead
    top = resp.leads[0]
    assert top.recommendation_id is not None
    # persisted as a 'suggested' OfficerRecommendation with a jsonb rationale
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "Status"::text, "Rationale"->>\'kind\', "RankOrder" '
                        'FROM "OfficerRecommendation" WHERE "RecommendationID"=%s',
                        (top.recommendation_id,))
            row = cur.fetchone()
    assert row and row[0] == "suggested" and row[1] == top.kind


@requires_db
def test_similar_missing_case_returns_none():
    from app.cases import service
    assert service.similar_cases(2_000_000_000, k=3) is None
