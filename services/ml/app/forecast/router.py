"""FastAPI router for Phase-12 forecasting + early warning.

  POST /forecast/run              — run the full stacked pipeline (writes)
  GET  /forecast/layers           — inspect the available layers (layer switcher)
  GET  /forecast/district/{id}    — per-layer forecast for a district (+ ?layer=)
  GET  /forecast/map              — forecast cells for the map, one layer at a time
  POST /forecast/near-repeat      — near-real-time near-repeat trigger for a new FIR
  GET  /forecast/validation       — PAI / hit-rate on held-out incidents

Forecasts are area/period decision support and every response carries confidence.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from . import horizons as horizons_mod
from . import service
from .schemas import (BacktestResponse, DistrictForecastResponse, ForecastMapResponse,
                      ForecastRunResponse, FreshnessResponse, LayersResponse,
                      NearRepeatTriggerResponse, ValidationResponse)

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/horizons")
def forecast_horizons():
    """Prompt 20 §F — the advertised forecast horizons and how each is validated.
    Day-ahead crime forecasting is declared future work (no held-out evaluation)."""
    return horizons_mod.horizon_contract()


@router.post("/run", response_model=ForecastRunResponse)
def run(head_id: int | None = Query(None, ge=1, description="crime head to scope, or all"),
        horizon_days: int = Query(30, ge=7, le=90)):
    return service.run_forecast(head_id=head_id, horizon_days=horizon_days)


@router.get("/layers", response_model=LayersResponse)
def layers():
    return service.list_layers()


@router.get("/district/{district_id}", response_model=DistrictForecastResponse)
def district(district_id: int, head_id: int | None = Query(None, ge=1),
             layer: str | None = Query(None, description="tabfm|timesfm|near_repeat|st_gnn|fused")):
    resp = service.district_forecast(district_id, head_id=head_id, layer=layer)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"District {district_id} not found")
    return resp


@router.get("/map", response_model=ForecastMapResponse)
def forecast_map(layer: str = Query("fused", description="tabfm|timesfm|near_repeat|st_gnn|fused"),
                 head_id: int | None = Query(None, ge=1),
                 min_lon: float | None = None, min_lat: float | None = None,
                 max_lon: float | None = None, max_lat: float | None = None):
    bbox = None
    if None not in (min_lon, min_lat, max_lon, max_lat):
        bbox = (min_lon, min_lat, max_lon, max_lat)
    return service.forecast_map(layer=layer, head_id=head_id, bbox=bbox)


@router.post("/near-repeat", response_model=NearRepeatTriggerResponse)
def near_repeat(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                district_id: int | None = Query(None, ge=1), head_id: int | None = Query(None, ge=1)):
    return service.near_repeat_trigger(lat, lon, district_id=district_id, head_id=head_id)


@router.get("/validation", response_model=ValidationResponse)
def forecast_validation(cutoff: str | None = Query(None, description="YYYY-MM-DD"),
                        horizon_months: int = Query(3, ge=1, le=12),
                        area_fraction: float = Query(0.25, gt=0, le=1)):
    cut = None
    if cutoff:
        try:
            cut = dt.date.fromisoformat(cutoff)
        except ValueError:
            raise HTTPException(status_code=400, detail="cutoff must be YYYY-MM-DD")
    return service.validation(cutoff=cut, horizon_months=horizon_months, area_fraction=area_fraction)


@router.get("/backtest", response_model=BacktestResponse)
def forecast_backtest(head_id: int | None = Query(None, ge=1),
                      horizon: int = Query(1, ge=1, le=6),
                      n_origins: int = Query(6, ge=2, le=24),
                      per_head: bool = Query(True),
                      persist: bool = Query(False, description="persist a ForecastBacktest row")):
    return service.backtest(head_id=head_id, horizon=horizon, n_origins=n_origins,
                            per_head=per_head, persist=persist)


@router.get("/freshness", response_model=FreshnessResponse)
def forecast_freshness():
    return service.freshness()
