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


# ===========================================================================
# Phase 12 additions: baselines, rolling-origin backtest, valid-geography
# exclusion, abstention, governed persistence, freshness.
# ===========================================================================
from app.forecast import baselines as bl
from app.forecast import backtest as btmod


# ---- unit: baselines -------------------------------------------------------
def test_baselines_produce_ordered_widening_native_fans():
    months = [f"{2021 + i // 12}-{i % 12 + 1:02d}" for i in range(30)]
    counts = [50 + (i % 12) + i // 12 for i in range(30)]
    for fc in (bl.SeasonalNaiveForecaster(), bl.MovingAverageForecaster(window=3)):
        traj = fc.forecast(counts, months, horizon=3)
        assert len(traj) == 3
        for s in traj:
            assert s["p10"] <= s["median"] <= s["p90"]      # ordered fan
            assert isinstance(s["median"], float)           # native float, not numpy
        # bands widen with the horizon
        assert traj[2]["p90"] - traj[2]["p10"] >= traj[0]["p90"] - traj[0]["p10"]


def test_baseline_registry_has_seasonal_naive_and_moving_average():
    reg = bl.baseline_forecasters()
    assert "seasonal_naive" in reg and "moving_average_3" in reg
    assert reg["seasonal_naive"].family == "baseline"


# ---- unit: backtest metrics + leakage-safe origin selection ----------------
def test_backtest_acc_metrics_are_correct():
    acc = btmod._Acc()
    acc.add(10, {"median": 11, "p10": 8, "p25": 9, "p75": 13, "p90": 14})   # |err|=1, in80, in50
    acc.add(20, {"median": 16, "p10": 18, "p25": 19, "p75": 22, "p90": 24})  # |err|=4, in80, in50
    m = acc.metrics()
    assert m["n"] == 2
    assert m["mae"] == 2.5                       # (1 + 4) / 2
    assert m["coverage_80"] == 1.0 and m["coverage_50"] == 1.0
    assert 0.0 <= m["wape"] <= 1.0 and 0.0 <= m["smape"] <= 200.0


def test_backtest_origins_are_leakage_safe():
    n, horizon, min_train = 30, 1, 18
    origins = btmod._origin_indices(n, horizon, 6, 1, min_train)
    assert origins                                    # some origins selected
    for o in origins:
        assert o >= min_train - 1                     # enough pre-cutoff history
        assert o + horizon < n                        # held-out target within range
        assert o < o + horizon                        # training slice excludes the target


def test_backtest_no_origins_when_history_too_short():
    # a short series (n=12) cannot satisfy min_train=18 -> no origins, no scoring
    assert btmod._origin_indices(12, 1, 6, 1, 18) == []


# ---- unit: interval derivation from confidence -----------------------------
def test_interval_from_confidence_is_consistent_with_cv():
    from app.forecast.governance_bridge import _interval_from_confidence
    lo, hi = _interval_from_confidence(40.0, 0.5)     # cv = 1/0.5 - 1 = 1 -> [0, 80]
    assert lo == 0.0 and abs(hi - 80.0) < 1e-6
    lo2, hi2 = _interval_from_confidence(40.0, 0.8)   # cv = 0.25 -> [30, 50]
    assert abs(lo2 - 30.0) < 1e-6 and abs(hi2 - 50.0) < 1e-6


# ---- unit: valid-geography exclusion predicate (no DB) ---------------------
def test_geoscope_exclusion_predicate(monkeypatch):
    from app.geo import geoscope

    class _C:  # a stand-in connection object
        pass

    conn = _C()
    monkeypatch.setattr(geoscope, "boundaries_available", lambda c: True)
    monkeypatch.setattr(geoscope, "out_of_state_case_ids", lambda c: (7, 9))
    pred, param = geoscope.exclusion_predicate(conn, True, "cm")
    assert pred == 'cm."CaseMasterID" <> ALL(%s)' and param == [7, 9]
    # empty out-of-state set -> no predicate (fast path)
    monkeypatch.setattr(geoscope, "out_of_state_case_ids", lambda c: ())
    assert geoscope.exclusion_predicate(conn, True, "cm") == (None, None)
    # disabled -> no predicate
    assert geoscope.exclusion_predicate(conn, False, "cm") == (None, None)


def test_geoscope_apply_exclusion_appends(monkeypatch):
    from app.geo import geoscope

    class _C:
        pass

    monkeypatch.setattr(geoscope, "boundaries_available", lambda c: True)
    monkeypatch.setattr(geoscope, "out_of_state_case_ids", lambda c: (3,))
    where, params = ['cm."x" IS NOT NULL'], []
    applied = geoscope.apply_exclusion(_C(), where, params, True, "cm")
    assert applied and where[-1] == 'cm."CaseMasterID" <> ALL(%s)' and params == [[3]]


# ---- integration -----------------------------------------------------------
@requires_db
def test_valid_geography_excludes_out_of_state_from_series():
    from app import db
    from app.geo import geoscope, trends
    with db.ro_conn() as conn:
        assert geoscope.boundaries_available(conn) is True        # boundaries loaded
        with conn.cursor() as cur:
            cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u '
                        'WHERE u."DistrictID" IS NOT NULL ORDER BY 1 LIMIT 1')
            did = int(cur.fetchone()[0])
        _p1, unfiltered = trends.monthly_series(conn, district_id=did, valid_geo_only=False)
        _p2, filtered = trends.monthly_series(conn, district_id=did, valid_geo_only=True)
        oos = geoscope.count_out_of_state(conn, district_id=did)
    # the valid-geography filter removes exactly the out-of-state incidents
    assert sum(filtered) == sum(unfiltered) - oos
    assert sum(filtered) <= sum(unfiltered)


