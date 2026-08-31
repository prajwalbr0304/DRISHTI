"""Admin/governance console service (Phase 15).

Read models + non-destructive configuration writes over the Phase-15 admin
schema (migration 022) plus the existing source/ingestion/evidence/model tables.
Reads use db.ro_conn(); writes use db.rw_conn() and always append an audit event.

Safety invariants enforced here (in addition to the DB CHECK constraints):
  * retention/legal-hold are NON-DESTRUCTIVE — nothing deletes rows;
  * an active LegalHold suppresses any evidence expiry flag;
  * source-reconciliation "repair" only re-stages/requeues synthetic records for
    review — it never fabricates canonical data.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..cache import get_cache, SEG_LOOKUP
from ..config import get_settings
from ..roles import ALL_ROLES
from . import permissions
from ..quickml import rag_enabled
from ..signals import signals_enabled
from ..notify_channels import notify_enabled


def _s(v) -> Optional[str]:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v) if v is not None else None


# ===========================================================================
# Status + RLS + identity/authorization
# ===========================================================================
def rls_status() -> dict:
    """RLS-disabled verification read model over fn_drishti_app_tables().

    Uses the OWNER connection (rw_conn) because fn_drishti_app_tables() filters on
    ``current_user`` = table owner; the read-only role owns no tables and would
    see an empty set. The query is a pure SELECT — the transaction commits nothing.
    """
    tables: list[dict] = []
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "schemaname","tablename","rls_enabled","rls_forced" '
                        'FROM fn_drishti_app_tables()')
            for r in cur.fetchall():
                tables.append({"schema_name": r[0], "table_name": r[1],
                               "rls_enabled": bool(r[2]), "rls_forced": bool(r[3])})
    offenders = [t["table_name"] for t in tables if t["rls_enabled"] or t["rls_forced"]]
    return {"rls_disabled": len(offenders) == 0, "tables_checked": len(tables),
            "tables_enabled": len(offenders), "offenders": offenders, "tables": tables}


def _component_flags() -> dict:
    return {
        "signals_enabled": signals_enabled(),
        "notify_enabled": notify_enabled(),
        "rag_enabled": rag_enabled(),
        "use_catalyst_datastore": os.getenv("DRISHTI_USE_CATALYST_DATASTORE", "").lower() == "true",
        "use_catalyst_stratus": os.getenv("DRISHTI_USE_CATALYST_STRATUS", "").lower() == "true",
        "use_catalyst_smartbrowz": os.getenv("DRISHTI_USE_CATALYST_SMARTBROWZ", "").lower() == "true",
    }


def _counts(conn) -> dict:
    out: dict[str, int] = {}
    pairs = {
        "cases": '"CaseMaster"', "evidence": '"EvidenceItem"', "source_systems": '"SourceSystem"',
        "audit_events": '"audit_logs"', "work_tasks": '"WorkTask"', "reports": '"ReportSnapshot"',
        "notifications": '"NotificationMessage"', "retention_policies": '"RetentionPolicy"',
        "legal_holds_active": '"LegalHold" WHERE "Status"=\'active\'',
    }
    with conn.cursor() as cur:
        for key, frm in pairs.items():
            try:
                cur.execute(f'SELECT count(*) FROM {frm}')
                out[key] = int(cur.fetchone()[0])
            except Exception:  # noqa: BLE001 — a missing optional table must not break status
                out[key] = 0
    return out


def admin_status() -> dict:
    from ..intake.guards import hackathon_status
    hs = hackathon_status()
    rls = rls_status()
    db_ok = True
    try:
        db_ok = db.ping()
    except Exception:  # noqa: BLE001
        db_ok = False
    counts: dict[str, int] = {}
    if db_ok:
        try:
            with db.ro_conn() as conn:
                counts = _counts(conn)
        except Exception:  # noqa: BLE001
            counts = {}
    return {
        "hackathon_mode": hs["hackathon_mode"], "demo_data_only": hs["demo_data_only"],
        "synthetic_db": hs["synthetic_db"], "environment_label": hs["environment_label"],
        "rls_disabled": rls["rls_disabled"], "rls_tables_checked": rls["tables_checked"],
        "rls_tables_enabled": rls["tables_enabled"], "database_ok": db_ok,
        "components": _component_flags(), "counts": counts,
    }


def identity_matrix(resolved_role: str) -> dict:
    return {"roles": list(permissions.ROLES), "permissions": list(permissions.PERMISSIONS),
            "matrix": permissions.authorization_matrix(), "resolved_role": resolved_role}


# ===========================================================================
# Units / stations / source systems / boundaries
# ===========================================================================
def list_units(limit: int = 200) -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT u."UnitID", u."UnitName", u."DistrictID", d."DistrictName", u."Active", '
                'count(c."CaseMasterID") '
                'FROM "Unit" u '
                'LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
                'LEFT JOIN "CaseMaster" c ON c."PoliceStationID" = u."UnitID" '
                'GROUP BY u."UnitID", u."UnitName", u."DistrictID", d."DistrictName", u."Active" '
                'ORDER BY count(c."CaseMasterID") DESC, u."UnitName" LIMIT %s', (limit,))
            items = [{"unit_id": int(r[0]), "unit_name": r[1], "district_id": r[2],
                      "district_name": r[3], "active": bool(r[4]), "case_count": int(r[5] or 0)}
                     for r in cur.fetchall()]
            cur.execute('SELECT count(*) FROM "Unit"')
            total = int(cur.fetchone()[0])
    return {"total": total, "items": items}


def list_source_systems() -> dict:
    boundaries: dict[str, int] = {}
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "SourceSystemID","Code","Name","Kind","IsSynthetic" '
                        'FROM "SourceSystem" ORDER BY "Code"')
            items = [{"source_system_id": int(r[0]), "code": r[1], "name": r[2],
                      "kind": r[3], "is_synthetic": bool(r[4])} for r in cur.fetchall()]
            for label, tbl in (("jurisdiction_boundaries", '"JurisdictionBoundary"'),
                               ("unit_locations", '"UnitLocation"')):
                try:
                    cur.execute(f'SELECT count(*) FROM {tbl}')
                    boundaries[label] = int(cur.fetchone()[0])
                except Exception:  # noqa: BLE001
                    boundaries[label] = 0
    return {"total": len(items), "boundaries": boundaries, "items": items}


# ===========================================================================
# Source reconciliation + non-destructive repair
# ===========================================================================
def reconciliation() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "SourceSystemID","Code","Name","Kind","TotalSourceRecords",'
                        '"CommittedRecords","RejectedRecords","DuplicateRecords","PendingRecords",'
                        '"TotalJobs","PartialJobs","FailedJobs","LastReceivedAt" '
                        'FROM "vw_source_reconciliation" ORDER BY "Code"')
            items = [{"source_system_id": int(r[0]), "code": r[1], "name": r[2], "kind": r[3],
                      "total_source_records": int(r[4] or 0), "committed_records": int(r[5] or 0),
                      "rejected_records": int(r[6] or 0), "duplicate_records": int(r[7] or 0),
                      "pending_records": int(r[8] or 0), "total_jobs": int(r[9] or 0),
                      "partial_jobs": int(r[10] or 0), "failed_jobs": int(r[11] or 0),
                      "last_received_at": _s(r[12])} for r in cur.fetchall()]
    return {"total": len(items), "items": items}


def _repair_import(conn, ingestion_job_id: Optional[int], source_record_ids: list[int],
                   reason: str, actor: Optional[str]) -> dict:
    """Non-destructive repair on ``conn`` (no commit): requeue a partial/failed
    job, re-stage rejected source records and re-open their quality issues.
    Nothing is deleted and no canonical row is fabricated."""
    jobs = staged = reopened = 0
    with conn.cursor() as cur:
        if ingestion_job_id is not None:
            cur.execute("UPDATE \"IngestionJob\" SET \"Status\"='pending', \"FinishedAt\"=NULL "
                        "WHERE \"IngestionJobID\"=%s AND \"Status\" IN ('failed','partial')",
                        (ingestion_job_id,))
            jobs = cur.rowcount
        if source_record_ids:
            cur.execute("UPDATE \"SourceRecord\" SET \"Status\"='staged' "
                        "WHERE \"SourceRecordID\" = ANY(%s) AND \"Status\"='rejected'",
                        (list(source_record_ids),))
            staged = cur.rowcount
            cur.execute("UPDATE \"DataQualityIssue\" SET \"Status\"='open', \"ResolvedAt\"=NULL "
                        "WHERE \"SourceRecordID\" = ANY(%s) AND \"Status\" IN ('quarantined','resolved')",
                        (list(source_record_ids),))
            reopened = cur.rowcount
    audit.record(audit.Action.UPDATE, "source_reconciliation_repair", ingestion_job_id,
                 actor=actor, conn=conn,
                 detail={"reason": reason, "jobs": jobs, "records": staged,
                         "issues_reopened": reopened})
    return {"ingestion_jobs_requeued": jobs, "source_records_restaged": staged,
            "quality_issues_reopened": reopened,
            "note": "Non-destructive: records re-staged for review; nothing deleted."}


def repair_import(ingestion_job_id: Optional[int], source_record_ids: list[int],
                  reason: str, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _repair_import(conn, ingestion_job_id, source_record_ids, reason, actor)


# ===========================================================================
# Audit search / export
# ===========================================================================
def search_audit(action: Optional[str], resource: Optional[str], actor: Optional[str],
                 text: Optional[str], since: Optional[str], until: Optional[str],
                 page: int, page_size: int) -> dict:
    where, params = [], []
    if action:
        where.append('"Action" = %s'); params.append(action)
    if resource:
        where.append('"Resource" = %s'); params.append(resource)
    if actor:
        where.append('"Actor" = %s'); params.append(actor)
    if since:
        where.append('"OccurredAt" >= %s'); params.append(since)
    if until:
        where.append('"OccurredAt" <= %s'); params.append(until)
    if text:
        where.append('(CAST("Detail" AS TEXT) ILIKE %s OR "Resource" ILIKE %s OR "Action" ILIKE %s)')
        like = f"%{text}%"; params.extend([like, like, like])
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (max(1, page) - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "vw_audit_events" {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute(f'SELECT "AuditEventID","OccurredAt","Actor","ActorRole","Action",'
                        f'"Resource","ResourceID","Detail" FROM "vw_audit_events" {clause} '
                        'ORDER BY "OccurredAt" DESC, "AuditEventID" DESC LIMIT %s OFFSET %s',
                        params + [page_size, offset])
            items = [{"audit_event_id": int(r[0]), "occurred_at": _s(r[1]), "actor": r[2],
                      "actor_role": r[3], "action": r[4], "resource": r[5], "resource_id": r[6],
                      "detail": r[7] or {}} for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def export_audit_rows(action: Optional[str], resource: Optional[str], actor: Optional[str],
                      text: Optional[str], since: Optional[str], until: Optional[str],
                      cap: int = 5000) -> list[dict]:
    data = search_audit(action, resource, actor, text, since, until, page=1, page_size=cap)
    return data["items"]


# ===========================================================================
# Retention / legal hold (non-destructive)
# ===========================================================================
_RP_COLS = ('"RetentionPolicyID","Code","Name","AppliesTo","RetentionDays","ArchiveAfterDays",'
            '"ExpiryAction","Description","IsActive"')


def _rp_row(r) -> dict:
    return {"retention_policy_id": int(r[0]), "code": r[1], "name": r[2], "applies_to": r[3],
            "retention_days": int(r[4]), "archive_after_days": r[5], "expiry_action": r[6],
            "description": r[7], "is_active": bool(r[8])}


def _lh_row(r) -> dict:
    return {"legal_hold_id": int(r[0]), "subject_kind": r[1], "subject_ref_id": r[2],
            "reason": r[3], "status": r[4], "placed_by_actor": r[5], "placed_at": _s(r[6]),
            "released_by_actor": r[7], "released_at": _s(r[8])}


def retention_overview() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_RP_COLS} FROM "RetentionPolicy" ORDER BY "AppliesTo","Code"')
            policies = [_rp_row(r) for r in cur.fetchall()]
            cur.execute('SELECT "LegalHoldID","SubjectKind","SubjectRefID","Reason","Status",'
                        '"PlacedByActor","PlacedAt","ReleasedByActor","ReleasedAt" '
                        'FROM "LegalHold" ORDER BY "PlacedAt" DESC LIMIT 200')
            holds = [_lh_row(r) for r in cur.fetchall()]
            summary = {"total": 0, "expiry_flagged": 0, "on_legal_hold": 0}
            try:
                cur.execute('SELECT count(*), count(*) FILTER (WHERE "ExpiryFlagged"), '
                            'count(*) FILTER (WHERE "OnLegalHold") FROM "vw_evidence_retention"')
                r = cur.fetchone()
                summary = {"total": int(r[0] or 0), "expiry_flagged": int(r[1] or 0),
                           "on_legal_hold": int(r[2] or 0)}
            except Exception:  # noqa: BLE001
                pass
    return {"policies": policies, "legal_holds": holds, "evidence_summary": summary,
            "non_destructive": True}


def upsert_retention_policy(body, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "RetentionPolicy" ("Code","Name","AppliesTo","RetentionDays",'
                '"ArchiveAfterDays","ExpiryAction","Description","IsActive","CreatedByActor") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT ("Code") DO UPDATE SET "Name"=EXCLUDED."Name",'
                '"AppliesTo"=EXCLUDED."AppliesTo","RetentionDays"=EXCLUDED."RetentionDays",'
                '"ArchiveAfterDays"=EXCLUDED."ArchiveAfterDays","ExpiryAction"=EXCLUDED."ExpiryAction",'
                '"Description"=EXCLUDED."Description","IsActive"=EXCLUDED."IsActive" '
                f'RETURNING {_RP_COLS}',
                (body.code, body.name, body.applies_to, body.retention_days, body.archive_after_days,
                 body.expiry_action, body.description, body.is_active, actor))
            row = _rp_row(cur.fetchone())
        audit.record(audit.Action.UPDATE, "retention_policy", row["retention_policy_id"],
                     actor=actor, conn=conn,
                     detail={"code": body.code, "applies_to": body.applies_to,
                             "expiry_action": body.expiry_action})
    return row


def place_legal_hold(subject_kind: str, subject_ref_id: str, reason: str,
                     actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO "LegalHold" ("SubjectKind","SubjectRefID","Reason",'
                        '"PlacedByActor") VALUES (%s,%s,%s,%s) '
                        'RETURNING "LegalHoldID","SubjectKind","SubjectRefID","Reason","Status",'
                        '"PlacedByActor","PlacedAt","ReleasedByActor","ReleasedAt"',
                        (subject_kind, subject_ref_id, reason, actor))
            row = _lh_row(cur.fetchone())
        audit.record(audit.Action.CREATE, "legal_hold", row["legal_hold_id"], actor=actor,
                     conn=conn, detail={"subject_kind": subject_kind, "subject_ref_id": subject_ref_id})
    return row


def release_legal_hold(legal_hold_id: int, actor: Optional[str]) -> Optional[dict]:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE \"LegalHold\" SET \"Status\"='released', \"ReleasedByActor\"=%s, "
                        '"ReleasedAt"=now() WHERE "LegalHoldID"=%s AND "Status"=\'active\' '
                        'RETURNING "LegalHoldID","SubjectKind","SubjectRefID","Reason","Status",'
                        '"PlacedByActor","PlacedAt","ReleasedByActor","ReleasedAt"',
                        (actor, legal_hold_id))
            r = cur.fetchone()
            if not r:
                return None
            row = _lh_row(r)
        audit.record(audit.Action.UPDATE, "legal_hold", legal_hold_id, actor=actor, conn=conn,
                     detail={"status": "released"})
    return row


# ===========================================================================
# Model lifecycle / review-due / drift
# ===========================================================================
def model_reviews() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "ModelVersionID","ModelName","Version","ApprovalStatus","Environment",'
                        '"ApprovedAt","ModelReviewID","ReviewKind","ReviewStatus","DueAt",'
                        '"DriftSignal","EffectiveReviewState" FROM "vw_model_review_due" '
                        'ORDER BY "ModelVersionID" DESC')
            items = [{"model_version_id": int(r[0]), "model_name": r[1], "version": r[2],
                      "approval_status": r[3], "environment": r[4], "approved_at": _s(r[5]),
                      "model_review_id": r[6], "review_kind": r[7], "review_status": r[8],
                      "due_at": _s(r[9]), "drift_signal": r[10] or {},
                      "effective_review_state": r[11]} for r in cur.fetchall()]
    return {"total": len(items), "items": items}


def upsert_model_review(model_version_id: int, review_kind: str, status: str,
                        findings: dict, drift_signal: dict, actor: Optional[str]) -> dict:
    completed_at = "now()" if status in ("completed", "waived") else "NULL"
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "ModelVersion" WHERE "ModelVersionID"=%s', (model_version_id,))
            if cur.fetchone() is None:
                raise ValueError(f"ModelVersion {model_version_id} not found")
            cur.execute(
                'INSERT INTO "ModelReview" ("ModelVersionID","ReviewKind","Status","ReviewerActor",'
                f'"Findings","DriftSignal","CompletedAt") VALUES (%s,%s,%s,%s,%s,%s,{completed_at}) '
                'ON CONFLICT ("ModelVersionID","ReviewKind") DO UPDATE SET "Status"=EXCLUDED."Status",'
                '"ReviewerActor"=EXCLUDED."ReviewerActor","Findings"=EXCLUDED."Findings",'
                f'"DriftSignal"=EXCLUDED."DriftSignal","CompletedAt"={completed_at} '
                'RETURNING "ModelReviewID"',
                (model_version_id, review_kind, status, actor, Json(findings or {}),
                 Json(drift_signal or {})))
            review_id = int(cur.fetchone()[0])
        audit.record(audit.Action.MODEL_RUN, "model_review", review_id, actor=actor, conn=conn,
                     detail={"model_version_id": model_version_id, "kind": review_kind,
                             "status": status})
    return {"model_review_id": review_id, "model_version_id": model_version_id,
            "review_kind": review_kind, "status": status}


# ===========================================================================
# Queues (ingestion / data-quality / evidence quarantine) — NO extraction queue
# ===========================================================================
def queues() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM \"DataQualityIssue\" WHERE \"Status\"='open'")
            dq_open = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM \"IngestionJob\" WHERE \"Status\" IN ('partial','failed')")
            ing = int(cur.fetchone()[0])
            cur.execute('SELECT count(*) FROM "vw_evidence_quarantine_queue"')
            quar = int(cur.fetchone()[0])
            cur.execute('SELECT "DataQualityIssueID","IssueType","Severity","Status","SourceRecordID",'
                        '"CaseMasterID" FROM "DataQualityIssue" WHERE "Status"=\'open\' '
                        'ORDER BY "DataQualityIssueID" DESC LIMIT 50')
            dq_items = [{"data_quality_issue_id": int(r[0]), "issue_type": r[1], "severity": r[2],
                         "status": r[3], "source_record_id": r[4], "case_master_id": r[5]}
                        for r in cur.fetchall()]
            cur.execute('SELECT "EvidenceObjectID","EvidenceItemID","Title","StorageStatus",'
                        '"MimeType","SizeBytes" FROM "vw_evidence_quarantine_queue" '
                        'ORDER BY "EvidenceObjectID" DESC LIMIT 50')
            quar_items = [{"evidence_object_id": int(r[0]), "evidence_item_id": int(r[1]),
                           "title": r[2], "storage_status": r[3], "mime_type": r[4],
                           "size_bytes": r[5]} for r in cur.fetchall()]
    return {"data_quality_open": dq_open, "ingestion_partial_failed": ing,
            "evidence_quarantine": quar, "extraction_queue_present": False,
            "data_quality_items": dq_items, "quarantine_items": quar_items}


# ===========================================================================
# Usage / budgets / feature flags
# ===========================================================================
def _repo_root() -> Optional[Path]:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "infra" / "catalyst" / "billing" / "budget.json").exists():
            return parent
    return None


def _budget() -> dict:
    root = _repo_root()
    if root is not None:
        try:
            with open(root / "infra" / "catalyst" / "billing" / "budget.json", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001
            pass
    # Fallback baseline (report §9) so the endpoint works in the AppSail container too.
    return {"plan_baseline": {"period": "2026-07-17 to 2026-08-17", "free_credit_inr": 300,
                              "basic_plan_inr": 1500, "envelope_inr": 1800,
                              "source": "console screenshot (report §9)"},
            "catalyst_budget_alerts_inr": {"thresholds": []}}


def _flag_runtime_effective(key: str, db_enabled: bool) -> Optional[bool]:
    """Some flags are ALSO gated by server env; report the effective runtime state."""
    if key == "rag_assistant":
        # The approved-text assistant supports either the database feature flag
        # (safe offline knowledge base) or the QuickML environment gate.
        return db_enabled or rag_enabled()
    if key in ("notifications_email", "notifications_push"):
        return db_enabled and notify_enabled()
    if key == "signals_enabled":
        return db_enabled and signals_enabled()
    return db_enabled


# Default feature-flag catalogue (config, enforced in code — mirrors the seed in
# services/ml/sql/022_admin_notifications_reports.sql). Feature flags are
# configuration, not RDS operational data, so they are served without a database
# in the deployed AppSail (Prompt 21 §B); runtime env gates are overlaid below.
_DEFAULT_FEATURE_FLAGS: tuple[tuple[str, bool, str, str], ...] = (
    ("rag_assistant", False, "rag",
     "Optional approved-text QuickML RAG assistant. Also requires DRISHTI_QUICKML_RAG_ENABLED."),
    ("notifications_email", False, "notifications",
     "Catalyst Mail delivery for synthetic summaries. Also requires DRISHTI_NOTIFY_ENABLED."),
    ("notifications_push", False, "notifications",
     "Catalyst Push delivery for synthetic summaries. Also requires DRISHTI_NOTIFY_ENABLED."),
    ("reports_smartbrowz", True, "reports",
     "Use Catalyst SmartBrowz for report rendering (else AppSail fallback)."),
    ("signals_enabled", True, "admin",
     "Publish Catalyst Signals after the Data Store commit."),
)


def list_feature_flags() -> list[dict]:
    from ..config import get_settings
    if get_settings().database_url:
        try:
            with db.ro_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT "Key","Enabled","Category","Description" FROM "FeatureFlag" '
                                'ORDER BY "Category","Key"')
                    rows = cur.fetchall()
            return [{"key": r[0], "enabled": bool(r[1]), "category": r[2], "description": r[3],
                     "runtime_effective": _flag_runtime_effective(r[0], bool(r[1]))} for r in rows]
        except Exception:  # noqa: BLE001 — RDS unreachable -> code-based catalogue
            pass
    # Deployed AppSail (no DATABASE_URL): code-based flag catalogue.
    return [{"key": k, "enabled": en, "category": cat, "description": desc,
             "runtime_effective": _flag_runtime_effective(k, en)}
            for (k, en, cat, desc) in sorted(_DEFAULT_FEATURE_FLAGS, key=lambda x: (x[2], x[0]))]


def usage() -> dict:
    budget = _budget()
    alerts = (budget.get("catalyst_budget_alerts_inr", {}) or {}).get("thresholds", [])
    return {"plan_baseline": budget.get("plan_baseline", {}), "budget_alerts": alerts,
            "feature_flags": list_feature_flags(),
            "note": ("Catalyst billing is console-only (no CLI/API on this login); AWS uses "
                     "AWS Budgets + CloudWatch. Values are the hackathon plan baseline.")}


def set_feature_flag(key: str, enabled: bool, actor: Optional[str]) -> Optional[dict]:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE "FeatureFlag" SET "Enabled"=%s, "UpdatedByActor"=%s, "UpdatedAt"=now() '
                        'WHERE "Key"=%s RETURNING "Key","Enabled","Category","Description"',
                        (enabled, actor, key))
            r = cur.fetchone()
            if not r:
                return None
        audit.record(audit.Action.UPDATE, "feature_flag", key, actor=actor, conn=conn,
                     detail={"enabled": enabled})
    # a flag toggle can change a cached lookup; clear the small lookup cache key.
    try:
        get_cache().put(SEG_LOOKUP, f"feature_flag:{key}", "1", ttl_s=1)
    except Exception:  # noqa: BLE001
        pass
    return {"key": r[0], "enabled": bool(r[1]), "category": r[2], "description": r[3],
            "runtime_effective": _flag_runtime_effective(r[0], bool(r[1]))}


# ===========================================================================
# Saved filters + report templates
# ===========================================================================
def list_saved_filters(actor: str, scope: Optional[str] = None) -> dict:
    where = ['("OwnerActor" = %s OR "IsShared" = TRUE)']
    params: list[Any] = [actor]
    if scope:
        where.append('"Scope" = %s'); params.append(scope)
    clause = 'WHERE ' + ' AND '.join(where)
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT "SavedFilterID","OwnerActor","Scope","Name","FilterJSON","IsShared" '
                        f'FROM "SavedFilter" {clause} ORDER BY "UpdatedAt" DESC LIMIT 200', params)
            items = [{"saved_filter_id": int(r[0]), "owner_actor": r[1], "scope": r[2],
                      "name": r[3], "filter_json": r[4] or {}, "is_shared": bool(r[5])}
                     for r in cur.fetchall()]
    return {"total": len(items), "items": items}


def create_saved_filter(owner_actor: str, scope: str, name: str, filter_json: dict,
                        is_shared: bool) -> dict:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "SavedFilter" ("OwnerActor","Scope","Name","FilterJSON","IsShared") '
                'VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT ("OwnerActor","Scope","Name") DO UPDATE SET '
                '"FilterJSON"=EXCLUDED."FilterJSON","IsShared"=EXCLUDED."IsShared" '
                'RETURNING "SavedFilterID","OwnerActor","Scope","Name","FilterJSON","IsShared"',
                (owner_actor, scope, name, Json(filter_json or {}), is_shared))
            r = cur.fetchone()
        audit.record(audit.Action.CREATE, "saved_filter", int(r[0]), actor=owner_actor, conn=conn,
                     detail={"scope": scope, "name": name})
    return {"saved_filter_id": int(r[0]), "owner_actor": r[1], "scope": r[2], "name": r[3],
            "filter_json": r[4] or {}, "is_shared": bool(r[5])}


def delete_saved_filter(saved_filter_id: int, owner_actor: str) -> bool:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "SavedFilter" WHERE "SavedFilterID"=%s AND "OwnerActor"=%s',
                        (saved_filter_id, owner_actor))
            deleted = cur.rowcount > 0
        if deleted:
            audit.record(audit.Action.DELETE, "saved_filter", saved_filter_id, actor=owner_actor,
                         conn=conn, detail={})
    return deleted


def list_report_templates(role: Optional[str] = None) -> list[dict]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "ReportTemplateID","Code","Name","Description","ReportKind",'
                        '"ScopeKind","AllowedRoles","ConfigSchema","IsActive" '
                        'FROM "ReportTemplate" WHERE "IsActive" ORDER BY "ReportKind","Code"')
            rows = cur.fetchall()
    out = []
    for r in rows:
        allowed = list(r[6] or [])
        # INTERIM: every command role reaches every template (see app/roles.py);
        # the per-template AllowedRoles list is kept for when RBAC narrows again.
        if role is not None and role not in allowed and role not in ALL_ROLES:
            continue
        out.append({"report_template_id": int(r[0]), "code": r[1], "name": r[2],
                    "description": r[3], "report_kind": r[4], "scope_kind": r[5],
                    "allowed_roles": allowed, "config_schema": r[7] or {}, "is_active": bool(r[8])})
    return out
