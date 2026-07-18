"""Read-only Case Explorer + Case-file data (Phase 15c).

Raw operational reads over CaseMaster and its children for the Cases UI:
list/search with filters, a full case detail (Overview/Timeline/people/sections),
a case-centric mini network (co-accused + name-linked cases), and the evidence
feed. All identifiers/casing match police_fir_schema.sql. Reads run under the
read-only role; the evidence write uses the read/write layer and is IO-gated.

These are plain data resources (not model outputs) so they DON'T wear the
AiResult contract — that is reserved for the AI endpoints (summary/leads/similar).
"""
from __future__ import annotations

from typing import Any, Optional

from psycopg2 import errors as pg_errors

from .. import db
from . import casedata

# ---------------------------------------------------------------------------
# Case Explorer — filterable list
# ---------------------------------------------------------------------------

_LIST_FROM = '''
    FROM "CaseMaster" cm
    LEFT JOIN "Unit"             u   ON u."UnitID"           = cm."PoliceStationID"
    LEFT JOIN "District"         d   ON d."DistrictID"       = u."DistrictID"
    LEFT JOIN "CrimeHead"        ch  ON ch."CrimeHeadID"     = cm."CrimeMajorHeadID"
    LEFT JOIN "CrimeSubHead"     csh ON csh."CrimeSubHeadID" = cm."CrimeMinorHeadID"
    LEFT JOIN "GravityOffence"   grv ON grv."GravityOffenceID" = cm."GravityOffenceID"
    LEFT JOIN "CaseStatusMaster" st  ON st."CaseStatusID"    = cm."CaseStatusID"
'''

_LIST_COLS = [
    "case_id", "crime_no", "case_no", "registered_date", "status_id", "status",
    "crime_group", "crime_subhead", "gravity", "district_id", "district",
    "station_id", "station", "latitude", "longitude", "brief_facts",
    "victim_count", "accused_count", "has_arrest", "has_chargesheet",
]

_LIST_SELECT = '''
    SELECT cm."CaseMasterID"        AS case_id,
           cm."CrimeNo"             AS crime_no,
           cm."CaseNo"              AS case_no,
           cm."CrimeRegisteredDate" AS registered_date,
           cm."CaseStatusID"        AS status_id,
           st."CaseStatusName"      AS status,
           ch."CrimeGroupName"      AS crime_group,
           csh."CrimeHeadName"      AS crime_subhead,
           grv."LookupValue"        AS gravity,
           d."DistrictID"           AS district_id,
           d."DistrictName"         AS district,
           cm."PoliceStationID"     AS station_id,
           u."UnitName"             AS station,
           cm."latitude"            AS latitude,
           cm."longitude"           AS longitude,
           LEFT(cm."BriefFacts", 240) AS brief_facts,
           (SELECT COUNT(*) FROM "Victim"  v  WHERE v."CaseMasterID" = cm."CaseMasterID")  AS victim_count,
           (SELECT COUNT(*) FROM "Accused" a  WHERE a."CaseMasterID" = cm."CaseMasterID")  AS accused_count,
           EXISTS(SELECT 1 FROM "ArrestSurrender"    ar WHERE ar."CaseMasterID" = cm."CaseMasterID") AS has_arrest,
           EXISTS(SELECT 1 FROM "ChargesheetDetails" cs WHERE cs."CaseMasterID" = cm."CaseMasterID") AS has_chargesheet
''' + _LIST_FROM


