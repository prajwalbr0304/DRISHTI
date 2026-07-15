"""Geospatial analytics tests: trend decomposition/band logic (no DB) + the
materialized hotspot/alert outputs and trends endpoint (integration)."""
import numpy as np
import pytest

from app.geo import trends
from conftest import requires_db


# ---- pure logic (no DB) ---------------------------------------------------
def test_rolling_band_flags_spike():
    # 12 flat months then a big spike -> the spike must be flagged anomalous
    counts = [10, 11, 9, 10, 12, 10, 11, 9, 10, 11, 10, 40]
    mean, upper, lower, anomaly = trends.rolling_band(counts, window=6, k=2.0)
    assert bool(anomaly[-1]) is True
    assert upper[-1] is not None and upper[-1] < 40
    assert not any(anomaly[:6])  # warm-up region has no band


def test_decompose_returns_aligned_components():
    # 3 years of a seasonal-plus-trend signal
    periods, counts = [], []
    for y in range(2022, 2025):
        for m in range(1, 13):
            periods.append(f"{y}-{m:02d}")
            counts.append(50 + (y - 2022) * 10 + (15 if m in (10, 11) else 0))
    tr, se, re = trends.decompose(periods, counts, period_len=12)
    assert len(tr) == len(se) == len(re) == len(periods)
    # October seasonal component should be clearly positive (festival bump)
    oct_idx = [i for i, p in enumerate(periods) if p.endswith("-10")]
    assert np.mean([se[i] for i in oct_idx]) > 0


def test_deltas_mom_yoy():
    periods = [f"2024-{m:02d}" for m in range(1, 13)] + ["2025-01"]
    counts = [100] * 12 + [130]
    d = trends.deltas(periods, counts)
    assert d["mom_delta"] == 30
    assert d["yoy_delta"] == 30  # vs 2024-01


# ---- integration: batch outputs on the loaded data -----------------------
@requires_db
def test_hotspots_written_and_active():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM "CrimeHotspot" WHERE "IsActive" '
                        'AND "ModelVersionID" IN (SELECT "ModelVersionID" FROM "ModelVersion" '
                        'WHERE "ModelName"=\'drishti-hotspot-kde\')')
            active_kde = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM "mv_active_hotspots"')
            mv = cur.fetchone()[0]
    assert active_kde > 0
    assert mv == active_kde  # matview reflects the freshly computed hotspots


@requires_db
def test_emerging_alerts_present():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM "AlertHistory" WHERE "AlertType"=\'anomaly\' '
                        'AND "Status"=\'open\'')
            assert cur.fetchone()[0] > 0


@requires_db
def test_trends_endpoint_bengaluru_cyber():
    from app.geo import service
    resp = service.trends_series(district_id=1, head_id=4, window=6, k=2.0, decompose=True)
    assert resp.total > 0
    assert len(resp.series) >= 12
    assert resp.decomposition is not None
    assert len(resp.decomposition.trend) == len(resp.series)
