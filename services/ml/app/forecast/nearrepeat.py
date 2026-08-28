"""Near-repeat forecasting — self-exciting point process (Hawkes / ETAS-style),
doc 05 Layer 1.

Each recent incident adds a decaying excitation in space and time, so a burglary
raises the short-horizon risk of another nearby (the near-repeat "echo"). The
per-grid-cell intensity is:

    lambda(cell) = mu(background) + sum_events  theta * exp(-dt/tau) * exp(-d^2 / 2 sigma^2)

Top cells are written to CrimePrediction (short horizon). A near-real-time trigger
recomputes the local surface when a new FIR lands in a watched area.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import models
from . import features as feat

_DEG_M = 111_000.0            # metres per degree latitude (approx)
GRID_DEG = 0.0025             # ~275 m grid cell


def _recent_points(conn, district_id, head_id, ref: dt.datetime, lookback_days: int):
    from ..cases import casedata
    from ..geo import geoscope
    where = ['cm."geom" IS NOT NULL', 'cm."IncidentFromDate" IS NOT NULL',
             'cm."IncidentFromDate" <= %s', 'cm."IncidentFromDate" >= %s',
             casedata.analytics_eligible_sql("cm")]
    params = [ref, ref - dt.timedelta(days=lookback_days)]
    joins = ' JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID"'
    if district_id is not None:
        where.append('u."DistrictID" = %s'); params.append(district_id)
    if head_id is not None:
        where.append('cm."CrimeMajorHeadID" = %s'); params.append(head_id)
    # Valid geography only: a self-exciting near-repeat surface must not be seeded
    # by an incident whose coordinates fall outside the state polygon.
    geoscope.apply_exclusion(conn, where, params, valid_geo_only=True)
    with conn.cursor() as cur:
        cur.execute('SELECT cm."latitude", cm."longitude", '
                    'EXTRACT(EPOCH FROM (%s - cm."IncidentFromDate"))/86400.0 '
                    'FROM "CaseMaster" cm' + joins + ' WHERE ' + ' AND '.join(where) +
                    ' LIMIT 4000', [ref] + params)
        rows = cur.fetchall()
    if not rows:
        return np.array([]), np.array([]), np.array([])
    lat = np.array([float(r[0]) for r in rows])
    lon = np.array([float(r[1]) for r in rows])
    age = np.array([float(r[2]) for r in rows])       # days before ref
    return lat, lon, age


def _cell(lat, lon):
    return (float(round(lat / GRID_DEG) * GRID_DEG), float(round(lon / GRID_DEG) * GRID_DEG))


def _intensity_surface(lat, lon, age, sigma_m, tau_days, theta, cells=None):
    """Compute self-excitation intensity at each candidate cell centroid."""
    if len(lat) == 0:
        return []
    if cells is None:
        cells = sorted({_cell(la, lo) for la, lo in zip(lat, lon)})
    tdecay = np.exp(-age / tau_days)                  # temporal kernel per event
    coslat = np.cos(np.radians(float(lat.mean())))
    out = []
    for clat, clon in cells:
        dlat = (lat - clat) * _DEG_M
        dlon = (lon - clon) * _DEG_M * coslat
        d2 = dlat * dlat + dlon * dlon
        spatial = np.exp(-d2 / (2.0 * sigma_m * sigma_m))
        excitation = float(theta * np.sum(tdecay * spatial))
        n_contrib = int(np.sum((d2 < (2 * sigma_m) ** 2) & (age < 3 * tau_days)))
        out.append({"lat": round(clat, 5), "lon": round(clon, 5),
                    "intensity": round(excitation, 4), "contributing_events": n_contrib})
    out.sort(key=lambda c: -c["intensity"])
    return out


def _ref_date(conn, district_id, head_id):
    from ..cases import casedata

    where = ['cm."IncidentFromDate" IS NOT NULL',
             casedata.analytics_eligible_sql("cm")]
    params = []
    joins = ' JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID"'
    if district_id is not None:
        where.append('u."DistrictID"=%s'); params.append(district_id)
    if head_id is not None:
        where.append('cm."CrimeMajorHeadID"=%s'); params.append(head_id)
    with conn.cursor() as cur:
        cur.execute('SELECT MAX(cm."IncidentFromDate") FROM "CaseMaster" cm' + joins +
                    ' WHERE ' + ' AND '.join(where), params)
        r = cur.fetchone()
    return r[0]


def run_near_repeat(conn, head_id: Optional[int] = None, top_cells_per_district: int = 5,
                    sigma_m: float = 500.0, tau_days: float = 7.0, theta: float = 1.0,
                    lookback_days: int = 30, horizon_days: int = 7,
                    policy_attestation=None) -> dict:
    from ..cases import analytics_policy

    attestation = policy_attestation or analytics_policy.current_attestation(conn)
    names = feat.district_names(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u WHERE u."DistrictID" IS NOT NULL')
        district_ids = sorted(int(r[0]) for r in cur.fetchall())

    mv_id = models.get_or_create_model_version(
        conn, "drishti-forecast-nearrepeat", "forecasting",
        analytics_policy.policy_model_version("1.0.0", attestation), framework="hawkes-etas",
        hyperparameters=analytics_policy.stamp(
            {"sigma_m": sigma_m, "tau_days": tau_days, "theta": theta,
             "lookback_days": lookback_days, "grid_deg": GRID_DEG}, attestation))

    rows, cells_out = [], []
    for d in district_ids:
        ref = _ref_date(conn, d, head_id)
        if ref is None:
            continue
        lat, lon, age = _recent_points(conn, d, head_id, ref, lookback_days)
        if len(lat) < 5:
            continue
        surface = _intensity_surface(lat, lon, age, sigma_m, tau_days, theta)[:top_cells_per_district]
        if not surface:
            continue
        imax = max(c["intensity"] for c in surface) or 1.0
        start = ref + dt.timedelta(days=1)
        end = start + dt.timedelta(days=horizon_days)
        for rank, c in enumerate(surface, start=1):
            conf = round(min(1.0, c["intensity"] / imax), 4)
            predicted = round(c["intensity"], 3)
            fj = analytics_policy.stamp(
                {"layer": "near_repeat", "grid_cell": [c["lat"], c["lon"]], "rank": rank,
                 "intensity": c["intensity"], "contributing_events": c["contributing_events"],
                 "sigma_m": sigma_m, "tau_days": tau_days, "ref_date": str(ref)[:10]},
                attestation)
            rows.append((mv_id, d, head_id, start, end, predicted,
                         round(min(1.0, c["intensity"] / (imax * 1.5)), 5), conf,
                         Json(fj), c["lon"], c["lon"], c["lat"]))
            cells_out.append({"district_id": d, "district": names.get(d), **c, "confidence": conf})

    analytics_policy.require_supplied_current(conn, attestation, "near-repeat forecast run")
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'near_repeat\' '
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
                page_size=300)
        models.log_inference(
            conn, mv_id, ref_table="CrimePrediction",
            inputs=analytics_policy.stamp(
                {"head_id": head_id, "sigma_m": sigma_m, "tau_days": tau_days},
                attestation),
            outputs={"cells": len(rows), "complete_generation": True})
    return {"written": len(rows), "model": "hawkes-etas", "model_version_id": mv_id,
            "cells": cells_out, "horizon_days": horizon_days,
            "analytics_policy_attestation": attestation.as_dict()}


def trigger(conn, lat: float, lon: float, when: Optional[dt.datetime] = None,
            district_id: Optional[int] = None, head_id: Optional[int] = None,
            sigma_m: float = 500.0, tau_days: float = 7.0, theta: float = 1.0,
            lookback_days: int = 30) -> dict:
    """Near-real-time: a new FIR landed at (lat,lon); recompute the LOCAL near-repeat
    surface (existing recent events + this one) and return the top affected cells."""
    when = when or dt.datetime.now(dt.timezone.utc)
    plat, plon, page = _recent_points(conn, district_id, head_id, when, lookback_days)
    # include the new event at age 0
    plat = np.append(plat, lat); plon = np.append(plon, lon); page = np.append(page, 0.0)
    # candidate cells: the new event's cell + its 8 neighbours
    c0 = _cell(lat, lon)
    cells = [(round(c0[0] + i * GRID_DEG, 5), round(c0[1] + j * GRID_DEG, 5))
             for i in (-1, 0, 1) for j in (-1, 0, 1)]
    surface = _intensity_surface(plat, plon, page, sigma_m, tau_days, theta, cells=cells)
    imax = max((c["intensity"] for c in surface), default=1.0) or 1.0
    top = [{**c, "confidence": round(min(1.0, c["intensity"] / imax), 4)} for c in surface[:5]]
    return {"event": {"lat": lat, "lon": lon, "when": when.isoformat()},
            "district_id": district_id, "head_id": head_id,
            "recent_events": int(len(plat) - 1), "affected_cells": top}
