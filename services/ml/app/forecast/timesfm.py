"""TimesFM count-trajectory layer (doc 02 §4, doc 05 §2 companion).

Per-area monthly crime-count trajectory with fan-chart confidence bands. Behind a
TrajectoryForecaster interface:

  * TimesFMForecaster    — Google TimesFM zero-shot forecaster, used when the
                           `timesfm` package + weights are importable.
  * SeasonalForecaster   — an always-available statistical forecaster
                           (deseasonalised level+trend, month-of-year seasonal
                           factors, residual-sigma quantile bands). Genuine fan
                           charts; the real TimesFM drops in behind the same call.

The next-period median is written to CrimePrediction (layer 'timesfm'); the full
trajectory + bands are returned for the Analytics fan charts and consumed by the
spatio-temporal layer.
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import db, models
from ..geo import trends
from . import features as feat

_SEASON = 12
_Z = {"p10": -1.2816, "p25": -0.6745, "p75": 0.6745, "p90": 1.2816}


class TrajectoryForecaster(ABC):
    name: str = "abstract"
    family: str = "abstract"

    @abstractmethod
    def forecast(self, counts: list[int], months: list[str], horizon: int) -> list[dict]:
        """Return a list of per-step dicts: {step, period, median, p10, p25, p75, p90}."""


def _next_periods(last_period: str, horizon: int) -> list[str]:
    y, m = map(int, last_period.split("-"))
    out = []
    for _ in range(horizon):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        out.append(f"{y:04d}-{m:02d}")
    return out


class SeasonalForecaster(TrajectoryForecaster):
    name = "drishti-timesfm-seasonal"
    family = "statistical"

    def forecast(self, counts, months, horizon: int) -> list[dict]:
        arr = np.array(counts, dtype=float)
        n = len(arr)
        overall = float(arr.mean()) or 1.0
        # month-of-year seasonal factors (multiplicative), smoothed toward 1.0
        factors = np.ones(13)
        for mth in range(1, 13):
            vals = [arr[i] for i, p in enumerate(months) if int(p.split("-")[1]) == mth]
            if vals:
                factors[mth] = 0.5 + 0.5 * (float(np.mean(vals)) / overall)
        deseason = np.array([arr[i] / factors[int(months[i].split("-")[1])] for i in range(n)])
        # level + trend on deseasonalised recent window
        w = min(n, 24)
        x = np.arange(w)
        slope, intercept = np.polyfit(x, deseason[-w:], 1)
        fitted = np.array([(intercept + slope * i) * factors[int(months[n - w + i].split("-")[1])]
                           for i in range(w)])
        sigma = float(np.sqrt(np.mean((arr[-w:] - fitted) ** 2)))
        out = []
        for k, period in enumerate(_next_periods(months[-1], horizon), start=1):
            base = float(max(0.0, (intercept + slope * (w - 1 + k)) * factors[int(period.split("-")[1])]))
            band = float(sigma * np.sqrt(k))               # widening band with horizon
            out.append({"step": k, "period": period, "median": round(base, 2),
                        "p10": round(max(0.0, base + _Z["p10"] * band), 2),
                        "p25": round(max(0.0, base + _Z["p25"] * band), 2),
                        "p75": round(base + _Z["p75"] * band, 2),
                        "p90": round(base + _Z["p90"] * band, 2)})
        return out


class TimesFMForecaster(TrajectoryForecaster):
    """Real Google TimesFM 2.5 (200M, PyTorch) — the doc's named zero-shot
    forecaster. Its continuous-quantile head gives calibrated fan-chart bands.
    Weights (~200M) load once per process; release() frees them for the next layer.
    """
    name = "drishti-timesfm-2.5-200m"
    family = "foundation"
    _MAX_HORIZON = 12
    _MAX_CONTEXT = 512

    def __init__(self):
        import timesfm  # raises if not installed
        self._q_index = {0.1: 1, 0.2: 2, 0.3: 3, 0.5: 5, 0.7: 7, 0.8: 8, 0.9: 9}
        self._m = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
        self._m.compile(timesfm.ForecastConfig(
            max_context=self._MAX_CONTEXT, max_horizon=self._MAX_HORIZON,
            normalize_inputs=True, use_continuous_quantile_head=True,
            fix_quantile_crossing=True, infer_is_positive=True))

    def forecast(self, counts, months, horizon: int) -> list[dict]:
        h = int(min(horizon, self._MAX_HORIZON))
        series = np.asarray(counts[-self._MAX_CONTEXT:], dtype=np.float32)
        point, quant = self._m.forecast(horizon=h, inputs=[series])
        quant = np.asarray(quant)[0]           # (h, 10): [mean, q0.1..q0.9]
        periods = _next_periods(months[-1], h)
        out = []
        for k in range(h):
            q = quant[k]
            p25 = 0.5 * (float(q[2]) + float(q[3]))   # ~q0.25 from deciles
            p75 = 0.5 * (float(q[7]) + float(q[8]))   # ~q0.75
            out.append({"step": k + 1, "period": periods[k],
                        "median": round(float(q[5]), 2),           # q0.5
                        "p10": round(max(0.0, float(q[1])), 2),    # q0.1
                        "p25": round(max(0.0, p25), 2),
                        "p75": round(p75, 2),
                        "p90": round(float(q[9]), 2)})             # q0.9
        return out

    def release(self):
        import gc
        self._m = None
        gc.collect()


class SageMakerTimesFMForecaster(TrajectoryForecaster):
    """Real Google TimesFM 2.5 on AWS SageMaker (T4/CUDA) via the protected
    adapter. Same TrajectoryForecaster contract, so the existing pipeline +
    persistence are unchanged. Fails closed: a result that is not TimesFM on CUDA
    raises, so a CPU fallback can never be written as the real TimesFM layer.
    Records the actual device/gpu/digest for the UI provenance banner. Requires
    DRISHTI_AWS_ADAPTER_URL/SECRET + a live SageMaker endpoint."""
    name = "drishti-timesfm-2.5-200m"
    family = "foundation"
    _MAX_HORIZON = 12
    _MAX_CONTEXT = 512

    def __init__(self, poll_timeout_s: int = 300, poll_interval_s: int = 5):
        from ..predict.adapter import SignedHttpsAdapter
        self._adapter = SignedHttpsAdapter()
        self._poll_timeout_s = poll_timeout_s
        self._poll_interval_s = poll_interval_s
        self.actual_device: Optional[str] = None
        self.gpu_name: Optional[str] = None
        self.model_artifact_digest: Optional[str] = None

    def forecast(self, counts, months, horizon: int) -> list[dict]:
        import time
        import uuid

        from ..predict.envelope import (BackendKind, ColumnDef, DispatchMode, JobState,
                                        ModelTask, PredictionRequestEnvelope)

        import calendar

        h = int(min(max(horizon, 1), self._MAX_HORIZON))
        series = [float(c) for c in counts[-self._MAX_CONTEXT:]]
        _y, _m = map(int, months[-1].split("-"))
        cutoff_iso = dt.datetime(_y, _m, calendar.monthrange(_y, _m)[1], 23, 59, 59,
                                 tzinfo=dt.timezone.utc).isoformat()
        env = PredictionRequestEnvelope(
            request_id=uuid.uuid4().hex,
            idempotency_key=f"timesfm:{months[-1]}:{h}:{len(series)}",
            task=ModelTask.TIMESFM_COUNT_FORECAST, requested_backend=BackendKind.TIMESFM,
            feature_schema_version="forecast-timesfm-1", model_version="timesfm-2.5-200m",
            feature_schema_digest="ts-series", subject_kind="district", subject_ids=[],
            observation_cutoff=cutoff_iso,
            source_version_hash=f"ts-{months[-1]}-{len(series)}",
            columns=[ColumnDef(name="count")], query_rows=[[v] for v in series],
            output_schema={"horizon": h, "freq": "M"}, dispatch_mode=DispatchMode.SAGEMAKER_ASYNC)
        env.validate_shapes()
        rid = self._adapter.dispatch(env)
        deadline = time.time() + self._poll_timeout_s
        res = None
        while time.time() < deadline:
            res = self._adapter.poll(rid)
            if res.state in (JobState.COMPLETED, JobState.FAILED, JobState.TIMED_OUT,
                             JobState.CANCELLED):
                break
            time.sleep(self._poll_interval_s)
        if res is None or res.state != JobState.COMPLETED:
            raise RuntimeError(f"TimesFM SageMaker dispatch did not complete: "
                               f"state={getattr(res, 'state', None)} "
                               f"error={getattr(res, 'error_code', None)}")
        dev = res.actual_device.value if res.actual_device else None
        if res.actual_backend != BackendKind.TIMESFM or dev != "cuda":
            raise RuntimeError(f"TimesFM returned {res.actual_backend}/{dev} — not real "
                               "TimesFM on CUDA (fail closed).")
        self.actual_device, self.gpu_name = dev, res.gpu_name
        self.model_artifact_digest = res.model_artifact_digest
        periods = _next_periods(months[-1], h)
        out = []
        for k, pred in enumerate(res.predictions[:h]):
            q = pred.get("quantiles") or []
            p25 = 0.5 * (float(q[2]) + float(q[3])) if len(q) >= 4 else float(pred.get("p10", 0.0))
            p75 = 0.5 * (float(q[7]) + float(q[8])) if len(q) >= 9 else float(pred.get("p90", 0.0))
            median = float(pred.get("p50", pred.get("point", 0.0)))
            out.append({"step": k + 1, "period": periods[k],
                        "median": round(median, 2),
                        "p10": round(max(0.0, float(pred.get("p10", 0.0))), 2),
                        "p25": round(max(0.0, p25), 2),
                        "p75": round(p75, 2),
                        "p90": round(float(pred.get("p90", 0.0)), 2)})
        return out


def get_forecaster() -> TrajectoryForecaster:
    """Resolve the trajectory forecaster. Order: explicit SageMaker T4 path
    (DRISHTI_TIMESFM_SAGEMAKER=true) -> real local TimesFM 2.5 (if importable) ->
    always-available seasonal fallback."""
    import os
    if os.getenv("DRISHTI_TIMESFM_SAGEMAKER", "").strip().lower() == "true":
        return SageMakerTimesFMForecaster()
    try:
        import timesfm  # noqa: F401
        return TimesFMForecaster()
    except Exception:
        return SeasonalForecaster()


def _confidence(step0: dict) -> float:
    """Tight band around the median -> high confidence."""
    med = max(step0["median"], 1e-6)
    cv = (step0["p90"] - step0["p10"]) / (2.0 * med)
    return round(float(1.0 / (1.0 + cv)), 4)


def forecast_trajectories(conn, head_id: Optional[int] = None, horizon: int = 3,
                          policy_attestation=None) -> dict:
    """Forecast each district's count trajectory; write an attested layer."""
    from ..cases import analytics_policy

    attestation = policy_attestation or analytics_policy.current_attestation(conn)
    fc = get_forecaster()
    centroids = feat.district_centroids(conn)
    names = feat.district_names(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u WHERE u."DistrictID" IS NOT NULL')
        district_ids = sorted(int(r[0]) for r in cur.fetchall())

    mv_id = models.get_or_create_model_version(
        conn, fc.name, "forecasting",
        analytics_policy.policy_model_version("1.0.0", attestation), framework=fc.family,
        hyperparameters=analytics_policy.stamp(
            {"horizon": horizon, "season": _SEASON}, attestation))

    trajectories, rows = [], []
    start = end = None
    for d in district_ids:
        periods, counts = trends.monthly_series(conn, district_id=d, head_id=head_id,
                                                valid_geo_only=True)
        if len(counts) < _SEASON + 2:
            continue
        traj = fc.forecast(counts, periods, horizon)
        s0 = traj[0]
        conf = _confidence(s0)
        y, m = map(int, s0["period"].split("-"))
        start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
        end = (start + dt.timedelta(days=31 * horizon)).replace(day=1)
        lon, lat = centroids.get(d, (None, None))
        features_json = analytics_policy.stamp(
            {"layer": "timesfm", "model": fc.name, "trajectory": traj,
             "history_tail": counts[-12:]}, attestation)
        if getattr(fc, "actual_device", None):   # real SageMaker T4 provenance
            features_json.update(actual_device=fc.actual_device, gpu_name=fc.gpu_name,
                                 model_artifact_digest=fc.model_artifact_digest,
                                 served_via="aws_sagemaker_async")
        trajectories.append({"district_id": d, "district": names.get(d),
                             "next_median": s0["median"], "confidence": conf, "trajectory": traj})
        rows.append((mv_id, d, head_id, start, end, s0["median"],
                     round(min(1.0, s0["median"] / (max(counts) or 1)), 5), conf,
                     Json(features_json), lon, lon, lat))

    analytics_policy.require_supplied_current(conn, attestation, "TimesFM forecast run")
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'timesfm\' '
                    'AND "CrimeHeadID" IS NOT DISTINCT FROM %s', (head_id,))
        if rows:
            execute_values(
                cur,
                'INSERT INTO "CrimePrediction" ("ModelVersionID","DistrictID","CrimeHeadID",'
                '"PredictionStart","PredictionEnd","PredictedCount","Probability","Confidence",'
                '"Features","geom") VALUES %s',
                rows,
                template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                         "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
                page_size=200)
        models.log_inference(
            conn, mv_id, ref_table="CrimePrediction",
            inputs=analytics_policy.stamp(
                {"head_id": head_id, "horizon": horizon}, attestation),
            outputs={"districts": len(rows), "model": fc.name,
                     "complete_generation": True})

    model_name = fc.name
    if hasattr(fc, "release"):     # free TimesFM weights before the next layer loads
        fc.release()
    return {"written": len(rows), "model": model_name, "model_version_id": mv_id,
            "horizon": horizon, "trajectories": trajectories,
            "analytics_policy_attestation": attestation.as_dict()}


