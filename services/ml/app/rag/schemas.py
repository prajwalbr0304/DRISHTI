"""Typed models for the optional approved-text RAG assistant (Phase 15)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RagStatus(BaseModel):
    enabled: bool
    provider: str                       # quickml | offline | disabled
    knowledge_base_version: str
    approved_sources: int
    retention_days: int
    reason: Optional[str] = None


class RagAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    case_scope_ref_id: Optional[str] = Field(None, description="Selected synthetic demo case context.")
    unit_scope_ref_id: Optional[str] = Field(None, description="Selected synthetic demo unit context.")
    actor: Optional[str] = None


class RagCitation(BaseModel):
    source: str
    version: Optional[str] = None
    title: Optional[str] = None


class RagAnswerOut(BaseModel):
    enabled: bool
    provider: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    refused: bool
    knowledge_base_version: str
    case_scope_ref_id: Optional[str] = None
    unit_scope_ref_id: Optional[str] = None
    latency_ms: Optional[int] = None


class RagEvalItem(BaseModel):
    question: str
    expect_answer: bool
    expect_source: Optional[str] = None
    refused: bool
    citations: list[str] = Field(default_factory=list)
    passed: bool


class RagEvalResult(BaseModel):
    total: int
    passed: int
    failed: int
    accuracy: float
    knowledge_base_version: str
    items: list[RagEvalItem] = Field(default_factory=list)
