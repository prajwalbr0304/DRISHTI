"""FastAPI router for the Phase-11 money-trail engine.

Every endpoint is gated by the 'money_trail' permission (read); the mutating
detection job additionally requires WRITE. All endpoints return the AiResult
contract with provenance. Auth context (the caller's role) comes from the X-Role
header for now and is replaced by the authenticated session in Phase 14.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from . import service
from .permissions import require_money_permission, require_money_write
from .schemas import (DetectionResponse, FlaggedFeedResponse, TraceResponse,
                      UnifiedResponse)

router = APIRouter(prefix="/money", tags=["money"],
                   dependencies=[Depends(require_money_permission)])


@router.get("/trace", response_model=TraceResponse)
def trace(account: int = Query(..., ge=1, description="start account id"),
          max_hops: int = Query(4, ge=1, le=6, description="hard-capped at 6")):
    resp = service.trace(account, max_hops=max_hops)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Account {account} not found")
    return resp


@router.get("/unified", response_model=UnifiedResponse)
def unified(entity_id: int | None = Query(None, ge=1),
            account_id: int | None = Query(None, ge=1),
            max_hops: int = Query(2, ge=1, le=4)):
    if (entity_id is None) == (account_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of entity_id or account_id")
    resp = service.unified(entity_id=entity_id, account_id=account_id, max_hops=max_hops)
    if resp is None:
        raise HTTPException(status_code=404, detail="Seed entity/account not found")
    return resp


@router.get("/flagged", response_model=FlaggedFeedResponse)
def flagged(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
            reason: str | None = Query(None, description="structuring|layering|circular")):
    return service.flagged_feed(page=page, page_size=page_size, reason=reason)


@router.post("/detect", response_model=DetectionResponse,
             dependencies=[Depends(require_money_write)])
def detect(structuring_min_count: int = Query(5, ge=2, le=50),
           structuring_window_days: int = Query(14, ge=1, le=90),
           cycle_min_amount: float = Query(10000, ge=0),
           cycle_max_len: int = Query(6, ge=2, le=10)):
    """Run the money-laundering detectors, flag transactions, write alerts."""
    return service.run_detection(
        structuring_min_count=structuring_min_count,
        structuring_window_days=structuring_window_days,
        cycle_min_amount=cycle_min_amount, cycle_max_len=cycle_max_len)
