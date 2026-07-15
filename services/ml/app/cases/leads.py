"""Ranked investigative leads (Phase 10).

Proposes the next investigative steps for a case, each with the EVIDENCE behind
it (real source record ids). Rules read only the case's linked records plus the
Phase-6 entity graph / Phase-11 financial sub-graph, so every lead is grounded
and contestable. These are SUGGESTIONS, not orders (written with Status
'suggested'); a human decides.
"""
from __future__ import annotations

from typing import Optional

from . import casedata

# Max leads surfaced per case.
MAX_LEADS = 6


def _gang_links(cur, names: list[str]) -> list[dict]:
    """Accused in this case whose name matches a known gang-member entity
    (Phase-6 graph). Name-based, so it is a lead to CHECK, not a fact."""
    if not names:
        return []
    cur.execute(
        '''SELECT p."EntityID", p."Label", gm."GangMembershipID", g."Label"
           FROM "EntityGraph" p
           JOIN "GangMembership" gm ON gm."MemberEntityID" = p."EntityID"
           JOIN "EntityGraph" g ON g."EntityID" = gm."GangEntityID"
           WHERE p."EntityType"='person' AND p."Label" = ANY(%s)
           LIMIT 20''', (names,))
    return [{"entity_id": int(r[0]), "person": r[1], "membership_id": int(r[2]), "gang": r[3]}
            for r in cur.fetchall()]


def _flagged_financial(cur, entity_ids: list[int]) -> list[dict]:
    if not entity_ids:
        return []
    cur.execute(
        'SELECT "AccountID","HolderName","EntityID" FROM "FinancialAccount" '
        'WHERE "IsFlagged" AND "EntityID" = ANY(%s) LIMIT 20', (entity_ids,))
    return [{"account_id": int(r[0]), "holder": r[1], "entity_id": int(r[2])}
            for r in cur.fetchall()]


def _days_open(core: dict) -> Optional[int]:
    import datetime as dt
    if not core.get("registered_date"):
        return None
    try:
        reg = dt.date.fromisoformat(str(core["registered_date"])[:10])
        return (dt.date.today() - reg).days
    except Exception:
        return None


def generate_leads(conn, case_id: int, similar_hits: Optional[list[dict]] = None) -> Optional[dict]:
    """Return ranked leads for a case, or None if the case doesn't exist.

    similar_hits (optional): precomputed similar-case results so we don't re-embed;
    each item needs at least 'case_id' (+ optional 'crime_subhead','similarity')."""
    with conn.cursor() as cur:
        core = casedata.fetch_case_core(cur, case_id)
        if not core:
            return None
        ch = casedata.fetch_case_children(cur, case_id)
        gang = _gang_links(cur, [a["name"] for a in ch["accused"] if a.get("name")])
        flagged = _flagged_financial(cur, [g["entity_id"] for g in gang])

    case_cite = f"CaseMaster:{case_id}"
    leads: list[dict] = []

    def add(kind, step, score, evidence, why):
        leads.append({"kind": kind, "step": step, "score": round(float(score), 4),
                      "evidence": evidence, "why": why})

    n_acc, n_arr, n_cs = len(ch["accused"]), len(ch["arrests"]), len(ch["chargesheets"])

    # 1) Named accused but no arrest -> pursue arrest.
    if n_acc and not n_arr:
        ev = [f"Accused:{a['id']}" for a in ch["accused"][:10]] + [case_cite]
        add("pursue_arrest",
            f"Pursue apprehension of the {n_acc} named accused — none has been arrested yet.",
            0.92, ev, "accused are named but ArrestSurrender has no records for this case")

    # 2) Arrests done, no chargesheet, still open -> file the final report.
    if n_arr and not n_cs:
        ev = [f"ArrestSurrender:{a['id']}" for a in ch["arrests"][:10]] + [case_cite]
        add("file_chargesheet",
            f"Prepare the chargesheet — {n_arr} arrest/surrender event(s) are recorded but no final report is filed.",
            0.85, ev, "ArrestSurrender rows exist while ChargesheetDetails is empty")

    # 3) No accused identified at all -> identification effort.
    if not n_acc:
        add("identify_suspects",
            "Identify suspects — no accused is named yet; canvass witnesses, CCTV and call-data.",
            0.8, [case_cite], "Accused child-set is empty for this case")

    # 4) Known-offender / gang linkage (Phase-6 graph).
    if gang:
        g0 = gang[0]
        ev = [case_cite] + [f"EntityGraph:{g['entity_id']}" for g in gang[:5]] \
            + [f"GangMembership:{g['membership_id']}" for g in gang[:5]]
        add("expand_network",
            f"Expand the network — accused '{g0['person']}' matches a known member of '{g0['gang']}'; "
            f"map co-offenders and check for a wider conspiracy.",
            0.78, ev,
            "accused name matches a known gang-member entity in the graph (verify identity)")

    # 5) Flagged financial trail (Phase-11 sub-graph).
    if flagged:
        f0 = flagged[0]
        ev = [case_cite] + [f"FinancialAccount:{f['account_id']}" for f in flagged[:5]]
        add("money_trail",
            f"Trace the money — a flagged account linked to an involved entity ('{f0['holder']}') "
            "should be run through the money-trail analysis.",
            0.74, ev, "a flagged FinancialAccount is linked to an entity tied to this case")

    # 6) Similar-case / MO linkage (Phase-10 semantic search).
    if similar_hits:
        top = similar_hits[:3]
        ev = [case_cite] + [f"CaseMaster:{h['case_id']}" for h in top]
        subheads = {h.get("crime_subhead") for h in top if h.get("crime_subhead")}
        mo = f" ({', '.join(sorted(subheads))})" if subheads else ""
        add("review_similar",
            f"Review {len(top)} semantically similar case(s){mo} for a possible serial pattern or shared MO.",
            0.7, ev, "high embedding similarity to prior cases (doc 02 §5)")

    # 7) Ageing case -> escalate.
    days = _days_open(core)
    if days is not None and days > 180 and not n_cs:
        add("escalate_ageing",
            f"Escalate / review — the case has been open for {days} days without disposal.",
            round(min(0.8, 0.5 + days / 1000.0), 4), [case_cite],
            f"registered {days} days ago and ChargesheetDetails is empty")

    # 8) Victim follow-up for body/violent crimes.
    if ch["victims"] and (core.get("crime_group") or "").lower().find("body") >= 0:
        ev = [f"Victim:{v['id']}" for v in ch["victims"][:10]] + [case_cite]
        add("victim_followup",
            f"Record statements and medical/forensic evidence for the {len(ch['victims'])} victim(s).",
            0.6, ev, "violent-crime head with victims on record")

    # Rank: highest score first, cap, assign RankOrder.
    leads.sort(key=lambda x: x["score"], reverse=True)
    leads = leads[:MAX_LEADS]
    for i, ld in enumerate(leads, start=1):
        ld["rank"] = i

    return {
        "case_id": case_id,
        "crime_no": core.get("crime_no"),
        "io_employee_id": core.get("io_employee_id"),
        "leads": leads,
    }
