"""Phase 9 — jurisdiction containment scan, reviewed reassignment, DB-backed
boundary GeoJSON and freshness.

The DATABASE is the source of truth: boundaries live in ``JurisdictionBoundary``
(versioned) and containment is enforced by ``fn_point_in_state`` /
``fn_point_in_district`` / ``fn_point_in_unit``. A canonical row that fails
containment is NEVER silently moved — it is flagged as a ``DataQualityIssue`` and
only a REVIEWED reassignment/override (audited in ``JurisdictionReassignment``,
recorded as a new versioned ``CaseVersion``) changes its assigned jurisdiction.

Design mirrors the intake/casework modules: internal ``_fn(conn, ...)`` helpers
never commit (tests drive them under rw_rollback); public wrappers open
db.rw_conn()/ro_conn().
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from psycopg2.extras import Json

from .. import audit, db


class JurisdictionError(Exception):
    pass


class JurisdictionNotFound(JurisdictionError):
    pass


class JurisdictionConflict(JurisdictionError):
    pass


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


_ISSUE_STATE = "invalid_jurisdiction_state"
_ISSUE_DISTRICT = "invalid_jurisdiction_district"


# ---------------------------------------------------------------------------
# DB-backed boundary GeoJSON (UI + DB share the SAME persisted geometry)
# ---------------------------------------------------------------------------
_LEVEL_SQL = {
    "state": ("state",),
    "district": ("district",),
    "taluk": ("taluk",),
    "unit": ("unit", "sho"),
    "sho": ("unit", "sho"),
}


def db_boundaries(level: str) -> dict:
    levels = _LEVEL_SQL.get(level)
    if levels is None:
        raise JurisdictionNotFound(f"unknown boundary level {level!r}")
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "JurisdictionBoundaryID","Name","DistrictID","UnitID","Version",'
                '"ValidFrom","Source", ST_AsGeoJSON("geom")::json '
                'FROM "JurisdictionBoundary" WHERE "Level" = ANY(%s) AND "IsCurrent" '
                'ORDER BY "Name"', (list(levels),))
            rows = cur.fetchall()
    features = [{
        "type": "Feature",
        "geometry": r[7],
        "properties": {
            "boundary_id": int(r[0]), "name": r[1], "district_id": r[2], "unit_id": r[3],
            "version": r[4], "valid_from": _s(r[5]), "source": r[6], "level": level,
        },
    } for r in rows]
    return {"type": "FeatureCollection", "level": level, "count": len(features),
            "features": features}


# ---------------------------------------------------------------------------
# Freshness (boundary versions + last scan + canonical containment)
# ---------------------------------------------------------------------------
def freshness() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "Level", count(*) FILTER (WHERE "IsCurrent"), max("Version"), '
                'min("ValidFrom"), max("Source") FROM "JurisdictionBoundary" GROUP BY "Level" '
                'ORDER BY "Level"')
            boundaries = {r[0]: {"count": int(r[1]), "version": r[2],
                                 "as_of": _s(r[3]), "source": r[4]} for r in cur.fetchall()}
            cur.execute('SELECT count(*) FILTER (WHERE "IsCurrent") FROM "UnitLocation"')
            unit_locations = int(cur.fetchone()[0])
            cur.execute(
                'SELECT "SpatialRepairRunID","Scope","CheckedCount","OutOfStateCount",'
                '"OutOfDistrictCount","IssuesRaised","Actor","CreatedAt" '
                'FROM "SpatialRepairRun" ORDER BY "SpatialRepairRunID" DESC LIMIT 1')
            r = cur.fetchone()
            last_scan = None if r is None else {
                "run_id": int(r[0]), "scope": r[1], "checked": r[2], "out_of_state": r[3],
                "out_of_district": r[4], "issues_raised": r[5], "actor": r[6], "at": _s(r[7])}
            # open jurisdiction data-quality issues (fast)
            cur.execute("SELECT count(*) FROM \"DataQualityIssue\" WHERE \"Status\"='open' "
                        'AND "IssueType" IN (%s,%s)', (_ISSUE_STATE, _ISSUE_DISTRICT))
            open_issues = int(cur.fetchone()[0])
    return {"boundaries": boundaries, "unit_locations": unit_locations,
            "last_scan": last_scan, "open_jurisdiction_issues": open_issues,
            "environment_label": "Synthetic Hackathon Demo"}


# ---------------------------------------------------------------------------
# Containment scan -> DataQualityIssue (no silent move)
# ---------------------------------------------------------------------------
def _has_open_issue(conn, case_id: int, issue_type: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM \"DataQualityIssue\" WHERE \"CaseMasterID\"=%s "
                    "AND \"IssueType\"=%s AND \"Status\"='open' LIMIT 1", (case_id, issue_type))
        return cur.fetchone() is not None


def _raise_issue(conn, case_id: Optional[int], issue_type: str, severity: str, detail: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "DataQualityIssue" ("IssueType","Severity","CaseMasterID","Detail","Status") '
            "VALUES (%s,%s,%s,%s,'open') RETURNING \"DataQualityIssueID\"",
            (issue_type, severity, case_id, Json(detail)))
        return int(cur.fetchone()[0])


def _district_containing(conn, lon: float, lat: float) -> tuple[Optional[int], Optional[str]]:
    """The district whose PERSISTED boundary contains the point (GiST, one query),
    so a scan can suggest the detected district for a reviewed reassignment."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT jb."DistrictID", d."DistrictName" FROM "JurisdictionBoundary" jb '
            'JOIN "District" d ON d."DistrictID" = jb."DistrictID" '
            'WHERE jb."Level"=\'district\' AND jb."IsCurrent" '
            'AND ST_Contains(jb."geom", ST_SetSRID(ST_MakePoint(%s,%s),4326)) LIMIT 1',
            (lon, lat))
        r = cur.fetchone()
        return (int(r[0]), r[1]) if r else (None, None)


