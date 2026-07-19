"""Catalyst Signals contract — cross-component event routing (Prompt 14 rows 21/22).

Signals publishes application events AFTER the authoritative Data Store write
commits (never before). Phase 15 uses it for:

  * ``report.ready``           — a report snapshot was generated + stored;
  * ``prediction.reviewed``    — a governed prediction result was reviewed;
  * ``notification.created``   — an in-app notification was recorded;
  * ``task.escalated``         — a work task crossed its escalation SLA;
  * ``source.reconcile``       — a source-reconciliation summary changed.

Data minimization is a hard rule: an event payload carries only IDs, types,
versions and short non-sensitive summaries. It NEVER carries evidence content,
full narratives, personal identifiers or secrets — the payload is sanitised with
the same rules the audit trail uses before it is published.

Narrow interface + in-memory fake (tests/local, keeps a published log) +
Catalyst-SDK impl (deployed). Publishing is gated by ``DRISHTI_SIGNALS_ENABLED``
so the demo runs cost-free when it is off. Signals rules live in
`infra/catalyst/jobs/signals-rules.json`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .audit import sanitize_detail

# Canonical Phase-15 event names (also registered in signals-rules.json).
EVENT_REPORT_READY = "report.ready"
EVENT_PREDICTION_REVIEWED = "prediction.reviewed"
EVENT_NOTIFICATION_CREATED = "notification.created"
EVENT_TASK_ESCALATED = "task.escalated"
EVENT_SOURCE_RECONCILE = "source.reconcile"
# Prompt 16 — published AFTER the authoritative Data Store board mutation commits.
# Payload carries only {board_id, board_activity_id, version, kind, target, actor};
# never a full sensitive snapshot. Signals is a backend notification path, NOT a
# browser transport — BoardActivity replay/polling remains the correctness path.
EVENT_BOARD_ACTIVITY = "board.activity"
# Prompt 17 — Emergency Response events, published AFTER the authoritative Data
# Store commit; payloads are data-minimised (ids/type/severity/status only).
EVENT_FEED_STALE = "feed.stale"
EVENT_FORECAST_COMPLETED = "forecast.completed"
EVENT_ALERT_REVIEW_REQUIRED = "alert.review_required"
EVENT_ALLOCATION_APPROVED = "allocation.approved"

_VALID_EVENTS = (
    EVENT_REPORT_READY, EVENT_PREDICTION_REVIEWED, EVENT_NOTIFICATION_CREATED,
    EVENT_TASK_ESCALATED, EVENT_SOURCE_RECONCILE, EVENT_BOARD_ACTIVITY,
    EVENT_FEED_STALE, EVENT_FORECAST_COMPLETED, EVENT_ALERT_REVIEW_REQUIRED,
    EVENT_ALLOCATION_APPROVED,
)


@dataclass(frozen=True)
class SignalEvent:
    event_type: str
    payload: dict[str, Any]
    published: bool
    # In the fake, an incrementing id; in deployment, the SDK signal id if any.
    signal_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {"event_type": self.event_type, "payload": self.payload,
                "published": self.published, "signal_id": self.signal_id}


def _minimize(payload: Optional[dict]) -> dict:
    """Drop sensitive keys, truncate strings, cap size (reuses the audit rules)."""
    return sanitize_detail(payload or {})


class SignalPublisher(ABC):
    @abstractmethod
    def publish(self, event_type: str, payload: dict[str, Any]) -> SignalEvent: ...


class InMemorySignals(SignalPublisher):
    """Deterministic fake that records every published event for assertions.

    Respects the same enabled-gate as the deployed publisher, so a test can prove
    that publishing is suppressed when Signals is disabled.
    """

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.events: list[SignalEvent] = []
        self._enabled = signals_enabled() if enabled is None else enabled
        self._seq = 0

    def publish(self, event_type: str, payload: dict[str, Any]) -> SignalEvent:
        if event_type not in _VALID_EVENTS:
            raise ValueError(f"unknown signal event {event_type!r}; expected {_VALID_EVENTS}")
        minimized = _minimize(payload)
        if not self._enabled:
            ev = SignalEvent(event_type=event_type, payload=minimized, published=False)
            self.events.append(ev)
            return ev
        self._seq += 1
        ev = SignalEvent(event_type=event_type, payload=minimized, published=True,
                         signal_id=f"mem-{self._seq}")
        self.events.append(ev)
        return ev


class CatalystSignals(SignalPublisher):
    """Deployed impl over the Catalyst SDK (custom Signals publisher). Deferred import."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        # Custom application event publisher configured in the Catalyst console.
        self._publisher = os.getenv("DRISHTI_SIGNALS_PUBLISHER", "drishti_app")

    def publish(self, event_type: str, payload: dict[str, Any]) -> SignalEvent:
        if event_type not in _VALID_EVENTS:
            raise ValueError(f"unknown signal event {event_type!r}")
        minimized = _minimize(payload)
        if not signals_enabled():
            return SignalEvent(event_type=event_type, payload=minimized, published=False)
        try:
            signals = self._app.signals() if hasattr(self._app, "signals") else None
            sid = None
            if signals is not None:
                res = signals.publish_event(publisher=self._publisher,
                                            event_type=event_type, data=minimized)
                sid = (res or {}).get("signal_id") if isinstance(res, dict) else None
            return SignalEvent(event_type=event_type, payload=minimized, published=True, signal_id=sid)
        except Exception:  # noqa: BLE001 — a Signal failure must never break the request path
            return SignalEvent(event_type=event_type, payload=minimized, published=False)


def signals_enabled() -> bool:
    """Signals publishing is on only when explicitly enabled (cost-free by default)."""
    return os.getenv("DRISHTI_SIGNALS_ENABLED", "").lower() == "true"


def get_signals() -> SignalPublisher:
    """Factory: Catalyst Signals when enabled+configured, else the in-memory fake."""
    if signals_enabled() and os.getenv("DRISHTI_USE_CATALYST_SIGNALS", "").lower() == "true":
        return CatalystSignals()
    return InMemorySignals()
