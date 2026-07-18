"""FastAPI router for the aggregate station-workload task (Phase 13).

  GET  /workload/task            — task definition + approved schema + model card
  GET  /workload/models          — registered workload model versions + lifecycle
  GET  /workload/predictions     — governed per-station workload band predictions
  GET  /workload/evaluation      — held-out evaluation (metrics + baselines + calib)
  GET  /workload/benchmarks      — recorded small/medium/full benchmark runs
  POST /workload/run             — persist a governed workload run (writes)
  POST /workload/benchmark       — run + persist a benchmark grid (writes)
  POST /workload/models/{id}/lifecycle — staged/shadow/active/retired (supervisory)

Reads are open (aggregate metadata, no PII). Writes require a role AND the
hackathon write guard (localhost + synthetic DB). Aggregate review-support only —
no page presents a person-level score.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..config import get_settings
from ..intake.guards import require_write_allowed
from . import service
from . import governance_bridge as gb
from .schemas import (WorkloadBenchmarkListResponse, WorkloadEvaluationResponse,
                      WorkloadLifecycleRequest, WorkloadLifecycleResponse,
                      WorkloadModelListResponse, WorkloadPredictionListResponse,
                      WorkloadRunRequest, WorkloadRunResponse, WorkloadTaskResponse)

router = APIRouter(prefix="/workload", tags=["workload"])

WORKLOAD_WRITE_ROLES = {"analyst", "investigator", "supervisor", "super_admin"}
WORKLOAD_ADMIN_ROLES = {"supervisor", "super_admin"}


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "analyst").strip()


def require_workload_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in WORKLOAD_WRITE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot run the workload pipeline.")
    return role


def require_workload_admin(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in WORKLOAD_ADMIN_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot change a model's lifecycle — supervisory action.")
    return role


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, gb.WorkloadSchemaMissing):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, gb.WorkloadGovernanceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
@router.get("/task", response_model=WorkloadTaskResponse)
def task():
    return service.task_definition()


@router.get("/models", response_model=WorkloadModelListResponse)
def models():
    return service.list_models()


@router.get("/predictions", response_model=WorkloadPredictionListResponse)
def predictions(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                include_stale: bool = Query(False)):
    return service.list_predictions(page, page_size, include_stale)


@router.get("/evaluation", response_model=WorkloadEvaluationResponse)
def evaluation(foundation_kind: str = Query("served", description="served|incontext|tabpfn|tabfm|auto"),
               refresh: bool = Query(False)):
    try:
        return service.evaluation_report(foundation_kind=foundation_kind, refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)


@router.get("/benchmarks", response_model=WorkloadBenchmarkListResponse)
def benchmarks():
    return service.list_benchmarks()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
@router.post("/run", response_model=WorkloadRunResponse)
def run(body: WorkloadRunRequest, request: Request, role: str = Depends(require_workload_write)):
    require_write_allowed(request)
    try:
        return service.run_governed(foundation_kind=body.foundation_kind, limit=body.limit,
                                    lifecycle=body.lifecycle, actor=body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)


@router.post("/benchmark", response_model=WorkloadBenchmarkListResponse)
def benchmark(request: Request, include_heavy: bool = Query(False),
              role: str = Depends(require_workload_write)):
    require_write_allowed(request)
    try:
        service.run_benchmark_and_persist(include_heavy=include_heavy, actor=f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    return service.list_benchmarks()


@router.post("/models/{model_version_id}/lifecycle", response_model=WorkloadLifecycleResponse)
def lifecycle(model_version_id: int, body: WorkloadLifecycleRequest, request: Request,
              role: str = Depends(require_workload_admin)):
    require_write_allowed(request)
    try:
        return service.set_model_lifecycle(model_version_id, body.stage, actor=body.actor or f"demo.{role}")
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
