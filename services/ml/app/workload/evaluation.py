"""Held-out evaluation for the aggregate station-workload band task (Phase 13).

A prediction is only decision-support if we can show, on data the model never
trained on, how often it is right and how well-calibrated it is — and that it
beats a naive baseline. This module mirrors the forecast rolling-origin protocol
for a CLASSIFICATION task:

  * Time split (train/val/test by cutoff order) + a geographic holdout so a
    station cannot "see itself"; the foundation model is retrained on non-holdout
    districts and re-scored on holdout districts for spatial generalisation.
  * Ordinal metrics: accuracy, macro-F1, quadratic weighted kappa (QWK), the
    multiclass Brier score and Expected Calibration Error (ECE).
  * Calibration by temperature scaling fit on the validation split; confidence =
    top-1 probability; ABSTENTION on low confidence or insufficient station
    history, with a threshold-review sweep.
  * Baseline comparison (prior-period, majority, gradient-boosted trees) with a
    skill score, and a beats_all_baselines flag.
  * Leakage / protected-feature / proxy guards run as part of every evaluation.
  * Metrics broken down by time, geography and data completeness.

Deterministic + CPU-friendly by default (in-context foundation stand-in); pass a
foundation_kind to evaluate the real TabFM/TabPFN. Aggregate only.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import features as feat
from . import models_iface as mi

# Feature-name substrings that would indicate a protected/proxy attribute leaking
# into the (supposedly aggregate, non-protected) schema.
PROTECTED_KEYWORDS = ("caste", "religion", "relig", "gender", "sex", "juvenile",
                      "minor", "age", "community", "ethnic", "race", "creed")

DEFAULT_ABSTAIN_CONFIDENCE = 0.45
DEFAULT_MIN_HISTORY_MONTHS = 12.0


def _resolve_model(foundation_kind: str, n_bands: int, n_estimators):
    """Construct the requested foundation model; fall back DETERMINISTICALLY to
    the in-context stand-in when a specific kind's weights/deps are unavailable
    (never silently escalate to the slow TabFM path). Returns (model, effective_kind)."""
    if foundation_kind == "auto":
        m = mi.get_foundation_model(n_bands=n_bands, n_estimators=n_estimators)
        return m, getattr(m, "_kind", foundation_kind)
    try:
        return mi.make_foundation_model(foundation_kind, n_bands=n_bands,
                                        n_estimators=n_estimators), foundation_kind
    except mi.ModelUnavailable:
        return mi.InContextFoundationModel(n_bands=n_bands), "incontext"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _accuracy(y, yhat) -> float:
    return float((np.asarray(y) == np.asarray(yhat)).mean()) if len(y) else 0.0


def _per_class(y, yhat, n_bands: int) -> list[dict]:
    y = np.asarray(y); yhat = np.asarray(yhat)
    out = []
    for c in range(n_bands):
        tp = int(((yhat == c) & (y == c)).sum())
        fp = int(((yhat == c) & (y != c)).sum())
        fn = int(((yhat != c) & (y == c)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        out.append({"band": c, "precision": round(prec, 4), "recall": round(rec, 4),
                    "f1": round(f1, 4), "support": int((y == c).sum())})
    return out


def _macro_f1(y, yhat, n_bands: int) -> float:
    pc = _per_class(y, yhat, n_bands)
    present = [c["f1"] for c in pc if c["support"] > 0]
    return float(np.mean(present)) if present else 0.0


def _qwk(y, yhat, n_bands: int) -> float:
    """Quadratic weighted kappa — agreement penalising far-off ordinal errors."""
    y = np.asarray(y, dtype=int); yhat = np.asarray(yhat, dtype=int)
    n = len(y)
    if n == 0 or n_bands < 2:
        return 0.0
    O = np.zeros((n_bands, n_bands))
    for a, b in zip(y, yhat):
        O[a, b] += 1
    w = np.zeros((n_bands, n_bands))
    for i in range(n_bands):
        for j in range(n_bands):
            w[i, j] = ((i - j) ** 2) / ((n_bands - 1) ** 2)
    hist_y = O.sum(axis=1); hist_yhat = O.sum(axis=0)
    E = np.outer(hist_y, hist_yhat) / n
    denom = float((w * E).sum())
    if denom == 0:
        return 1.0
    return float(1.0 - (w * O).sum() / denom)


def _brier(y, proba, n_bands: int) -> float:
    y = np.asarray(y, dtype=int)
    oh = np.eye(n_bands)[y]
    return float(np.mean(np.sum((proba - oh) ** 2, axis=1))) if len(y) else 0.0


def _ece(y, proba, n_bins: int = 10) -> float:
    y = np.asarray(y, dtype=int)
    if not len(y):
        return 0.0
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    correct = (pred == y).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        m = (conf > bins[i]) & (conf <= bins[i + 1])
        if m.sum():
            ece += (m.mean()) * abs(correct[m].mean() - conf[m].mean())
    return float(ece)


def _confusion(y, yhat, n_bands: int) -> list[list[int]]:
    M = np.zeros((n_bands, n_bands), dtype=int)
    for a, b in zip(np.asarray(y, int), np.asarray(yhat, int)):
        M[a, b] += 1
    return M.tolist()


def _metric_block(y, proba, n_bands: int) -> dict:
    yhat = proba.argmax(axis=1)
    return {"n": int(len(y)), "accuracy": round(_accuracy(y, yhat), 4),
            "macro_f1": round(_macro_f1(y, yhat, n_bands), 4),
            "qwk": round(_qwk(y, yhat, n_bands), 4),
            "brier": round(_brier(y, proba, n_bands), 4),
            "ece": round(_ece(y, proba), 4)}


# ---------------------------------------------------------------------------
# Temperature-scaling calibration (fit on val)
# ---------------------------------------------------------------------------
def _apply_temperature(proba: np.ndarray, T: float) -> np.ndarray:
    logits = np.log(np.clip(proba, 1e-9, 1.0)) / max(T, 1e-3)
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def _fit_temperature(proba_val: np.ndarray, y_val: np.ndarray) -> float:
    """Grid-search the scalar temperature minimising validation NLL. Deterministic."""
    if not len(y_val):
        return 1.0
    y = np.asarray(y_val, dtype=int)
    best_T, best_nll = 1.0, np.inf
    for T in np.linspace(0.5, 5.0, 46):
        p = _apply_temperature(proba_val, float(T))
        nll = float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1.0))))
        if nll < best_nll:
            best_nll, best_T = nll, float(T)
    return round(best_T, 3)


# ---------------------------------------------------------------------------
# Slices
# ---------------------------------------------------------------------------
def _slice_metrics(y, proba, keys, n_bands: int, limit: Optional[int] = None) -> dict:
    y = np.asarray(y); keys = np.asarray(keys, dtype=object)
    out = {}
    for k in sorted(set(keys.tolist())):
        m = keys == k
        out[str(k)] = _metric_block(y[m], proba[m], n_bands)
    if limit and len(out) > limit:
        out = dict(sorted(out.items(), key=lambda kv: kv[1]["n"], reverse=True)[:limit])
    return out


def _completeness_bucket(history_months: float) -> str:
    h = float(history_months)
    if h < 12:
        return "lt_12m"
    if h < 24:
        return "12_23m"
    if h < 36:
        return "24_35m"
    return "ge_36m"


# ---------------------------------------------------------------------------
# Leakage / protected / proxy checks
# ---------------------------------------------------------------------------
def leakage_report(ds) -> dict:
    """Structural + statistical leakage/protected/proxy guards over the dataset."""
    names = ds.feature_names
    protected = [n for n in names for kw in PROTECTED_KEYWORDS if kw in n.lower()]
    # label independence: forward window strictly after every cutoff (structural)
    horizon = ds.meta["label_horizon_months"]
    label_after_cutoff = horizon >= 1
    # statistical: a feature that perfectly reproduces the label would be a leak.
    y = ds.label_count.astype(float)
    max_corr, worst = 0.0, None
    if len(y) > 2 and y.std() > 0:
        for j, n in enumerate(names):
            col = ds.X[:, j]
            if col.std() == 0:
                continue
            c = abs(float(np.corrcoef(col, y)[0, 1]))
            if c > max_corr:
                max_corr, worst = c, n
    # feature columns must not equal the label vector exactly
    identical = [names[j] for j in range(ds.X.shape[1])
                 if np.array_equal(ds.X[:, j].astype(float), y)]
    return {
        "protected_or_proxy_features": protected,
        "has_protected_or_proxy": bool(protected),
        "label_independent_of_features": not identical,
        "label_window_after_cutoff": bool(label_after_cutoff),
        "max_feature_label_correlation": round(max_corr, 4),
        "max_correlation_feature": worst,
        "suspected_leak": bool(identical) or max_corr >= 0.999,
        "leakage_safe": (not identical) and (max_corr < 0.999) and (not protected) and label_after_cutoff,
    }


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------
def evaluate_dataset(ds, *, foundation_kind: str = "incontext",
                     n_estimators: Optional[int] = None,
                     abstain_confidence: float = DEFAULT_ABSTAIN_CONFIDENCE,
                     min_history_months: float = DEFAULT_MIN_HISTORY_MONTHS,
                     seed: int = 42) -> dict:
    """Evaluate a foundation candidate + baselines on a prebuilt Dataset."""
    np.random.seed(seed)
    n_bands = ds.n_bands
    tr, va, te = ds.mask("train"), ds.mask("val"), ds.mask("test")
    Xtr, ytr = ds.X[tr], ds.y[tr]
    Xva, yva = ds.X[va], ds.y[va]
    Xte, yte = ds.X[te], ds.y[te]

    # -- foundation candidate (deterministic in-context fallback if unavailable) --
    model, foundation_kind = _resolve_model(foundation_kind, n_bands, n_estimators)
    model.fit(Xtr, ytr)
    proba_te_raw = model.predict_proba(Xte)

    # calibration on val
    T = 1.0
    if len(yva):
        proba_va = model.predict_proba(Xva)
        T = _fit_temperature(proba_va, yva)
    proba_te = _apply_temperature(proba_te_raw, T)

    model_metrics = _metric_block(yte, proba_te, n_bands)
    model_metrics_uncalibrated = _metric_block(yte, proba_te_raw, n_bands)

    # -- baselines (measured on the identical test split) --
    baselines = mi.get_baseline_models(ds.thresholds, n_bands=n_bands,
                                        recent_index=ds.feature_names.index("wl_recent_case_volume"))
    baseline_reports: dict[str, dict] = {}
    for key, bm in baselines.items():
        bm.fit(Xtr, ytr)
        bp = bm.predict_proba(Xte)
        baseline_reports[key] = {"name": bm.name, "family": bm.family,
                                 **_metric_block(yte, bp, n_bands)}

    # skill vs baselines (QWK-based; positive => model better) + beats flag
    skill = {}
    for key, br in baseline_reports.items():
        b_err = 1.0 - br["qwk"]
        m_err = 1.0 - model_metrics["qwk"]
        skill[key] = round(1.0 - m_err / b_err, 4) if b_err > 0 else None
    beats = all(model_metrics["qwk"] >= br["qwk"] for br in baseline_reports.values()) and \
        model_metrics["accuracy"] >= max((br["accuracy"] for br in baseline_reports.values()),
                                         default=0.0)

    # -- abstention + threshold review --
    conf = proba_te.max(axis=1)
    hist = ds.X[te][:, ds.feature_names.index("wl_history_months")]
    retain = (conf >= abstain_confidence) & (hist >= min_history_months)
    abstained = int((~retain).sum())
    retained_metrics = _metric_block(yte[retain], proba_te[retain], n_bands) if retain.any() else None
    sweep = []
    for thr in [0.3, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8]:
        r = conf >= thr
        sweep.append({"confidence_threshold": thr, "coverage": round(float(r.mean()), 4),
                      "accuracy_on_retained": round(_accuracy(yte[r], proba_te[r].argmax(axis=1)), 4)
                      if r.any() else None})

    # -- slices --
    by_time = _slice_metrics(yte, proba_te, ds.cutoff_periods[te], n_bands)
    by_geo = _slice_metrics(yte, proba_te, ds.district_ids[te], n_bands, limit=40)
    completeness_keys = [_completeness_bucket(h) for h in hist]
    by_completeness = _slice_metrics(yte, proba_te, completeness_keys, n_bands)

    # -- geographic holdout: retrain on non-holdout, score holdout test rows --
    geo = _geo_holdout_eval(ds, model_kind=foundation_kind, n_estimators=n_estimators,
                            n_bands=n_bands, T=T)

    return {
        "task": feat.TASK, "schema": f"{feat.SCHEMA_NAME} v{feat.SCHEMA_VERSION}",
        "bands": ds.bands, "n_bands": n_bands, "band_thresholds": ds.thresholds,
        "model": {"name": model.name, "family": model.family,
                  "foundation_kind": foundation_kind, "temperature": T,
                  "calibrated": model_metrics, "uncalibrated": model_metrics_uncalibrated,
                  "per_class": _per_class(yte, proba_te.argmax(axis=1), n_bands),
                  "confusion": _confusion(yte, proba_te.argmax(axis=1), n_bands)},
        "baselines": baseline_reports,
        "skill_vs_baselines": skill,
        "beats_all_baselines": bool(beats),
        "abstention": {"confidence_threshold": abstain_confidence,
                       "min_history_months": min_history_months,
                       "abstained": abstained, "n_test": int(te.sum()),
                       "abstention_rate": round(abstained / max(int(te.sum()), 1), 4),
                       "metrics_on_retained": retained_metrics,
                       "threshold_review": sweep},
        "metrics_by_time": by_time,
        "metrics_by_geography": by_geo,
        "metrics_by_data_completeness": by_completeness,
        "geo_holdout": geo,
        "leakage": leakage_report(ds),
        "splits": {"train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum())},
        "dataset": ds.meta,
    }


def _geo_holdout_eval(ds, *, model_kind: str, n_estimators, n_bands: int, T: float) -> dict:
    """Train on TRAIN rows in non-holdout districts, evaluate on TEST rows in
    holdout districts (pure spatial+temporal generalisation)."""
    tr = ds.mask("train") & (~ds.geo_holdout)
    te = ds.mask("test") & ds.geo_holdout
    if tr.sum() < 20 or te.sum() < 5:
        return {"skipped": True, "reason": "insufficient holdout rows",
                "n_train_nonholdout": int(tr.sum()), "n_test_holdout": int(te.sum())}
    model, _ = _resolve_model(model_kind, n_bands, n_estimators)
    model.fit(ds.X[tr], ds.y[tr])
    proba = _apply_temperature(model.predict_proba(ds.X[te]), T)
    return {"skipped": False, "holdout_districts": ds.holdout_districts,
            "n_train_nonholdout": int(tr.sum()), "n_test_holdout": int(te.sum()),
            "metrics": _metric_block(ds.y[te], proba, n_bands)}


def evaluate(conn, *, foundation_kind: str = "incontext", valid_geo_only: bool = True,
             n_estimators: Optional[int] = None, **kw) -> dict:
    """Build the dataset from the DB and evaluate. Returns the full report."""
    ds = feat.build_dataset(conn, valid_geo_only=valid_geo_only)
    report = evaluate_dataset(ds, foundation_kind=foundation_kind, n_estimators=n_estimators, **kw)
    return report


def summarize(report: dict) -> dict:
    """Compact summary for the AiResult + logs + model registry metrics."""
    m = (report.get("model") or {}).get("calibrated") or {}
    return {"accuracy": m.get("accuracy"), "macro_f1": m.get("macro_f1"),
            "qwk": m.get("qwk"), "ece": m.get("ece"),
            "beats_all_baselines": report.get("beats_all_baselines"),
            "abstention_rate": (report.get("abstention") or {}).get("abstention_rate"),
            "leakage_safe": (report.get("leakage") or {}).get("leakage_safe")}
