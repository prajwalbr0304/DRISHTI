"""Catalyst Mail + Push contract — non-sensitive synthetic notices (rows 24/25).

Mail and Push deliver ONLY data-minimized synthetic summaries (a short subject +
a short body + a resource pointer). They never carry evidence content, full
narratives, personal identifiers or secrets. The notification service builds the
minimized payload; this module is the delivery boundary.

Narrow interface + in-memory fake (tests/local, records sent messages) +
Catalyst-SDK impl (deployed). Delivery is gated by ``DRISHTI_NOTIFY_ENABLED`` so
the demo runs cost-free (in-app notifications still work) when it is off.
Templates live in `infra/catalyst/functions/notify_dispatch/`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# Hard caps so a mis-built payload can never smuggle a long body through email/push.
_MAX_SUBJECT = 120
_MAX_BODY = 400


@dataclass(frozen=True)
class DeliveryResult:
    channel: str            # email | push
    provider: str           # catalyst_mail | catalyst_push | none
    status: str             # sent | failed | suppressed
    detail: Optional[str] = None

    def as_dict(self) -> dict:
        return {"channel": self.channel, "provider": self.provider,
                "status": self.status, "detail": self.detail}


def _clip(s: Optional[str], n: int) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s[:n]


class MailClient(ABC):
    @abstractmethod
    def send(self, *, to_actor: str, subject: str, summary: str,
             resource: Optional[str] = None) -> DeliveryResult: ...


class PushClient(ABC):
    @abstractmethod
    def send(self, *, to_actor: str, title: str, summary: str,
             resource: Optional[str] = None) -> DeliveryResult: ...


class InMemoryMail(MailClient):
    """Records sent mail (minimized) for tests. Suppressed when notify disabled."""

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.sent: list[dict] = []
        self._enabled = notify_enabled() if enabled is None else enabled

    def send(self, *, to_actor, subject, summary, resource=None):
        msg = {"to_actor": to_actor, "subject": _clip(subject, _MAX_SUBJECT),
               "summary": _clip(summary, _MAX_BODY), "resource": resource}
        if not self._enabled:
            return DeliveryResult("email", "none", "suppressed", "notify disabled")
        self.sent.append(msg)
        return DeliveryResult("email", "catalyst_mail", "sent")


class InMemoryPush(PushClient):
    """Records sent push (minimized) for tests. Suppressed when notify disabled."""

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.sent: list[dict] = []
        self._enabled = notify_enabled() if enabled is None else enabled

    def send(self, *, to_actor, title, summary, resource=None):
        msg = {"to_actor": to_actor, "title": _clip(title, _MAX_SUBJECT),
               "summary": _clip(summary, _MAX_BODY), "resource": resource}
        if not self._enabled:
            return DeliveryResult("push", "none", "suppressed", "notify disabled")
        self.sent.append(msg)
        return DeliveryResult("push", "catalyst_push", "sent")


class CatalystMail(MailClient):
    """Deployed impl over the Catalyst SDK (Mail). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._from = os.getenv("DRISHTI_MAIL_FROM", "")

    def send(self, *, to_actor, subject, summary, resource=None):
        if not notify_enabled():
            return DeliveryResult("email", "none", "suppressed", "notify disabled")
        try:
            mail = self._app.email() if hasattr(self._app, "email") else None
            if mail is None or not self._from:
                return DeliveryResult("email", "none", "failed", "mail not configured")
            mail.send_mail({"from_email": self._from, "to_email": to_actor,
                            "subject": _clip(subject, _MAX_SUBJECT),
                            "content": _clip(summary, _MAX_BODY)})
            return DeliveryResult("email", "catalyst_mail", "sent")
        except Exception:  # noqa: BLE001 — delivery failure must not break the request
            return DeliveryResult("email", "catalyst_mail", "failed")


class CatalystPush(PushClient):
    """Deployed impl over the Catalyst SDK (Push Notifications). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._app_id = os.getenv("DRISHTI_PUSH_APP_ID", "")

    def send(self, *, to_actor, title, summary, resource=None):
        if not notify_enabled() or not self._app_id:
            return DeliveryResult("push", "none", "suppressed", "push not configured")
        try:
            push = self._app.push_notification().mobile(self._app_id)
            push.send_notification({"recipient": to_actor,
                                    "message": _clip(f"{title}: {summary}", _MAX_BODY)})
            return DeliveryResult("push", "catalyst_push", "sent")
        except Exception:  # noqa: BLE001
            return DeliveryResult("push", "catalyst_push", "failed")


def notify_enabled() -> bool:
    """Email/push delivery is on only when explicitly enabled (in-app always works)."""
    return os.getenv("DRISHTI_NOTIFY_ENABLED", "").lower() == "true"


def get_mail() -> MailClient:
    if notify_enabled() and os.getenv("DRISHTI_USE_CATALYST_MAIL", "").lower() == "true":
        return CatalystMail()
    return InMemoryMail()


def get_push() -> PushClient:
    if notify_enabled() and os.getenv("DRISHTI_USE_CATALYST_PUSH", "").lower() == "true":
        return CatalystPush()
    return InMemoryPush()
