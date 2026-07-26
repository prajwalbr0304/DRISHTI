"""Phase 10 — governed feature & prediction contract tests.

Exercise the leakage-safe feature builder + the prediction state machine against
the live synthetic schema under ``rw_rollback`` (real SQL, then discarded), via
the internal ``_fn(conn, ...)`` helpers so nothing commits. No secrets printed.

Covers the prompt's checklist: reproducibility from a snapshot, schema-mismatch
rejection, unapproved-schema (unverified source) blocked, stale-after-correction,
leakage check, protected-feature check, idempotent request, and review/audit.
"""
import datetime as dt
import json

import pytest

from app.governance import builder, service
from conftest import requires_db


# ---------------------------------------------------------------------------
# helpers (all operate on the rolled-back connection)
# ---------------------------------------------------------------------------
def _approved_schema(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "FeatureSchemaVersionID","Task" FROM "FeatureSchemaVersion" '
                    "WHERE \"Status\"='approved' ORDER BY \"FeatureSchemaVersionID\" LIMIT 1")
        r = cur.fetchone()
    assert r is not None, "expected a seeded approved FeatureSchemaVersion"
    return int(r[0]), r[1]


def _governed_model(conn, fsv_id):
    with conn.cursor() as cur:
        cur.execute('SELECT "ModelVersionID" FROM "ModelVersion" '
                    "WHERE \"ApprovalStatus\"='approved' AND \"FeatureSchemaVersionID\"=%s LIMIT 1",
                    (fsv_id,))
        r = cur.fetchone()
        if r:
            return int(r[0])
        cur.execute('INSERT INTO "ModelVersion" ("ModelName","ModelType","Version","ApprovalStatus",'
                    '"FeatureSchemaVersionID","Environment") VALUES (%s,%s,%s,%s,%s,%s) '
                    'RETURNING "ModelVersionID"',
                    ("test_area_model", "forecasting", "t1", "approved", fsv_id, "disposable_test"))
        return int(cur.fetchone()[0])


def _a_district(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictID" FROM "District" ORDER BY "DistrictID" LIMIT 1')
        return int(cur.fetchone()[0])


def _draft_schema(conn, task="area_incident_forecast"):
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "FeatureSchemaVersion" ("SchemaName","Version","FeatureDefinitionIDs",'
                    '"Task","Status") VALUES (%s,%s,%s,%s,%s) RETURNING "FeatureSchemaVersionID"',
                    ("test_draft_schema", "1", json.dumps([]), task, "draft"))
        return int(cur.fetchone()[0])


def _protected_schema(conn, task="area_incident_forecast"):
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "FeatureDefinition" ("Name","ValueType","Sensitivity","ApprovalStatus",'
                    '"AllowedTasks") VALUES (%s,%s,%s,%s,%s) RETURNING "FeatureDefinitionID"',
                    ("test_caste_share", "numeric", "protected", "approved", []))
        prot_fd = int(cur.fetchone()[0])
        cur.execute('INSERT INTO "FeatureSchemaVersion" ("SchemaName","Version","FeatureDefinitionIDs",'
                    '"Task","Status") VALUES (%s,%s,%s,%s,%s) RETURNING "FeatureSchemaVersionID"',
                    ("test_protected_schema", "1", json.dumps([prot_fd]), task, "approved"))
        return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# feature builder
# ---------------------------------------------------------------------------
@requires_db
def test_snapshot_reproducible_hash(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    did = _a_district(conn)
    cutoff = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc)
    a = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                               subject_ref_id=str(did), observation_cutoff=cutoff, actor="t")
    b = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                               subject_ref_id=str(did), observation_cutoff=cutoff, actor="t")
    assert a["content_hash"] == b["content_hash"]        # reproducible
    assert a["quality_status"] == "ok"
    assert set(a["values"]) == {"area_incident_count_precutoff", "area_night_share_precutoff",
                                "area_cyber_share_precutoff", "area_prioryear_count"}


