"""FastAPI router for Phase-10 governed feature/prediction contracts.

  GET  /governance/features                      — feature-definition catalogue
  GET  /governance/schemas                       — versioned feature schemas
  GET  /governance/models                        — governed ModelVersions
  GET  /governance/snapshots                      — immutable feature snapshots
  POST /governance/snapshots/build                — build one immutable snapshot
  POST /governance/snapshots/invalidate           — mark a subject's snapshots stale
  GET  /governance/predictions                     — prediction request queue
  GET  /governance/predictions/{request_id}        — request + result + reviews
  POST /governance/predictions                     — create a governed request (idempotent)
  POST /governance/predictions/{request_id}/run    — run queued -> completed
  POST /governance/predictions/{request_id}/review — reviewer accept/override/reject
  POST /governance/models/{model_version_id}/rollback
  GET  /governance/labels                          — leakage-safe outcome labels

Reads are open (aggregate governance metadata, no PII). Writes require a
governance role AND the hackathon write guard (localhost + synthetic DB).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..config import get_settings
from ..intake.guards import require_write_allowed
from ..roles import ALL_ROLES, DEFAULT_ROLE
from . import service
from .schemas import (BuildSnapshotRequest, BuildSnapshotResult, CreatePredictionRequest,
                      FeatureDefinitionListResponse, FeatureSchemaListResponse,
                      FeatureSnapshotListResponse, InvalidateSnapshotRequest,
                      InvalidateSnapshotResult, ModelVersionListResponse, OutcomeLabelListResponse,
                      PredictionDetail, PredictionRequestListResponse, ReviewPredictionRequest,
                      RunPredictionRequest)

router = APIRouter(prefix="/governance", tags=["governance"])

# Running the governed feature/prediction pipeline and governing a result
# (review, invalidate a snapshot, roll a model back) — INTERIM: every command role.
GOV_WRITE_ROLES = set(ALL_ROLES)
GOV_REVIEW_ROLES = set(ALL_ROLES)


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


def require_gov_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in GOV_WRITE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot run the governed feature/prediction pipeline.")
    return role


def require_gov_review(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in GOV_REVIEW_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot govern predictions — this is a supervisory action.")
    return role


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (service.NotFound, service.builder.SubjectNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, service.SchemaMismatch):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (service.ProtectedFeatureError, service.SchemaNotApproved)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (service.ModelNotApproved, service.StaleSnapshot, service.InvalidState)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (service.BuilderError, service.GovernanceError)):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Registry reads
# ---------------------------------------------------------------------------
@router.get("/features", response_model=FeatureDefinitionListResponse)
def features():
    return service.list_feature_definitions()


@router.get("/schemas", response_model=FeatureSchemaListResponse)
def schemas():
    return service.list_schemas(include_features=True)


@router.get("/models", response_model=ModelVersionListResponse)
def models(governed_only: bool = Query(True)):
    return service.list_model_versions(governed_only=governed_only)


@router.get("/snapshots", response_model=FeatureSnapshotListResponse)
def snapshots(subject_kind: Optional[str] = Query(None), subject_ref_id: Optional[str] = Query(None),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    return service.list_snapshots(subject_kind, subject_ref_id, page, page_size)


@router.get("/labels", response_model=OutcomeLabelListResponse)
def labels(split: Optional[str] = Query(None), page: int = Query(1, ge=1),
           page_size: int = Query(50, ge=1, le=200)):
    return service.list_labels(split, page, page_size)


@router.get("/predictions", response_model=PredictionRequestListResponse)
def predictions(status: Optional[str] = Query(None), page: int = Query(1, ge=1),
                page_size: int = Query(50, ge=1, le=200)):
    return service.list_requests(status, page, page_size)


@router.get("/predictions/{request_id}", response_model=PredictionDetail)
def prediction_detail(request_id: int):
    detail = service.get_prediction_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"PredictionRequest {request_id} not found.")
    return detail


# ---------------------------------------------------------------------------
# Feature snapshot builder + invalidation (writes)
# ---------------------------------------------------------------------------
@router.post("/snapshots/build", response_model=BuildSnapshotResult)
def build_snapshot(body: BuildSnapshotRequest, request: Request,
                   role: str = Depends(require_gov_write)):
    require_write_allowed(request)
    try:
        return service.build_snapshot(body.feature_schema_version_id, body.subject_kind,
                                      body.subject_ref_id, body.observation_cutoff,
                                      body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)


@router.post("/snapshots/invalidate", response_model=InvalidateSnapshotResult)
def invalidate_snapshot(body: InvalidateSnapshotRequest, request: Request,
                        role: str = Depends(require_gov_review)):
    require_write_allowed(request)
    return service.invalidate_for_subject(body.subject_kind, body.subject_ref_id, body.reason,
                                          body.actor or f"demo.{role}")


# ---------------------------------------------------------------------------
# Prediction workflow (writes)
# ---------------------------------------------------------------------------
@router.post("/predictions", response_model=PredictionDetail)
def create_prediction(body: CreatePredictionRequest, request: Request,
                      role: str = Depends(require_gov_write)):
    require_write_allowed(request)
    try:
        req = service.create_request(body.model_version_id, body.feature_snapshot_id,
                                     body.request_kind, body.idempotency_key,
                                     body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    detail = service.get_prediction_detail(req["prediction_request_id"])
    if detail is None:
        raise HTTPException(status_code=500, detail="request created but not retrievable")
    return detail


@router.post("/predictions/{request_id}/run", response_model=PredictionDetail)
def run_prediction(request_id: int, body: RunPredictionRequest, request: Request,
                   role: str = Depends(require_gov_write)):
    require_write_allowed(request)
    try:
        service.run_request(request_id, body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    return service.get_prediction_detail(request_id)


@router.post("/predictions/{request_id}/review", response_model=PredictionDetail)
def review_prediction(request_id: int, body: ReviewPredictionRequest, request: Request,
                      role: str = Depends(require_gov_review)):
    require_write_allowed(request)
    try:
        service.review_request(request_id, body.decision, body.override_reason,
                               body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    return service.get_prediction_detail(request_id)


@router.post("/models/{model_version_id}/rollback", response_model=ModelVersionListResponse)
def rollback_model(model_version_id: int, request: Request,
                   to_model_version_id: Optional[int] = Query(None),
                   role: str = Depends(require_gov_review)):
    require_write_allowed(request)
    try:
        service.rollback_model(model_version_id, to_model_version_id, f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    return service.list_model_versions(governed_only=True)
