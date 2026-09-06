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
from ..geo import geoscope
from . import (backtest as backtest_mod, context as context_mod, earlywarning,
               features as feat, fusion, governance_bridge, nearrepeat, stgnn,
               tabfm_forecast, timesfm, validation as validation_mod)
from .schemas import (BacktestResponse, DistrictForecastResponse, ForecastMapResponse,
                      ForecastRunResponse, FreshnessResponse, FusedDistrict, GovernedPersistence,
                      LayerInfo, LayerPrediction, LayerRun, LayersResponse, MapCell, NearRepeatCell,
                      NearRepeatTriggerResponse, ValidationResponse)

# Features->>'layer' tag -> human label (order = pipeline order)
LAYER_ORDER = ["tabfm", "timesfm", "near_repeat", "st_gnn", "fused"]
_LAYER_MODEL_NAMES = {
    "tabfm": ["drishti-forecast-tabfm"],
    "timesfm": ["drishti-timesfm-seasonal", "drishti-timesfm-2.5-200m"],
    "near_repeat": ["drishti-forecast-nearrepeat"],
    "st_gnn": ["drishti-forecast-stgnn"],
    "fused": ["drishti-forecast-fusion"],
}


class UnknownForecastLayer(ValueError):
    pass


def _layer_generation(conn, layer: str, head_id, current):
    from ..cases import analytics_policy

    names = _LAYER_MODEL_NAMES.get(layer)
    if names is None:
        raise UnknownForecastLayer(f"Unknown persisted forecast layer '{layer}'.")
    return analytics_policy.latest_complete_generation(
        conn, model_names=names, ref_table="CrimePrediction",
        artifact=f"forecast layer '{layer}'", scope={"head_id": head_id},
        current=current)


def _validate_prediction_metadata(conn, prediction_id, features, hyperparameters, current) -> None:
    from ..cases import analytics_policy

    analytics_policy.require_current(
        conn, features, f"CrimePrediction {prediction_id}", current=current)
    analytics_policy.require_current(
        conn, hyperparameters, f"CrimePrediction {prediction_id} model", current=current)


# ---- run the whole pipeline ------------------------------------------------
def _p(msg: str) -> None:
    import sys
    print(f"[forecast] {msg}", file=sys.stderr, flush=True)


def run_forecast(head_id: Optional[int] = None, horizon_days: int = 30,
                 persist_governed: bool = True) -> ForecastRunResponse:
    import gc

    from ..cases import analytics_policy

    months = max(1, horizon_days // 30)
    with db.rw_conn() as conn:
        attestation = analytics_policy.current_attestation(conn)
        _p("tabfm layer ...")
        tab = tabfm_forecast.forecast(
            conn, head_id=head_id, horizon_days=horizon_days,
            policy_attestation=attestation)
        gc.collect()
        _p(f"tabfm done ({tab.get('written')} rows); timesfm layer ...")
        tim = timesfm.forecast_trajectories(
            conn, head_id=head_id, horizon=max(3, months),
            policy_attestation=attestation)
        gc.collect()
        _p(f"timesfm done ({tim.get('written')} rows, {tim.get('model')}); near-repeat layer ...")
        nr = nearrepeat.run_near_repeat(
            conn, head_id=head_id, horizon_days=min(14, horizon_days),
            policy_attestation=attestation)
        _p(f"near-repeat done ({nr.get('written')} cells); st-gnn layer ...")
        stg = stgnn.run_stgnn(
            conn, head_id=head_id, horizon_days=horizon_days,
            policy_attestation=attestation)
        gc.collect()
        _p(f"st-gnn done ({stg.get('written')} rows, {stg.get('model')}); fusion ...")
        fused = fusion.fuse(
            conn, head_id, tab, tim, stg, nr, horizon_days=horizon_days,
            policy_attestation=attestation)
        _p(f"fusion done ({fused.get('written')} rows); early warning ...")
        ew = earlywarning.run(
            conn, head_id, tab, fused, policy_attestation=attestation)
        analytics_policy.require_supplied_current(conn, attestation, "complete forecast run")
        _p(f"early warning done ({ew['alerts_written']} alerts). committing ...")

    layers = [
        LayerRun(layer="tabfm", model=tab.get("model"), model_version_id=tab.get("model_version_id"), written=tab.get("written", 0)),
        LayerRun(layer="timesfm", model=tim.get("model"), model_version_id=tim.get("model_version_id"), written=tim.get("written", 0)),
        LayerRun(layer="near_repeat", model=nr.get("model"), model_version_id=nr.get("model_version_id"), written=nr.get("written", 0)),
        LayerRun(layer="st_gnn", model=stg.get("model"), model_version_id=stg.get("model_version_id"), written=stg.get("written", 0)),
        LayerRun(layer="fused", model="stacked-inspectable", model_version_id=fused.get("model_version_id"), written=fused.get("written", 0)),
    ]
    # Persist the fused forecast through the governed contract in its own
    # transaction, but do not downgrade a policy mismatch to an optional warning.
    governed_summary = None
    if persist_governed:
        try:
            with db.rw_conn() as gconn:
                gv = governance_bridge.persist_forecast(
                    gconn, districts=fused.get("districts", []), head_id=head_id,
                    prediction_start=fused.get("prediction_start"),
                    prediction_end=fused.get("prediction_end"), horizon_days=horizon_days,
                    model_metrics={"layers_written": {l.layer: l.written for l in layers}},
                    policy_attestation=attestation)
            governed_summary = GovernedPersistence(**gv)
        except analytics_policy.DerivedArtifactUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — non-policy governance remains advisory
            _p(f"governed persistence skipped: {type(exc).__name__}: {exc}")
            governed_summary = GovernedPersistence(error=f"{type(exc).__name__}: {exc}")

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
        layers=layers, alerts_written=ew["alerts_written"], fused=fused_districts,
        governed=governed_summary)


