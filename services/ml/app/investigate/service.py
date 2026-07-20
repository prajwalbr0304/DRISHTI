"""Case-scoped investigation-assistant orchestration (Prompt 20 Part D).

Read-only composition of the EXISTING case capabilities on ONE connection:
  * case overview + lifecycle timeline (casedata + explorer._timeline);
  * similar cases / modus-operandi (similar_mod.find_similar);
  * cited case brief (summary_mod.build_summary — computed read-only);
  * ranked investigative leads (leads_mod.generate_leads — computed read-only);
  * reviewed canonical identity links (shared CanonicalPerson cross-case).

Facts (evidence-backed) are returned SEPARATELY from hypotheses (suggestions /
inferences). Two people are never asserted to be the same on embedding similarity
alone: canonical (reviewed) links are facts; name/embedding matches are candidate
hypotheses. Every item carries source record ids so it can be sent to the Board.
"""
from __future__ import annotations

from typing import Optional

from .. import db
from ..cases import casedata
from ..cases import explorer
from ..cases import leads as leads_mod
from ..cases import similar as similar_mod
from ..cases import summary as summary_mod
from . import intent as intent_mod

# Board ref_tables we can emit as citable objects (subset of the board whitelist).
_BOARD_REF_KIND = {
    "CaseMaster": "case", "CanonicalPerson": "entity", "CrimeHotspot": "hotspot",
    "OfficerRecommendation": "note", "AISummary": "note",
}

_IDENTITY_GUARD = ("Identity sameness is asserted only from a reviewed canonical "
                   "resolution; embedding/name similarity alone never establishes "
                   "that two people are the same.")


def _item(kind: str, label: str, detail: str, source_ids: list[str],
          basis: str, confidence: Optional[float] = None) -> dict:
    it = {"type": kind, "label": label, "detail": detail,
          "source_ids": source_ids, "basis": basis}
    if confidence is not None:
        it["confidence"] = round(float(confidence), 4)
    return it


def _canonical_links(cur, case_id: int) -> list[dict]:
    """Reviewed cross-case links via a SHARED CANONICAL accused person (fact)."""
    cur.execute(
        'SELECT DISTINCT r2."CaseMasterID", cm2."CrimeNo", '
        ' COALESCE(p."DisplayLabel", p."PublicRef"), p."CanonicalPersonID" '
        'FROM "CasePartyRole" r1 '
        'JOIN "CasePartyRole" r2 ON r2."CanonicalPersonID" = r1."CanonicalPersonID" '
        '                        AND r2."CaseMasterID" <> r1."CaseMasterID" '
        '                        AND r2."RoleType" = \'accused\' '
        'JOIN "CanonicalPerson" p ON p."CanonicalPersonID" = r1."CanonicalPersonID" '
        'JOIN "CaseMaster" cm2 ON cm2."CaseMasterID" = r2."CaseMasterID" '
        'WHERE r1."CaseMasterID"=%s AND r1."RoleType"=\'accused\' '
        '  AND r1."CanonicalPersonID" IS NOT NULL AND p."IsUnknown"=FALSE '
        'ORDER BY r2."CaseMasterID" LIMIT 20', (case_id,))
    return [{"case_id": int(r[0]), "crime_no": r[1], "person": r[2],
             "canonical_person_id": int(r[3])} for r in cur.fetchall()]


