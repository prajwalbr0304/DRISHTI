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
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ModelVersionID","ModelName","Version","ModelType","ApprovalStatus",'
                '"Status","Environment","FeatureSchemaVersionID","TrainingDatasetSnapshotID",'
                'COALESCE("EvaluationReport",\'{}\'::jsonb) '
                'FROM "ModelVersion" WHERE "ModelName"=ANY(%s) ORDER BY "ModelVersionID"',
                (list(_WORKLOAD_MODEL_NAMES),))
            rows = cur.fetchall()
    models = [{"model_version_id": r[0], "model_name": r[1], "version": r[2], "model_type": r[3],
               "approval_status": r[4], "status": r[5], "environment": r[6],
               "feature_schema_version_id": r[7], "training_dataset_snapshot_id": r[8],
               # drop the large stored held-out report from the registry payload
               "metrics": {k: v for k, v in (r[9] or {}).items() if k != "held_out"}}
              for r in rows]
    served = next((m["model_version_id"] for m in models
                   if m["model_name"] == gb.WORKLOAD_MODEL_NAME and m["status"] == "active"), None)
    if served is None:
        served = next((m["model_version_id"] for m in models
                       if m["model_name"] == gb.WORKLOAD_MODEL_NAME), None)
    return {"models": models, "served_model_version_id": served}


def list_predictions(page: int = 1, page_size: int = 50, include_stale: bool = False) -> dict:
    offset = (page - 1) * page_size
    stale_clause = "" if include_stale else "AND pr.\"IsStale\"=FALSE"
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT count(*) FROM "PredictionResult" pr '
                f'JOIN "FeatureSnapshot" fs ON fs."FeatureSnapshotID"=pr."FeatureSnapshotID" '
                f'JOIN "ModelVersion" mv ON mv."ModelVersionID"=pr."ModelVersionID" '
                f'WHERE mv."ModelName"=%s AND fs."SubjectKind"=%s {stale_clause}',
                (gb.WORKLOAD_MODEL_NAME, feat.SUBJECT_KIND))
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT pr."PredictionResultID", pr."PredictionRequestID", fs."SubjectRefID", '
                f'fs."ObservationCutoff", pr."OutputJSON", pr."Confidence", pr."IsStale", '
                f'pr."CreatedAt", mv."ModelName", mv."Version" '
                f'FROM "PredictionResult" pr '
                f'JOIN "FeatureSnapshot" fs ON fs."FeatureSnapshotID"=pr."FeatureSnapshotID" '
                f'JOIN "ModelVersion" mv ON mv."ModelVersionID"=pr."ModelVersionID" '
                f'WHERE mv."ModelName"=%s AND fs."SubjectKind"=%s {stale_clause} '
                f'ORDER BY pr."Confidence" DESC NULLS LAST, pr."PredictionResultID" DESC '
                f'LIMIT %s OFFSET %s',
                (gb.WORKLOAD_MODEL_NAME, feat.SUBJECT_KIND, page_size, offset))
            rows = cur.fetchall()
    preds, cutoff_period = [], None
    for r in rows:
        out = r[4] or {}
        cutoff_period = cutoff_period or out.get("cutoff_period")
        preds.append({
            "prediction_result_id": r[0], "prediction_request_id": r[1], "unit_id": r[2],
            "unit_name": out.get("district_name") or out.get("unit_name"),
            "district_id": out.get("district_id"),
            "observation_cutoff": r[3].isoformat() if r[3] else None,
            "workload_band": out.get("workload_band"), "band_ordinal": out.get("band_ordinal"),
            "band_probabilities": out.get("band_probabilities") or {},
            "confidence": float(r[5]) if r[5] is not None else None,
            "abstained": out.get("abstained"), "recent_case_volume": out.get("recent_case_volume"),
            "is_stale": bool(r[6]), "model_version": f"{r[8]}@{r[9]}",
            "created_at": r[7].isoformat() if r[7] else None})
    return {"predictions": preds, "total": total, "page": page, "page_size": page_size,
            "cutoff_period": cutoff_period, "aggregate_only": True, "limitations": gb._LIMITATIONS}


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
    """The full held-out report stored by the last governed run (served model)."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "EvaluationReport" FROM "ModelVersion" WHERE "ModelName"=%s '
                        'ORDER BY ("Status"=\'active\') DESC, "ModelVersionID" DESC LIMIT 1',
                        (gb.WORKLOAD_MODEL_NAME,))
            r = cur.fetchone()
    ev = (r[0] if r else None) or {}
    held = ev.get("held_out")
    return held if held else None


def evaluation_report(foundation_kind: str = "served", refresh: bool = False) -> dict:
    """Held-out evaluation. Default ("served") returns the report STORED by the
    last governed run (instant, no recompute). A specific foundation_kind, or
    refresh=True, recomputes (short-cached) — used for ad-hoc comparison."""
    if foundation_kind in ("served", "", None) and not refresh:
        stored = _served_held_out()
        if stored:
            return stored
        foundation_kind = "incontext"   # no stored report yet -> deterministic compute
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


def run_benchmark_and_persist(*, include_heavy: Optional[bool] = None,
                              actor: str = "workload-benchmark") -> dict:
    with db.rw_conn() as conn:
        result = bench.run_benchmark(conn, include_heavy=include_heavy)
        mv = list_models_conn(conn)
        gb.persist_benchmark(conn, result["rows"], model_version_id=mv, actor=actor)
    return result


def list_models_conn(conn) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "ModelVersionID" FROM "ModelVersion" WHERE "ModelName"=%s '
                    'ORDER BY "ModelVersionID" DESC LIMIT 1', (gb.WORKLOAD_MODEL_NAME,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def set_model_lifecycle(model_version_id: int, stage: str, actor: str = "workload-admin") -> dict:
    with db.rw_conn() as conn:
        return gb.set_lifecycle(conn, model_version_id, stage, actor=actor)
