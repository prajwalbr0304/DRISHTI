"""Phase 9 — jurisdiction geography tests.

Covers the DB containment functions, persisted/versioned boundary readback,
freshness, and the containment-scan -> reviewed-reassignment repair path. All
mutating tests run under ``rw_rollback`` (real SQL against the live synthetic
schema, then discarded) and call the internal ``_fn(conn, ...)`` helpers so
nothing is ever committed. No secrets are printed.
"""
import pytest

from app.geo import jurisdiction as J
from app.geo import persist
from conftest import requires_db


# Unambiguous reference points (lon, lat).
BENGALURU = (77.5946, 12.9716)      # inside Karnataka
ODISHA = (85.0, 20.0)              # far outside Karnataka


def _first_geo_caseversion(conn):
    """A current CaseVersion with coordinates + an assigned district."""
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID","AssignedDistrictID","IncidentLongitude","IncidentLatitude" '
                    'FROM "CaseVersion" WHERE "IsCurrent" AND "IncidentLatitude" IS NOT NULL '
                    'AND "AssignedDistrictID" IS NOT NULL LIMIT 1')
        r = cur.fetchone()
    assert r is not None, "expected at least one geo-located current CaseVersion"
    return int(r[0]), int(r[1]), float(r[2]), float(r[3])


def _wrong_district(conn, good_did, lon, lat) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictID" FROM "District" WHERE "DistrictID"<>%s '
                    'AND NOT fn_point_in_district("DistrictID",%s::double precision,%s::double precision) '
                    'ORDER BY "DistrictID" LIMIT 1', (good_did, lon, lat))
        r = cur.fetchone()
    assert r is not None, "expected a district that does not contain the point"
    return int(r[0])


