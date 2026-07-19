"""FastAPI router for the Part G prediction runtime + placement/policy introspection.

  GET  /predict/placement        — ML/RAG placement map + validation summary
  GET  /predict/capability-gaps  — retained-AWS-path capability-gap justifications
  GET  /predict/routing          — introspect the input->model routing decision (G.1)
  GET  /predict/dispatch-policy   — introspect the AWS dispatch-mode decision (G.3)
  GET  /predict/health           — adapter/circuit + placement/policy health
  POST /predict/jobs             — submit a governed prediction job (writes)
  GET  /predict/jobs/{request_id}— collect + validate + persist the result (writes)

Reads are open aggregate metadata (no PII). The job endpoints go through the
``PredictionRuntime`` (routing gate -> Data Store persist -> AWS adapter ->
validate -> Data Store result -> data-minimized notice) and are protected by a
role gate + the hackathon write guard. A single process-cached runtime is used so
the offline fake adapter/Data-Store state is shared across submit + collect.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..intake.guards import require_write_allowed
from . import capability_gaps, enablement, placement
from .adapter import SignedHttpsAdapter
from .dispatch_policy import (DEFERRED_MODES, SINGLE_MECHANISM, DispatchPolicyError,
                             Purpose, multimode_enabled, select_dispatch_mode)
from .envelope import BackendKind, ColumnDef, ModelTask
from .routing import InputEvent, RoutingContext, route
from .runtime import (PredictionJobInput, PredictionRuntime, RuntimeRefused)
from ..stream.router import publish_to_channel
from ..channel import channel_enabled

router = APIRouter(prefix="/predict", tags=["predict"])

PREDICT_WRITE_ROLES = {"analyst", "investigator", "supervisor", "super_admin"}


@lru_cache(maxsize=1)
def _runtime() -> PredictionRuntime:
    """Process-cached runtime (shared fake adapter + Data Store across calls)."""
    return PredictionRuntime()


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "analyst").strip()


def require_predict_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in PREDICT_WRITE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot submit a prediction job.")
    return role


# --- Introspection (open aggregate metadata) --------------------------------
@router.get("/placement")
def get_placement():
    return {"summary": placement.validate_placements(), **placement.emit()}


@router.get("/capability-gaps")
def get_capability_gaps():
    return {"summary": capability_gaps.validate_capability_gaps(), **capability_gaps.emit()}


@router.get("/enablement")
def get_enablement():
    """Which routes/models are ENABLED for the demo vs documented-but-deferred (G.1/G.2)."""
    return enablement.summary()


@router.get("/routing")
def get_routing(
        event: str = Query(..., description="input lifecycle/ingestion event"),
        subject_kind: str = Query("station"),
        has_verified_geography: bool = Query(False),
        has_verified_time: bool = Query(False),
        has_verified_head: bool = Query(False),
        near_repeat_eligible: bool = Query(False),
        metadata_schema_lists_fields: bool = Query(False),
        changed_source_fields: str = Query("", description="comma-separated field names")):
    try:
        ev = InputEvent(event)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown event {event!r}")
    ctx = RoutingContext(
        event=ev, subject_kind=subject_kind,
        has_verified_geography=has_verified_geography,
        has_verified_time=has_verified_time, has_verified_head=has_verified_head,
        near_repeat_eligible=near_repeat_eligible,
        metadata_schema_lists_fields=metadata_schema_lists_fields,
        changed_source_fields=frozenset(
            f.strip() for f in changed_source_fields.split(",") if f.strip()))
    return route(ctx).as_dict()


@router.get("/dispatch-policy")
def get_dispatch_policy(
        task: str = Query(...), backend: str = Query(...),
        purpose: str = Query("offline_forecast"),
        latency_slo_ms: Optional[int] = Query(None, ge=1),
        realtime_benchmarked: bool = Query(False)):
    try:
        decision = select_dispatch_mode(
            task=task, backend=backend, purpose=Purpose(purpose),
            latency_slo_ms=latency_slo_ms, realtime_benchmarked=realtime_benchmarked)
    except (DispatchPolicyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**decision.as_dict(),
            "single_mechanism": SINGLE_MECHANISM.value,
            "deferred_modes": [m.value for m in DEFERRED_MODES],
            "multimode_enabled": multimode_enabled()}


@router.get("/health")
def get_health():
    rt = _runtime()
    adapter = rt._adapter  # introspection only
    en = enablement.summary()
    health = {
        "adapter": type(adapter).__name__,
        "placement_valid": True,
        "channel_enabled": channel_enabled(),
        "enabled_tasks": en["enabled_tasks"],
        "deferred_tasks": en["deferred_tasks"],
    }
    try:
        placement.validate_placements()
    except Exception as exc:  # noqa: BLE001
        health["placement_valid"] = False
        health["placement_error"] = str(exc)
    if isinstance(adapter, SignedHttpsAdapter):
        snap = adapter.circuit.snapshot()
        health["circuit"] = {"state": snap.state.value,
                             "consecutive_failures": snap.consecutive_failures,
                             "cooldown_remaining_s": snap.cooldown_remaining_s}
    return health


# --- Job submit / collect (writes) ------------------------------------------
class ColumnSpec(BaseModel):
    name: str
    dtype: str = "float"
    role: str = "feature"


class PredictJobRequest(BaseModel):
    event: str = Field(..., description="input lifecycle event, e.g. fir_approved")
    task: str
    requested_backend: str
    subject_kind: str = "station"
    subject_ids: list[str] = Field(default_factory=list)
    columns: list[ColumnSpec] = Field(default_factory=list)
    query_rows: list[list[float]] = Field(default_factory=list)
    feature_schema_version: str
    model_version: str
    feature_schema_digest: str = ""
    observation_cutoff: str
    source_version_hash: str
    values: dict = Field(default_factory=dict)
    purpose: str = "offline_forecast"
    context_x: Optional[list[list[float]]] = None
    context_y: Optional[list[int]] = None
    context_s3_uri: Optional[str] = None
    context_version: Optional[str] = None
    context_digest: Optional[str] = None
    model_artifact_digest: Optional[str] = None
    training_dataset_snapshot: Optional[str] = None
    output_schema: dict = Field(default_factory=dict)
    latency_slo_ms: Optional[int] = None
    realtime_benchmarked: bool = False
    timeout_s: int = 900
    # routing-context facts (all must be APPROVED canonical state)
    has_verified_geography: bool = False
    has_verified_time: bool = False
    has_verified_head: bool = False
    near_repeat_eligible: bool = False
    metadata_schema_lists_fields: bool = False
    changed_source_fields: list[str] = Field(default_factory=list)


def _to_job(body: PredictJobRequest) -> PredictionJobInput:
    try:
        ev = InputEvent(body.event)
        task = ModelTask(body.task)
        backend = BackendKind(body.requested_backend)
        purpose = Purpose(body.purpose)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ctx = RoutingContext(
        event=ev, subject_kind=body.subject_kind,
        has_verified_geography=body.has_verified_geography,
        has_verified_time=body.has_verified_time,
        has_verified_head=body.has_verified_head,
        near_repeat_eligible=body.near_repeat_eligible,
        metadata_schema_lists_fields=body.metadata_schema_lists_fields,
        changed_source_fields=frozenset(body.changed_source_fields))
    return PredictionJobInput(
        routing_ctx=ctx, task=task, requested_backend=backend,
        subject_kind=body.subject_kind, subject_ids=body.subject_ids,
        columns=[ColumnDef(name=c.name, dtype=c.dtype, role=c.role) for c in body.columns],
        query_rows=body.query_rows, feature_schema_version=body.feature_schema_version,
        model_version=body.model_version, feature_schema_digest=body.feature_schema_digest,
        observation_cutoff=body.observation_cutoff, source_version_hash=body.source_version_hash,
        values=body.values, purpose=purpose, context_x=body.context_x, context_y=body.context_y,
        context_s3_uri=body.context_s3_uri, context_version=body.context_version,
        context_digest=body.context_digest, model_artifact_digest=body.model_artifact_digest,
        training_dataset_snapshot=body.training_dataset_snapshot, output_schema=body.output_schema,
        latency_slo_ms=body.latency_slo_ms, realtime_benchmarked=body.realtime_benchmarked,
        timeout_s=body.timeout_s)


@router.post("/jobs")
def submit_job(body: PredictJobRequest, request: Request,
               role: str = Depends(require_predict_write)):
    require_write_allowed(request)
    job = _to_job(body)
    try:
        handle = _runtime().submit(job)
    except RuntimeRefused as exc:
        # The routing gate refused (draft / not-routed / missing verified fields).
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:  # envelope shape / dispatch-policy error
        raise HTTPException(status_code=400, detail=str(exc))
    return handle.as_dict()


@router.get("/jobs/{request_id}")
def collect_job(request_id: str,
                prediction_request_external_id: Optional[str] = Query(None),
                board_id: Optional[str] = Query(None),
                user_id: Optional[str] = Query(None),
                role: str = Depends(require_predict_write)):
    try:
        result = _runtime().collect(
            request_id, prediction_request_external_id=prediction_request_external_id)
    except RuntimeRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # If a UI stream is bound, forward the data-minimized notice to the channel.
    if result.persisted and result.notice and board_id and user_id and channel_enabled():
        publish_to_channel(board_id, user_id, result.notice)
    return result.as_dict()
