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

from .. import models
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


def get_forecaster() -> TrajectoryForecaster:
    """Prefer the real TimesFM 2.5 model; fall back to the seasonal forecaster."""
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


def forecast_trajectories(conn, head_id: Optional[int] = None, horizon: int = 3) -> dict:
    """Forecast each district's count trajectory; write the next-period median to
    CrimePrediction and return the full fan-chart trajectories."""
    fc = get_forecaster()
    centroids = feat.district_centroids(conn)
    names = feat.district_names(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u WHERE u."DistrictID" IS NOT NULL')
        district_ids = sorted(int(r[0]) for r in cur.fetchall())

    mv_id = models.get_or_create_model_version(
        conn, fc.name, "forecasting", "1.0.0", framework=fc.family,
        hyperparameters={"horizon": horizon, "season": _SEASON})

    trajectories, rows = [], []
    start = end = None
    for d in district_ids:
        periods, counts = trends.monthly_series(conn, district_id=d, head_id=head_id)
        if len(counts) < _SEASON + 2:
            continue
        traj = fc.forecast(counts, periods, horizon)
        s0 = traj[0]
        conf = _confidence(s0)
        y, m = map(int, s0["period"].split("-"))
        start = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
        end = (start + dt.timedelta(days=31 * horizon)).replace(day=1)
        lon, lat = centroids.get(d, (None, None))
        features_json = {"layer": "timesfm", "model": fc.name, "trajectory": traj,
                         "history_tail": counts[-12:]}
        trajectories.append({"district_id": d, "district": names.get(d),
                             "next_median": s0["median"], "confidence": conf, "trajectory": traj})
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
        models.log_inference(conn, mv_id, ref_table="CrimePrediction",
                             inputs={"head_id": head_id, "horizon": horizon},
                             outputs={"districts": len(rows), "model": fc.name})

    model_name = fc.name
    if hasattr(fc, "release"):     # free TimesFM weights before the next layer loads
        fc.release()
    return {"written": len(rows), "model": model_name, "model_version_id": mv_id,
            "horizon": horizon, "trajectories": trajectories}
