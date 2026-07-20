"""Typed models for the case-scoped investigation assistant (Prompt 20 Part D)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InvestigationItem(BaseModel):
    type: str
    label: str
    detail: str
    source_ids: list[str] = Field(default_factory=list)
    basis: str                       # "evidence" | "hypothesis"
    confidence: Optional[float] = None


class CitableObject(BaseModel):
    ref_table: str
    ref_id: str
    label: str
    kind: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    k: int = Field(5, ge=1, le=20)


class InvestigationAnswer(BaseModel):
    case_id: int
    crime_no: Optional[str] = None
    question: Optional[str] = None
    language: str = "en"
    intent: str
    answer: str
    confidence: float
    facts: list[InvestigationItem] = Field(default_factory=list)
    hypotheses: list[InvestigationItem] = Field(default_factory=list)
    citable_objects: list[CitableObject] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    reasoning_summary: str
    limitations: list[str] = Field(default_factory=list)
    planner_source: str


class SendObject(BaseModel):
    ref_table: str
    ref_id: str
    label: Optional[str] = None
    kind: Optional[str] = None


class SendToBoardRequest(BaseModel):
    board_id: int = Field(..., ge=1)
    objects: list[SendObject] = Field(..., min_length=1)


class SendToBoardResult(BaseModel):
    board_id: int
    created_count: int
    skipped_count: int
    created: list[dict] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)
