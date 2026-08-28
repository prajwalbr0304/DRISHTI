"""Validation: PAI / hit-rate on held-out incidents + Karnataka known-pattern checks.

PAI (Prediction Accuracy Index) is the standard hotspot-forecast metric:
    PAI = (hit_rate) / (area_fraction)
where hit_rate = share of held-out incidents falling inside predicted hotspots and
area_fraction = hotspot area / study area. PAI > 1 means the hotspots concentrate
future crime better than chance; higher is better.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
from sklearn.metrics.pairwise import haversine_distances

from . import hotspots

EARTH_M = 6_371_000.0


def _points(conn, district_id, head_id, start, end):
    lon, lat, t = hotspots._fetch_points(conn, district_id, head_id, start, end, cap=5000)
    return lon, lat, t


def pai_for_cell(conn, district_id, head_id, cutoff: dt.date,
                 eps_m=1500.0, eps_days=150.0, min_samples=15) -> dict | None:
    # train = before cutoff, test = on/after cutoff
    lon_tr, lat_tr, t_tr = _points(conn, district_id, head_id, dt.date(2021, 1, 1), cutoff)
    lon_te, lat_te, _ = _points(conn, district_id, head_id, cutoff, dt.date(2026, 1, 1))
    if len(lon_tr) < min_samples or len(lon_te) < 20:
        return None
    labels = hotspots._st_dbscan(lon_tr, lat_tr, t_tr, eps_m, eps_days, min_samples)
    circles = []  # (clat, clon, radius_m)
    for lab in set(labels):
        if lab < 0:
            continue
        m = labels == lab
        clat, clon = float(lat_tr[m].mean()), float(lon_tr[m].mean())
        rad = np.radians(np.column_stack([lat_tr[m], lon_tr[m]]))
        cen = np.radians([[clat, clon]])
        d = haversine_distances(rad, cen).ravel() * EARTH_M
        r = float(np.clip(np.percentile(d, 90), 250.0, 4000.0))
        circles.append((clat, clon, r))
    if not circles:
        return None

    # hit rate on held-out points (a point is a "hit" if inside any hotspot circle)
    te = np.radians(np.column_stack([lat_te, lon_te]))
    inside = np.zeros(len(lon_te), dtype=bool)
    for clat, clon, r in circles:
        cen = np.radians([[clat, clon]])
        d = haversine_distances(te, cen).ravel() * EARTH_M
        inside |= d <= r
    hit_rate = float(inside.mean())

    hotspot_area = sum(math.pi * r * r for _, _, r in circles)
    # study area = area of the bounding circle of all training points
    all_rad = np.radians(np.column_stack([lat_tr, lon_tr]))
    c_all = np.radians([[float(lat_tr.mean()), float(lon_tr.mean())]])
    span = haversine_distances(all_rad, c_all).ravel() * EARTH_M
    study_r = max(float(span.max()), 1.0)
    study_area = math.pi * study_r * study_r
    area_fraction = min(1.0, hotspot_area / study_area)
    pai = round(hit_rate / area_fraction, 2) if area_fraction > 0 else None
    return {"district_id": district_id, "head_id": head_id, "n_train": int(len(lon_tr)),
            "n_test": int(len(lon_te)), "clusters": len(circles),
            "hit_rate": round(hit_rate, 3), "area_fraction": round(area_fraction, 4),
            "pai": pai}


def pai_report(conn, cutoff: dt.date = dt.date(2025, 1, 1), top_cells: int = 8) -> dict:
    from ..cases import casedata

    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", cm."CrimeMajorHeadID", COUNT(*) c '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'WHERE cm."geom" IS NOT NULL '
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1,2 ORDER BY c DESC LIMIT %s',
            (top_cells,))
        cells = cur.fetchall()
    results = []
    for d, h, _ in cells:
        r = pai_for_cell(conn, d, h, cutoff)
        if r:
            results.append(r)
    pais = [r["pai"] for r in results if r["pai"] is not None]
    hitrates = [r["hit_rate"] for r in results]
    return {"cutoff": str(cutoff), "cells_evaluated": len(results),
            "mean_pai": round(float(np.mean(pais)), 2) if pais else None,
            "mean_hit_rate": round(float(np.mean(hitrates)), 3) if hitrates else None,
            "per_cell": results}


def known_patterns(conn) -> dict:
    from ..cases import casedata

    out = {}
    with conn.cursor() as cur:
        # Bengaluru dominates cyber/economic
        cur.execute(
            'SELECT d."DistrictName", COUNT(*) c FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
            "WHERE ch.\"CrimeGroupName\"='Economic & Cyber Crime' "
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1 ORDER BY c DESC LIMIT 3')
        cyber = cur.fetchall()
        out["cyber_top_districts"] = [(r[0], int(r[1])) for r in cyber]
        out["bengaluru_leads_cyber"] = bool(cyber) and cyber[0][0].startswith("Bengaluru")

        # coastal districts over-represented in smuggling
        cur.execute(
            'SELECT d."DistrictName", COUNT(*) c FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
            "WHERE ch.\"CrimeGroupName\"='Smuggling & Excise' "
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1 ORDER BY c DESC LIMIT 5')
        smug = [(r[0], int(r[1])) for r in cur.fetchall()]
        out["smuggling_top_districts"] = smug
        coastal = {"Dakshina Kannada", "Udupi", "Uttara Kannada"}
        out["coastal_in_smuggling_top5"] = sorted(coastal & {d for d, _ in smug})

        # border districts in NDPS / drug offences
        cur.execute(
            'SELECT d."DistrictName", COUNT(*) c FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
            "WHERE ch.\"CrimeGroupName\"='Drug Offences' "
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1 ORDER BY c DESC LIMIT 6')
        ndps = [(r[0], int(r[1])) for r in cur.fetchall()]
        out["ndps_top_districts"] = ndps
        border = {"Belagavi", "Kalaburagi", "Bidar", "Vijayapura", "Raichur", "Yadgir", "Chamarajanagar", "Kolar"}
        out["border_in_ndps_top6"] = sorted(border & {d for d, _ in ndps})

        # festival theft spike: theft counts by calendar month
        cur.execute(
            'SELECT EXTRACT(MONTH FROM cm."CrimeRegisteredDate")::int m, COUNT(*) c '
            'FROM "CaseMaster" cm JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID" '
            "WHERE csh.\"CrimeHeadName\"='Theft' "
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1 ORDER BY 1')
        by_month = {int(r[0]): int(r[1]) for r in cur.fetchall()}
        avg = float(np.mean(list(by_month.values()))) if by_month else 0.0
        festival = {m: by_month.get(m, 0) for m in (10, 11)}
        out["theft_by_month"] = by_month
        out["theft_festival_months_above_avg"] = {m: (v > avg) for m, v in festival.items()}
    return out
