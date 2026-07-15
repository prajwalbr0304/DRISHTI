"""Early warning: forecast threshold breaches -> AlertHistory (doc 05 §4).

When the fused/TabFM forecast puts a district into a High/Severe next-period risk
class (or its elevated-probability crosses a threshold), an AlertType='prediction'
row is written — this drives the map red-zone pulse and the bell feed. The active
hotspots matview is refreshed afterwards so downstream dashboards reflect the new
state.
"""
from __future__ import annotations

from psycopg2.extras import Json, execute_values

from .. import matviews, models
from . import features as feat

_SEV = {"Severe": "critical", "High": "high", "Elevated": "medium"}
_SEV_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0, "info": 0}


def run(conn, head_id, tabfm_res, fused_res, prob_threshold: float = 0.6,
        max_alerts: int = 100) -> dict:
    centroids = feat.district_centroids(conn)
    fused_by_d = {r["district_id"]: r for r in fused_res.get("districts", [])}

    mv_id = models.get_or_create_model_version(
        conn, "drishti-early-warning", "anomaly_detection", "1.0.0", framework="threshold",
        hyperparameters={"prob_threshold": prob_threshold, "trigger": "risk_class>=High or P(elevated+)>=thr"})

    candidates = []
    for r in tabfm_res.get("districts", []):
        cls, prob = r["risk_class"], float(r.get("probability", 0.0))
        if cls in ("High", "Severe") or prob >= prob_threshold:
            sev = _SEV.get(cls, "medium")
            fused = fused_by_d.get(r["district_id"], {})
            candidates.append({
                "district_id": r["district_id"], "district": r["district"], "severity": sev,
                "risk_class": cls, "probability": prob,
                "fused_count": fused.get("fused_count"), "confidence": r.get("confidence"),
                "rank": _SEV_RANK[sev] * 1000 + prob})
    candidates.sort(key=lambda c: c["rank"], reverse=True)
    candidates = candidates[:max_alerts]

    rows = []
    for c in candidates:
        lon, lat = centroids.get(c["district_id"], (None, None))
        title = f"Forecast: {c['risk_class']} risk next period — {c['district']}"
        msg = (f"{c['district']} is forecast {c['risk_class']} "
               f"(P(elevated+)={c['probability']:.0%}, fused count ~{c['fused_count']}).")
        payload = {"risk_class": c["risk_class"], "probability": round(c["probability"], 4),
                   "fused_count": c["fused_count"], "confidence": c["confidence"],
                   "crime_head_id": head_id}
        rows.append(("prediction", c["severity"], title, msg, c["district_id"], mv_id,
                     Json(payload), "open", lon, lon, lat))

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "AlertHistory" WHERE "ModelVersionID"=%s '
                    'AND "AlertType"=\'prediction\'', (mv_id,))
        if rows:
            execute_values(
                cur,
                'INSERT INTO "AlertHistory" ("AlertType","Severity","Title","Message",'
                '"DistrictID","ModelVersionID","Payload","Status","geom") VALUES %s',
                rows,
                template="(%s,%s,%s,%s,%s,%s,%s,%s,"
                         "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
                page_size=200)
        models.log_inference(conn, mv_id, ref_table="AlertHistory",
                             inputs={"head_id": head_id, "prob_threshold": prob_threshold},
                             outputs={"alerts": len(rows)})

    # refresh the active-hotspots matview (own txn inside helper)
    refreshed = matviews.refresh_matview(conn, "mv_active_hotspots")
    by_sev = {}
    for c in candidates:
        by_sev[c["severity"]] = by_sev.get(c["severity"], 0) + 1
    return {"alerts_written": len(rows), "by_severity": by_sev, "model_version_id": mv_id,
            "matview_refresh": refreshed}
