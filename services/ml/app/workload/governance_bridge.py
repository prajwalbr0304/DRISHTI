"""Bridge the aggregate station-workload prediction into the governed contract.

Every model output must be reproducible from an IMMUTABLE ``FeatureSnapshot`` and
a governed ``PredictionResult`` bound to an APPROVED ``ModelVersion`` + feature
schema (Phase 10). This module does for the workload task exactly what
``forecast/governance_bridge`` does for the district forecast, plus the Phase-13
model-registry duties:

  * registers/looks up the approved ``drishti-tabfm-workload`` ModelVersion,
    binding it to the approved ``tabfm-workload-band`` schema + a reproducible
    ``TrainingDatasetSnapshot`` (time/geo splits, label windows, band thresholds,
    content hash), and drives its staged/shadow/active/retired lifecycle;
  * persists each station's band prediction as an immutable, hashed
    ``FeatureSnapshot`` (subject_kind ``area_unit``) + idempotent
    ``PredictionRequest`` + ``PredictionResult`` (band, confidence, abstention,
    explanation, limitations, expiry), superseding the station's prior snapshot;
  * records small/medium/full benchmark runs into ``ModelBenchmark``.

Aggregate area/period resource-planning support only — never a person-level
criminal-justice judgement. Nothing here operationalises the retired synthetic
individual offender-risk score.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
from psycopg2.extras import Json

from .. import audit, models
from ..cases import analytics_policy
from ..governance import builder
from . import evaluation
from . import features as feat
from . import models_iface as mi

WORKLOAD_MODEL_NAME = "drishti-tabfm-workload"
WORKLOAD_MODEL_VERSION = "1.0.0"
_RESULT_TTL_DAYS = 30
_LIFECYCLE = ("staged", "shadow", "active", "retired")
_LIMITATIONS = (
    "Aggregate DISTRICT case-review WORKLOAD band for resource planning and "
    "review-queue triage only. It projects how much case-review work a police "
    "district is likely to receive next quarter — it is NOT a person-level "
    "judgement, not evidence of an offence, and not a measure of any individual's "
    "risk. Bands are ordinal and uncertain; see the held-out evaluation for "
    "accuracy/calibration and baseline comparison. Requires human review before "
    "any operational use."
)


class WorkloadGovernanceError(Exception):
    pass


class WorkloadSchemaMissing(WorkloadGovernanceError):
    pass


# ---------------------------------------------------------------------------
# Approved schema + governed model + lifecycle
# ---------------------------------------------------------------------------
def workload_schema_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "FeatureSchemaVersionID","Status" FROM "FeatureSchemaVersion" '
                    'WHERE "SchemaName"=%s AND "Version"=%s',
                    (feat.SCHEMA_NAME, feat.SCHEMA_VERSION))
        r = cur.fetchone()
    if not r:
        raise WorkloadSchemaMissing(
            f"Approved schema {feat.SCHEMA_NAME} v{feat.SCHEMA_VERSION} not present — "
            "apply migration 020.")
    if r[1] != "approved":
        raise WorkloadSchemaMissing(
            f"Schema {feat.SCHEMA_NAME} v{feat.SCHEMA_VERSION} is '{r[1]}', not 'approved'.")
    return int(r[0])


def _training_snapshot_identity(conn, snapshot_id: Optional[int], attestation) -> str:
    if snapshot_id is None:
        raise analytics_policy.DerivedArtifactUnavailable(
            "A workload model requires immutable training-snapshot lineage.")
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ContentHash","Exclusions" FROM "TrainingDatasetSnapshot" '
            'WHERE "TrainingDatasetSnapshotID"=%s', (snapshot_id,))
        row = cur.fetchone()
    if not row or not row[0]:
        raise analytics_policy.DerivedArtifactUnavailable(
            f"TrainingDatasetSnapshot {snapshot_id} is missing or has no content identity.")
    analytics_policy.require_current(
        conn, row[1], f"TrainingDatasetSnapshot {snapshot_id}", current=attestation)
    return str(row[0])


def require_workload_model_identity(metadata, artifact: str = "workload model") -> dict:
    values = metadata if isinstance(metadata, dict) else {}
    identity = values.get("model_identity")
    digest = values.get("model_identity_sha256")
    if not isinstance(identity, dict) or not isinstance(digest, str):
        raise analytics_policy.ArtifactPolicyMismatch(
            f"{artifact} has no immutable workload model identity; regenerate it.")
    if builder._hash(identity) != digest:
        raise analytics_policy.ArtifactPolicyMismatch(
            f"{artifact} has inconsistent workload model identity metadata; regenerate it.")
    return identity


def ensure_workload_model(conn, feature_schema_version_id: int, *,
                          training_dataset_snapshot_id: Optional[int] = None,
                          metrics: Optional[dict] = None, backend: str = "incontext",
                          held_out_report: Optional[dict] = None,
                          model_config: Optional[dict] = None,
                          lifecycle: str = "staged", actor: Optional[str] = None,
                          policy_attestation=None) -> int:
    """Register an immutable policy-, training-, and backend-qualified model."""
    attestation = policy_attestation or analytics_policy.current_attestation(conn)
    analytics_policy.require_supplied_current(conn, attestation, "workload model")
    training_hash = _training_snapshot_identity(
        conn, training_dataset_snapshot_id, attestation)
    if lifecycle not in _LIFECYCLE:
        lifecycle = "staged"
    model_identity = {
        "release_version": WORKLOAD_MODEL_VERSION,
        "feature_schema_version_id": int(feature_schema_version_id),
        "training_dataset_snapshot_id": int(training_dataset_snapshot_id),
        "training_content_hash": training_hash,
        "served_backend": backend,
        "configuration": dict(model_config or {}),
    }
    identity_digest = builder._hash(model_identity)
    report_blob = analytics_policy.stamp(
        {"summary": metrics or {}, "phase13_backend": backend,
         "production_backend": "google-tabfm-v1 (GPU, Prompt 14)",
         "held_out": held_out_report or {}},
        attestation)
    hyperparameters = analytics_policy.stamp(
        {"task": feat.TASK, "bands": feat.BANDS,
         "production_candidate": "tabfm",
         "phase13_candidates": ["tabpfn", "incontext"],
         "baselines": ["prior_period", "majority", "gbm"],
         "served_backend": backend,
         "model_identity": model_identity,
         "model_identity_sha256": identity_digest},
        attestation)
    immutable_version = f"{WORKLOAD_MODEL_VERSION}+identity.{identity_digest[:16]}"
    mv_id = models.get_or_create_model_version(
        conn, WORKLOAD_MODEL_NAME, "classification",
        analytics_policy.policy_model_version(immutable_version, attestation),
        framework="tabfm-foundation", status=lifecycle,
        hyperparameters=hyperparameters, metrics=metrics or {})
    analytics_policy.require_model(conn, mv_id, "workload", current=attestation)
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "Hyperparameters","FeatureSchemaVersionID",'
            '"TrainingDatasetSnapshotID" FROM "ModelVersion" '
            'WHERE "ModelVersionID"=%s', (mv_id,))
        existing = cur.fetchone()
    if not existing:
        raise analytics_policy.DerivedArtifactUnavailable(
            f"Workload ModelVersion {mv_id} disappeared during registration.")
    existing_identity = require_workload_model_identity(
        existing[0], f"Workload ModelVersion {mv_id}")
    if existing_identity != model_identity:
        raise analytics_policy.ArtifactPolicyMismatch(
            f"Workload ModelVersion {mv_id} collides with different immutable inputs.")
    if existing[1] not in (None, feature_schema_version_id) or existing[2] not in (
            None, training_dataset_snapshot_id):
        raise analytics_policy.ArtifactPolicyMismatch(
            f"Workload ModelVersion {mv_id} has conflicting schema or training lineage.")
    with conn.cursor() as cur:
        if lifecycle == "active":
            cur.execute(
                'UPDATE "ModelVersion" SET "Status"=\'shadow\' '
                'WHERE "ModelName"=%s AND "ModelVersionID"<>%s AND "Status"=\'active\'',
                (WORKLOAD_MODEL_NAME, mv_id))
        cur.execute(
            'UPDATE "ModelVersion" SET "FeatureSchemaVersionID"=%s, '
            '"TrainingDatasetSnapshotID"=%s, '
            '"ApprovalStatus"=\'approved\', "ApprovedBy"=COALESCE("ApprovedBy",%s), '
            '"ApprovedAt"=COALESCE("ApprovedAt", now()), "Environment"=\'hackathon_demo\', '
            '"Status"=%s, "EvaluationReport"=%s WHERE "ModelVersionID"=%s',
            (feature_schema_version_id, training_dataset_snapshot_id,
             actor or "workload-bridge", lifecycle, Json(report_blob), mv_id))
    return mv_id


def set_lifecycle(conn, model_version_id: int, stage: str, actor: Optional[str] = None) -> dict:
    """Move a workload model version through staged/shadow/active/retired."""
    if stage not in _LIFECYCLE:
        raise WorkloadGovernanceError(f"unknown lifecycle stage '{stage}'")
    approval = "retired" if stage == "retired" else "shadow" if stage == "shadow" else "approved"
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "ModelVersion" WHERE "ModelVersionID"=%s', (model_version_id,))
        if cur.fetchone() is None:
            raise WorkloadGovernanceError(f"ModelVersion {model_version_id} not found")
        # a single active served model per name: demote any current active one
        if stage == "active":
            cur.execute('UPDATE "ModelVersion" SET "Status"=\'shadow\' '
                        'WHERE "ModelName"=%s AND "ModelVersionID"<>%s AND "Status"=\'active\'',
                        (WORKLOAD_MODEL_NAME, model_version_id))
        cur.execute('UPDATE "ModelVersion" SET "Status"=%s, "ApprovalStatus"=%s WHERE "ModelVersionID"=%s',
                    (stage, approval, model_version_id))
    audit.record(audit.Action.MODEL_RUN, "workload_lifecycle", model_version_id, actor=actor,
                 conn=conn, detail={"stage": stage, "approval": approval})
    return {"model_version_id": model_version_id, "status": stage, "approval_status": approval}


# ---------------------------------------------------------------------------
# Reproducible training dataset snapshot (time/geo splits + label windows)
# ---------------------------------------------------------------------------
def register_training_snapshot(conn, ds, *, feature_schema_version_id: int,
                               actor: Optional[str] = None,
                               policy_attestation=None) -> int:
    """Persist/reuse an attested workload TrainingDatasetSnapshot."""
    attestation = policy_attestation or analytics_policy.current_attestation(conn)
    analytics_policy.require_supplied_current(conn, attestation, "workload training snapshot")
    meta = ds.meta
    time_split = {"train": meta["train_cutoffs"], "val": meta["val_cutoffs"],
                  "test": meta["test_cutoffs"], "unit": "quarterly_cutoff"}
    geo_split = {"holdout_fraction": meta["geo_holdout_fraction"],
                 "holdout_districts": ds.holdout_districts,
                 "method": "every_kth_sorted_district"}
    dataset_content_hash = builder._hash({
        "feature_names": list(ds.feature_names),
        "features": np.asarray(ds.X, dtype=float).tolist(),
        "band_labels": np.asarray(ds.y, dtype=int).tolist(),
        "label_counts": np.asarray(ds.label_count, dtype=float).tolist(),
        "unit_ids": np.asarray(ds.unit_ids, dtype=int).tolist(),
        "district_ids": np.asarray(ds.district_ids, dtype=int).tolist(),
        "cutoff_periods": np.asarray(ds.cutoff_periods).tolist(),
        "split_tags": np.asarray(ds.split_tags).tolist(),
        "geo_holdout": np.asarray(ds.geo_holdout, dtype=bool).tolist(),
        "meta": meta,
    })
    exclusions = analytics_policy.stamp(
        {"valid_geography_only": meta["valid_geography"],
         "band_thresholds": ds.thresholds, "bands": ds.bands,
         "dataset_content_sha256": dataset_content_hash},
        attestation)
    content_hash = builder._hash({
        "schema": feature_schema_version_id,
        "time": time_split,
        "geo": geo_split,
        "rows": meta["n_rows"],
        "thresholds": ds.thresholds,
        "axis": [meta["axis_first"], meta["axis_last"]],
        "dataset_content_sha256": dataset_content_hash,
        "exclusions": exclusions,
    })
    name = f"{feat.SCHEMA_NAME}-train"
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "TrainingDatasetSnapshotID","Exclusions" '
            'FROM "TrainingDatasetSnapshot" WHERE "Name"=%s AND "ContentHash"=%s',
            (name, content_hash))
        row = cur.fetchone()
        if row:
            analytics_policy.require_current(
                conn, row[1], f"TrainingDatasetSnapshot {row[0]}", current=attestation)
            return int(row[0])
        cutoff_dt = feat._period_end_dt(meta["cutoffs"][-1])
        label_start = (feat._period_end_dt(meta["test_cutoffs"][0])
                       if meta["test_cutoffs"] else cutoff_dt)
        label_end = feat._period_end_dt(meta["axis_last"])
        cur.execute(
            'INSERT INTO "TrainingDatasetSnapshot" ("Name","FeatureSchemaVersionID","TimeSplit",'
            '"GeoSplit","RowCount","ObservationCutoff","LabelWindowStart","LabelWindowEnd",'
            '"Exclusions","ApprovalStatus","ContentHash") '
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',%s) RETURNING \"TrainingDatasetSnapshotID\"",
            (name, feature_schema_version_id, Json(time_split), Json(geo_split), meta["n_rows"],
             cutoff_dt, label_start, label_end, Json(exclusions), content_hash))
        snapshot_id = int(cur.fetchone()[0])
    audit.record(audit.Action.MODEL_RUN, "training_dataset_snapshot", snapshot_id, actor=actor,
                 conn=conn, detail={"rows": meta["n_rows"],
                                    "schema": feature_schema_version_id})
    return snapshot_id


# ---------------------------------------------------------------------------
# Immutable per-station feature snapshot (idempotent + supersession)
# ---------------------------------------------------------------------------
def _find_live_snapshot(conn, schema_id: int, subject_ref_id: str, content_hash: str,
                        policy_attestation) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSnapshotID","SourceVersions" FROM "FeatureSnapshot" '
            'WHERE "FeatureSchemaVersionID"=%s AND "SubjectKind"=%s AND "SubjectRefID"=%s '
            "AND \"ContentHash\"=%s AND \"SupersededByFeatureSnapshotID\" IS NULL "
            "AND \"QualityStatus\" <> 'stale' ORDER BY \"FeatureSnapshotID\" DESC LIMIT 1",
            (schema_id, feat.SUBJECT_KIND, subject_ref_id, content_hash))
        row = cur.fetchone()
    if not row:
        return None
    analytics_policy.require_current(
        conn, row[1], f"FeatureSnapshot {row[0]}", current=policy_attestation)
    return int(row[0])


def _supersede_prior(conn, schema_id: int, subject_ref_id: str, new_id: int,
                     actor: Optional[str]) -> int:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSnapshotID" FROM "FeatureSnapshot" '
            'WHERE "FeatureSchemaVersionID"=%s AND "SubjectKind"=%s AND "SubjectRefID"=%s '
            'AND "FeatureSnapshotID"<>%s AND "SupersededByFeatureSnapshotID" IS NULL',
            (schema_id, feat.SUBJECT_KIND, subject_ref_id, new_id))
        prior = [int(r[0]) for r in cur.fetchall()]
        for sid in prior:
            cur.execute('UPDATE "FeatureSnapshot" SET "SupersededByFeatureSnapshotID"=%s, '
                        '"SupersededAt"=now(), "StaleReason"=%s WHERE "FeatureSnapshotID"=%s',
                        (new_id, "superseded by newer workload snapshot", sid))
            cur.execute("UPDATE \"PredictionResult\" SET \"IsStale\"=TRUE, \"StaleReason\"=%s, "
                        '"StaleAt"=now() WHERE "FeatureSnapshotID"=%s AND "IsStale"=FALSE',
                        ("superseded workload snapshot", sid))
            cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='superseded' "
                        "WHERE \"FeatureSnapshotID\"=%s AND \"Status\" IN ('queued','running','completed')",
                        (sid,))
    return len(prior)


def _stale_missing_snapshots(conn, schema_id: int, current_snapshot_ids: set[int]) -> int:
    """Retire workload snapshots/results omitted by a complete or zero run."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSnapshotID" FROM "FeatureSnapshot" '
            'WHERE "FeatureSchemaVersionID"=%s AND "SubjectKind"=%s '
            'AND "SupersededByFeatureSnapshotID" IS NULL AND "QualityStatus"<>\'stale\'',
            (schema_id, feat.SUBJECT_KIND))
        stale_ids = [int(row[0]) for row in cur.fetchall()
                     if int(row[0]) not in current_snapshot_ids]
        if not stale_ids:
            return 0
        reason = "absent from current workload generation"
        cur.execute(
            'UPDATE "FeatureSnapshot" SET "QualityStatus"=\'stale\',"StaleReason"=%s,'
            '"SupersededAt"=now() WHERE "FeatureSnapshotID"=ANY(%s)',
            (reason, stale_ids))
        cur.execute(
            'UPDATE "PredictionResult" SET "IsStale"=TRUE,"StaleReason"=%s,"StaleAt"=now() '
            'WHERE "FeatureSnapshotID"=ANY(%s) AND "IsStale"=FALSE',
            (reason, stale_ids))
        cur.execute(
            'UPDATE "PredictionRequest" SET "Status"=\'stale\' '
            'WHERE "FeatureSnapshotID"=ANY(%s) '
            'AND "Status" IN (\'queued\',\'running\',\'completed\')',
            (stale_ids,))
    return len(stale_ids)


