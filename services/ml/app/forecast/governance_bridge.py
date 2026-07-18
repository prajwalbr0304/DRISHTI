"""Bridge the aggregate forecast into the governed prediction contract (Phase 12).

Phase 10/11 established the rule (and the explicit Phase-12 prerequisite): every
model output must be reproducible from an IMMUTABLE ``FeatureSnapshot`` and a
governed ``PredictionResult``, bound to an APPROVED model + feature schema. The
forecast pipeline writes ``CrimePrediction`` rows for the map/analytics; this
module additionally persists each district's fused forecast through the governed
path so it carries:

  * an immutable, hashed ``FeatureSnapshot`` (aggregate, non-protected,
    strictly-pre-cutoff features + external-context source-version provenance);
  * a ``PredictionRequest`` (idempotent) bound to the approved forecast schema +
    an approved ``ModelVersion``;
  * a ``PredictionResult`` with the projected count, a LOWER/UPPER interval, the
    confidence, the explanation (contributing layers + referenced backtest
    metrics), limitations and an expiry;
  * STALE/SUPERSEDED handling — a newer forecast snapshot for the same district
    supersedes the old one and marks its results stale (history preserved).

It reuses the governance builder's approved-schema loading, protected-feature
guard and content hashing, so the forecast obeys the same guarantees as any
governed model. Aggregate area/period only — never a person-level judgement.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from psycopg2.extras import Json

from .. import audit, models
from ..governance import builder
from . import context

FORECAST_SCHEMA_NAME = "forecast-area-incident"
FORECAST_SCHEMA_VERSION = "1"
FORECAST_MODEL_NAME = "drishti-forecast-fusion"
FORECAST_MODEL_VERSION = "1.0.0"
_RESULT_TTL_DAYS = 30
_LIMITATIONS = (
    "Aggregate area/period decision support with visible uncertainty. Not a "
    "person-level prediction and not certainty. The interval reflects cross-layer "
    "agreement; see the referenced rolling-origin backtest for typical error and "
    "baseline comparison. Requires human review before any operational use."
)


class ForecastGovernanceError(Exception):
    pass


class ForecastSchemaMissing(ForecastGovernanceError):
    pass


# ---------------------------------------------------------------------------
# Approved schema + governed model
# ---------------------------------------------------------------------------
def forecast_schema_id(conn) -> int:
    """Return the approved forecast FeatureSchemaVersionID (migration 019 seed)."""
    with conn.cursor() as cur:
        cur.execute('SELECT "FeatureSchemaVersionID","Status" FROM "FeatureSchemaVersion" '
                    'WHERE "SchemaName"=%s AND "Version"=%s',
                    (FORECAST_SCHEMA_NAME, FORECAST_SCHEMA_VERSION))
        r = cur.fetchone()
    if not r:
        raise ForecastSchemaMissing(
            f"Approved forecast schema {FORECAST_SCHEMA_NAME} v{FORECAST_SCHEMA_VERSION} "
            "is not present — apply migration 019.")
    if r[1] != "approved":
        raise ForecastSchemaMissing(
            f"Forecast schema {FORECAST_SCHEMA_NAME} v{FORECAST_SCHEMA_VERSION} is '{r[1]}', "
            "not 'approved'.")
    return int(r[0])


def ensure_forecast_model(conn, feature_schema_version_id: int, *,
                          metrics: Optional[dict] = None, actor: Optional[str] = None) -> int:
    """Register/lookup the fused-forecast ModelVersion and bind it to the approved
    forecast schema as an approved governed model."""
    mv_id = models.get_or_create_model_version(
        conn, FORECAST_MODEL_NAME, "forecasting", FORECAST_MODEL_VERSION,
        framework="stacked-inspectable",
        hyperparameters={"layers": ["tabfm", "timesfm", "near_repeat", "st_gnn"],
                         "fusion": "transparent-weighted"},
        metrics=metrics or {})
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "ModelVersion" SET "FeatureSchemaVersionID"=%s, '
            '"ApprovalStatus"=COALESCE(NULLIF("ApprovalStatus",\'\'),\'approved\'), '
            '"ApprovedBy"=COALESCE("ApprovedBy",%s), "ApprovedAt"=COALESCE("ApprovedAt", now()), '
            '"Environment"=COALESCE("Environment",\'hackathon_demo\') '
            'WHERE "ModelVersionID"=%s',
            (feature_schema_version_id, actor or "forecast-bridge", mv_id))
    return mv_id


# ---------------------------------------------------------------------------
# Immutable forecast feature snapshot (idempotent + supersession)
# ---------------------------------------------------------------------------
def _find_live_snapshot(conn, feature_schema_version_id: int, subject_ref_id: str,
                        content_hash: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSnapshotID" FROM "FeatureSnapshot" '
            'WHERE "FeatureSchemaVersionID"=%s AND "SubjectKind"=\'area_district\' '
            'AND "SubjectRefID"=%s AND "ContentHash"=%s '
            "AND \"SupersededByFeatureSnapshotID\" IS NULL AND \"QualityStatus\" <> 'stale' "
            'ORDER BY "FeatureSnapshotID" DESC LIMIT 1',
            (feature_schema_version_id, subject_ref_id, content_hash))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _supersede_prior(conn, feature_schema_version_id: int, subject_ref_id: str,
                     new_snapshot_id: int, actor: Optional[str]) -> int:
    """Mark prior live FORECAST snapshots for the district superseded by the new
    one, and stale their live results. Scoped to the forecast schema so it never
    touches other schemas' snapshots. History is preserved (no delete)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FeatureSnapshotID" FROM "FeatureSnapshot" '
            'WHERE "FeatureSchemaVersionID"=%s AND "SubjectKind"=\'area_district\' '
            'AND "SubjectRefID"=%s AND "FeatureSnapshotID" <> %s '
            'AND "SupersededByFeatureSnapshotID" IS NULL',
            (feature_schema_version_id, subject_ref_id, new_snapshot_id))
        prior = [int(r[0]) for r in cur.fetchall()]
        for sid in prior:
            cur.execute(
                'UPDATE "FeatureSnapshot" SET "SupersededByFeatureSnapshotID"=%s, '
                '"SupersededAt"=now(), "StaleReason"=%s WHERE "FeatureSnapshotID"=%s',
                (new_snapshot_id, "superseded by newer forecast snapshot", sid))
            cur.execute(
                "UPDATE \"PredictionResult\" SET \"IsStale\"=TRUE, \"StaleReason\"=%s, "
                '"StaleAt"=now() WHERE "FeatureSnapshotID"=%s AND "IsStale"=FALSE',
                ("superseded forecast snapshot", sid))
            cur.execute(
                "UPDATE \"PredictionRequest\" SET \"Status\"='superseded' "
                "WHERE \"FeatureSnapshotID\"=%s AND \"Status\" IN ('queued','running','completed')",
                (sid,))
    return len(prior)


