"""Rolling-origin backtest for the Phase-12 aggregate forecasts (doc 02 §4, 05 §6).

A forecast is only decision-support if we can say how wrong it usually is. This
module evaluates the district monthly incident-count forecast with a proper,
leakage-safe protocol and compares it against transparent baselines:

  * Rolling-origin (walk-forward) backtest: at each origin ``o`` the forecaster
    sees ONLY ``counts[:o+1]`` (strictly on/before the cutoff) and predicts the
    next ``horizon`` month(s); the held-out actuals ``counts[o+1:o+1+h]`` are
    never visible to the forecaster. Several origins are evaluated per series.
  * Geographic holdout: districts are split deterministically into an in-sample
    and a spatial-holdout set; error is reported separately so a district cannot
    "see itself" in the aggregate skill.
  * Metrics: MAE, RMSE, WAPE, sMAPE, and prediction-interval COVERAGE (share of
    actuals inside the 80% and 50% fan bands).
  * Baselines: seasonal-naive + moving-average, scored under the identical
    protocol; the model's SKILL is 1 - model_error / baseline_error.
  * Error is broken down by district, crime head and season, and the forecaster
    ABSTAINS on series that are too short/sparse to forecast responsibly.

The forecaster under test is the deterministic ``SeasonalForecaster`` — the same
statistical trajectory model the TimesFM layer falls back to when the foundation
weights are absent — so the backtest is fast, CPU-only, reproducible, and does
not require the heavy models in the inner loop.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Optional

import numpy as np

from . import features as feat
from .baselines import baseline_forecasters
from .timesfm import SeasonalForecaster

# The model under evaluation (deterministic statistical trajectory forecaster).
MODEL_KEY = "seasonal_trend"

# A district-month series must have at least this much history before an origin,
# and at least this average monthly volume, to be forecast; otherwise we ABSTAIN.
DEFAULT_MIN_TRAIN = 18
DEFAULT_MIN_MONTHLY_AVG = 1.0


# ---------------------------------------------------------------------------
# Series loading (bulk, one query per scope) with valid-geography filtering
# ---------------------------------------------------------------------------
def _load_matrix(conn, head_id: Optional[int], valid_geo_only: bool):
    """Return (periods, {district_id: counts}) monthly, zero-filled on a shared
    axis, excluding out-of-state incidents. One grouped query for all districts."""
    from ..cases import casedata
    from ..geo import geoscope
    where = ['cm."CrimeRegisteredDate" IS NOT NULL',
             casedata.analytics_eligible_sql("cm")]
    params: list = []
    if head_id is not None:
        where.append('cm."CrimeMajorHeadID" = %s')
        params.append(head_id)
    geoscope.apply_exclusion(conn, where, params, valid_geo_only)
    sql = ('SELECT u."DistrictID", '
           'to_char(date_trunc(\'month\', cm."CrimeRegisteredDate"), \'YYYY-MM\') ym, COUNT(*) '
           'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
           'WHERE ' + ' AND '.join(where) + ' GROUP BY 1,2')
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    if not rows:
        return [], {}
    raw: dict[int, dict[str, int]] = {}
    all_months = set()
    for d, ym, c in rows:
        raw.setdefault(int(d), {})[ym] = int(c)
        all_months.add(ym)
    periods = _month_axis(min(all_months), max(all_months))
    series = {d: [months.get(p, 0) for p in periods] for d, months in raw.items()}
    return _trim_incomplete_tail(periods, series)


def _trim_incomplete_tail(periods: list[str], series: dict[int, list[int]]):
    """Drop trailing months that fall OUTSIDE the data's real coverage.

    The shared month axis runs from the first to the last month that appears in
    ANY district's data, so a single stray/demo case in the current (partial)
    month — or the natural gap between the synthetic corpus end and today's date —
    zero-fills every intervening month. Scoring those empty future/partial months
    as ``actual == 0`` is not a real forecast target: it silently destroys the
    scale-relative metrics (WAPE/sMAPE explode toward the count magnitude / 200)
    and makes a collapse-to-zero baseline look artificially perfect. A trailing
    month is only a valid backtest target once its total activity across districts
    is a meaningful fraction of the median monthly total; incomplete/near-empty
    trailing months are trimmed. Internal zero months (genuinely quiet months
    inside the coverage) are preserved."""
    if not periods:
        return periods, series
    totals = [sum(series[d][i] for d in series) for i in range(len(periods))]
    nonzero = sorted(t for t in totals if t > 0)
    if not nonzero:
        return periods, series
    median = nonzero[len(nonzero) // 2]
    floor = max(1.0, 0.1 * median)
    last = len(periods)
    while last > 0 and totals[last - 1] < floor:
        last -= 1
    if last <= 0 or last == len(periods):
        return periods, series
    return periods[:last], {d: c[:last] for d, c in series.items()}


def _month_axis(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
_SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Summer", 4: "Summer",
            5: "Summer", 6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
            10: "Post-monsoon", 11: "Post-monsoon"}


def _season_of(period: str) -> str:
    return _SEASONS[int(period.split("-")[1])]


class _Acc:
    """Accumulates paired (actual, predicted) points + interval hits -> metrics."""
    def __init__(self):
        self.y: list[float] = []
        self.yhat: list[float] = []
        self.in80 = 0
        self.in50 = 0

    def add(self, y: float, step: dict):
        self.y.append(float(y))
        self.yhat.append(float(step["median"]))
        if step["p10"] <= y <= step["p90"]:
            self.in80 += 1
        if step["p25"] <= y <= step["p75"]:
            self.in50 += 1

    @property
    def n(self) -> int:
        return len(self.y)

    def metrics(self) -> Optional[dict]:
        if not self.y:
            return None
        y = np.asarray(self.y)
        yhat = np.asarray(self.yhat)
        err = yhat - y
        abs_err = np.abs(err)
        mae = float(abs_err.mean())
        rmse = float(np.sqrt(np.mean(err ** 2)))
        denom = float(np.abs(y).sum())
        wape = float(abs_err.sum() / denom) if denom > 0 else None
        sm_denom = np.abs(y) + np.abs(yhat)
        ratio = np.divide(2.0 * abs_err, sm_denom, out=np.zeros_like(abs_err, dtype=float),
                          where=sm_denom > 0)
        smape = float(np.mean(ratio) * 100.0)
        return {"mae": round(mae, 3), "rmse": round(rmse, 3),
                "wape": round(wape, 4) if wape is not None else None,
                "smape": round(smape, 2),
                "coverage_80": round(self.in80 / self.n, 4),
                "coverage_50": round(self.in50 / self.n, 4),
                "n": self.n}


def _mae_acc() -> "_Acc":
    return _Acc()


def _origin_indices(n: int, horizon: int, n_origins: int, step: int, min_train: int) -> list[int]:
    """Walk-forward origin indices for a length-``n`` series. Each origin ``o``
    means the forecaster trains on ``counts[:o+1]`` (strictly on/before the
    cutoff) and predicts ``counts[o+1:o+1+horizon]``. Leakage-safe by
    construction: the target index ``o+horizon`` is always AFTER the training
    slice and within the observed range."""
    o_max = n - 1 - horizon
    candidates = [o_max - i * step for i in range(n_origins)]
    return [o for o in candidates if o >= min_train - 1 and o + horizon < n]


def _skill(model: Optional[dict], base: Optional[dict]) -> dict:
    """1 - model_error/baseline_error per metric (positive => model better)."""
    out = {}
    if not model or not base:
        return out
    for k in ("mae", "rmse", "wape"):
        mv, bv = model.get(k), base.get(k)
        if mv is not None and bv:
            out[f"{k}_skill"] = round(1.0 - mv / bv, 4)
    return out


# ---------------------------------------------------------------------------
# Core rolling-origin backtest for one scope (head_id, or all heads)
# ---------------------------------------------------------------------------
def rolling_origin_backtest(conn, head_id: Optional[int] = None, horizon: int = 1,
                            n_origins: int = 6, step: int = 1,
                            min_train: int = DEFAULT_MIN_TRAIN,
                            min_monthly_avg: float = DEFAULT_MIN_MONTHLY_AVG,
                            geo_holdout_fraction: float = 0.25,
                            valid_geo_only: bool = True, seed: int = 42) -> dict:
    from ..geo import geoscope
    periods, series = _load_matrix(conn, head_id, valid_geo_only)
    names = feat.district_names(conn)
    district_ids = sorted(series)

    # Deterministic geographic holdout: every k-th district (sorted) is held out.
    holdout_set: set[int] = set()
    if district_ids and 0 < geo_holdout_fraction < 1:
        k = max(2, round(1 / geo_holdout_fraction))
        holdout_set = {d for i, d in enumerate(district_ids) if i % k == 0}

    model = SeasonalForecaster()
    forecasters = {MODEL_KEY: model, **baseline_forecasters()}

    overall = {name: _mae_acc() for name in forecasters}
    by_district: dict[int, _Acc] = {}
    by_season: dict[str, _Acc] = {}
    geo_train, geo_holdout = _mae_acc(), _mae_acc()
    origins_used: set[str] = set()
    scored_points = 0
    abstained = 0
    considered = 0

    for d in district_ids:
        counts = series[d]
        n = len(counts)
        origins = _origin_indices(n, horizon, n_origins, step, min_train)
        for o in origins:
            considered += 1
            train = counts[:o + 1]
            train_periods = periods[:o + 1]
            recent = train[-12:] if len(train) >= 12 else train
            if len(train) < min_train or float(np.mean(recent)) < min_monthly_avg:
                abstained += 1
                continue
            origins_used.add(train_periods[-1])
            actual = counts[o + 1:o + 1 + horizon]
            for name, fc in forecasters.items():
                traj = fc.forecast(train, train_periods, horizon)
                for kstep in range(horizon):
                    y = actual[kstep]
                    st = traj[kstep]
                    overall[name].add(y, st)
                    if name == MODEL_KEY:
                        by_district.setdefault(d, _mae_acc()).add(y, st)
                        by_season.setdefault(_season_of(st["period"]), _mae_acc()).add(y, st)
                        (geo_holdout if d in holdout_set else geo_train).add(y, st)
            scored_points += horizon

    model_m = overall[MODEL_KEY].metrics()
    baselines_m = {k: overall[k].metrics() for k in forecasters if k != MODEL_KEY}
    skill = {k: _skill(model_m, baselines_m.get(k)) for k in baselines_m}
    beats = None
    if model_m and baselines_m:
        base_maes = [b["mae"] for b in baselines_m.values() if b]
        beats = bool(base_maes) and model_m["mae"] <= min(base_maes)

    return {
        "scope": {"head_id": head_id, "horizon": horizon, "n_origins": n_origins, "step": step,
                  "min_train": min_train, "min_monthly_avg": min_monthly_avg,
                  "valid_geography": geoscope.scope_summary(conn)["valid_geography_filter"]},
        "n_series": len(district_ids),
        "origins": sorted(origins_used),
        "scored_points": scored_points,
        "cells_considered": considered,
        "abstained_cells": abstained,
        "abstention_rate": round(abstained / considered, 4) if considered else 0.0,
        "model": {"name": model.name, "family": model.family, **(model_m or {})},
        "baselines": {k: {"name": forecasters[k].name, **(v or {})} for k, v in baselines_m.items()},
        "skill_vs_baselines": skill,
        "beats_all_baselines": beats,
        "error_by_district": sorted(
            ({"district_id": d, "district": names.get(d), **(acc.metrics() or {})}
             for d, acc in by_district.items()),
            key=lambda r: (r.get("mae") is None, r.get("mae", 0)), reverse=False)[:64],
        "error_by_season": {s: acc.metrics() for s, acc in sorted(by_season.items())},
        "geo_holdout": {
            "holdout_fraction": geo_holdout_fraction,
            "holdout_districts": sorted(holdout_set),
            "train": geo_train.metrics(),
            "holdout": geo_holdout.metrics(),
        },
    }


# ---------------------------------------------------------------------------
# Full report: all-head scope + per-head breakdown
# ---------------------------------------------------------------------------
def _top_heads(conn, limit: int) -> list[tuple[int, str]]:
    from ..cases import casedata

    with conn.cursor() as cur:
        cur.execute(
            'SELECT cm."CrimeMajorHeadID", ch."CrimeGroupName", COUNT(*) c '
            'FROM "CaseMaster" cm JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
            'WHERE cm."CrimeMajorHeadID" IS NOT NULL '
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1,2 ORDER BY c DESC LIMIT %s',
            (limit,))
        return [(int(r[0]), r[1]) for r in cur.fetchall()]


def backtest_report(conn, head_id: Optional[int] = None, horizon: int = 1, n_origins: int = 6,
                    step: int = 1, per_head: bool = True, max_heads: int = 6,
                    valid_geo_only: bool = True, seed: int = 42) -> dict:
    """Assemble the full backtest report: the all-head (or scoped) rolling-origin
    backtest plus, when ``per_head`` and no head is scoped, a compact per-head
    error breakdown over the highest-volume crime heads."""
    core = rolling_origin_backtest(conn, head_id=head_id, horizon=horizon, n_origins=n_origins,
                                   step=step, valid_geo_only=valid_geo_only, seed=seed)
    by_head: dict[str, dict] = {}
    if per_head and head_id is None:
        for hid, hname in _top_heads(conn, max_heads):
            r = rolling_origin_backtest(conn, head_id=hid, horizon=horizon, n_origins=n_origins,
                                        step=step, valid_geo_only=valid_geo_only, seed=seed)
            by_head[hname] = {
                "crime_head_id": hid,
                "model": r["model"], "beats_all_baselines": r["beats_all_baselines"],
                "abstention_rate": r["abstention_rate"], "scored_points": r["scored_points"],
            }
    core["error_by_head"] = by_head
    core["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return core


def summarize(report: dict) -> dict:
    """A compact one-line-per-metric summary for the AiResult + logs."""
    m = report.get("model") or {}
    return {"mae": m.get("mae"), "rmse": m.get("rmse"), "wape": m.get("wape"),
            "smape": m.get("smape"), "coverage_80": m.get("coverage_80"),
            "beats_all_baselines": report.get("beats_all_baselines"),
            "scored_points": report.get("scored_points"),
            "abstention_rate": report.get("abstention_rate")}