def build_workload_snapshot(conn, *, schema_id: int, unit_id: int, cutoff: dt.datetime,
                            values: dict, source_versions: dict, actor: Optional[str] = None,
                            policy_attestation=None) -> dict:
    attestation = policy_attestation or analytics_policy.current_attestation(conn)
    analytics_policy.require_supplied_current(conn, attestation, "workload feature snapshot")
    schema = builder._load_schema(conn, schema_id)
    if schema["status"] != "approved":
        raise builder.SchemaNotApproved(f"schema {schema_id} not approved.")
    definitions = builder._load_definitions(conn, schema["feature_definition_ids"])
    builder.assert_no_protected_features(schema["task"], definitions)

    names = [d["name"] for d in definitions]
    vals, unknown = {}, []
    for name in names:
        if name in values and values[name] is not None:
            vals[name] = values[name]
        else:
            vals[name] = None
            unknown.append(name)
    quality = "partial" if unknown else "ok"
    subject_ref = str(unit_id)
    attested_sources = analytics_policy.stamp(source_versions, attestation)
    content_hash = builder._hash({
        "schema": schema_id,
        "subject": [feat.SUBJECT_KIND, subject_ref],
        "cutoff": builder._iso(cutoff),
        "values": vals,
        "source_versions": attested_sources,
    })
    existing = _find_live_snapshot(
        conn, schema_id, subject_ref, content_hash, attestation)
    if existing is not None:
        return {"feature_snapshot_id": existing, "reused": True,
                "quality_status": quality, "content_hash": content_hash,
                "superseded_prior": 0}
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "FeatureSnapshot" ("FeatureSchemaVersionID","SubjectKind","SubjectRefID",'
            '"ObservationCutoff","Values","SourceVersions","QualityStatus","ContentHash",'
            '"IsImmutable","BuiltByActor") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) '
            'RETURNING "FeatureSnapshotID"',
            (schema_id, feat.SUBJECT_KIND, subject_ref, cutoff, Json(vals), Json(attested_sources),
             quality, content_hash, actor))
        snapshot_id = int(cur.fetchone()[0])
    superseded = _supersede_prior(conn, schema_id, subject_ref, snapshot_id, actor)
    return {"feature_snapshot_id": snapshot_id, "reused": False,
            "quality_status": quality, "content_hash": content_hash,
            "superseded_prior": superseded}


