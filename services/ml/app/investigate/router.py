"""FastAPI router for the case-scoped investigation assistant (Prompt 20 Part D).

  GET  /investigate/{case_id}/brief         — composed facts + hypotheses + citable objects
  POST /investigate/{case_id}/ask           — bilingual case-scoped question -> cited answer
  POST /investigate/{case_id}/send-to-board — send selected cited objects to a Board

Case access is gated by require_case_read (policymaker denied — aggregate-only).
Send-to-board reuses the Board authorization (policymaker denied) + write guard.
This composes existing governed APIs; it is not a second free-form chatbot.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..board import guards as board_guards
from ..cases.permissions import require_case_read
from . import service
from .schemas import (AskRequest, InvestigationAnswer, SendToBoardRequest,
                      SendToBoardResult)

router = APIRouter(prefix="/investigate", tags=["investigation-assistant"])


@router.get("/{case_id}/brief", response_model=InvestigationAnswer)
def brief(case_id: int, k: int = Query(5, ge=1, le=20),
          _role: str = Depends(require_case_read)):
    try:
        return service.brief(case_id, k=k)
    except service.CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{case_id}/ask", response_model=InvestigationAnswer)
def ask(case_id: int, body: AskRequest, _role: str = Depends(require_case_read)):
    try:
        return service.ask(case_id, body.question, k=body.k)
    except service.CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{case_id}/send-to-board", response_model=SendToBoardResult)
def send_to_board(case_id: int, body: SendToBoardRequest, request: Request,
                  role: str = Depends(board_guards.require_board_role)):
    board_guards.require_board_write_allowed(request)
    actor = board_guards.resolve_actor(request)
    objects = [o.model_dump() for o in body.objects]
    return service.send_to_board(body.board_id, objects, actor=actor, role=role)