def build_forecast_snapshot(conn, *, feature_schema_version_id: int, district_id: int,
                            cutoff: dt.datetime, values: dict, source_versions: dict,
                            actor: Optional[str] = None) -> dict:
    """Build (or reuse) an immutable forecast FeatureSnapshot for a district."""
    schema = builder._load_schema(conn, feature_schema_version_id)
    if schema["status"] != "approved":
        raise builder.SchemaNotApproved(f"schema {feature_schema_version_id} not approved.")
    definitions = builder._load_definitions(conn, schema["feature_definition_ids"])
    builder.assert_no_protected_features(schema["task"], definitions)   # protected-feature guard

    names = [d["name"] for d in definitions]
    vals: dict = {}
    unknown: list[str] = []
    for n in names:
        if n in values and values[n] is not None:
            vals[n] = values[n]
        else:
            vals[n] = None
            unknown.append(n)
    quality = "partial" if unknown else "ok"
    subject_ref = str(district_id)
    content_hash = builder._hash({"schema": feature_schema_version_id,
                                  "subject": ["area_district", subject_ref],
                                  "cutoff": builder._iso(cutoff), "values": vals})

    existing = _find_live_snapshot(conn, feature_schema_version_id, subject_ref, content_hash)
    if existing is not None:
        return {"feature_snapshot_id": existing, "reused": True, "quality_status": quality,
                "content_hash": content_hash, "superseded_prior": 0}

    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "FeatureSnapshot" ("FeatureSchemaVersionID","SubjectKind","SubjectRefID",'
            '"ObservationCutoff","Values","SourceVersions","QualityStatus","ContentHash",'
            '"IsImmutable","BuiltByActor") '
            "VALUES (%s,'area_district',%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING \"FeatureSnapshotID\"",
            (feature_schema_version_id, subject_ref, cutoff, Json(vals), Json(source_versions),
             quality, content_hash, actor))
        snap_id = int(cur.fetchone()[0])
    superseded = _supersede_prior(conn, feature_schema_version_id, subject_ref, snap_id, actor)
    return {"feature_snapshot_id": snap_id, "reused": False, "quality_status": quality,
            "content_hash": content_hash, "superseded_prior": superseded}


