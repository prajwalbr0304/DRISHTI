"""AWS dispatch-mode selection policy (Prompt 14 G item 3, scoped by G.3).

**G.3 scoping:** the hackathon keeps exactly ONE AWS GPU execution mechanism —
**SageMaker asynchronous inference** — which scales to zero when idle and can be
torn down after the demo. Supporting multiple SageMaker execution modes
simultaneously (AWS Batch, Batch Transform, a real-time endpoint) is DEFERRED:
the richer selection logic is retained + tested, but it is OFF unless
``DRISHTI_DISPATCH_MULTIMODE_ENABLED=true``.

So by default ``select_dispatch_mode`` always returns ``SAGEMAKER_ASYNC``
(scale-to-zero). The one hard guard that always applies: a GPU-only backend may
never use SageMaker Serverless (Serverless has no GPU) — ``assert_no_serverless_gpu``
fails closed. ``validate_dispatch_policy`` checks both the single-mechanism default
and the (deferred) multi-mode invariants at import/CI time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from .envelope import DispatchMode
from .placement import GPU_BACKENDS


class Purpose(str, Enum):
    """Why a prediction run is happening (kept for the deferred multi-mode logic)."""
    OFFLINE_FORECAST = "offline_forecast"   # scheduled aggregate forecast
    BACKFILL = "backfill"                   # historical re-run
    EVALUATION = "evaluation"               # held-out / backtest evaluation
    NEAR_REAL_TIME = "near_real_time"       # measured seconds/minutes requirement
    REAL_TIME = "real_time"                 # interactive; needs a benchmark first


# Purposes that run offline (used only by the deferred multi-mode path).
_OFFLINE_PURPOSES = frozenset({Purpose.OFFLINE_FORECAST, Purpose.BACKFILL,
                               Purpose.EVALUATION})

# The ONE mechanism the hackathon keeps (G.3).
SINGLE_MECHANISM = DispatchMode.SAGEMAKER_ASYNC
# Modes documented but DEFERRED for the hackathon (only used when multimode is on).
DEFERRED_MODES = (DispatchMode.AWS_BATCH, DispatchMode.BATCH_TRANSFORM,
                  DispatchMode.SAGEMAKER_REALTIME)

# Raw dispatch-mode strings FORBIDDEN for a GPU-only workload (no Serverless GPU).
FORBIDDEN_GPU_MODES = frozenset({"sagemaker_serverless", "serverless"})


class DispatchPolicyError(ValueError):
    """Raised when a dispatch request violates the policy (fail-closed)."""


@dataclass(frozen=True)
class DispatchDecision:
    """The selected mode + why, plus the scale-to-zero + benchmark posture."""
    mode: DispatchMode
    scale_to_zero: bool
    reason: str
    purpose: Purpose
    requires_benchmark: bool = False
    benchmark_satisfied: bool = True

    def as_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "scale_to_zero": self.scale_to_zero,
            "reason": self.reason,
            "purpose": self.purpose.value,
            "requires_benchmark": self.requires_benchmark,
            "benchmark_satisfied": self.benchmark_satisfied,
        }


def multimode_enabled() -> bool:
    """The deferred multi-mode selection is OFF unless explicitly enabled."""
    return os.getenv("DRISHTI_DISPATCH_MULTIMODE_ENABLED", "").strip().lower() == "true"


def assert_no_serverless_gpu(backend: str, requested_mode: str) -> None:
    """Fail-closed guard (ALWAYS on): a GPU-only backend must never use
    SageMaker Serverless (Serverless has no GPU)."""
    if backend in GPU_BACKENDS and (requested_mode or "").lower() in FORBIDDEN_GPU_MODES:
        raise DispatchPolicyError(
            f"SageMaker Serverless has no GPU; backend {backend!r} is GPU-only. "
            "The hackathon uses SageMaker asynchronous inference.")


def select_dispatch_mode(*, task: str, backend: str, purpose: Purpose,
                         latency_slo_ms: int | None = None,
                         realtime_benchmarked: bool = False) -> DispatchDecision:
    """Choose the AWS dispatch mode. Deterministic; no side effects.

    Default (G.3): the single SageMaker async mechanism, regardless of purpose.
    Only when ``DRISHTI_DISPATCH_MULTIMODE_ENABLED=true`` does the richer,
    deferred multi-mode logic run.
    """
    if not isinstance(purpose, Purpose):
        purpose = Purpose(str(purpose))
    if backend in GPU_BACKENDS and latency_slo_ms is not None and latency_slo_ms <= 0:
        raise DispatchPolicyError("latency_slo_ms must be positive when provided")

    if multimode_enabled():
        return _select_multimode(task=task, backend=backend, purpose=purpose,
                                 latency_slo_ms=latency_slo_ms,
                                 realtime_benchmarked=realtime_benchmarked)

    # --- Single mechanism (the hackathon default) ---------------------------
    if purpose is Purpose.REAL_TIME:
        note = (" A real-time endpoint is deferred (needs a latency/traffic benchmark "
                "+ DRISHTI_DISPATCH_MULTIMODE_ENABLED).")
        return DispatchDecision(
            mode=SINGLE_MECHANISM, scale_to_zero=True, purpose=purpose,
            requires_benchmark=True, benchmark_satisfied=False,
            reason="Single SageMaker asynchronous-inference mechanism for the hackathon "
                   "(scales to zero when idle)." + note)
    note = ""
    if purpose in _OFFLINE_PURPOSES:
        note = " (AWS Batch / Batch Transform are deferred for the hackathon)."
    return DispatchDecision(
        mode=SINGLE_MECHANISM, scale_to_zero=True, purpose=purpose,
        reason="Single SageMaker asynchronous-inference mechanism for the hackathon "
               "(scales to zero when idle)." + note)


def _select_multimode(*, task: str, backend: str, purpose: Purpose,
                      latency_slo_ms: int | None = None,
                      realtime_benchmarked: bool = False) -> DispatchDecision:
    """DEFERRED richer selection (only when multimode is explicitly enabled):
    AWS Batch for offline; async for measured NRT; real-time only after a
    benchmark."""
    if purpose in _OFFLINE_PURPOSES:
        return DispatchDecision(
            mode=DispatchMode.AWS_BATCH, scale_to_zero=True, purpose=purpose,
            reason=f"{purpose.value}: AWS Batch (GPU/CPU), scale compute to zero when idle.")
    if purpose is Purpose.NEAR_REAL_TIME:
        return DispatchDecision(
            mode=DispatchMode.SAGEMAKER_ASYNC, scale_to_zero=True, purpose=purpose,
            reason="Measured near-real-time requirement -> SageMaker asynchronous inference.")
    if purpose is Purpose.REAL_TIME:
        if not realtime_benchmarked:
            return DispatchDecision(
                mode=DispatchMode.SAGEMAKER_ASYNC, scale_to_zero=True, purpose=purpose,
                requires_benchmark=True, benchmark_satisfied=False,
                reason="Real-time requested but no benchmark on record -> SageMaker async.")
        return DispatchDecision(
            mode=DispatchMode.SAGEMAKER_REALTIME, scale_to_zero=False, purpose=purpose,
            requires_benchmark=True, benchmark_satisfied=True,
            reason="Benchmarked latency/traffic SLO -> SageMaker real-time endpoint.")
    raise DispatchPolicyError(f"unhandled purpose {purpose!r}")


def validate_dispatch_policy() -> dict:
    """Assert both the single-mechanism default (G.3) and the deferred multi-mode
    invariants. Raises ``DispatchPolicyError`` on any violation; returns a summary."""
    gpu, cpu = "tabfm", "baseline"

    # Single mechanism (default): EVERY purpose -> SageMaker async, scale-to-zero.
    for purpose in Purpose:
        d = select_dispatch_mode(task="station_workload_band", backend=gpu, purpose=purpose)
        if d.mode is not SINGLE_MECHANISM or not d.scale_to_zero:
            raise DispatchPolicyError(
                f"single-mode {purpose}: expected {SINGLE_MECHANISM.value} + scale-to-zero")

    # GPU-only backend + serverless -> rejected (this guard is always on).
    rejected = False
    try:
        assert_no_serverless_gpu(gpu, "sagemaker_serverless")
    except DispatchPolicyError:
        rejected = True
    if not rejected:
        raise DispatchPolicyError("GPU + serverless must be rejected")
    assert_no_serverless_gpu(cpu, "sagemaker_serverless")  # cpu is not GPU-only

    # Deferred multi-mode logic (verified directly, not env-dependent).
    for purpose in _OFFLINE_PURPOSES:
        d = _select_multimode(task="t", backend=gpu, purpose=purpose)
        if d.mode is not DispatchMode.AWS_BATCH or not d.scale_to_zero:
            raise DispatchPolicyError(f"multimode {purpose}: expected AWS_BATCH + scale-to-zero")
    if _select_multimode(task="t", backend=cpu, purpose=Purpose.NEAR_REAL_TIME).mode \
            is not DispatchMode.SAGEMAKER_ASYNC:
        raise DispatchPolicyError("multimode NRT: expected SageMaker async")
    d = _select_multimode(task="t", backend=gpu, purpose=Purpose.REAL_TIME, realtime_benchmarked=False)
    if d.mode is DispatchMode.SAGEMAKER_REALTIME or d.benchmark_satisfied:
        raise DispatchPolicyError("multimode real-time w/o benchmark must not be real-time")
    if _select_multimode(task="t", backend=gpu, purpose=Purpose.REAL_TIME,
                         realtime_benchmarked=True).mode is not DispatchMode.SAGEMAKER_REALTIME:
        raise DispatchPolicyError("multimode benchmarked real-time must be a real-time endpoint")

    return {
        "single_mechanism": SINGLE_MECHANISM.value,
        "deferred_modes": [m.value for m in DEFERRED_MODES],
        "multimode_enabled": multimode_enabled(),
        "gpu_serverless_forbidden": sorted(FORBIDDEN_GPU_MODES),
        "real_time_requires_benchmark": True,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(validate_dispatch_policy(), indent=2))
