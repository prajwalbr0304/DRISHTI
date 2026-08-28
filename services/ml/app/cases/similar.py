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
    """Most recent model with a live, currently eligible case corpus."""
    eligible = casedata.analytics_eligible_sql("cm")
    cur.execute(
        '''SELECT ce."ModelVersionID", mv."ModelName",
                  COUNT(DISTINCT ce."CaseMasterID")
           FROM "CrimeEmbedding" ce
           JOIN "ModelVersion" mv ON mv."ModelVersionID" = ce."ModelVersionID"
           JOIN "CaseMaster" cm ON cm."CaseMasterID" = ce."CaseMasterID"
           WHERE ce."SourceType" = 'case'
             AND ce."IsArchived" = FALSE
             AND ce."CaseMasterID" IS NOT NULL
             AND ''' + eligible + '''
           GROUP BY ce."ModelVersionID", mv."ModelName"
           ORDER BY MAX(ce."CreatedAt") DESC, ce."ModelVersionID" DESC
           LIMIT 1''')
    return cur.fetchone()


def _fetch_cards(cur, ids: list[int]) -> dict[int, dict]:
    """Eligible case summaries with presentation-safe official references."""
    if not ids:
        return {}
    eligible = casedata.analytics_eligible_sql("cm")
    cur.execute(
        '''SELECT cm."CaseMasterID",
                  COALESCE(NULLIF(cv."SnapshotAttributes" #>>
                                      '{official_references,police_crime_no}', ''),
                           cm."CrimeNo"),
                  cm."CrimeRegisteredDate",
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
           LEFT JOIN LATERAL (
               SELECT cv0."SnapshotAttributes"
               FROM "CaseVersion" cv0
               WHERE cv0."CaseMasterID"=cm."CaseMasterID" AND cv0."IsCurrent"=TRUE
               ORDER BY cv0."VersionNo" DESC LIMIT 1
           ) cv ON TRUE
           WHERE cm."CaseMasterID" = ANY(%s) AND ''' + eligible, (ids,))
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


def _query_context(cur, case_id: int) -> dict:
    """The query case's demo context: district + crime group/sub-head (for the
    case/unit-context filter and the why-match explanation)."""
    cur.execute(
        'SELECT u."DistrictID", ch."CrimeGroupName", csh."CrimeHeadName", cm."PoliceStationID" '
        'FROM "CaseMaster" cm '
        'LEFT JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
        'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
        'LEFT JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID" = cm."CrimeMinorHeadID" '
        'WHERE cm."CaseMasterID" = %s', (case_id,))
    r = cur.fetchone()
    if not r:
        return {}
    return {"district_id": r[0], "crime_group": r[1], "crime_subhead": r[2], "unit_id": r[3]}


def _why_match(query_ctx: dict, card: dict) -> list[str]:
    """Human-readable reasons the hit matched (shared context/MO). Never outcome."""
    why: list[str] = []
    if query_ctx.get("crime_group") and card.get("crime_group") == query_ctx["crime_group"]:
        why.append(f"same crime group ({card['crime_group']})")
    if query_ctx.get("crime_subhead") and card.get("crime_subhead") == query_ctx["crime_subhead"]:
        why.append(f"same sub-head ({card['crime_subhead']})")
    if card.get("district") and query_ctx.get("district_name") \
            and card["district"] == query_ctx["district_name"]:
        why.append(f"same district ({card['district']})")
    return why


def find_similar(conn, case_id: int, k: int = 5, scope: str = "district",
                 district_id: Optional[int] = None) -> Optional[dict]:
    """Top-k semantically nearest cases with similarity, why-match, source links.

    ``scope`` applies the demo case/unit CONTEXT FILTER before the ANN search:
      * 'district' (default) — restrict candidates to the query case's district
        (or ``district_id`` if given), so retrieval stays within the selected
        synthetic demo context;
      * 'all' — search the whole embedded corpus.
    None if the case doesn't exist; a dict with 'error' if the corpus is empty.
    The query text is leakage-safe (no outcome/label fields); outcomes appear
    only on result cards for display.
    """
    with conn.cursor() as cur:
        q = casedata.case_query_text(cur, case_id)
        if not q:
            return None
        ctx = _query_context(cur, case_id)
        cm = corpus_model(cur)
        if not cm:
            return {"error": "no_corpus", "query_case_id": case_id}
        mv_id, model_name, corpus_size = int(cm[0]), cm[1], int(cm[2])

        # resolve the demo-context district filter
        scope_district = None
        if scope == "district":
            scope_district = district_id if district_id is not None else ctx.get("district_id")
        elif district_id is not None:
            scope_district = district_id

        embedder = embedder_for_model_name(model_name)
        qvec = to_pgvector(embedder.embed([q["text"]])[0])

        # ANN candidates are joined back to the live case row and policy-filtered
        # before distance ordering/LIMIT. Card hydration repeats the check so a
        # policy change between reads cannot re-expose a stale embedding.
        params: list = [qvec, mv_id, case_id]
        joins = 'JOIN "CaseMaster" candidate ON candidate."CaseMasterID" = ce."CaseMasterID" '
        where_ctx = ""
        if scope_district is not None:
            joins += 'JOIN "Unit" candidate_unit ON candidate_unit."UnitID" = candidate."PoliceStationID" '
            where_ctx = 'AND candidate_unit."DistrictID" = %s '
        candidate_eligible = casedata.analytics_eligible_sql("candidate")
        cur.execute(
            'SELECT ce."CaseMasterID", (ce."Embedding" <=> %s::vector) AS dist '
            'FROM "CrimeEmbedding" ce ' + joins +
            'WHERE ce."ModelVersionID"=%s AND ce."SourceType"=\'case\' '
            '  AND ce."IsArchived" = FALSE AND ce."CaseMasterID" <> %s '
            '  AND ' + candidate_eligible + ' ' + where_ctx +
            'ORDER BY ce."Embedding" <=> %s::vector LIMIT %s',
            params + ([scope_district] if scope_district is not None else []) + [qvec, int(k)])
        hits = [(int(r[0]), float(r[1])) for r in cur.fetchall()]
        cards = _fetch_cards(cur, [h[0] for h in hits])
        # query district name for the why-match
        if ctx.get("district_id") is not None:
            cur.execute('SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s', (ctx["district_id"],))
            dn = cur.fetchone()
            ctx["district_name"] = dn[0] if dn else None

    results = []
    for cid, dist in hits:
        card = cards.get(cid)
        if card is None:
            # Fail closed if the independently policy-filtered card read no longer
            # finds this ANN candidate.
            continue
        # cosine distance in [0,2] -> similarity in [-1,1]; clamp to [0,1] for display
        card["similarity"] = round(max(0.0, min(1.0, 1.0 - dist)), 4)
        card["distance"] = round(dist, 6)
        card["why_match"] = _why_match(ctx, card)
        card["source_links"] = [f"CaseMaster:{cid}"]
        results.append(card)

    return {
        "query_case_id": case_id,
        "query_text": q["text"],
        "model_version_id": mv_id,
        "model_name": model_name,
        "corpus_size": corpus_size,
        "scope": scope,
        "scope_district_id": scope_district,
        "results": results,
    }