def _scan_caseversions(conn, limit: int, case_master_id: Optional[int] = None) -> dict:
    """Scan current CaseVersions for containment failures, raise DataQualityIssues."""
    with conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='120000'")
        sql = ('SELECT "CaseMasterID","AssignedDistrictID","IncidentLongitude","IncidentLatitude",'
               '"InState","InAssignedDistrict" FROM "vw_caseversion_containment" '
               'WHERE ("InState" = FALSE OR "InAssignedDistrict" = FALSE)')
        params: list = []
        if case_master_id is not None:
            sql += ' AND "CaseMasterID" = %s'
            params.append(case_master_id)
        sql += ' LIMIT %s'
        params.append(limit)
        cur.execute(sql, params)
        bad = cur.fetchall()
    out_of_state = out_of_district = issues = 0
    for case_id, dist_id, lon, lat, in_state, in_district in bad:
        case_id = int(case_id)
        if in_state is False:
            out_of_state += 1
            if not _has_open_issue(conn, case_id, _ISSUE_STATE):
                _raise_issue(conn, case_id, _ISSUE_STATE, "blocker",
                             {"assigned_district_id": dist_id, "lon": float(lon), "lat": float(lat),
                              "check": "outside Karnataka state boundary"})
                issues += 1
        elif in_district is False:
            out_of_district += 1
            if not _has_open_issue(conn, case_id, _ISSUE_DISTRICT):
                det_id, det_name = _district_containing(conn, float(lon), float(lat))
                _raise_issue(conn, case_id, _ISSUE_DISTRICT, "error",
                             {"assigned_district_id": dist_id, "lon": float(lon), "lat": float(lat),
                              "check": "outside assigned district boundary",
                              "resolved_district_id": det_id, "resolved_district_name": det_name})
                issues += 1
    return {"out_of_state": out_of_state, "out_of_district": out_of_district,
            "issues_raised": issues, "checked": None}


def _count_checked_caseversions(conn, limit: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='120000'")
        cur.execute('SELECT count(*) FROM (SELECT 1 FROM "vw_caseversion_containment" '
                    'LIMIT %s) s', (limit,))
        return int(cur.fetchone()[0])


def scan_containment(conn, scope: str = "all", actor: Optional[str] = None,
                     limit: int = 100000, case_master_id: Optional[int] = None) -> dict:
    """Identify canonical containment failures and stage them as DataQualityIssues.
    Records a SpatialRepairRun. Idempotent (skips cases that already have an open
    issue of the same type). NEVER moves a row — repair is a reviewed action.
    ``case_master_id`` scopes the scan to one case (fast targeted re-check)."""
    cv = _scan_caseversions(conn, limit, case_master_id) if scope in ("caseversion", "all") else \
        {"out_of_state": 0, "out_of_district": 0, "issues_raised": 0}
    checked = (1 if case_master_id is not None else _count_checked_caseversions(conn, limit)) \
        if scope in ("caseversion", "all") else 0
    run_key = "geoscan-" + uuid.uuid4().hex[:10]
    totals = {"caseversion": cv}
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "SpatialRepairRun" ("RunKey","Scope","CheckedCount","OutOfStateCount",'
            '"OutOfDistrictCount","IssuesRaised","Totals","Actor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "SpatialRepairRunID"',
            (run_key, scope, checked, cv["out_of_state"], cv["out_of_district"],
             cv["issues_raised"], Json(totals), actor))
        run_id = int(cur.fetchone()[0])
    audit.record(audit.Action.MODEL_RUN, "spatial_repair_run", run_id, actor=actor, conn=conn,
                 detail={"scope": scope, "out_of_state": cv["out_of_state"],
                         "out_of_district": cv["out_of_district"], "issues": cv["issues_raised"]})
    return {"run_id": run_id, "run_key": run_key, "scope": scope, "checked": checked,
            "out_of_state": cv["out_of_state"], "out_of_district": cv["out_of_district"],
            "issues_raised": cv["issues_raised"]}


# ---------------------------------------------------------------------------
# Reviewed reassignment (versioned; audited; resolves the issue)
# ---------------------------------------------------------------------------
def _current_caseversion(conn, case_id: int):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CaseVersionID","VersionNo","CaseCategoryCode","StatusCode","AssignedDistrictID",'
            '"AssignedUnitID","IncidentLatitude","IncidentLongitude","SnapshotAttributes" '
            'FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent" LIMIT 1', (case_id,))
        return cur.fetchone()


