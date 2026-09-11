"""Crime-volume trends: monthly series by scope, MoM/YoY deltas, a rolling-average
anomaly band, and a classic additive decomposition (trend/seasonal/residual).

The decomposition is computed in numpy (centered moving-average trend + month-of-year
seasonal means) to avoid a heavy statsmodels dependency; it feeds the Analytics
'STL decomposition toggle' (doc 03 §2.3).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np


def _month_key(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _iter_months(first: str, last: str):
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def monthly_series(conn, district_id: Optional[int] = None, head_id: Optional[int] = None,
                   sub_head_id: Optional[int] = None,
                   start: Optional[dt.date] = None, end: Optional[dt.date] = None,
                   valid_geo_only: bool = False,
                   district_ids: Optional[list] = None,
                   crime_head_ids: Optional[list] = None,
                   unit_id: Optional[int] = None):
    """Return (periods, counts) monthly, zero-filled, for the given scope.

    ``valid_geo_only`` (Phase 12) restricts the series to canonical, valid
    geography: incidents whose coordinates fall outside the state polygon are
    excluded. It is a safe no-op when no jurisdiction boundary is loaded, so the
    descriptive-analytics callers (which pass the default False) are unaffected.

    ``district_ids`` / ``crime_head_ids`` carry a SEAT's confinement: a district
    SET for a range seat (which a single ``district_id`` cannot express), and a
    crime-head set for a wing seat (which is state-wide geographically and narrowed
    by head instead). An EMPTY district list means a seat entitled to nothing and
    yields an empty series, never an unfiltered one.

    ``unit_id`` is the STATION grain, one rung below district. Without it an SHO's
    trend chart was its whole district's series while every KPI card beside it came
    from a station-confined ``/performance/overview`` — the same board reporting two
    different jurisdictions, with nothing on screen saying so. It filters
    ``CaseMaster.PoliceStationID`` directly and needs no join, and it is applied ON
    TOP of any district filter rather than instead of it: a station is inside its
    district, so both conditions hold and neither can widen the other.
    """
    from ..cases import casedata

    where = ['cm."CrimeRegisteredDate" IS NOT NULL',
             casedata.analytics_eligible_sql("cm")]
    params: list = []
    joins = ""
    # One Unit join serves both the single-district and the district-set filter.
    if district_id is not None or district_ids is not None:
        joins += ' JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"'
    if unit_id is not None:
        where.append('cm."PoliceStationID" = %s')
        params.append(int(unit_id))
    if district_id is not None:
        where.append('u."DistrictID" = %s')
        params.append(district_id)
    if district_ids is not None:
        if not district_ids:
            where.append("FALSE")
        else:
            where.append('u."DistrictID" = ANY(%s)')
            params.append([int(d) for d in district_ids])
    if head_id is not None:
        where.append('cm."CrimeMajorHeadID" = %s')
        params.append(head_id)
    if crime_head_ids:
        where.append('cm."CrimeMajorHeadID" = ANY(%s)')
        params.append([int(h) for h in crime_head_ids])
    if sub_head_id is not None:
        where.append('cm."CrimeMinorHeadID" = %s')
        params.append(sub_head_id)
    if start is not None:
        where.append('cm."CrimeRegisteredDate" >= %s')
        params.append(start)
    if end is not None:
        where.append('cm."CrimeRegisteredDate" < %s')
        params.append(end)
    if valid_geo_only:
        from . import geoscope
        geoscope.apply_exclusion(conn, where, params, valid_geo_only=True)
    sql = (
        'SELECT to_char(date_trunc(\'month\', cm."CrimeRegisteredDate"), \'YYYY-MM\') AS ym, COUNT(*) '
        'FROM "CaseMaster" cm' + joins +
        ' WHERE ' + ' AND '.join(where) + ' GROUP BY ym ORDER BY ym'
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        raw = {r[0]: int(r[1]) for r in cur.fetchall()}
    if not raw:
        return [], []
    periods = _iter_months(min(raw), max(raw))
    counts = [raw.get(p, 0) for p in periods]
    return periods, counts


def rolling_band(counts, window: int = 6, k: float = 2.0):
    """Trailing rolling mean and +/- k*std band; flags anomalies above the band."""
    arr = np.array(counts, dtype=float)
    n = len(arr)
    mean = [None] * n
    upper = [None] * n
    lower = [None] * n
    anomaly = [False] * n
    for i in range(n):
        if i < window:
            continue
        w = arr[i - window:i]
        mu, sd = float(w.mean()), float(w.std(ddof=0))
        mean[i] = round(mu, 2)
        upper[i] = round(mu + k * sd, 2)
        lower[i] = round(max(0.0, mu - k * sd), 2)
        anomaly[i] = bool(arr[i] > (mu + k * sd))
    return mean, upper, lower, anomaly


def decompose(periods, counts, period_len: int = 12):
    """Additive decomposition: trend (centered MA), seasonal (month-of-year mean of
    detrended), residual. Returns aligned lists (None where undefined)."""
    arr = np.array(counts, dtype=float)
    n = len(arr)
    trend: list = [None] * n
    if n >= period_len:
        half = period_len // 2
        for i in range(half, n - half):
            # centered MA with half-weights at the ends (standard for even periods)
            window = arr[i - half:i + half + 1].copy()
            weights = np.ones(len(window))
            weights[0] = weights[-1] = 0.5
            trend[i] = float(np.sum(window * weights) / np.sum(weights))
    detr = np.array([arr[i] - trend[i] if trend[i] is not None else np.nan for i in range(n)])
    # seasonal = mean detrended value per calendar month
    by_month: dict[int, list] = {}
    for i, p in enumerate(periods):
        mth = int(p.split("-")[1])
        if not np.isnan(detr[i]):
            by_month.setdefault(mth, []).append(detr[i])
    seasonal_of_month = {m: float(np.mean(v)) for m, v in by_month.items()}
    # center seasonal to sum ~0
    if seasonal_of_month:
        avg = float(np.mean(list(seasonal_of_month.values())))
        seasonal_of_month = {m: v - avg for m, v in seasonal_of_month.items()}
    seasonal = [round(seasonal_of_month.get(int(p.split("-")[1]), 0.0), 3) for p in periods]
    residual = [round(float(arr[i] - (trend[i] or 0.0) - seasonal[i]), 3)
                if trend[i] is not None else None for i in range(n)]
    trend = [round(t, 3) if t is not None else None for t in trend]
    return trend, seasonal, residual


def deltas(periods, counts):
    """MoM and YoY deltas for the latest period."""
    if not counts:
        return {}
    n = len(counts)
    latest = counts[-1]
    out = {"latest_period": periods[-1], "latest": latest}
    if n >= 2:
        prev = counts[-2]
        out["mom_delta"] = latest - prev
        out["mom_pct"] = round((latest - prev) / prev * 100, 1) if prev else None
    if n >= 13:
        yoy = counts[-13]
        out["yoy_delta"] = latest - yoy
        out["yoy_pct"] = round((latest - yoy) / yoy * 100, 1) if yoy else None
    return out
