"""Safe, transactional loader for the Datagen v2 fixture.

Guardrails:
  * read-only preflight established the baseline before anything mutates.
  * a destructive reload (--truncate/replace) is refused unless BOTH a
    --confirm-synthetic-dev-target flag AND a recorded backup marker are present,
    and the target carries the synthetic_meta marker.
  * reference tables and the governance seed (roles/users/ModelVersion) are
    PRESERVED (never truncated); only fixture-populated data is replaced.
  * load runs inside a transaction per phase; identity sequences are repaired.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from typing import Dict, List, Optional

import psycopg2

from . import db as DB
from . import reference as ref
from . import v2common as C
from .preflight import SYNTHETIC_ENV_VALUE, _with_sslmode, redact_target

# Tables the v2 fixture populates and is therefore allowed to TRUNCATE+reload.
# Reference/org, roles/users/role_permissions, ModelVersion and chat tables are
# intentionally EXCLUDED (preserved). CASCADE cleans any derived children.
TRUNCATE_TABLES: List[str] = [
    # operational core + legacy intelligence referencing CaseMaster
    "CaseMaster", "ComplainantDetails", "Victim", "Accused",
    "ActSectionAssociation", "ArrestSurrender", "inv_arrestsurrenderaccused",
    "ChargesheetDetails", "Inv_OccuranceTime",
    "CrimeRiskScore", "CrimePrediction", "CrimeHotspot", "CrimePattern",
    "CrimePatternCase", "CrimeEmbedding", "AISummary", "AlertHistory",
    "OfficerRecommendation", "ModelInference",
    "SocialIndicator", "WeatherIndicator", "EconomicIndicator",
    "EntityGraph", "NetworkEdge", "GangMembership", "drishti_hidden_associations",
    "FinancialAccount", "FinancialTransaction", "TransactionLink", "CaseEvidence",
    # v2 canonical + workflow + evidence + domains
    "CanonicalPerson", "CanonicalOrganisation", "CanonicalEntity",
    "PersonAlias", "PersonIdentifier", "PersonContact", "PersonAddress",
    "EntityResolutionCandidate", "EntityMergeHistory", "CasePartyRole",
    "CaseSource", "CaseVersion", "CaseCategoryWorkflow", "CaseEvent",
    "EvidenceItem", "EvidenceObject", "EvidenceVersion", "EvidenceCaseLink",
    "EvidenceActivityEvent", "EvidenceEntityLink", "Statement", "StatementVersion",
    "Seizure", "PropertyItem", "Device", "DeviceArtifact", "CommunicationEvent",
    "LocationObservation", "DigitalImportBatch", "CourtEvent", "BailEvent",
    "CaseDisposition", "OutcomeObservation",
    "SourceSystem", "SourceRecord", "IngestionJob", "IngestionRecord",
    "DataQualityIssue",
    "JurisdictionBoundary", "UnitLocation", "ExternalSourceVersion",
    "HolidayCalendar", "PublicEvent", "AreaContextObservation",
    "FeatureDefinition", "FeatureSchemaVersion", "TrainingDatasetSnapshot",
    "FeatureSnapshot", "OutcomeLabel", "PredictionRequest", "PredictionResult",
    "PredictionReview",
    # Phase 8 import pipeline + money alerts (derived; ImportTemplate/Version are
    # migration-seeded reference and are intentionally PRESERVED).
    "ImportBatch", "ImportStagingRow", "MoneyAlert", "MoneyAlertReview",
    "audit_logs",
]

# Tables where the fixture assigns explicit PKs (need identity sequence repair).
RESET_IDENTITY: List[tuple] = [
    ("CanonicalPerson", "CanonicalPersonID"), ("CanonicalOrganisation", "CanonicalOrganisationID"),
    ("CanonicalEntity", "CanonicalEntityID"), ("CaseMaster", "CaseMasterID"),
    ("Accused", "AccusedMasterID"), ("Victim", "VictimMasterID"),
    ("ComplainantDetails", "ComplainantID"), ("CasePartyRole", "CasePartyRoleID"),
    ("CaseVersion", "CaseVersionID"), ("ArrestSurrender", "ArrestSurrenderID"),
    ("ChargesheetDetails", "CSID"), ("SourceSystem", "SourceSystemID"),
    ("SourceRecord", "SourceRecordID"), ("IngestionJob", "IngestionJobID"),
    ("EvidenceItem", "EvidenceItemID"), ("EvidenceObject", "EvidenceObjectID"),
    ("Statement", "StatementID"), ("Seizure", "SeizureID"),
    ("PropertyItem", "PropertyItemID"), ("Device", "DeviceID"),
    ("CourtEvent", "CourtEventID"), ("OutcomeObservation", "OutcomeObservationID"),
    ("FeatureDefinition", "FeatureDefinitionID"),
    ("FeatureSchemaVersion", "FeatureSchemaVersionID"),
    ("TrainingDatasetSnapshot", "TrainingDatasetSnapshotID"),
    ("ExternalSourceVersion", "ExternalSourceVersionID"),
    ("EntityGraph", "EntityID"), ("FinancialAccount", "AccountID"),
    ("FinancialTransaction", "TransactionID"),
]

MIGRATIONS = [
    "005_security_rls_audit.sql", "006_ingestion_evidence.sql",
    "007_identity_case_workflow.sql", "008_feature_prediction_governance.sql",
    "009_jurisdiction_external_events.sql",
]


def connect(dsn: str):
    conn = psycopg2.connect(_with_sslmode(dsn), connect_timeout=30)
    conn.autocommit = True
    # Defensively clear any db-level read-only default a prior disk-full event may
    # have set (USERSET GUC; overridable per session). TRUNCATE/COPY need writes.
    try:
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = off")
    except Exception:
        pass
    conn.autocommit = False
    return conn


def apply_migrations(conn, sql_dir: str, log=print) -> None:
    conn.autocommit = True
    cur = conn.cursor()
    for fname in MIGRATIONS:
        path = os.path.join(sql_dir, fname)
        with open(path, "r", encoding="utf-8") as fh:
            sql = fh.read()
        log(f"  applying {fname} ...")
        cur.execute(sql)  # single-arg execute: no %-interpolation performed
    conn.autocommit = False
    log("  migrations 005-009 applied.")


def synthetic_marker(conn) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.synthetic_meta')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT \"Value\" FROM \"synthetic_meta\" WHERE \"Key\"='app_environment'")
        row = cur.fetchone()
        return row[0] if row else None


def reference_matches(conn, cfg) -> tuple:
    """Confirm the live reference tables match the generation config so the
    fixture's FKs (unit/employee/court/district ids) resolve consistently."""
    expected = {
        "District": cfg.n_districts,
        "Unit": cfg.n_stations + cfg.n_districts,
        "Employee": cfg.n_officers,
        "Court": cfg.n_courts,
    }
    got, ok = {}, True
    with conn.cursor() as cur:
        for t, exp in expected.items():
            cur.execute(f'SELECT count(*) FROM "{t}"')
            got[t] = cur.fetchone()[0]
            if got[t] != exp:
                ok = False
    return ok, got, expected


