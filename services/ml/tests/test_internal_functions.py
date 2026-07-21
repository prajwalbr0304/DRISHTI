"""Prompt 21 §F — executable contract tests for the mandatory Function/job
targets (a config file marked active is NOT evidence; these exercise the code).

Covers:
  * persist-before-emit: emit_prediction_requested writes the authoritative
    PredictionRequest Data Store row BEFORE publishing prediction.requested;
  * idempotency: dispatch/forecast/notify never double-act on a duplicate key
    (Signals retries up to 20x);
  * disabled-until-Prompt-23: dispatch/forecast persist state but do not act
    externally unless their enable flag is set;
  * terminal failed state on a dispatch failure (controlled replay);
  * signals suppressed by default (cost-free) unless DRISHTI_SIGNALS_ENABLED;
  * the internal endpoints require a SERVICE-scope signed context (401/403/200).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""
os.environ["ZOHO_APPSAIL_SIGNING_SECRET"] = "test-signing-secret-internal"
# Ensure the dispatch/forecast gates start disabled for the default-path tests.
os.environ.pop("DRISHTI_PREDICTION_DISPATCH_ENABLED", None)
os.environ.pop("DRISHTI_FORECAST_CRON_ENABLED", None)
os.environ.pop("DRISHTI_SIGNALS_ENABLED", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import gateway_context as gc, signals as sig  # noqa: E402
from app.cache import InMemoryCache  # noqa: E402
from app.datastore.repository import InMemoryDataStore  # noqa: E402
from app.internal import service  # noqa: E402
from app.main import app  # noqa: E402

_SECRET = "test-signing-secret-internal"


def test_persist_before_emit_ordering():
    """The Data Store row must exist at the instant the Signal is published."""
    repo = InMemoryDataStore()
    order: list[str] = []

    class _Spy(sig.SignalPublisher):
        def publish(self, event_type, payload):
            # At publish time the authoritative record MUST already be persisted.
            assert repo.get("PredictionRequest", "predreq:PR-1") is not None, \
                "signal published before the Data Store row was persisted"
            order.append("emit")
            return sig.SignalEvent(event_type=event_type, payload=payload, published=True)

    out = service.emit_prediction_requested(
        prediction_request_id="PR-1", task="workload_band", district_id=3,
        repo=repo, signals=_Spy())
    assert out["record"]["State"] == "approved"
    assert out["signal"]["event_type"] == "prediction.requested"
    assert order == ["emit"]


def test_emit_uses_prediction_requested_event_and_is_data_minimized():
    repo = InMemoryDataStore()
    signals = sig.InMemorySignals(enabled=True)
    out = service.emit_prediction_requested(
        prediction_request_id="PR-2", task="forecast", district_id=1,
        repo=repo, signals=signals)
    assert signals.events[-1].event_type == sig.EVENT_PREDICTION_REQUESTED
    # payload carries only ids/type/state/district — never PII/narratives
    assert set(out["signal"]["payload"]) <= {"prediction_request_id", "task",
                                             "state", "district_id"}


def test_signals_suppressed_by_default():
    repo = InMemoryDataStore()
    signals = sig.InMemorySignals()  # honours DRISHTI_SIGNALS_ENABLED (unset -> off)
    out = service.emit_prediction_requested(
        prediction_request_id="PR-3", task="forecast", repo=repo, signals=signals)
    assert out["signal"]["published"] is False  # cost-free by default


def test_dispatch_is_idempotent_and_disabled_by_default():
    repo, cache = InMemoryDataStore(), InMemoryCache()
    first = service.dispatch_prediction(
        idempotency_key="idem-1", prediction_request_id="PR-10", task="workload_band",
        repo=repo, cache=cache)
    assert first["status"] == "skipped_disabled"
    assert first["state"] == "queued"
    # duplicate delivery (Signals retry) must NOT re-act
    second = service.dispatch_prediction(
        idempotency_key="idem-1", prediction_request_id="PR-10", task="workload_band",
        repo=repo, cache=cache)
    assert second["status"] == "duplicate"


def test_dispatch_records_terminal_failed_state(monkeypatch):
    repo, cache = InMemoryDataStore(), InMemoryCache()
    monkeypatch.setenv("DRISHTI_PREDICTION_DISPATCH_ENABLED", "true")

    def _boom():
        raise RuntimeError("adapter down")
    monkeypatch.setattr("app.predict.adapter.get_adapter", _boom)

    out = service.dispatch_prediction(
        idempotency_key="idem-fail", prediction_request_id="PR-11", task="workload_band",
        repo=repo, cache=cache)
    assert out["status"] == "failed"
    assert out["retryable"] is True
    assert repo.get("PredictionRequest", "predreq:PR-11")["State"] == "failed"


def test_forecast_run_idempotent_per_window_and_disabled_by_default():
    repo, cache = InMemoryDataStore(), InMemoryCache()
    first = service.run_forecast(window="2026-07-21", repo=repo, cache=cache)
    assert first["status"] == "skipped_disabled" and first["state"] == "queued"
    dup = service.run_forecast(window="2026-07-21", repo=repo, cache=cache)
    assert dup["status"] == "duplicate"
    # a different window is a distinct authoritative record
    other = service.run_forecast(window="2026-07-22", repo=repo, cache=cache)
    assert other["status"] == "skipped_disabled"


def test_notify_is_idempotent():
    repo, cache = InMemoryDataStore(), InMemoryCache()
    a = service.record_notification(idempotency_key="n-1", template="prediction.result.ready",
                                    repo=repo, cache=cache)
    b = service.record_notification(idempotency_key="n-1", template="prediction.result.ready",
                                    repo=repo, cache=cache)
    assert a["status"] == "recorded"
    assert b["status"] == "duplicate"


# --- endpoint service-scope enforcement ------------------------------------
client = TestClient(app)


def _mint(scope="service", nonce="n", source="cron_forecast"):
    now = gc._now_ms()
    p = {"scope": scope, "aud": gc.DEFAULT_AUDIENCE, "role": "investigator",
         "ts": now, "exp": now + 60_000, "nonce": nonce, "request_id": "r",
         "source": source}
    raw = json.dumps(p).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    s = hmac.new(_SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()
    return {"X-DRISHTI-Context": b64, "X-DRISHTI-Signature": s}


def test_internal_endpoint_requires_signed_context():
    r = client.post("/internal/forecast/run", json={"window": "2026-07-21"})
    assert r.status_code == 401  # no signed context


def test_internal_endpoint_rejects_user_scope():
    hdrs = _mint(scope="gateway", nonce="user-scope-1", source=None)
    r = client.post("/internal/forecast/run", json={"window": "2026-07-21"}, headers=hdrs)
    assert r.status_code == 403  # user context cannot call an internal endpoint


def test_internal_endpoint_accepts_service_scope():
    hdrs = _mint(scope="service", nonce="svc-scope-1")
    r = client.post("/internal/forecast/run", json={"window": "2026-07-30"}, headers=hdrs)
    assert r.status_code == 200
    assert r.json()["window"] == "2026-07-30"