def _compose(conn, case_id: int, k: int, intent: str) -> Optional[dict]:
    with conn.cursor() as cur:
        core = casedata.fetch_case_core(cur, case_id)
        if not core:
            return None
        children = casedata.fetch_case_children(cur, case_id)
        timeline = explorer._timeline(core, children)
        canonical = _canonical_links(cur, case_id)

    case_cite = f"CaseMaster:{case_id}"
    facts: list[dict] = []
    hypotheses: list[dict] = []
    citable: list[dict] = []
    seen_cite: set[tuple] = set()

    def add_citable(ref_table: str, ref_id, label: str):
        key = (ref_table, str(ref_id))
        if key in seen_cite or ref_table not in _BOARD_REF_KIND:
            return
        seen_cite.add(key)
        citable.append({"ref_table": ref_table, "ref_id": str(ref_id), "label": label,
                        "kind": _BOARD_REF_KIND[ref_table]})

    # --- FACT: the case itself ------------------------------------------------
    ov = (f"{core.get('crime_group') or ''} / {core.get('crime_subhead') or ''} — "
          f"{core.get('status') or 'status n/a'} "
          f"(registered {core.get('registered_date') or 'n/a'})")
    facts.append(_item("case_overview", core.get("crime_no") or f"Case {case_id}",
                       ov.strip(" —/"), [case_cite], "evidence"))
    add_citable("CaseMaster", case_id, core.get("crime_no") or f"Case {case_id}")

    # --- FACT: lifecycle timeline --------------------------------------------
    if timeline:
        tl = "; ".join(f"{e['date']}: {e['label']}" for e in timeline[:8])
        facts.append(_item("timeline", "Lifecycle timeline", tl, [case_cite], "evidence"))

    # --- similar cases (facts: related FIRs + shared context) ----------------
    similar = None
    if intent in (intent_mod.SIMILAR, intent_mod.OVERVIEW, intent_mod.LEADS):
        similar = similar_mod.find_similar(conn, case_id, k=k)
        if similar and not similar.get("error"):
            for hit in similar["results"][:k]:
                sid = f"CaseMaster:{hit['case_id']}"
                why = ", ".join(hit.get("why_match") or []) or "semantic MO similarity"
                facts.append(_item(
                    "related_fir",
                    f"{hit.get('crime_no') or hit['case_id']} ({hit.get('crime_subhead') or '?'})",
                    f"shared context: {why}; similarity {hit.get('similarity')}",
                    [sid], "evidence"))
                add_citable("CaseMaster", hit["case_id"], hit.get("crime_no") or f"Case {hit['case_id']}")
            if similar["results"]:
                subs = {h.get("crime_subhead") for h in similar["results"][:3] if h.get("crime_subhead")}
                hypotheses.append(_item(
                    "possible_serial_pattern", "Possible serial pattern / shared MO",
                    (f"{len(similar['results'])} case(s) share modus operandi"
                     + (f" ({', '.join(sorted(subs))})" if subs else "")
                     + ". Similarity is a lead by shared context/MO, not proof of a shared offender."),
                    [case_cite] + [f"CaseMaster:{h['case_id']}" for h in similar["results"][:3]],
                    "hypothesis", similar["results"][0].get("similarity")))

    # --- FACT: reviewed canonical identity links -----------------------------
    if canonical:
        for lk in canonical[:10]:
            facts.append(_item(
                "reviewed_identity_link",
                f"{lk['person']} also in {lk['crime_no'] or lk['case_id']}",
                "shared REVIEWED canonical person across cases (not a name match)",
                [f"CanonicalPerson:{lk['canonical_person_id']}", f"CaseMaster:{lk['case_id']}"],
                "evidence"))
            add_citable("CanonicalPerson", lk["canonical_person_id"], lk["person"])
            add_citable("CaseMaster", lk["case_id"], lk["crime_no"] or f"Case {lk['case_id']}")

    # --- HYPOTHESES: leads (suggestions) -------------------------------------
    if intent in (intent_mod.LEADS, intent_mod.OVERVIEW, intent_mod.NETWORK):
        similar_hits = ([c for c in similar["results"]] if (similar and not similar.get("error")) else None)
        lead_payload = leads_mod.generate_leads(conn, case_id, similar_hits=similar_hits)
        if lead_payload:
            for ld in lead_payload["leads"]:
                basis_note = ld["why"]
                # gang/identity-linkage leads are name-based candidates -> guard.
                if ld["kind"] == "expand_network":
                    basis_note += f" — {_IDENTITY_GUARD}"
                hypotheses.append(_item(
                    f"lead:{ld['kind']}", ld["step"], basis_note, ld["evidence"],
                    "hypothesis", ld["score"]))

    # --- confidence + answer --------------------------------------------------
    top_sim = (similar["results"][0].get("similarity")
               if (similar and not similar.get("error") and similar["results"]) else None)
    n_similar = len(similar["results"]) if (similar and not similar.get("error")) else 0
    answers = {
        intent_mod.SIMILAR: (f"{n_similar} similar case(s) found for {core.get('crime_no') or case_id} "
                             "by shared modus-operandi/context (leads, not identity matches)."),
        intent_mod.LEADS: (f"{len([h for h in hypotheses if h['type'].startswith('lead:')])} "
                           "investigative lead(s) suggested; each cites its evidence."),
        intent_mod.IDENTITY: (f"{len(canonical)} reviewed canonical cross-case identity link(s). "
                              + _IDENTITY_GUARD),
        intent_mod.NETWORK: (f"{len(canonical)} reviewed identity link(s) and "
                             f"{len([h for h in hypotheses if h['type'].startswith('lead:')])} lead(s)."),
        intent_mod.TIMELINE: f"{len(timeline)} lifecycle event(s) reconstructed from dated records.",
        intent_mod.SUMMARY: ov.strip(" —/"),
        intent_mod.OVERVIEW: (f"Case {core.get('crime_no') or case_id}: {n_similar} related FIR(s), "
                              f"{len(canonical)} reviewed identity link(s), "
                              f"{len([h for h in hypotheses if h['type'].startswith('lead:')])} lead(s)."),
    }
    citations = sorted({sid for it in (facts + hypotheses) for sid in it["source_ids"]})
    return {
        "case_id": case_id, "crime_no": core.get("crime_no"), "intent": intent,
        "answer": answers.get(intent, answers[intent_mod.OVERVIEW]),
        "confidence": round(float(top_sim), 4) if top_sim is not None else 0.6,
        "facts": facts, "hypotheses": hypotheses, "citable_objects": citable,
        "citations": citations,
        "reasoning_summary": ("Composed from existing case summary/similar-case/identity/"
                              "leads/timeline APIs; facts (evidence-backed) are separated from "
                              "hypotheses (suggestions). Read-only; no second free-form model."),
        "limitations": [
            "Similar cases are leads by shared context/MO, not proof of a shared offender.",
            _IDENTITY_GUARD,
            "Leads are suggestions for a human investigator, not orders.",
        ],
        "planner_source": "case-orchestrator",
    }