@requires_db
def test_builder_is_leakage_safe(rw_rollback):
    """The snapshot's pre-cutoff count equals a direct count of only-pre-cutoff
    canonical cases; a later cutoff never sees fewer cases (post-cutoff rows can
    never leak into an earlier snapshot)."""
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    did = _a_district(conn)
    early = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc)
    late = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    s_early = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                     subject_ref_id=str(did), observation_cutoff=early, actor="t")
    s_late = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                    subject_ref_id=str(did), observation_cutoff=late, actor="t")
    n_early = s_early["source_versions"]["n_pre_cutoff_cases"]
    n_late = s_late["source_versions"]["n_pre_cutoff_cases"]
    assert n_late >= n_early                    # monotonic: no post-cutoff leakage
    # the recorded count matches a direct pre-cutoff-only query
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                    'WHERE u."DistrictID"=%s AND cm."CrimeRegisteredDate" <= %s '
                    'AND EXISTS (SELECT 1 FROM "CaseVersion" cv WHERE cv."CaseMasterID"=cm."CaseMasterID" '
                    'AND cv."IsCurrent")', (did, early))
        direct = int(cur.fetchone()[0])
    assert n_early == direct


@requires_db
def test_unapproved_schema_blocked(rw_rollback):
    conn = rw_rollback
    draft = _draft_schema(conn)
    did = _a_district(conn)
    with pytest.raises(builder.SchemaNotApproved):
        builder.build_snapshot(conn, feature_schema_version_id=draft, subject_kind="area_district",
                               subject_ref_id=str(did), actor="t")


@requires_db
def test_protected_feature_blocked(rw_rollback):
    conn = rw_rollback
    prot = _protected_schema(conn)
    did = _a_district(conn)
    with pytest.raises(builder.ProtectedFeatureError):
        builder.build_snapshot(conn, feature_schema_version_id=prot, subject_kind="area_district",
                               subject_ref_id=str(did), actor="t")


@requires_db
def test_snapshot_is_immutable(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    did = _a_district(conn)
    snap = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                  subject_ref_id=str(did), actor="t")
    with pytest.raises(Exception) as ei:   # trigger raises; txn then needs a rollback
        with conn.cursor() as cur:
            cur.execute('UPDATE "FeatureSnapshot" SET "Values"=%s WHERE "FeatureSnapshotID"=%s',
                        (json.dumps({"tampered": 1}), snap["feature_snapshot_id"]))
    assert "immutable" in str(ei.value).lower()
    conn.rollback()


# ---------------------------------------------------------------------------
# prediction state machine
# ---------------------------------------------------------------------------
@requires_db
def test_prediction_flow_and_idempotent_request(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    mv = _governed_model(conn, fsv)
    did = _a_district(conn)
    snap = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                  subject_ref_id=str(did), actor="t")

    r1 = service._create_request(conn, mv, snap["feature_snapshot_id"], "batch", "t-req", "crime_analyst")
    r2 = service._create_request(conn, mv, snap["feature_snapshot_id"], "batch", "t-req", "crime_analyst")
    assert r1["status"] == "queued"
    assert r1["prediction_request_id"] == r2["prediction_request_id"]   # idempotent
    assert r2["reused"] is True

    run = service._run_request(conn, r1["prediction_request_id"], "crime_analyst")
    assert run["request"]["status"] == "completed"
    assert run["result"]["output"].get("band") in ("low", "medium", "high")
    assert run["result"]["limitations"]                       # decision-support disclaimer present

    # idempotent replay: running again does not recompute.
    again = service._run_request(conn, r1["prediction_request_id"], "crime_analyst")
    assert again["reran"] is False


