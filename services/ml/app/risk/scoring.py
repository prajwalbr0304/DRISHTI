"""Offender risk scoring: batch + on-demand, Factors, and calibration.

Foundation model (TabFM-family) scores offenders zero-shot from a stratified
labelled context; a gradient-boosted baseline is kept for calibration. Results
are written to CrimeRiskScore (AccusedMasterID + DistrictID scope, RiskScore,
RiskLevel, Factors jsonb with signed SHAP-style contributions) plus a
ModelInference audit row per offender. Every score is reproducible: inputs +
model version are stored.
"""
from __future__ import annotations

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import matviews, models
from . import features as feat
from . import models_iface as mi

RISK_BANDS = feat.RISK_BANDS


# ---- helpers ---------------------------------------------------------------
def _stratified_context(X, y, n=2000, seed=42):
    """Sample up to n rows, stratified by class so rare Severe is represented."""
    rng = np.random.default_rng(seed)
    idx_by_c = {c: np.where(y == c)[0] for c in mi.CLASSES}
    per = max(1, n // mi.N_CLASSES)
    picks = []
    for c, idxs in idx_by_c.items():
        if len(idxs) == 0:
            continue
        take = min(per, len(idxs))
        picks.append(rng.choice(idxs, size=take, replace=False))
    sel = np.concatenate(picks) if picks else np.arange(min(n, len(X)))
    return sel


def _surrogate_weights(X, y):
    """Signed linear weights over standardized features -> attribution (SHAP-like)."""
    from sklearn.linear_model import LinearRegression
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    lr = LinearRegression().fit(Z, y.astype(float))
    return lr.coef_, mu, sd


def _factors_for(x_row, z_row, weights, top=6):
    contribs = weights * z_row
    order = np.argsort(-np.abs(contribs))[:top]
    out = []
    for i in order:
        fname = feat.FEATURE_NAMES[i]
        out.append({
            "feature": fname,
            "label": feat.FEATURE_LABELS[fname],
            "value": round(float(x_row[i]), 4),
            "contribution": round(float(contribs[i]), 4),
            "direction": "increases" if contribs[i] >= 0 else "decreases",
        })
    return out


def _risk_from_proba(proba):
    exp_class = float((proba * np.arange(mi.N_CLASSES)).sum())
    band = RISK_BANDS[int(proba.argmax())]
    score = round(exp_class / (mi.N_CLASSES - 1), 5)
    return score, band, exp_class


# ---- batch scoring ---------------------------------------------------------
def score_all(conn, seed: int = 42, context_size: int = 1000,
              limit: int | None = None, foundation_estimators: int | None = None) -> dict:
    data = feat.build(conn, seed=seed)
    X, y, meta = data["X"], data["y"], data["meta"]

    model = mi.get_foundation_model(n_estimators=foundation_estimators)
    sel = _stratified_context(X, y, n=context_size, seed=seed)
    model.fit(X[sel], y[sel])

    # Which offenders to score/write. `limit` (a stratified sample) makes heavy
    # foundation models (TabFM on CPU) tractable; default scores everyone.
    if limit and limit < len(X):
        score_idx = np.sort(_stratified_context(X, y, n=limit, seed=seed + 1))
    else:
        score_idx = np.arange(len(X))
    proba_sub = model.predict_proba(X[score_idx])
    proba = {int(score_idx[j]): proba_sub[j] for j in range(len(score_idx))}

    weights, mu, sd = _surrogate_weights(X, y)
    sd_safe = sd.copy(); sd_safe[sd_safe == 0] = 1.0
    Z = (X - mu) / sd_safe

    mv_id = models.get_or_create_model_version(
        conn, model.name, "classification", "1.0.0", framework=model.family,
        hyperparameters={"context_size": int(len(sel)), "classes": RISK_BANDS,
                         "features": feat.FEATURE_NAMES},
        metrics={"scored": len(score_idx)})

    risk_rows, inf_rows = [], []
    band_counts = {b: 0 for b in RISK_BANDS}
    score_set = set(int(i) for i in score_idx)
    for i, m in enumerate(meta):
        if i not in score_set or m["district_id"] is None:
            continue  # not in the scored sample, or no scope for the CHECK
        p = proba[int(i)]
        score, band, exp_class = _risk_from_proba(p)
        level = models.risk_level_for(score)
        band_counts[band] += 1
        factors_list = _factors_for(X[i], Z[i], weights)
        factors = {
            "risk_band": band, "expected_class": round(exp_class, 3),
            "probs": {RISK_BANDS[c]: round(float(p[c]), 4) for c in mi.CLASSES},
            "top_factors": factors_list,
            "features": {feat.FEATURE_NAMES[j]: round(float(X[i][j]), 4)
                         for j in range(len(feat.FEATURE_NAMES))},
            "entity_id": m["entity_id"], "offender": m["name"], "model": model.name,
        }
        conf = float(p.max())
        risk_rows.append((m["accused_master_id"], m["district_id"], mv_id,
                          score, level, Json(factors)))
        inf_rows.append((mv_id, "accused", "EntityGraph", str(m["entity_id"]),
                         Json({feat.FEATURE_NAMES[j]: round(float(X[i][j]), 4)
                               for j in range(len(feat.FEATURE_NAMES))}),
                         Json({"risk_band": band, "risk_score": score}), round(conf, 5)))

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimeRiskScore" WHERE "ModelVersionID"=%s '
                    'AND "AccusedMasterID" IS NOT NULL', (mv_id,))
        execute_values(
            cur,
            'INSERT INTO "CrimeRiskScore" ("AccusedMasterID","DistrictID","ModelVersionID",'
            '"RiskScore","RiskLevel","Factors") VALUES %s',
            risk_rows, page_size=2000)
        execute_values(
            cur,
            'INSERT INTO "ModelInference" ("ModelVersionID","EntityType","RefTable","RefID",'
            '"Input","Output","Confidence") VALUES %s',
            inf_rows, page_size=2000)

    matviews.refresh_matview(conn, "mv_district_risk_profile")
    return {"offenders_scored": len(risk_rows), "model": model.name,
            "model_version_id": mv_id, "context_size": int(len(sel)),
            "sampled": bool(limit), "band_distribution": band_counts}


