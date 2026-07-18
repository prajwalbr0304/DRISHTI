"""Phase-13 aggregate workload task tests.

Pure-Python tests exercise the task/label/leakage/model logic on a synthetic
dataset (fast, hermetic); @requires_db tests exercise the approved schema, the
real leakage-safety of the built dataset and governed snapshot supersession
against the synthetic development database (rolled back).
"""
import datetime as dt

import numpy as np
import pytest

from app.workload import evaluation
from app.workload import features as feat
from app.workload import governance_bridge as gb
from app.workload import models_iface as mi
from app.workload import service
from conftest import requires_db


# ---------------------------------------------------------------------------
# Synthetic dataset (no DB) mirroring features.build_dataset's contract
# ---------------------------------------------------------------------------
def _synthetic_ds(n=240, n_bands=4, seed=0, leak=False, protected=False) -> feat.Dataset:
    rng = np.random.default_rng(seed)
    recent = rng.integers(0, 40, size=n).astype(float)          # wl_recent_case_volume
    X = rng.normal(size=(n, len(feat.FEATURE_NAMES)))
    X[:, 0] = recent
    X[:, feat.FEATURE_NAMES.index("wl_history_months")] = rng.integers(24, 60, size=n).astype(float)
    label_count = np.clip(recent + rng.normal(0, 3, n), 0, None)  # persistent + noise -> learnable
    names = list(feat.FEATURE_NAMES)
    if protected:
        names = names + ["caste_share"]
        X = np.column_stack([X, rng.normal(size=n)])
    if leak:
        X[:, 0] = label_count                                    # a feature == the label (leak)
    thresholds = feat.compute_band_thresholds(label_count[: int(0.6 * n)], n_bands)
    y = np.array([feat.band_of(v, thresholds) for v in label_count], dtype=int)
    n_tr, n_va = int(0.6 * n), int(0.2 * n)
    tags = np.array(["train"] * n_tr + ["val"] * n_va + ["test"] * (n - n_tr - n_va), dtype=object)
    district_ids = np.arange(n) % 8
    return feat.Dataset(
        X=X.astype(float), y=y, label_count=label_count.astype(float),
        feature_names=names, feature_dicts=[], unit_ids=np.arange(n), district_ids=district_ids,
        cutoff_idx=np.zeros(n, int), cutoff_periods=np.array(["2025-03"] * n, dtype=object),
        split_tags=tags, geo_holdout=(district_ids == 0), thresholds=thresholds, n_bands=n_bands,
        bands=feat.BANDS[:n_bands], periods=[], unit_names={}, unit_district={}, holdout_districts=[0],
        meta={"label_horizon_months": feat.LABEL_HORIZON_MONTHS, "n_rows": n, "subject_level": "synthetic"},
    )


# ---------------------------------------------------------------------------
# 1. Task / target definition
# ---------------------------------------------------------------------------
def test_task_is_aggregate_not_person_level():
    assert feat.TASK == "area_workload_band"
    assert feat.SUBJECT_KIND == "area_district"          # aggregate area, never a person
    assert len(feat.FEATURE_NAMES) == 10
    card = service.model_card()
    assert card["protected_attributes"]["used"] is False
    assert any("person" in p.lower() for p in card["prohibited_use"])


@requires_db
def test_approved_schema_non_protected():
    td = service.task_definition()
    assert td["schema_approved"] is True
    assert td["task"] == "area_workload_band"
    assert td["subject_kind"] == "area_district"
    assert len(td["features"]) == 10
    assert all(f["sensitivity"] == "normal" for f in td["features"])   # no protected/proxy feature


# ---------------------------------------------------------------------------
# 2. Label independence + leakage
# ---------------------------------------------------------------------------
def test_label_independent_of_features_clean():
    rep = evaluation.leakage_report(_synthetic_ds(leak=False))
    assert rep["label_independent_of_features"] is True
    assert rep["label_window_after_cutoff"] is True
    assert rep["suspected_leak"] is False