# ---- layer switcher / reads ------------------------------------------------
def list_layers() -> LayersResponse:
    from ..cases import analytics_policy

    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        manifests = {layer: _layer_generation(conn, layer, None, current)
                     for layer in LAYER_ORDER}
        with conn.cursor() as cur:
            cur.execute(
                'SELECT cp."PredictionID",cp."Features"->>\'layer\' AS layer,mv."ModelName",'
                'cp."ModelVersionID",'
                'EXTRACT(EPOCH FROM (cp."PredictionEnd"-cp."PredictionStart"))/86400,'
                'cp."Features",mv."Hyperparameters" '
                'FROM "CrimePrediction" cp '
                'JOIN "ModelVersion" mv ON mv."ModelVersionID"=cp."ModelVersionID" '
                'WHERE cp."Features" ? \'layer\' AND cp."CrimeHeadID" IS NULL '
                'ORDER BY cp."PredictionID"')
            rows = cur.fetchall()
        grouped: dict[tuple[str, str, int], dict] = {}
        for row in rows:
            if row[1] not in _LAYER_MODEL_NAMES:
                raise analytics_policy.DerivedArtifactUnavailable(
                    f"CrimePrediction {row[0]} has unclassified forecast layer {row[1]!r}.")
            _validate_prediction_metadata(conn, row[0], row[5], row[6], current)
            key = (row[1], row[2], int(row[3]))
            item = grouped.setdefault(key, {"count": 0, "horizon": None})
            item["count"] += 1
            if row[4] is not None:
                days = int(row[4])
                item["horizon"] = max(item["horizon"] or days, days)

    infos = [LayerInfo(layer=layer, model_name=model_name, model_version_id=model_version_id,
                       predictions=item["count"], horizon_days=item["horizon"])
             for (layer, model_name, model_version_id), item in grouped.items()]
    present = {info.layer for info in infos}
    for layer in LAYER_ORDER:
        if layer not in present:
            manifest = manifests[layer]
            infos.append(LayerInfo(
                layer=layer, model_name=manifest["model_name"],
                model_version_id=manifest["model_version_id"], predictions=0,
                horizon_days=None))
    order = {layer: i for i, layer in enumerate(LAYER_ORDER)}
    infos.sort(key=lambda item: order.get(item.layer, 99))
    result = AiResult(
        answer=f"{len(infos)} forecast layer(s) available for inspection.",
        confidence=1.0, source_record_ids=[f"ModelVersion:{i.model_version_id}" for i in infos],
        reasoning_summary="Each layer is a separately-auditable model version writing to CrimePrediction; "
                          "the fusion combines them transparently.",
        model_version="drishti-forecast-fusion@1.0.0")
    return LayersResponse(result=result, layers=infos)


