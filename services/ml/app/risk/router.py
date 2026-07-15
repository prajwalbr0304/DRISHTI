"""FastAPI router for Phase-9 offender risk scoring."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import service
from .schemas import CalibrationResponse, RiskResponse

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/calibration", response_model=CalibrationResponse)
def calibration():
    """Held-out calibration of the TabFM-family model vs the GBM baseline."""
    return service.calibration()


@router.get("/entity/{entity_id}", response_model=RiskResponse)
def risk_by_entity(entity_id: int, rescore: bool = Query(False, description="re-score on demand")):
    resp = service.rescore_entity(entity_id) if rescore else service.get_by_entity(entity_id)
    if resp is None:
        raise HTTPException(status_code=404,
                            detail=f"No risk score for entity {entity_id} (run the batch job or rescore=true)")
    return resp


@router.get("/{accused_id}", response_model=RiskResponse)
def risk_by_accused(accused_id: int):
    """Offender risk by AccusedMasterID: score + signed factors + provenance."""
    resp = service.get_by_accused(accused_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"No risk score for accused {accused_id}")
    return resp
