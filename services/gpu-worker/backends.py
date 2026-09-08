"""GPU model backends for the external AWS custom-model plane (Prompt 14 G.3 /
Prompt 24).

This module runs ONLY on AWS SageMaker / AWS Batch GPU compute (or a local CUDA
host for validation), never inside Catalyst AppSail. It is the single place that
loads real TabFM / TimesFM weights.

Hard rules enforced here:
  * A ``tabfm`` request selects CUDA explicitly and loads the REAL Google TabFM
    v1.0.0 weights (``google/tabfm-1.0.0-pytorch``, Apache-2.0) into the real
    ``TabFMClassifier`` in-context learner. Precision uses the classifier's AMP
    autocast (fp16 on Turing/T4, bf16 on Ampere+); no manual dtype cast that
    would break on a T4.
  * A ``timesfm`` request loads the REAL Google TimesFM 2.5-200M PyTorch model
    (``google/timesfm-2.5-200m-pytorch``, Apache-2.0), compiles a continuous
    quantile head and returns calibrated interval forecasts. The 2.5 torch model
    auto-selects cuda:0 when available.
  * If CUDA is unavailable OR the real weights cannot be loaded, the job FAILS
    CLOSED (raises ``BackendUnavailable``). It NEVER silently returns a CPU
    fallback labelled as TabFM/TimesFM. A separately named fallback request may
    run afterwards, reported with its TRUE backend + device.
  * ``eval()`` / inference-mode; queries chunked to bounded memory; measured GPU
    name / memory / cold-start / inference latency reported.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import _tabfm_loader

TIMESFM_HF_REPO = os.getenv("TIMESFM_HF_REPO", "google/timesfm-2.5-200m-pytorch")
_TABFM_ESTIMATORS = int(os.getenv("DRISHTI_TABFM_ESTIMATORS", "8"))
_TIMESFM_MAX_CONTEXT = int(os.getenv("DRISHTI_TIMESFM_MAX_CONTEXT", "1024"))
_TIMESFM_MAX_HORIZON = int(os.getenv("DRISHTI_TIMESFM_MAX_HORIZON", "64"))
_ABSTAIN_BELOW = float(os.getenv("DRISHTI_TABFM_ABSTAIN_BELOW", "0.34"))


class BackendUnavailable(RuntimeError):
    """Raised when a requested real backend/device cannot be honored. Fail closed."""


@dataclass
class BackendResult:
    actual_backend: str
    actual_device: str
    predictions: list[dict]
    model_artifact_digest: str
    confidence: Optional[float] = None
    abstained: Optional[bool] = None
    runtime_ms: Optional[int] = None
    cold_start_ms: Optional[int] = None
    peak_gpu_mem_mb: Optional[float] = None
    gpu_name: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Device helpers
# --------------------------------------------------------------------------- #
def _require_cuda():
    """Return the torch module iff a CUDA device is actually present, else fail."""
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        raise BackendUnavailable(f"torch not importable: {exc}") from exc
    if not torch.cuda.is_available():
        raise BackendUnavailable("CUDA is not available on this worker (fail closed).")
    return torch


def _autocast_dtype(torch):
    """bf16 on Ampere+ (cc>=8.0), fp16 on Turing/T4 (cc 7.5). T4 lacks native bf16."""
    major = torch.cuda.get_device_capability(0)[0]
    return torch.bfloat16 if major >= 8 else torch.float16


def _numerical_smoke_test(torch, device, dtype) -> None:
    """Prove a low-precision matmul on the device is numerically sane before real
    inference (guards a broken driver / unsupported dtype)."""
    a = torch.randn(64, 64, device=device, dtype=dtype)
    b = torch.randn(64, 64, device=device, dtype=dtype)
    out = (a @ b).float()
    ref = a.float() @ b.float()
    rel = (out - ref).abs().max().item() / (ref.abs().max().item() + 1e-6)
    if rel > 0.08:
        raise BackendUnavailable(
            f"low-precision numerical smoke test failed (rel err {rel:.3f}).")


# --------------------------------------------------------------------------- #
# TabFM (station workload band) — real in-context classification
# --------------------------------------------------------------------------- #
def _tabfm_infer_core(device_str: str, context_x, context_y, query_rows, *,
                      n_bands: int, weight_digest: str, chunk: int):
    """Device-parametrised REAL TabFM inference. Used by ``run_tabfm`` (cuda) and
    the local self-test (cpu). Returns ``(preds, digest, license_id, timings)``."""
    import numpy as np
    from tabfm import TabFMClassifier

    t_load = time.time()
    base, digest, license_id = _tabfm_loader.load_base_model(
        model_type="classification", device=device_str, expected_digest=weight_digest)
    load_s = time.time() - t_load

    clf = TabFMClassifier(model=base, n_estimators=_TABFM_ESTIMATORS,
                          random_state=42, use_amp=True, verbose=False)
    Xc = np.asarray(context_x, dtype=float)
    yc = np.asarray(context_y, dtype=int)
    clf.fit(Xc, yc)  # in-context: sets labelled examples; does NOT update pretrained weights
    classes = [int(c) for c in getattr(clf, "classes_", list(range(n_bands)))]

    t_inf = time.time()
    preds: list[dict] = []
    query = np.asarray(query_rows, dtype=float)
    for i in range(0, len(query), chunk):
        proba = np.asarray(clf.predict_proba(query[i:i + chunk]))
        for j, row in enumerate(proba):
            full = [0.0] * n_bands
            for col, cls in enumerate(classes):
                if 0 <= cls < n_bands:
                    full[cls] = float(row[col])
            total = sum(full) or 1.0
            full = [x / total for x in full]
            preds.append({
                "row": i + j,
                "band_probabilities": [round(x, 6) for x in full],
                "band_ordinal": int(max(range(n_bands), key=full.__getitem__)),
            })
    infer_s = time.time() - t_inf
    return preds, digest, license_id, {"load_s": load_s, "infer_s": infer_s}


def run_tabfm(columns, context_x, context_y, query_rows, *, n_bands: int,
              weight_digest: str, predict_chunk_size: int = 512) -> BackendResult:
    """Real Google TabFM zero-shot in-context inference on CUDA. Fails closed."""
    torch = _require_cuda()
    device = torch.device("cuda:0")
    gpu_name = torch.cuda.get_device_name(0)
    _numerical_smoke_test(torch, device, _autocast_dtype(torch))

    if context_x is None or context_y is None:
        raise BackendUnavailable("TabFM requires labelled in-context examples (context_x/y).")

    t_cold = time.time()
    try:
        torch.cuda.reset_peak_memory_stats(device)
        preds, digest, license_id, timings = _tabfm_infer_core(
            "cuda", context_x, context_y, query_rows,
            n_bands=n_bands, weight_digest=weight_digest, chunk=predict_chunk_size)
    except (FileNotFoundError, RuntimeError) as exc:
        # missing/mismatched weights or licence -> fail closed as TabFM-unavailable
        raise BackendUnavailable(f"TabFM weights/licence unavailable: {exc}") from exc
    except ImportError as exc:
        raise BackendUnavailable(f"TabFM package not available: {exc}") from exc
    peak_mb = torch.cuda.max_memory_allocated(device) / 1e6

    # A numerically broken forward pass (e.g. an fp16 overflow) yields NaN/Inf
    # probabilities. Returning those as a COMPLETED result would violate the
    # fail-closed contract, so reject them here rather than shipping NaN bands.
    if not preds:
        raise BackendUnavailable("TabFM returned no predictions (fail closed).")
    for pred in preds:
        if not all(math.isfinite(x) for x in pred["band_probabilities"]):
            raise BackendUnavailable(
                "TabFM produced non-finite (NaN/Inf) band probabilities — fail "
                "closed. The parameter dtype most likely cannot represent this "
                "model's activations; see _tabfm_loader._resolve_dtype.")

    top = [max(p["band_probabilities"]) for p in preds] if preds else []
    confidence = float(sum(top) / len(top)) if top else None
    abstained = bool(confidence is not None and confidence < _ABSTAIN_BELOW)
    cold_ms = int(timings["load_s"] * 1000)
    runtime_ms = int(timings["infer_s"] * 1000)
    warnings = [f"tabfm license={license_id}"]
    if abstained:
        warnings.append(f"low-confidence: mean top-prob {confidence:.3f} < {_ABSTAIN_BELOW}")
    return BackendResult(
        actual_backend="tabfm", actual_device="cuda", predictions=preds,
        model_artifact_digest=digest, confidence=confidence, abstained=abstained,
        runtime_ms=runtime_ms, cold_start_ms=cold_ms, peak_gpu_mem_mb=peak_mb,
        gpu_name=gpu_name, warnings=warnings)


# --------------------------------------------------------------------------- #
# TimesFM (count forecast) — real zero-shot forecast with quantile intervals
# --------------------------------------------------------------------------- #
def _extract_series(query_rows) -> list[float]:
    """Interpret the query rows as a univariate target series (column 0)."""
    series: list[float] = []
    for row in query_rows:
        if isinstance(row, (list, tuple)):
            if not row:
                continue
            series.append(float(row[0]))
        else:
            series.append(float(row))
    return series


@lru_cache(maxsize=2)
def _load_timesfm(repo: str, max_context: int, max_horizon: int):
    """Load + compile TimesFM ONCE per worker process and cache it.

    Without this cache every request built a fresh ``TimesFM_2p5_200M_torch`` and
    left it resident on the device. Serving 37 district forecasts accumulated
    ~14 GiB of PyTorch allocations next to the pinned TabFM model and the endpoint
    died with "CUDA out of memory. Tried to allocate 20.00 MiB". It also made each
    request pay a ~5 s model load instead of ~0.2 s of actual inference.

    Returns ``(model, weight_digest)``. The digest is best-effort observability and
    is computed once here rather than re-hashing the weight file per request.
    """
    from timesfm import ForecastConfig, TimesFM_2p5_200M_torch

    model = TimesFM_2p5_200M_torch.from_pretrained(repo)
    model.compile(ForecastConfig(
        max_context=max_context, max_horizon=max_horizon,
        normalize_inputs=True, use_continuous_quantile_head=True,
        fix_quantile_crossing=True, infer_is_positive=True))

    digest = ""
    try:
        from huggingface_hub import snapshot_download

        wpath = os.path.join(snapshot_download(repo_id=repo), "model.safetensors")
        if os.path.exists(wpath):
            digest = _tabfm_loader.sha256_file(wpath)
    except Exception:  # noqa: BLE001 — digest is best-effort observability
        digest = ""
    return model, digest


def _timesfm_infer_core(device_hint: str, series, *, horizon: int):
    """Device-aware REAL TimesFM inference. The 2.5 torch model auto-selects
    cuda:0 when available. Returns ``(preds, digest, device_str, timings)``."""
    import numpy as np

    horizon = int(min(max(horizon, 1), _TIMESFM_MAX_HORIZON))

    t_load = time.time()
    model, digest = _load_timesfm(TIMESFM_HF_REPO, _TIMESFM_MAX_CONTEXT,
                                 _TIMESFM_MAX_HORIZON)
    load_s = time.time() - t_load

    device_str = str(getattr(getattr(model, "model", None), "device", device_hint))

    values = np.asarray(_extract_series(series)[-_TIMESFM_MAX_CONTEXT:], dtype=np.float32)
    if values.size < 3:
        raise BackendUnavailable("TimesFM requires a series of at least 3 points.")

    t_inf = time.time()
    point, quant = model.forecast(horizon=horizon, inputs=[values])
    infer_s = time.time() - t_inf

    point = np.asarray(point)[0]        # (horizon,)
    quant = np.asarray(quant)[0]        # (horizon, 10): [mean, q0.1..q0.9]
    if not (np.isfinite(point).all() and np.isfinite(quant).all()):
        raise BackendUnavailable(
            "TimesFM produced non-finite (NaN/Inf) forecast values — fail closed.")
    preds = []
    for k in range(horizon):
        q = quant[k]
        preds.append({
            "step": k + 1,
            "point": round(float(point[k]), 4),
            "p10": round(float(q[1]), 4),
            "p50": round(float(q[5]), 4),
            "p90": round(float(q[9]), 4),
            "quantiles": [round(float(x), 4) for x in q],
        })
    return preds, digest, device_str, {"load_s": load_s, "infer_s": infer_s}


def run_timesfm(series, *, horizon: int, freq: str, weight_digest: str) -> BackendResult:
    """Real TimesFM 2.5 zero-shot count forecast on CUDA with quantile intervals.
    Fails closed if CUDA/weights are unavailable."""
    torch = _require_cuda()
    device = torch.device("cuda:0")
    gpu_name = torch.cuda.get_device_name(0)

    t_cold = time.time()
    try:
        torch.cuda.reset_peak_memory_stats(device)
        preds, digest, device_str, timings = _timesfm_infer_core("cuda", series, horizon=horizon)
    except ImportError as exc:
        raise BackendUnavailable(f"timesfm not available: {exc}") from exc
    peak_mb = torch.cuda.max_memory_allocated(device) / 1e6

    if not device_str.startswith("cuda"):
        raise BackendUnavailable(
            f"TimesFM did not run on CUDA (device={device_str}); fail closed.")

    # interval-width -> confidence proxy on the first step
    conf = None
    if preds:
        first = preds[0]
        med = max(abs(first["p50"]), 1e-6)
        width = (first["p90"] - first["p10"]) / (2.0 * med)
        conf = round(float(1.0 / (1.0 + width)), 4)
    return BackendResult(
        actual_backend="timesfm", actual_device="cuda", predictions=preds,
        model_artifact_digest=digest, confidence=conf, abstained=False,
        runtime_ms=int(timings["infer_s"] * 1000),
        cold_start_ms=int(timings["load_s"] * 1000),
        peak_gpu_mem_mb=peak_mb, gpu_name=gpu_name,
        warnings=[f"timesfm freq={freq}", "timesfm license=apache-2.0"])


# --------------------------------------------------------------------------- #
# CPU fallback — reports its TRUE backend so it is never mislabelled as tabfm
# --------------------------------------------------------------------------- #
def run_fallback(columns, context_x, context_y, query_rows, *, backend: str,
                 n_bands: int) -> BackendResult:
    """CPU fallback (tabpfn / incontext / baseline). Reports its TRUE backend +
    device so it can never masquerade as tabfm. Only run when EXPLICITLY requested."""
    import numpy as np
    from sklearn.neighbors import NearestNeighbors

    Xc = np.asarray(context_x, dtype=float)
    yc = np.asarray(context_y, dtype=int)
    query = np.asarray(query_rows, dtype=float)
    t0 = time.time()
    mu, sd = Xc.mean(0), Xc.std(0)
    sd[sd == 0] = 1.0
    Xn, Qn = (Xc - mu) / sd, (query - mu) / sd
    k = min(50, len(Xn))
    nn = NearestNeighbors(n_neighbors=k).fit(Xn)
    dist, idx = nn.kneighbors(Qn)
    bandwidth = max(float(np.median(dist)), 1e-3)
    weight = np.exp(-(dist ** 2) / (2 * bandwidth ** 2)) + 1e-9
    preds = []
    for r in range(len(Qn)):
        proba = np.zeros(n_bands)
        for c in range(n_bands):
            proba[c] = (weight[r] * (yc[idx[r]] == c)).sum()
        proba /= proba.sum()
        preds.append({"row": r, "band_probabilities": [float(x) for x in proba],
                      "band_ordinal": int(proba.argmax())})
    return BackendResult(
        actual_backend=backend or "incontext", actual_device="cpu", predictions=preds,
        model_artifact_digest="cpu-fallback-no-weights",
        runtime_ms=int((time.time() - t0) * 1000),
        warnings=["explicit fallback backend — NOT tabfm; CPU distance-weighted vote"])


def report_environment() -> dict:
    """Best-effort device report for the /ping health handler."""
    info = {"cuda": False, "gpu_name": None, "torch": None}
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda"] = bool(torch.cuda.is_available())
        if info["cuda"]:
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["compute_capability"] = ".".join(map(str, torch.cuda.get_device_capability(0)))
    except Exception:  # noqa: BLE001
        pass
    info["worker_version"] = os.getenv("GPU_WORKER_VERSION", "0.2.0")
    return info
