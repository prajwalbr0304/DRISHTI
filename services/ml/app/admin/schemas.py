"""Typed request/response models for the Phase-15 admin/governance console."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- status / indicators ----------------------------------------------------
class ComponentFlags(BaseModel):
    signals_enabled: bool
    notify_enabled: bool
    rag_enabled: bool
    use_catalyst_datastore: bool
    use_catalyst_stratus: bool
    use_catalyst_smartbrowz: bool


class AdminStatus(BaseModel):
    hackathon_mode: bool
    demo_data_only: bool
    synthetic_db: bool
    environment_label: str
    rls_disabled: bool
    rls_tables_checked: int
    rls_tables_enabled: int
    database_ok: bool
    components: ComponentFlags
    counts: dict[str, int] = Field(default_factory=dict)


class RlsTable(BaseModel):
    schema_name: str
    table_name: str
    rls_enabled: bool
    rls_forced: bool


class RlsStatus(BaseModel):
    rls_disabled: bool
    tables_checked: int
    tables_enabled: int
    offenders: list[str] = Field(default_factory=list)
    tables: list[RlsTable] = Field(default_factory=list)


class AuthorizationMatrix(BaseModel):
    roles: list[str]
    permissions: list[str]
    matrix: dict[str, dict[str, bool]]
    resolved_role: str


# --- units / stations / source systems --------------------------------------
class UnitOut(BaseModel):
    unit_id: int
    unit_name: str
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    active: bool = True
    case_count: int = 0


class UnitListResponse(BaseModel):
    total: int
    items: list[UnitOut] = Field(default_factory=list)


class SourceSystemOut(BaseModel):
    source_system_id: int
    code: str
    name: str
    kind: str
    is_synthetic: bool = True


class SourceSystemListResponse(BaseModel):
    total: int
    boundaries: dict[str, int] = Field(default_factory=dict)
    items: list[SourceSystemOut] = Field(default_factory=list)


class ReconciliationRow(BaseModel):
    source_system_id: int
    code: str
    name: str
    kind: str
    total_source_records: int = 0
    committed_records: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    pending_records: int = 0
    total_jobs: int = 0
    partial_jobs: int = 0
    failed_jobs: int = 0
    last_received_at: Optional[str] = None


class ReconciliationResponse(BaseModel):
    total: int
    items: list[ReconciliationRow] = Field(default_factory=list)


class RepairRequest(BaseModel):
    ingestion_job_id: Optional[int] = Field(None, description="Requeue a partial/failed job.")
    source_record_ids: list[int] = Field(default_factory=list,
                                         description="Rejected source records to re-stage for review.")
    reason: str = Field("synthetic demo repair", min_length=3)
    actor: Optional[str] = None


class RepairResult(BaseModel):
    ingestion_jobs_requeued: int = 0
    source_records_restaged: int = 0
    quality_issues_reopened: int = 0
    note: str


# --- audit search / export ---------------------------------------------------
class AuditEventOut(BaseModel):
    audit_event_id: int
    occurred_at: Optional[str] = None
    actor: Optional[str] = None
    actor_role: Optional[str] = None
    action: Optional[str] = None
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AuditSearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditEventOut] = Field(default_factory=list)


# --- retention / legal hold --------------------------------------------------
class RetentionPolicyOut(BaseModel):
    retention_policy_id: int
    code: str
    name: str
    applies_to: str
    retention_days: int
    archive_after_days: Optional[int] = None
    expiry_action: str
    description: Optional[str] = None
    is_active: bool = True


class RetentionPolicyUpsert(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2)
    applies_to: str = Field(..., pattern="^(case|evidence|audit|report|prediction|notification)$")
    retention_days: int = Field(..., ge=1, le=36500)
    archive_after_days: Optional[int] = Field(None, ge=1, le=36500)
    # Non-destructive only: no 'delete' option is accepted.
    expiry_action: str = Field("flag_only", pattern="^(flag_only|archive_flag|review_required)$")
    description: Optional[str] = None
    is_active: bool = True
    actor: Optional[str] = None


class LegalHoldOut(BaseModel):
    legal_hold_id: int
    subject_kind: str
    subject_ref_id: str
    reason: str
    status: str
    placed_by_actor: Optional[str] = None
    placed_at: Optional[str] = None
    released_by_actor: Optional[str] = None
    released_at: Optional[str] = None


class LegalHoldCreate(BaseModel):
    subject_kind: str = Field(..., pattern="^(case|evidence)$")
    subject_ref_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=3)
    actor: Optional[str] = None


class RetentionOverview(BaseModel):
    policies: list[RetentionPolicyOut] = Field(default_factory=list)
    legal_holds: list[LegalHoldOut] = Field(default_factory=list)
    evidence_summary: dict[str, int] = Field(default_factory=dict)
    non_destructive: bool = True


# --- model lifecycle / review-due / drift ------------------------------------
class ModelReviewOut(BaseModel):
    model_version_id: int
    model_name: str
    version: str
    approval_status: Optional[str] = None
    environment: Optional[str] = None
    approved_at: Optional[str] = None
    model_review_id: Optional[int] = None
    review_kind: Optional[str] = None
    review_status: Optional[str] = None
    due_at: Optional[str] = None
    drift_signal: dict[str, Any] = Field(default_factory=dict)
    effective_review_state: str


class ModelReviewListResponse(BaseModel):
    total: int
    items: list[ModelReviewOut] = Field(default_factory=list)


class ModelReviewUpsert(BaseModel):
    review_kind: str = Field("independent", pattern="^(independent|drift|quality)$")
    status: str = Field("completed", pattern="^(due|in_progress|completed|overdue|waived)$")
    findings: dict[str, Any] = Field(default_factory=dict)
    drift_signal: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


# --- queues ------------------------------------------------------------------
class QueuesResponse(BaseModel):
    data_quality_open: int
    ingestion_partial_failed: int
    evidence_quarantine: int
    # explicit: no OCR/transcription/semantic-extraction queue exists.
    extraction_queue_present: bool = False
    data_quality_items: list[dict[str, Any]] = Field(default_factory=list)
    quarantine_items: list[dict[str, Any]] = Field(default_factory=list)


# --- usage / budgets / feature flags -----------------------------------------
class FeatureFlagOut(BaseModel):
    key: str
    enabled: bool
    category: str
    description: Optional[str] = None
    runtime_effective: Optional[bool] = None


class UsageResponse(BaseModel):
    plan_baseline: dict[str, Any] = Field(default_factory=dict)
    budget_alerts: list[dict[str, Any]] = Field(default_factory=list)
    feature_flags: list[FeatureFlagOut] = Field(default_factory=list)
    note: str


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    actor: Optional[str] = None


# --- saved filters / report templates ----------------------------------------
class SavedFilterOut(BaseModel):
    saved_filter_id: int
    owner_actor: str
    scope: str
    name: str
    filter_json: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False


class SavedFilterCreate(BaseModel):
    scope: str = Field("dashboard", pattern="^(dashboard|report|cases|map)$")
    name: str = Field(..., min_length=1, max_length=120)
    filter_json: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False
    actor: Optional[str] = None


class ReportTemplateOut(BaseModel):
    report_template_id: int
    code: str
    name: str
    description: Optional[str] = None
    report_kind: str
    scope_kind: str
    allowed_roles: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
