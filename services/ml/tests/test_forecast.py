"""Phase-12 forecasting tests.

Unit (no DB): feature builder, the seasonal fan-chart forecaster, the near-repeat
self-excitation kernel, the ST base forecast, and validation date math. Integration
(@requires_db): the layer switcher, per-district layer inspection + fusion
transparency, PAI validation, near-repeat trigger, and (slow) the full pipeline run.
"""
import datetime as dt

import numpy as np
import pytest

from app.contracts import AiResult
from app.forecast import features as feat
from app.forecast import nearrepeat, stgnn, validation as val
from app.forecast.timesfm import SeasonalForecaster
from conftest import requires_db


# ---- unit ------------------------------------------------------------------
def test_feat_at_trend_and_shape():
    counts = [1, 2, 3, 4, 5, 6]
    f = feat._feat_at(counts, 5, window=6)
    assert len(f) == 7
    assert f[2] > 0.9          # trend_slope ~ +1 for a linear increase
    assert f[6] == 6.0         # last_value


def test_seasonal_forecaster_bands_and_native_floats():
    months = [f"{2021 + i // 12}-{i % 12 + 1:02d}" for i in range(36)]
    counts = [100 + 10 * (m % 12 == 0) + i // 6 for i, m in enumerate(range(36))]
    traj = SeasonalForecaster().forecast(counts, months, horizon=3)
    assert len(traj) == 3
    for step in traj:
        assert step["p10"] <= step["median"] <= step["p90"]     # ordered fan
        assert isinstance(step["median"], float)                # not numpy
    assert traj[2]["p90"] - traj[2]["p10"] >= traj[0]["p90"] - traj[0]["p10"]  # widens


def test_near_repeat_intensity_higher_near_events():
    lat = np.array([12.90, 12.9005]); lon = np.array([77.60, 77.6005])
    age = np.array([1.0, 2.0])
    cells = [(12.90, 77.60), (13.50, 78.10)]     # near vs far
    surface = nearrepeat._intensity_surface(lat, lon, age, sigma_m=500, tau_days=7, theta=1.0, cells=cells)
    near = next(c for c in surface if c["lat"] == 12.90)
    far = next(c for c in surface if c["lat"] == 13.50)
    assert near["intensity"] > far["intensity"]
    assert isinstance(near["lat"], float)


def test_cell_returns_native_floats():
    la, lo = nearrepeat._cell(np.float64(12.9412), np.float64(77.6033))
    assert isinstance(la, float) and isinstance(lo, float)


def test_stgnn_base_forecast_extrapolates():
    nxt, sigma = stgnn._base_forecast([10, 12, 14, 16, 18, 20], window=6)
    assert nxt > 18            # increasing series -> next above last window mean
    assert sigma >= 0.0


def test_validation_add_months():
    assert val._add_months(dt.date(2025, 10, 1), 3) == dt.date(2026, 1, 1)
    assert val._add_months(dt.date(2025, 10, 1), -12) == dt.date(2024, 10, 1)


# ---- integration -----------------------------------------------------------
def _assert_airesult(r: AiResult):
    assert isinstance(r.answer, str) and r.answer
    assert 0.0 <= r.confidence <= 1.0
    assert isinstance(r.source_record_ids, list)
    assert "@" in r.model_version


@requires_db
def test_layers_and_district_switcher_and_fusion_transparency():
    from app import db
    from app.forecast import service
    ls = service.list_layers()
    _assert_airesult(ls.result)
    if not ls.layers:
        pytest.skip("no layered forecast yet; run `python -m app.batch forecast-run`")
    layer_names = {l.layer for l in ls.layers}
    assert "fused" in layer_names and "tabfm" in layer_names

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT \"DistrictID\" FROM \"CrimePrediction\" "
                        "WHERE \"Features\"->>'layer'='fused' LIMIT 1")
            row = cur.fetchone()
    d = int(row[0])
    df = service.district_forecast(d)
    _assert_airesult(df.result)
    fused = next((p for p in df.layers if p.layer == "fused"), None)
    assert fused is not None
    # fusion is transparent: the fused cell records its contributing models + confidence
    contribs = fused.features.get("contributing_models")
    assert contribs and all("layer" in c and "confidence" in c and "model_version_id" in c for c in contribs)
    # every layer's forecast carries a confidence
    assert all(p.confidence is not None for p in df.layers)


@requires_db
def test_district_layer_filter_and_stgnn_is_uncertainty_aware():
    from app import db
    from app.forecast import service
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT \"DistrictID\" FROM \"CrimePrediction\" "
                        "WHERE \"Features\"->>'layer'='st_gnn' LIMIT 1")
            row = cur.fetchone()
    if not row:
        pytest.skip("no st_gnn forecast yet")
    d = int(row[0])
    resp = service.district_forecast(d, layer="st_gnn")
    assert len(resp.layers) == 1 and resp.layers[0].layer == "st_gnn"
    f = resp.layers[0].features
    assert "std" in f and "lower_p10" in f and "upper_p90" in f     # emits a distribution
    assert f["upper_p90"] >= f["lower_p10"]


@requires_db
def test_forecast_pai_beats_chance():
    from app.forecast import service
    resp = service.validation(cutoff=dt.date(2025, 10, 1), horizon_months=3)
    _assert_airesult(resp.result)
    assert resp.overall and resp.overall["pai"] is not None
    assert resp.overall["pai"] > 1.0                # concentrates crime better than chance
    assert 0.0 <= resp.overall["hit_rate"] <= 1.0
    assert resp.per_crime_head                        # per crime type reported


@requires_db
def test_near_repeat_trigger_returns_cells():
    from app import db
    from app.forecast import service
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "latitude","longitude" FROM "CaseMaster" '
                        'WHERE "geom" IS NOT NULL LIMIT 1')
            lat, lon = cur.fetchone()
    resp = service.near_repeat_trigger(float(lat), float(lon))
    _assert_airesult(resp.result)
    assert resp.affected_cells and all(0.0 <= c.confidence <= 1.0 for c in resp.affected_cells)


@requires_db
@pytest.mark.slow
def test_full_forecast_run_writes_every_layer():
    import os
    os.environ["DRISHTI_FOUNDATION_MODEL"] = "incontext"   # keep the run fast + deterministic
    from app.forecast import service
    resp = service.run_forecast(head_id=None, horizon_days=30)
    _assert_airesult(resp.result)
    written = {l.layer: l.written for l in resp.layers}
    for layer in ("tabfm", "timesfm", "near_repeat", "st_gnn", "fused"):
        assert written.get(layer, 0) > 0
    assert resp.fused and all(0.0 <= d.confidence <= 1.0 for d in resp.fused)
