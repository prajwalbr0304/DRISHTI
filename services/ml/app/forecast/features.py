"""Forecast feature builder + district geometry graph.

Per district (optionally per crime head) we turn the monthly incident series into
feature rows — recent level/volatility/trend, month-over-month and year-over-year
change, a seasonal index — and attach the slow-moving socio-economic overlay
(unemployment, literacy, per-capita income, density). A next-period risk CLASS
(0..4 by count percentile) is the supervised target the foundation model consumes
as in-context examples. District centroids + k-NN adjacency give the spatial-
spillover graph the ST layer needs.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..geo import trends

FEATURE_NAMES = [
    "recent_mean", "recent_std", "trend_slope", "mom_pct", "yoy_pct",
    "seasonal_index", "last_value", "unemployment", "literacy",
    "per_capita_income_k", "pop_density_k",
]
RISK_CLASSES = ["Low", "Guarded", "Elevated", "High", "Severe"]
_PCTL = [20, 40, 60, 80]


def overlay(conn) -> dict[int, dict]:
    """Latest socio-economic overlay per district (nulls -> 0.0)."""
    out: dict[int, dict] = {}
    with conn.cursor() as cur:
        cur.execute(
            'SELECT DISTINCT ON ("DistrictID") "DistrictID","UnemploymentRate",'
            '"LiteracyRate","PopulationDensity" FROM "SocialIndicator" '
            'WHERE "DistrictID" IS NOT NULL ORDER BY "DistrictID","ObservedDate" DESC')
        for r in cur.fetchall():
            out.setdefault(int(r[0]), {})
            out[int(r[0])].update({"unemployment": float(r[1] or 0), "literacy": float(r[2] or 0),
                                   "pop_density_k": float(r[3] or 0) / 1000.0})
        cur.execute(
            'SELECT DISTINCT ON ("DistrictID") "DistrictID","PerCapitaIncome" '
            'FROM "EconomicIndicator" WHERE "DistrictID" IS NOT NULL '
            'ORDER BY "DistrictID","PeriodStart" DESC')
        for r in cur.fetchall():
            out.setdefault(int(r[0]), {})
            out[int(r[0])]["per_capita_income_k"] = float(r[1] or 0) / 1000.0
    return out


def district_centroids(conn, valid_geo_only: bool = True) -> dict[int, tuple[float, float]]:
    """District centroids from incident coordinates.

    ``valid_geo_only`` (default True for forecasting) excludes incidents whose
    coordinates fall outside the state polygon, so an out-of-jurisdiction outlier
    cannot drag a district's forecast centroid off the Karnataka landmass. Safe
    no-op when no boundary is loaded.
    """
    from ..cases import casedata
    from ..geo import geoscope
    where = ['cm."geom" IS NOT NULL', casedata.analytics_eligible_sql("cm")]
    params: list = []
    geoscope.apply_exclusion(conn, where, params, valid_geo_only)
    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", AVG(cm."longitude"), AVG(cm."latitude") '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'WHERE ' + ' AND '.join(where) + ' GROUP BY u."DistrictID"', params)
        return {int(r[0]): (float(r[1]), float(r[2])) for r in cur.fetchall()}


def district_names(conn) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictID","DistrictName" FROM "District"')
        return {int(r[0]): r[1] for r in cur.fetchall()}


def district_adjacency(conn, k: int = 4) -> dict[int, list[int]]:
    """k-nearest districts by centroid distance (a proxy for shared boundaries —
    District has no polygon geometry). Symmetric neighbour lists."""
    cents = district_centroids(conn)
    ids = list(cents)
    adj: dict[int, set] = {d: set() for d in ids}
    for a in ids:
        la, lo = cents[a][1], cents[a][0]
        dists = sorted(((np.hypot(la - cents[b][1], lo - cents[b][0]), b) for b in ids if b != a))
        for _, b in dists[:k]:
            adj[a].add(b); adj[b].add(a)
    return {d: sorted(v) for d, v in adj.items()}


def _feat_at(counts: list[int], i: int, window: int) -> list[float]:
    """Feature vector using data up to and including index i."""
    lo = max(0, i - window + 1)
    w = np.array(counts[lo:i + 1], dtype=float)
    recent_mean = float(w.mean())
    recent_std = float(w.std(ddof=0))
    # trend slope over the window (per month)
    if len(w) >= 2:
        x = np.arange(len(w))
        trend_slope = float(np.polyfit(x, w, 1)[0])
    else:
        trend_slope = 0.0
    last = float(counts[i])
    prev = float(counts[i - 1]) if i >= 1 else last
    mom_pct = (last - prev) / prev * 100 if prev else 0.0
    yoy = float(counts[i - 12]) if i >= 12 else last
    yoy_pct = (last - yoy) / yoy * 100 if yoy else 0.0
    # seasonal index: this month vs trailing 12-month average
    ann = np.array(counts[max(0, i - 11):i + 1], dtype=float)
    seasonal_index = last / float(ann.mean()) if ann.mean() else 1.0
    return [recent_mean, recent_std, trend_slope, mom_pct, yoy_pct,
            seasonal_index, last]


def build(conn, head_id: Optional[int] = None, window: int = 6) -> dict:
    """Build training context (features_t -> class_{t+1}) across all districts and
    the latest feature row per district (to forecast the next period)."""
    ov = overlay(conn)
    names = district_names(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u WHERE u."DistrictID" IS NOT NULL')
        district_ids = sorted(int(r[0]) for r in cur.fetchall())

    series = {d: trends.monthly_series(conn, district_id=d, head_id=head_id, valid_geo_only=True)
              for d in district_ids}
    # class edges from the pooled monthly-count distribution
    all_counts = [c for d in district_ids for c in series[d][1] if series[d][1]]
    edges = list(np.percentile(all_counts, _PCTL)) if all_counts else [1, 2, 3, 4]

    def _ov_vec(d):
        o = ov.get(d, {})
        return [o.get("unemployment", 0.0), o.get("literacy", 0.0),
                o.get("per_capita_income_k", 0.0), o.get("pop_density_k", 0.0)]

    X_ctx, y_ctx = [], []
    X_latest, meta = [], []
    for d in district_ids:
        periods, counts = series[d]
        if len(counts) < window + 2:
            continue
        ov_vec = _ov_vec(d)
        # training pairs: feature at t -> class of count at t+1
        for i in range(window - 1, len(counts) - 1):
            X_ctx.append(_feat_at(counts, i, window) + ov_vec)
            y_ctx.append(int(np.digitize(counts[i + 1], edges)))
        # latest row: forecast the month AFTER the last observed
        i = len(counts) - 1
        X_latest.append(_feat_at(counts, i, window) + ov_vec)
        recent_mean = float(np.mean(counts[max(0, i - window + 1):i + 1]))
        meta.append({"district_id": d, "district": names.get(d), "last_period": periods[-1],
                     "last_value": int(counts[i]), "recent_mean": round(recent_mean, 2),
                     "history": counts})
    return {"X_ctx": np.array(X_ctx, dtype=float), "y_ctx": np.array(y_ctx, dtype=int),
            "X_latest": np.array(X_latest, dtype=float), "meta": meta,
            "district_ids": [m["district_id"] for m in meta], "class_edges": edges,
            "feature_names": FEATURE_NAMES, "head_id": head_id}
