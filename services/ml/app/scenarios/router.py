"""FastAPI router for the synthetic scenario registry (Prompt 20 Part A).

  GET /scenarios              — overview + counts + taxonomy (jurisdiction/family)
  GET /scenarios/search       — search/filter by keyword (EN/KN), scope, family
  GET /scenarios/validate     — deterministic validation gate result
  GET /scenarios/nl-examples  — bilingual NL-query examples
  GET /scenarios/{id}         — one scenario with its typed entity graph

Reads only; every scenario is clearly synthetic descriptor metadata (no PII, no
live collection). Safe as open aggregate reads like the other taxonomy endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from . import service
from .schemas import (NlExamplesResponse, Scenario, ScenariosOverview,
                      ScenarioSearchResponse, ValidationResponse)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=ScenariosOverview)
def overview():
    return service.overview()


@router.get("/search", response_model=ScenarioSearchResponse)
def search(q: Optional[str] = Query(None), scope: Optional[str] = Query(None),
           family: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    return service.search(q, scope, family, limit)


@router.get("/validate", response_model=ValidationResponse)
def validate():
    return service.validate()


@router.get("/nl-examples", response_model=NlExamplesResponse)
def nl_examples():
    return service.nl_examples()


@router.get("/{scenario_id}", response_model=Scenario)
def get_scenario(scenario_id: str):
    scn = service.get(scenario_id)
    if scn is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    return scn
