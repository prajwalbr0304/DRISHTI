"""Learned spatio-temporal forecasting layer (doc 05 Layer 3), uncertainty-aware.

Primary: a REAL spatio-temporal GNN on the PyTorch-Geometric stack — a GRU encodes
each district's recent monthly window (temporal) and a GCNConv mixes neighbours over
the district adjacency graph (spatial spillover). Uncertainty is Bayesian via
MC-dropout: dropout stays active at inference and N stochastic passes give a
per-district mean + std -> honest confidence bands.

(torch-geometric-temporal's prebuilt ST-GNN classes require torch-scatter/torch-
sparse, which have no wheels for this torch build; this model uses torch-geometric
directly to the same end. A pure-numpy graph-diffusion fallback runs if torch /
torch-geometric are unavailable.)
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
from psycopg2.extras import Json, execute_values

from .. import models
from ..geo import trends
from . import features as feat

_Z90 = 1.2816


# ---------------------------------------------------------------------------
def _load_series(conn, head_id, window):
    adj = feat.district_adjacency(conn, k=4)
    ids = [d for d in adj]
    series, last_period = {}, None
    for d in ids:
        p, c = trends.monthly_series(conn, district_id=d, head_id=head_id)
        if len(c) >= window + 2:
            series[d] = (p, c)
            last_period = p[-1]
    ids = [d for d in ids if d in series]
    return adj, ids, series, last_period


def _next_window(last_period: str, horizon_days: int):
    y, m = map(int, last_period.split("-"))
    start = dt.datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(days=horizon_days)


def _write(conn, head_id, model_name, version, framework, hyperparams, districts, start, end):
    centroids = feat.district_centroids(conn)
    names = feat.district_names(conn)
    mv_id = models.get_or_create_model_version(
        conn, model_name, "forecasting", version, framework=framework, hyperparameters=hyperparams)
    scale = max((d["mean"] for d in districts), default=1.0) or 1.0
    rows, out = [], []
    for r in districts:
        d = r["district_id"]
        lon, lat = centroids.get(d, (None, None))
        fj = {"layer": "st_gnn", "model": framework, "mean": round(r["mean"], 3),
              "std": round(r["std"], 3), "lower_p10": round(r["lower"], 3),
              "upper_p90": round(r["upper"], 3), **r.get("extra", {})}
        rows.append((mv_id, d, head_id, start, end, round(r["mean"], 2),
                     round(min(1.0, r["mean"] / (scale * 1.5)), 5), r["confidence"],
                     Json(fj), lon, lon, lat))
        out.append({"district_id": d, "district": names.get(d), "mean": round(r["mean"], 2),
                    "std": round(r["std"], 2), "lower_p10": round(r["lower"], 2),
                    "upper_p90": round(r["upper"], 2), "confidence": r["confidence"]})
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "CrimePrediction" WHERE "Features"->>\'layer\'=\'st_gnn\' '
                    'AND "CrimeHeadID" IS NOT DISTINCT FROM %s', (head_id,))
        execute_values(
            cur,
            'INSERT INTO "CrimePrediction" ("ModelVersionID","DistrictID","CrimeHeadID",'
            '"PredictionStart","PredictionEnd","PredictedCount","Probability","Confidence",'
            '"Features","geom") VALUES %s',
            rows,
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                     "CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END)",
            page_size=200)
        models.log_inference(conn, mv_id, ref_table="CrimePrediction",
                             inputs={"head_id": head_id, **hyperparams},
                             outputs={"districts": len(rows), "framework": framework})
    return {"written": len(rows), "model": framework, "model_version_id": mv_id, "districts": out,
            "prediction_start": start.isoformat(), "prediction_end": end.isoformat()}


# ---- REAL PyG spatio-temporal GNN (GRU + GCN, MC-dropout uncertainty) ------
def _run_torch_stgnn(conn, head_id, window, horizon_days, epochs=80, mc_samples=30,
                     hidden=32, dropout=0.2, seed=42) -> dict:
    import torch
    import torch.nn as nn
    from torch_geometric.nn import GCNConv
    torch.manual_seed(seed)
    np.random.seed(seed)

    adj, ids, series, last_period = _load_series(conn, head_id, window)
    if len(ids) < 3:
        raise RuntimeError("insufficient districts for ST-GNN")
    idx = {d: i for i, d in enumerate(ids)}
    T = min(len(series[d][1]) for d in ids)
    C = np.array([series[d][1][-T:] for d in ids], dtype=np.float32)   # (n, T)
    node_mean = C.mean(axis=1, keepdims=True)
    node_mean[node_mean == 0] = 1.0
    Cn = torch.tensor(C / node_mean)                                  # per-node normalised

    src, dst, w = [], [], []
    for d in ids:
        for nb in adj[d]:
            if nb in idx:
                src.append(idx[d]); dst.append(idx[nb]); w.append(1.0)
    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_weight = torch.tensor(w, dtype=torch.float32)

    class STGNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(1, hidden, batch_first=True)     # temporal
            self.gcn = GCNConv(hidden, hidden)                 # spatial spillover
            self.drop = nn.Dropout(dropout)
            self.out = nn.Linear(hidden, 1)

        def forward(self, xseq, ei, ew):
            _, h = self.gru(xseq)                              # (1, n, hidden)
            h = self.drop(torch.relu(h.squeeze(0)))
            h = self.drop(torch.relu(self.gcn(h, ei, ew)))
            return self.out(h).squeeze(-1)                     # (n,)

    model = STGNN()
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    lossf = nn.MSELoss()
    ts = list(range(window, T))
    model.train()
    for _ in range(epochs):
        np.random.shuffle(ts)
        for t in ts:
            xseq = Cn[:, t - window:t].unsqueeze(-1)           # (n, window, 1)
            opt.zero_grad()
            loss = lossf(model(xseq, edge_index, edge_weight), Cn[:, t])
            loss.backward()
            opt.step()

    # MC-dropout inference: dropout ON, N stochastic passes -> mean + std
    xfin = Cn[:, T - window:T].unsqueeze(-1)
    model.train()
    preds = []
    with torch.no_grad():
        for _ in range(mc_samples):
            preds.append(model(xfin, edge_index, edge_weight).numpy())
    P = np.stack(preds)                                        # (mc, n) normalised
    mean_n, std_n = P.mean(axis=0), P.std(axis=0)
    nm = node_mean[:, 0]
    mean = np.maximum(0.0, mean_n * nm)
    std = np.abs(std_n * nm)

    start, end = _next_window(last_period, horizon_days)
    districts = []
    for d in ids:
        i = idx[d]
        m_, s_ = float(mean[i]), float(std[i])
        lower, upper = max(0.0, m_ - _Z90 * s_), m_ + _Z90 * s_
        cv = (upper - lower) / (2.0 * max(m_, 1e-6))
        districts.append({"district_id": d, "mean": m_, "std": s_, "lower": lower, "upper": upper,
                          "confidence": round(float(1.0 / (1.0 + cv)), 4),
                          "extra": {"mc_samples": mc_samples, "neighbours": sorted(adj[d])}})
    return _write(conn, head_id, "drishti-forecast-stgnn", "2.0.0", "pyg-gcn-gru-mcdropout",
                  {"window": window, "hidden": hidden, "dropout": dropout, "epochs": epochs,
                   "mc_samples": mc_samples, "uncertainty": "mc_dropout"}, districts, start, end)


# ---- numpy fallback: graph diffusion + temporal ----------------------------
def _base_forecast(counts, window):
    arr = np.array(counts, dtype=float)
    w = min(len(arr), window)
    x = np.arange(w)
    slope, intercept = np.polyfit(x, arr[-w:], 1)
    nxt = max(0.0, float(intercept + slope * w))
    sigma = float(np.sqrt(np.mean((arr[-w:] - (intercept + slope * x)) ** 2)))
    return nxt, sigma


def _run_numpy_stgnn(conn, head_id, window, alpha, diffusion_steps, horizon_days) -> dict:
    adj, ids, series, last_period = _load_series(conn, head_id, window)
    if not ids:
        return {"written": 0, "districts": []}
    base, sigma_local = {}, {}
    for d in ids:
        base[d], sigma_local[d] = _base_forecast(series[d][1], window)
    f = dict(base)
    for _ in range(diffusion_steps):
        f = {d: (1 - alpha) * f[d] + alpha * (np.mean([f[n] for n in adj[d] if n in f])
                                              if [n for n in adj[d] if n in f] else f[d])
             for d in ids}
    start, end = _next_window(last_period, horizon_days)
    districts = []
    for d in ids:
        neigh = [n for n in adj[d] if n in base]
        disagree = float(np.std([base[n] for n in neigh])) if neigh else 0.0
        std_d = float(np.sqrt(sigma_local[d] ** 2 + disagree ** 2))
        m_ = max(0.0, f[d])
        lower, upper = max(0.0, m_ - _Z90 * std_d), m_ + _Z90 * std_d
        cv = (upper - lower) / (2.0 * max(m_, 1e-6))
        districts.append({"district_id": d, "mean": m_, "std": std_d, "lower": lower, "upper": upper,
                          "confidence": round(float(1.0 / (1.0 + cv)), 4),
                          "extra": {"spillover_alpha": alpha, "neighbours": neigh,
                                    "neighbour_disagreement": round(disagree, 3)}})
    return _write(conn, head_id, "drishti-forecast-stgnn", "1.0.0", "graph-diffusion-temporal",
                  {"window": window, "alpha": alpha, "diffusion_steps": diffusion_steps},
                  districts, start, end)


def run_stgnn(conn, head_id: Optional[int] = None, window: int = 12, horizon_days: int = 30,
              alpha: float = 0.3, diffusion_steps: int = 2, epochs: int = 80,
              mc_samples: int = 30) -> dict:
    """Real PyG ST-GNN when torch-geometric is available; numpy graph-diffusion otherwise."""
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
        return _run_torch_stgnn(conn, head_id, window, horizon_days, epochs=epochs, mc_samples=mc_samples)
    except Exception as e:  # pragma: no cover - observable, non-silent fallback
        import sys, traceback
        print(f"[stgnn] PyG ST-GNN unavailable ({type(e).__name__}: {e}); "
              "falling back to numpy graph-diffusion.", file=sys.stderr)
        traceback.print_exc()
        return _run_numpy_stgnn(conn, head_id, window, alpha, diffusion_steps, horizon_days)
