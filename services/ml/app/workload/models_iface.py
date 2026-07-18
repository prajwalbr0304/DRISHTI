"""Model interface for the aggregate station-workload band task (Phase 13).

Parameterised by the number of ordinal bands (the risk module's interface is
hard-wired to 5 offender classes and is being RETIRED, so workload keeps its own
thin, n-class-configurable backends). All backends expose the identical contract
``fit(X, y) -> predict_proba(X) -> (n_rows, n_bands)`` so the evaluator, the
calibrator and the benchmark treat every candidate the same way:

  * foundation candidates — the real Google TabFM (reusing the cached singleton
    loader from the risk module so the 3.3GB weights load at most once), TabPFN
    v2, and a deterministic in-context distance-weighted stand-in used when the
    heavy weights are unavailable (CPU/RAM-gated). This is the DETERMINISTIC
    FALLBACK the phase requires.
  * baselines — a prior-period rule (next quarter := this quarter's band), a
    majority-class floor, and gradient-boosted trees (XGBoost, else sklearn
    HistGradientBoosting). Every foundation candidate must be measured against
    these.

Aggregate area/period support only — never a person-level model.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager

import numpy as np


@contextmanager
def limit_threads(n: int = 1):
    """Cap native OpenMP/BLAS threads for the enclosed block.

    Some hosts (notably Windows with torch + sklearn + xgboost each bundling
    their own OpenMP runtime) DEADLOCK a gradient-boosting fit because the
    conflicting runtimes contend on thread-pool creation. Capping threads via
    threadpoolctl is the reliable, import-order-independent fix and keeps fits
    deterministic. Degrades to a no-op if threadpoolctl is unavailable."""
    try:
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=n):
            yield
    except Exception:  # noqa: BLE001
        yield


# ---------------------------------------------------------------------------
# Interface + helpers
# ---------------------------------------------------------------------------
class WorkloadModel(ABC):
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
        X = np.asarray(X, dtype=float)
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        return self

    def transform(self, X):
        return (np.asarray(X, dtype=float) - self.mu) / self.sd


def _align(p: np.ndarray, classes, n_bands: int) -> np.ndarray:
    """Map a classifier's own class order onto fixed 0..n_bands-1 columns."""
    out = np.zeros((p.shape[0], n_bands))
    for j, c in enumerate(classes):
        ci = int(c)
        if 0 <= ci < n_bands:
            out[:, ci] = p[:, j]
    s = out.sum(axis=1, keepdims=True)
    s[s == 0] = 1.0
    return out / s


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
class PriorPeriodBaseline(WorkloadModel):
    """Prior-period rule: the next quarter's band equals THIS quarter's workload
    band. Bands the ``wl_recent_case_volume`` feature with the same train
    thresholds used for the label. Transparent, statistical, no training — the
    hard-to-beat reference for a workload series."""
    name = "drishti-workload-prior"
    family = "baseline"

    def __init__(self, thresholds, recent_index: int = 0, n_bands: int = 4,
                 peak: float = 0.8):
        self.thresholds = list(thresholds)
        self.recent_index = int(recent_index)
        self.n_bands = int(n_bands)
        self.peak = float(peak)

    def fit(self, X, y):
        return self

    def predict_proba(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        bands = np.digitize(X[:, self.recent_index], self.thresholds)
        proba = np.full((len(X), self.n_bands), (1.0 - self.peak) / max(self.n_bands - 1, 1))
        for i, b in enumerate(bands):
            b = int(min(max(b, 0), self.n_bands - 1))
            proba[i, :] = (1.0 - self.peak) / max(self.n_bands - 1, 1)
            proba[i, b] = self.peak
        return proba / proba.sum(axis=1, keepdims=True)


class MajorityClassBaseline(WorkloadModel):
    """Trivial floor: always predict the most frequent training band."""
    name = "drishti-workload-majority"
    family = "baseline"

    def __init__(self, n_bands: int = 4):
        self.n_bands = int(n_bands)
        self._major = 0
        self._prior = None

    def fit(self, X, y):
        y = np.asarray(y, dtype=int)
        counts = np.bincount(y, minlength=self.n_bands).astype(float)
        self._major = int(counts.argmax())
        self._prior = counts / counts.sum() if counts.sum() else None
        return self

    def predict_proba(self, X) -> np.ndarray:
        n = len(np.asarray(X))
        row = self._prior if self._prior is not None else \
            np.eye(self.n_bands)[self._major]
        return np.tile(row, (n, 1))


class GradientBoostingBaseline(WorkloadModel):
    """Gradient-boosted-tree baseline. Defaults to sklearn HistGradientBoosting
    (reliable + fast everywhere, no OpenMP-runtime conflicts); XGBoost is opt-in
    via DRISHTI_WORKLOAD_GBM=xgboost. Deterministic (fixed seed)."""
    family = "baseline"

    def __init__(self, n_bands: int = 4):
        self.n_bands = int(n_bands)
        prefer = os.getenv("DRISHTI_WORKLOAD_GBM", "histgbm").strip().lower()
        if prefer == "xgboost":
            try:
                from xgboost import XGBClassifier
                # single-threaded 'hist' tree method: deterministic + avoids the
                # OpenMP thread-contention stalls seen on some Windows hosts.
                self._clf = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                          objective="multi:softprob", num_class=n_bands,
                                          tree_method="hist", n_jobs=1, random_state=42,
                                          verbosity=0)
                self.name = "drishti-workload-xgboost"
                return
            except Exception:  # noqa: BLE001
                pass
        from sklearn.ensemble import HistGradientBoostingClassifier
        self._clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4,
                                                   learning_rate=0.1, random_state=42)
        self.name = "drishti-workload-histgbm"

    def fit(self, X, y):
        with limit_threads(1):
            self._clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X) -> np.ndarray:
        with limit_threads(1):
            p = self._clf.predict_proba(np.asarray(X, dtype=float))
        return _align(p, self._clf.classes_, self.n_bands)


