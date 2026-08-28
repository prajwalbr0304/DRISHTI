"""Typed models for the read-only Ask-DRISHTI chat history endpoints (doc 01 §4.7).

These are PLAIN resources (stored conversations), not model outputs, so they do
NOT wear the AiResult contract — that is reserved for the AI endpoints. Assistant
turns already carry their own confidence / cited records / generated SQL, which
this surfaces verbatim from the DB. The live NL->SQL engine arrives in Phase 2.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts import AiResult


class VoiceInfo(BaseModel):
    """Speech-to-text metadata for a voice query (VoiceTranscript)."""
    transcript_text: Optional[str] = None
    language: Optional[str] = None
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    raw_audio_ref: Optional[str] = None


class ChatMessageOut(BaseModel):
    message_id: int
    sender: str                                  # user | assistant
    content: Optional[str] = None
    language: Optional[str] = None               # en | kn
    generated_sql: Optional[str] = None          # assistant turns (read-only proof)
    cited_record_ids: list[Any] = []             # source case ids backing the answer
    confidence: Optional[float] = None
    model_version: Optional[str] = None          # ModelName@Version
    created_at: Optional[str] = None
    voice: Optional[VoiceInfo] = None


class ChatSessionSummary(BaseModel):
    session_id: int
    title: Optional[str] = None
    role: Optional[str] = None                   # role snapshot at session time
    language: Optional[str] = None
    user_display_name: Optional[str] = None
    created_at: Optional[str] = None
    last_activity: Optional[str] = None
    message_count: int = 0
    user_message_count: int = 0
    assistant_message_count: int = 0
    first_question: Optional[str] = None
    has_voice: bool = False


class ChatSessionsResponse(BaseModel):
    count: int
    sessions: list[ChatSessionSummary]


class ChatSessionDetail(BaseModel):
    session_id: int
    title: Optional[str] = None
    role: Optional[str] = None
    language: Optional[str] = None
    user_display_name: Optional[str] = None
    created_at: Optional[str] = None
    messages: list[ChatMessageOut]


# --- Phase 4: voice metadata for a dictated question ------------------------
class VoiceIn(BaseModel):
    """Reviewed speech-recognition metadata linked to the user turn."""
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    language: Optional[str] = None          # en | kn
    transcript: Optional[str] = None        # defaults to the question text
    is_low_confidence: Optional[bool] = None
    # Required when confidence is missing or below the configured threshold.
    # The server enforces this; the browser gate is only the first UX layer.
    confirmed: bool = False


# --- Phase 2: the live NL->SQL conversational engine ------------------------
class AskRequest(BaseModel):
    question: str
    session_id: Optional[int] = None       # continue a thread (multi-turn memory)
    language: Optional[str] = None          # en | kn (auto-detected if omitted)
    voice: Optional[VoiceIn] = None         # present when the question was spoken


# --- Phase 5: bilingual PDF export helper -----------------------------------
class TranslateRequest(BaseModel):
    text: str
    target: str                             # "en" | "kn"


class TranslateResponse(BaseModel):
    text: str                               # original
    translated: Optional[str] = None        # None when no LLM is configured
    target: str
    available: bool = False                 # whether a real translation was produced


class ExplainRequest(BaseModel):
    """'Explain this' — a chart/hotspot/alert context routed in for a grounded,
    cited narrative (doc 01 §8.9)."""
    context: str                            # the composed natural-language request
    session_id: Optional[int] = None
    language: Optional[str] = None


class AskResponse(BaseModel):
    # An AI output, so it honours the shared contract (ground rule #2 / doc 02 §10).
    result: AiResult
    session_id: int
    reply: str
    language: str
    sql: Optional[str] = None               # the SQL that RAN (proof of grounding)
    cited_record_ids: list[str] = []        # provenance: "Table:id" (evidence trail)
    confidence: float = 0.0
    needs_clarification: bool = False
    blocked: bool = False                   # refused (scope/guard) — no data fabricated
    model_version: Optional[str] = None
    row_count: int = 0
    columns: list[str] = []
    rows_preview: list[list[Any]] = []      # small result preview for the UI table
    # Prompt 19 §B: transparent planner provenance (primary vs labelled fallback).
    planner_source: str = "deterministic-fallback"
    planner_primary: str = "deterministic-fallback"
    planner_degraded: bool = False          # fell back from the primary (outage)
    # Prompt 19 §F: server-validated typed visualization spec (None = text only).
    visualization: Optional[dict] = None


# --- Prompt 19: truthful capability advertisement ---------------------------
class SemanticPlannerInfo(BaseModel):
    primary: str                            # planner used in the live-ready contract
    provider: str                           # configured provider id ("" = none)
    quickml_llm_configured: bool
    fallback: str = "deterministic-fallback"


class ScopeFlags(BaseModel):
    query_voice_enabled: bool               # voice dictation IN scope
    evidence_extraction_enabled: bool       # OCR/extraction OUT of scope (false)


class CapabilitiesResponse(BaseModel):
    """What Ask DRISHTI can actually do — read by the SPA so it never over-claims
    (e.g. it labels the mic 'browser voice', not Zia, when Zia is unavailable)."""
    semantic_planner: SemanticPlannerInfo
    voice: dict                             # app.zia_voice.voice_capability_status()
    languages: list[str]
    visualization_kinds: list[str]
    scope: ScopeFlags
