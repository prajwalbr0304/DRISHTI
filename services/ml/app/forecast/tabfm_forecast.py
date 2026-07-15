"""TabFM district forecast layer (doc 05 §3, doc 02 §4).

The tabular question: given a district's recent time-series features + socio-
economic overlay, what is next period's risk CLASS? The Phase-9 foundation model
(TabFM -> TabPFN -> in-context, resolved at call time) is fit zero-shot on the
historical (features_t -> class_{t+1}) pairs and predicts the latest row per
district. Results are the district-level expectation the fusion step distributes
over geometry. Written to CrimePrediction with a ModelVersion + audit.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import models
from ..risk import models_iface as mi
from ..risk.scoring import _stratified_context
from . import features as feat

MODEL_TYPE = "forecasting"


def _next_window(last_period: str, horizon_days: int) -> tuple[dt.datetime, dt.datetime]:
    y, m = map(int, last_period.split("-"))
    start = dt.datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(days=horizon_days)


def forecast(conn, head_id: Optional[int] = None, window: int = 6, horizon_days: int = 30,
             context_size: int = 1000, foundation_estimators: Optional[int] = None,
             seed: int = 42) -> dict:
    data = feat.build(conn, head_id=head_id, window=window)
    Xc, yc, Xl, meta = data["X_ctx"], data["y_ctx"], data["X_latest"], data["meta"]
    if len(Xl) == 0:
        return {"written": 0, "districts": [], "note": "insufficient history"}

    model = mi.get_foundation_model(n_estimators=foundation_estimators)
    sel = _stratified_context(Xc, yc, n=context_size, seed=seed)
    model.fit(Xc[sel], yc[sel])
    proba = model.predict_proba(Xl)                       # (n_districts, 5)

    centroids = feat.district_centroids(conn)
    mv_id = models.get_or_create_model_version(
        conn, "drishti-forecast-tabfm", MODEL_TYPE, "1.0.0", framework=model.family,
        hyperparameters={"window": window, "classes": feat.RISK_CLASSES,
                         "features": feat.FEATURE_NAMES, "context_size": int(len(sel))},
        metrics={"districts": len(meta)})

    start, end = _next_window(meta[0]["last_period"], horizon_days)
    districts, rows = [], []
    for i, m in enumerate(meta):
        p = proba[i]
        exp_class = float((p * np.arange(mi.N_CLASSES)).sum())
        cls = int(p.argmax())
        # PredictedCount: recent level nudged by the expected risk class
        predicted = max(0.0, m["recent_mean"] * (0.7 + 0.15 * exp_class))
        prob_elevated = float(p[2] + p[3] + p[4])         # P(Elevated+)
        confidence = float(p.max())
        lon, lat = centroids.get(m["district_id"], (None, None))
        features_json = {
            "layer": "tabfm", "risk_class": feat.RISK_CLASSES[cls], "risk_class_id": cls,
            "expected_class": round(exp_class, 3),
            "class_probs": {feat.RISK_CLASSES[c]: round(float(p[c]), 4) for c in range(mi.N_CLASSES)},
            "features": {feat.FEATURE_NAMES[j]: round(float(Xl[i][j]), 4) for j in range(len(feat.FEATURE_NAMES))},
            "model": model.name, "last_period": m["last_period"], "recent_mean": m["recent_mean"],
        }
        districts.append({
            "district_id": m["district_id"], "district": m["district"],
            "risk_class": feat.RISK_CLASSES[cls], "predicted_count": round(predicted, 2),
            "probability": round(prob_elevated, 4), "confidence": round(confidence, 4),
            "class_probs": features_json["class_probs"]})
        # geom template references lon twice (null-check + MakePoint), then lat
        rows.append((mv_id, m["district_id"], head_id, start, end, round(predicted, 2),
                     round(prob_elevated, 5), round(confidence, 5), Json(features_json),
                     lon, lon, lat))

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'tabfm\' '
                    'AND "CrimeHeadID" IS NOT DISTINCT FROM %s', (head_id,))
        execute_values(
            cur,
            'INSERT INTO "CrimePrediction" ("ModelVersionID","DistrictID","CrimeHeadID",'
            '"PredictionStart","PredictionEnd","PredictedCount","Probability","Confidence",'
            '"Features","geom") VALUES %s',
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                     "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
            page_size=200)

    models.log_inference(
        conn, mv_id, ref_table="CrimePrediction",
        inputs={"head_id": head_id, "window": window, "horizon_days": horizon_days,
                "context_size": int(len(sel))},
        outputs={"districts": len(rows), "model": model.name})

    return {"written": len(rows), "model": model.name, "model_version_id": mv_id,
            "prediction_start": start.isoformat(), "prediction_end": end.isoformat(),
            "districts": districts}
