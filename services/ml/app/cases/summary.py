"""Grounded case summary + timeline (Ontology-Augmented Generation, doc 02 §6).

Every claim is generated STRICTLY from a linked record and carries an inline
citation to that record's id (e.g. [CaseMaster:82412], [ArrestSurrender:99]). The
generator is deterministic and reproducible: the same linked records + model
version always yield the same text. `build_summary` refuses to emit any sentence
without a citation (assert_all_cited), so the "no claim without a citation" rule
is structural, not advisory.
"""
from __future__ import annotations

from typing import Optional

from . import casedata


def _names(items: list[dict], n: int = 3) -> str:
    labels = [str(i["name"]) for i in items[:n] if i.get("name")]
    extra = len(items) - len(labels)
    text = ", ".join(labels)
    if extra > 0:
        text += f" and {extra} other" + ("s" if extra > 1 else "")
    return text


class _Claim:
    __slots__ = ("text", "citations")

    def __init__(self, text: str, citations: list[str]):
        self.text = text
        self.citations = citations


def _build_claims(core: dict, ch: dict) -> list[_Claim]:
    cid = core["case_id"]
    case_cite = f"CaseMaster:{cid}"
    claims: list[_Claim] = []

    # 1) Registration — always grounded in the CaseMaster row.
    where = " at " + core["station"] if core.get("station") else ""
    where += (", " + core["district"]) if core.get("district") else ""
    kind = " / ".join([p for p in (core.get("crime_group"), core.get("crime_subhead")) if p]) or "an offence"
    grav = f" (gravity: {core['gravity']})" if core.get("gravity") else ""
    reg = f" on {core['registered_date']}" if core.get("registered_date") else ""
    claims.append(_Claim(
        f"FIR {core.get('crime_no') or cid} was registered{reg}{where} for {kind}{grav}.",
        [case_cite]))

    # 2) Charges — one citation per act-section row.
    if ch["sections"]:
        labels = sorted({s["section"] for s in ch["sections"] if s.get("section")})
        cites = [f"ActSectionAssociation:{cid}:{s['act']}:{s['section']}" for s in ch["sections"]]
        claims.append(_Claim("The case is booked under " + ", ".join(labels) + ".", cites))

    # 3) Incident timing — from the CaseMaster incident window.
    if core.get("incident_from"):
        span = f" on {core['incident_from']}"
        if core.get("incident_to") and core["incident_to"] != core["incident_from"]:
            span += f" through {core['incident_to']}"
        claims.append(_Claim(f"The incident is recorded as occurring{span}.", [case_cite]))

    # 4) Complainant(s).
    if ch["complainants"]:
        cites = [f"ComplainantDetails:{c['id']}" for c in ch["complainants"]]
        claims.append(_Claim(f"The complaint was filed by {_names(ch['complainants'])}.", cites))

    # 5) Victim(s).
    if ch["victims"]:
        cites = [f"Victim:{v['id']}" for v in ch["victims"]]
        claims.append(_Claim(
            f"{len(ch['victims'])} victim(s) are on record, including {_names(ch['victims'])}.", cites))

    # 6) Accused.
    if ch["accused"]:
        cites = [f"Accused:{a['id']}" for a in ch["accused"]]
        claims.append(_Claim(
            f"{len(ch['accused'])} accused person(s) are named, including {_names(ch['accused'])}.", cites))

    # 7) Arrests / surrenders (present -> cite each event; absent -> cite the case
    #    whose arrest child-set is empty, so even the negative claim is grounded).
    if ch["arrests"]:
        dated = [a["date"] for a in ch["arrests"] if a.get("date")]
        earliest = f", the earliest on {min(dated)}" if dated else ""
        cites = [f"ArrestSurrender:{a['id']}" for a in ch["arrests"]]
        claims.append(_Claim(
            f"{len(ch['arrests'])} arrest/surrender event(s) have been recorded{earliest}.", cites))
    else:
        claims.append(_Claim("No arrest or surrender has been recorded for this case.", [case_cite]))

    # 8) Disposition / status.
    if ch["chargesheets"]:
        cs = ch["chargesheets"][-1]
        disp = casedata.CSTYPE_LABEL.get(cs.get("cstype"), "a final report")
        on = f" on {cs['date']}" if cs.get("date") else ""
        claims.append(_Claim(f"The case was disposed as {disp}{on}.", [f"ChargesheetDetails:{cs['id']}"]))
    elif core.get("status"):
        claims.append(_Claim(f"The current case status is {core['status']}.", [case_cite]))

    # 9) Recorded facts (verbatim from the FIR).
    if core.get("brief_facts"):
        claims.append(_Claim(f"Recorded facts: {core['brief_facts']}", [case_cite]))

    return claims


def _build_timeline(core: dict, ch: dict) -> list[dict]:
    cid = core["case_id"]
    events: list[dict] = []
    if core.get("incident_from"):
        events.append({"date": core["incident_from"], "label": "Incident occurred",
                       "citations": [f"CaseMaster:{cid}"]})
    if core.get("registered_date"):
        events.append({"date": core["registered_date"], "label": "FIR registered",
                       "citations": [f"CaseMaster:{cid}"]})
    for a in ch["arrests"]:
        if a.get("date"):
            who = f" (accused {a['accused_id']})" if a.get("accused_id") else ""
            events.append({"date": a["date"], "label": f"Arrest/surrender{who}",
                           "citations": [f"ArrestSurrender:{a['id']}"]})
    for cs in ch["chargesheets"]:
        if cs.get("date"):
            disp = casedata.CSTYPE_LABEL.get(cs.get("cstype"), "final report")
            events.append({"date": cs["date"], "label": f"Disposition: {disp}",
                           "citations": [f"ChargesheetDetails:{cs['id']}"]})
    events.sort(key=lambda e: str(e["date"]))
    return events


def assert_all_cited(claims: list[_Claim]) -> None:
    """OAG guarantee: every claim must carry >=1 citation (no uncited claim)."""
    for c in claims:
        if not c.citations:
            raise ValueError(f"uncited claim would be emitted: {c.text!r}")


def _confidence(core: dict, ch: dict) -> float:
    # More linked evidence -> a more complete, better-grounded summary.
    present = sum(bool(x) for x in (
        ch["sections"], ch["victims"] or ch["complainants"], ch["accused"],
        ch["arrests"], ch["chargesheets"], core.get("brief_facts")))
    return round(min(0.95, 0.6 + 0.06 * present), 4)


def build_summary(conn, case_id: int) -> Optional[dict]:
    """Return the cited summary payload for a case, or None if it doesn't exist."""
    with conn.cursor() as cur:
        core = casedata.fetch_case_core(cur, case_id)
        if not core:
            return None
        ch = casedata.fetch_case_children(cur, case_id)

    claims = _build_claims(core, ch)
    assert_all_cited(claims)  # structural "no uncited claim" guarantee
    timeline = _build_timeline(core, ch)

    # Inline-cited prose: each sentence followed by its bracketed source ids.
    sentences = [{"text": c.text, "citations": c.citations} for c in claims]
    body = " ".join(f"{c.text} [{'; '.join(c.citations)}]" for c in claims)

    all_cites: list[str] = []
    for c in claims:
        for cite in c.citations:
            if cite not in all_cites:
                all_cites.append(cite)

    return {
        "case_id": case_id,
        "crime_no": core.get("crime_no"),
        "summary_text": body,
        "sentences": sentences,
        "timeline": timeline,
        "source_record_ids": all_cites,
        "claim_count": len(claims),
        "cited_claim_count": sum(1 for c in claims if c.citations),
        "confidence": _confidence(core, ch),
    }