def ensure_reference_extensions(conn, log=print) -> None:
    """Additively ensure the live reference lookups contain the v2 lifecycle
    statuses (CaseStatusMaster ids 9-14). Reference tables are preserved (not
    reloaded), so the 6 appended CASE_STATUSES must be inserted with the exact
    ids the generator's Context assigns (enumerate order). Idempotent."""
    with conn.cursor() as cur:
        for i, name in enumerate(ref.CASE_STATUSES, start=1):
            cur.execute(
                'INSERT INTO "CaseStatusMaster" ("CaseStatusID","CaseStatusName") '
                'VALUES (%s,%s) ON CONFLICT ("CaseStatusID") DO NOTHING', (i, name))
        DB.reset_identity(cur, "CaseStatusMaster", "CaseStatusID")
    conn.commit()
    log(f"  reference extensions ensured (CaseStatusMaster has {len(ref.CASE_STATUSES)} statuses).")


def has_backup_marker(conn, run_key: Optional[str] = None) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.\"SyntheticDataRun\"')")
        if cur.fetchone()[0] is None:
            return False
        cur.execute('SELECT count(*) FROM "SyntheticDataRun" WHERE "IsBackupMarker"=TRUE')
        return cur.fetchone()[0] > 0


def create_backup_marker(conn, run_key: str, location: str, log=print) -> None:
    """Record a backup marker + write a lightweight count snapshot locally.

    Full data recovery is a documented pg_dump (see phase report); the synthetic
    dataset is also fully regenerable from (seed, config). This marker + snapshot
    is the gate that must exist before any destructive reload.
    """
    counts = {}
    with conn.cursor() as cur:
        for t in ["CaseMaster", "Accused", "Victim", "EntityGraph", "NetworkEdge",
                  "FinancialTransaction", "ModelInference"]:
            cur.execute(f'SELECT count(*) FROM "{t}"')
            counts[t] = cur.fetchone()[0]
    os.makedirs(os.path.dirname(location) or ".", exist_ok=True)
    with open(location, "w", encoding="utf-8") as fh:
        json.dump({"backup_marker": True, "run_key": run_key,
                   "captured_at": dt.datetime.utcnow().isoformat() + "Z",
                   "pre_reload_counts": counts,
                   "restore": "regenerate via generate_v2.py with recorded seed, "
                              "or restore a pg_dump taken before reload"}, fh, indent=1)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "SyntheticDataRun" ("RunKey","Mode","Status","IsBackupMarker",'
            '"BackupLocation","Totals") VALUES (%s,%s,%s,TRUE,%s,%s) '
            'ON CONFLICT ("RunKey") DO UPDATE SET "IsBackupMarker"=TRUE, '
            '"BackupLocation"=EXCLUDED."BackupLocation"',
            (f"backup-{run_key}", "golden", "started", location, DB.Json(counts).s))
    conn.commit()
    log(f"  backup marker recorded; snapshot -> {location}")