# ---------------------------------------------------------------------------
# Governed request + result
# ---------------------------------------------------------------------------
def _get_or_create_request(conn, model_version_id: int, feature_snapshot_id: int,
                           actor: Optional[str], policy_attestation) -> tuple[int, bool]:
    idem = (f"workload:{feat.SUBJECT_KIND}:{feature_snapshot_id}:"
            f"model:{model_version_id}:{policy_attestation.sha256}")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "PredictionRequest" ("ModelVersionID","FeatureSnapshotID","RequestKind",'
            '"IdempotencyKey","Status","RequestedByActor") VALUES (%s,%s,\'batch\',%s,\'queued\',%s) '
            'ON CONFLICT ("IdempotencyKey") DO NOTHING RETURNING "PredictionRequestID"',
            (model_version_id, feature_snapshot_id, idem, actor))
        r = cur.fetchone()
        if r:
            return int(r[0]), True
        cur.execute(
            'SELECT "PredictionRequestID","ModelVersionID","FeatureSnapshotID" '
            'FROM "PredictionRequest" WHERE "IdempotencyKey"=%s', (idem,))
        existing = cur.fetchone()
    if not existing or int(existing[1]) != int(model_version_id) or int(existing[2]) != int(
            feature_snapshot_id):
        raise analytics_policy.ArtifactPolicyMismatch(
            "Workload request idempotency key collides with different immutable lineage.")
    return int(existing[0]), False


