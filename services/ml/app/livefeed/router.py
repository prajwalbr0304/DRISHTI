"""FastAPI router for the Live Command Center committed-FIR flow (Prompt 20 E).

  POST /livefeed/fir-committed  — process a committed-FIR event (idempotent)
  POST /livefeed/project        — read-only WHAT-IF: a committed FIR's aggregate delta
  GET  /livefeed/freshness      — projection freshness + last-success/failure + recent

fir-committed is a supervisory/write action (localhost + synthetic-DB guard);
project + freshness are open aggregate reads. This flow only updates aggregate
projections — it never rescores a person or auto-dispatches staff.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..config import get_settings
from ..intake.guards import require_write_allowed
from . import flow
from .schemas import (FirCommittedRequest, FreshnessResponse, ProcessedFirResponse,
                      ProjectFirRequest)

router = APIRouter(prefix="/livefeed", tags=["live-command-center"])

_COMMIT_ROLES = {"supervisor", "super_admin", "investigator"}


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


def require_commit_role(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in _COMMIT_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot emit committed-FIR events.")
    return role


@router.post("/fir-committed", response_model=ProcessedFirResponse)
def fir_committed(body: FirCommittedRequest, request: Request,
                  role: str = Depends(require_commit_role)):
    require_write_allowed(request)
    # detect idempotent replay (already processed) for the response flag.
    replay = flow._LEDGER.seen(f"case:{body.case_id}") is not None
    rec = flow.on_fir_committed(body.case_id, source_ts=body.source_ts)
    out = rec.__dict__.copy()
    out["idempotent_replay"] = replay
    return out


@router.post("/project")
def project(body: ProjectFirRequest):
    return flow.project_committed_fir(
        district_id=body.district_id, crime_head_id=body.crime_head_id,
        station_id=body.station_id)


@router.get("/freshness", response_model=FreshnessResponse)
def freshness():
    return flow.freshness_state()