def test_planted_leak_is_detected():
    rep = evaluation.leakage_report(_synthetic_ds(leak=True))
    assert rep["label_independent_of_features"] is False
    assert rep["suspected_leak"] is True
    assert rep["leakage_safe"] is False


@requires_db
def test_built_dataset_is_leakage_safe():
    from app import db
    with db.ro_conn() as conn:
        ds = feat.build_dataset(conn)
    rep = evaluation.leakage_report(ds)
    assert rep["leakage_safe"] is True
    assert rep["has_protected_or_proxy"] is False
    assert rep["label_window_after_cutoff"] is True
    # label window (a forward quarter) is disjoint from the pre-cutoff features
    assert ds.meta["label_horizon_months"] >= 1


# ---------------------------------------------------------------------------
# 3. Protected / proxy feature guard
# ---------------------------------------------------------------------------
def test_protected_feature_flagged():
    rep = evaluation.leakage_report(_synthetic_ds(protected=True))
    assert rep["has_protected_or_proxy"] is True
    assert "caste_share" in rep["protected_or_proxy_features"]
    assert rep["leakage_safe"] is False


# ---------------------------------------------------------------------------
# 4. Baseline comparison
# ---------------------------------------------------------------------------
def test_baseline_comparison_reported():
    rep = evaluation.evaluate_dataset(_synthetic_ds(seed=1), foundation_kind="incontext")
    assert set(rep["baselines"]) == {"prior_period", "majority", "gbm"}
    assert isinstance(rep["beats_all_baselines"], bool)
    for b in rep["baselines"].values():
        assert 0.0 <= b["accuracy"] <= 1.0
        assert "qwk" in b
    m = rep["model"]["calibrated"]
    assert 0.0 <= m["accuracy"] <= 1.0
    assert m["accuracy"] > 0.3                       # learns signal (4-class chance ~0.25)
    assert "prior_period" in rep["skill_vs_baselines"]


def test_calibration_abstention_and_slices_present():
    rep = evaluation.evaluate_dataset(_synthetic_ds(seed=2), foundation_kind="incontext")
    assert 0.0 <= rep["model"]["calibrated"]["ece"] <= 1.0
    assert 0.0 <= rep["abstention"]["abstention_rate"] <= 1.0
    assert rep["abstention"]["threshold_review"]                    # sweep present
    assert rep["metrics_by_time"] and rep["metrics_by_data_completeness"]


# ---------------------------------------------------------------------------
# 5. Deterministic fallback
# ---------------------------------------------------------------------------
def test_incontext_is_deterministic():
    ds = _synthetic_ds(seed=3)
    r1 = evaluation.evaluate_dataset(ds, foundation_kind="incontext")
    r2 = evaluation.evaluate_dataset(ds, foundation_kind="incontext")
    assert r1["model"]["calibrated"] == r2["model"]["calibrated"]
    assert r1["beats_all_baselines"] == r2["beats_all_baselines"]


# ---------------------------------------------------------------------------
# 6. Model unavailable -> graceful deterministic fallback
# ---------------------------------------------------------------------------
def test_unknown_foundation_raises():
    with pytest.raises(mi.ModelUnavailable):
        mi.make_foundation_model("does-not-exist", n_bands=4)


def test_resolve_falls_back_to_incontext(monkeypatch):
    def _boom(*a, **k):
        raise mi.ModelUnavailable("weights unavailable on this host")
    monkeypatch.setattr(mi, "make_foundation_model", _boom)
    model, kind = evaluation._resolve_model("tabfm", n_bands=4, n_estimators=None)
    assert isinstance(model, mi.InContextFoundationModel)
    assert kind == "incontext"


def test_evaluate_survives_unavailable_foundation(monkeypatch):
    def _boom(*a, **k):
        raise mi.ModelUnavailable("no tabpfn")
    monkeypatch.setattr(mi, "make_foundation_model", _boom)
    rep = evaluation.evaluate_dataset(_synthetic_ds(seed=4), foundation_kind="tabpfn")
    assert rep["model"]["calibrated"]["n"] > 0        # still produced a report via fallback


