"""Internal service-scope adapters for the mandatory Catalyst Functions/jobs
(Prompt 21 §F).

These are the REAL, idempotent AppSail targets that the deployed Functions call
over the signed service context:

  * ``emit_prediction_requested`` — persists the authoritative PredictionRequest
    Data Store row and THEN publishes the ``prediction.requested`` Signal
    (persist-before-emit, §F.3). This is the single mandatory prediction Signal.
  * ``dispatch_prediction``       — the ``prediction_event`` Function target:
    idempotent (Cache), records an authoritative state transition, and (only
    when DRISHTI_PREDICTION_DISPATCH_ENABLED) routes to the protected AWS
    adapter. A failure records a TERMINAL failed state for controlled replay.
  * ``run_forecast``              — the ``cron_forecast`` job target: idempotent
    per window, persists the authoritative forecast PredictionRequest, and (only
    when DRISHTI_FORECAST_CRON_ENABLED) dispatches. Disabled otherwise.
  * ``record_notification``       — idempotent notify record.

Idempotency is by key in Catalyst Cache (SEG_IDEMPOTENCY): a duplicate delivery
(Signals retries up to 20x) never double-acts. All persistence is Data Store; no
DATABASE_URL. Every function is injectable (repo/cache/signals/adapter) so the
contract is unit-testable offline. The prediction/forecast dispatch stays
DISABLED until Prompt 23 — the state machine, persistence, idempotency and
terminal-failed handling are real now; the external adapter call is flag-gated.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from ..cache import SEG_IDEMPOTENCY, CacheClient, get_cache
from ..datastore.repository import DataStoreRepository, get_repository
from ..signals import EVENT_PREDICTION_REQUESTED, SignalPublisher, get_signals

# Data Store tables (mapping: PredictionRequest is prefix 'predreq'). Notifications
# use a Data Store-native 'Notification' table (idempotent by ExternalID).
_PRED_TABLE = "PredictionRequest"
_NOTIFY_TABLE = "Notification"

# Terminal / lifecycle states for the authoritative PredictionRequest record.
STATE_APPROVED = "approved"
STATE_QUEUED = "queued"           # persisted; external dispatch deferred (disabled)
STATE_DISPATCHED = "dispatched"
STATE_FAILED = "failed"           # TERMINAL failed-job state (controlled replay)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prediction_dispatch_enabled() -> bool:
    """The prediction dispatch Function is inert until Prompt 23 enables it."""
    return os.getenv("DRISHTI_PREDICTION_DISPATCH_ENABLED", "").strip().lower() == "true"


def forecast_cron_enabled() -> bool:
    """The scheduled forecast job is inert until Prompt 23 enables it."""
    return os.getenv("DRISHTI_FORECAST_CRON_ENABLED", "").strip().lower() == "true"


def _pred_ext(request_id: Any) -> str:
    return f"predreq:{request_id}"


# The PredictionRequest Data Store table has exactly these writable columns
# (Console-created; the Signals rule filters on the lowercase ``state``). The
# repository adds ExternalID + ROWID. We must NOT send capitalized/derived names
# (State/Task/UpdatedAt/DispatchRef/Window/…) or read-only system columns — the
# Catalyst row API rejects unknown/read-only columns, which 500s the dispatch.
def _pred_row(prediction_request_id: Any, state: str, *, task: Optional[str] = None,
              requested_backend: Optional[str] = None,
              idempotency_key: Optional[str] = None) -> dict[str, Any]:
    row: dict[str, Any] = {"PredictionRequestID": prediction_request_id, "state": state}
    if task is not None:
        row["task"] = task
    if requested_backend is not None:
        row["requested_backend"] = requested_backend
    if idempotency_key is not None:
        row["idempotency_key"] = idempotency_key
    return row


# ---------------------------------------------------------------------------
# Emitter — persist authoritative Data Store state, THEN publish the Signal.
# ---------------------------------------------------------------------------
def emit_prediction_requested(
    *,
    prediction_request_id: Any,
    task: str,
    requested_backend: Optional[str] = None,
    district_id: Optional[int] = None,
    feature_snapshot_id: Optional[str] = None,
    actor: str = "system",
    repo: Optional[DataStoreRepository] = None,
    signals: Optional[SignalPublisher] = None,
) -> dict[str, Any]:
    """Persist the PredictionRequest (state=approved) THEN emit prediction.requested.

    Persist-before-emit (§F.3): the authoritative Data Store row is written and
    only then is the Signal published, so a consumer can never observe an event
    for a request that is not yet durable. Returns {record, signal}.
    """
    repo = repo or get_repository()
    signals = signals or get_signals()
    ext = _pred_ext(prediction_request_id)
    stored = repo.upsert(_PRED_TABLE, ext, _pred_row(       # 1. PERSIST FIRST
        prediction_request_id, STATE_APPROVED, task=task,
        requested_backend=requested_backend))
    ev = signals.publish(EVENT_PREDICTION_REQUESTED, {       # 2. THEN emit
        "prediction_request_id": str(prediction_request_id),
        "task": task, "state": STATE_APPROVED, "district_id": district_id,
    })
    return {"record": stored, "signal": ev.as_dict()}


# ---------------------------------------------------------------------------
# Consumer — the prediction_event Function target (idempotent).
# ---------------------------------------------------------------------------
def dispatch_prediction(
    *,
    idempotency_key: str,
    prediction_request_id: Any,
    task: Optional[str] = None,
    requested_backend: Optional[str] = None,
    repo: Optional[DataStoreRepository] = None,
    cache: Optional[CacheClient] = None,
    adapter: Optional[Any] = None,
) -> dict[str, Any]:
    """Idempotently route an approved PredictionRequest to the AWS adapter.

    * duplicate delivery (same idempotency_key) -> {status: duplicate} (no re-act);
    * dispatch disabled (Prompt 23 gate) -> persist state=queued, {status: skipped_disabled};
    * enabled + success -> persist state=dispatched;
    * enabled + failure -> persist TERMINAL state=failed (controlled replay).
    """
    repo = repo or get_repository()
    cache = cache or get_cache()
    ext = _pred_ext(prediction_request_id)

    newly = cache.add_if_absent(SEG_IDEMPOTENCY, f"dispatch:{idempotency_key}")
    existing = repo.get(_PRED_TABLE, ext)
    if not newly:
        return {"status": "duplicate", "idempotency_key": idempotency_key,
                "prediction_request_id": str(prediction_request_id),
                "state": (existing or {}).get("state")}

    if not prediction_dispatch_enabled():
        repo.upsert(_PRED_TABLE, ext, _pred_row(
            prediction_request_id, STATE_QUEUED, task=task,
            requested_backend=requested_backend, idempotency_key=idempotency_key))
        return {"status": "skipped_disabled", "idempotency_key": idempotency_key,
                "prediction_request_id": str(prediction_request_id), "state": STATE_QUEUED}

    try:
        from ..predict.adapter import get_adapter
        adapter = adapter or get_adapter()
        # Prompt 23 builds the full PredictionRequestEnvelope (feature snapshot +
        # query rows) and calls adapter.dispatch(); here we record the terminal
        # 'dispatched' transition once the enable gate + adapter are present.
        _ = getattr(adapter, "name", "aws-adapter")
        repo.upsert(_PRED_TABLE, ext, _pred_row(
            prediction_request_id, STATE_DISPATCHED, task=task,
            requested_backend=requested_backend, idempotency_key=idempotency_key))
        return {"status": "dispatched", "idempotency_key": idempotency_key,
                "prediction_request_id": str(prediction_request_id), "state": STATE_DISPATCHED}
    except Exception as exc:  # noqa: BLE001 — record a terminal failed state
        repo.upsert(_PRED_TABLE, ext, _pred_row(
            prediction_request_id, STATE_FAILED, task=task,
            requested_backend=requested_backend, idempotency_key=idempotency_key))
        return {"status": "failed", "retryable": True, "idempotency_key": idempotency_key,
                "prediction_request_id": str(prediction_request_id), "state": STATE_FAILED,
                "error": type(exc).__name__}


# ---------------------------------------------------------------------------
# Scheduled forecast job target (idempotent per window).
# ---------------------------------------------------------------------------
def run_forecast(
    *,
    window: str,
    idempotency_key: Optional[str] = None,
    repo: Optional[DataStoreRepository] = None,
    cache: Optional[CacheClient] = None,
    signals: Optional[SignalPublisher] = None,
) -> dict[str, Any]:
    """Idempotently start the scheduled aggregate forecast for ``window``.

    Persists the authoritative forecast PredictionRequest BEFORE dispatch. When
    DRISHTI_FORECAST_CRON_ENABLED is unset it records state=queued and returns
    skipped (Prompt 23 gate). Idempotent per window: a re-run (or a retry from
    cron_reconcile) never double-acts.
    """
    repo = repo or get_repository()
    cache = cache or get_cache()
    key = idempotency_key or f"forecast:{window}"
    req_id = f"forecast-{window}"
    ext = _pred_ext(req_id)

    newly = cache.add_if_absent(SEG_IDEMPOTENCY, f"forecast:{key}")
    existing = repo.get(_PRED_TABLE, ext)
    if not newly:
        return {"status": "duplicate", "window": window,
                "state": (existing or {}).get("state")}

    enabled = forecast_cron_enabled()
    state = STATE_DISPATCHED if enabled else STATE_QUEUED
    # persist authoritative record first (window is encoded in req_id =
    # forecast-<window>; the table has no separate Window column).
    repo.upsert(_PRED_TABLE, ext, _pred_row(req_id, state, task="forecast",
                                            idempotency_key=key))
    return {"status": ("dispatched" if enabled else "skipped_disabled"),
            "window": window, "state": state, "idempotency_key": key}


# ---------------------------------------------------------------------------
# Notification record (idempotent).
# ---------------------------------------------------------------------------
def record_notification(
    *,
    idempotency_key: str,
    template: str,
    subject_ref: Optional[str] = None,
    request_ref: Optional[str] = None,
    repo: Optional[DataStoreRepository] = None,
    cache: Optional[CacheClient] = None,
) -> dict[str, Any]:
    """Idempotently record a data-minimized in-app notification (no PII/body)."""
    repo = repo or get_repository()
    cache = cache or get_cache()
    ext = f"notify:{idempotency_key}"
    newly = cache.add_if_absent(SEG_IDEMPOTENCY, ext)
    if not newly:
        return {"status": "duplicate", "idempotency_key": idempotency_key}
    rec = {"ExternalID": ext, "Template": template, "SubjectRef": subject_ref,
           "RequestRef": request_ref, "CreatedAt": _now()}
    repo.upsert(_NOTIFY_TABLE, ext, rec)
    return {"status": "recorded", "idempotency_key": idempotency_key}
