"""FastAPI router for read-only Ask-DRISHTI chat history (doc 01 §4.7).

  GET /chat/sessions          — past conversation sessions (History sub-page)
  GET /chat/sessions/{id}     — one session's ordered messages + voice transcripts

Read-only over the seeded ChatSession/ChatMessage/VoiceTranscript rows. The live
conversational NL->SQL engine (composer answers) lands in Phase 2.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from . import service
from .schemas import (AskRequest, AskResponse, CapabilitiesResponse, ChatSessionDetail,
                      ChatSessionsResponse, ExplainRequest, TranslateRequest, TranslateResponse)

router = APIRouter(prefix="/chat", tags=["chat"])

_MAX_Q = 2000


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    """Truthful Ask-DRISHTI capabilities (semantic planner, voice provider,
    languages, visualization kinds, scope flags) so the SPA never over-claims."""
    return service.capabilities()


@router.get("/sessions", response_model=ChatSessionsResponse)
def sessions(limit: int = Query(50, ge=1, le=200)):
    return service.list_sessions(limit)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def session(session_id: int):
    resp = service.get_session(session_id)
    if resp is None:
        raise HTTPException(status_code=404, detail=f"Chat session {session_id} not found")
    return resp


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_role: Optional[str] = Header(default=None)):
    """NL->SQL: a grounded, cited, read-only answer scoped to the caller's role.

    The role comes from the X-Role header and drives server-side scoping — a
    an aggregate-only role's same question returns aggregates. Scoping is NOT in the
    prompt; it's enforced by the guarded executor.
    """
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="A question is required.")
    if len(q) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Question is too long.")
    voice = req.voice.model_dump() if req.voice else None
    return service.ask(x_role, q, language=req.language, session_id=req.session_id, voice=voice)


@router.post("/explain", response_model=AskResponse)
def explain(req: ExplainRequest, x_role: Optional[str] = Header(default=None)):
    """'Explain this' — route a chart/hotspot/alert context into the grounded engine."""
    ctx = (req.context or "").strip()
    if not ctx:
        raise HTTPException(status_code=400, detail="Context is required.")
    if len(ctx) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Context is too long.")
    return service.explain(x_role, ctx, language=req.language, session_id=req.session_id)


@router.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest):
    """Best-effort EN<->KN translation for the bilingual PDF export (Phase 5).
    Returns available=false (no fabricated text) when no language model is set."""
    if len((req.text or "").strip()) > _MAX_Q:
        raise HTTPException(status_code=400, detail="Text is too long.")
    return service.translate(req.text, req.target)