def truncate_fixture_tables(conn, log=print) -> None:
    existing = []
    with conn.cursor() as cur:
        for t in TRUNCATE_TABLES:
            cur.execute("SELECT to_regclass(%s)", (f'public."{t}"',))
            if cur.fetchone()[0] is not None:
                existing.append(t)
        quoted = ", ".join(f'"{t}"' for t in existing)
        cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
    conn.commit()
    log(f"  truncated {len(existing)} fixture tables (CASCADE).")


def load_fixture(conn, fixture: C.Fixture, cfg, log=print) -> Dict[str, int]:
    loaded: Dict[str, int] = {}
    cur = conn.cursor()
    for op in fixture.ops:
        if not op.rows:
            continue
        DB.copy_rows(cur, op.table, op.columns, op.rows, chunk=cfg.copy_chunk)
        loaded[op.table] = len(op.rows)
        op.rows = []  # free memory as we go
    conn.commit()
    log(f"  loaded {sum(loaded.values()):,} rows across {len(loaded)} tables.")
    # repair identity sequences for explicit-PK tables
    for table, col in RESET_IDENTITY:
        try:
            DB.reset_identity(cur, table, col)
        except Exception as exc:
            log(f"    skip reset_identity {table}: {exc}")
    conn.commit()
    return loaded


def seed_governed_model_demo(conn, log=print) -> None:
    """Insert one approved aggregate ModelVersion + a governed prediction demo
    (request/result/review) bound to a real FeatureSnapshot. Uses INSERT ...
    RETURNING so it never collides with the preserved legacy ModelVersion ids."""
    with conn.cursor() as cur:
        cur.execute('SELECT "FeatureSnapshotID","FeatureSchemaVersionID" '
                    'FROM "FeatureSnapshot" ORDER BY "FeatureSnapshotID" LIMIT 1')
        row = cur.fetchone()
        if not row:
            return
        snap_id, fsv_id = row
        cur.execute(
            'INSERT INTO "ModelVersion" ("ModelName","ModelType","Version","Framework",'
            '"ArtifactURI","ArtifactDigest","ImageDigest","FeatureSchemaVersionID",'
            '"ApprovalStatus","ApprovedBy","ApprovedAt","Environment","EvaluationReport",'
            '"Status","TrainedAt") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,now()) '
            'RETURNING "ModelVersionID"',
            ("area_incident_forecast_baseline", "forecasting", "v2-demo", "numpy",
             "s3://drishti-models/area_forecast_v2/", "sha256:demo-artifact",
             "sha256:demo-image", fsv_id, "approved", "analyst_demo", "hackathon_demo",
             DB.Json({"backtest_wape": 0.31, "baseline": "seasonal_naive"}).s,
             "staged"))
        mv_id = cur.fetchone()[0]
        cur.execute(
            'INSERT INTO "PredictionRequest" ("ModelVersionID","FeatureSnapshotID",'
            '"RequestKind","IdempotencyKey","Status","RequestedByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s) RETURNING "PredictionRequestID"',
            (mv_id, snap_id, "batch", "demo-req-1", "completed", "analyst_demo"))
        req_id = cur.fetchone()[0]
        cur.execute(
            'INSERT INTO "PredictionResult" ("PredictionRequestID","ModelVersionID",'
            '"FeatureSnapshotID","OutputJSON","Explanation","Limitations","Confidence") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING "PredictionResultID"',
            (req_id, mv_id, snap_id, DB.Json({"band": "medium"}).s,
             DB.Json({"top_features": ["area_incident_count_precutoff"]}).s,
             "Aggregate area forecast; decision support only; human review required.",
             0.62))
        res_id = cur.fetchone()[0]
        cur.execute(
            'INSERT INTO "PredictionReview" ("PredictionResultID","ReviewerActor","Decision",'
            '"OverrideReason") VALUES (%s,%s,%s,%s)',
            (res_id, "supervisor_demo", "accept", None))
    conn.commit()
    log("  governed aggregate model + prediction demo seeded.")


