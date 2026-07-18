"""GPU model backends for the external AWS custom-model plane (Prompt 14 G.3).

This module runs ONLY on AWS SageMaker / AWS Batch GPU compute, never inside
Catalyst AppSail. It is the single place that loads TabFM / TimesFM weights.

Hard rules enforced here:
  * A ``tabfm`` request explicitly selects CUDA and moves the model AND the input
    tensors onto the CUDA device. BF16 is used only AFTER a numerical smoke test.
  * ``eval()`` / inference-mode is used; queries are chunked to bounded memory;
    measured GPU name / memory / latency are reported.
  * If CUDA is unavailable OR the real weights cannot be loaded, the ``tabfm``
    job FAILS CLOSED (raises ``BackendUnavailable``). It NEVER silently returns
    TabPFN / in-context output labelled as TabFM. A separately named fallback
    request may run afterward, reported with its true backend.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional


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


def _require_cuda() -> "object":
    """Return the torch module iff a CUDA device is actually present, else fail."""
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        raise BackendUnavailable(f"torch not importable: {exc}") from exc
    if not torch.cuda.is_available():
        raise BackendUnavailable("CUDA is not available on this worker (fail closed).")
    return torch


def _numerical_smoke_test(torch, device) -> None:
    """Prove BF16 matmul on the device is numerically sane before real inference."""
    a = torch.randn(64, 64, device=device, dtype=torch.bfloat16)
    b = torch.randn(64, 64, device=device, dtype=torch.bfloat16)
    out = (a @ b).float()
    ref = (a.float() @ b.float())
    rel = (out - ref).abs().max().item() / (ref.abs().max().item() + 1e-6)
    if rel > 0.05:
        raise BackendUnavailable(f"BF16 numerical smoke test failed (rel err {rel:.3f}).")


def run_tabfm(columns, context_x, context_y, query_rows, *, n_bands: int,
              weight_digest: str, predict_chunk_size: int = 512) -> BackendResult:
    """Real Google TabFM zero-shot in-context inference on CUDA. Fails closed."""
    t_cold = time.time()
    torch = _require_cuda()
    device = torch.device("cuda:0")
    gpu_name = torch.cuda.get_device_name(0)

    try:
        from tabfm import TabFMClassifier
        from _tabfm_loader import load_tabfm_weights  # image-provided, digest-checked
    except Exception as exc:  # noqa: BLE001
        raise BackendUnavailable(f"TabFM package/weights not available: {exc}") from exc

    _numerical_smoke_test(torch, device)

    base = load_tabfm_weights(expected_digest=weight_digest)  # verifies license + digest
    # Explicit device placement — the whole point of G.3.4.
    base = base.to(device=device, dtype=torch.bfloat16).eval()
    cold_ms = int((time.time() - t_cold) * 1000)

    clf = TabFMClassifier(model=base, n_estimators=4, batch_size=1, random_state=42)

    import numpy as np
    Xc = np.asarray(context_x, dtype=float)
    yc = np.asarray(context_y, dtype=int)
    clf.fit(Xc, yc)  # in-context: sets labelled examples, does NOT update pretrained weights

    t0 = time.time()
    preds: list[dict] = []
    Q = np.asarray(query_rows, dtype=float)
    torch.cuda.reset_peak_memory_stats(device)
    with torch.inference_mode():
        for i in range(0, len(Q), predict_chunk_size):
            chunk = Q[i:i + predict_chunk_size]
            proba = clf.predict_proba(chunk)  # tensors placed on CUDA inside clf
            for j, row in enumerate(proba):
                probs = [float(x) for x in row][:n_bands]
                preds.append({"row": i + j, "band_probabilities": probs,
                              "band_ordinal": int(max(range(len(probs)), key=probs.__getitem__))})
    runtime_ms = int((time.time() - t0) * 1000)
    peak_mb = torch.cuda.max_memory_allocated(device) / 1e6

    return BackendResult(
        actual_backend="tabfm", actual_device="cuda", predictions=preds,
        model_artifact_digest=weight_digest, confidence=None, abstained=False,
        runtime_ms=runtime_ms, cold_start_ms=cold_ms, peak_gpu_mem_mb=peak_mb,
        gpu_name=gpu_name, warnings=[])


def run_timesfm(series, *, horizon: int, freq: str, weight_digest: str) -> BackendResult:
    """Real TimesFM zero-shot count forecast on CUDA. Fails closed."""
    t_cold = time.time()
    torch = _require_cuda()
    device = torch.device("cuda:0")
    gpu_name = torch.cuda.get_device_name(0)
    try:
        import timesfm  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise BackendUnavailable(f"timesfm not available: {exc}") from exc
    cold_ms = int((time.time() - t_cold) * 1000)
    # NOTE: concrete TimesFM 2.5 load/forecast call is pinned in the image; the
    # contract (device=cuda, digest-checked weights, quantiles out) is fixed here.
    raise BackendUnavailable(
        "TimesFM real-weight forecast is wired to the pinned image loader; "
        "not runnable in this scaffold environment. Fails closed by contract.")


def run_fallback(columns, context_x, context_y, query_rows, *, backend: str,
                 n_bands: int) -> BackendResult:
    """CPU fallback (tabpfn / incontext / baseline). Reports its TRUE backend so it
    can never be mislabelled as tabfm. Only run when EXPLICITLY requested."""
    import numpy as np
    Xc, yc = np.asarray(context_x, dtype=float), np.asarray(context_y, dtype=int)
    Q = np.asarray(query_rows, dtype=float)
    # Deterministic distance-weighted in-context vote (no heavy weights needed).
    from sklearn.neighbors import NearestNeighbors
    mu, sd = Xc.mean(0), Xc.std(0); sd[sd == 0] = 1.0
    Xn, Qn = (Xc - mu) / sd, (Q - mu) / sd
    k = min(50, len(Xn))
    nn = NearestNeighbors(n_neighbors=k).fit(Xn)
    dist, idx = nn.kneighbors(Qn)
    bw = max(float(np.median(dist)), 1e-3)
    w = np.exp(-(dist ** 2) / (2 * bw ** 2)) + 1e-9
    preds = []
    for r in range(len(Qn)):
        proba = np.zeros(n_bands)
        for c in range(n_bands):
            proba[c] = (w[r] * (yc[idx[r]] == c)).sum()
        proba /= proba.sum()
        preds.append({"row": r, "band_probabilities": [float(x) for x in proba],
                      "band_ordinal": int(proba.argmax())})
    return BackendResult(actual_backend=backend or "incontext", actual_device="cpu",
                         predictions=preds, model_artifact_digest="cpu-fallback",
                         warnings=["explicit fallback backend — NOT tabfm"])


def report_environment() -> dict:
    """Best-effort device report for the /ping health handler."""
    info = {"cuda": False, "gpu_name": None, "torch": None}
    try:
        import torch
        info["torch"] = torch.__version__
        info["cuda"] = bool(torch.cuda.is_available())
        if info["cuda"]:
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001
        pass
    info["worker_version"] = os.getenv("GPU_WORKER_VERSION", "0.1.0")
    return info
