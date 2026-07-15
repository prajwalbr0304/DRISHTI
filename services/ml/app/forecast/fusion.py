"""Transparent, inspectable fusion (doc 05 §3).

NOT a mystery ensemble: TabFM sets the district-level expectation; the temporal
(TimesFM) and spatio-temporal (ST-GNN) layers refine it, and near-repeat adds a
short-term spike flag where recent events cluster. Every fused district cell
records its CONTRIBUTING MODELS (each with its own prediction, confidence and
ModelVersion) so the Evidence Trail can show exactly how the number was formed,
and each layer remains independently inspectable (layer switcher).
"""
from __future__ import annotations

import datetime as dt

from psycopg2.extras import Json, execute_values

from .. import models
from . import features as feat

DEFAULT_WEIGHTS = {"tabfm": 0.4, "timesfm": 0.3, "st_gnn": 0.3}


def fuse(conn, head_id, tabfm_res, timesfm_res, stgnn_res, nearrepeat_res,
         weights=None, horizon_days: int = 30) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    centroids = feat.district_centroids(conn)
    names = feat.district_names(conn)

    tab = {r["district_id"]: r for r in tabfm_res.get("districts", [])}
    tim = {r["district_id"]: r for r in timesfm_res.get("trajectories", [])}
    stg = {r["district_id"]: r for r in stgnn_res.get("districts", [])}
    # near-repeat: top cell intensity per district
    nr_by_d: dict[int, dict] = {}
    for c in nearrepeat_res.get("cells", []):
        d = c["district_id"]
        if d not in nr_by_d or c["intensity"] > nr_by_d[d]["intensity"]:
            nr_by_d[d] = c

    mv_id = models.get_or_create_model_version(
        conn, "drishti-forecast-fusion", "forecasting", "1.0.0", framework="stacked-inspectable",
        hyperparameters={"weights": weights, "anchor": "tabfm",
                         "layers": ["tabfm", "timesfm", "st_gnn", "near_repeat"]})

    start = end = None
    rows, out = [], []
    for d, t in tab.items():
        contribs = []
        num = den = conf_sum = 0.0
        for layer, res_row, mvid, cnt in (
                ("tabfm", t, tabfm_res.get("model_version_id"), t.get("predicted_count")),
                ("timesfm", tim.get(d), timesfm_res.get("model_version_id"),
                 (tim.get(d) or {}).get("next_median")),
                ("st_gnn", stg.get(d), stgnn_res.get("model_version_id"),
                 (stg.get(d) or {}).get("mean"))):
            if res_row is None or cnt is None:
                continue
            w = weights.get(layer, 0.0)
            conf = float(res_row.get("confidence", 0.0))
            num += w * float(cnt); den += w; conf_sum += conf
            contribs.append({"layer": layer, "model_version_id": mvid,
                             "predicted_count": round(float(cnt), 2), "confidence": round(conf, 4)})
        if den == 0:
            continue
        fused_count = round(num / den, 2)
        fused_conf = round(conf_sum / len(contribs), 4)
        spike = nr_by_d.get(d)
        fj = {"layer": "fused", "contributing_models": contribs, "weights": weights,
              "tabfm_risk_class": t.get("risk_class"), "fused_count": fused_count,
              "near_term_spike": bool(spike),
              "near_repeat_top_cell": ({"lat": spike["lat"], "lon": spike["lon"],
                                        "intensity": spike["intensity"]} if spike else None)}
        lon, lat = centroids.get(d, (None, None))
        # fused window follows TabFM's
        start = tabfm_res.get("prediction_start"); end = tabfm_res.get("prediction_end")
        rows.append((mv_id, d, head_id, start, end, fused_count,
                     round(min(1.0, fused_count / (max(1.0, t.get("predicted_count", 1) * 2))), 5),
                     fused_conf, Json(fj), lon, lon, lat))
        out.append({"district_id": d, "district": names.get(d), "fused_count": fused_count,
                    "confidence": fused_conf, "risk_class": t.get("risk_class"),
                    "contributing_models": [c["layer"] for c in contribs],
                    "near_term_spike": bool(spike)})

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'fused\' '
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
                             inputs={"head_id": head_id, "weights": weights},
                             outputs={"districts": len(rows)})
    return {"written": len(rows), "model": "stacked-inspectable", "model_version_id": mv_id,
            "districts": out, "prediction_start": start, "prediction_end": end}
