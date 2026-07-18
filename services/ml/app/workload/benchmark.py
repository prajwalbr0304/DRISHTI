"""Small / medium / full benchmarks for the workload task (Phase 13).

Records, per (model, scale), what the phase requires: 500 / 5,000 / full-row
runtime, CPU/GPU memory, latency/throughput, an indicative cost estimate and the
held-out metric comparison against the baselines. "Scale" is the number of
labelled context/training rows the model is fitted on; every candidate is scored
on the SAME fixed test split so the numbers are comparable.

The tractable models (prior-period, majority, gradient-boosted trees, in-context
foundation stand-in) run at every scale on CPU. The heavy real weights are gated:
TabPFN runs up to its efficient context size; the 3.3GB Google TabFM runs at the
small scale with a capped query count on CPU and is marked DEFERRED at larger
scales (AWS Batch GPU, Prompt 14) — recorded honestly rather than faked.
"""
from __future__ import annotations

import os
import time

import numpy as np

from . import evaluation
from . import features as feat
from . import models_iface as mi

# Indicative on-demand rates (ap-south-1) — DOCUMENTED ASSUMPTIONS, not live
# pricing. The cost estimate is directional; verify against current AWS pricing.
COST_ASSUMPTIONS = {
    "cpu_instance": {"name": "ml.m5.xlarge (assumed, ap-south-1)", "usd_per_hour": 0.23},
    "gpu_instance": {"name": "ml.g5.xlarge (assumed, ap-south-1)", "usd_per_hour": 1.40},
    "note": "Indicative SageMaker/EC2 on-demand rates; confirm against current AWS pricing.",
}
SCALES = [("small", 500), ("medium", 5000), ("full", None)]


def _rss_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1e6
    except Exception:  # noqa: BLE001
        return 0.0


def _gpu_mem_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / 1e6
        return None
    except Exception:  # noqa: BLE001
        return None


def _device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def _stratified_subsample(X, y, n, seed=42) -> tuple[np.ndarray, np.ndarray]:
    if n is None or n >= len(X):
        return X, y
    rng = np.random.default_rng(seed)
    idx_all = []
    for c in np.unique(y):
        idx = np.where(y == c)[0]
        take = max(1, int(round(n * len(idx) / len(X))))
        idx_all.append(rng.choice(idx, size=min(take, len(idx)), replace=False))
    idx = np.concatenate(idx_all)
    rng.shuffle(idx)
    return X[idx[:n]], y[idx[:n]]


def _cost(total_seconds: float, throughput: float, device: str) -> dict:
    inst = COST_ASSUMPTIONS["gpu_instance"] if device == "cuda" else COST_ASSUMPTIONS["cpu_instance"]
    rate = inst["usd_per_hour"]
    per_1000 = (1000.0 / throughput) * (rate / 3600.0) if throughput > 0 else None
    return {"instance": inst["name"], "usd_per_hour": rate,
            "usd_this_run": round(total_seconds * rate / 3600.0, 6),
            "usd_per_1000_predictions": round(per_1000, 6) if per_1000 is not None else None}


def _bench_one(model, Xtr, ytr, Xte, yte, n_bands, *, scale_label, row_scale,
               family, device, query_cap=None, note=None) -> dict:
    rss0 = _rss_mb()
    t0 = time.time()
    model.fit(Xtr, ytr)
    fit_s = time.time() - t0
    rss_fit = _rss_mb()
    Xq = Xte if not query_cap else Xte[:query_cap]
    yq = yte if not query_cap else yte[:query_cap]
    t1 = time.time()
    proba = model.predict_proba(Xq)
    pred_s = time.time() - t1
    rss_pred = _rss_mb()
    n_q = max(len(Xq), 1)
    throughput = n_q / pred_s if pred_s > 0 else 0.0
    m = evaluation._metric_block(yq, proba, n_bands)
    total = fit_s + pred_s
    return {
        "model_name": model.name, "family": family, "scale_label": scale_label,
        "row_scale": int(row_scale), "device": device,
        "fit_seconds": round(fit_s, 4), "predict_seconds": round(pred_s, 4),
        "total_seconds": round(total, 4),
        "latency_ms_per_row": round(1000.0 * pred_s / n_q, 4),
        "throughput_rows_per_sec": round(throughput, 2),
        "peak_rss_mb": round(max(rss_fit, rss_pred), 1),
        "gpu_mem_mb": (round(_gpu_mem_mb(), 1) if _gpu_mem_mb() is not None else None),
        "accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "qwk": m["qwk"], "ece": m["ece"],
        "cost_estimate": _cost(total, throughput, device),
        "metrics": {**m, "n_query_rows": n_q, "queries_capped": bool(query_cap)},
        "available": True, "note": note,
    }


