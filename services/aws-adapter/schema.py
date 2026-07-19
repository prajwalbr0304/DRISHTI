"""Minimal routing view + validation for the protected AWS adapter (Part F, item 3).

The adapter is a control-plane ROUTER: it authenticates the request, extracts
just enough to choose the right AWS backend (SageMaker async/real-time, AWS Batch
or Batch Transform), enforces limits, then forwards the *full, unmodified*
envelope to the model backend. It therefore validates the routing-relevant
fields without re-implementing the whole pydantic envelope (that full contract
lives in ``services/gpu-worker/schema.py`` and the AppSail app). Keeping this view
thin avoids a third mirror drifting out of sync — only ``ENVELOPE_VERSION`` and
the enum literals below are shared, and they are carried on the wire.
"""
from __future__ import annotations

from dataclasses import dataclass

from signing import ENVELOPE_VERSION


class EnvelopeError(ValueError):
    """Raised when the request envelope is malformed or over a hard limit."""


# Approved, typed tasks (mirror of ModelTask). Anything else is rejected — there
# is no generic "score everything" task.
_TASKS = frozenset({
    "station_workload_band", "area_incident_forecast_tabfm",
    "timesfm_count_forecast", "stgnn_area_forecast", "near_repeat_intensity",
    "hotspot_clusters", "forecast_fusion",
})
_BACKENDS = frozenset({
    "tabfm", "tabpfn", "incontext", "timesfm", "stgnn", "hawkes", "kde", "baseline",
})
_DISPATCH_MODES = frozenset({
    "sagemaker_async", "sagemaker_realtime", "batch_transform", "aws_batch",
})

# Hard ceilings enforced at the boundary (defence in depth vs the app-side cap).
MAX_QUERY_ROWS = 5000
MAX_ENVELOPE_BYTES = 5_000_000  # 5 MB — feature vectors only, never evidence bytes


@dataclass(frozen=True)
class RoutingView:
    """The routing-relevant projection of a prediction request envelope."""
    request_id: str
    idempotency_key: str
    task: str
    requested_backend: str
    dispatch_mode: str
    timeout_s: int
    n_query_rows: int
    subject_kind: str

    @property
    def is_realtime(self) -> bool:
        return self.dispatch_mode == "sagemaker_realtime"

    @property
    def is_async(self) -> bool:
        return self.dispatch_mode == "sagemaker_async"

    @property
    def is_batch(self) -> bool:
        return self.dispatch_mode in ("aws_batch", "batch_transform")


def parse_and_validate(body: dict, *, raw_len: int) -> RoutingView:
    """Validate the routing fields of an inbound envelope. Fail-closed: any
    unknown task/backend/dispatch mode or an over-limit body is rejected."""
    if raw_len > MAX_ENVELOPE_BYTES:
        raise EnvelopeError(f"envelope {raw_len} bytes exceeds {MAX_ENVELOPE_BYTES}")
    if not isinstance(body, dict):
        raise EnvelopeError("envelope must be a JSON object")

    ver = body.get("envelope_version")
    if ver != ENVELOPE_VERSION:
        raise EnvelopeError(f"unsupported envelope version {ver!r}")

    request_id = str(body.get("request_id") or "").strip()
    idem = str(body.get("idempotency_key") or "").strip()
    if not request_id or not idem:
        raise EnvelopeError("request_id and idempotency_key are required")

    task = str(body.get("task") or "")
    if task not in _TASKS:
        raise EnvelopeError(f"unknown task {task!r}")
    backend = str(body.get("requested_backend") or "")
    if backend not in _BACKENDS:
        raise EnvelopeError(f"unknown requested_backend {backend!r}")
    mode = str(body.get("dispatch_mode") or "sagemaker_async")
    if mode not in _DISPATCH_MODES:
        raise EnvelopeError(f"unknown dispatch_mode {mode!r}")

    rows = body.get("query_rows") or []
    if not isinstance(rows, list):
        raise EnvelopeError("query_rows must be a list")
    if len(rows) > MAX_QUERY_ROWS:
        raise EnvelopeError(f"{len(rows)} query rows exceeds {MAX_QUERY_ROWS}")

    try:
        timeout_s = int(body.get("timeout_s", 900))
    except (TypeError, ValueError):
        raise EnvelopeError("timeout_s must be an integer")
    if not (1 <= timeout_s <= 86_400):
        raise EnvelopeError("timeout_s out of range")

    return RoutingView(
        request_id=request_id, idempotency_key=idem, task=task,
        requested_backend=backend, dispatch_mode=mode, timeout_s=timeout_s,
        n_query_rows=len(rows), subject_kind=str(body.get("subject_kind") or "station"))
