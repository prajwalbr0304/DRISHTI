"""ModelInterface for risk classification with pluggable backends (doc 02 §2-3).

  * foundation : TabFM/TabPFN family — zero-shot in-context learning ("context in,
                 prediction out, no per-dataset training"). Uses TabPFN if it is
                 importable (torch present); otherwise an in-context distance-
                 weighted classifier over the labelled context that follows the
                 same contract (the real model drops in behind this interface).
  * baseline   : gradient-boosted trees — XGBoost if importable, else sklearn
                 HistGradientBoosting — kept purely as a CALIBRATION reference.

All backends expose fit(context_X, context_y) + predict_proba(X) over the fixed
class set 0..4 (Low..Severe).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

N_CLASSES = 5
CLASSES = list(range(N_CLASSES))


class RiskModel(ABC):
    name: str = "abstract"
    family: str = "abstract"

    @abstractmethod
    def fit(self, X, y): ...

    @abstractmethod
    def predict_proba(self, X) -> np.ndarray: ...

    def predict(self, X) -> np.ndarray:
        return self.predict_proba(X).argmax(axis=1)


class _Standardizer:
    def fit(self, X):
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        return self

    def transform(self, X):
        return (X - self.mu) / self.sd


class InContextFoundationModel(RiskModel):
    """Zero-shot in-context classifier: no training loop; predictions come from
    distance-weighted voting over the provided labelled context (TabFM-family
    stand-in when TabPFN/torch is unavailable)."""
    name = "drishti-tabfm-incontext"
    family = "foundation"

    def __init__(self, k: int = 50, bandwidth: float | None = None):
        self.k = k
        self.bandwidth = bandwidth

    def fit(self, X, y):
        from sklearn.neighbors import NearestNeighbors
        self.scaler = _Standardizer().fit(X)
        self.Xc = self.scaler.transform(X)
        self.yc = np.asarray(y, dtype=int)
        k = min(self.k, len(self.Xc))
        self.nn = NearestNeighbors(n_neighbors=k).fit(self.Xc)
        # kernel bandwidth = median neighbour distance (scale-free)
        d, _ = self.nn.kneighbors(self.Xc[: min(500, len(self.Xc))])
        self._bw = self.bandwidth or max(float(np.median(d[:, 1:])), 1e-3)
        return self

    def predict_proba(self, X) -> np.ndarray:
        Xq = self.scaler.transform(np.asarray(X, dtype=float))
        dist, idx = self.nn.kneighbors(Xq)
        w = np.exp(-(dist ** 2) / (2 * self._bw ** 2)) + 1e-9
        proba = np.zeros((len(Xq), N_CLASSES))
        for c in CLASSES:
            mask = (self.yc[idx] == c)
            proba[:, c] = (w * mask).sum(axis=1)
        proba /= proba.sum(axis=1, keepdims=True)
        return proba


class TabPFNFoundationModel(RiskModel):
    """Real TabPFN v2 backend (only if importable)."""
    name = "drishti-tabpfn"
    family = "foundation"

    def __init__(self, device: str = "cpu"):
        from tabpfn import TabPFNClassifier  # noqa: F401
        # ignore_pretraining_limits lets us run on CPU; we still keep the context
        # small (<=1000 stratified rows) which is TabPFN's efficient sweet spot.
        self._clf = TabPFNClassifier(device=device, ignore_pretraining_limits=True)

    def fit(self, X, y):
        self._clf.fit(np.asarray(X), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X) -> np.ndarray:
        p = self._clf.predict_proba(np.asarray(X))
        # align to fixed 0..4 columns
        out = np.zeros((len(X), N_CLASSES))
        for j, c in enumerate(self._clf.classes_):
            out[:, int(c)] = p[:, j]
        return out


class GradientBoostingBaseline(RiskModel):
    """Gradient-boosted-tree calibration reference (XGBoost if present, else
    sklearn HistGradientBoosting)."""
    family = "baseline"

    def __init__(self):
        try:
            from xgboost import XGBClassifier
            self._clf = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                      objective="multi:softprob", num_class=N_CLASSES,
                                      verbosity=0)
            self.name = "drishti-xgboost"
        except Exception:
            from sklearn.ensemble import HistGradientBoostingClassifier
            self._clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4,
                                                       learning_rate=0.1, random_state=42)
            self.name = "drishti-histgbm"

    def fit(self, X, y):
        self._clf.fit(np.asarray(X), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X) -> np.ndarray:
        p = self._clf.predict_proba(np.asarray(X))
        out = np.zeros((len(X), N_CLASSES))
        for j, c in enumerate(self._clf.classes_):
            out[:, int(c)] = p[:, j]
        return out


# ---------------------------------------------------------------------------
# Google TabFM — the real zero-shot tabular foundation model (doc 02 §2).
# It is a 1.64B-param / 6.3GB model, so we load it lazily, once, and in a
# memory-lean bfloat16 form (a pre-converted 3.3GB file if present). On a GPU or
# a box with enough free RAM it is the PREFERRED foundation backend; otherwise
# get_foundation_model() falls back to TabPFN v2 then the in-context stand-in.
# ---------------------------------------------------------------------------
from pathlib import Path

_TABFM_BF16_FILE = Path(__file__).resolve().parents[2] / "models" / "tabfm_clf_bf16.safetensors"
_TABFM_MODEL_CACHE: dict = {}


def _tabfm_cast_wrapper(base_model, dtype):
    """Wrap TabFM so the classifier's float32 inputs are cast to the model dtype
    (bf16) and outputs cast back to float32. Delegates max_classes/params."""
    import torch

    class _CastWrapper(torch.nn.Module):
        def __init__(self, m, cast_dtype):
            super().__init__()
            self.m = m  # registered submodule -> .parameters() works
            self._cast_dtype = cast_dtype

        def forward(self, X, y, train_size, cat_mask=None, d=None):
            out = self.m(X.to(self._cast_dtype), y, train_size, cat_mask=cat_mask, d=d)
            return out.float()

        @property
        def max_classes(self):
            return self.m.max_classes

    return _CastWrapper(base_model, dtype)


def _load_tabfm_model(dtype_str: str = "bfloat16"):
    """Load Google's TabFM classification model, worked around the released
    loader's pytorch_model.bin/safetensors mismatch. Cached as a singleton."""
    if dtype_str in _TABFM_MODEL_CACHE:
        return _TABFM_MODEL_CACHE[dtype_str]
    import os
    import torch
    from safetensors import safe_open
    from tabfm.src.pytorch.model import TabFM
    from tabfm.src.pytorch.tabfm_v1_0_0 import ClassificationConfig

    dtype = torch.bfloat16 if dtype_str == "bfloat16" else torch.float32
    model = TabFM(**ClassificationConfig().to_dict()).to(dtype)
    sd = model.state_dict()

    if dtype == torch.bfloat16 and _TABFM_BF16_FILE.exists():
        src = str(_TABFM_BF16_FILE)          # pre-converted 3.3GB bf16 (low-mem)
    else:
        from huggingface_hub import snapshot_download
        src = os.path.join(snapshot_download("google/tabfm-1.0.0-pytorch"),
                           "classification", "model.safetensors")
    with safe_open(src, framework="pt") as f:
        for k in f.keys():
            if k in sd:
                sd[k].copy_(f.get_tensor(k).to(dtype))
    model.eval()
    wrapped = _tabfm_cast_wrapper(model, dtype) if dtype == torch.bfloat16 else model
    _TABFM_MODEL_CACHE[dtype_str] = wrapped
    return wrapped