def _write_result(conn, request_id: int, model_version_id: int, feature_snapshot_id: int,
                  *, output: dict, explanation: dict, confidence: float) -> tuple[int, bool]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "PredictionResultID" FROM "PredictionResult" '
            'WHERE "PredictionRequestID"=%s AND "ModelVersionID"=%s '
            'AND "FeatureSnapshotID"=%s AND "SupersededByResultID" IS NULL '
            'AND "IsStale"=FALSE AND ("ExpiresAt" IS NULL OR "ExpiresAt">now()) '
            'ORDER BY "PredictionResultID" DESC LIMIT 1',
            (request_id, model_version_id, feature_snapshot_id))
        r = cur.fetchone()
        if r:
            return int(r[0]), False
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_RESULT_TTL_DAYS)
        cur.execute(
            'INSERT INTO "PredictionResult" ("PredictionRequestID","ModelVersionID",'
            '"FeatureSnapshotID","OutputJSON","Explanation","Limitations","Confidence","ExpiresAt") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "PredictionResultID"',
            (request_id, model_version_id, feature_snapshot_id, Json(output), Json(explanation),
             _LIMITATIONS, round(float(confidence), 5), expires))
        res_id = int(cur.fetchone()[0])
        cur.execute(
            'UPDATE "PredictionResult" SET "IsStale"=TRUE,"StaleReason"=%s,'
            '"StaleAt"=now(),"SupersededByResultID"=%s '
            'WHERE "PredictionRequestID"=%s AND "PredictionResultID"<>%s '
            'AND "SupersededByResultID" IS NULL',
            ("superseded by regenerated workload result", res_id, request_id, res_id))
        cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='completed' "
                    "WHERE \"PredictionRequestID\"=%s AND \"Status\" IN ('queued','running')",
                    (request_id,))
    return res_id, True


