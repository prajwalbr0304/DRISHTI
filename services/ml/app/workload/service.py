"""Orchestration + reads for the aggregate station-workload task (Phase 13).

Assembles the model card + task definition, serves the governed predictions and
the held-out evaluation for the UI, lists the registered model versions and
benchmark runs, and wraps the write paths (governed run, benchmark, lifecycle)
behind the same DB connection discipline as the rest of the service.

Aggregate area/period review-support only — never a person-level score.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from .. import db
from ..cases import analytics_policy
from ..intake.guards import hackathon_status
from . import benchmark as bench
from . import evaluation
from . import features as feat
from . import governance_bridge as gb

_WORKLOAD_MODEL_NAMES = (gb.WORKLOAD_MODEL_NAME, "drishti-workload-prior",
                         "drishti-workload-majority", "drishti-workload-xgboost",
                         "drishti-workload-histgbm", "drishti-workload-tabpfn",
                         "drishti-workload-incontext")

# short-lived in-process cache for the (fresh) held-out evaluation so a demo
# refresh does not re-hit the throttled DB repeatedly
_EVAL_CACHE: dict[str, Any] = {"key": None, "at": 0.0, "report": None}
_EVAL_TTL_S = 300


# ---------------------------------------------------------------------------
# Model card + task definition
# ---------------------------------------------------------------------------
def model_card(metrics: Optional[dict] = None) -> dict:
    return {
        "name": gb.WORKLOAD_MODEL_NAME,
        "version": gb.WORKLOAD_MODEL_VERSION,
        "task": feat.TASK,
        "task_type": "ordinal tabular classification (aggregate)",
        "owners": ["DRISHTI analytics (hackathon)"],
        "approved_use": [
            "Rank/triage police DISTRICTS by likely NEXT-QUARTER case-review workload "
            "band to support supervisory resource and review-queue planning.",
            "Aggregate, area/period decision support that a human supervisor reviews.",
        ],
        "prohibited_use": [
            "Any person-level scoring, targeting, arrest, detention, bail, guilt or "
            "individual criminal-justice decision.",
            "Treating a band as evidence of an offence or of any individual's risk.",
            "Operationalising the retired synthetic offender-risk score.",
        ],
        "subject": "police district",
        "prediction": {"bands": feat.BANDS, "kind": "ordinal band",
                       "horizon_months": feat.LABEL_HORIZON_MONTHS},
        "label_definition": (
            "Verified OUTCOME: the count of cases registered in the DISTRICT in the "
            "forward window (cutoff, cutoff + %d months], banded into ordinal "
            "quartiles whose thresholds are fit on the TRAIN split only. The label "
            "is disjoint from and independent of the input feature formula."
            % feat.LABEL_HORIZON_MONTHS),
        "features": [{"name": n, "label": feat.FEATURE_LABELS[n], "sensitivity": "normal"}
                     for n in feat.FEATURE_NAMES],
        "protected_attributes": {
            "used": False,
            "note": ("No caste, religion, gender, juvenile status, age or any "
                     "protected/proxy attribute enters the schema (enforced by the "
                     "governed FeatureDefinition sensitivity + a leakage/proxy check)."),
        },
        "feature_schema": f"{feat.SCHEMA_NAME} v{feat.SCHEMA_VERSION} (approved)",
        "data_splits": "Time split (earliest cutoffs train -> latest test) + a "
                       "held-out district (geographic) split.",
        "baselines": ["prior-period (this quarter's band)", "majority-class",
                      "gradient-boosted trees (XGBoost/HistGradientBoosting)"],
        "candidate_models": ["Google TabFM v1 (foundation)", "TabPFN v2 (foundation)",
                             "deterministic in-context stand-in (foundation fallback)"],
        "calibration": "Temperature scaling fit on the validation split; confidence "
                       "is the top-1 band probability.",
        "abstention": "Abstains on low confidence or insufficient station history; a "
                      "threshold-review sweep accompanies the evaluation.",
        "metrics": metrics or {},
        "limitations": gb._LIMITATIONS,
        "ethical_notes": [
            "Bands are uncertain and synthetic-data-derived; not operational truth.",
            "Every prediction is decision-support and requires human review.",
        ],
        "governance": "Registered ModelVersion bound to the approved feature schema + "
                      "a reproducible TrainingDatasetSnapshot; staged/shadow/active/"
                      "retired lifecycle; immutable FeatureSnapshot + PredictionResult "
                      "per station.",
    }


def task_definition() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "Status" FROM "FeatureSchemaVersion" '
                        'WHERE "SchemaName"=%s AND "Version"=%s',
                        (feat.SCHEMA_NAME, feat.SCHEMA_VERSION))
            r = cur.fetchone()
            approved = bool(r and r[0] == "approved")
            cur.execute(
                'SELECT fd."Name", fd."Description", fd."Sensitivity", fd."WindowSpec" '
                'FROM "FeatureSchemaVersion" fsv '
                'JOIN LATERAL jsonb_array_elements_text(fsv."FeatureDefinitionIDs") x(id) ON TRUE '
                'JOIN "FeatureDefinition" fd ON fd."FeatureDefinitionID" = x.id::bigint '
                'WHERE fsv."SchemaName"=%s AND fsv."Version"=%s ORDER BY fd."FeatureDefinitionID"',
                (feat.SCHEMA_NAME, feat.SCHEMA_VERSION))
            features = [{"name": n, "description": d, "sensitivity": s, "window": w}
                        for n, d, s, w in cur.fetchall()]
    env = hackathon_status().get("environment_label", "Synthetic Hackathon Demo")
    return {
        "task": feat.TASK, "schema_name": feat.SCHEMA_NAME, "schema_version": feat.SCHEMA_VERSION,
        "schema_approved": approved, "subject_kind": feat.SUBJECT_KIND, "bands": feat.BANDS,
        "label_definition": model_card()["label_definition"],
        "label_horizon_months": feat.LABEL_HORIZON_MONTHS,
        "aggregate_only": True, "not_person_level": True,
        "features": features or [{"name": n, "description": feat.FEATURE_LABELS[n],
                                  "sensitivity": "normal", "window": None} for n in feat.FEATURE_NAMES],
        "limitations": gb._LIMITATIONS, "model_card": model_card(), "environment_label": env,
    }


# ---------------------------------------------------------------------------
# Registry + predictions reads
# ---------------------------------------------------------------------------
def list_models() -> dict:
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT mv."ModelVersionID",mv."ModelName",mv."Version",mv."ModelType",'
                'mv."ApprovalStatus",mv."Status",mv."Environment",mv."FeatureSchemaVersionID",'
                'mv."TrainingDatasetSnapshotID",COALESCE(mv."EvaluationReport",\'{}\'::jsonb),'
                'mv."Hyperparameters",tds."Exclusions" '
                'FROM "ModelVersion" mv LEFT JOIN "TrainingDatasetSnapshot" tds '
                'ON tds."TrainingDatasetSnapshotID"=mv."TrainingDatasetSnapshotID" '
                'WHERE mv."ModelName"=ANY(%s) ORDER BY mv."ModelVersionID"',
                (list(_WORKLOAD_MODEL_NAMES),))
            rows = cur.fetchall()

        models_out = []
        main_rows = 0
        valid_main = 0
        for row in rows:
            if row[1] == gb.WORKLOAD_MODEL_NAME:
                main_rows += 1
                try:
                    analytics_policy.require_current(
                        conn, row[10], f"ModelVersion {row[0]}", current=current)
                    gb.require_workload_model_identity(
                        row[10], f"Workload ModelVersion {row[0]}")
                    analytics_policy.require_current(
                        conn, row[9], f"ModelVersion {row[0]} evaluation", current=current)
                    if row[8] is None or row[11] is None:
                        raise analytics_policy.DerivedArtifactUnavailable(
                            f"Workload ModelVersion {row[0]} has no training snapshot lineage.")
                    analytics_policy.require_current(
                        conn, row[11], f"TrainingDatasetSnapshot {row[8]}", current=current)
                except analytics_policy.DerivedArtifactUnavailable:
                    continue
                valid_main += 1
            models_out.append({
                "model_version_id": row[0], "model_name": row[1], "version": row[2],
                "model_type": row[3], "approval_status": row[4], "status": row[5],
                "environment": row[6], "feature_schema_version_id": row[7],
                "training_dataset_snapshot_id": row[8],
                "metrics": {key: value for key, value in (row[9] or {}).items()
                            if key not in {"held_out", analytics_policy.ATTESTATION_KEY}},
            })
        if main_rows and not valid_main:
            raise analytics_policy.DerivedArtifactUnavailable(
                "No workload model is attested to the current analytics policy; rerun the "
                "workload producer before serving model metadata.")
    served = next((model["model_version_id"] for model in models_out
                   if model["model_name"] == gb.WORKLOAD_MODEL_NAME
                   and model["status"] == "active"), None)
    if served is None:
        served = next((model["model_version_id"] for model in reversed(models_out)
                       if model["model_name"] == gb.WORKLOAD_MODEL_NAME), None)
    return {"models": models_out, "served_model_version_id": served}


def list_predictions(page: int = 1, page_size: int = 50,
                     include_stale: bool = False) -> dict:
    offset = (page - 1) * page_size
    stale_clause = "" if include_stale else 'AND pr."IsStale"=FALSE'
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        generation = analytics_policy.latest_complete_generation(
            conn, model_names=[gb.WORKLOAD_MODEL_NAME], ref_table="PredictionResult",
            artifact="workload predictions", scope={"task": feat.TASK}, current=current)
        served_model_version_id = generation["model_version_id"]
        with conn.cursor() as cur:
            cur.execute(
                'SELECT mv."Hyperparameters",mv."TrainingDatasetSnapshotID",'
                'tds."Exclusions",mv."ApprovalStatus",mv."Status" '
                'FROM "ModelVersion" mv LEFT JOIN "TrainingDatasetSnapshot" tds '
                'ON tds."TrainingDatasetSnapshotID"=mv."TrainingDatasetSnapshotID" '
                'WHERE mv."ModelVersionID"=%s', (served_model_version_id,))
            model_lineage = cur.fetchone()
        if (not model_lineage or model_lineage[1] is None or model_lineage[2] is None
                or model_lineage[3] != "approved" or model_lineage[4] == "retired"):
            raise analytics_policy.DerivedArtifactUnavailable(
                "The latest complete workload generation has no operational model/training lineage.")
        gb.require_workload_model_identity(
            model_lineage[0], f"Workload ModelVersion {served_model_version_id}")
        analytics_policy.require_current(
            conn, model_lineage[2], f"TrainingDatasetSnapshot {model_lineage[1]}",
            current=current)
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT count(*) FROM "PredictionResult" pr '
                f'JOIN "FeatureSnapshot" fs ON fs."FeatureSnapshotID"=pr."FeatureSnapshotID" '
                f'JOIN "ModelVersion" mv ON mv."ModelVersionID"=pr."ModelVersionID" '
                f'WHERE mv."ModelName"=%s AND pr."ModelVersionID"=%s '
                f'AND fs."SubjectKind"=%s {stale_clause}',
                (gb.WORKLOAD_MODEL_NAME, served_model_version_id, feat.SUBJECT_KIND))
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT pr."PredictionResultID",pr."PredictionRequestID",fs."SubjectRefID",'
                f'fs."ObservationCutoff",pr."OutputJSON",pr."Confidence",pr."IsStale",'
                f'pr."CreatedAt",mv."ModelName",mv."Version",fs."SourceVersions",'
                f'fs."QualityStatus",fs."SupersededByFeatureSnapshotID",mv."Hyperparameters",'
                f'mv."ApprovalStatus",mv."Status",mv."TrainingDatasetSnapshotID",'
                f'tds."Exclusions",pr."Explanation",pr."SupersededByResultID",'
                f'(pr."ExpiresAt" IS NULL OR pr."ExpiresAt">now()),'
                f'(req."ModelVersionID"=pr."ModelVersionID" AND '
                f' req."FeatureSnapshotID"=pr."FeatureSnapshotID") '
                f'FROM "PredictionResult" pr '
                f'JOIN "PredictionRequest" req ON req."PredictionRequestID"=pr."PredictionRequestID" '
                f'JOIN "FeatureSnapshot" fs ON fs."FeatureSnapshotID"=pr."FeatureSnapshotID" '
                f'JOIN "ModelVersion" mv ON mv."ModelVersionID"=pr."ModelVersionID" '
                f'LEFT JOIN "TrainingDatasetSnapshot" tds '
                f'ON tds."TrainingDatasetSnapshotID"=mv."TrainingDatasetSnapshotID" '
                f'WHERE mv."ModelName"=%s AND pr."ModelVersionID"=%s '
                f'AND fs."SubjectKind"=%s {stale_clause} '
                f'ORDER BY pr."Confidence" DESC NULLS LAST,pr."PredictionResultID" DESC '
                f'LIMIT %s OFFSET %s',
                (gb.WORKLOAD_MODEL_NAME, served_model_version_id, feat.SUBJECT_KIND,
                 page_size, offset))
            rows = cur.fetchall()

        for row in rows:
            result_id = row[0]
            analytics_policy.require_current(
                conn, row[10], f"FeatureSnapshot for PredictionResult {result_id}",
                current=current)
            analytics_policy.require_current(
                conn, row[13], f"ModelVersion for PredictionResult {result_id}",
                current=current)
            gb.require_workload_model_identity(
                row[13], f"Workload ModelVersion for PredictionResult {result_id}")
            if row[16] is None or row[17] is None:
                raise analytics_policy.DerivedArtifactUnavailable(
                    f"PredictionResult {result_id} has no workload training-snapshot lineage.")
            analytics_policy.require_current(
                conn, row[17], f"TrainingDatasetSnapshot {row[16]}", current=current)
            analytics_policy.require_current(
                conn, row[18], f"PredictionResult {result_id}", current=current)
            if not include_stale and (
                    row[11] == "stale" or row[12] is not None or row[19] is not None
                    or not row[20] or row[14] != "approved" or row[15] == "retired"
                    or not row[21]):
                raise analytics_policy.DerivedArtifactUnavailable(
                    f"PredictionResult {result_id} is not an operationally current, complete "
                    "workload result; regenerate the workload predictions.")

    predictions, cutoff_period = [], None
    for row in rows:
        output = row[4] or {}
        cutoff_period = cutoff_period or output.get("cutoff_period")
        predictions.append({
            "prediction_result_id": row[0], "prediction_request_id": row[1],
            "unit_id": row[2],
            "unit_name": output.get("district_name") or output.get("unit_name"),
            "district_id": output.get("district_id"),
            "observation_cutoff": row[3].isoformat() if row[3] else None,
            "workload_band": output.get("workload_band"),
            "band_ordinal": output.get("band_ordinal"),
            "band_probabilities": output.get("band_probabilities") or {},
            "confidence": float(row[5]) if row[5] is not None else None,
            "abstained": output.get("abstained"),
            "recent_case_volume": output.get("recent_case_volume"),
            "is_stale": bool(row[6]), "model_version": f"{row[8]}@{row[9]}",
            "created_at": row[7].isoformat() if row[7] else None,
            "actual_backend": output.get("actual_backend"),
            "actual_device": output.get("actual_device"), "gpu_name": output.get("gpu_name"),
            "served_via": output.get("served_via"),
            "model_artifact_digest": output.get("model_artifact_digest"),
        })
    return {"predictions": predictions, "total": total, "page": page,
            "page_size": page_size, "cutoff_period": cutoff_period,
            "aggregate_only": True, "limitations": gb._LIMITATIONS}


def list_benchmarks() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ModelName","ModelFamily","ScaleLabel","RowScale","Device","FitSeconds",'
                '"PredictSeconds","TotalSeconds","LatencyMsPerRow","ThroughputRowsPerSec","PeakRssMB",'
                '"GpuMemMB","Accuracy","MacroF1","QWK","ECE","CostEstimate","Available","Note","CreatedAt" '
                'FROM "ModelBenchmark" WHERE "Task"=%s ORDER BY "CreatedAt" DESC, "ModelBenchmarkID" DESC '
                'LIMIT 200', (feat.TASK,))
            rows = cur.fetchall()

    def f(x):
        return float(x) if x is not None else None
    benchmarks = [{
        "model_name": r[0], "family": r[1], "scale_label": r[2], "row_scale": int(r[3]),
        "device": r[4], "fit_seconds": f(r[5]), "predict_seconds": f(r[6]), "total_seconds": f(r[7]),
        "latency_ms_per_row": f(r[8]), "throughput_rows_per_sec": f(r[9]), "peak_rss_mb": f(r[10]),
        "gpu_mem_mb": f(r[11]), "accuracy": f(r[12]), "macro_f1": f(r[13]), "qwk": f(r[14]),
        "ece": f(r[15]), "cost_estimate": r[16] or {}, "available": bool(r[17]), "note": r[18],
        "created_at": r[19].isoformat() if r[19] else None} for r in rows]
    return {"benchmarks": benchmarks, "assumptions": bench.COST_ASSUMPTIONS}


# ---------------------------------------------------------------------------
# Held-out evaluation (fresh, deterministic, short-cached)
# ---------------------------------------------------------------------------
def _served_held_out() -> Optional[dict]:
    """Return only a held-out report with current model/training policy lineage."""
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT mv."ModelVersionID",mv."EvaluationReport",mv."Hyperparameters",'
                'mv."TrainingDatasetSnapshotID",tds."Exclusions" '
                'FROM "ModelVersion" mv LEFT JOIN "TrainingDatasetSnapshot" tds '
                'ON tds."TrainingDatasetSnapshotID"=mv."TrainingDatasetSnapshotID" '
                'WHERE mv."ModelName"=%s '
                'ORDER BY (mv."Status"=\'active\') DESC,mv."ModelVersionID" DESC',
                (gb.WORKLOAD_MODEL_NAME,))
            rows = cur.fetchall()
        for row in rows:
            try:
                analytics_policy.require_current(
                    conn, row[2], f"ModelVersion {row[0]}", current=current)
                gb.require_workload_model_identity(
                    row[2], f"Workload ModelVersion {row[0]}")
                analytics_policy.require_current(
                    conn, row[1], f"ModelVersion {row[0]} evaluation", current=current)
                if row[3] is None or row[4] is None:
                    raise analytics_policy.DerivedArtifactUnavailable(
                        f"ModelVersion {row[0]} has no training snapshot lineage.")
                analytics_policy.require_current(
                    conn, row[4], f"TrainingDatasetSnapshot {row[3]}", current=current)
            except analytics_policy.DerivedArtifactUnavailable:
                continue
            held_out = (row[1] or {}).get("held_out")
            if held_out:
                return held_out
    if rows:
        raise analytics_policy.DerivedArtifactUnavailable(
            "No stored workload evaluation has complete current policy, model-identity, and "
            "training lineage; rerun the workload producer.")
    raise analytics_policy.DerivedArtifactUnavailable(
        "No governed workload model/evaluation has been produced; run the workload producer "
        "before requesting the served evaluation.")


def evaluation_report(foundation_kind: str = "served", refresh: bool = False) -> dict:
    """Held-out evaluation. Default ("served") returns the report STORED by the
    last governed run (instant, no recompute). A specific foundation_kind, or
    refresh=True, recomputes (short-cached) — used for ad-hoc comparison."""
    served_requested = foundation_kind in ("served", "", None)
    if served_requested and not refresh:
        return _served_held_out()
    if served_requested:
        # Refresh is an explicit request for a fresh deterministic comparison,
        # not permission to disguise it as the persisted served report.
        foundation_kind = "incontext"
    key = foundation_kind
    now = time.time()
    if not refresh and _EVAL_CACHE["key"] == key and (now - _EVAL_CACHE["at"]) < _EVAL_TTL_S \
            and _EVAL_CACHE["report"] is not None:
        return _EVAL_CACHE["report"]
    with db.ro_conn() as conn:
        report = evaluation.evaluate(conn, foundation_kind=foundation_kind)
    _EVAL_CACHE.update(key=key, at=now, report=report)
    return report


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def run_governed(*, foundation_kind: str = "incontext", limit: Optional[int] = None,
                 lifecycle: str = "staged", actor: str = "workload-batch") -> dict:
    with db.rw_conn() as conn:
        result = gb.persist_predictions(conn, foundation_kind=foundation_kind, limit=limit,
                                        lifecycle=lifecycle, actor=actor)
    _EVAL_CACHE.update(key=None, at=0.0, report=None)  # data changed
    return result


def run_governed_sagemaker(*, context_limit: int = 512,
                           actor: str = "workload-sagemaker") -> dict:
    """Run the LIVE per-district workload band on the REAL AWS SageMaker TabFM
    (T4/CUDA) via the protected adapter and persist the governed result to RDS
    (the store the Workload UI reads). Long-running (SageMaker cold start + async
    poll); intended for a background task or an offline driver, never a
    gateway-bounded synchronous request."""
    with db.rw_conn() as conn:
        result = gb.persist_predictions_via_sagemaker(conn, context_limit=context_limit,
                                                      actor=actor)
    _EVAL_CACHE.update(key=None, at=0.0, report=None)  # served data changed
    return result


def run_benchmark_and_persist(*, include_heavy: Optional[bool] = None,
                              actor: str = "workload-benchmark") -> dict:
    with db.rw_conn() as conn:
        result = bench.run_benchmark(conn, include_heavy=include_heavy)
        mv = list_models_conn(conn)
        gb.persist_benchmark(conn, result["rows"], model_version_id=mv, actor=actor)
    return result


def list_models_conn(conn) -> Optional[int]:
    current = analytics_policy.current_attestation(conn)
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ModelVersionID","Hyperparameters" FROM "ModelVersion" '
            'WHERE "ModelName"=%s ORDER BY "ModelVersionID" DESC',
            (gb.WORKLOAD_MODEL_NAME,))
        rows = cur.fetchall()
    for model_version_id, hyperparameters in rows:
        try:
            analytics_policy.require_current(
                conn, hyperparameters, f"ModelVersion {model_version_id}", current=current)
            gb.require_workload_model_identity(
                hyperparameters, f"Workload ModelVersion {model_version_id}")
        except analytics_policy.DerivedArtifactUnavailable:
            continue
        return int(model_version_id)
    return None


def set_model_lifecycle(model_version_id: int, stage: str, actor: str = "workload-admin") -> dict:
    with db.rw_conn() as conn:
        return gb.set_lifecycle(conn, model_version_id, stage, actor=actor)
