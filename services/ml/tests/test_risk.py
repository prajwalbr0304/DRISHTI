"""Risk scoring tests: ModelInterface backends + scoring helpers (no DB) and the
/risk read path + calibration (integration)."""
import numpy as np
import pytest

from app.risk import models_iface as mi
from app.risk import scoring
from app.risk.features import RISK_BANDS
from conftest import requires_db


def _fixture(n=300, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    # label driven mostly by feature 0 -> learnable signal
    latent = X[:, 0] * 2 + rng.normal(0, 0.5, n)
    y = np.digitize(latent, np.percentile(latent, [20, 40, 60, 80]))
    return X, y


@pytest.mark.parametrize("factory", [mi.get_foundation_model, mi.get_baseline_model])
def test_backend_proba_shape_and_learns(factory):
    X, y = _fixture()
    m = factory().fit(X, y)
    p = m.predict_proba(X)
    assert p.shape == (len(X), mi.N_CLASSES)
    assert np.allclose(p.sum(axis=1), 1.0, atol=1e-6)
    acc = (p.argmax(1) == y).mean()
    assert acc > 0.35  # comfortably beats 5-class chance (~0.2)


def test_tabfm_is_the_wired_foundation_backend():
    # Real Google TabFM package is installed and registered as a foundation model.
    import tabfm  # noqa: F401
    from tabfm import TabFMClassifier  # noqa: F401
    assert issubclass(mi.TabFMFoundationModel, mi.RiskModel)
    assert mi.TabFMFoundationModel.name == "drishti-tabfm"
    assert mi.TabFMFoundationModel.family == "foundation"
    # explicit env override selects TabFM (class routing; not instantiated here
    # because the model is 6.3GB). The RAM-gated auto path prefers it too.
    import inspect
    src = inspect.getsource(mi.get_foundation_model)
    assert "tabfm" in src.lower() and "_tabfm()" in src


def test_risk_from_proba_maps_band_and_score():
    p = np.array([0.0, 0.0, 0.0, 0.0, 1.0])   # all mass on Severe
    score, band, exp = scoring._risk_from_proba(p)
    assert band == "Severe"
    assert score == 1.0
    p2 = np.array([1.0, 0.0, 0.0, 0.0, 0.0])   # all mass on Low
    score2, band2, _ = scoring._risk_from_proba(p2)
    assert band2 == "Low" and score2 == 0.0


def test_factors_are_signed_and_ranked():
    X, y = _fixture()
    w, mu, sd = scoring._surrogate_weights(X, y)
    z = (X[0] - mu) / np.where(sd == 0, 1, sd)
    facs = scoring._factors_for(X[0], z, w, top=3)
    assert len(facs) == 3
    mags = [abs(f["contribution"]) for f in facs]
    assert mags == sorted(mags, reverse=True)   # ranked by |contribution|
    assert all(f["direction"] in ("increases", "decreases") for f in facs)


# ---- integration ----------------------------------------------------------
@requires_db
def test_offender_risk_read_has_5_bands_and_factors():
    from app.risk import service
    resp = service.get_by_entity(61)
    if resp is None:
        pytest.skip("individual offender-risk retired in Phase 13 — CrimeRiskScore is "
                    "empty synthetic-demo; the approved model is the aggregate workload band")
    assert resp.risk_band in RISK_BANDS               # 5 ordinal levels
    assert resp.risk_level in ("low", "medium", "high", "critical")
    assert 0.0 <= resp.risk_score <= 1.0
    assert len(resp.factors) > 0                       # SHAP-style factor bars
    assert abs(sum(resp.class_probabilities.values()) - 1.0) < 1e-3
    # provenance present
    assert any("EntityGraph" in s for s in resp.result.source_record_ids)


@requires_db
def test_by_accused_resolves():
    from app.risk import service
    ent = service.get_by_entity(61)
    if ent is None:
        pytest.skip("individual offender-risk retired in Phase 13 — CrimeRiskScore is "
                    "empty synthetic-demo; the approved model is the aggregate workload band")
    resp = service.get_by_accused(ent.accused_master_id)
    assert resp is not None
    assert resp.entity_id == 61


def test_calibration_metrics_and_logic():
    # Validate the calibration machinery (Brier/ECE + model comparison) on a fast
    # synthetic fixture. The full DB calibration with real TabPFN is exercised by
    # the `risk-calibration` batch CLI (too slow for the unit suite on CPU).
    X, y = _fixture(n=400, seed=1)
    n_test = 120
    tr, te = np.arange(len(X))[n_test:], np.arange(len(X))[:n_test]
    base = mi.get_baseline_model().fit(X[tr], y[tr])
    icl = mi.InContextFoundationModel().fit(X[tr], y[tr])   # instant, no weights
    pb, pi = base.predict_proba(X[te]), icl.predict_proba(X[te])
    # Brier is a proper score in [0, 2] for one-hot targets; ECE in [0, 1]
    for p in (pb, pi):
        assert 0.0 <= scoring._brier(p, y[te]) <= 2.0
        assert 0.0 <= scoring._ece(p, y[te]) <= 1.0
        assert (p.argmax(1) == y[te]).mean() > 0.3   # beats 5-class chance


@requires_db
@pytest.mark.slow
def test_full_calibration_report_runs():
    from app.risk import service
    rep = service.calibration()
    assert rep.foundation["accuracy"] > 0.3
    assert rep.baseline["accuracy"] > 0.3
    assert 0.0 <= rep.agreement <= 1.0
