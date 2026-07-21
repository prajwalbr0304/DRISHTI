"""Internal router — signed-context trust-boundary proof (Prompt 14 §8.2).

`/internal/ping` requires a valid signed context (from the gateway or an
event/cron function) and echoes back the verified, server-trusted fields. It is
the smoke-test target that proves: (a) an unsigned/forged request is rejected
401, and (b) a correctly signed request is accepted and its identity is derived
server-side — never from client-supplied headers.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..gateway_context import (GatewayContext, require_gateway_context,
                               require_service_context)
from . import service

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/ping")
@router.post("/ping")
def internal_ping(ctx: GatewayContext = Depends(require_gateway_context)) -> dict:
    """Return the verified context (proves the signed boundary works)."""
    return {
        "ok": True,
        "scope": ctx.scope,
        "role": ctx.role,
        "source": ctx.source,
        "user_id": ctx.user_id,
        "request_id": ctx.request_id,
    }


# --- Mandatory Function / job targets (service-scope only) -----------------
# Every endpoint below requires a valid SERVICE-scope signed context (minted by
# an event/cron Function), never a browser/user context. They are idempotent and
# persist authoritative Data Store state; the external AWS dispatch stays
# disabled until Prompt 23 (DRISHTI_PREDICTION_DISPATCH_ENABLED / _FORECAST_CRON_ENABLED).

class DispatchRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    prediction_request_id: str = Field(..., min_length=1, max_length=100)
    task: Optional[str] = Field(None, max_length=60)
    requested_backend: Optional[str] = Field(None, max_length=60)


class ForecastRunRequest(BaseModel):
    idempotency_key: Optional[str] = Field(None, max_length=200)
    window: str = Field(..., min_length=1, max_length=40)


class NotifyRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    template: str = Field(..., min_length=1, max_length=120)
    subject_ref: Optional[str] = Field(None, max_length=200)
    request_ref: Optional[str] = Field(None, max_length=200)


@router.post("/predictions/dispatch")
def predictions_dispatch(body: DispatchRequest,
                         ctx: GatewayContext = Depends(require_service_context)) -> dict:
    """prediction_event target: idempotently route an approved PredictionRequest."""
    return service.dispatch_prediction(
        idempotency_key=body.idempotency_key,
        prediction_request_id=body.prediction_request_id,
        task=body.task, requested_backend=body.requested_backend)


@router.post("/forecast/run")
def forecast_run(body: ForecastRunRequest,
                 ctx: GatewayContext = Depends(require_service_context)) -> dict:
    """cron_forecast target: idempotently start the scheduled aggregate forecast."""
    return service.run_forecast(window=body.window, idempotency_key=body.idempotency_key)


@router.post("/notify")
def notify(body: NotifyRequest,
           ctx: GatewayContext = Depends(require_service_context)) -> dict:
    """Idempotent data-minimized notification record (notify_dispatch target)."""
    return service.record_notification(
        idempotency_key=body.idempotency_key, template=body.template,
        subject_ref=body.subject_ref, request_ref=body.request_ref)
