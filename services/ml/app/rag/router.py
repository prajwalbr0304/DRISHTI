"""FastAPI router for the optional approved-text RAG assistant (Phase 15).

The assistant is optional and gracefully disabled by default. Reads (status) are
open to any authenticated demo role with rag_use; asking requires rag_use and the
write guard (an interaction is audited). Evaluation is a governance action
(supervisor + super_admin). It answers only from approved SOP/policy text, cites
sources, refuses when unsupported, and never parses uploaded files (no OCR).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..admin.permissions import has_permission, resolve_role, require_admin_read
from ..intake.guards import require_write_allowed
from . import service
from .schemas import RagAnswerOut, RagAskRequest, RagEvalResult, RagStatus

router = APIRouter(prefix="/rag", tags=["rag"])


def require_rag_use(x_role: Optional[str] = Header(default=None)) -> str:
    role = resolve_role(x_role)
    if not has_permission(role, "rag_use"):
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot use the approved-text assistant.")
    return role


@router.get("/status", response_model=RagStatus)
def status(_role: str = Depends(require_rag_use)):
    return service.status()


@router.post("/ask", response_model=RagAnswerOut)
def ask(body: RagAskRequest, request: Request,
        x_demo_actor: Optional[str] = Header(default=None),
        role: str = Depends(require_rag_use)):
    require_write_allowed(request)
    actor = (body.actor or x_demo_actor or f"demo.{role}").strip()
    return service.ask(role, body.question, case_scope_ref_id=body.case_scope_ref_id,
                       unit_scope_ref_id=body.unit_scope_ref_id, actor=actor)


@router.get("/evaluate", response_model=RagEvalResult)
def evaluate(_role: str = Depends(require_admin_read)):
    return service.evaluate()