# ---- on-demand scoring (one offender) --------------------------------------
def score_one(conn, entity_id: int, seed: int = 42, context_size: int = 1000) -> dict | None:
    data = feat.build(conn, seed=seed)
    X, y, meta = data["X"], data["y"], data["meta"]
    idx = next((i for i, m in enumerate(meta) if m["entity_id"] == entity_id), None)
    if idx is None:
        return None
    m = meta[idx]
    model = mi.get_foundation_model()
    sel = _stratified_context(X, y, n=context_size, seed=seed)
    model.fit(X[sel], y[sel])
    p = model.predict_proba(X[idx:idx + 1])[0]
    score, band, exp_class = _risk_from_proba(p)
    level = models.risk_level_for(score)
    weights, mu, sd = _surrogate_weights(X, y)
    sd_safe = sd.copy(); sd_safe[sd_safe == 0] = 1.0
    z = (X[idx] - mu) / sd_safe
    factors = {
        "risk_band": band, "expected_class": round(exp_class, 3),
        "probs": {RISK_BANDS[c]: round(float(p[c]), 4) for c in mi.CLASSES},
        "top_factors": _factors_for(X[idx], z, weights),
        "features": {feat.FEATURE_NAMES[j]: round(float(X[idx][j]), 4)
                     for j in range(len(feat.FEATURE_NAMES))},
        "entity_id": entity_id, "offender": m["name"], "model": model.name,
    }
    mv_id = models.get_or_create_model_version(
        conn, model.name, "classification", "1.0.0", framework=model.family)
    with conn.cursor() as cur:
        if m["accused_master_id"] is not None:
            cur.execute('DELETE FROM "CrimeRiskScore" WHERE "ModelVersionID"=%s '
                        'AND "AccusedMasterID"=%s', (mv_id, m["accused_master_id"]))
        cur.execute(
            'INSERT INTO "CrimeRiskScore" ("AccusedMasterID","DistrictID","ModelVersionID",'
            '"RiskScore","RiskLevel","Factors") VALUES (%s,%s,%s,%s,%s,%s) RETURNING "RiskScoreID"',
            (m["accused_master_id"], m["district_id"], mv_id, score, level, Json(factors)))
        rid = cur.fetchone()[0]
        models.log_inference(
            conn, mv_id, entity_type="accused", ref_table="EntityGraph",
            ref_id=str(entity_id),
            inputs=factors["features"], outputs={"risk_band": band, "risk_score": score},
            confidence=round(float(p.max()), 5))
    return {"risk_score_id": rid, "entity_id": entity_id, "accused_master_id": m["accused_master_id"],
            "risk_band": band, "risk_score": score, "risk_level": level, "factors": factors}


# ---- calibration report ----------------------------------------------------
def _ece(proba, y_true, n_bins=10):
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    correct = (pred == y_true).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for b in range(n_bins):
        m = (conf > bins[b]) & (conf <= bins[b + 1])
        if m.sum() > 0:
            ece += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(ece)


def _brier(proba, y_true):
    onehot = np.zeros_like(proba)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(((proba - onehot) ** 2).sum(axis=1).mean())


def calibration_report(conn, seed: int = 42, test_frac: float = 0.3) -> dict:
    from sklearn.metrics import accuracy_score, f1_score
    data = feat.build(conn, seed=seed)
    X, y = data["X"], data["y"]
    rng = np.random.default_rng(seed)
    n = len(X)
    perm = rng.permutation(n)
    n_test = int(n * test_frac)
    te, tr = perm[:n_test], perm[n_test:]

    foundation = mi.get_foundation_model()
    sel = _stratified_context(X[tr], y[tr], n=1000, seed=seed)
    foundation.fit(X[tr][sel], y[tr][sel])
    p_found = foundation.predict_proba(X[te])

    baseline = mi.get_baseline_model()
    baseline.fit(X[tr], y[tr])
    p_base = baseline.predict_proba(X[te])

    def metrics(p):
        pred = p.argmax(axis=1)
        return {"accuracy": round(float(accuracy_score(y[te], pred)), 4),
                "macro_f1": round(float(f1_score(y[te], pred, average="macro")), 4),
                "brier": round(_brier(p, y[te]), 4),
                "ece": round(_ece(p, y[te]), 4)}

    agree = float((p_found.argmax(1) == p_base.argmax(1)).mean())
    report = {"n_train": len(tr), "n_test": len(te),
              "foundation": {"model": foundation.name, **metrics(p_found)},
              "baseline": {"model": baseline.name, **metrics(p_base)},
              "agreement": round(agree, 4)}

    # register both + audit
    fmv = models.get_or_create_model_version(conn, foundation.name, "classification", "1.0.0",
                                             framework=foundation.family, metrics=report["foundation"])
    bmv = models.get_or_create_model_version(conn, baseline.name, "classification", "1.0.0",
                                             framework=baseline.family, metrics=report["baseline"])
    models.log_inference(conn, fmv, inputs={"test_frac": test_frac},
                         outputs=report, ref_table="CrimeRiskScore")
    report["foundation"]["model_version_id"] = fmv
    report["baseline"]["model_version_id"] = bmv
    return report
