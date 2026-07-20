"""Forecast-horizon contract (Prompt 20 Part F).

The single source of truth for WHICH forecast horizons DRISHTI advertises and HOW
each is validated. Only validated horizons are advertised; a day-ahead (1-day)
crime forecast is explicitly FUTURE WORK because there is no held-out day-ahead
evaluation — the honest near-term alternative is the validated near-repeat trigger.
"""
from __future__ import annotations

# Base modelled crime-forecast horizon (rolling-origin backtested + PAI-validated).
BASE_MODELED_HORIZON_DAYS = 30
# Horizons the crime-forecast UI may present (matches web MapHotspots HORIZONS).
UI_HORIZON_DAYS = (7, 14, 30)
# API bounds for /forecast/run (min 7 => no unvalidated 1-day/day-ahead crime forecast).
MIN_API_HORIZON_DAYS = 7
MAX_API_HORIZON_DAYS = 90
# Disaster hazard-forecast operational horizons (separate hours-based plane).
DISASTER_HORIZON_HOURS = (24, 48, 72)


def horizon_contract() -> dict:
    return {
        "crime_forecast": {
            "base_modeled_horizon_days": BASE_MODELED_HORIZON_DAYS,
            "advertised_horizon_days": list(UI_HORIZON_DAYS),
            "validated": True,
            "validation": {
                "rolling_origin_backtest": (
                    "MAE/RMSE/WAPE/sMAPE + 80% interval coverage, baseline-compared "
                    "(seasonal-naive, moving-average) with a geographic holdout "
                    "(GET /forecast/backtest)."),
                "pai_hit_rate": (
                    "Held-out PAI (hit-rate / area-fraction) > 1 on post-cutoff "
                    "incidents, per district & crime head (GET /forecast/validation)."),
            },
            "near_term_note": (
                "The 7- and 14-day views are a transparent LINEAR scaling of the "
                "30-day base forecast (approximation for the map density), not "
                "separately-fitted day-level models."),
            "api_range_days": {"min": MIN_API_HORIZON_DAYS, "max": MAX_API_HORIZON_DAYS,
                               "default": BASE_MODELED_HORIZON_DAYS},
        },
        "short_term_near_repeat": {
            "method": "Hawkes/ETAS self-exciting near-repeat trigger (POST /forecast/near-repeat).",
            "horizon": "hours-to-days (near-real-time spatial-temporal risk).",
            "validated": True,
            "note": "The genuine short-horizon signal; used instead of a naive day-ahead scaling.",
        },
        "day_ahead": {
            "status": "future_work",
            "advertised": False,
            "reason": ("No held-out day-ahead (1-day) crime-forecast evaluation exists; "
                       "advertising one would be an untested horizon."),
            "honest_alternative": "the validated near-repeat trigger for near-term risk.",
        },
        "disaster_hazard_forecast": {
            "advertised_horizon_hours": list(DISASTER_HORIZON_HOURS),
            "path": "POST /disaster/forecast/run + GET /disaster/forecast/validate.",
            "note": ("Separate hazard-forecast plane (Prompt 17); hours-based operational "
                     "horizons with their own held-out validation."),
        },
        "declaration": ("Only validated horizons are advertised. Day-ahead crime "
                        "forecasting is future work; near-term risk uses the validated "
                        "near-repeat trigger."),
    }