def _point_in_district(conn, district_id: int, lon: float, lat: float) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT fn_point_in_district(%s,%s::double precision,%s::double precision)",
                    (district_id, lon, lat))
        return bool(cur.fetchone()[0])


def _reassign(conn, case_id: int, to_district_id: Optional[int], actor: Optional[str],
              reason: str, action: str = "reassign",
              data_quality_issue_id: Optional[int] = None) -> dict:
    cv = _current_caseversion(conn, case_id)
    if cv is None:
        raise JurisdictionNotFound(f"No current CaseVersion for case {case_id}.")
    (cv_id, version_no, category, status, from_district, from_unit,
     lat, lon, snapshot) = cv
    snapshot = snapshot or {}

    if action == "reassign":
        if to_district_id is None:
            raise JurisdictionConflict("reassign requires a target district.")
        if lat is None or lon is None:
            raise JurisdictionConflict("case has no incident coordinates to validate against.")
        if not _point_in_district(conn, to_district_id, float(lon), float(lat)):
            raise JurisdictionConflict(
                f"Incident point is not inside district {to_district_id}; use 'override' or "
                "'quarantine' if the coordinates are wrong.")
    elif action in ("override", "quarantine"):
        # override keeps the assigned district but records a reviewed acceptance;
        # quarantine flags the case out of the canonical analytics set.
        to_district_id = to_district_id if to_district_id is not None else from_district
    else:
        raise JurisdictionConflict(f"unknown reassignment action '{action}'.")

    # provenance for the reviewed change
    with conn.cursor() as cur:
        cur.execute("SELECT \"SourceSystemID\" FROM \"SourceSystem\" WHERE \"Code\"='FIR_FORM' LIMIT 1")
        r = cur.fetchone()
        ssid = int(r[0]) if r else None
        cur.execute(
            'INSERT INTO "SourceRecord" ("SourceSystemID","RecordKind","Payload","Status") '
            "VALUES (%s,'jurisdiction_reassignment',%s,'committed') RETURNING \"SourceRecordID\"",
            (ssid, Json({"case_id": case_id, "action": action, "reason": reason,
                         "from_district": from_district, "to_district": to_district_id})))
        source_record_id = int(cur.fetchone()[0])

    new_cv_id = cv_id
    if action in ("reassign", "quarantine"):
        # supersede the current version with a corrected one (no silent in-place move)
        new_snapshot = dict(snapshot)
        new_snapshot["jurisdiction_reassignment"] = {
            "from_district": from_district, "to_district": to_district_id,
            "action": action, "reason": reason, "actor": actor}
        with conn.cursor() as cur:
            # flip the current version off first (partial unique index allows one current)
            cur.execute('UPDATE "CaseVersion" SET "IsCurrent"=FALSE WHERE "CaseVersionID"=%s', (cv_id,))
            cur.execute(
                'INSERT INTO "CaseVersion" ("CaseMasterID","VersionNo","CaseCategoryCode","StatusCode",'
                '"IsCurrent","IncidentLatitude","IncidentLongitude","AssignedDistrictID","AssignedUnitID",'
                '"SnapshotAttributes","ChangeReason","Actor") '
                'VALUES (%s,%s,%s,%s,TRUE,%s,%s,%s,%s,%s,%s,%s) RETURNING "CaseVersionID"',
                (case_id, int(version_no) + 1, category, status, lat, lon,
                 to_district_id, from_unit, Json(new_snapshot),
                 f"jurisdiction_{action}: {reason}", actor))
            new_cv_id = int(cur.fetchone()[0])
            cur.execute(
                'INSERT INTO "CaseEvent" ("CaseMasterID","EventType","EventCategory","SequenceNo",'
                '"OccurredAt","FromStatus","ToStatus","Payload","ActorRole") '
                'SELECT %s, %s, \'admin\', COALESCE(MAX("SequenceNo"),0)+1, now(), %s, %s, %s, %s '
                'FROM "CaseEvent" WHERE "CaseMasterID"=%s',
                (case_id, f"jurisdiction_{action}", status, status,
                 Json({"from_district": from_district, "to_district": to_district_id,
                       "reason": reason}), actor, case_id))

    # audit row in JurisdictionReassignment
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "JurisdictionReassignment" ("CaseMasterID","FromCaseVersionID","ToCaseVersionID",'
            '"Action","FromDistrictID","ToDistrictID","FromUnitID","ToUnitID","Reason","ReviewerActor",'
            '"SourceRecordID","DataQualityIssueID","BeforeState","AfterState") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "JurisdictionReassignmentID"',
            (case_id, cv_id, new_cv_id, action, from_district, to_district_id, from_unit, from_unit,
             reason, actor, source_record_id, data_quality_issue_id,
             Json({"district_id": from_district, "case_version_id": cv_id}),
             Json({"district_id": to_district_id, "case_version_id": new_cv_id, "action": action})))
        reassignment_id = int(cur.fetchone()[0])
        # resolve any open jurisdiction issue for this case
        cur.execute(
            "UPDATE \"DataQualityIssue\" SET \"Status\"='resolved', \"ResolvedByActor\"=%s, "
            '"ResolvedAt"=now() WHERE "CaseMasterID"=%s AND "Status"=\'open\' '
            'AND "IssueType" IN (%s,%s)', (actor, case_id, _ISSUE_STATE, _ISSUE_DISTRICT))
        resolved = cur.rowcount

    audit.record(audit.Action.ENTITY_CHANGE, "jurisdiction_reassignment", reassignment_id,
                 actor=actor, conn=conn,
                 detail={"case_id": case_id, "action": action, "to_district": to_district_id,
                         "issues_resolved": resolved})
    return {"jurisdiction_reassignment_id": reassignment_id, "case_master_id": case_id,
            "action": action, "from_district_id": from_district, "to_district_id": to_district_id,
            "new_case_version_id": new_cv_id, "issues_resolved": resolved,
            "source_record_id": source_record_id}


