"""Forecast validation — PAI / hit-rate on held-out incidents, per district & crime
type (doc 05 §6).

Train on incidents strictly before a cutoff, forecast each (district, crime-head)
cell's next-period level (trailing seasonal average), then rank cells and flag the
top `area_fraction`. On the held-out post-cutoff window:

    hit_rate = share of post-cutoff incidents inside flagged cells
    PAI      = hit_rate / area_fraction         (>1 beats chance; higher is better)

Reported overall and per crime head.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def forecast_pai(conn, cutoff: dt.date = dt.date(2025, 10, 1), horizon_months: int = 3,
                 lookback_months: int = 12, area_fraction: float = 0.25) -> dict:
    pre_start = _add_months(cutoff, -lookback_months)
    post_end = _add_months(cutoff, horizon_months)
    with conn.cursor() as cur:
        # predicted level per (district, head): trailing monthly average scaled to horizon
        cur.execute(
            'SELECT u."DistrictID", cm."CrimeMajorHeadID", COUNT(*)::float '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'WHERE cm."CrimeMajorHeadID" IS NOT NULL '
            'AND cm."CrimeRegisteredDate" >= %s AND cm."CrimeRegisteredDate" < %s '
            'GROUP BY 1,2', (pre_start, cutoff))
        pred = {(int(r[0]), int(r[1])): float(r[2]) / lookback_months * horizon_months
                for r in cur.fetchall()}
        # actual held-out counts per cell
        cur.execute(
            'SELECT u."DistrictID", cm."CrimeMajorHeadID", COUNT(*) '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'WHERE cm."CrimeMajorHeadID" IS NOT NULL '
            'AND cm."CrimeRegisteredDate" >= %s AND cm."CrimeRegisteredDate" < %s '
            'GROUP BY 1,2', (cutoff, post_end))
        actual = {(int(r[0]), int(r[1])): int(r[2]) for r in cur.fetchall()}
        cur.execute('SELECT "CrimeHeadID","CrimeGroupName" FROM "CrimeHead"')
        head_names = {int(r[0]): r[1] for r in cur.fetchall()}

    cells = sorted(set(pred) | set(actual))

    def _pai(cell_subset):
        subset = [c for c in cells if c in cell_subset] if cell_subset is not None else cells
        if not subset:
            return None
        total_actual = sum(actual.get(c, 0) for c in subset)
        if total_actual == 0:
            return None
        k = max(1, math.ceil(area_fraction * len(subset)))
        ranked = sorted(subset, key=lambda c: pred.get(c, 0.0), reverse=True)[:k]
        hit = sum(actual.get(c, 0) for c in ranked)
        hit_rate = hit / total_actual
        af = k / len(subset)
        return {"cells": len(subset), "flagged": k, "area_fraction": round(af, 4),
                "hit_rate": round(hit_rate, 4), "pai": round(hit_rate / af, 2) if af else None,
                "held_out_incidents": total_actual}

    overall = _pai(None)
    per_head = {}
    heads = defaultdict(set)
    for (d, h) in cells:
        heads[h].add((d, h))
    for h, cs in heads.items():
        r = _pai(cs)
        if r:
            per_head[head_names.get(h, str(h))] = r

    return {"cutoff": str(cutoff), "horizon_months": horizon_months,
            "area_fraction": area_fraction, "overall": overall, "per_crime_head": per_head}
