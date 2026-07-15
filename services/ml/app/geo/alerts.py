"""Emerging-trend alerts (doc 05 §4): where a (district, crime-head) monthly count
exceeds its own trailing rolling average by a configurable threshold, write an
AlertHistory row (Severity, Title, Payload, geom). These drive the map red-zone
pulse and the bell feed. Typed rows with a ModelVersion — auditable, not files.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import models
from . import trends


def _district_centroids(conn) -> dict[int, tuple[float, float]]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", AVG(cm."longitude"), AVG(cm."latitude") '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'WHERE cm."geom" IS NOT NULL GROUP BY u."DistrictID"'
        )
        return {int(r[0]): (float(r[1]), float(r[2])) for r in cur.fetchall()}


def _cells(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", d."DistrictName", cm."CrimeMajorHeadID", ch."CrimeGroupName", COUNT(*) '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
            'GROUP BY 1,2,3,4 HAVING COUNT(*) >= 60'
        )
        return cur.fetchall()


def _severity(z: float) -> str:
    if z >= 4.0:
        return "critical"
    if z >= 3.0:
        return "high"
    if z >= 2.5:
        return "medium"
    return "low"


def detect_and_write(conn, window: int = 6, threshold_sigma: float = 2.0,
                     recent_months: int = 12, max_alerts: int = 250) -> dict:
    """Scan every sizable (district, head) cell; write AlertHistory rows for
    months in the trailing `recent_months` whose count exceeds the trailing
    `window`-month mean by >= threshold_sigma standard deviations."""
    mv_id = models.get_or_create_model_version(
        conn, "drishti-emerging-trend", "anomaly_detection", "1.0.0", framework="numpy",
        hyperparameters={"window": window, "threshold_sigma": threshold_sigma})
    centroids = _district_centroids(conn)

    candidates = []
    for district_id, dname, head_id, gname, _cnt in _cells(conn):
        periods, counts = trends.monthly_series(conn, district_id=district_id, head_id=head_id)
        if len(counts) <= window + 1:
            continue
        arr = np.array(counts, dtype=float)
        recent_start = max(window, len(counts) - recent_months)
        for i in range(recent_start, len(counts)):
            base = arr[i - window:i]
            mu, sd = float(base.mean()), float(base.std(ddof=0))
            if sd <= 0:
                continue
            z = (arr[i] - mu) / sd
            if z >= threshold_sigma and arr[i] > mu:
                lon, lat = centroids.get(district_id, (None, None))
                pct = round((arr[i] - mu) / mu * 100, 1) if mu else None
                candidates.append({
                    "district_id": district_id, "dname": dname, "head_id": head_id,
                    "gname": gname, "period": periods[i], "count": int(arr[i]),
                    "mean": round(mu, 1), "std": round(sd, 2), "z": round(z, 2),
                    "pct": pct, "lon": lon, "lat": lat,
                    "severity": _severity(z),
                })
    # rank: severity then recency then z
    sev_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    candidates.sort(key=lambda c: (sev_rank[c["severity"]], c["period"], c["z"]), reverse=True)
    candidates = candidates[:max_alerts]

    rows = []
    for c in candidates:
        title = f"Emerging {c['gname']} spike — {c['dname']} ({c['period']})"
        msg = (f"{c['count']} cases vs trailing {window}-mo baseline {c['mean']:.0f} "
               f"(+{c['pct']}%), {c['z']:.1f}σ above average.")
        payload = {"district_id": c["district_id"], "crime_head_id": c["head_id"],
                   "period": c["period"], "count": c["count"], "baseline_mean": c["mean"],
                   "baseline_std": c["std"], "z_score": c["z"], "pct_over_baseline": c["pct"],
                   "window": window, "threshold_sigma": threshold_sigma}
        # AlertHistory has no CrimeHeadID column; the head lives in Payload.
        rows.append(("anomaly", c["severity"], title, msg, c["district_id"],
                     mv_id, Json(payload), "open", c["lon"], c["lon"], c["lat"]))

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "AlertHistory" WHERE "ModelVersionID"=%s AND "AlertType"=\'anomaly\'', (mv_id,))
        if rows:
            execute_values(
                cur,
                'INSERT INTO "AlertHistory" '
                '("AlertType","Severity","Title","Message","DistrictID",'
                '"ModelVersionID","Payload","Status","geom") VALUES %s',
                rows,
                template="(%s,%s,%s,%s,%s,%s,%s,%s,"
                         "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
                page_size=500,
            )
        models.log_inference(
            conn, mv_id,
            inputs={"window": window, "threshold_sigma": threshold_sigma, "recent_months": recent_months},
            outputs={"alerts_written": len(rows)}, ref_table="AlertHistory")
    by_sev: dict[str, int] = {}
    for c in candidates:
        by_sev[c["severity"]] = by_sev.get(c["severity"], 0) + 1
    return {"alerts_written": len(rows), "by_severity": by_sev, "model_version_id": mv_id,
            "top_examples": [{"title": rows[i][2]} for i in range(min(5, len(rows)))]}