# ---------------------------------------------------------------------------
# Foundation candidates
# ---------------------------------------------------------------------------
class InContextFoundationModel(WorkloadModel):
    """Deterministic zero-shot in-context classifier: distance-weighted voting
    over the labelled context (no training loop). TabFM-family stand-in when the
    real weights are unavailable — deterministic given the same data + seed."""
    name = "drishti-workload-incontext"
    family = "foundation"

    def __init__(self, n_bands: int = 4, k: int = 50, bandwidth: float | None = None):
        self.n_bands = int(n_bands)
        self.k = int(k)
        self.bandwidth = bandwidth

    def fit(self, X, y):
        from sklearn.neighbors import NearestNeighbors
        self.scaler = _Standardizer().fit(X)
        self.Xc = self.scaler.transform(X)
        self.yc = np.asarray(y, dtype=int)
        k = min(self.k, len(self.Xc))
        self.nn = NearestNeighbors(n_neighbors=k).fit(self.Xc)
        d, _ = self.nn.kneighbors(self.Xc[: min(500, len(self.Xc))])
        self._bw = self.bandwidth or max(float(np.median(d[:, 1:])), 1e-3)
        return self

    def predict_proba(self, X) -> np.ndarray:
        Xq = self.scaler.transform(np.asarray(X, dtype=float))
        dist, idx = self.nn.kneighbors(Xq)
        w = np.exp(-(dist ** 2) / (2 * self._bw ** 2)) + 1e-9
        proba = np.zeros((len(Xq), self.n_bands))
        for c in range(self.n_bands):
            proba[:, c] = (w * (self.yc[idx] == c)).sum(axis=1)
        proba /= proba.sum(axis=1, keepdims=True)
        return proba


class TabPFNCandidate(WorkloadModel):
    """Real TabPFN v2 backend (only if importable)."""
    name = "drishti-workload-tabpfn"
    family = "foundation"

    def __init__(self, n_bands: int = 4, device: str = "cpu"):
        from tabpfn import TabPFNClassifier
        self.n_bands = int(n_bands)
        self._clf = TabPFNClassifier(device=device, ignore_pretraining_limits=True,
                                     random_state=42)

    def fit(self, X, y):
        with limit_threads(1):
            self._clf.fit(np.asarray(X), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X) -> np.ndarray:
        with limit_threads(1):
            p = self._clf.predict_proba(np.asarray(X))
        return _align(p, self._clf.classes_, self.n_bands)