def district_forecast(district_id: int, head_id: Optional[int] = None,
                      layer: Optional[str] = None) -> Optional[DistrictForecastResponse]:
    from ..cases import analytics_policy

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s', (district_id,))
            row = cur.fetchone()
            if not row:
                return None
            dname = row[0]
        current = analytics_policy.current_attestation(conn)
        requested_layers = [layer] if layer else LAYER_ORDER
        for requested_layer in requested_layers:
            _layer_generation(conn, requested_layer, head_id, current)
        q = ('SELECT DISTINCT ON (cp."Features"->>\'layer\') cp."PredictionID",'
             'cp."Features"->>\'layer\',mv."ModelName",cp."PredictedCount",'
             'cp."Probability",cp."Confidence",cp."Features",'
             'cp."PredictionStart"::text,cp."PredictionEnd"::text,mv."Hyperparameters" '
             'FROM "CrimePrediction" cp '
             'JOIN "ModelVersion" mv ON mv."ModelVersionID"=cp."ModelVersionID" '
             'WHERE cp."DistrictID"=%s AND cp."CrimeHeadID" IS NOT DISTINCT FROM %s '
             'AND cp."Features" ? \'layer\'')
        args = [district_id, head_id]
        if layer:
            q += ' AND cp."Features"->>\'layer\'=%s'
            args.append(layer)
        q += ' ORDER BY cp."Features"->>\'layer\', cp."PredictionStart" DESC'
        with conn.cursor() as cur:
            cur.execute(q, args)
            rows = cur.fetchall()
        for row in rows:
            _validate_prediction_metadata(conn, row[0], row[6], row[9], current)
    order = {name: i for i, name in enumerate(LAYER_ORDER)}
    preds = sorted((LayerPrediction(
        layer=r[1], model_name=r[2],
        predicted_count=float(r[3]) if r[3] is not None else None,
        probability=float(r[4]) if r[4] is not None else None,
        confidence=float(r[5]) if r[5] is not None else None,
        features=r[6] or {}, prediction_start=r[7], prediction_end=r[8]) for r in rows),
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
                 bbox: Optional[tuple] = None,
                 district_ids: Optional[list] = None) -> ForecastMapResponse:
    """Forecast cells for the map, optionally confined to a seat's districts.

    ``district_ids`` is the SEAT's confinement. An EMPTY list means a seat entitled
    to nothing and yields no cells, rather than being ignored and returning the
    whole state.
    """
    from ..cases import analytics_policy

    q = ('SELECT cp."PredictionID", cp."DistrictID", ST_Y(cp."geom"), ST_X(cp."geom"), '
         'cp."PredictedCount", cp."Confidence", '
         'COALESCE(cp."Features"->>\'risk_class\', cp."Features"->>\'tabfm_risk_class\'), '
         'cp."Features",mv."Hyperparameters" '
         'FROM "CrimePrediction" cp '
         'JOIN "ModelVersion" mv ON mv."ModelVersionID"=cp."ModelVersionID" '
         'WHERE cp."Features"->>\'layer\'=%s AND cp."CrimeHeadID" IS NOT DISTINCT FROM %s '
         'AND cp."geom" IS NOT NULL')
    args = [layer, head_id]
    if district_ids is not None:
        if not district_ids:
            q += ' AND FALSE'
        else:
            q += ' AND cp."DistrictID" = ANY(%s)'
            args.append([int(d) for d in district_ids])
    if bbox:
        q += ' AND cp."geom" && ST_MakeEnvelope(%s,%s,%s,%s,4326)'
        args += list(bbox)
    q += ' ORDER BY cp."PredictedCount" DESC LIMIT 2000'
    with db.ro_conn() as conn:
        current = analytics_policy.current_attestation(conn)
        _layer_generation(conn, layer, head_id, current)
        with conn.cursor() as cur:
            cur.execute(q, args)
            rows = cur.fetchall()
        for row in rows:
            _validate_prediction_metadata(conn, row[0], row[7], row[8], current)
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


