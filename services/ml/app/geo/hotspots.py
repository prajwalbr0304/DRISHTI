"""Descriptive hotspot job (doc 05 Layer 0): ST-DBSCAN clusters + KDE intensity.

For each (district, crime head) within a period we cluster the incident points
(CaseMaster.geom + IncidentFromDate) with ST-DBSCAN — dense in SPACE *and* TIME —
then score each cluster's intensity with a Gaussian KDE. Clusters are written to
CrimeHotspot as typed rows (polygon geom, centroid, intensity, case count,
period) tagged with a ModelVersion, and mv_active_hotspots is refreshed.

Libraries: scikit-learn (DBSCAN), scipy (gaussian_kde). Geometry polygons are
built server-side with PostGIS (ST_Buffer over geography) so they are valid and
CRS-correct without shapely.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
from psycopg2.extras import execute_values
from scipy.stats import gaussian_kde
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import haversine_distances

from .. import matviews, models

EARTH_M = 6_371_000.0


def _fetch_cells(conn, start, end):
    """Return {(district_id, head_id): (district_name, group_name)} with counts."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", cm."CrimeMajorHeadID", d."DistrictName", ch."CrimeGroupName", COUNT(*) '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID" = u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
            'WHERE cm."geom" IS NOT NULL AND cm."IncidentFromDate" >= %s AND cm."IncidentFromDate" < %s '
            'GROUP BY 1,2,3,4',
            (start, end),
        )
        return cur.fetchall()


def _fetch_points(conn, district_id, head_id, start, end, cap=2500):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT cm."longitude", cm."latitude", cm."IncidentFromDate" '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'WHERE u."DistrictID" = %s AND cm."CrimeMajorHeadID" = %s '
            '  AND cm."geom" IS NOT NULL '
            '  AND cm."IncidentFromDate" >= %s AND cm."IncidentFromDate" < %s '
            'ORDER BY cm."IncidentFromDate"',
            (district_id, head_id, start, end),
        )
        rows = cur.fetchall()
    if len(rows) > cap:  # deterministic stride sample keeps time coverage
        idx = np.linspace(0, len(rows) - 1, cap).astype(int)
        rows = [rows[i] for i in idx]
    lon = np.array([float(r[0]) for r in rows])
    lat = np.array([float(r[1]) for r in rows])
    t_days = np.array([r[2].timestamp() / 86400.0 for r in rows])
    return lon, lat, t_days


def _st_dbscan(lon, lat, t_days, eps_m=1500.0, eps_days=150.0, min_samples=15):
    """ST-DBSCAN via a precomputed distance: two points are neighbours iff within
    eps_m spatially AND eps_days temporally. Returns cluster labels (-1 = noise)."""
    n = len(lon)
    if n < min_samples:
        return np.full(n, -1)
    rad = np.radians(np.column_stack([lat, lon]))
    spatial_m = haversine_distances(rad) * EARTH_M
    temporal = np.abs(t_days[:, None] - t_days[None, :])
    # block pairs that violate the temporal constraint by pushing them past eps_m
    blocked = temporal > eps_days
    dist = spatial_m.copy()
    dist[blocked] = eps_m * 10.0 + 1.0
    labels = DBSCAN(eps=eps_m, min_samples=min_samples, metric="precomputed").fit_predict(dist)
    return labels


def _kde_intensity(lon, lat, cx, cy, n_cell):
    """Gaussian-KDE density at (cx,cy) scaled by cell volume -> comparable score."""
    try:
        if len(lon) < 5:
            return float(n_cell)
        kde = gaussian_kde(np.vstack([lon, lat]))
        dens = float(kde([[cx], [cy]])[0])
        return round(dens * n_cell, 4)
    except Exception:
        return float(n_cell)


def run_hotspots(conn, start: Optional[dt.date] = None, end: Optional[dt.date] = None,
                 eps_m: float = 1500.0, eps_days: float = 150.0, min_samples: int = 15) -> dict:
    start = start or dt.date(2021, 1, 1)
    end = end or dt.date(2026, 1, 1)
    mv_id = models.get_or_create_model_version(
        conn, "drishti-hotspot-kde", "clustering", "1.1.0", framework="sklearn+scipy",
        hyperparameters={"eps_m": eps_m, "eps_days": eps_days, "min_samples": min_samples,
                         "algorithm": "ST-DBSCAN + gaussian_kde"})

    cells = _fetch_cells(conn, start, end)
    rows = []
    total_clusters = 0
    for district_id, head_id, dname, gname, cnt in cells:
        if cnt < min_samples:
            continue
        lon, lat, t_days = _fetch_points(conn, district_id, head_id, start, end)
        labels = _st_dbscan(lon, lat, t_days, eps_m, eps_days, min_samples)
        for lab in sorted(set(labels)):
            if lab < 0:
                continue
            mask = labels == lab
            clon, clat = float(lon[mask].mean()), float(lat[mask].mean())
            size = int(mask.sum())
            # radius = 90th-pct distance from centroid (metres), clamped
            rad = np.radians(np.column_stack([lat[mask], lon[mask]]))
            cen = np.radians([[clat, clon]])
            dists = haversine_distances(rad, cen).ravel() * EARTH_M
            radius_m = float(np.clip(np.percentile(dists, 90), 250.0, 4000.0))
            intensity = _kde_intensity(lon, lat, clon, clat, len(lon))
            total_clusters += 1
            rows.append((f"{dname} · {gname} cluster", district_id, head_id, mv_id,
                         intensity, size, start, end, True,
                         clon, clat, radius_m, clon, clat))

    with conn.cursor() as cur:
        # idempotent: drop this model's prior surfaces; deactivate any others so
        # mv_active_hotspots reflects only the freshly computed KDE hotspots.
        cur.execute('DELETE FROM "CrimeHotspot" WHERE "ModelVersionID" = %s', (mv_id,))
        cur.execute('UPDATE "CrimeHotspot" SET "IsActive" = FALSE WHERE "IsActive" AND "ModelVersionID" <> %s', (mv_id,))
        if rows:
            execute_values(
                cur,
                'INSERT INTO "CrimeHotspot" '
                '("Name","DistrictID","CrimeHeadID","ModelVersionID","Intensity","CaseCount",'
                '"PeriodStart","PeriodEnd","IsActive","geom","Centroid") VALUES %s',
                rows,
                template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                         "ST_Buffer(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)::geometry,"
                         "ST_SetSRID(ST_MakePoint(%s,%s),4326))",
                page_size=1000,
            )
        models.log_inference(
            conn, mv_id,
            inputs={"start": str(start), "end": str(end), "eps_m": eps_m,
                    "eps_days": eps_days, "min_samples": min_samples, "cells": len(cells)},
            outputs={"hotspots_written": len(rows), "clusters": total_clusters},
            ref_table="CrimeHotspot")

    # refresh the dependent matview
    matviews.refresh_matview(conn, "mv_active_hotspots")
    return {"cells_considered": len(cells), "hotspots_written": len(rows),
            "model_version_id": mv_id}
