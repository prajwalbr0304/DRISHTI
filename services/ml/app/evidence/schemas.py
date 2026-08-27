"""Typed request/response models for the digital-evidence API (Phase 5).

Metadata is entered MANUALLY. The system generates only file name, MIME type,
size and SHA-256 (from the uploaded object) — never content-derived fields.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Status + lookups
# ---------------------------------------------------------------------------
class EvidenceStatusResponse(BaseModel):
    hackathon_mode: bool
    demo_data_only: bool
    synthetic_db: bool
    writes_localhost_only: bool
    s3_configured: bool
    upload_enabled: bool
    max_bytes: int
    allowed_extensions: list[str] = Field(default_factory=list)
    allowed_mime_types: list[str] = Field(default_factory=list)
    presign_expiry_seconds: int
    extraction_disabled_note: str
    environment_label: str


class LabelledValue(BaseModel):
    value: str
    label: str


class EvidenceLookupsResponse(BaseModel):
    evidence_types: list[LabelledValue] = Field(default_factory=list)
    categories: list[LabelledValue] = Field(default_factory=list)
    confidentialities: list[LabelledValue] = Field(default_factory=list)
    languages: list[LabelledValue] = Field(default_factory=list)
    link_types: list[LabelledValue] = Field(default_factory=list)
    source_systems: list[LabelledValue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Create / correct metadata
# ---------------------------------------------------------------------------
class EvidenceCreateRequest(BaseModel):
    case_id: Optional[int] = Field(None, ge=1, description="Primary case; also EvidenceCaseLink.")
    canonical_entity_id: Optional[int] = Field(None, ge=1, description="Optional linked entity.")
    evidence_type: str = "document"
    category: Optional[str] = None
    title: str
    description: Optional[str] = None
    source_system_code: Optional[str] = None          # FIR_FORM | CSV_IMPORT | ...
    synthetic_reference: Optional[str] = None          # unmistakably-synthetic ref no
    captured_at: Optional[str] = None                  # ISO datetime (manual)
    received_at: Optional[str] = None
    language: str = "en"
    tags: list[str] = Field(default_factory=list)
    confidentiality: str = "demo_normal"
    uploader_actor: Optional[str] = None               # demo actor (display/audit)
    notes: Optional[str] = None
    external_reference_url: Optional[str] = None        # for external_reference (no file)
    # No file will be attached (external reference / metadata-only) -> item is
    # 'available' immediately instead of waiting for an upload.
    metadata_only: bool = False
    idempotency_key: Optional[str] = None


class EvidenceMetadataUpdate(BaseModel):
    """Metadata correction. All optional; only provided fields change. An
    append-only 'metadata_updated' activity event is always recorded."""
    evidence_type: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    synthetic_reference: Optional[str] = None
    captured_at: Optional[str] = None
    received_at: Optional[str] = None
    language: Optional[str] = None
    tags: Optional[list[str]] = None
    confidentiality: Optional[str] = None
    notes: Optional[str] = None
    change_reason: Optional[str] = None
    actor: Optional[str] = None


# ---------------------------------------------------------------------------
# Upload / complete / download
# ---------------------------------------------------------------------------
class UploadUrlRequest(BaseModel):
    file_name: str
    mime_type: str
    size_bytes: int = Field(..., ge=0)
    # Optional client-declared hash (server re-computes + verifies regardless).
    sha256: Optional[str] = None
    change_reason: Optional[str] = None                # for a replacement version
    actor: Optional[str] = None


class UploadUrlResponse(BaseModel):
    evidence_item_id: int
    version_no: int
    storage_key: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_in: int
    expires_at: str
    max_bytes: int


class CompleteUploadRequest(BaseModel):
    storage_key: str
    file_name: str
    mime_type: str
    size_bytes: int = Field(..., ge=0)
    sha256: Optional[str] = None                        # verified server-side
    version_no: Optional[int] = None
    change_reason: Optional[str] = None
    actor: Optional[str] = None


class DownloadUrlResponse(BaseModel):
    evidence_item_id: int
    evidence_object_id: int
    version_no: int
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    url: str
    expires_in: int
    expires_at: str


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------
class EvidenceObjectOut(BaseModel):
    evidence_object_id: int
    version_no: int
    is_current: bool
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: str
    storage_status: str
    storage_key: Optional[str] = None
    created_at: Optional[str] = None


class EvidenceVersionOut(BaseModel):
    evidence_version_id: int
    version_no: int
    evidence_object_id: Optional[int] = None
    change_reason: Optional[str] = None
    created_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class EvidenceActivityOut(BaseModel):
    evidence_activity_event_id: int
    event_type: str
    actor: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class EvidenceCaseLinkOut(BaseModel):
    evidence_case_link_id: int
    case_master_id: int
    crime_no: Optional[str] = None
    link_type: str
    created_at: Optional[str] = None


class EvidenceEntityLinkOut(BaseModel):
    evidence_entity_link_id: int
    canonical_entity_id: int
    entity_ref: Optional[str] = None
    entity_label: Optional[str] = None
    link_type: str
    review_status: str
    confidence: Optional[float] = None


class EvidenceItemOut(BaseModel):
    evidence_item_id: int
    case_master_id: Optional[int] = None
    crime_no: Optional[str] = None
    source_system_id: Optional[int] = None
    evidence_type: str
    category: Optional[str] = None
    title: str
    description: Optional[str] = None
    synthetic_reference: Optional[str] = None
    language: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    uploader_actor: Optional[str] = None
    confidentiality: str
    state: str
    is_synthetic: bool = True
    is_read_only: bool = False
    manual_metadata: dict[str, Any] = Field(default_factory=dict)
    captured_at: Optional[str] = None
    received_at: Optional[str] = None
    uploaded_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    current_object: Optional[EvidenceObjectOut] = None
    objects: list[EvidenceObjectOut] = Field(default_factory=list)
    versions: list[EvidenceVersionOut] = Field(default_factory=list)
    case_links: list[EvidenceCaseLinkOut] = Field(default_factory=list)
    entity_links: list[EvidenceEntityLinkOut] = Field(default_factory=list)
    activity: list[EvidenceActivityOut] = Field(default_factory=list)
    is_previewable: bool = False


class EvidenceListItem(BaseModel):
    evidence_item_id: int
    case_master_id: Optional[int] = None
    evidence_type: str
    category: Optional[str] = None
    title: str
    synthetic_reference: Optional[str] = None
    source_label: Optional[str] = None
    state: str
    is_synthetic: bool = True
    is_read_only: bool = False
    language: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    version_no: Optional[int] = None
    sha256: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    captured_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class EvidenceListResponse(BaseModel):
    items: list[EvidenceListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    by_state: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Link / archive / reset / migrate
# ---------------------------------------------------------------------------
class LinkRequest(BaseModel):
    case_id: Optional[int] = Field(None, ge=1)
    canonical_entity_id: Optional[int] = Field(None, ge=1)
    link_type: str = "evidence"
    actor: Optional[str] = None


class ArchiveRequest(BaseModel):
    reason: Optional[str] = None
    actor: Optional[str] = None


class CreateResponse(BaseModel):
    item: EvidenceItemOut
    duplicate_warning: Optional[str] = None


class CompleteUploadResponse(BaseModel):
    item: EvidenceItemOut
    evidence_object_id: int
    version_no: int
    sha256: str
    size_bytes: int
    duplicate_warning: Optional[str] = None
    duplicate_of_item_ids: list[int] = Field(default_factory=list)


class ResetRequest(BaseModel):
    case_id: int = Field(..., ge=1)
    confirm: bool = False
    actor: Optional[str] = None


class ResetResponse(BaseModel):
    case_master_id: int
    items_deleted: int
    objects_deleted_in_storage: int
    ok: bool


class MigrateLegacyRequest(BaseModel):
    case_id: Optional[int] = Field(None, ge=1)
    actor: Optional[str] = None


class MigrateLegacyResponse(BaseModel):
    scanned: int
    migrated: int
    skipped_existing: int
    item_ids: list[int] = Field(default_factory=list)