def forecast_trajectories_safe(head_id: Optional[int] = None, horizon: int = 6) -> dict:
    """Connection-safe TimesFM layer for the slow SageMaker path.

    The source policy is captured with the input read and revalidated in the
    fresh write transaction. A policy change during remote inference rejects the
    write rather than stamping rows generated from a stale cohort.
    """
    from ..cases import analytics_policy

    with db.ro_conn() as conn:
        attestation = analytics_policy.current_attestation(conn)
        centroids = feat.district_centroids(conn)
        names = feat.district_names(conn)
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u '
                        'WHERE u."DistrictID" IS NOT NULL')
            district_ids = sorted(int(r[0]) for r in cur.fetchall())
        series = {}
        for d in district_ids:
            periods, counts = trends.monthly_series(conn, district_id=d, head_id=head_id,
                                                    valid_geo_only=True)
            if len(counts) >= _SEASON + 2:
                series[d] = (periods, counts)

    fc = get_forecaster()                                   # SageMaker T4 when flagged
    done = []
    for d, (periods, counts) in series.items():
        traj = fc.forecast(counts, periods, horizon)        # no DB connection held
        done.append((d, periods, counts, traj, _confidence(traj[0])))
    device = getattr(fc, "actual_device", None)
    gpu = getattr(fc, "gpu_name", None)
    digest = getattr(fc, "model_artifact_digest", None)

    with db.rw_conn() as conn:
        analytics_policy.require_supplied_current(conn, attestation, "TimesFM SageMaker run")
        mv_id = models.get_or_create_model_version(
            conn, fc.name, "forecasting",
            analytics_policy.policy_model_version("1.0.0", attestation), framework=fc.family,
            hyperparameters=analytics_policy.stamp(
                {"horizon": horizon, "season": _SEASON,
                 "served_via": "aws_sagemaker_async" if device else "local"},
                attestation))
        rows = []
        for d, periods, counts, traj, conf in done:
            s0 = traj[0]
            y, m = map(int, s0["period"].split("-"))
            start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
            end = (start + dt.timedelta(days=31 * horizon)).replace(day=1)
            lon, lat = centroids.get(d, (None, None))
            features_json = analytics_policy.stamp(
                {"layer": "timesfm", "model": fc.name, "trajectory": traj,
                 "history_tail": counts[-12:], "district": names.get(d)}, attestation)
            if device:
                features_json.update(actual_device=device, gpu_name=gpu,
                                     model_artifact_digest=digest,
                                     served_via="aws_sagemaker_async")
            rows.append((mv_id, d, head_id, start, end, s0["median"],
                         round(min(1.0, s0["median"] / (max(counts) or 1)), 5), conf,
                         Json(features_json), lon, lon, lat))
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'timesfm\' '
                        'AND "CrimeHeadID" IS NOT DISTINCT FROM %s', (head_id,))
            if rows:
                execute_values(
                    cur,
                    'INSERT INTO "CrimePrediction" ("ModelVersionID","DistrictID","CrimeHeadID",'
                    '"PredictionStart","PredictionEnd","PredictedCount","Probability","Confidence",'
                    '"Features","geom") VALUES %s',
                    rows,
                    template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                             "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
                    page_size=200)
            models.log_inference(
                conn, mv_id, ref_table="CrimePrediction",
                inputs=analytics_policy.stamp(
                    {"head_id": head_id, "horizon": horizon}, attestation),
                outputs={"districts": len(rows), "model": fc.name,
                         "actual_device": device, "gpu_name": gpu,
                         "complete_generation": True})
    return {"written": len(rows), "model": fc.name, "model_version_id": mv_id,
            "actual_device": device, "gpu_name": gpu, "model_artifact_digest": digest,
            "districts": len(done), "analytics_policy_attestation": attestation.as_dict()}