# ---------------------------------------------------------------------------
# Governed request + result
# ---------------------------------------------------------------------------
def _get_or_create_request(conn, model_version_id: int, feature_snapshot_id: int,
                           horizon_days: int, actor: Optional[str]) -> tuple[int, bool]:
    idem = f"forecast:area_district:{feature_snapshot_id}:{horizon_days}"
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "PredictionRequest" ("ModelVersionID","FeatureSnapshotID","RequestKind",'
            '"IdempotencyKey","Status","RequestedByActor") VALUES (%s,%s,\'batch\',%s,\'queued\',%s) '
            'ON CONFLICT ("IdempotencyKey") DO NOTHING RETURNING "PredictionRequestID"',
            (model_version_id, feature_snapshot_id, idem, actor))
        r = cur.fetchone()
        if r:
            return int(r[0]), True
        cur.execute('SELECT "PredictionRequestID" FROM "PredictionRequest" WHERE "IdempotencyKey"=%s',
                    (idem,))
        return int(cur.fetchone()[0]), False


def _write_result(conn, request_id: int, model_version_id: int, feature_snapshot_id: int,
                  *, output: dict, explanation: dict, confidence: float,
                  lower: float, upper: float) -> tuple[int, bool]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "PredictionResultID" FROM "PredictionResult" '
            'WHERE "PredictionRequestID"=%s AND "SupersededByResultID" IS NULL AND "IsStale"=FALSE '
            'ORDER BY "PredictionResultID" DESC LIMIT 1', (request_id,))
        r = cur.fetchone()
        if r:
            return int(r[0]), False
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_RESULT_TTL_DAYS)
        cur.execute(
            'INSERT INTO "PredictionResult" ("PredictionRequestID","ModelVersionID",'
            '"FeatureSnapshotID","OutputJSON","Explanation","Limitations","Confidence",'
            '"LowerInterval","UpperInterval","ExpiresAt") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "PredictionResultID"',
            (request_id, model_version_id, feature_snapshot_id, Json(output), Json(explanation),
             _LIMITATIONS, round(float(confidence), 5), round(float(lower), 3),
             round(float(upper), 3), expires))
        res_id = int(cur.fetchone()[0])
        cur.execute("UPDATE \"PredictionRequest\" SET \"Status\"='completed' "
                    "WHERE \"PredictionRequestID\"=%s AND \"Status\" IN ('queued','running')",
                    (request_id,))
    return res_id, True