class TabFMFoundationModel(RiskModel):
    """Google TabFM v1.0.0 zero-shot tabular foundation model (real weights)."""
    name = "drishti-tabfm"
    family = "foundation"

    def __init__(self, n_estimators: int | None = 4, dtype: str = "bfloat16",
                 predict_chunk_size: int = 512):
        from tabfm import TabFMClassifier
        n_estimators = n_estimators or 4
        base = _load_tabfm_model(dtype)
        # n_estimators kept small: each member is a full forward over a 1.64B
        # model; 32 (the library default) is impractical on CPU.
        self._clf = TabFMClassifier(model=base, n_estimators=n_estimators,
                                    batch_size=1, random_state=42)
        # Query chunk size: TabFM forms one sequence of (context + queries) per
        # forward, so unbounded query counts blow up attention (O(n^2)). We cap
        # the queries per forward and concatenate — this is what makes scoring
        # the full offender population tractable.
        self._chunk = max(1, int(predict_chunk_size))

    def fit(self, X, y):
        self._clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
        return self

    def _align(self, p, n: int) -> np.ndarray:
        out = np.zeros((n, N_CLASSES))
        for j, c in enumerate(self._clf.classes_):
            out[:, int(c)] = p[:, j]
        return out

    def predict_proba(self, X) -> np.ndarray:
        import sys
        import time
        X = np.asarray(X, dtype=float)
        n = len(X)
        if n <= self._chunk:
            return self._align(self._clf.predict_proba(X), n)
        n_chunks = (n + self._chunk - 1) // self._chunk
        parts = []
        for ci, i in enumerate(range(0, n, self._chunk), 1):
            t = time.time()
            xb = X[i:i + self._chunk]
            parts.append(self._align(self._clf.predict_proba(xb), len(xb)))
            print(f"[TabFM] query chunk {ci}/{n_chunks} ({len(xb)} rows) "
                  f"{time.time() - t:.0f}s", file=sys.stderr, flush=True)
        return np.vstack(parts)


def _free_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:
        return 0.0


def get_foundation_model(n_estimators: int | None = None) -> RiskModel:
    """Preferred foundation backend, resolved at call time.

    Order: explicit env override (DRISHTI_FOUNDATION_MODEL=tabfm|tabpfn|incontext)
    -> real Google TabFM when importable AND enough free RAM (it is a 6.3GB
    model; default gate 8GB, override via TABFM_MIN_FREE_GB) -> TabPFN v2
    -> in-context stand-in. n_estimators only affects TabFM.
    """
    import os
    def _tabfm():
        return TabFMFoundationModel(n_estimators=n_estimators) if n_estimators \
            else TabFMFoundationModel()

    choice = os.getenv("DRISHTI_FOUNDATION_MODEL", "").strip().lower()
    if choice == "tabfm":
        return _tabfm()
    if choice == "tabpfn":
        return TabPFNFoundationModel()
    if choice == "incontext":
        return InContextFoundationModel()

    min_ram = float(os.getenv("TABFM_MIN_FREE_GB", "8"))
    try:
        import tabfm  # noqa: F401
        if _free_ram_gb() >= min_ram:
            return _tabfm()
    except Exception:
        pass
    try:
        return TabPFNFoundationModel()
    except Exception:
        return InContextFoundationModel()


def get_baseline_model() -> RiskModel:
    return GradientBoostingBaseline()
