"""Case decision-support service: assemble the AiResult contract over the typed
payloads and perform the typed writes (AISummary, OfficerRecommendation) with a
ModelInference audit row so every summary/lead is reproducible (doc 02 §6, §10)."""
from __future__ import annotations

from psycopg2.extras import Json

from .. import db, models
from ..contracts import AiResult
from . import leads as leads_mod
from . import similar as similar_mod
from . import summary as summary_mod
from .schemas import (Lead, LeadsResponse, SimilarCase, SimilarResponse,
                      SummaryClaim, SummaryResponse, TimelineEvent)

# Sentinel: similar-case search needs the corpus embedded first (run embed-cases).
NO_CORPUS = object()

_SUMMARY_MODEL = ("drishti-oag-summary", "nlp", "1.0.0")
_LEADS_MODEL = ("drishti-leads", "nlp", "1.0.0")


# ---- 1. similar cases (live, read-only) ------------------------------------
def similar_cases(case_id: int, k: int = 5):
    with db.ro_conn() as conn:
        res = similar_mod.find_similar(conn, case_id, k=k)
        if res is None:
            return None
        if res.get("error") == "no_corpus":
            return NO_CORPUS
        model_label = f"{res['model_name']}@1.0.0"

    cases = [SimilarCase(**c) for c in res["results"]]
    top_sim = cases[0].similarity if cases else 0.0
    src = [f"CaseMaster:{c.case_id}" for c in cases]
    result = AiResult(
        answer=(f"Found {len(cases)} case(s) with the closest modus-operandi / context to "
                f"case {case_id}." if cases else f"No comparable cases found for case {case_id}."),
        confidence=round(float(top_sim), 4),
        source_record_ids=src,
        reasoning_summary=("Semantic nearest-neighbour search over case embeddings "
                           "(pgvector HNSW, cosine distance), computed live against the "
                           f"{res['corpus_size']}-case corpus. Similarity = 1 - cosine distance."),
        model_version=model_label,
    )
    return SimilarResponse(
        result=result, query_case_id=case_id, model_name=res["model_name"],
        model_version_id=res["model_version_id"], corpus_size=res["corpus_size"],
        results=cases)


# ---- 2. cited AI summary (writes AISummary) --------------------------------
def case_summary(case_id: int):
    with db.rw_conn() as conn:
        payload = summary_mod.build_summary(conn, case_id)
        if payload is None:
            return None
        name, mtype, ver = _SUMMARY_MODEL
        mv_id = models.get_or_create_model_version(
            conn, name, mtype, ver, framework="ontology-augmented-generation",
            hyperparameters={"pattern": "OAG", "deterministic": True})
        mv_label = models.model_version_label(conn, mv_id)

        with conn.cursor() as cur:
            # idempotent: replace this model version's summary for the case
            cur.execute('DELETE FROM "AISummary" WHERE "CaseMasterID"=%s AND "ModelVersionID"=%s',
                        (case_id, mv_id))
            cur.execute(
                'INSERT INTO "AISummary" ("SummaryType","CaseMasterID","ModelVersionID",'
                '"SummaryText","TokensUsed","Confidence") '
                "VALUES ('case_brief',%s,%s,%s,%s,%s) RETURNING \"SummaryID\"",
                (case_id, mv_id, payload["summary_text"],
                 len(payload["summary_text"].split()), payload["confidence"]))
            summary_id = int(cur.fetchone()[0])

        models.log_inference(
            conn, mv_id, case_master_id=case_id, ref_table="AISummary", ref_id=str(summary_id),
            inputs={"case_id": case_id, "source_record_ids": payload["source_record_ids"]},
            outputs={"summary_id": summary_id, "claims": payload["claim_count"],
                     "cited_claims": payload["cited_claim_count"]},
            confidence=payload["confidence"])

    fully_cited = payload["cited_claim_count"] == payload["claim_count"]
    src = list(payload["source_record_ids"]) + [f"AISummary:{summary_id}"]
    result = AiResult(
        answer=payload["sentences"][0]["text"] if payload["sentences"] else f"Summary for case {case_id}.",
        confidence=payload["confidence"],
        source_record_ids=src,
        reasoning_summary=(f"Case brief + timeline generated strictly from {len(payload['source_record_ids'])} "
                           f"linked records; all {payload['claim_count']} claims carry an inline citation "
                           "(Ontology-Augmented Generation). Deterministic and reproducible."),
        model_version=mv_label,
    )
    return SummaryResponse(
        result=result, case_id=case_id, crime_no=payload.get("crime_no"),
        summary_id=summary_id, summary_text=payload["summary_text"],
        sentences=[SummaryClaim(**s) for s in payload["sentences"]],
        timeline=[TimelineEvent(**t) for t in payload["timeline"]],
        claim_count=payload["claim_count"], cited_claim_count=payload["cited_claim_count"],
        fully_cited=fully_cited, confidence=payload["confidence"])