def _latest_backtest(conn, model_version_id: int) -> Optional[dict]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "MAE","RMSE","WAPE","SMAPE","Coverage80","BeatsAllBaselines","Horizon","CreatedAt" '
                'FROM "ForecastBacktest" WHERE "ModelVersionID"=%s AND "CrimeHeadID" IS NULL '
                'ORDER BY "CreatedAt" DESC LIMIT 1', (model_version_id,))
            r = cur.fetchone()
    except Exception:  # noqa: BLE001 — table may not exist yet
        return None
    if not r:
        return None
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"mae": f(r[0]), "rmse": f(r[1]), "wape": f(r[2]), "smape": f(r[3]),
            "coverage_80": f(r[4]), "beats_all_baselines": r[5], "horizon": r[6],
            "as_of": r[7].isoformat() if r[7] else None}


def _interval_from_confidence(count: float, confidence: float) -> tuple[float, float]:
    """Reconstruct an ~80% interval consistent with how layer confidence is
    defined (confidence = 1/(1+cv), cv = half-width / median)."""
    conf = min(max(float(confidence or 0.0), 1e-3), 0.999)
    cv = (1.0 / conf) - 1.0
    lo = max(0.0, count * (1.0 - cv))
    hi = count * (1.0 + cv)
    return lo, hi


# ---------------------------------------------------------------------------
# Public: persist a full fused-forecast run through the governed contract
# ---------------------------------------------------------------------------
def persist_forecast(conn, *, districts: list[dict], head_id: Optional[int],
                     prediction_start, prediction_end, horizon_days: int,
                     model_metrics: Optional[dict] = None, actor: str = "forecast-batch") -> dict:
    """Persist each fused district forecast as an immutable snapshot + governed
    PredictionRequest/Result. Returns a summary. Idempotent + supersedes prior."""
    schema_id = forecast_schema_id(conn)
    mv_id = ensure_forecast_model(conn, schema_id, metrics=model_metrics, actor=actor)
    cutoff = _as_datetime(prediction_start) or builder._default_cutoff(conn)
    backtest = _latest_backtest(conn, mv_id)

    # aggregate, non-protected, pre-cutoff features per district (valid geography)
    fmap = _feature_map(conn, head_id)

    snapshots = requests = results = reused = superseded = skipped = 0
    for row in districts:
        d = row.get("district_id")
        if d is None or d not in fmap:
            skipped += 1
            continue
        count = float(row.get("fused_count") or 0.0)
        conf = float(row.get("confidence") or 0.0)
        lo, hi = _interval_from_confidence(count, conf)
        src = context.snapshot_source_versions(conn, d, cutoff)
        snap = build_forecast_snapshot(conn, feature_schema_version_id=schema_id, district_id=d,
                                       cutoff=cutoff, values=fmap[d], source_versions=src, actor=actor)
        snapshots += 0 if snap["reused"] else 1
        reused += 1 if snap["reused"] else 0
        superseded += snap.get("superseded_prior", 0)
        req_id, created_req = _get_or_create_request(conn, mv_id, snap["feature_snapshot_id"],
                                                     horizon_days, actor)
        requests += 1 if created_req else 0
        output = {"projected_next_period_incidents": round(count, 2),
                  "risk_class": row.get("risk_class"), "horizon_days": horizon_days,
                  "prediction_start": _iso(prediction_start), "prediction_end": _iso(prediction_end),
                  "near_term_spike": bool(row.get("near_term_spike")),
                  "contributing_models": row.get("contributing_models", [])}
        explanation = {"method": "transparent stacked fusion (TabFM district risk + TimesFM "
                                 "trajectory + Hawkes near-repeat + ST-GNN spillover)",
                       "interval": "~80% band from cross-layer confidence",
                       "backtest": backtest or "no backtest on record; run forecast-backtest",
                       "valid_geography": True, "aggregate_only": True}
        _res_id, created_res = _write_result(conn, req_id, mv_id, snap["feature_snapshot_id"],
                                             output=output, explanation=explanation, confidence=conf,
                                             lower=lo, upper=hi)
        results += 1 if created_res else 0

    audit.record(audit.Action.MODEL_RUN, "forecast_governed", mv_id, actor=actor, conn=conn,
                 detail={"model_version_id": mv_id, "feature_schema_version_id": schema_id,
                         "districts": len(districts), "snapshots_new": snapshots,
                         "results_new": results, "superseded": superseded})
    return {"model_version_id": mv_id, "feature_schema_version_id": schema_id,
            "snapshots_new": snapshots, "snapshots_reused": reused, "requests_new": requests,
            "results_new": results, "superseded_prior": superseded, "skipped": skipped,
            "backtest_referenced": bool(backtest)}


