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
    LEFT JOIN LATERAL (
        SELECT cv0."SnapshotAttributes" AS attrs
        FROM "CaseVersion" cv0
        WHERE cv0."CaseMasterID"=cm."CaseMasterID" AND cv0."IsCurrent"=TRUE
        ORDER BY cv0."VersionNo" DESC LIMIT 1
    ) cv ON TRUE
'''

_LIST_COLS = [
    "case_id", "crime_no", "internal_crime_no", "case_no", "registered_date",
    "status_id", "status", "crime_group", "crime_subhead", "gravity",
    "district_id", "district", "station_id", "station", "latitude", "longitude",
    "brief_facts", "record_origin", "is_synthetic", "reference_mapping_kind",
    "location_label", "location_precision", "not_exact_incident_scene",
    "location_uncertainty_radius_m", "location_attribution",
    "victim_count", "accused_count", "has_arrest", "has_chargesheet",
]

_LIST_SELECT = '''
    SELECT cm."CaseMasterID" AS case_id,
           COALESCE(NULLIF(cv.attrs #>> '{official_references,police_crime_no}', ''),
                    cm."CrimeNo") AS crime_no,
           cm."CrimeNo" AS internal_crime_no,
           cm."CaseNo" AS case_no,
           cm."CrimeRegisteredDate" AS registered_date,
           cm."CaseStatusID" AS status_id,
           st."CaseStatusName" AS status,
           ch."CrimeGroupName" AS crime_group,
           csh."CrimeHeadName" AS crime_subhead,
           grv."LookupValue" AS gravity,
           d."DistrictID" AS district_id,
           d."DistrictName" AS district,
           cm."PoliceStationID" AS station_id,
           CASE WHEN cv.attrs #>> '{reference_mapping,kind}' = 'proxy'
                THEN NULLIF(cv.attrs #>> '{reference_mapping,public_station_label}', '')
                ELSE u."UnitName" END AS station,
           cm."latitude" AS latitude,
           cm."longitude" AS longitude,
           LEFT(cm."BriefFacts", 240) AS brief_facts,
           COALESCE(NULLIF(cv.attrs->>'record_origin', ''), 'synthetic_fixture') AS record_origin,
           COALESCE((cv.attrs->>'is_synthetic')::boolean, TRUE) AS is_synthetic,
           cv.attrs #>> '{reference_mapping,kind}' AS reference_mapping_kind,
           cv.attrs #>> '{location,label}' AS location_label,
           cv.attrs #>> '{location,precision}' AS location_precision,
           COALESCE((cv.attrs #>> '{location,not_exact_incident_scene}')::boolean,
                    FALSE) AS not_exact_incident_scene,
           NULLIF(cv.attrs #>> '{location,uncertainty_radius_m}', '')::int
                AS location_uncertainty_radius_m,
           cv.attrs #>> '{location,attribution}' AS location_attribution,
           (SELECT COUNT(*) FROM "Victim"  v  WHERE v."CaseMasterID" = cm."CaseMasterID")  AS victim_count,
           (SELECT COUNT(*) FROM "Accused" a  WHERE a."CaseMasterID" = cm."CaseMasterID")  AS accused_count,
           EXISTS(SELECT 1 FROM "ArrestSurrender"    ar WHERE ar."CaseMasterID" = cm."CaseMasterID") AS has_arrest,
           EXISTS(SELECT 1 FROM "ChargesheetDetails" cs WHERE cs."CaseMasterID" = cm."CaseMasterID") AS has_chargesheet
''' + _LIST_FROM


def _build_filters(f: dict, *, analytics_only: bool = False) -> tuple[str, list]:
    clauses: list[str] = []
    params: list[Any] = []
    if f.get("district_id"):
        clauses.append('d."DistrictID" = %s'); params.append(f["district_id"])
    if f.get("station_id"):
        # A deterministic fixture proxy is not an operational station
        # assignment and must never satisfy station-level filtering.
        clauses.append(
            'cm."PoliceStationID" = %s AND '
            'COALESCE(cv.attrs #>> \'{reference_mapping,kind}\', \'\') <> \'proxy\''
        )
        params.append(f["station_id"])
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
        clauses.append(
            '''(
                concat_ws(' ', cm."CrimeNo", cm."CaseNo", cm."BriefFacts",
                    cv.attrs #>> '{official_references,police_crime_no}',
                    cv.attrs #>> '{official_references,committal_case_no}',
                    cv.attrs #>> '{official_references,sessions_case_no}') ILIKE %s
                OR EXISTS (
                    SELECT 1 FROM "CasePartyRole" cpr
                    LEFT JOIN "CanonicalPerson" cp
                      ON cp."CanonicalPersonID"=cpr."CanonicalPersonID"
                    LEFT JOIN "PersonAlias" pa
                      ON pa."CanonicalPersonID"=cpr."CanonicalPersonID"
                    WHERE cpr."CaseMasterID"=cm."CaseMasterID"
                      AND concat_ws(' ', cpr."PartyLabel", cp."DisplayLabel",
                                    cp."PublicRef", pa."AliasName") ILIKE %s
                )
                OR EXISTS (
                    SELECT 1 FROM "CaseSource" cs
                    JOIN "SourceRecord" sr ON sr."SourceRecordID"=cs."SourceRecordID"
                    WHERE cs."CaseMasterID"=cm."CaseMasterID"
                      AND sr."Payload"->>'record_origin'='public_source_curated'
                      AND COALESCE(sr."Payload"->>'availability_only', 'false') <> 'true'
                      AND concat_ws(' ', sr."ExternalRef", sr."Payload"->>'id',
                                    sr."Payload"->>'title', sr."Payload"->>'publisher',
                                    sr."Payload"->>'official_crime_reference') ILIKE %s
                )
                OR EXISTS (
                    SELECT 1 FROM "EvidenceItem" ei
                    WHERE ei."CaseMasterID"=cm."CaseMasterID"
                      AND concat_ws(' ', ei."Title", ei."Description",
                                    ei."SyntheticReference",
                                    array_to_string(ei."Tags", ' ')) ILIKE %s
                )
            )'''
        )
        params.extend([like, like, like, like])
    if analytics_only:
        clauses.append(casedata.analytics_eligible_sql("cm"))
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
# Caseload summary — per-stage counts for the Command Center pipeline
# ---------------------------------------------------------------------------

# The canonical FIR-lifecycle stages the Command Center pipeline renders
# (doc 01 §4.1 / doc 03 §2.13). Each case sits in exactly ONE stage, so the
# per-stage counts always sum to the in-scope total.
CASELOAD_STAGES: list[tuple[str, str]] = [
    ("registered", "Registered"),
    ("under_investigation", "Under investigation"),
    ("chargesheet", "Chargesheeted"),
    ("trial", "Trial"),
    ("disposed", "Disposed"),
]

# Fold each real CaseStatusMaster.CaseStatusName onto a canonical stage. The
# still-active "Missing - Under Trace" stays under investigation; every terminal
# outcome (convicted / acquitted / B-report / C-report / transferred / untraced /
# enquiry- or inquest-closed / reclassified / recovered) folds into "disposed".
# A NULL / unrecognised status falls back to "registered" (a freshly-registered
# FIR not yet actioned) so no case is ever dropped from the total.
STATUS_TO_STAGE: dict[str, str] = {
    "Under Investigation": "under_investigation",
    "Missing - Under Trace": "under_investigation",
    "Charge Sheeted": "chargesheet",
    "Pending Trial": "trial",
    "Closed - Convicted": "disposed",
    "Closed - Acquitted": "disposed",
    "Undetected / B-Report": "disposed",
    "False / C-Report": "disposed",
    "Transferred": "disposed",
    "Missing - Recovered": "disposed",
    "Closed - Untraced": "disposed",
    "Enquiry Closed": "disposed",
    "Inquest Closed": "disposed",
    "Converted / Reclassified": "disposed",
}

_CASELOAD_DEFAULT_STAGE = "registered"
_CASELOAD_DISPOSED_STAGE = "disposed"


def caseload_summary(filters: dict) -> dict:
    """Per-stage caseload counts (a present-state snapshot) for the pipeline.

    Reuses the Explorer filter builder, so the same jurisdiction / date / crime
    filters scope the caseload. Every case maps to exactly one canonical stage
    via its current status, so the stage counts sum to ``total``. Also returns
    the raw per-status breakdown (for tooltips) and open/disposed splits.
    """
    where, params = _build_filters(filters, analytics_only=True)
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT st."CaseStatusName", COUNT(*) '
                + _LIST_FROM + where +
                ' GROUP BY st."CaseStatusName"',
                params)
            rows = cur.fetchall()

    counts = {key: 0 for key, _ in CASELOAD_STAGES}
    by_status: list[dict] = []
    total = 0
    for name, n in rows:
        n = int(n)
        total += n
        stage = STATUS_TO_STAGE.get(name, _CASELOAD_DEFAULT_STAGE) if name else _CASELOAD_DEFAULT_STAGE
        counts[stage] += n
        by_status.append({"status": name or "Unspecified", "stage": stage, "count": n})
    by_status.sort(key=lambda r: r["count"], reverse=True)

    stages = [{"key": key, "label": label, "count": counts[key]}
              for key, label in CASELOAD_STAGES]
    disposed_total = counts[_CASELOAD_DISPOSED_STAGE]
    return {
        "stages": stages,
        "by_status": by_status,
        "total": total,
        "open_total": total - disposed_total,
        "disposed_total": disposed_total,
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
            provenance = casedata.fetch_case_provenance(cur, case_id)
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
        **provenance,
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
