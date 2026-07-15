"""Live similar-case search over CrimeEmbedding (pgvector HNSW, cosine `<=>`).

The query case is embedded AT QUERY TIME with the same embedder that produced the
corpus, then compared against the live corpus with ORDER BY embedding <=> :qvec.
No precomputed similar_case_links table — new/edited cases are searchable as soon
as the corpus is (re)embedded (doc 02 §5).
"""
from __future__ import annotations

from typing import Optional

from . import casedata
from .embeddings import embedder_for_model_name, to_pgvector


def corpus_model(cur) -> Optional[tuple]:
    """The most recent 'case' embedding ModelVersion actually present in the corpus."""
    cur.execute(
        '''SELECT ce."ModelVersionID", mv."ModelName", COUNT(*)
           FROM "CrimeEmbedding" ce
           JOIN "ModelVersion" mv ON mv."ModelVersionID" = ce."ModelVersionID"
           WHERE ce."SourceType" = 'case'
           GROUP BY ce."ModelVersionID", mv."ModelName"
           ORDER BY MAX(ce."CreatedAt") DESC, ce."ModelVersionID" DESC
           LIMIT 1''')
    return cur.fetchone()


def _fetch_cards(cur, ids: list[int]) -> dict[int, dict]:
    """Per-case summary + OUTCOME (status, chargesheet disposition, arrest count)."""
    if not ids:
        return {}
    cur.execute(
        '''SELECT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate",
                  ch."CrimeGroupName", csh."CrimeHeadName", grv."LookupValue",
                  d."DistrictName", st."CaseStatusName",
                  (SELECT COUNT(*) FROM "Accused" a WHERE a."CaseMasterID"=cm."CaseMasterID"),
                  (SELECT COUNT(*) FROM "ArrestSurrender" ar WHERE ar."CaseMasterID"=cm."CaseMasterID"),
                  (SELECT cd."cstype"::text FROM "ChargesheetDetails" cd
                   WHERE cd."CaseMasterID"=cm."CaseMasterID" ORDER BY cd."CSID" DESC LIMIT 1)
           FROM "CaseMaster" cm
           LEFT JOIN "Unit"             u   ON u."UnitID"           = cm."PoliceStationID"
           LEFT JOIN "District"         d   ON d."DistrictID"       = u."DistrictID"
           LEFT JOIN "CrimeHead"        ch  ON ch."CrimeHeadID"     = cm."CrimeMajorHeadID"
           LEFT JOIN "CrimeSubHead"     csh ON csh."CrimeSubHeadID" = cm."CrimeMinorHeadID"
           LEFT JOIN "GravityOffence"   grv ON grv."GravityOffenceID" = cm."GravityOffenceID"
           LEFT JOIN "CaseStatusMaster" st  ON st."CaseStatusID"    = cm."CaseStatusID"
           WHERE cm."CaseMasterID" = ANY(%s)''', (ids,))
    out = {}
    for r in cur.fetchall():
        cstype = r[10]
        out[int(r[0])] = {
            "case_id": int(r[0]), "crime_no": r[1],
            "registered_date": str(r[2]) if r[2] else None,
            "crime_group": r[3], "crime_subhead": r[4], "gravity": r[5],
            "district": r[6], "status": r[7],
            "accused_count": int(r[8] or 0), "arrest_count": int(r[9] or 0),
            "disposition": casedata.CSTYPE_LABEL.get(cstype) if cstype else None,
        }
    return out


def find_similar(conn, case_id: int, k: int = 5) -> Optional[dict]:
    """Return the query case, the resolved corpus model, and the top-k neighbours
    with similarity scores + outcomes. None if the case doesn't exist; a dict with
    'error' if the corpus isn't embedded yet."""
    with conn.cursor() as cur:
        q = casedata.case_query_text(cur, case_id)
        if not q:
            return None
        cm = corpus_model(cur)
        if not cm:
            return {"error": "no_corpus", "query_case_id": case_id}
        mv_id, model_name, corpus_size = int(cm[0]), cm[1], int(cm[2])

        embedder = embedder_for_model_name(model_name)
        qvec = to_pgvector(embedder.embed([q["text"]])[0])

        # ANN search in the SAME model-version space, excluding the query case.
        cur.execute(
            'SELECT ce."CaseMasterID", (ce."Embedding" <=> %s::vector) AS dist '
            'FROM "CrimeEmbedding" ce '
            'WHERE ce."ModelVersionID"=%s AND ce."SourceType"=\'case\' '
            '  AND ce."CaseMasterID" <> %s '
            'ORDER BY ce."Embedding" <=> %s::vector LIMIT %s',
            (qvec, mv_id, case_id, qvec, int(k)))
        hits = [(int(r[0]), float(r[1])) for r in cur.fetchall()]
        cards = _fetch_cards(cur, [h[0] for h in hits])

    results = []
    for cid, dist in hits:
        card = cards.get(cid, {"case_id": cid})
        # cosine distance in [0,2] -> similarity in [-1,1]; clamp to [0,1] for display
        card["similarity"] = round(max(0.0, min(1.0, 1.0 - dist)), 4)
        card["distance"] = round(dist, 6)
        results.append(card)

    return {
        "query_case_id": case_id,
        "query_text": q["text"],
        "model_version_id": mv_id,
        "model_name": model_name,
        "corpus_size": corpus_size,
        "results": results,
    }