@requires_db
def test_rolling_origin_backtest_metrics_and_baseline_comparison():
    from app import db
    with db.ro_conn() as conn:
        rep = btmod.rolling_origin_backtest(conn, head_id=None, horizon=1, n_origins=4)
    m = rep["model"]
    assert m["n"] > 0 and m["mae"] is not None and m["mae"] >= 0
    assert m["rmse"] is not None and m["rmse"] >= 0
    assert m["wape"] is not None and 0.0 <= m["wape"] < 1.5      # metric threshold
    assert 0.0 <= m["coverage_80"] <= 1.0                        # valid coverage
    # baseline-compared under the identical protocol
    assert "seasonal_naive" in rep["baselines"] and "moving_average_3" in rep["baselines"]
    assert "seasonal_naive" in rep["skill_vs_baselines"]
    # the model beats the simple baselines on this synthetic fixture (metric gate)
    assert rep["beats_all_baselines"] is True
    # geographic holdout + per-season error reported
    assert rep["geo_holdout"]["train"] and rep["geo_holdout"]["holdout"]
    assert rep["error_by_season"]
    assert rep["abstention_rate"] >= 0.0


@requires_db
def test_backtest_abstains_on_insufficient_volume():
    from app import db
    with db.ro_conn() as conn:
        rep = btmod.rolling_origin_backtest(conn, head_id=None, horizon=1, n_origins=3,
                                            min_monthly_avg=1e9)   # impossible threshold
    assert rep["cells_considered"] > 0        # origins were selected
    assert rep["scored_points"] == 0          # ... but every cell abstained
    assert rep["abstained_cells"] == rep["cells_considered"]
    assert rep["abstention_rate"] == 1.0


@requires_db
def test_backtest_report_per_head_breakdown():
    from app import db
    with db.ro_conn() as conn:
        rep = btmod.backtest_report(conn, head_id=None, horizon=1, n_origins=3,
                                    per_head=True, max_heads=3)
    assert rep["error_by_head"]                # per-crime-head breakdown present
    for _name, r in rep["error_by_head"].items():
        assert "model" in r and r["model"]["n"] >= 0


@requires_db
def test_governed_forecast_persistence_and_idempotency(rw_rollback):
    from app.forecast import governance_bridge as gb
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT u."DistrictID" FROM "Unit" u '
                    'WHERE u."DistrictID" IS NOT NULL ORDER BY 1 LIMIT 1')
        did = int(cur.fetchone()[0])
    districts = [{"district_id": did, "fused_count": 30.0, "confidence": 0.6,
                  "risk_class": "Elevated", "contributing_models": ["tabfm", "timesfm"],
                  "near_term_spike": False}]
    kw = dict(head_id=None, prediction_start="2025-06-01T00:00:00+00:00",
              prediction_end="2025-06-30T00:00:00+00:00", horizon_days=30, actor="test")
    s1 = gb.persist_forecast(conn, districts=districts, **kw)
    assert s1["model_version_id"] and s1["feature_schema_version_id"]
    assert s1["results_new"] == 1 and s1["snapshots_new"] == 1
    # idempotent replay: same inputs reuse the snapshot, write no new result
    s2 = gb.persist_forecast(conn, districts=districts, **kw)
    assert s2["snapshots_reused"] == 1 and s2["results_new"] == 0
    # the governed result carries a lower/upper interval + confidence
    with conn.cursor() as cur:
        cur.execute('SELECT "LowerInterval","UpperInterval","Confidence" FROM "PredictionResult" '
                    'WHERE "ModelVersionID"=%s ORDER BY "PredictionResultID" DESC LIMIT 1',
                    (s1["model_version_id"],))
        lo, hi, conf = cur.fetchone()
    assert lo is not None and hi is not None and float(hi) >= float(lo)
    assert conf is not None and 0.0 <= float(conf) <= 1.0


@requires_db
def test_forecast_freshness_reports_sources_and_geo_scope():
    from app.forecast import service
    resp = service.freshness()
    _assert_airesult(resp.result)
    assert resp.as_of.get("cases")            # data-as-of present
    assert resp.valid_geography.get("valid_geography_filter") in ("active", "inactive_no_boundary")
    assert isinstance(resp.approved_sources, list)