# ---------------------------------------------------------------------------
# Public: persist a full governed workload run
# ---------------------------------------------------------------------------
def persist_predictions(conn, *, foundation_kind: str = "incontext", limit: Optional[int] = None,
                        abstain_confidence: float = evaluation.DEFAULT_ABSTAIN_CONFIDENCE,
                        min_history_months: float = evaluation.DEFAULT_MIN_HISTORY_MONTHS,
                        lifecycle: str = "staged", actor: str = "workload-batch") -> dict:
    """Persist a policy-attested workload generation, including valid zero runs."""
    attestation = analytics_policy.current_attestation(conn)
    schema_id = workload_schema_id(conn)
    dataset = feat.build_dataset(conn)
    report = evaluation.evaluate_dataset(
        dataset, foundation_kind=foundation_kind,
        abstain_confidence=abstain_confidence,
        min_history_months=min_history_months)
    metrics = evaluation.summarize(report)
    training_snapshot_id = register_training_snapshot(
        conn, dataset, feature_schema_version_id=schema_id, actor=actor,
        policy_attestation=attestation)

    model, backend = evaluation._resolve_model(foundation_kind, dataset.n_bands, None)
    model.fit(dataset.X, dataset.y)
    validation_mask = dataset.mask("val")
    temperature = (evaluation._fit_temperature(
        model.predict_proba(dataset.X[validation_mask]), dataset.y[validation_mask])
        if validation_mask.any() else 1.0)

    model_config = {
        "requested_foundation": foundation_kind,
        "resolved_model_class": type(model).__name__,
        "temperature": round(float(temperature), 12),
        "abstain_confidence": float(abstain_confidence),
        "min_history_months": float(min_history_months),
        "n_bands": int(dataset.n_bands),
    }
    model_version_id = ensure_workload_model(
        conn, schema_id, training_dataset_snapshot_id=training_snapshot_id,
        metrics={**metrics, "backend": backend}, backend=backend,
        held_out_report=report, model_config=model_config, lifecycle=lifecycle,
        actor=actor, policy_attestation=attestation)

    live = feat.build_live_features(conn)
    cutoff = feat._period_end_dt(live["cutoff_period"])
    rows = live["rows"][:limit] if limit else live["rows"]
    if rows:
        vectors = np.asarray([row["vector"] for row in rows], dtype=float)
        probabilities = evaluation._apply_temperature(
            model.predict_proba(vectors), temperature)
    else:
        probabilities = np.zeros((0, dataset.n_bands))

    source_base = {
        "canonical_layer": "CaseVersion", "throughput_layer": "ChargesheetDetails",
        "as_of": cutoff.isoformat(), "feature_schema_version_id": schema_id,
        "task": feat.TASK, "backend": backend, "temperature": temperature,
    }
    snapshots = requests = results = reused = superseded = 0
    current_snapshot_ids: set[int] = set()
    history_index = feat.FEATURE_NAMES.index("wl_history_months")
    for index, row in enumerate(rows):
        probability = probabilities[index]
        band = int(probability.argmax())
        confidence = float(probability.max())
        history = float(row["vector"][history_index])
        abstain = bool(confidence < abstain_confidence or history < min_history_months)
        sources = {**source_base, "unit_id": row["unit_id"],
                   "district_id": row["district_id"]}
        snapshot = build_workload_snapshot(
            conn, schema_id=schema_id, unit_id=row["unit_id"], cutoff=cutoff,
            values=row["features"], source_versions=sources, actor=actor,
            policy_attestation=attestation)
        snapshot_id = snapshot["feature_snapshot_id"]
        current_snapshot_ids.add(snapshot_id)
        snapshots += 0 if snapshot["reused"] else 1
        reused += 1 if snapshot["reused"] else 0
        superseded += snapshot.get("superseded_prior", 0)
        request_id, created_request = _get_or_create_request(
            conn, model_version_id, snapshot_id, actor, attestation)
        requests += 1 if created_request else 0
        output = {
            "workload_band": dataset.bands[band], "band_ordinal": band,
            "band_probabilities": {dataset.bands[b]: round(float(probability[b]), 4)
                                   for b in range(dataset.n_bands)},
            "abstained": abstain, "cutoff_period": live["cutoff_period"],
            "recent_case_volume": row["features"]["wl_recent_case_volume"],
            "aggregate_subject": "police_district", "district_id": row["district_id"],
            "district_name": row["unit_name"],
        }
        explanation = analytics_policy.stamp(
            {"method": f"TabFM aggregate workload classifier ({backend} backend); "
                       "temperature-calibrated; ordinal band from pre-cutoff station "
                       "volume/trend/seasonality/throughput features",
             "top_features": ["wl_recent_case_volume", "wl_trailing_year_volume",
                              "wl_prioryear_same_quarter", "wl_trend_slope"],
             "aggregate_only": True, "not_person_level": True,
             "evaluation": metrics},
            attestation)
        _result_id, created_result = _write_result(
            conn, request_id, model_version_id, snapshot_id, output=output,
            explanation=explanation, confidence=confidence)
        results += 1 if created_result else 0

    complete_generation = limit is None
    analytics_policy.require_supplied_current(conn, attestation, "workload prediction run")
    if complete_generation:
        superseded += _stale_missing_snapshots(conn, schema_id, current_snapshot_ids)
    models.log_inference(
        conn, model_version_id, ref_table="PredictionResult",
        inputs=analytics_policy.stamp(
            {"task": feat.TASK, "feature_schema_version_id": schema_id,
             "cutoff_period": live["cutoff_period"], "limit": limit}, attestation),
        outputs={"stations": len(rows), "results": results,
                 "complete_generation": complete_generation})
    audit.record(audit.Action.MODEL_RUN, "workload_governed", model_version_id,
                 actor=actor, conn=conn,
                 detail={"model_version_id": model_version_id,
                         "feature_schema_version_id": schema_id,
                         "training_dataset_snapshot_id": training_snapshot_id,
                         "stations": len(rows), "snapshots_new": snapshots,
                         "results_new": results, "backend": backend,
                         "complete_generation": complete_generation})
    return {"model_version_id": model_version_id, "feature_schema_version_id": schema_id,
            "training_dataset_snapshot_id": training_snapshot_id, "backend": backend,
            "cutoff": live["cutoff_period"], "stations": len(rows),
            "snapshots_new": snapshots, "snapshots_reused": reused,
            "requests_new": requests, "results_new": results,
            "superseded_prior": superseded, "metrics": metrics}