# ---- 3. ranked investigative leads (writes OfficerRecommendation) ----------
def case_leads(case_id: int):
    # best-effort similar-case hits for the MO-linkage lead (needs the corpus)
    similar_hits = None
    sim = similar_cases(case_id, k=3)
    if isinstance(sim, SimilarResponse):
        similar_hits = [c.model_dump() for c in sim.results]

    with db.rw_conn() as conn:
        payload = leads_mod.generate_leads(conn, case_id, similar_hits=similar_hits)
        if payload is None:
            return None
        io_id = payload["io_employee_id"]
        name, mtype, ver = _LEADS_MODEL
        mv_id = models.get_or_create_model_version(
            conn, name, mtype, ver, framework="rules",
            hyperparameters={"decision_support": True, "suggestions_not_orders": True})
        mv_label = models.model_version_label(conn, mv_id)

        written = []
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "OfficerRecommendation" WHERE "CaseMasterID"=%s AND "ModelVersionID"=%s',
                        (case_id, mv_id))
            for ld in payload["leads"]:
                cur.execute(
                    'INSERT INTO "OfficerRecommendation" ("CaseMasterID","EmployeeID","ModelVersionID",'
                    '"Score","RankOrder","Rationale","Status") '
                    "VALUES (%s,%s,%s,%s,%s,%s,'suggested') RETURNING \"RecommendationID\"",
                    (case_id, io_id, mv_id, ld["score"], ld["rank"],
                     Json({"kind": ld["kind"], "step": ld["step"], "evidence": ld["evidence"],
                           "why": ld["why"]})))
                rid = int(cur.fetchone()[0])
                written.append({**ld, "recommendation_id": rid})

        models.log_inference(
            conn, mv_id, case_master_id=case_id, ref_table="OfficerRecommendation",
            inputs={"case_id": case_id, "io_employee_id": io_id,
                    "similar_used": bool(similar_hits)},
            outputs={"n_leads": len(written), "kinds": [w["kind"] for w in written]},
            confidence=round(float(written[0]["score"]), 4) if written else None)

    evidence: list[str] = []
    for w in written:
        for e in w["evidence"]:
            if e not in evidence:
                evidence.append(e)
    evidence += [f"OfficerRecommendation:{w['recommendation_id']}" for w in written]
    result = AiResult(
        answer=(written[0]["step"] if written else f"No investigative leads generated for case {case_id}."),
        confidence=round(float(written[0]["score"]), 4) if written else 0.0,
        source_record_ids=evidence,
        reasoning_summary=(f"{len(written)} ranked investigative lead(s); each carries the evidence "
                           "record ids behind it. Decision support only — suggestions, not orders."),
        model_version=mv_label,
    )
    return LeadsResponse(
        result=result, case_id=case_id, crime_no=payload.get("crime_no"),
        io_employee_id=io_id, leads=[Lead(**w) for w in written])