class TabFMCandidate(WorkloadModel):
    """Google TabFM v1.0.0 zero-shot tabular foundation model (real weights),
    reusing the cached singleton loader from the risk module so the 3.3GB
    weights are read at most once per process."""
    name = "drishti-tabfm-workload"
    family = "foundation"

    def __init__(self, n_bands: int = 4, n_estimators: int | None = 4,
                 dtype: str = "bfloat16", predict_chunk_size: int = 512):
        from tabfm import TabFMClassifier

        from ..risk.models_iface import _load_tabfm_model
        self.n_bands = int(n_bands)
        base = _load_tabfm_model(dtype)
        self._clf = TabFMClassifier(model=base, n_estimators=n_estimators or 4,
                                    batch_size=1, random_state=42)
        self._chunk = max(1, int(predict_chunk_size))

    def fit(self, X, y):
        with limit_threads(1):
            self._clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
        return self

    def predict_proba(self, X) -> np.ndarray:
        import sys
        import time
        X = np.asarray(X, dtype=float)
        n = len(X)
        with limit_threads(1):
            if n <= self._chunk:
                return _align(self._clf.predict_proba(X), self._clf.classes_, self.n_bands)
            parts = []
            n_chunks = (n + self._chunk - 1) // self._chunk
            for ci, i in enumerate(range(0, n, self._chunk), 1):
                t = time.time()
                xb = X[i:i + self._chunk]
                parts.append(_align(self._clf.predict_proba(xb), self._clf.classes_, self.n_bands))
                print(f"[TabFM-workload] query chunk {ci}/{n_chunks} ({len(xb)} rows) "
                      f"{time.time() - t:.0f}s", file=sys.stderr, flush=True)
            return np.vstack(parts)


# ---------------------------------------------------------------------------
# Resolvers (env override + RAM gate + graceful, deterministic fallback)
# ---------------------------------------------------------------------------
def _free_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:  # noqa: BLE001
        return 0.0


class ModelUnavailable(RuntimeError):
    pass


def make_foundation_model(kind: str, n_bands: int = 4,
                          n_estimators: int | None = None) -> WorkloadModel:
    """Construct a named foundation candidate, raising ModelUnavailable if its
    dependency/weights cannot be loaded (so callers can fall back explicitly)."""
    kind = (kind or "").strip().lower()
    try:
        if kind == "tabfm":
            return TabFMCandidate(n_bands=n_bands, n_estimators=n_estimators)
        if kind == "tabpfn":
            return TabPFNCandidate(n_bands=n_bands)
        if kind == "incontext":
            return InContextFoundationModel(n_bands=n_bands)
    except Exception as e:  # noqa: BLE001
        raise ModelUnavailable(f"foundation model '{kind}' unavailable: {e}") from e
    raise ModelUnavailable(f"unknown foundation model '{kind}'")


def get_foundation_model(n_bands: int = 4, n_estimators: int | None = None) -> WorkloadModel:
    """Preferred foundation backend, resolved at call time. Order: explicit env
    override (DRISHTI_FOUNDATION_MODEL=tabfm|tabpfn|incontext) -> real TabFM when
    importable AND enough free RAM (gate TABFM_MIN_FREE_GB, default 8) -> TabPFN v2
    -> deterministic in-context stand-in. Never raises: always returns a usable,
    deterministic model."""
    choice = os.getenv("DRISHTI_FOUNDATION_MODEL", "").strip().lower()
    if choice in ("tabfm", "tabpfn", "incontext"):
        try:
            return make_foundation_model(choice, n_bands, n_estimators)
        except ModelUnavailable:
            if choice == "incontext":
                raise
            # fall through to the resolution ladder below
    min_ram = float(os.getenv("TABFM_MIN_FREE_GB", "8"))
    try:
        import tabfm  # noqa: F401
        if _free_ram_gb() >= min_ram:
            return TabFMCandidate(n_bands=n_bands, n_estimators=n_estimators)
    except Exception:  # noqa: BLE001
        pass
    try:
        return TabPFNCandidate(n_bands=n_bands)
    except Exception:  # noqa: BLE001
        return InContextFoundationModel(n_bands=n_bands)


def get_baseline_models(thresholds, n_bands: int = 4, recent_index: int = 0) -> dict:
    """The transparent comparators every foundation candidate is measured against."""
    return {
        "prior_period": PriorPeriodBaseline(thresholds, recent_index=recent_index, n_bands=n_bands),
        "majority": MajorityClassBaseline(n_bands=n_bands),
        "gbm": GradientBoostingBaseline(n_bands=n_bands),
    }