@requires_db
def test_schema_mismatch_rejected(rw_rollback):
    conn = rw_rollback
    fsv, task = _approved_schema(conn)
    mv = _governed_model(conn, fsv)          # model bound to fsv
    did = _a_district(conn)
    # a snapshot on a DIFFERENT approved schema
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "FeatureSchemaVersion" ("SchemaName","Version","FeatureDefinitionIDs",'
                    '"Task","Status") VALUES (%s,%s,%s,%s,%s) RETURNING "FeatureSchemaVersionID"',
                    ("test_other_schema", "1", json.dumps([]), task, "approved"))
        other_fsv = int(cur.fetchone()[0])
        cur.execute("INSERT INTO \"FeatureSnapshot\" (\"FeatureSchemaVersionID\",\"SubjectKind\","
                    '"SubjectRefID","ObservationCutoff","Values","SourceVersions","QualityStatus",'
                    "\"ContentHash\") VALUES (%s,'area_district',%s,now(),%s,%s,'ok',%s) "
                    'RETURNING "FeatureSnapshotID"',
                    (other_fsv, str(did), json.dumps({}), json.dumps({}), "deadbeef01"))
        other_snap = int(cur.fetchone()[0])
    with pytest.raises(service.SchemaMismatch):
        service._create_request(conn, mv, other_snap, "batch", "t-mismatch", "crime_analyst")


@requires_db
def test_unapproved_model_rejected(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    did = _a_district(conn)
    snap = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                  subject_ref_id=str(did), actor="t")
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "ModelVersion" ("ModelName","ModelType","Version","ApprovalStatus",'
                    '"FeatureSchemaVersionID") VALUES (%s,%s,%s,%s,%s) RETURNING "ModelVersionID"',
                    ("test_draft_model", "forecasting", "d1", "draft", fsv))
        draft_mv = int(cur.fetchone()[0])
    with pytest.raises(service.ModelNotApproved):
        service._create_request(conn, draft_mv, snap["feature_snapshot_id"], "batch", "t-draftmv", "crime_analyst")


@requires_db
def test_stale_after_correction_blocks_run(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    mv = _governed_model(conn, fsv)
    did = _a_district(conn)
    snap = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                  subject_ref_id=str(did), actor="t")
    # an accepted canonical edit invalidates the subject's live snapshots
    inv = service._invalidate_for_subject(conn, "area_district", str(did), "canonical correction", "sup")
    assert inv["snapshots_marked_stale"] >= 1
    r = service._create_request(conn, mv, snap["feature_snapshot_id"], "batch", "t-stale", "crime_analyst")
    with pytest.raises(service.StaleSnapshot):
        service._run_request(conn, r["prediction_request_id"], "crime_analyst")


@requires_db
def test_review_writes_review_and_audit(rw_rollback):
    conn = rw_rollback
    fsv, _ = _approved_schema(conn)
    mv = _governed_model(conn, fsv)
    did = _a_district(conn)
    snap = builder.build_snapshot(conn, feature_schema_version_id=fsv, subject_kind="area_district",
                                  subject_ref_id=str(did), actor="t")
    r = service._create_request(conn, mv, snap["feature_snapshot_id"], "batch", "t-review", "crime_analyst")
    run = service._run_request(conn, r["prediction_request_id"], "crime_analyst")
    result_id = run["result"]["prediction_result_id"]

    rev = service._review_result(conn, result_id, "accept", None, "supervisor_demo")
    assert rev["status"] == "reviewed"
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "PredictionReview" WHERE "PredictionResultID"=%s '
                    "AND \"Decision\"='accept'", (result_id,))
        assert int(cur.fetchone()[0]) == 1
        cur.execute('SELECT "Status" FROM "PredictionRequest" WHERE "PredictionRequestID"=%s',
                    (r["prediction_request_id"],))
        assert cur.fetchone()[0] == "reviewed"
        cur.execute("SELECT count(*) FROM \"audit_logs\" WHERE \"action\"='prediction.review' "
                    'AND "resource_id"=%s', (str(result_id),))
        assert int(cur.fetchone()[0]) == 1

    # override requires a reason
    run2 = service._run_request(conn, r["prediction_request_id"], "crime_analyst")  # idempotent replay
    with pytest.raises(service.InvalidState):
        service._review_result(conn, run2["result"]["prediction_result_id"], "override", "  ", "sup")


# ---------------------------------------------------------------------------
# labels — leakage-safe (public read)
# ---------------------------------------------------------------------------
@requires_db
def test_labels_leakage_safe():
    out = service.list_labels(page_size=10)
    assert out["leakage_safe"] is True          # no LabelWindowStart < ObservationCutoff
    assert out["total"] >= 1
    assert sum(out["splits"].values()) == out["total"]   # splits partition all labels
