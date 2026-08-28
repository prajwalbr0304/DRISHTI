"""Shared reads of a case and its linked records + the canonical case text.

Everything Phase 10 says about a case is derived STRICTLY from these operational
rows (CaseMaster + children + reference lookups), so every similar-case vector,
every summary claim and every lead traces back to a real source record id. All
identifiers/casing match police_fir_schema.sql exactly.
"""
from __future__ import annotations

from typing import Optional

from . import analytics_policy


def analytics_eligible_sql(alias: str = "cm") -> str:
    """SQL predicate for the versioned, fail-closed case analytics policy."""
    return analytics_policy.analytics_eligible_sql(alias)


# One resolved "core" row per case: CaseMaster plus presentation-safe lookups.
# For a source-curated case, the official public reference replaces the internal
# surrogate in ``crime_no`` and disclosed proxy authority labels are suppressed.
CASE_CORE_SELECT = '''
    SELECT cm."CaseMasterID",
           COALESCE(NULLIF(cv."SnapshotAttributes" #>> '{official_references,police_crime_no}', ''),
                    cm."CrimeNo") AS "CrimeNo",
           cm."CrimeRegisteredDate",
           cm."IncidentFromDate", cm."IncidentToDate", cm."BriefFacts",
           cm."latitude", cm."longitude", cm."PoliceStationID", cm."PolicePersonID",
           cm."CrimeMajorHeadID", cm."CrimeMinorHeadID",
           ch."CrimeGroupName", csh."CrimeHeadName",
           grv."LookupValue"  AS gravity,
           st."CaseStatusName",
           d."DistrictID", d."DistrictName",
           CASE WHEN cv."SnapshotAttributes" #>> '{reference_mapping,kind}' = 'proxy'
                THEN NULLIF(cv."SnapshotAttributes" #>> '{reference_mapping,public_station_label}', '')
                ELSE u."UnitName" END AS station,
           CASE WHEN cv."SnapshotAttributes" #>> '{reference_mapping,kind}' = 'proxy'
                THEN NULL ELSE e."FirstName" END AS io_name,
           cm."CrimeNo" AS internal_crime_no,
           COALESCE(NULLIF(cv."SnapshotAttributes"->>'record_origin', ''),
                    'synthetic_fixture') AS record_origin,
           COALESCE((cv."SnapshotAttributes"->>'is_synthetic')::boolean, TRUE) AS is_synthetic,
           cv."SnapshotAttributes" #>> '{reference_mapping,kind}' AS reference_mapping_kind,
           cv."SnapshotAttributes" #>> '{location,label}' AS location_label,
           cv."SnapshotAttributes" #>> '{location,precision}' AS location_precision,
           COALESCE((cv."SnapshotAttributes" #>> '{location,not_exact_incident_scene}')::boolean,
                    FALSE) AS not_exact_incident_scene,
           NULLIF(cv."SnapshotAttributes" #>> '{location,uncertainty_radius_m}', '')::int
                AS location_uncertainty_radius_m,
           cv."SnapshotAttributes" #>> '{location,attribution}' AS location_attribution
    FROM "CaseMaster" cm
    LEFT JOIN "Unit"             u   ON u."UnitID"           = cm."PoliceStationID"
    LEFT JOIN "District"         d   ON d."DistrictID"       = u."DistrictID"
    LEFT JOIN "CrimeHead"        ch  ON ch."CrimeHeadID"     = cm."CrimeMajorHeadID"
    LEFT JOIN "CrimeSubHead"     csh ON csh."CrimeSubHeadID" = cm."CrimeMinorHeadID"
    LEFT JOIN "GravityOffence"   grv ON grv."GravityOffenceID" = cm."GravityOffenceID"
    LEFT JOIN "CaseStatusMaster" st  ON st."CaseStatusID"    = cm."CaseStatusID"
    LEFT JOIN "Employee"         e   ON e."EmployeeID"       = cm."PolicePersonID"
    LEFT JOIN LATERAL (
        SELECT cv0."SnapshotAttributes"
        FROM "CaseVersion" cv0
        WHERE cv0."CaseMasterID"=cm."CaseMasterID" AND cv0."IsCurrent"=TRUE
        ORDER BY cv0."VersionNo" DESC LIMIT 1
    ) cv ON TRUE
'''

