"""Prompt 20 Part F — forecast-horizon audit: only validated horizons are
advertised; day-ahead crime forecasting is future work; the API refuses an
out-of-range (unvalidated) horizon. Offline (no DB, no heavy pipeline run).

The validated-horizon EVIDENCE itself (rolling-origin backtest beats baselines,
held-out PAI > 1) is proven by test_forecast.py's DB tests; this file audits the
advertised-horizon contract + the no-untested-horizon guard."""
from fastapi.testclient import TestClient

from app.main import app
from app.forecast import horizons as H

client = TestClient(app)


def test_contract_advertises_only_validated_and_day_ahead_is_future_work():
    c = H.horizon_contract()
    assert c["crime_forecast"]["validated"] is True
    assert c["short_term_near_repeat"]["validated"] is True
    # day-ahead is explicitly future work and NOT advertised
    assert c["day_ahead"]["status"] == "future_work"
    assert c["day_ahead"]["advertised"] is False
    assert "future work" in c["declaration"].lower()


def test_advertised_crime_horizons_match_the_ui_and_api_range():
    c = H.horizon_contract()
    assert c["crime_forecast"]["advertised_horizon_days"] == [7, 14, 30]
    assert H.UI_HORIZON_DAYS == (7, 14, 30)             # == web MapHotspots HORIZONS
    rng = c["crime_forecast"]["api_range_days"]
    assert rng["min"] == 7 and rng["default"] == 30      # no 1-day advertised
    # 7/14-day are transparently labelled as a scaling of the 30-day base
    assert "linear" in c["crime_forecast"]["near_term_note"].lower()


def test_validation_claims_point_to_real_registered_endpoints():
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/forecast/backtest" in paths        # rolling-origin backtest
    assert "/forecast/validation" in paths       # held-out PAI hit-rate
    assert "/forecast/near-repeat" in paths      # validated short-term signal
    assert "/forecast/horizons" in paths


def test_horizons_endpoint_returns_the_contract():
    r = client.get("/forecast/horizons")
    assert r.status_code == 200
    body = r.json()
    assert body["day_ahead"]["status"] == "future_work"
    assert body["disaster_hazard_forecast"]["advertised_horizon_hours"] == [24, 48, 72]


def test_forecast_run_refuses_unvalidated_out_of_range_horizons():
    # < 7 days (a naive day-ahead) and > 90 days are refused by validation (422),
    # before the pipeline runs — no untested horizon is ever accepted.
    assert client.post("/forecast/run", params={"horizon_days": 1}).status_code == 422
    assert client.post("/forecast/run", params={"horizon_days": 6}).status_code == 422
    assert client.post("/forecast/run", params={"horizon_days": 91}).status_code == 422