# ---------------------------------------------------------------------------
# Benchmark persistence
# ---------------------------------------------------------------------------
def persist_benchmark(conn, benchmark_rows: list[dict], *, model_version_id: Optional[int] = None,
                      actor: str = "workload-benchmark") -> int:
    """Persist small/medium/full benchmark rows into ModelBenchmark."""
    n = 0
    with conn.cursor() as cur:
        for b in benchmark_rows:
            cur.execute(
                'INSERT INTO "ModelBenchmark" ("ModelVersionID","ModelName","ModelFamily","Task",'
                '"RowScale","ScaleLabel","Device","FitSeconds","PredictSeconds","TotalSeconds",'
                '"LatencyMsPerRow","ThroughputRowsPerSec","PeakRssMB","GpuMemMB","Accuracy",'
                '"MacroF1","QWK","ECE","CostEstimate","Metrics","Available","Note","Actor") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (model_version_id, b.get("model_name"), b.get("family"), feat.TASK,
                 b.get("row_scale"), b.get("scale_label"), b.get("device"), b.get("fit_seconds"),
                 b.get("predict_seconds"), b.get("total_seconds"), b.get("latency_ms_per_row"),
                 b.get("throughput_rows_per_sec"), b.get("peak_rss_mb"), b.get("gpu_mem_mb"),
                 b.get("accuracy"), b.get("macro_f1"), b.get("qwk"), b.get("ece"),
                 Json(b.get("cost_estimate") or {}), Json(b.get("metrics") or {}),
                 b.get("available", True), b.get("note"), actor))
            n += 1
    audit.record(audit.Action.MODEL_RUN, "workload_benchmark", model_version_id, actor=actor,
                 conn=conn, detail={"rows": n})
    return n