_CORE_COLS = [
    "case_id", "crime_no", "registered_date", "incident_from", "incident_to",
    "brief_facts", "latitude", "longitude", "station_id", "io_employee_id",
    "major_head_id", "minor_head_id", "crime_group", "crime_subhead",
    "gravity", "status", "district_id", "district", "station", "io_name",
    "internal_crime_no", "record_origin", "is_synthetic", "reference_mapping_kind",
    "location_label", "location_precision", "not_exact_incident_scene",
    "location_uncertainty_radius_m", "location_attribution",
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
    """Case ids eligible for derived embeddings, stratified by crime sub-head.

    Source-curated records can remain discoverable as governed case files while
    explicitly opting out of vector corpora and related model-derived outputs.
    """
    eligible = analytics_eligible_sql("cm")
    if not limit or limit <= 0:
        cur.execute(
            f'SELECT cm."CaseMasterID" FROM "CaseMaster" cm '
            f'WHERE {eligible} ORDER BY cm."CaseMasterID"'
        )
        return [int(r[0]) for r in cur.fetchall()]
    cur.execute(
        f'''WITH ranked AS (
               SELECT cm."CaseMasterID",
                      ROW_NUMBER() OVER (PARTITION BY cm."CrimeMinorHeadID"
                                         ORDER BY cm."CaseMasterID") AS rn
               FROM "CaseMaster" cm
               WHERE {eligible})
           SELECT "CaseMasterID" FROM ranked
           ORDER BY rn, "CaseMasterID"
           LIMIT %s''', (int(limit),))
    return [int(r[0]) for r in cur.fetchall()]


def fetch_corpus_batch(cur, ids: list[int]) -> list[dict]:
    """Bulk-fetch only analytics-eligible corpus records for the requested ids.

    The defensive policy check remains here even though callers normally obtain
    ids through :func:`select_corpus_case_ids`; direct or stale-id callers cannot
    bypass a case's current exclusion marker.
    """
    if not ids:
        return []
    eligible = analytics_eligible_sql("cm")
    cur.execute(
        'SELECT core.*, '
        '(SELECT COUNT(*) FROM "Victim" v  WHERE v."CaseMasterID"=core."CaseMasterID"), '
        '(SELECT COUNT(*) FROM "Accused" a WHERE a."CaseMasterID"=core."CaseMasterID"), '
        '(SELECT string_agg(DISTINCT sa."ActID" || \' \' || sa."SectionID", \', \') '
        ' FROM "ActSectionAssociation" sa WHERE sa."CaseMasterID"=core."CaseMasterID") '
        'FROM (' + CASE_CORE_SELECT + f' WHERE cm."CaseMasterID" = ANY(%s) AND {eligible}) core',
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


# Stable legal/source notices emitted only when a CaseVersion explicitly opts in.
_CASE_NOTICE_CATALOG = {
    "PENDING_TRIAL": {
        "code": "PENDING_TRIAL",
        "severity": "warning",
        "title": "Trial pending",
        "message": "No final verdict or finding of guilt is represented. All accused retain the presumption of innocence.",
    },
    "ALLEGATION_NOT_FINDING": {
        "code": "ALLEGATION_NOT_FINDING",
        "severity": "warning",
        "title": "Allegations, not findings",
        "message": "Narrative events describe the prosecution case or public reporting and must not be presented as proven facts.",
    },
    "PUBLIC_SOURCE_REFERENCE": {
        "code": "PUBLIC_SOURCE_REFERENCE",
        "severity": "info",
        "title": "Public-source references",
        "message": "Linked court and publisher records are attribution references, not certified court copies or forensic originals.",
    },
}


def fetch_case_provenance(cur, case_id: int) -> dict:
    """Return the current case origin plus a compact, safe source inventory.

    Source summaries expose attribution and handling caveats only. Native evidence,
    private identifiers, excluded graphic material, and raw SourceRecord payloads
    are never returned by the case-detail endpoint.
    """
    cur.execute(
        'SELECT "CaseVersionID","VersionNo","StatusCode","SnapshotAttributes",'
        '"ChangeReason" FROM "CaseVersion" '
        'WHERE "CaseMasterID"=%s AND "IsCurrent"=TRUE '
        'ORDER BY "VersionNo" DESC LIMIT 1',
        (case_id,),
    )
    row = cur.fetchone()
    current_version = None
    notice_codes: list[str] = []
    if row:
        attrs = row[3] or {}
        if not isinstance(attrs, dict):
            attrs = {}
        origin = attrs.get("record_origin") or "synthetic_fixture"
        current_version = {
            "case_version_id": int(row[0]),
            "version_no": int(row[1]),
            "status_code": row[2],
            "record_origin": origin,
            "is_synthetic": bool(attrs.get("is_synthetic", origin != "public_source_curated")),
            "read_only": origin == "public_source_curated",
            "excluded_from_derived_analytics": bool(
                attrs.get("excluded_from_derived_analytics", False)
            ),
            "source_cutoff": attrs.get("source_cutoff"),
            "official_references": attrs.get("official_references") or {},
            "reference_mapping": attrs.get("reference_mapping") or {},
            "location": attrs.get("location") or {},
            "change_reason": row[4],
        }
        notice_codes = [
            str(code) for code in (attrs.get("notices") or [])
            if str(code) in _CASE_NOTICE_CATALOG
        ]
        # PENDING_TRIAL is a current-state safeguard, not immutable prose from
        # the initial snapshot. Suppress it if a later sourced version advances
        # status or if any final judgment/disposition has been recorded.
        if "PENDING_TRIAL" in notice_codes:
            pending_is_current = row[2] == "pending_trial"
            if pending_is_current:
                cur.execute(
                    'SELECT EXISTS(SELECT 1 FROM "CaseDisposition" '
                    'WHERE "CaseMasterID"=%s AND "IsFinal"=TRUE) OR '
                    'EXISTS(SELECT 1 FROM "CourtEvent" '
                    'WHERE "CaseMasterID"=%s AND "EventType"=\'judgment\')',
                    (case_id, case_id),
                )
                pending_is_current = not bool(cur.fetchone()[0])
            if not pending_is_current:
                notice_codes.remove("PENDING_TRIAL")

    cur.execute(
        'SELECT sr."SourceRecordID", sr."ExternalRef", sr."RecordKind", '
        'ss."Code", ss."Name", sr."Payload" '
        'FROM "CaseSource" cs '
        'JOIN "SourceRecord" sr ON sr."SourceRecordID"=cs."SourceRecordID" '
        'LEFT JOIN "SourceSystem" ss ON ss."SourceSystemID"=sr."SourceSystemID" '
        'WHERE cs."CaseMasterID"=%s '
        'ORDER BY sr."SourceRecordID"',
        (case_id,),
    )
    sources = []
    for source_row in cur.fetchall():
        payload = source_row[5] or {}
        if not isinstance(payload, dict):
            payload = {}
        source_url = payload.get("source_url")
        # CaseSource is intentionally limited to presentation-safe records, but
        # fail closed if an excluded/availability-only payload is ever linked.
        if payload.get("record_origin") != "public_source_curated":
            continue
        if payload.get("availability_only") or source_row[2] in {
            "excluded_reference", "nonpublic_availability"
        }:
            continue
        sources.append({
            "source_record_id": int(source_row[0]),
            "external_ref": source_row[1],
            "record_kind": source_row[2],
            "source_system_code": source_row[3],
            "source_system_name": source_row[4],
            "public_source_id": payload.get("id"),
            "title": payload.get("title") or source_row[1],
            "publisher": payload.get("publisher"),
            "published_date": payload.get("date"),
            "source_url": source_url if isinstance(source_url, str) and source_url.startswith("https://") else None,
            "authenticity": payload.get("authenticity"),
            "presentation_use": payload.get("presentation_use"),
            "rights_and_handling": payload.get("rights_and_handling"),
            "last_checked": payload.get("last_checked"),
        })

    notices = [dict(_CASE_NOTICE_CATALOG[code]) for code in notice_codes]
    return {"current_version": current_version, "sources": sources, "notices": notices}