def _deferred(model_name, family, scale_label, row_scale, reason) -> dict:
    return {"model_name": model_name, "family": family, "scale_label": scale_label,
            "row_scale": int(row_scale), "device": _device(), "available": False,
            "note": reason, "cost_estimate": {}, "metrics": {}}


def run_benchmark(conn, *, include_heavy: bool | None = None, tabfm_query_cap: int = 60,
                  tabfm_context: int = 500, seed: int = 42, ds=None,
                  level: str = "station") -> dict:
    """Run the benchmark grid and return {assumptions, device, level, rows:[...]}.

    The benchmark measures COMPUTATIONAL scaling (runtime/memory/latency/cost) at
    500/5,000/full-row context sizes, so it builds the larger STATION-level
    feature matrix (~16k rows) to reach those scales. The approved DISTRICT task
    is small-tabular (~500 rows) and is evaluated for QUALITY separately (held-out
    metrics + baselines). include_heavy defaults to env WORKLOAD_BENCH_HEAVY.
    """
    if include_heavy is None:
        include_heavy = os.getenv("WORKLOAD_BENCH_HEAVY", "").strip().lower() in ("1", "true", "yes")
    if ds is None:
        ds = feat.build_dataset(conn, level=level)
    device = _device()
    tr = ds.mask("train")
    Xtr_full, ytr_full = ds.X[tr], ds.y[tr]
    te = ds.mask("test")
    Xte, yte = ds.X[te], ds.y[te]
    recent_idx = ds.feature_names.index("wl_recent_case_volume")
    rows: list[dict] = []

    for scale_label, scale_n in SCALES:
        Xtr, ytr = _stratified_subsample(Xtr_full, ytr_full, scale_n, seed)
        eff = len(Xtr)

        # -- tractable models at every scale --
        rows.append(_bench_one(mi.PriorPeriodBaseline(ds.thresholds, recent_idx, ds.n_bands),
                               Xtr, ytr, Xte, yte, ds.n_bands, scale_label=scale_label,
                               row_scale=eff, family="baseline", device=device))
        rows.append(_bench_one(mi.MajorityClassBaseline(ds.n_bands), Xtr, ytr, Xte, yte, ds.n_bands,
                               scale_label=scale_label, row_scale=eff, family="baseline", device=device))
        rows.append(_bench_one(mi.GradientBoostingBaseline(ds.n_bands), Xtr, ytr, Xte, yte, ds.n_bands,
                               scale_label=scale_label, row_scale=eff, family="baseline", device=device))
        rows.append(_bench_one(mi.InContextFoundationModel(ds.n_bands), Xtr, ytr, Xte, yte, ds.n_bands,
                               scale_label=scale_label, row_scale=eff, family="foundation", device=device))

        # -- TabPFN: efficient up to a few thousand context rows --
        if include_heavy and eff <= 5000:
            try:
                rows.append(_bench_one(mi.TabPFNCandidate(ds.n_bands, device=device), Xtr, ytr,
                                       Xte, yte, ds.n_bands, scale_label=scale_label, row_scale=eff,
                                       family="foundation", device=device, query_cap=1000,
                                       note="real TabPFN v2 weights (1k-query cap)"))
            except Exception as e:  # noqa: BLE001
                rows.append(_deferred("drishti-workload-tabpfn", "foundation", scale_label, eff,
                                      f"TabPFN unavailable: {e}"))
        elif eff > 5000:
            rows.append(_deferred("drishti-workload-tabpfn", "foundation", scale_label, eff,
                                  "context exceeds TabPFN efficient range; deferred"))

        # -- Google TabFM: real 3.3GB weights, small scale + capped queries on CPU --
        if include_heavy and scale_label == "small":
            try:
                m = mi.TabFMCandidate(n_bands=ds.n_bands, n_estimators=2)
                Xtc, ytc = _stratified_subsample(Xtr_full, ytr_full, min(tabfm_context, eff), seed)
                rows.append(_bench_one(m, Xtc, ytc, Xte, yte, ds.n_bands, scale_label=scale_label,
                                       row_scale=len(Xtc), family="foundation", device=device,
                                       query_cap=tabfm_query_cap,
                                       note=f"real Google TabFM v1 weights, {tabfm_query_cap}-query cap, CPU"))
            except Exception as e:  # noqa: BLE001
                rows.append(_deferred("drishti-tabfm-workload", "foundation", scale_label, eff,
                                      f"TabFM unavailable on this host: {e}"))
        elif scale_label != "small":
            rows.append(_deferred("drishti-tabfm-workload", "foundation", scale_label, eff,
                                  "CPU-infeasible at this scale; deferred to AWS Batch GPU (Prompt 14)"))

    return {"assumptions": COST_ASSUMPTIONS, "device": device, "level": level,
            "test_rows": int(te.sum()), "train_rows_full": int(tr.sum()),
            "n_bands": ds.n_bands, "rows": rows}