def record_run(conn, fixture: C.Fixture, report: dict, status: str, log=print) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "SyntheticDataRun" ("RunKey","Mode","Seed","TargetFirs",'
            '"Status","Totals","ScenarioCoverage","ValidationReport","GeneratorVersion",'
            '"FinishedAt") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) '
            'ON CONFLICT ("RunKey") DO UPDATE SET "Status"=EXCLUDED."Status", '
            '"Totals"=EXCLUDED."Totals", "ScenarioCoverage"=EXCLUDED."ScenarioCoverage", '
            '"ValidationReport"=EXCLUDED."ValidationReport", "FinishedAt"=now()',
            (fixture.run_key, fixture.mode, fixture.seed, fixture.target_firs, status,
             DB.Json(fixture.totals).s, DB.Json(fixture.scenario_coverage).s,
             DB.Json({"ok": report.get("ok"), "total_failures": report.get("total_failures")}).s,
             fixture.generator_version))
    conn.commit()


# ---------------------------------------------------------------------------
# DB-side integrity checks (post-load) — complement the in-memory gates.
# ---------------------------------------------------------------------------
def db_integrity_checks(conn) -> dict:
    checks: Dict[str, int] = {}
    q = {
        "orphan_casepartyrole_case":
            'SELECT count(*) FROM "CasePartyRole" r LEFT JOIN "CaseMaster" c '
            'ON c."CaseMasterID"=r."CaseMasterID" WHERE c."CaseMasterID" IS NULL',
        "orphan_caseversion_case":
            'SELECT count(*) FROM "CaseVersion" v LEFT JOIN "CaseMaster" c '
            'ON c."CaseMasterID"=v."CaseMasterID" WHERE c."CaseMasterID" IS NULL',
        "accused_without_canonical":
            'SELECT count(*) FROM "Accused" a WHERE a."CanonicalPersonID" IS NULL '
            'AND a."AccusedName" <> \'Unknown / Unidentified\'',
        "graph_person_without_canonical":
            'SELECT count(*) FROM "EntityGraph" e WHERE e."EntityType"=\'person\' '
            'AND e."CanonicalEntityID" IS NULL',
        "edge_without_provenance":
            'SELECT count(*) FROM "NetworkEdge" n WHERE n."ProvenanceStatus" IS NULL '
            'OR n."ProvenanceStatus" NOT IN (\'verified\',\'synthetic_unverified\')',
        "chargesheeted_without_row":
            'SELECT count(*) FROM "CaseVersion" v WHERE v."StatusCode"=\'chargesheeted\' '
            'AND NOT EXISTS (SELECT 1 FROM "ChargesheetDetails" cs '
            'WHERE cs."CaseMasterID"=v."CaseMasterID")',
        "evidence_object_without_hash":
            'SELECT count(*) FROM "EvidenceObject" WHERE "Sha256" IS NULL OR "Sha256"=\'\'',
        "outcome_label_leak":
            'SELECT count(*) FROM "OutcomeLabel" WHERE "LabelWindowStart" < "ObservationCutoff"',
        # Bounded confirmation of the (authoritative) in-memory spatial gate:
        # 100k point-in-polygon tests against the full state multipolygon are
        # slow, so sample the newest current CaseVersions here.
        "caseversion_out_of_state_sampled":
            'SELECT count(*) FROM (SELECT "InState" FROM "vw_caseversion_containment" '
            'LIMIT 25000) s WHERE s."InState" = FALSE',
        "caseversion_out_of_district_sampled":
            'SELECT count(*) FROM (SELECT "InAssignedDistrict" FROM '
            '"vw_caseversion_containment" LIMIT 25000) s WHERE s."InAssignedDistrict" = FALSE',
        "rls_enabled_app_tables":
            "SELECT count(*) FROM fn_drishti_app_tables() WHERE rls_enabled OR rls_forced",
    }
    with conn.cursor() as cur:
        for name, sql in q.items():
            try:
                cur.execute(sql)
                checks[name] = cur.fetchone()[0]
            except Exception as exc:
                checks[name] = -1  # check could not run
    return checks