def _build_filters(f: dict) -> tuple[str, list]:
    clauses: list[str] = []
    params: list[Any] = []
    if f.get("district_id"):
        clauses.append('d."DistrictID" = %s'); params.append(f["district_id"])
    if f.get("station_id"):
        clauses.append('cm."PoliceStationID" = %s'); params.append(f["station_id"])
    if f.get("major_head_id"):
        clauses.append('cm."CrimeMajorHeadID" = %s'); params.append(f["major_head_id"])
    if f.get("minor_head_id"):
        clauses.append('cm."CrimeMinorHeadID" = %s'); params.append(f["minor_head_id"])
    if f.get("status_id"):
        clauses.append('cm."CaseStatusID" = %s'); params.append(f["status_id"])
    if f.get("gravity_id"):
        clauses.append('cm."GravityOffenceID" = %s'); params.append(f["gravity_id"])
    if f.get("date_from"):
        clauses.append('cm."CrimeRegisteredDate" >= %s'); params.append(f["date_from"])
    if f.get("date_to"):
        clauses.append('cm."CrimeRegisteredDate" <= %s'); params.append(f["date_to"])
    if f.get("has_arrest"):
        clauses.append('EXISTS(SELECT 1 FROM "ArrestSurrender" ar WHERE ar."CaseMasterID" = cm."CaseMasterID")')
    if f.get("has_chargesheet"):
        clauses.append('EXISTS(SELECT 1 FROM "ChargesheetDetails" cs WHERE cs."CaseMasterID" = cm."CaseMasterID")')
    if f.get("q"):
        like = f"%{f['q'].strip()}%"
        clauses.append('(cm."CrimeNo" ILIKE %s OR cm."CaseNo" ILIKE %s OR cm."BriefFacts" ILIKE %s)')
        params.extend([like, like, like])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_cases(filters: dict, page: int = 1, page_size: int = 25) -> dict:
    where, params = _build_filters(filters)
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) {_LIST_FROM}{where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'{_LIST_SELECT}{where} '
                'ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST, cm."CaseMasterID" DESC '
                "LIMIT %s OFFSET %s",
                params + [page_size, offset])
            rows = cur.fetchall()
    items = []
    for r in rows:
        d = dict(zip(_LIST_COLS, r))
        d["registered_date"] = str(d["registered_date"]) if d["registered_date"] else None
        d["latitude"] = float(d["latitude"]) if d["latitude"] is not None else None
        d["longitude"] = float(d["longitude"]) if d["longitude"] is not None else None
        d["victim_count"] = int(d["victim_count"] or 0)
        d["accused_count"] = int(d["accused_count"] or 0)
        items.append(d)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def filter_options() -> dict:
    """Reference values for the Explorer's filter rail (real lookups)."""
    def rows(cur, sql):
        cur.execute(sql)
        return [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            return {
                "districts": rows(cur, 'SELECT "DistrictID","DistrictName" FROM "District" ORDER BY "DistrictName"'),
                "stations": rows(cur, 'SELECT "UnitID","UnitName" FROM "Unit" ORDER BY "UnitName" LIMIT 1000'),
                "crime_heads": rows(cur, 'SELECT "CrimeHeadID","CrimeGroupName" FROM "CrimeHead" ORDER BY "CrimeGroupName"'),
                "sub_heads": rows(cur, 'SELECT "CrimeSubHeadID","CrimeHeadName" FROM "CrimeSubHead" ORDER BY "CrimeHeadName"'),
                "statuses": rows(cur, 'SELECT "CaseStatusID","CaseStatusName" FROM "CaseStatusMaster" ORDER BY "CaseStatusID"'),
                "gravities": rows(cur, 'SELECT "GravityOffenceID","LookupValue" FROM "GravityOffence" ORDER BY "GravityOffenceID"'),
            }


# ---------------------------------------------------------------------------
# Case detail (Overview / Timeline / people / sections)
# ---------------------------------------------------------------------------

def _timeline(core: dict, children: dict) -> list[dict]:
    """Derive a typed lifecycle timeline from the case's real dated records."""
    ev: list[dict] = []
    if core.get("registered_date"):
        ev.append({"date": core["registered_date"], "type": "registered",
                   "label": "FIR registered", "detail": core.get("crime_no")})
    if core.get("incident_from"):
        ev.append({"date": core["incident_from"], "type": "incident",
                   "label": "Incident window (from)", "detail": None})
    if core.get("incident_to") and core.get("incident_to") != core.get("incident_from"):
        ev.append({"date": core["incident_to"], "type": "incident",
                   "label": "Incident window (to)", "detail": None})
    for a in children.get("arrests", []):
        if a.get("date"):
            ev.append({"date": a["date"], "type": "arrest", "label": "Arrest / surrender",
                       "detail": f"Accused #{a['accused_id']}" if a.get("accused_id") else None})
    for c in children.get("chargesheets", []):
        if c.get("date"):
            ev.append({"date": c["date"], "type": "chargesheet",
                       "label": casedata.CSTYPE_LABEL.get(c.get("cstype"), "Chargesheet"),
                       "detail": c.get("cstype")})
    ev.sort(key=lambda e: str(e["date"]))
    return ev


def case_detail(case_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            core = casedata.fetch_case_core(cur, case_id)
            if core is None:
                return None
            children = casedata.fetch_case_children(cur, case_id)
    sections = casedata.section_labels(children.get("sections", []))
    return {
        "core": core,
        "sections": children.get("sections", []),
        "section_labels": sections,
        "victims": children.get("victims", []),
        "accused": children.get("accused", []),
        "complainants": children.get("complainants", []),
        "arrests": children.get("arrests", []),
        "chargesheets": children.get("chargesheets", []),
        "timeline": _timeline(core, children),
    }


# ---------------------------------------------------------------------------
# Case network (cases linked through a SHARED CANONICAL accused person)
# ---------------------------------------------------------------------------

def case_network(case_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            core = casedata.fetch_case_core(cur, case_id)
            if core is None:
                return None
            cur.execute('SELECT "AccusedMasterID","AccusedName" FROM "Accused" '
                        'WHERE "CaseMasterID"=%s ORDER BY "AccusedMasterID"', (case_id,))
            accused = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
            # Other cases sharing a CANONICAL accused person (Phase 4). Canonical
            # identity is the honest cross-case link; duplicate names never join.
            cur.execute(
                'SELECT DISTINCT r2."CaseMasterID", cm2."CrimeNo", ch."CrimeGroupName", '
                ' COALESCE(p."DisplayLabel", p."PublicRef") '
                'FROM "CasePartyRole" r1 '
                'JOIN "CasePartyRole" r2 ON r2."CanonicalPersonID" = r1."CanonicalPersonID" '
                '                        AND r2."CaseMasterID" <> r1."CaseMasterID" '
                '                        AND r2."RoleType" = \'accused\' '
                'JOIN "CanonicalPerson" p ON p."CanonicalPersonID" = r1."CanonicalPersonID" '
                'JOIN "CaseMaster" cm2 ON cm2."CaseMasterID" = r2."CaseMasterID" '
                'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm2."CrimeMajorHeadID" '
                'WHERE r1."CaseMasterID"=%s AND r1."RoleType"=\'accused\' '
                '  AND r1."CanonicalPersonID" IS NOT NULL AND p."IsUnknown"=FALSE '
                'ORDER BY r2."CaseMasterID" LIMIT 30', (case_id,))
            linked = [{"case_id": r[0], "crime_no": r[1], "crime_group": r[2], "via": r[3]}
                      for r in cur.fetchall()]

    root = f"case:{case_id}"
    nodes: list[dict] = [{"id": root, "kind": "case", "label": core.get("crime_no") or f"Case {case_id}",
                          "sub": core.get("crime_group"), "root": True}]
    edges: list[dict] = []
    for a in accused:
        nid = f"acc:{a['id']}"
        nodes.append({"id": nid, "kind": "accused", "label": a["name"], "sub": "Accused", "root": False})
        edges.append({"source": root, "target": nid, "type": "accused"})
    for lk in linked:
        nid = f"case:{lk['case_id']}"
        if any(n["id"] == nid for n in nodes):
            continue
        nodes.append({"id": nid, "kind": "case", "label": lk["crime_no"] or f"Case {lk['case_id']}",
                      "sub": lk["crime_group"], "root": False, "case_id": lk["case_id"]})
        edges.append({"source": root, "target": nid, "type": "shared-accused", "label": lk["via"]})

    return {
        "case_id": case_id,
        "crime_no": core.get("crime_no"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "linked_case_count": len(linked),
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Evidence (read + IO-gated write)
# ---------------------------------------------------------------------------

_EVIDENCE_EXISTS = 'SELECT to_regclass(\'public."CaseEvidence"\')'


def _evidence_row(r) -> dict:
    return {
        "evidence_id": int(r[0]),
        "evidence_type": r[1],
        "title": r[2],
        "description": r[3],
        "reference": r[4],
        "created_by_role": r[5],
        "created_at": str(r[6]) if r[6] else None,
    }


def list_evidence(case_id: int) -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_EVIDENCE_EXISTS)
            if cur.fetchone()[0] is None:
                return {"available": False, "items": []}
            cur.execute(
                'SELECT "EvidenceID","EvidenceType","Title","Description","Reference",'
                '"CreatedByRole","CreatedAt" FROM "CaseEvidence" '
                'WHERE "CaseMasterID"=%s ORDER BY "CreatedAt" DESC, "EvidenceID" DESC', (case_id,))
            items = [_evidence_row(r) for r in cur.fetchall()]
    return {"available": True, "items": items}


# Sentinels for the router to translate into HTTP responses.
NO_TABLE = object()
NO_CASE = object()


def add_evidence(case_id: int, evidence_type: str, title: str,
                 description: Optional[str], reference: Optional[str], role: str):
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_EVIDENCE_EXISTS)
            if cur.fetchone()[0] is None:
                return NO_TABLE
            cur.execute('SELECT 1 FROM "CaseMaster" WHERE "CaseMasterID"=%s', (case_id,))
            if not cur.fetchone():
                return NO_CASE
            try:
                cur.execute(
                    'INSERT INTO "CaseEvidence" '
                    '("CaseMasterID","EvidenceType","Title","Description","Reference","CreatedByRole") '
                    'VALUES (%s,%s,%s,%s,%s,%s) '
                    'RETURNING "EvidenceID","EvidenceType","Title","Description","Reference",'
                    '"CreatedByRole","CreatedAt"',
                    (case_id, evidence_type, title, description, reference, role))
            except pg_errors.CheckViolation:
                conn.rollback()
                raise ValueError(f"Invalid evidence type '{evidence_type}'.")
            row = cur.fetchone()
    return _evidence_row(row)