# ---------------------------------------------------------------------------
# DB containment functions
# ---------------------------------------------------------------------------
@requires_db
def test_point_in_state_land_vs_outside(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute("SELECT fn_point_in_state(%s::double precision,%s::double precision)", BENGALURU)
        assert cur.fetchone()[0] is True
        cur.execute("SELECT fn_point_in_state(%s::double precision,%s::double precision)", ODISHA)
        assert cur.fetchone()[0] is False


@requires_db
def test_point_in_district_true_and_false(rw_rollback):
    case_id, good_did, lon, lat = _first_geo_caseversion(rw_rollback)
    # the assigned district contains its own incident point ...
    assert J._point_in_district(rw_rollback, good_did, lon, lat) is True
    # ... and a neighbouring district does not.
    wrong = _wrong_district(rw_rollback, good_did, lon, lat)
    assert J._point_in_district(rw_rollback, wrong, lon, lat) is False


# ---------------------------------------------------------------------------
# Persisted / versioned boundaries + freshness (UI + DB share one source)
# ---------------------------------------------------------------------------
@requires_db
def test_db_boundaries_persisted_geojson():
    for level in ("state", "district", "taluk"):
        fc = J.db_boundaries(level)
        assert fc["type"] == "FeatureCollection"
        assert fc["count"] >= 1
        # every feature carries real geometry + a version (versioned source of truth)
        f0 = fc["features"][0]
        assert f0["geometry"] and f0["geometry"].get("type")
        assert f0["properties"]["version"] is not None


@requires_db
def test_boundary_loader_idempotent(rw_rollback):
    # boundaries are already persisted (committed by the load-boundaries batch),
    # so ensuring them again inserts nothing.
    inserted = persist.ensure_boundaries(rw_rollback, log=lambda *_: None)
    assert inserted == {"state": 0, "district": 0, "taluk": 0}
    summ = persist.summary(rw_rollback)
    assert summ["boundaries"].get("state", 0) >= 1
    assert summ["boundaries"].get("district", 0) >= 1
    assert summ["unit_locations"] > 0


@requires_db
def test_freshness_reports_levels_and_env():
    fr = J.freshness()
    assert "state" in fr["boundaries"] and "district" in fr["boundaries"]
    assert fr["unit_locations"] > 0
    assert fr["environment_label"]


# ---------------------------------------------------------------------------
# Containment scan -> DataQualityIssue -> reviewed reassignment (no silent move)
# ---------------------------------------------------------------------------
@requires_db
def test_scan_flags_wrong_district_then_reassign_supersedes(rw_rollback):
    conn = rw_rollback
    case_id, good_did, lon, lat = _first_geo_caseversion(conn)
    wrong = _wrong_district(conn, good_did, lon, lat)

    # simulate a mis-assigned canonical row (in-place; rolled back)
    with conn.cursor() as cur:
        cur.execute('UPDATE "CaseVersion" SET "AssignedDistrictID"=%s '
                    'WHERE "CaseMasterID"=%s AND "IsCurrent"', (wrong, case_id))
        cur.execute('SELECT "VersionNo" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        base_version = int(cur.fetchone()[0])

    # scan (scoped to this case -> fast) stages a DataQualityIssue, no move
    scan = J.scan_containment(conn, scope="caseversion", actor="test", case_master_id=case_id)
    assert scan["out_of_district"] == 1
    assert scan["issues_raised"] == 1
    assert scan["run_id"] > 0  # SpatialRepairRun recorded

    with conn.cursor() as cur:
        cur.execute("SELECT \"DataQualityIssueID\",\"Detail\" FROM \"DataQualityIssue\" "
                    "WHERE \"CaseMasterID\"=%s AND \"Status\"='open' "
                    "AND \"IssueType\"='invalid_jurisdiction_district'", (case_id,))
        dq_id, detail = cur.fetchone()
        dq_id = int(dq_id)
        # the scan recorded the DETECTED district so the reviewer can reassign
        assert detail.get("resolved_district_id") == good_did

    # the case was NOT moved by the scan (still mis-assigned until reviewed)
    with conn.cursor() as cur:
        cur.execute('SELECT "AssignedDistrictID" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        assert int(cur.fetchone()[0]) == wrong

    # reviewed reassignment to the detected district supersedes the version
    res = J._reassign(conn, case_id, to_district_id=good_did, actor="sup.test",
                      reason="incident falls inside the detected district", action="reassign",
                      data_quality_issue_id=dq_id)
    assert res["action"] == "reassign"
    assert res["to_district_id"] == good_did
    assert res["issues_resolved"] == 1

    with conn.cursor() as cur:
        cur.execute('SELECT "AssignedDistrictID","VersionNo" FROM "CaseVersion" '
                    'WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        new_did, new_ver = cur.fetchone()
        assert int(new_did) == good_did          # corrected
        assert int(new_ver) == base_version + 1  # superseded (new version, not in-place)
        cur.execute("SELECT \"Status\" FROM \"DataQualityIssue\" WHERE \"DataQualityIssueID\"=%s", (dq_id,))
        assert cur.fetchone()[0] == "resolved"
        cur.execute('SELECT count(*) FROM "JurisdictionReassignment" WHERE "CaseMasterID"=%s '
                    "AND \"Action\"='reassign'", (case_id,))
        assert int(cur.fetchone()[0]) == 1


@requires_db
def test_scan_is_idempotent_for_open_issue(rw_rollback):
    conn = rw_rollback
    case_id, good_did, lon, lat = _first_geo_caseversion(conn)
    wrong = _wrong_district(conn, good_did, lon, lat)
    with conn.cursor() as cur:
        cur.execute('UPDATE "CaseVersion" SET "AssignedDistrictID"=%s '
                    'WHERE "CaseMasterID"=%s AND "IsCurrent"', (wrong, case_id))
    first = J.scan_containment(conn, scope="caseversion", actor="test", case_master_id=case_id)
    second = J.scan_containment(conn, scope="caseversion", actor="test", case_master_id=case_id)
    assert first["issues_raised"] == 1
    assert second["out_of_district"] == 1      # still detected ...
    assert second["issues_raised"] == 0        # ... but not double-raised


@requires_db
def test_reassign_to_wrong_district_is_refused(rw_rollback):
    conn = rw_rollback
    case_id, good_did, lon, lat = _first_geo_caseversion(conn)
    wrong = _wrong_district(conn, good_did, lon, lat)
    with pytest.raises(J.JurisdictionConflict):
        J._reassign(conn, case_id, to_district_id=wrong, actor="sup.test",
                    reason="should fail — point not inside target", action="reassign")


@requires_db
def test_override_keeps_assigned_district_without_new_version(rw_rollback):
    conn = rw_rollback
    case_id, good_did, lon, lat = _first_geo_caseversion(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT "VersionNo" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        base_version = int(cur.fetchone()[0])

    res = J._reassign(conn, case_id, to_district_id=None, actor="sup.test",
                      reason="cross-border case retained here by order", action="override")
    assert res["action"] == "override"
    assert res["to_district_id"] == good_did       # assigned district kept
    with conn.cursor() as cur:
        cur.execute('SELECT "VersionNo" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        assert int(cur.fetchone()[0]) == base_version   # override does NOT supersede the version
        cur.execute('SELECT count(*) FROM "JurisdictionReassignment" WHERE "CaseMasterID"=%s '
                    "AND \"Action\"='override'", (case_id,))
        assert int(cur.fetchone()[0]) == 1


@requires_db
def test_quarantine_supersedes_version(rw_rollback):
    conn = rw_rollback
    case_id, good_did, lon, lat = _first_geo_caseversion(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT "VersionNo" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        base_version = int(cur.fetchone()[0])
    res = J._reassign(conn, case_id, to_district_id=None, actor="sup.test",
                      reason="coordinates are wrong; hold out of canonical analytics",
                      action="quarantine")
    assert res["action"] == "quarantine"
    with conn.cursor() as cur:
        cur.execute('SELECT "VersionNo" FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent"', (case_id,))
        assert int(cur.fetchone()[0]) == base_version + 1  # quarantine supersedes
