"""Forecasting service: runs the stacked pipeline and reads it back per layer.

run_forecast executes every layer + the transparent fusion + early warning in one
transaction. The read endpoints power the layer switcher (inspect each model
alone) and the map. Every response carries the AiResult contract + provenance.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..contracts import AiResult
from . import (earlywarning, features as feat, fusion, nearrepeat, stgnn,
               tabfm_forecast, timesfm, validation as validation_mod)
from .schemas import (DistrictForecastResponse, ForecastMapResponse, ForecastRunResponse,
                      FusedDistrict, LayerInfo, LayerPrediction, LayerRun, LayersResponse,
                      MapCell, NearRepeatCell, NearRepeatTriggerResponse, ValidationResponse)

# Features->>'layer' tag -> human label (order = pipeline order)
LAYER_ORDER = ["tabfm", "timesfm", "near_repeat", "st_gnn", "fused"]


# ---- run the whole pipeline ------------------------------------------------
def _p(msg: str) -> None:
    import sys
    print(f"[forecast] {msg}", file=sys.stderr, flush=True)


def run_forecast(head_id: Optional[int] = None, horizon_days: int = 30) -> ForecastRunResponse:
    import gc
    months = max(1, horizon_days // 30)
    with db.rw_conn() as conn:
        _p("tabfm layer ...")
        tab = tabfm_forecast.forecast(conn, head_id=head_id, horizon_days=horizon_days)
        gc.collect()
        _p(f"tabfm done ({tab.get('written')} rows); timesfm layer ...")
        tim = timesfm.forecast_trajectories(conn, head_id=head_id, horizon=max(3, months))
        gc.collect()
        _p(f"timesfm done ({tim.get('written')} rows, {tim.get('model')}); near-repeat layer ...")
        nr = nearrepeat.run_near_repeat(conn, head_id=head_id, horizon_days=min(14, horizon_days))
        _p(f"near-repeat done ({nr.get('written')} cells); st-gnn layer ...")
        stg = stgnn.run_stgnn(conn, head_id=head_id, horizon_days=horizon_days)
        gc.collect()
        _p(f"st-gnn done ({stg.get('written')} rows, {stg.get('model')}); fusion ...")
        fused = fusion.fuse(conn, head_id, tab, tim, stg, nr, horizon_days=horizon_days)
        _p(f"fusion done ({fused.get('written')} rows); early warning ...")
        ew = earlywarning.run(conn, head_id, tab, fused)
        _p(f"early warning done ({ew['alerts_written']} alerts). committing ...")

    layers = [
        LayerRun(layer="tabfm", model=tab.get("model"), model_version_id=tab.get("model_version_id"), written=tab.get("written", 0)),
        LayerRun(layer="timesfm", model=tim.get("model"), model_version_id=tim.get("model_version_id"), written=tim.get("written", 0)),
        LayerRun(layer="near_repeat", model=nr.get("model"), model_version_id=nr.get("model_version_id"), written=nr.get("written", 0)),
        LayerRun(layer="st_gnn", model=stg.get("model"), model_version_id=stg.get("model_version_id"), written=stg.get("written", 0)),
        LayerRun(layer="fused", model="stacked-inspectable", model_version_id=fused.get("model_version_id"), written=fused.get("written", 0)),
    ]
    fused_districts = [FusedDistrict(**d) for d in fused.get("districts", [])]
    high = [d for d in fused_districts if d.risk_class in ("High", "Severe")]
    mean_conf = round(sum(d.confidence for d in fused_districts) / len(fused_districts), 4) if fused_districts else 0.0
    result = AiResult(
        answer=(f"Forecast next period for {len(fused_districts)} district(s): "
                f"{len(high)} at High/Severe risk; {ew['alerts_written']} early-warning alert(s) raised."),
        confidence=mean_conf,
        source_record_ids=["CrimePrediction", "AlertHistory",
                           f"ModelVersion:{fused.get('model_version_id')}"],
        reasoning_summary=("Stacked inspectable pipeline: TabFM district risk class + TimesFM "
                           "trajectory + Hawkes near-repeat + uncertainty-aware ST-GNN spillover, "
                           "fused transparently (each cell records its contributing models + "
                           "confidence). Area/period decision support with visible confidence."),
        model_version=f"drishti-forecast-fusion@1.0.0 (id {fused.get('model_version_id')})",
    )
    return ForecastRunResponse(
        result=result, head_id=head_id, horizon_days=horizon_days,
        prediction_start=fused.get("prediction_start"), prediction_end=fused.get("prediction_end"),
        layers=layers, alerts_written=ew["alerts_written"], fused=fused_districts)


# ---- layer switcher / reads ------------------------------------------------
def list_layers() -> LayersResponse:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT cp."Features"->>\'layer\' AS layer, mv."ModelName", cp."ModelVersionID", COUNT(*), '
                'MAX(EXTRACT(EPOCH FROM (cp."PredictionEnd"-cp."PredictionStart"))/86400)::int '
                'FROM "CrimePrediction" cp JOIN "ModelVersion" mv ON mv."ModelVersionID"=cp."ModelVersionID" '
                'WHERE cp."Features" ? \'layer\' '
                'GROUP BY 1,2,3 ORDER BY 1')
            rows = cur.fetchall()
    order = {l: i for i, l in enumerate(LAYER_ORDER)}
    infos = sorted((LayerInfo(layer=r[0], model_name=r[1], model_version_id=int(r[2]),
                              predictions=int(r[3]), horizon_days=int(r[4]) if r[4] is not None else None)
                    for r in rows), key=lambda x: order.get(x.layer, 99))
    result = AiResult(
        answer=f"{len(infos)} forecast layer(s) available for inspection.",
        confidence=1.0, source_record_ids=[f"ModelVersion:{i.model_version_id}" for i in infos],
        reasoning_summary="Each layer is a separately-auditable model version writing to CrimePrediction; "
                          "the fusion combines them transparently.",
        model_version="drishti-forecast-fusion@1.0.0")
    return LayersResponse(result=result, layers=infos)


def district_forecast(district_id: int, head_id: Optional[int] = None,
                      layer: Optional[str] = None) -> Optional[DistrictForecastResponse]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s', (district_id,))
            row = cur.fetchone()
            if not row:
                return None
            dname = row[0]
            q = ('SELECT DISTINCT ON (cp."Features"->>\'layer\') cp."Features"->>\'layer\', mv."ModelName", '
                 'cp."PredictedCount", cp."Probability", cp."Confidence", cp."Features", '
                 'cp."PredictionStart"::text, cp."PredictionEnd"::text '
                 'FROM "CrimePrediction" cp JOIN "ModelVersion" mv ON mv."ModelVersionID"=cp."ModelVersionID" '
                 'WHERE cp."DistrictID"=%s AND cp."CrimeHeadID" IS NOT DISTINCT FROM %s AND cp."Features" ? \'layer\'')
            args = [district_id, head_id]
            if layer:
                q += ' AND cp."Features"->>\'layer\'=%s'
                args.append(layer)
            q += ' ORDER BY cp."Features"->>\'layer\', cp."PredictionStart" DESC'
            cur.execute(q, args)
            rows = cur.fetchall()
    order = {l: i for i, l in enumerate(LAYER_ORDER)}
    preds = sorted((LayerPrediction(
        layer=r[0], model_name=r[1],
        predicted_count=float(r[2]) if r[2] is not None else None,
        probability=float(r[3]) if r[3] is not None else None,
        confidence=float(r[4]) if r[4] is not None else None,
        features=r[5] or {}, prediction_start=r[6], prediction_end=r[7]) for r in rows),
        key=lambda x: order.get(x.layer, 99))
    fused = next((p for p in preds if p.layer == "fused"), None)
    result = AiResult(
        answer=(f"{dname}: {len(preds)} forecast layer(s)"
                + (f"; fused next-period count ~{fused.predicted_count} "
                   f"({(fused.features or {}).get('tabfm_risk_class')} risk)." if fused else ".")),
        confidence=fused.confidence if fused else (preds[0].confidence if preds else 0.0),
        source_record_ids=[f"CrimePrediction:district:{district_id}"],
        reasoning_summary="Per-layer forecasts for the district (layer switcher); the fused row lists "
                          "its contributing models + confidence for the Evidence Trail.",
        model_version="drishti-forecast-fusion@1.0.0")
    return DistrictForecastResponse(result=result, district_id=district_id, district=dname,
                                    head_id=head_id, layers=preds)


def forecast_map(layer: str = "fused", head_id: Optional[int] = None,
                 bbox: Optional[tuple] = None) -> ForecastMapResponse:
    q = ('SELECT cp."PredictionID", cp."DistrictID", ST_Y(cp."geom"), ST_X(cp."geom"), '
         'cp."PredictedCount", cp."Confidence", '
         'COALESCE(cp."Features"->>\'risk_class\', cp."Features"->>\'tabfm_risk_class\') '
         'FROM "CrimePrediction" cp '
         'WHERE cp."Features"->>\'layer\'=%s AND cp."CrimeHeadID" IS NOT DISTINCT FROM %s '
         'AND cp."geom" IS NOT NULL')
    args = [layer, head_id]
    if bbox:
        q += ' AND cp."geom" && ST_MakeEnvelope(%s,%s,%s,%s,4326)'
        args += list(bbox)
    q += ' ORDER BY cp."PredictedCount" DESC LIMIT 2000'
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, args)
            rows = cur.fetchall()
    cells = [MapCell(prediction_id=int(r[0]), district_id=int(r[1]) if r[1] is not None else None,
                     lat=float(r[2]) if r[2] is not None else None,
                     lon=float(r[3]) if r[3] is not None else None,
                     predicted_count=float(r[4]) if r[4] is not None else None,
                     confidence=float(r[5]) if r[5] is not None else None, risk_class=r[6])
             for r in rows]
    result = AiResult(
        answer=f"{len(cells)} forecast cell(s) for layer '{layer}'.",
        confidence=round(sum(c.confidence or 0 for c in cells) / len(cells), 4) if cells else 0.0,
        source_record_ids=[f"CrimePrediction:{c.prediction_id}" for c in cells[:50]],
        reasoning_summary=f"Server-side aggregated '{layer}' forecast cells for the map, with confidence.",
        model_version="drishti-forecast@1.0.0")
    return ForecastMapResponse(result=result, layer=layer, head_id=head_id, count=len(cells), cells=cells)


# ---- near-real-time near-repeat trigger ------------------------------------
def near_repeat_trigger(lat: float, lon: float, district_id: Optional[int] = None,
                        head_id: Optional[int] = None, when: Optional[dt.datetime] = None) -> NearRepeatTriggerResponse:
    with db.ro_conn() as conn:
        payload = nearrepeat.trigger(conn, lat, lon, when=when, district_id=district_id, head_id=head_id)
    cells = [NearRepeatCell(**c) for c in payload["affected_cells"]]
    top = cells[0].confidence if cells else 0.0
    result = AiResult(
        answer=(f"A new event at ({lat:.4f},{lon:.4f}) raises near-repeat risk in "
                f"{len(cells)} nearby cell(s)."),
        confidence=round(float(top), 4),
        source_record_ids=[f"grid:{c.lat},{c.lon}" for c in cells],
        reasoning_summary=("Self-exciting (Hawkes/ETAS) recompute of the local grid intensity from "
                           f"{payload['recent_events']} recent event(s) + the new one — short-horizon."),
        model_version="drishti-forecast-nearrepeat@1.0.0")
    return NearRepeatTriggerResponse(result=result, event=payload["event"],
                                     district_id=district_id, head_id=head_id,
                                     recent_events=payload["recent_events"], affected_cells=cells)


# ---- validation ------------------------------------------------------------
def validation(cutoff: Optional[dt.date] = None, horizon_months: int = 3,
               area_fraction: float = 0.25) -> ValidationResponse:
    kwargs = {"horizon_months": horizon_months, "area_fraction": area_fraction}
    if cutoff:
        kwargs["cutoff"] = cutoff
    with db.ro_conn() as conn:
        rep = validation_mod.forecast_pai(conn, **kwargs)
    overall = rep.get("overall") or {}
    result = AiResult(
        answer=(f"Held-out forecast PAI {overall.get('pai')} (hit-rate {overall.get('hit_rate')}) "
                f"flagging the top {int(rep['area_fraction']*100)}% of cells after {rep['cutoff']}."),
        confidence=round(float(overall.get("hit_rate") or 0.0), 4),
        source_record_ids=["CaseMaster"],
        reasoning_summary="PAI = hit-rate / area-fraction on incidents held out after the cutoff, "
                          "per district & crime head. PAI > 1 beats chance.",
        model_version="drishti-forecast@1.0.0")
    return ValidationResponse(result=result, cutoff=rep["cutoff"], horizon_months=rep["horizon_months"],
                              area_fraction=rep["area_fraction"], overall=rep.get("overall"),
                              per_crime_head=rep.get("per_crime_head", {}))
