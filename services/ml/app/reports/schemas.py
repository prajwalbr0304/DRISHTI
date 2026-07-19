"""Typed models for Phase-15 report generation.

Reports are generated from STRUCTURED database fields only (no OCR / no parsing
of uploaded files). Every snapshot carries a reproducible source snapshot, a
SHA-256, source/version citations and a prominent synthetic watermark.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    template_code: str = Field(..., min_length=2)
    scope_kind: str = Field("global", pattern="^(case|unit|district|global)$")
    scope_ref_id: Optional[str] = Field(None, description="CaseMasterID / UnitID / DistrictID as text.")
    title: Optional[str] = Field(None, max_length=160)
    filters: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


class ReportCitation(BaseModel):
    source: str
    version: Optional[str] = None
    record_id: Optional[str] = None


class ReportSnapshotOut(BaseModel):
    report_snapshot_id: int
    report_template_id: Optional[int] = None
    template_code: Optional[str] = None
    title: str
    requested_by_actor: Optional[str] = None
    requested_by_role: Optional[str] = None
    scope_kind: str
    scope_ref_id: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_citations: list[dict[str, Any]] = Field(default_factory=list)
    content_hash: str
    watermark: str
    stratus_bucket: Optional[str] = None
    stratus_object_key: Optional[str] = None
    stratus_version_id: Optional[str] = None
    object_sha256: Optional[str] = None
    object_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    render_backend: Optional[str] = None
    status: str = "generated"
    version: int = 1
    expires_at: Optional[str] = None
    created_at: Optional[str] = None


class ReportListItem(BaseModel):
    report_snapshot_id: int
    template_code: Optional[str] = None
    title: str
    scope_kind: str
    scope_ref_id: Optional[str] = None
    requested_by_actor: Optional[str] = None
    content_hash: str
    object_sha256: Optional[str] = None
    render_backend: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class ReportListResponse(BaseModel):
    total: int
    items: list[ReportListItem] = Field(default_factory=list)


class ReportDownload(BaseModel):
    report_snapshot_id: int
    url: str
    expires_in_seconds: int
    object_sha256: Optional[str] = None
    watermark: str


class ReportVerifyResult(BaseModel):
    report_snapshot_id: int
    reproducible: bool
    stored_hash: str
    recomputed_hash: str
