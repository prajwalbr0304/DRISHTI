"""FastAPI router for Phase-13 explainability & evidence trails.

  GET /explain/contract              — live AiResult-contract conformance audit
  GET /explain/models                — calibration + inference stats per ModelVersion
  GET /explain/models/{id}           — calibration + drift for one ModelVersion
  GET /explain/{table}/{id}          — evidence chain for a CrimeRiskScore /
                                       CrimePrediction / AISummary / AlertHistory row

Specific routes are declared before the generic /{table}/{id} so they win matching.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..cases import analytics_policy
from . import service
from .schemas import (ContractAuditResponse, ExplainResponse, ModelDetailResponse,
                      ModelsResponse)

router = APIRouter(prefix="/explain", tags=["explain"])

_EXPLAINABLE = ("CrimeRiskScore", "CrimePrediction", "AISummary", "AlertHistory")


@router.get("/contract", response_model=ContractAuditResponse)
def contract():
    return service.contract_audit()


@router.get("/models", response_model=ModelsResponse)
def models():
    return service.model_explainability()


@router.get("/models/{model_version_id}", response_model=ModelDetailResponse)
def model_detail(model_version_id: int):
    resp = service.model_detail(model_version_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"ModelVersion {model_version_id} not found")
    return resp


@router.get("/{table}/{record_id}", response_model=ExplainResponse)
def explain(table: str, record_id: int):
    try:
        resp = service.explain_row(table, record_id)
    except analytics_policy.DerivedArtifactUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if resp is service.UNSUPPORTED:
        raise HTTPException(status_code=400,
                            detail=f"Not explainable: '{table}'. Supported: {', '.join(_EXPLAINABLE)}.")
    if resp is None:
        raise HTTPException(status_code=404, detail=f"{table} {record_id} not found")
    return resp