class CaseNotFound(LookupError):
    pass


def ask(case_id: int, question: str, k: int = 5) -> dict:
    intent = intent_mod.classify(question)
    language = intent_mod.detect_language(question)
    with db.ro_conn() as conn:
        out = _compose(conn, case_id, k, intent)
    if out is None:
        raise CaseNotFound(f"case {case_id} not found")
    out["question"] = question
    out["language"] = language
    return out


def brief(case_id: int, k: int = 5) -> dict:
    with db.ro_conn() as conn:
        out = _compose(conn, case_id, k, intent_mod.OVERVIEW)
    if out is None:
        raise CaseNotFound(f"case {case_id} not found")
    out["question"] = None
    out["language"] = "en"
    return out


# ---------------------------------------------------------------------------
# Send cited objects to the Investigation Board (reuses board.service.add_node)
# ---------------------------------------------------------------------------
def send_to_board(board_id: int, objects: list[dict], *, actor: str, role: str) -> dict:
    from ..board import service as board_service
    from ..board.schemas import NodeCreate

    created, skipped = [], []
    x = 0.0
    for obj in objects:
        ref_table = obj.get("ref_table")
        ref_id = obj.get("ref_id")
        kind = obj.get("kind") or _BOARD_REF_KIND.get(ref_table or "", "note")
        label = obj.get("label") or (f"{ref_table}:{ref_id}" if ref_table else "note")
        try:
            req = NodeCreate(node_kind=kind, ref_table=ref_table, ref_id=(str(ref_id) if ref_id else None),
                             label=label, pos_x=x, pos_y=0.0)
            res = board_service.add_node(board_id, req, actor, role)
            created.append({"ref_table": ref_table, "ref_id": ref_id, "label": label,
                            "result": getattr(res, "model_dump", lambda: res)()})
            x += 220.0
        except Exception as exc:  # noqa: BLE001 — surface per-object failure, keep going
            skipped.append({"ref_table": ref_table, "ref_id": ref_id,
                            "reason": f"{type(exc).__name__}: {exc}"})
    return {"board_id": board_id, "created_count": len(created),
            "skipped_count": len(skipped), "created": created, "skipped": skipped}