def containment_issues(status: str = "open", page: int = 1, page_size: int = 50) -> dict:
    offset = (max(1, page) - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT count(*) FROM "DataQualityIssue" WHERE "Status"=%s '
                'AND "IssueType" IN (%s,%s)', (status, _ISSUE_STATE, _ISSUE_DISTRICT))
            total = int(cur.fetchone()[0])
            cur.execute(
                'SELECT dq."DataQualityIssueID", dq."IssueType", dq."Severity", dq."Status", '
                'dq."CaseMasterID", cm."CrimeNo", dq."Detail", dq."CreatedAt", '
                'cv."AssignedDistrictID", d."DistrictName" '
                'FROM "DataQualityIssue" dq '
                'LEFT JOIN "CaseMaster" cm ON cm."CaseMasterID" = dq."CaseMasterID" '
                'LEFT JOIN "CaseVersion" cv ON cv."CaseMasterID" = dq."CaseMasterID" AND cv."IsCurrent" '
                'LEFT JOIN "District" d ON d."DistrictID" = cv."AssignedDistrictID" '
                'WHERE dq."Status"=%s AND dq."IssueType" IN (%s,%s) '
                'ORDER BY dq."DataQualityIssueID" DESC LIMIT %s OFFSET %s',
                (status, _ISSUE_STATE, _ISSUE_DISTRICT, page_size, offset))
            items = [{
                "data_quality_issue_id": int(r[0]), "issue_type": r[1], "severity": r[2],
                "status": r[3], "case_master_id": r[4], "crime_no": r[5], "detail": r[6] or {},
                "created_at": _s(r[7]), "assigned_district_id": r[8], "assigned_district_name": r[9],
                "resolved_district_id": (r[6] or {}).get("resolved_district_id"),
                "resolved_district_name": (r[6] or {}).get("resolved_district_name")}
                for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "status": status, "items": items}


# ===========================================================================
# Public wrappers
# ===========================================================================
def reassign(case_id: int, to_district_id: Optional[int], actor: Optional[str],
             reason: str, action: str = "reassign",
             data_quality_issue_id: Optional[int] = None) -> dict:
    with db.rw_conn() as conn:
        return _reassign(conn, case_id, to_district_id, actor, reason, action, data_quality_issue_id)


def scan(scope: str = "all", actor: Optional[str] = None) -> dict:
    with db.rw_conn() as conn:
        return scan_containment(conn, scope=scope, actor=actor)