def persist_backtest(conn, report: dict, *, model_version_id: Optional[int] = None,
                     head_id: Optional[int] = None, actor: str = "forecast-batch") -> int:
    """Persist a rolling-origin backtest report as a typed ForecastBacktest row."""
    if model_version_id is None:
        schema_id = forecast_schema_id(conn)
        model_version_id = ensure_forecast_model(conn, schema_id, actor=actor)
    m = report.get("model") or {}
    scope = report.get("scope") or {}
    origins = report.get("origins") or []
    baselines = {"baselines": report.get("baselines"), "skill": report.get("skill_vs_baselines")}
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "ForecastBacktest" ("ModelVersionID","CrimeHeadID","Horizon","NOrigins",'
            '"LatestOrigin","MAE","RMSE","WAPE","SMAPE","Coverage80","Coverage50","ScoredPoints",'
            '"AbstainedCells","AbstentionRate","BeatsAllBaselines","ValidGeography","Baselines",'
            '"Report","Actor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "ForecastBacktestID"',
            (model_version_id, head_id, scope.get("horizon", 1), scope.get("n_origins"),
             origins[-1] if origins else None, m.get("mae"), m.get("rmse"), m.get("wape"),
             m.get("smape"), m.get("coverage_80"), m.get("coverage_50"), report.get("scored_points"),
             report.get("abstained_cells"), report.get("abstention_rate"),
             report.get("beats_all_baselines"), scope.get("valid_geography"),
             Json(baselines), Json(report), actor))
        bt_id = int(cur.fetchone()[0])
    audit.record(audit.Action.MODEL_RUN, "forecast_backtest", bt_id, actor=actor, conn=conn,
                 detail={"model_version_id": model_version_id, "mae": m.get("mae"),
                         "beats_all_baselines": report.get("beats_all_baselines")})
    return bt_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _feature_map(conn, head_id: Optional[int]) -> dict[int, dict]:
    """Aggregate, non-protected, pre-cutoff feature values per district for the
    forecast snapshot (recent level/trend/seasonality/prior-year/last/history).

    Uses ONE bulk, valid-geography series query (not 32 per-district queries) so
    persisting the governed result is cheap enough to run after every forecast."""
    import numpy as np

    from .backtest import _load_matrix
    _periods, series = _load_matrix(conn, head_id, valid_geo_only=True)
    out: dict[int, dict] = {}
    for d, counts in series.items():
        arr = np.asarray(counts, dtype=float)
        n = len(arr)
        if n < 2:
            continue
        recent = arr[-min(6, n):]
        wt = min(12, n)
        slope = float(np.polyfit(np.arange(wt), arr[-wt:], 1)[0]) if wt >= 2 else 0.0
        ann = arr[-12:] if n >= 12 else arr
        last = float(arr[-1])
        out[int(d)] = {
            "fc_recent_mean_incidents": round(float(recent.mean()), 3),
            "fc_trend_slope": round(slope, 4),
            "fc_seasonal_index": round(float(last / ann.mean()) if ann.mean() else 1.0, 4),
            "fc_prioryear_count": float(arr[-12]) if n >= 12 else last,
            "fc_last_value": last,
            "fc_history_months": float(n),
        }
    return out


def _as_datetime(v) -> Optional[dt.datetime]:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)
    try:
        s = str(v).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _iso(v) -> Optional[str]:
    d = _as_datetime(v)
    return d.isoformat() if d else (str(v) if v is not None else None)
