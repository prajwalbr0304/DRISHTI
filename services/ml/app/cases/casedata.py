"""Shared reads of a case and its linked records + the canonical case text.

Everything Phase 10 says about a case is derived STRICTLY from these operational
rows (CaseMaster + children + reference lookups), so every similar-case vector,
every summary claim and every lead traces back to a real source record id. All
identifiers/casing match police_fir_schema.sql exactly.
"""
from __future__ import annotations

from typing import Optional

# One resolved "core" row per case: the CaseMaster fields + human-readable
# lookups (crime heads, gravity, status, district, station, investigating officer).
CASE_CORE_SELECT = '''
    SELECT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate",
           cm."IncidentFromDate", cm."IncidentToDate", cm."BriefFacts",
           cm."latitude", cm."longitude", cm."PoliceStationID", cm."PolicePersonID",
           cm."CrimeMajorHeadID", cm."CrimeMinorHeadID",
           ch."CrimeGroupName", csh."CrimeHeadName",
           grv."LookupValue"  AS gravity,
           st."CaseStatusName",
           d."DistrictID", d."DistrictName", u."UnitName",
           e."FirstName"      AS io_name
    FROM "CaseMaster" cm
    LEFT JOIN "Unit"             u   ON u."UnitID"           = cm."PoliceStationID"
    LEFT JOIN "District"         d   ON d."DistrictID"       = u."DistrictID"
    LEFT JOIN "CrimeHead"        ch  ON ch."CrimeHeadID"     = cm."CrimeMajorHeadID"
    LEFT JOIN "CrimeSubHead"     csh ON csh."CrimeSubHeadID" = cm."CrimeMinorHeadID"
    LEFT JOIN "GravityOffence"   grv ON grv."GravityOffenceID" = cm."GravityOffenceID"
    LEFT JOIN "CaseStatusMaster" st  ON st."CaseStatusID"    = cm."CaseStatusID"
    LEFT JOIN "Employee"         e   ON e."EmployeeID"       = cm."PolicePersonID"
'''

_CORE_COLS = [
    "case_id", "crime_no", "registered_date", "incident_from", "incident_to",
    "brief_facts", "latitude", "longitude", "station_id", "io_employee_id",
    "major_head_id", "minor_head_id", "crime_group", "crime_subhead",
    "gravity", "status", "district_id", "district", "station", "io_name",
]


def _row_to_core(row) -> dict:
    d = dict(zip(_CORE_COLS, row))
    d["registered_date"] = str(d["registered_date"]) if d["registered_date"] else None
    d["incident_from"] = str(d["incident_from"]) if d["incident_from"] else None
    d["incident_to"] = str(d["incident_to"]) if d["incident_to"] else None
    return d


def fetch_case_core(cur, case_id: int) -> Optional[dict]:
    cur.execute(CASE_CORE_SELECT + ' WHERE cm."CaseMasterID" = %s', (case_id,))
    row = cur.fetchone()
    return _row_to_core(row) if row else None


def fetch_case_children(cur, case_id: int) -> dict:
    """Victims, accused, complainants, act-sections, arrests, chargesheets."""
    out: dict = {}

    cur.execute('SELECT "VictimMasterID","VictimName","AgeYear","GenderID" '
                'FROM "Victim" WHERE "CaseMasterID"=%s ORDER BY "VictimMasterID"', (case_id,))
    out["victims"] = [{"id": r[0], "name": r[1], "age": r[2], "gender": r[3]}
                      for r in cur.fetchall()]

    cur.execute('SELECT "AccusedMasterID","AccusedName","AgeYear","PersonID" '
                'FROM "Accused" WHERE "CaseMasterID"=%s ORDER BY "AccusedMasterID"', (case_id,))
    out["accused"] = [{"id": r[0], "name": r[1], "age": r[2], "person_id": r[3]}
                      for r in cur.fetchall()]

    cur.execute('SELECT "ComplainantID","ComplainantName","AgeYear" '
                'FROM "ComplainantDetails" WHERE "CaseMasterID"=%s ORDER BY "ComplainantID"', (case_id,))
    out["complainants"] = [{"id": r[0], "name": r[1], "age": r[2]} for r in cur.fetchall()]

    cur.execute('SELECT a."CaseMasterID", a."ActID", a."SectionID", s."SectionDescription", '
                'ac."ShortName" '
                'FROM "ActSectionAssociation" a '
                'LEFT JOIN "Section" s ON s."SectionCode"=a."SectionID" '
                'LEFT JOIN "Act" ac ON ac."ActCode"=a."ActID" '
                'WHERE a."CaseMasterID"=%s ORDER BY a."ActID", a."SectionID"', (case_id,))
    out["sections"] = [{"act": r[1], "section": r[2], "description": r[3], "act_name": r[4]}
                       for r in cur.fetchall()]

    cur.execute('SELECT "ArrestSurrenderID","AccusedMasterID","ArrestSurrenderDate",'
                '"IOID","ArrestSurrenderTypeID" '
                'FROM "ArrestSurrender" WHERE "CaseMasterID"=%s ORDER BY "ArrestSurrenderID"', (case_id,))
    out["arrests"] = [{"id": r[0], "accused_id": r[1],
                       "date": str(r[2]) if r[2] else None, "io_id": r[3], "type": r[4]}
                      for r in cur.fetchall()]

    cur.execute('SELECT "CSID","csdate","cstype"::text '
                'FROM "ChargesheetDetails" WHERE "CaseMasterID"=%s ORDER BY "CSID"', (case_id,))
    out["chargesheets"] = [{"id": r[0], "date": str(r[1]) if r[1] else None, "cstype": r[2]}
                           for r in cur.fetchall()]
    return out


