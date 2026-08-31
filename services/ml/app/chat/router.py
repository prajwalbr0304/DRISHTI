"""FastAPI router for owner-scoped Ask DRISHTI conversations."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from ..config import get_settings
from . import service
from .identity import resolve_chat_caller
from .schemas import (AskRequest, AskResponse, CapabilitiesResponse, ChatSessionDetail,
                      ChatSessionsResponse, ExplainRequest, TranslateRequest, TranslateResponse)

router = APIRouter(prefix="/chat", tags=["chat"])

_MAX_Q = 2000


def _caller(request: Request, x_role: Optional[str], x_demo_actor: Optional[str]):
    return resolve_chat_caller(request, x_role=x_role, x_demo_actor=x_demo_actor)


def _not_found(session_id: int) -> HTTPException:
    # Deliberately opaque: foreign and absent session ids are indistinguishable.
    return HTTPException(status_code=404, detail=f"Chat session {session_id} not found")


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    """Truthful planner and voice capabilities for capability-driven UI."""
    return service.capabilities()


@router.get("/sessions", response_model=ChatSessionsResponse)
def sessions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    x_role: Optional[str] = Header(default=None),
    x_demo_actor: Optional[str] = Header(default=None),
):
    caller = _caller(request, x_role, x_demo_actor)
    return service.list_sessions(caller.owner_subject, limit)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def session(
    session_id: int,
    request: Request,
    x_role: Optional[str] = Header(default=None),
    x_demo_actor: Optional[str] = Header(default=None),
):
    caller = _caller(request, x_role, x_demo_actor)
    resp = service.get_session(session_id, caller.owner_subject)
    if resp is None:
        raise _not_found(session_id)
    return resp


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    request: Request,
    x_role: Optional[str] = Header(default=None),
    x_demo_actor: Optional[str] = Header(default=None),
):
    """Run the guarded NL-to-SQL path for the authenticated conversation owner."""
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="A question is required.")
    if len(q) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Question is too long.")

    if req.voice is not None:
        threshold = float(get_settings().voice_low_confidence_threshold)
        confidence = req.voice.confidence
        unscored_opt_in = confidence is None and req.voice.auto_send
        if (confidence is None or confidence < threshold) and not (req.voice.confirmed or unscored_opt_in):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "voice_confirmation_required",
                    "message": "Review and confirm this voice transcript before sending.",
                },
            )

    caller = _caller(request, x_role, x_demo_actor)
    voice = req.voice.model_dump() if req.voice else None
    try:
        return service.ask(
            caller.role,
            q,
            owner_subject=caller.owner_subject,
            language=req.language,
            session_id=req.session_id,
            voice=voice,
        )
    except service.ChatSessionAccessError:
        raise _not_found(req.session_id or 0)


@router.post("/explain", response_model=AskResponse)
def explain(
    req: ExplainRequest,
    request: Request,
    x_role: Optional[str] = Header(default=None),
    x_demo_actor: Optional[str] = Header(default=None),
):
    """Route chart/alert context through the same owner-bound guarded engine."""
    ctx = (req.context or "").strip()
    if not ctx:
        raise HTTPException(status_code=400, detail="Context is required.")
    if len(ctx) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Context is too long.")
    caller = _caller(request, x_role, x_demo_actor)
    try:
        return service.explain(
            caller.role,
            ctx,
            owner_subject=caller.owner_subject,
            language=req.language,
            session_id=req.session_id,
        )
    except service.ChatSessionAccessError:
        raise _not_found(req.session_id or 0)


@router.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    """Best-effort EN/KN translation; never fabricates when unavailable."""
    if len((req.text or "").strip()) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Text is too long.")
    return service.translate(req.text, req.target)