# ---------------------------------------------------------------------------
# 7. Prior-period baseline bands from the recent-volume feature
# ---------------------------------------------------------------------------
def test_prior_period_baseline_uses_thresholds():
    ds = _synthetic_ds(seed=5)
    bm = mi.PriorPeriodBaseline(ds.thresholds, recent_index=0, n_bands=ds.n_bands).fit(ds.X, ds.y)
    proba = bm.predict_proba(ds.X)
    assert proba.shape == (len(ds.X), ds.n_bands)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)
    # predicted band equals the banded recent-volume feature
    expected = np.digitize(ds.X[:, 0], ds.thresholds)
    assert np.array_equal(proba.argmax(axis=1), np.clip(expected, 0, ds.n_bands - 1))


# ---------------------------------------------------------------------------
# 8. Stale / superseded governed snapshot
# ---------------------------------------------------------------------------
@requires_db
def test_snapshot_supersession_marks_prior_stale(rw_rollback):
    conn = rw_rollback
    schema_id = gb.workload_schema_id(conn)
    with conn.cursor() as cur:
        cur.execute('SELECT "ModelVersionID" FROM "ModelVersion" WHERE "ModelName"=%s LIMIT 1',
                    (gb.WORKLOAD_MODEL_NAME,))
        row = cur.fetchone()
    if not row:
        pytest.skip("workload model not registered yet")
    mv_id = int(row[0])
    cutoff = dt.datetime(2025, 9, 30, tzinfo=dt.timezone.utc)
    subject = 999001  # synthetic district id (SubjectRefID is free text; rolled back)

    v1 = {n: 1.0 for n in feat.FEATURE_NAMES}
    s1 = gb.build_workload_snapshot(conn, schema_id=schema_id, unit_id=subject, cutoff=cutoff,
                                    values=v1, source_versions={"t": 1}, actor="test")
    req_id, _ = gb._get_or_create_request(conn, mv_id, s1["feature_snapshot_id"], "test")
    res_id, created = gb._write_result(conn, req_id, mv_id, s1["feature_snapshot_id"],
                                       output={"workload_band": "Low"}, explanation={}, confidence=0.6)
    assert created

    v2 = {n: 9.0 for n in feat.FEATURE_NAMES}   # different values -> different content hash
    s2 = gb.build_workload_snapshot(conn, schema_id=schema_id, unit_id=subject, cutoff=cutoff,
                                    values=v2, source_versions={"t": 2}, actor="test")
    assert s2["feature_snapshot_id"] != s1["feature_snapshot_id"]
    assert s2["superseded_prior"] >= 1

    with conn.cursor() as cur:
        cur.execute('SELECT "SupersededByFeatureSnapshotID" FROM "FeatureSnapshot" WHERE "FeatureSnapshotID"=%s',
                    (s1["feature_snapshot_id"],))
        assert int(cur.fetchone()[0]) == s2["feature_snapshot_id"]      # prior snapshot superseded
        cur.execute('SELECT "IsStale" FROM "PredictionResult" WHERE "PredictionResultID"=%s', (res_id,))
        assert cur.fetchone()[0] is True                                # its result went stale
        cur.execute('SELECT "Status" FROM "PredictionRequest" WHERE "PredictionRequestID"=%s', (req_id,))
        assert cur.fetchone()[0] == "superseded"


@requires_db
def test_idempotent_snapshot_reused(rw_rollback):
    conn = rw_rollback
    schema_id = gb.workload_schema_id(conn)
    cutoff = dt.datetime(2025, 9, 30, tzinfo=dt.timezone.utc)
    vals = {n: 3.0 for n in feat.FEATURE_NAMES}
    a = gb.build_workload_snapshot(conn, schema_id=schema_id, unit_id=999002, cutoff=cutoff,
                                   values=vals, source_versions={"t": 1}, actor="test")
    b = gb.build_workload_snapshot(conn, schema_id=schema_id, unit_id=999002, cutoff=cutoff,
                                   values=vals, source_versions={"t": 1}, actor="test")
    assert b["reused"] is True
    assert a["feature_snapshot_id"] == b["feature_snapshot_id"]