# ---- rolling-origin backtest (MAE/RMSE/WAPE/sMAPE + coverage + baselines) ---
def backtest(head_id: Optional[int] = None, horizon: int = 1, n_origins: int = 6,
             per_head: bool = True, persist: bool = True) -> BacktestResponse:
    """Rolling-origin, leakage-safe backtest with geographic holdout, baseline
    comparison and per-dimension error. Optionally persists a ForecastBacktest."""
    from ..cases import analytics_policy

    with db.rw_conn() as conn:
        attestation = analytics_policy.current_attestation(conn)
        report = backtest_mod.backtest_report(conn, head_id=head_id, horizon=horizon,
                                              n_origins=n_origins, per_head=per_head)
        analytics_policy.require_supplied_current(conn, attestation, "forecast backtest")
        persisted_id = None
        if persist:
            try:
                persisted_id = governance_bridge.persist_backtest(
                    conn, report, head_id=head_id, actor="forecast-batch",
                    policy_attestation=attestation)
            except analytics_policy.DerivedArtifactUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 — non-policy persistence remains advisory
                _p(f"backtest persistence skipped: {type(exc).__name__}: {exc}")

    m = report.get("model") or {}
    skill = report.get("skill_vs_baselines") or {}
    naive_skill = (skill.get("seasonal_naive") or {}).get("mae_skill")
    result = AiResult(
        answer=(f"Rolling-origin backtest over {report.get('scored_points', 0)} held-out "
                f"district-months: MAE {m.get('mae')}, RMSE {m.get('rmse')}, WAPE {m.get('wape')}, "
                f"sMAPE {m.get('smape')}%, 80% interval coverage {m.get('coverage_80')}. "
                f"Beats all simple baselines: {report.get('beats_all_baselines')}."),
        confidence=round(float(m.get("coverage_80") or 0.0), 4),
        source_record_ids=["CaseMaster", "ForecastBacktest"
                           + (f":{persisted_id}" if persisted_id else "")],
        reasoning_summary=("Walk-forward origins: the forecaster sees only pre-cutoff months and "
                           "predicts the next horizon; held-out actuals score MAE/RMSE/WAPE/sMAPE "
                           "and interval coverage, versus seasonal-naive + moving-average baselines, "
                           "with a geographic holdout. Valid geography only; aggregate, never "
                           "person-level."),
        model_version=f"{m.get('name', 'drishti-forecast')}@1.0.0"
                      + (f" (mae_skill vs naive {naive_skill})" if naive_skill is not None else ""))
    return BacktestResponse(
        result=result, scope=report.get("scope", {}), n_series=report.get("n_series", 0),
        origins=report.get("origins", []), scored_points=report.get("scored_points", 0),
        cells_considered=report.get("cells_considered", 0),
        abstained_cells=report.get("abstained_cells", 0),
        abstention_rate=report.get("abstention_rate", 0.0), model=m,
        baselines=report.get("baselines", {}), skill_vs_baselines=skill,
        beats_all_baselines=report.get("beats_all_baselines"),
        error_by_district=report.get("error_by_district", []),
        error_by_season=report.get("error_by_season", {}),
        error_by_head=report.get("error_by_head", {}),
        geo_holdout=report.get("geo_holdout", {}), persisted_backtest_id=persisted_id)


# ---- data freshness + approved external context -----------------------------
def freshness() -> FreshnessResponse:
    """Data-as-of per source, approved external-context versions, and the
    valid-geography scope applied to every forecast."""
    with db.ro_conn() as conn:
        fr = context_mod.data_freshness(conn)
        scope = geoscope.scope_summary(conn)
    stale = fr.get("case_data_stale_days")
    result = AiResult(
        answer=(f"Forecast inputs as of {fr['as_of'].get('cases')} "
                + (f"({stale} day(s) old); " if stale is not None else "; ")
                + f"{len(fr.get('approved_sources', []))} approved external-context source(s); "
                f"valid-geography filter {scope.get('valid_geography_filter')}."),
        confidence=1.0,
        source_record_ids=["CaseMaster", "ExternalSourceVersion", "JurisdictionBoundary"],
        reasoning_summary=("Data-as-of drives the freshness banner; forecasts use only approved, "
                           "versioned weather/holiday/event/area context up to the observation "
                           "cutoff, and exclude incidents outside the state polygon."),
        model_version="drishti-forecast@1.0.0")
    return FreshnessResponse(
        result=result, as_of=fr.get("as_of", {}), case_data_stale_days=stale,
        approved_sources=fr.get("approved_sources", []), valid_geography=scope)