# ---------------------------------------------------------------------------
# Public: persist a LIVE workload run computed on the REAL AWS SageMaker TabFM
# ---------------------------------------------------------------------------
def persist_predictions_via_sagemaker(conn, *, context_limit: int = 512,
                                      poll_timeout_s: int = 420, poll_interval_s: int = 6,
                                      actor: str = "workload-sagemaker") -> dict:
    """Run the LIVE per-district workload band on the REAL Google TabFM on AWS
    SageMaker (T4/CUDA) through the protected adapter, then persist the governed
    result into the RDS ``PredictionResult`` the Workload UI reads.

    Reuses the proven ``PredictionRuntime`` + ``SignedHttpsAdapter`` so the
    fail-closed guarantee holds: a ``tabfm`` request that comes back as any
    fallback is REJECTED by ``validate_result`` and nothing is persisted (never a
    CPU fallback mislabelled as TabFM). The runtime's own Data-Store writes go to a
    throwaway in-memory store; only the validated result is persisted here to RDS.

    Requires ``DRISHTI_AWS_ADAPTER_URL`` / ``DRISHTI_AWS_ADAPTER_SECRET`` and a live
    SageMaker endpoint. Aggregate DISTRICT support only — never a person-level score.
    """
    import time

    import numpy as np

    from ..datastore.repository import InMemoryDataStore
    from ..predict.adapter import SignedHttpsAdapter
    from ..predict.envelope import BackendKind, ColumnDef, ModelTask
    from ..predict.routing import InputEvent, RoutingContext
    from ..predict.runtime import PredictionJobInput, PredictionRuntime

    attestation = analytics_policy.current_attestation(conn)
    schema_id = workload_schema_id(conn)
    ds = feat.build_dataset(conn)
    training_snapshot_id = register_training_snapshot(
        conn, ds, feature_schema_version_id=schema_id, actor=actor,
        policy_attestation=attestation)

    # Labelled in-context examples for TabFM (deterministic subsample to a context
    # budget so the crossing payload stays bounded). All rows are historical.
    ctx_X, ctx_y = ds.X, ds.y
    if len(ctx_X) > context_limit:
        idx = np.random.default_rng(42).choice(len(ctx_X), size=context_limit, replace=False)
        ctx_X, ctx_y = ctx_X[idx], ctx_y[idx]
    context_x = [[round(float(v), 6) for v in row] for row in ctx_X]
    context_y = [int(v) for v in ctx_y]
    context_digest = builder._hash({
        "feature_names": list(feat.FEATURE_NAMES),
        "context_x": context_x,
        "context_y": context_y,
        "context_limit": int(context_limit),
    })

    live = feat.build_live_features(conn)
    rows = live["rows"]
    cutoff_dt = feat._period_end_dt(live["cutoff_period"])
    if not rows:
        zero_metrics = {"backend": "tabfm", "served_via": "not_dispatched_zero_rows"}
        model_version_id = ensure_workload_model(
            conn, schema_id, training_dataset_snapshot_id=training_snapshot_id,
            metrics=zero_metrics, backend="google-tabfm-v1 (not dispatched)",
            model_config={"dispatch": "not_dispatched_zero_rows",
                          "context_sha256": context_digest,
                          "context_limit": int(context_limit),
                          "n_bands": int(ds.n_bands)},
            lifecycle="active", actor=actor, policy_attestation=attestation)
        superseded = _stale_missing_snapshots(conn, schema_id, set())
        analytics_policy.require_supplied_current(
            conn, attestation, "SageMaker workload zero run")
        models.log_inference(
            conn, model_version_id, ref_table="PredictionResult",
            inputs=analytics_policy.stamp(
                {"task": feat.TASK, "feature_schema_version_id": schema_id,
                 "cutoff_period": live["cutoff_period"], "dispatch": "sagemaker_async"},
                attestation),
            outputs={"stations": 0, "results": 0, "complete_generation": True})
        audit.record(
            audit.Action.MODEL_RUN, "workload_sagemaker", model_version_id,
            actor=actor, conn=conn,
            detail={"model_version_id": model_version_id, "districts": 0,
                    "results_new": 0, "complete_generation": True})
        return {"model_version_id": model_version_id,
                "feature_schema_version_id": schema_id,
                "training_dataset_snapshot_id": training_snapshot_id,
                "backend": "google-tabfm-v1", "cutoff": live["cutoff_period"],
                "districts": 0, "snapshots_new": 0, "snapshots_reused": 0,
                "requests_new": 0, "results_new": 0,
                "superseded_prior": superseded, "metrics": zero_metrics}
    query_rows = [[round(float(v), 6) for v in r["vector"]] for r in rows]

    columns = [ColumnDef(name=n) for n in feat.FEATURE_NAMES]
    query_digest = builder._hash({
        "subject_ids": [str(r["district_id"]) for r in rows],
        "query_rows": query_rows,
        "cutoff_period": live["cutoff_period"],
    })
    svh = builder._hash({
        "feature_schema_version": feat.SCHEMA_VERSION,
        "training_dataset_snapshot_id": training_snapshot_id,
        "context_sha256": context_digest,
        "query_sha256": query_digest,
        "policy_version": attestation.version,
        "policy_sha256": attestation.sha256,
    })

    job = PredictionJobInput(
        routing_ctx=RoutingContext(event=InputEvent.FIR_APPROVED, subject_kind=feat.SUBJECT_KIND,
                                   has_verified_geography=True, has_verified_time=True,
                                   has_verified_head=True),
        task=ModelTask.STATION_WORKLOAD_BAND, requested_backend=BackendKind.TABFM,
        subject_kind=feat.SUBJECT_KIND, subject_ids=[str(r["district_id"]) for r in rows],
        columns=columns, query_rows=query_rows,
        feature_schema_version=feat.SCHEMA_VERSION,
        model_version=analytics_policy.policy_model_version(
            WORKLOAD_MODEL_VERSION, attestation),
        feature_schema_digest=f"wl-schema-{schema_id}", observation_cutoff=live["cutoff"],
        source_version_hash=svh, context_x=context_x, context_y=context_y,
        output_schema={"n_bands": ds.n_bands})

    runtime = PredictionRuntime(adapter=SignedHttpsAdapter(), repository=InMemoryDataStore())
    handle = runtime.submit(job)                              # signed dispatch to real SageMaker
    terminal = {"completed", "failed", "rejected", "timed_out", "cancelled"}
    deadline = time.time() + poll_timeout_s
    result = None
    while time.time() < deadline:
        result = runtime.collect(handle)
        if result.state in terminal:
            break
        time.sleep(poll_interval_s)
    if result is None or result.state != "completed" or not result.result:
        raise WorkloadGovernanceError(
            "SageMaker TabFM workload run did not complete: "
            f"state={getattr(result, 'state', None)} "
            f"reason={getattr(result, 'rejected_reason', None)}")

    res = result.result                                      # validated PredictionResultEnvelope
    device = getattr(res.actual_device, "value", str(res.actual_device))
    gpu = res.gpu_name
    digest = res.model_artifact_digest
    if not isinstance(digest, str) or not digest.strip():
        raise WorkloadGovernanceError(
            "SageMaker TabFM result has no immutable model-artifact digest.")
    preds = res.predictions or []
    if len(preds) != len(rows):
        raise WorkloadGovernanceError(
            f"SageMaker returned {len(preds)} predictions for {len(rows)} workload subjects; "
            "refusing a partial persisted generation.")
    backend_label = f"google-tabfm-v1 ({device}/{gpu})"

    # Revalidate after the long remote inference before any database artifact is stamped.
    analytics_policy.require_supplied_current(conn, attestation, "SageMaker workload run")
    metrics = {"backend": "tabfm", "actual_device": device, "gpu_name": gpu,
               "model_artifact_digest": digest, "served_via": "aws_sagemaker_async_t4",
               "adapter_request_id": res.request_id, "runtime_ms": res.runtime_ms,
               "cold_start_ms": res.cold_start_ms, "peak_gpu_mem_mb": res.peak_gpu_mem_mb}
    mv_id = ensure_workload_model(
        conn, schema_id, training_dataset_snapshot_id=training_snapshot_id,
        metrics=metrics, backend=backend_label,
        model_config={"dispatch": "sagemaker_async",
                      "model_artifact_digest": digest,
                      "context_sha256": context_digest,
                      "context_limit": int(context_limit),
                      "n_bands": int(ds.n_bands)},
        lifecycle="active", actor=actor, policy_attestation=attestation)

    src_base = {"canonical_layer": "CaseVersion", "throughput_layer": "ChargesheetDetails",
                "as_of": cutoff_dt.isoformat(), "feature_schema_version_id": schema_id,
                "task": feat.TASK, "backend": "google-tabfm-v1", "actual_device": device,
                "gpu_name": gpu, "model_artifact_digest": digest, "dispatch": "sagemaker_async"}
    snapshots = requests = results = reused = superseded = 0
    current_snapshot_ids: set[int] = set()
    for i, row in enumerate(rows):
        pred = preds[i] if i < len(preds) else {}
        probs = pred.get("band_probabilities") or [0.0] * ds.n_bands
        band = int(pred.get("band_ordinal", int(np.argmax(probs))))
        band = min(max(band, 0), ds.n_bands - 1)
        conf = float(max(probs)) if probs else 0.0
        src = {**src_base, "unit_id": row["unit_id"], "district_id": row["district_id"]}
        snap = build_workload_snapshot(
            conn, schema_id=schema_id, unit_id=row["unit_id"], cutoff=cutoff_dt,
            values=row["features"], source_versions=src, actor=actor,
            policy_attestation=attestation)
        current_snapshot_ids.add(snap["feature_snapshot_id"])
        snapshots += 0 if snap["reused"] else 1
        reused += 1 if snap["reused"] else 0
        superseded += snap.get("superseded_prior", 0)
        req_id, created_req = _get_or_create_request(
            conn, mv_id, snap["feature_snapshot_id"], actor, attestation)
        requests += 1 if created_req else 0
        output = {"workload_band": ds.bands[band], "band_ordinal": band,
                  "band_probabilities": {ds.bands[b]: round(float(probs[b]), 4)
                                         for b in range(ds.n_bands)},
                  "abstained": bool(conf < 0.34), "cutoff_period": live["cutoff_period"],
                  "recent_case_volume": row["features"]["wl_recent_case_volume"],
                  "aggregate_subject": "police_district", "district_id": row["district_id"],
                  "district_name": row["unit_name"], "actual_backend": "tabfm",
                  "actual_device": device, "gpu_name": gpu, "model_artifact_digest": digest,
                  "served_via": "aws_sagemaker_async"}
        explanation = analytics_policy.stamp(
            {"method": (f"REAL Google TabFM v1 in-context classifier on AWS SageMaker "
                        f"({device}, {gpu}); fail-closed validated; ordinal band from "
                        "pre-cutoff district volume/trend/seasonality/throughput features"),
             "top_features": ["wl_recent_case_volume", "wl_trailing_year_volume",
                              "wl_prioryear_same_quarter", "wl_trend_slope"],
             "aggregate_only": True, "not_person_level": True,
             "model_artifact_digest": digest},
            attestation)
        _res_id, created_res = _write_result(conn, req_id, mv_id, snap["feature_snapshot_id"],
                                             output=output, explanation=explanation, confidence=conf)
        results += 1 if created_res else 0

    superseded += _stale_missing_snapshots(conn, schema_id, current_snapshot_ids)
    analytics_policy.require_supplied_current(conn, attestation, "SageMaker workload run")
    models.log_inference(
        conn, mv_id, ref_table="PredictionResult",
        inputs=analytics_policy.stamp(
            {"task": feat.TASK, "feature_schema_version_id": schema_id,
             "cutoff_period": live["cutoff_period"], "dispatch": "sagemaker_async"},
            attestation),
        outputs={"stations": len(rows), "results": results,
                 "complete_generation": True})
    audit.record(audit.Action.MODEL_RUN, "workload_sagemaker", mv_id, actor=actor, conn=conn,
                 detail={"model_version_id": mv_id, "backend": "tabfm", "device": device,
                         "gpu_name": gpu, "model_artifact_digest": digest,
                         "districts": len(rows), "results_new": results,
                         "adapter_request_id": res.request_id, "complete_generation": True})
    return {"model_version_id": mv_id, "feature_schema_version_id": schema_id,
            "training_dataset_snapshot_id": training_snapshot_id,
            "backend": "google-tabfm-v1",
            "actual_device": device, "gpu_name": gpu, "model_artifact_digest": digest,
            "cutoff": live["cutoff_period"], "districts": len(rows),
            "snapshots_new": snapshots, "snapshots_reused": reused,
            "requests_new": requests, "results_new": results,
            "superseded_prior": superseded, "runtime_ms": res.runtime_ms,
            "cold_start_ms": res.cold_start_ms,
            "peak_gpu_mem_mb": res.peak_gpu_mem_mb,
            "adapter_request_id": res.request_id}
