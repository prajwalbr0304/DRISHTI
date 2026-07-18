"""Typed request/response models for the Phase-8 import + money-alert API.

Content is structured (CSV/JSON) and entered through validated imports. Files are
uploaded as evidence; only committed, provenanced canonical rows affect anything
downstream. Graph/entity links are created as CANDIDATES and must be reviewed.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..contracts import AiResult


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
class TemplateVersionOut(BaseModel):
    import_template_version_id: int
    version: str
    status: str
    target_table: Optional[str] = None
    fields: list[dict[str, Any]] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    dedupe_keys: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class TemplateOut(BaseModel):
    import_template_id: int
    code: str
    name: str
    domain: str
    target_table: str
    description: Optional[str] = None
    versions: list[TemplateVersionOut] = Field(default_factory=list)


class TemplateListResponse(BaseModel):
    count: int
    templates: list[TemplateOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch create / dry-run
# ---------------------------------------------------------------------------
class CreateBatchRequest(BaseModel):
    import_template_version_id: int = Field(..., ge=1)
    content: str = Field(..., description="Raw CSV/JSON file content (structured; no OCR).")
    source_format: str = Field("csv", pattern="^(csv|json)$")
    source_file_name: Optional[str] = None
    source_sha256: Optional[str] = None
    case_master_id: Optional[int] = Field(None, ge=1)
    evidence_item_id: Optional[int] = Field(None, ge=1)
    mapping_override: Optional[dict[str, str]] = None   # {canonical_field: source_column}
    idempotency_key: Optional[str] = None
    created_by_actor: Optional[str] = None


class StagingRowOut(BaseModel):
    import_staging_row_id: Optional[int] = None
    row_number: Optional[int] = None
    status: str
    reject_reason: Optional[str] = None
    mapped: dict[str, Any] = Field(default_factory=dict)
    canonical_target_table: Optional[str] = None
    canonical_target_id: Optional[int] = None


class BatchResponse(BaseModel):
    import_batch_id: int
    ingestion_job_id: Optional[int] = None
    import_template_version_id: int
    template_code: Optional[str] = None
    template_version: Optional[str] = None
    domain: str
    target_table: Optional[str] = None
    case_master_id: Optional[int] = None
    evidence_item_id: Optional[int] = None
    source_file_name: Optional[str] = None
    source_format: str = "csv"
    status: str
    dry_run: bool = True
    totals: dict[str, int] = Field(default_factory=dict)
    error_summary: dict[str, int] = Field(default_factory=dict)
    mapping: dict[str, Any] = Field(default_factory=dict)
    superseded_by_import_batch_id: Optional[int] = None
    created_by_actor: Optional[str] = None
    approved_by_actor: Optional[str] = None
    committed_at: Optional[str] = None
    created_at: Optional[str] = None
    sample_rows: list[StagingRowOut] = Field(default_factory=list)


class BatchListItem(BaseModel):
    import_batch_id: int
    domain: str
    template_code: Optional[str] = None
    status: str
    dry_run: bool = True
    case_master_id: Optional[int] = None
    totals: dict[str, int] = Field(default_factory=dict)
    created_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class BatchListResponse(BaseModel):
    items: list[BatchListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class StagingRowListResponse(BaseModel):
    import_batch_id: int
    total: int
    page: int
    page_size: int
    status_filter: Optional[str] = None
    items: list[StagingRowOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Commit / rollback / supersede
# ---------------------------------------------------------------------------
class CommitRequest(BaseModel):
    actor: Optional[str] = None


class CommitResult(BaseModel):
    import_batch_id: int
    status: str                                # committed|partial
    target_table: Optional[str] = None
    committed: int = 0
    rejected: int = 0
    duplicate: int = 0
    source_records_created: int = 0
    canonical_rows_created: int = 0
    candidate_entity_links: int = 0
    idempotent_replay: bool = False


class RollbackRequest(BaseModel):
    actor: Optional[str] = None
    reason: Optional[str] = None


class RollbackResult(BaseModel):
    import_batch_id: int
    status: str                                # rolled_back
    canonical_rows_deleted: int = 0
    source_records_retracted: int = 0


class SupersedeRequest(BaseModel):
    content: str
    source_format: str = Field("csv", pattern="^(csv|json)$")
    source_file_name: Optional[str] = None
    mapping_override: Optional[dict[str, str]] = None
    actor: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Reviewed entity-link queue
# ---------------------------------------------------------------------------
class EntityLinkItem(BaseModel):
    evidence_entity_link_id: int
    evidence_item_id: Optional[int] = None
    evidence_title: Optional[str] = None
    canonical_entity_id: int
    entity_kind: Optional[str] = None
    entity_label: Optional[str] = None
    entity_ref: Optional[str] = None
    link_type: str
    confidence: Optional[float] = None
    review_status: str
    reviewed_by_actor: Optional[str] = None
    reviewed_at: Optional[str] = None
    source_record_id: Optional[int] = None
    import_batch_id: Optional[int] = None
    case_master_id: Optional[int] = None


class EntityLinkQueueResponse(BaseModel):
    total: int
    page: int
    page_size: int
    review_status: Optional[str] = None
    items: list[EntityLinkItem] = Field(default_factory=list)


class EntityLinkReviewRequest(BaseModel):
    decision: str = Field(..., pattern="^(accept|reject)$")
    actor: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Account / transaction views (financial)
# ---------------------------------------------------------------------------
class AccountOut(BaseModel):
    account_id: int
    account_no: Optional[str] = None
    account_type: Optional[str] = None
    holder_name: Optional[str] = None
    bank: Optional[str] = None
    ifsc: Optional[str] = None
    currency: Optional[str] = None
    is_flagged: bool = False
    owner_canonical_person_id: Optional[int] = None
    owner_review_status: Optional[str] = None
    import_batch_id: Optional[int] = None
    txn_in: Optional[int] = None
    txn_out: Optional[int] = None


class AccountListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AccountOut] = Field(default_factory=list)


class TransactionOut(BaseModel):
    transaction_id: int
    source_account_id: int
    destination_account_id: int
    amount: float
    currency: Optional[str] = None
    txn_timestamp: Optional[str] = None
    channel: Optional[str] = None
    normalized_channel: Optional[str] = None
    is_flagged: bool = False
    flag_reason: Optional[str] = None
    review_status: Optional[str] = None
    evidence_case_id: Optional[int] = None
    import_batch_id: Optional[int] = None
    synthetic_reference: Optional[str] = None


class TransactionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[TransactionOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CDR / device timeline + aggregates
# ---------------------------------------------------------------------------
class CommEventOut(BaseModel):
    communication_event_id: int
    comm_type: str
    occurred_at: Optional[str] = None
    duration_sec: Optional[int] = None
    endpoint_a: Optional[str] = None
    endpoint_b: Optional[str] = None
    review_status: Optional[str] = None
    case_master_id: Optional[int] = None
    import_batch_id: Optional[int] = None


class CdrTimelineResponse(BaseModel):
    scope: str                                 # case|entity
    scope_id: int
    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_day: dict[str, int] = Field(default_factory=dict)
    top_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    events: list[CommEventOut] = Field(default_factory=list)


class DeviceArtifactOut(BaseModel):
    device_artifact_id: int
    artifact_type: str
    synthetic_reference: Optional[str] = None
    import_batch_id: Optional[int] = None


class DeviceOut(BaseModel):
    device_id: int
    device_type: Optional[str] = None
    synthetic_identifier: Optional[str] = None
    label: Optional[str] = None
    case_master_id: Optional[int] = None
    import_batch_id: Optional[int] = None
    artifacts: list[DeviceArtifactOut] = Field(default_factory=list)


class DeviceListResponse(BaseModel):
    scope: str
    scope_id: int
    count: int
    devices: list[DeviceOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Money alerts (rule-based, reason-coded, reviewable)
# ---------------------------------------------------------------------------
class MoneyScanResponse(BaseModel):
    result: AiResult
    transactions_scanned: int
    alerts_written: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_reason_code: dict[str, int] = Field(default_factory=dict)
    model_version_id: int


class MoneyAlertOut(BaseModel):
    money_alert_id: int
    alert_type: str
    reason_code: str
    severity: str
    title: Optional[str] = None
    message: Optional[str] = None
    account_id: Optional[int] = None
    case_master_id: Optional[int] = None
    evidence_item_id: Optional[int] = None
    transaction_ids: list[int] = Field(default_factory=list)
    source_record_ids: list[int] = Field(default_factory=list)
    status: str
    latest_disposition: Optional[str] = None
    created_at: Optional[str] = None


class MoneyAlertListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    by_status: dict[str, int] = Field(default_factory=dict)
    items: list[MoneyAlertOut] = Field(default_factory=list)


class MoneyAlertDispositionRequest(BaseModel):
    disposition: str = Field(..., pattern="^(acknowledge|dismiss|escalate|false_positive|confirm_pattern)$")
    actor: Optional[str] = None
    reason: Optional[str] = None