# cstype_enum: A=Chargesheet, B=False Case, C=Undetected
CSTYPE_LABEL = {"A": "chargesheet filed", "B": "closed as false case",
                "C": "closed as undetected"}


def section_labels(sections: list[dict]) -> list[str]:
    """['IPC 302', 'NDPS 20', ...] — the charge tokens used in text + citations."""
    return [f"{s['act']} {s['section']}" for s in sections if s.get("act")]


def canonical_text(core: dict, sections: list[str], n_victims: int, n_accused: int) -> str:
    """The text that gets embedded — a compact, MO-forward description of the case.

    Shared by the corpus embed job and the live query embed so both land in the
    same vector space. Ordered most-discriminative-first (crime type, charges,
    gravity) so semantically similar crimes cluster under cosine distance.
    """
    parts: list[str] = []
    if core.get("crime_group"):
        parts.append(str(core["crime_group"]))
    if core.get("crime_subhead"):
        parts.append(str(core["crime_subhead"]))
    if sections:
        parts.append("Charges: " + ", ".join(sections))
    if core.get("gravity"):
        parts.append(f"Gravity: {core['gravity']}")
    if core.get("district"):
        parts.append(f"District: {core['district']}")
    parts.append(f"Victims: {n_victims}, accused: {n_accused}")
    if core.get("registered_date"):
        parts.append(f"Registered: {str(core['registered_date'])[:4]}")
    if core.get("brief_facts"):
        parts.append(str(core["brief_facts"]))
    return ". ".join(parts)


def select_corpus_case_ids(cur, limit: Optional[int]) -> list[int]:
    """Case ids to embed for the corpus. Stratified across crime sub-heads (the MO
    axis) so every crime type is represented, then capped to `limit` (None/0 = all)."""
    if not limit or limit <= 0:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID"')
        return [int(r[0]) for r in cur.fetchall()]
    cur.execute(
        '''WITH ranked AS (
               SELECT "CaseMasterID",
                      ROW_NUMBER() OVER (PARTITION BY "CrimeMinorHeadID"
                                         ORDER BY "CaseMasterID") AS rn
               FROM "CaseMaster")
           SELECT "CaseMasterID" FROM ranked
           ORDER BY rn, "CaseMasterID"
           LIMIT %s''', (int(limit),))
    return [int(r[0]) for r in cur.fetchall()]


def fetch_corpus_batch(cur, ids: list[int]) -> list[dict]:
    """Bulk-fetch {case_id, head_id, text} for a batch of case ids (one round trip).

    Sections are string_agg'd and victim/accused counts are lateral subqueries so
    the canonical text can be built without an N+1 per case."""
    if not ids:
        return []
    cur.execute(
        'SELECT core.*, '
        '(SELECT COUNT(*) FROM "Victim" v  WHERE v."CaseMasterID"=core."CaseMasterID"), '
        '(SELECT COUNT(*) FROM "Accused" a WHERE a."CaseMasterID"=core."CaseMasterID"), '
        '(SELECT string_agg(DISTINCT sa."ActID" || \' \' || sa."SectionID", \', \') '
        ' FROM "ActSectionAssociation" sa WHERE sa."CaseMasterID"=core."CaseMasterID") '
        'FROM (' + CASE_CORE_SELECT + ' WHERE cm."CaseMasterID" = ANY(%s)) core',
        (ids,))
    rows = cur.fetchall()
    ncore = len(_CORE_COLS)
    out = []
    for row in rows:
        core = _row_to_core(row[:ncore])
        n_vic, n_acc, sec_str = row[ncore], row[ncore + 1], row[ncore + 2]
        secs = [s.strip() for s in sec_str.split(",")] if sec_str else []
        out.append({
            "case_id": core["case_id"],
            "head_id": core["major_head_id"],
            "text": canonical_text(core, secs, int(n_vic or 0), int(n_acc or 0)),
        })
    return out


def case_query_text(cur, case_id: int) -> Optional[dict]:
    """Canonical text for a single (query) case — same shape as the corpus rows."""
    batch = fetch_corpus_batch(cur, [case_id])
    return batch[0] if batch else None
