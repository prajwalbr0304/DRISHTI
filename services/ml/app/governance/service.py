"""Governed feature/prediction service (Phase 10).

Registry reads + the prediction state machine + snapshot invalidation + label
reads. Internal ``_fn(conn, ...)`` helpers never commit (tests drive them under
rw_rollback); public wrappers open db.rw_conn()/ro_conn().

Predictions are aggregate decision-support only. A request binds to an exact
approved ModelVersion + an immutable FeatureSnapshot whose FeatureSchemaVersion
matches the model's (strict compatibility). Nothing operationalises the
synthetic offender-risk labels.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from psycopg2.extras import Json

from .. import audit, db
from ..contracts import AiResult
from . import builder

# Re-export builder guards so the router can map them uniformly.
BuilderError = builder.BuilderError
ProtectedFeatureError = builder.ProtectedFeatureError
SchemaNotApproved = builder.SchemaNotApproved
SubjectNotFound = builder.SubjectNotFound

_RESULT_TTL_DAYS = 30
_LIMITATIONS = (
    "Aggregate area forecast for investigation support and resource planning "
    "only. It is not a person-level judgement, not evidence of an offence, and "
    "must be reviewed by an officer before any action.")


class GovernanceError(Exception):
    pass


class NotFound(GovernanceError):
    pass


class SchemaMismatch(GovernanceError):
    pass


class ModelNotApproved(GovernanceError):
    pass


class StaleSnapshot(GovernanceError):
    pass


class InvalidState(GovernanceError):
    pass


def _s(v) -> Optional[str]:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v) if v is not None else None


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


# ===========================================================================
# Registry reads
# ===========================================================================
def _feature_def_row(r) -> dict:
    return {"feature_definition_id": int(r[0]), "name": r[1], "value_type": r[2],
            "description": r[3], "source_table": r[4], "source_field": r[5],
            "source_event": r[6], "transformation": r[7], "window_spec": r[8],
            "observation_cutoff_behavior": r[9], "sensitivity": r[10],
            "allowed_tasks": list(r[11] or []), "missing_policy": r[12],
            "stale_policy": r[13], "owner": r[14], "approval_status": r[15]}


_FD_COLS = ('"FeatureDefinitionID","Name","ValueType","Description","SourceTable",'
            '"SourceField","SourceEvent","Transformation","WindowSpec",'
            '"ObservationCutoffBehavior","Sensitivity","AllowedTasks","MissingPolicy",'
            '"StalePolicy","Owner","ApprovalStatus"')


def list_feature_definitions() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_FD_COLS} FROM "FeatureDefinition" ORDER BY "Name"')
            items = [_feature_def_row(r) for r in cur.fetchall()]
    return {"total": len(items), "items": items}


def list_schemas(include_features: bool = True) -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "FeatureSchemaVersionID","SchemaName","Version",'
                        '"FeatureDefinitionIDs","Task","Status","ApprovedByActor",'
                        '"ApprovedAt","CreatedAt" FROM "FeatureSchemaVersion" '
                        'ORDER BY "SchemaName","Version"')
            rows = cur.fetchall()
            defs_by_id: dict[int, dict] = {}
            if include_features:
                cur.execute(f'SELECT {_FD_COLS} FROM "FeatureDefinition"')
                defs_by_id = {int(r[0]): _feature_def_row(r) for r in cur.fetchall()}
    items = []
    for r in rows:
        ids = [int(x) for x in (r[3] or [])]
        feats = [defs_by_id[i] for i in ids if i in defs_by_id] if include_features else []
        items.append({
            "feature_schema_version_id": int(r[0]), "schema_name": r[1], "version": r[2],
            "feature_definition_ids": ids, "task": r[4], "status": r[5],
            "approved_by_actor": r[6], "approved_at": _s(r[7]), "created_at": _s(r[8]),
            "features": feats,
            "has_protected_feature": any(f["sensitivity"] in ("protected", "restricted") for f in feats),
        })
    return {"total": len(items), "items": items}


_MV_COLS = ('"ModelVersionID","ModelName","ModelType","Version","Framework","ArtifactURI",'
            '"ArtifactDigest","ImageDigest","FeatureSchemaVersionID","TrainingDatasetSnapshotID",'
            '"ApprovalStatus","ApprovedBy","ApprovedAt","Environment","EvaluationReport",'
            '"Status","IsRollbackTarget","RollbackToModelVersionID"')


def _mv_row(r) -> dict:
    return {"model_version_id": int(r[0]), "model_name": r[1], "model_type": r[2],
            "version": r[3], "framework": r[4], "artifact_uri": r[5], "artifact_digest": r[6],
            "image_digest": r[7], "feature_schema_version_id": r[8],
            "training_dataset_snapshot_id": r[9], "approval_status": r[10], "approved_by": r[11],
            "approved_at": _s(r[12]), "environment": r[13], "evaluation_report": r[14] or {},
            "status": r[15], "is_rollback_target": bool(r[16]), "rollback_to_model_version_id": r[17]}


def list_model_versions(governed_only: bool = True) -> dict:
    where = 'WHERE "FeatureSchemaVersionID" IS NOT NULL OR "ApprovalStatus" IS NOT NULL' \
        if governed_only else ''
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_MV_COLS} FROM "ModelVersion" {where} '
                        'ORDER BY "ModelVersionID" DESC')
            items = [_mv_row(r) for r in cur.fetchall()]
    return {"total": len(items), "items": items}


_FS_COLS = ('"FeatureSnapshotID","FeatureSchemaVersionID","SubjectKind","SubjectRefID",'
            '"ObservationCutoff","Values","SourceVersions","QualityStatus","ContentHash",'
            '"IsImmutable","SupersededByFeatureSnapshotID","StaleReason","SupersededAt",'
            '"BuiltByActor","CreatedAt"')


def _fs_row(r) -> dict:
    return {"feature_snapshot_id": int(r[0]), "feature_schema_version_id": r[1],
            "subject_kind": r[2], "subject_ref_id": r[3], "observation_cutoff": _s(r[4]),
            "values": r[5] or {}, "source_versions": r[6] or {}, "quality_status": r[7],
            "content_hash": r[8], "is_immutable": bool(r[9]),
            "superseded_by_feature_snapshot_id": r[10], "stale_reason": r[11],
            "superseded_at": _s(r[12]), "built_by_actor": r[13], "created_at": _s(r[14])}


def list_snapshots(subject_kind: Optional[str] = None, subject_ref_id: Optional[str] = None,
                   page: int = 1, page_size: int = 50) -> dict:
    where, params = [], []
    if subject_kind:
        where.append('"SubjectKind"=%s'); params.append(subject_kind)
    if subject_ref_id:
        where.append('"SubjectRefID"=%s'); params.append(subject_ref_id)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (max(1, page) - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "FeatureSnapshot" {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute(f'SELECT {_FS_COLS} FROM "FeatureSnapshot" {clause} '
                        'ORDER BY "FeatureSnapshotID" DESC LIMIT %s OFFSET %s',
                        params + [page_size, offset])
            items = [_fs_row(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def get_snapshot(conn, snapshot_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_FS_COLS} FROM "FeatureSnapshot" WHERE "FeatureSnapshotID"=%s',
                    (snapshot_id,))
        r = cur.fetchone()
    return _fs_row(r) if r else None


# ===========================================================================
# Feature builder (public)
# ===========================================================================
def build_snapshot(feature_schema_version_id: int, subject_kind: str, subject_ref_id: str,
                   observation_cutoff: Optional[str], actor: Optional[str]) -> dict:
    cutoff = None
    if observation_cutoff:
        cutoff = dt.datetime.fromisoformat(observation_cutoff)
    with db.rw_conn() as conn:
        out = builder.build_snapshot(
            conn, feature_schema_version_id=feature_schema_version_id,
            subject_kind=subject_kind, subject_ref_id=subject_ref_id,
            observation_cutoff=cutoff, actor=actor)
        audit.record(audit.Action.MODEL_RUN, "feature_snapshot", out["feature_snapshot_id"],
                     actor=actor, conn=conn,
                     detail={"schema": feature_schema_version_id, "subject_kind": subject_kind,
                             "quality": out["quality_status"]})
    return out


# ===========================================================================
# Prediction state machine
# ===========================================================================
def _load_request(conn, request_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('SELECT "PredictionRequestID","ModelVersionID","FeatureSnapshotID",'
                    '"RequestKind","IdempotencyKey","Status","RequestedByActor","CreatedAt" '
                    'FROM "PredictionRequest" WHERE "PredictionRequestID"=%s', (request_id,))
        r = cur.fetchone()
    if not r:
        return None
    return {"prediction_request_id": int(r[0]), "model_version_id": r[1],
            "feature_snapshot_id": r[2], "request_kind": r[3], "idempotency_key": r[4],
            "status": r[5], "requested_by_actor": r[6], "created_at": _s(r[7])}


def _model_label(conn, mv_id: Optional[int]) -> Optional[str]:
    if mv_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute('SELECT "ModelName","Version" FROM "ModelVersion" WHERE "ModelVersionID"=%s',
                    (mv_id,))
        r = cur.fetchone()
    return f"{r[0]}@{r[1]}" if r else None


def _create_request(conn, model_version_id: int, feature_snapshot_id: int,
                    request_kind: str = "batch", idempotency_key: Optional[str] = None,
                    actor: Optional[str] = None) -> dict:
    key = idempotency_key or f"auto:{model_version_id}:{feature_snapshot_id}:{request_kind}"
    # idempotency: an existing request with this key is returned unchanged.
    with conn.cursor() as cur:
        cur.execute('SELECT "PredictionRequestID" FROM "PredictionRequest" WHERE "IdempotencyKey"=%s',
                    (key,))
        existing = cur.fetchone()
    if existing:
        req = _load_request(conn, int(existing[0]))
        req["reused"] = True
        return req

    # strict model/feature-schema compatibility.
    with conn.cursor() as cur:
        cur.execute('SELECT "ApprovalStatus","FeatureSchemaVersionID" FROM "ModelVersion" '
                    'WHERE "ModelVersionID"=%s', (model_version_id,))
        m = cur.fetchone()
        if not m:
            raise NotFound(f"ModelVersion {model_version_id} not found.")
        cur.execute('SELECT "FeatureSchemaVersionID" FROM "FeatureSnapshot" '
                    'WHERE "FeatureSnapshotID"=%s', (feature_snapshot_id,))
        s = cur.fetchone()
        if not s:
            raise NotFound(f"FeatureSnapshot {feature_snapshot_id} not found.")
    model_approval, model_fsv = m[0], m[1]
    snapshot_fsv = s[0]
    if model_approval != "approved":
        raise ModelNotApproved(
            f"ModelVersion {model_version_id} is '{model_approval or 'ungoverned'}' — only an "
            "approved, governed model may serve predictions.")
    if model_fsv is None or snapshot_fsv is None or int(model_fsv) != int(snapshot_fsv):
        raise SchemaMismatch(
            f"Feature-schema mismatch: model expects schema {model_fsv}, snapshot uses {snapshot_fsv}.")

    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PredictionRequest" ("ModelVersionID","FeatureSnapshotID",'
                    '"RequestKind","IdempotencyKey","Status","RequestedByActor") '
                    "VALUES (%s,%s,%s,%s,'queued',%s) RETURNING \"PredictionRequestID\"",
                    (model_version_id, feature_snapshot_id, request_kind, key, actor))
        req_id = int(cur.fetchone()[0])
    audit.record(audit.Action.MODEL_RUN, "prediction_request", req_id, actor=actor, conn=conn,
                 detail={"model_version_id": model_version_id, "feature_snapshot_id": feature_snapshot_id,
                         "kind": request_kind})
    req = _load_request(conn, req_id)
    req["reused"] = False
    return req


def _infer(model_row: dict, values: dict) -> tuple[dict, dict, float, float, float]:
    """Transparent, rule-based AREA baseline over the (aggregate) snapshot values.
    Not a trained model and never a person-level judgement — the governed ML
    models arrive in later phases; this proves the contract end-to-end."""
    pre = float(values.get("area_incident_count_precutoff") or 0)
    prior = float(values.get("area_prioryear_count") or pre)
    night = float(values.get("area_night_share_precutoff") or 0.0)
    cyber = float(values.get("area_cyber_share_precutoff") or 0.0)
    projected = round(0.5 * pre + 0.5 * prior)          # seasonal-naive blend
    band = "low" if projected <= 20 else "medium" if projected <= 60 else "high"
    output = {"projected_next_period_incidents": projected, "band": band}
    explanation = {"method": "seasonal-naive blend of pre-cutoff and prior-year counts",
                   "top_features": ["area_incident_count_precutoff", "area_prioryear_count"],
                   "night_share": round(night, 4), "cyber_share": round(cyber, 4)}
    return output, explanation, 0.5, float(round(projected * 0.7)), float(round(projected * 1.3))


def _run_request(conn, request_id: int, actor: Optional[str] = None) -> dict:
    req = _load_request(conn, request_id)
    if not req:
        raise NotFound(f"PredictionRequest {request_id} not found.")
    if req["status"] in ("completed", "reviewed"):
        # idempotent replay: return the current result, don't recompute.
        res = _current_result(conn, request_id)
        return {"request": _load_request(conn, request_id), "result": res, "reran": False}
    if req["status"] in ("stale", "superseded", "rejected"):
        raise InvalidState(f"Request {request_id} is '{req['status']}' and cannot be run.")

    snap = get_snapshot(conn, int(req["feature_snapshot_id"]))
    if snap is None:
        raise NotFound(f"FeatureSnapshot {req['feature_snapshot_id']} not found.")
    if snap["quality_status"] == "stale" or snap["superseded_by_feature_snapshot_id"] is not None:
        with conn.cursor() as cur:
            cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='stale' WHERE \"PredictionRequestID\"=%s",
                        (request_id,))
        raise StaleSnapshot(f"FeatureSnapshot {snap['feature_snapshot_id']} is stale/superseded; "
                            "rebuild the snapshot before predicting.")

    with conn.cursor() as cur:
        cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='running' WHERE \"PredictionRequestID\"=%s",
                    (request_id,))
        cur.execute('SELECT "ModelName","Version" FROM "ModelVersion" WHERE "ModelVersionID"=%s',
                    (req["model_version_id"],))
        mrow = cur.fetchone()

    output, explanation, confidence, lo, hi = _infer({"name": mrow[0] if mrow else None}, snap["values"])
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_RESULT_TTL_DAYS)
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PredictionResult" ("PredictionRequestID","ModelVersionID",'
                    '"FeatureSnapshotID","OutputJSON","Explanation","Limitations","Confidence",'
                    '"LowerInterval","UpperInterval","ExpiresAt") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "PredictionResultID"',
                    (request_id, req["model_version_id"], req["feature_snapshot_id"],
                     Json(output), Json(explanation), _LIMITATIONS, confidence, lo, hi, expires))
        result_id = int(cur.fetchone()[0])
        cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='completed' WHERE \"PredictionRequestID\"=%s",
                    (request_id,))
    audit.record(audit.Action.MODEL_RUN, "prediction_result", result_id, actor=actor, conn=conn,
                 detail={"request_id": request_id, "band": output.get("band")})
    return {"request": _load_request(conn, request_id),
            "result": _load_result(conn, result_id), "reran": True}


def _load_result(conn, result_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('SELECT "PredictionResultID","ModelVersionID","FeatureSnapshotID","OutputJSON",'
                    '"Explanation","Limitations","Confidence","LowerInterval","UpperInterval",'
                    '"ExpiresAt","IsStale","StaleReason","SupersededByResultID","CreatedAt" '
                    'FROM "PredictionResult" WHERE "PredictionResultID"=%s', (result_id,))
        r = cur.fetchone()
    if not r:
        return None
    return {"prediction_result_id": int(r[0]), "model_version_id": r[1], "feature_snapshot_id": r[2],
            "output": r[3] or {}, "explanation": r[4] or {}, "limitations": r[5],
            "confidence": _f(r[6]), "lower_interval": _f(r[7]), "upper_interval": _f(r[8]),
            "expires_at": _s(r[9]), "is_stale": bool(r[10]), "stale_reason": r[11],
            "superseded_by_result_id": r[12], "created_at": _s(r[13])}


def _current_result(conn, request_id: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute('SELECT "PredictionResultID" FROM "PredictionResult" '
                    'WHERE "PredictionRequestID"=%s AND "SupersededByResultID" IS NULL '
                    'ORDER BY "PredictionResultID" DESC LIMIT 1', (request_id,))
        r = cur.fetchone()
    return _load_result(conn, int(r[0])) if r else None


def _review_result(conn, result_id: int, decision: str, override_reason: Optional[str],
                   actor: Optional[str]) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT "PredictionRequestID" FROM "PredictionResult" WHERE "PredictionResultID"=%s',
                    (result_id,))
        r = cur.fetchone()
    if not r:
        raise NotFound(f"PredictionResult {result_id} not found.")
    if decision == "override" and not (override_reason and override_reason.strip()):
        raise InvalidState("An override decision requires a reason.")
    request_id = int(r[0])
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "PredictionReview" ("PredictionResultID","ReviewerActor","Decision",'
                    '"OverrideReason") VALUES (%s,%s,%s,%s) RETURNING "PredictionReviewID"',
                    (result_id, actor, decision, override_reason))
        review_id = int(cur.fetchone()[0])
        new_status = "rejected" if decision == "reject" else "reviewed"
        cur.execute('UPDATE "PredictionRequest" SET "Status"=%s WHERE "PredictionRequestID"=%s',
                    (new_status, request_id))
    audit.record(audit.Action.PREDICTION_REVIEW, "prediction_result", result_id, actor=actor,
                 conn=conn, detail={"decision": decision, "request_id": request_id})
    return {"prediction_review_id": review_id, "reviewer_actor": actor, "decision": decision,
            "override_reason": override_reason, "request_id": request_id, "status": new_status}


def _invalidate_for_subject(conn, subject_kind: str, subject_ref_id: str, reason: str,
                            actor: Optional[str]) -> dict:
    """Accepted canonical edit -> mark the subject's live snapshots stale + their
    prediction results/requests stale. No snapshot is edited in place (the
    immutability trigger allows only the stale/supersession columns)."""
    with conn.cursor() as cur:
        cur.execute('SELECT "FeatureSnapshotID" FROM "FeatureSnapshot" '
                    'WHERE "SubjectKind"=%s AND "SubjectRefID"=%s '
                    "AND \"QualityStatus\" <> 'stale' AND \"SupersededByFeatureSnapshotID\" IS NULL",
                    (subject_kind, subject_ref_id))
        snap_ids = [int(r[0]) for r in cur.fetchall()]
    results = requests = 0
    for sid in snap_ids:
        with conn.cursor() as cur:
            cur.execute("UPDATE \"FeatureSnapshot\" SET \"QualityStatus\"='stale', \"StaleReason\"=%s, "
                        '"SupersededAt"=now() WHERE "FeatureSnapshotID"=%s', (reason, sid))
            cur.execute("UPDATE \"PredictionResult\" SET \"IsStale\"=TRUE, \"StaleReason\"=%s, "
                        '"StaleAt"=now() WHERE "FeatureSnapshotID"=%s AND "IsStale"=FALSE', (reason, sid))
            results += cur.rowcount
            cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='stale' WHERE \"FeatureSnapshotID\"=%s "
                        "AND \"Status\" IN ('queued','running','completed')", (sid,))
            requests += cur.rowcount
    audit.record(audit.Action.UPDATE, "feature_snapshot_invalidate", None, actor=actor, conn=conn,
                 detail={"subject_kind": subject_kind, "subject_ref_id": subject_ref_id,
                         "snapshots": len(snap_ids), "reason": reason})
    return {"subject_kind": subject_kind, "subject_ref_id": subject_ref_id,
            "snapshots_marked_stale": len(snap_ids), "results_marked_stale": results,
            "requests_marked_stale": requests}


def _rollback_model(conn, model_version_id: int, to_model_version_id: Optional[int],
                    actor: Optional[str]) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "ModelVersion" WHERE "ModelVersionID"=%s', (model_version_id,))
        if cur.fetchone() is None:
            raise NotFound(f"ModelVersion {model_version_id} not found.")
        cur.execute('UPDATE "ModelVersion" SET "ApprovalStatus"=\'rolled_back\', '
                    '"RollbackToModelVersionID"=%s WHERE "ModelVersionID"=%s',
                    (to_model_version_id, model_version_id))
        if to_model_version_id is not None:
            cur.execute('UPDATE "ModelVersion" SET "IsRollbackTarget"=TRUE WHERE "ModelVersionID"=%s',
                        (to_model_version_id,))
    audit.record(audit.Action.MODEL_RUN, "model_rollback", model_version_id, actor=actor, conn=conn,
                 detail={"rolled_back_to": to_model_version_id})
    return {"model_version_id": model_version_id, "rolled_back_to": to_model_version_id,
            "approval_status": "rolled_back"}


# ===========================================================================
# Detail assembly + public wrappers
# ===========================================================================
def _ai_answer(conn, req: dict, result: Optional[dict]) -> Optional[dict]:
    if not result:
        return None
    out = result["output"] or {}
    band = out.get("band")
    proj = out.get("projected_next_period_incidents")
    return AiResult(
        answer=(f"Projected next-period band '{band}' (~{proj} incidents) for "
                f"{req.get('feature_snapshot_id') and 'the selected area'}."),
        confidence=result.get("confidence") or 0.0,
        source_record_ids=[f"FeatureSnapshot:{req['feature_snapshot_id']}",
                           f"ModelVersion:{req['model_version_id']}"],
        reasoning_summary=(result.get("explanation") or {}).get("method", ""),
        model_version=_model_label(conn, req["model_version_id"]) or "unknown",
    ).model_dump()


def get_prediction_detail(request_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        req = _load_request(conn, request_id)
        if not req:
            return None
        req["model_version_label"] = _model_label(conn, req["model_version_id"])
        result = _current_result(conn, request_id)
        snap = get_snapshot(conn, int(req["feature_snapshot_id"])) if req["feature_snapshot_id"] else None
        with conn.cursor() as cur:
            cur.execute('SELECT "PredictionReviewID","ReviewerActor","Decision","OverrideReason",'
                        '"ReviewedAt" FROM "PredictionReview" pr '
                        'JOIN "PredictionResult" res ON res."PredictionResultID"=pr."PredictionResultID" '
                        'WHERE res."PredictionRequestID"=%s ORDER BY pr."PredictionReviewID"', (request_id,))
            reviews = [{"prediction_review_id": int(r[0]), "reviewer_actor": r[1], "decision": r[2],
                        "override_reason": r[3], "reviewed_at": _s(r[4])} for r in cur.fetchall()]
            mv = None
            if req["model_version_id"]:
                cur.execute(f'SELECT {_MV_COLS} FROM "ModelVersion" WHERE "ModelVersionID"=%s',
                            (req["model_version_id"],))
                m = cur.fetchone()
                mv = _mv_row(m) if m else None
        expired = False
        if result and result.get("expires_at"):
            try:
                expired = dt.datetime.fromisoformat(result["expires_at"]) < dt.datetime.now(dt.timezone.utc)
            except ValueError:
                expired = False
        is_current = (req["status"] in ("completed", "reviewed") and result is not None
                      and not result["is_stale"] and result["superseded_by_result_id"] is None
                      and not expired)
        answer = _ai_answer(conn, req, result)
    return {"request": req, "result": result, "reviews": reviews, "feature_snapshot": snap,
            "model_version": mv, "is_current": is_current, "answer": answer}


def list_requests(status: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict:
    where, params = [], []
    if status:
        where.append('pr."Status"=%s'); params.append(status)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (max(1, page) - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "PredictionRequest" pr {clause}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                'SELECT pr."PredictionRequestID",pr."ModelVersionID",pr."FeatureSnapshotID",'
                'pr."RequestKind",pr."IdempotencyKey",pr."Status",pr."RequestedByActor",pr."CreatedAt",'
                'mv."ModelName",mv."Version" FROM "PredictionRequest" pr '
                'LEFT JOIN "ModelVersion" mv ON mv."ModelVersionID"=pr."ModelVersionID" '
                f'{clause} ORDER BY pr."PredictionRequestID" DESC LIMIT %s OFFSET %s',
                params + [page_size, offset])
            items = [{"prediction_request_id": int(r[0]), "model_version_id": r[1],
                      "feature_snapshot_id": r[2], "request_kind": r[3], "idempotency_key": r[4],
                      "status": r[5], "requested_by_actor": r[6], "created_at": _s(r[7]),
                      "model_version_label": (f"{r[8]}@{r[9]}" if r[8] else None)}
                     for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def list_labels(split: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict:
    where, params = [], []
    if split:
        where.append('"SplitTag"=%s'); params.append(split)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (max(1, page) - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "OutcomeLabel" {clause}', params)
            total = int(cur.fetchone()[0])
            # leakage self-check: no label window may start before its cutoff.
            cur.execute('SELECT count(*) FROM "OutcomeLabel" WHERE "LabelWindowStart" < "ObservationCutoff"')
            leaks = int(cur.fetchone()[0])
            cur.execute('SELECT "SplitTag", count(*) FROM "OutcomeLabel" GROUP BY 1', ())
            splits = {(r[0] or "unassigned"): int(r[1]) for r in cur.fetchall()}
            cur.execute('SELECT "OutcomeLabelID","CaseMasterID","SubjectKind","SubjectRefID","LabelName",'
                        '"LabelValue","OutcomeObservationID","ObservationCutoff","LabelWindowStart",'
                        f'"LabelWindowEnd","SplitTag" FROM "OutcomeLabel" {clause} '
                        'ORDER BY "OutcomeLabelID" LIMIT %s OFFSET %s', params + [page_size, offset])
            items = [{"outcome_label_id": int(r[0]), "case_master_id": r[1], "subject_kind": r[2],
                      "subject_ref_id": r[3], "label_name": r[4], "label_value": r[5],
                      "outcome_observation_id": r[6], "observation_cutoff": _s(r[7]),
                      "label_window_start": _s(r[8]), "label_window_end": _s(r[9]), "split_tag": r[10]}
                     for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "leakage_safe": leaks == 0,
            "splits": splits, "items": items}


# --- public write wrappers --------------------------------------------------
def create_request(model_version_id: int, feature_snapshot_id: int, request_kind: str,
                   idempotency_key: Optional[str], actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _create_request(conn, model_version_id, feature_snapshot_id, request_kind,
                               idempotency_key, actor)


def run_request(request_id: int, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _run_request(conn, request_id, actor)


def _emit_prediction_reviewed(out: dict) -> None:
    """Publish a data-minimized ``prediction.reviewed`` Signal AFTER the review
    transaction commits (Phase 15). Never carries the model output/explanation."""
    try:
        from ..signals import EVENT_PREDICTION_REVIEWED, get_signals
        get_signals().publish(EVENT_PREDICTION_REVIEWED, {
            "prediction_request_id": out.get("request_id"),
            "prediction_review_id": out.get("prediction_review_id"),
            "decision": out.get("decision"), "status": out.get("status")})
    except Exception:  # noqa: BLE001 — a Signal failure must not break the review
        pass


def review_result(result_id: int, decision: str, override_reason: Optional[str],
                  actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        out = _review_result(conn, result_id, decision, override_reason, actor)
    _emit_prediction_reviewed(out)
    return out


def review_request(request_id: int, decision: str, override_reason: Optional[str],
                   actor: Optional[str]) -> dict:
    """Review the CURRENT result of a request (the ergonomic UI path)."""
    with db.rw_conn() as conn:
        res = _current_result(conn, request_id)
        if res is None:
            raise NotFound(f"Request {request_id} has no result to review yet.")
        out = _review_result(conn, res["prediction_result_id"], decision, override_reason, actor)
    _emit_prediction_reviewed(out)
    return out


def invalidate_for_subject(subject_kind: str, subject_ref_id: str, reason: str,
                           actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _invalidate_for_subject(conn, subject_kind, subject_ref_id, reason, actor)


def rollback_model(model_version_id: int, to_model_version_id: Optional[int],
                   actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _rollback_model(conn, model_version_id, to_model_version_id, actor)
