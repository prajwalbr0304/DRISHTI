"""Typed request/response models for the FIR/case intake API (Phase 2).

Draft payload fields are Optional so partial autosave works; completeness is
enforced by the /validate + /submit gate, which returns blocking ``errors`` and
non-blocking review ``warnings`` separately (DoD §E). Every write response
returns the affected draft/version/event ids and the current validation state.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Draft payload (wizard steps 1-6). All Optional -> autosave-friendly.
# ---------------------------------------------------------------------------
class SourceInfo(BaseModel):
    source_system_code: Optional[str] = None      # FIR_FORM | CSV_IMPORT | JSON_IMPORT
    source_method: Optional[str] = None            # e.g. walk_in | phone | online | transfer
    external_source_id: Optional[str] = None       # source-system key (dedupe)
    originating_unit_id: Optional[int] = None       # Zero FIR: where it was first registered
    receiving_unit_id: Optional[int] = None         # Zero FIR: jurisdiction unit


class Registration(BaseModel):
    crime_no: Optional[str] = None                 # left blank -> auto (18-digit) on approval
    registration_date: Optional[str] = None        # YYYY-MM-DD
    registration_time: Optional[str] = None         # HH:MM (optional)
    registering_officer_id: Optional[int] = None    # Employee
    station_id: Optional[int] = None                # Unit (police station)
    district_id: Optional[int] = None               # derived from station; overridable
    assigned_io_id: Optional[int] = None            # Employee (IO)
    sensitivity: Optional[str] = None               # demo_normal | restricted
    classification: Optional[str] = None            # free classification label


class IncidentInfo(BaseModel):
    incident_from: Optional[str] = None            # ISO datetime
    incident_to: Optional[str] = None              # ISO datetime
    info_received_at: Optional[str] = None         # ISO datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    landmark: Optional[str] = None
    beat: Optional[str] = None                      # beat / SHO jurisdiction note
    occurrence_description: Optional[str] = None
    # Phase 9: a supervisory override reason lets an out-of-assigned-district
    # incident be submitted (recorded + audited). Empty -> the mismatch blocks
    # submit; the officer should instead reassign the registering district.
    jurisdiction_override_reason: Optional[str] = None


class ActSection(BaseModel):
    act_code: str
    section_code: str


class Classification(BaseModel):
    major_head_id: Optional[int] = None            # CrimeHead
    minor_head_id: Optional[int] = None            # CrimeSubHead
    gravity_id: Optional[int] = None               # GravityOffence
    acts_sections: list[ActSection] = Field(default_factory=list)
    # category-specific fields (last-seen for missing person, inquest for UDR, etc.)
    category_specific: dict[str, Any] = Field(default_factory=dict)


class Narrative(BaseModel):
    brief_facts: Optional[str] = None
    language: Optional[str] = "en"
    source_notes: Optional[str] = None
    reviewer_notes: Optional[str] = None
    restricted: bool = False


class DraftPayload(BaseModel):
    source: SourceInfo = Field(default_factory=SourceInfo)
    registration: Registration = Field(default_factory=Registration)
    incident: IncidentInfo = Field(default_factory=IncidentInfo)
    classification: Classification = Field(default_factory=Classification)
    narrative: Narrative = Field(default_factory=Narrative)


# ---------------------------------------------------------------------------
# Party (draft-scoped, canonicalised on approval)
# ---------------------------------------------------------------------------
class PartyInput(BaseModel):
    role_type: str                                  # complainant|victim|accused|witness|informant|guardian|organisation|unknown
    party_nature: str = "person"                    # person|organisation|unknown
    canonical_person_id: Optional[int] = None       # link an existing canonical person
    canonical_organisation_id: Optional[int] = None
    is_unknown: bool = False
    display_name: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)  # age/gender/alias/contact/address/org fields
    sequence_no: Optional[int] = None


class PartyOut(PartyInput):
    intake_draft_party_id: int


# ---------------------------------------------------------------------------
# Draft create/update
# ---------------------------------------------------------------------------
class CreateDraftRequest(BaseModel):
    case_kind: str = "fir_standard"
    case_category_code: Optional[str] = None        # derived from kind if omitted
    idempotency_key: Optional[str] = None
    created_by_actor: Optional[str] = None
    payload: DraftPayload = Field(default_factory=DraftPayload)
    parties: list[PartyInput] = Field(default_factory=list)


class UpdateDraftRequest(BaseModel):
    case_kind: Optional[str] = None
    case_category_code: Optional[str] = None
    payload: Optional[DraftPayload] = None
    actor: Optional[str] = None
    # optimistic concurrency: reject if the stored revision has moved on.
    expected_revision_no: Optional[int] = None
    autosave: bool = False


# ---------------------------------------------------------------------------
# Validation + duplicate check
# ---------------------------------------------------------------------------
class ValidationIssue(BaseModel):
    field: str
    code: str
    message: str
    severity: str = "error"                         # error (blocking) | warning (review)


class JurisdictionInfo(BaseModel):
    has_point: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    in_state: Optional[bool] = None
    in_assigned_district: Optional[bool] = None
    resolved_district_id: Optional[int] = None
    resolved_district_name: Optional[str] = None
    nearest_unit_id: Optional[int] = None
    nearest_unit_name: Optional[str] = None
    note: Optional[str] = None


class DuplicateCandidate(BaseModel):
    kind: str                                       # case | draft | source
    id: int
    crime_no: Optional[str] = None
    external_ref: Optional[str] = None
    reason: str
    match_score: float = 0.0
    detail: Optional[str] = None


class ValidationResponse(BaseModel):
    ok: bool                                        # no blocking errors
    can_submit: bool                                # ok AND prerequisites present
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    jurisdiction: JurisdictionInfo = Field(default_factory=JurisdictionInfo)
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)
    validated_at: Optional[str] = None


class DuplicateCheckResponse(BaseModel):
    external_source_id: Optional[str] = None
    candidates: list[DuplicateCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Draft read models
# ---------------------------------------------------------------------------
class DraftActivity(BaseModel):
    intake_draft_activity_id: int
    event_type: str
    actor: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class DraftResponse(BaseModel):
    intake_draft_id: int
    draft_key: str
    status: str
    case_kind: str
    case_category_code: str
    source_system_id: Optional[int] = None
    source_record_id: Optional[int] = None
    ingestion_job_id: Optional[int] = None
    case_master_id: Optional[int] = None
    crime_no: Optional[str] = None
    revision_no: int = 0
    created_by_actor: Optional[str] = None
    submitted_by_actor: Optional[str] = None
    reviewed_by_actor: Optional[str] = None
    review_note: Optional[str] = None
    return_reason: Optional[str] = None
    payload: DraftPayload = Field(default_factory=DraftPayload)
    parties: list[PartyOut] = Field(default_factory=list)
    validation: Optional[ValidationResponse] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    submitted_at: Optional[str] = None
    reviewed_at: Optional[str] = None


class DraftListItem(BaseModel):
    intake_draft_id: int
    draft_key: str
    status: str
    case_kind: str
    case_category_code: str
    crime_no: Optional[str] = None
    case_master_id: Optional[int] = None
    party_count: int = 0
    validation_ok: Optional[bool] = None
    created_by_actor: Optional[str] = None
    submitted_by_actor: Optional[str] = None
    reviewed_by_actor: Optional[str] = None
    revision_no: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    submitted_at: Optional[str] = None


class DraftListResponse(BaseModel):
    items: list[DraftListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Submit / review / event
# ---------------------------------------------------------------------------
class SubmitRequest(BaseModel):
    actor: Optional[str] = None


class ReviewRequest(BaseModel):
    actor: Optional[str] = None
    note: Optional[str] = None                      # approval note / return/reject reason


class ApprovalResult(BaseModel):
    draft: DraftResponse
    case_master_id: int
    case_version_id: int
    case_event_id: int
    crime_no: str
    case_party_role_ids: list[int] = Field(default_factory=list)
    canonical_person_ids: list[int] = Field(default_factory=list)


class CaseEventRequest(BaseModel):
    event_type: str
    occurred_at: Optional[str] = None
    actor_role: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CaseEventResponse(BaseModel):
    case_master_id: int
    case_event_id: int
    from_status: Optional[str] = None
    to_status: str
    is_terminal: bool = False
    legacy_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Lookups + workflow metadata
# ---------------------------------------------------------------------------
class OptionItem(BaseModel):
    id: int
    name: Optional[str] = None
    parent_id: Optional[int] = None
    extra: Optional[str] = None


class ActOption(BaseModel):
    act_code: str
    short_name: Optional[str] = None
    description: Optional[str] = None


class SectionOption(BaseModel):
    section_code: str
    act_code: str
    description: Optional[str] = None


class PartyRoleOption(BaseModel):
    value: str
    label: str


class TransitionMeta(BaseModel):
    event_type: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    requires_prior_event: Optional[str] = None
    is_terminal: bool = False
    description: Optional[str] = None


class CaseKindMeta(BaseModel):
    kind: str
    category: str
    label: str
    allow_accused: bool
    allow_arrest: bool
    allow_chargesheet: bool
    allow_court: bool
    initial_event: str
    initial_status: str
    description: str
    allowed_party_roles: list[str]


class StatusMeta(BaseModel):
    code: str
    label: str
    legacy_name: Optional[str] = None


class WorkflowMetaResponse(BaseModel):
    kinds: list[CaseKindMeta]
    statuses: list[StatusMeta]
    party_roles: list[PartyRoleOption]
    transitions_by_category: dict[str, list[TransitionMeta]]
    event_labels: dict[str, str]


class LookupsResponse(BaseModel):
    categories: list[OptionItem]
    gravities: list[OptionItem]
    districts: list[OptionItem]
    units: list[OptionItem]                          # station_id, name, parent_id=district
    crime_heads: list[OptionItem]
    crime_subheads: list[OptionItem]                 # parent_id = crime_head_id
    statuses: list[OptionItem]
    officers: list[OptionItem]                       # Employee (registering officer / IO)
    courts: list[OptionItem]
    acts: list[ActOption]
    sections: list[SectionOption]
    party_roles: list[PartyRoleOption]


class IntakeStatusResponse(BaseModel):
    hackathon_mode: bool
    demo_data_only: bool
    synthetic_db: bool
    writes_localhost_only: bool
    submit_enabled: bool
    submit_disabled_reason: Optional[str] = None
    environment_label: str


# ---------------------------------------------------------------------------
# Scanned-FIR lane (Catalyst Zia OCR -> reviewed prefill)
# ---------------------------------------------------------------------------
class ScanExtractedField(BaseModel):
    """One field OCR proposed, with everything a reviewer needs to judge it."""
    field: str
    value: Any = None
    raw_text: str = ""
    # Derived by the parser, NOT Zia's own score (Zia returns one document-level
    # number only). Surfaced so the UI can rank what needs attention.
    confidence: float = 0.0
    label_matched: str = ""
    requires_review: bool = False
    auto_filled: bool = False
    note: Optional[str] = None


class ScanUnresolvedLookup(BaseModel):
    """A reference value read from the page that the server refused to guess."""
    field: str
    raw_text: str
    lookup: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""


class ScanProposedParty(BaseModel):
    role_type: str
    party_nature: str = "person"
    is_unknown: bool = False
    display_name: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class ScanResponse(BaseModel):
    """Result of one OCR run. Nothing here is committed to a case."""
    scan_key: str
    status: str
    review_state: str
    provider: str
    template_code: Optional[str] = None
    template_matched: bool = False
    matched_label_count: int = 0
    detected_language: Optional[str] = None
    # Zia's document-level confidence (0-1), reported separately from field
    # confidence so the two are never conflated.
    ocr_confidence: Optional[float] = None
    ocr_low_confidence: bool = False
    raw_text: str = ""
    payload: DraftPayload = Field(default_factory=DraftPayload)
    case_kind: str = "fir_standard"
    fields: list[ScanExtractedField] = Field(default_factory=list)
    parties: list[ScanProposedParty] = Field(default_factory=list)
    unresolved: list[ScanUnresolvedLookup] = Field(default_factory=list)
    fields_needing_review: int = 0
    notes: list[str] = Field(default_factory=list)
    # Present once the scan has been applied to a draft.
    draft_key: Optional[str] = None
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    created_at: Optional[str] = None


class ScanApplyRequest(BaseModel):
    """Turn a reviewed scan into a draft.

    ``payload``/``parties``/``case_kind`` are what the officer actually accepted
    after editing the proposal, so the draft records the corrected values while
    ``IntakeScanField`` keeps what OCR originally proposed. Omitting them applies
    the machine proposal unchanged (still subject to the normal review gate).
    """
    payload: Optional[DraftPayload] = None
    parties: Optional[list[PartyInput]] = None
    case_kind: Optional[str] = None
    actor: Optional[str] = None
    idempotency_key: Optional[str] = None
    # Field paths the officer changed, so provenance can distinguish an accepted
    # machine value from a corrected one.
    edited_fields: list[str] = Field(default_factory=list)


class ScanApplyResult(BaseModel):
    scan_key: str
    draft: DraftResponse
    fields_from_scan: int = 0
    fields_edited: int = 0
    fields_needing_review: int = 0


class ScanFieldProvenance(BaseModel):
    field: str
    extracted_text: Optional[str] = None
    proposed_value: Any = None
    accepted_value: Any = None
    confidence: Optional[float] = None
    origin: str = "ocr"
    was_edited: bool = False
    requires_review: bool = False


class ScanProvenanceResponse(BaseModel):
    """Per-field provenance for a prefilled draft — what was machine-read,
    what the officer accepted, and what they corrected."""
    scan_key: str
    draft_key: Optional[str] = None
    template_code: Optional[str] = None
    detected_language: Optional[str] = None
    ocr_confidence: Optional[float] = None
    provider: str = ""
    file_name: Optional[str] = None
    sha256: Optional[str] = None
    evidence_item_id: Optional[int] = None
    fields: list[ScanFieldProvenance] = Field(default_factory=list)


class ScanQueueItem(BaseModel):
    scan_key: str
    status: str
    review_state: str
    detected_language: Optional[str] = None
    ocr_confidence: Optional[float] = None
    template_code: Optional[str] = None
    template_matched: bool = False
    file_name: Optional[str] = None
    size_bytes: Optional[int] = None
    created_by_actor: Optional[str] = None
    created_at: Optional[str] = None
    draft_key: Optional[str] = None
    draft_status: Optional[str] = None
    case_kind: Optional[str] = None
    case_master_id: Optional[int] = None
    field_count: int = 0
    fields_needing_review: int = 0
    fields_edited: int = 0
    unresolved_count: int = 0


class ScanQueueResponse(BaseModel):
    items: list[ScanQueueItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    # True once the queue exists at all, which the admin panel reports honestly.
    extraction_queue_present: bool = True


class ScanTemplateLine(BaseModel):
    index: int
    field: str
    kind: str
    label_en: str
    label_kn: str = ""
    aliases_en: list[str] = Field(default_factory=list)
    multiline: bool = False
    boxed: bool = False
    format_hint: str = ""
    help_en: str = ""
    party_role: Optional[str] = None


class ScanTemplateResponse(BaseModel):
    """The printable form contract, generated from the parser's own field table."""
    template_code: str
    separator: str = ":"
    languages: list[str] = Field(default_factory=list)
    lines: list[ScanTemplateLine] = Field(default_factory=list)
    auto_fill_threshold: float = 0.7
    guidance_en: list[str] = Field(default_factory=list)
    guidance_kn: list[str] = Field(default_factory=list)
    notice_en: str = ""


class ScanCapabilityResponse(BaseModel):
    """Truthful capability so the UI never implies extraction it is not doing."""
    scan_ocr_enabled: bool
    feature_enabled: bool
    provider: str
    manual_entry_always_available: bool = True
    languages: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    max_bytes: int
    max_mb: int
    allowed_extensions: list[str] = Field(default_factory=list)
    low_confidence_threshold: float
    auto_fill_threshold: float
    requires_human_review: bool = True
    creates_case_directly: bool = False
    evidence_extraction_enabled: bool = False
    handwriting_supported: bool = True
    handwriting_caveat: str = ""
    evidence: Optional[str] = None
    platform_limitation: Optional[str] = None


# ---------------------------------------------------------------------------
# Data-quality review queue (read-only over the staging DataQualityIssue table)
# ---------------------------------------------------------------------------
class DataQualityIssueOut(BaseModel):
    data_quality_issue_id: int
    issue_type: str
    severity: str
    status: str
    source_record_id: Optional[int] = None
    ingestion_job_id: Optional[int] = None
    case_master_id: Optional[int] = None
    evidence_item_id: Optional[int] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    resolved_by_actor: Optional[str] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


class DataQualityListResponse(BaseModel):
    items: list[DataQualityIssueOut] = Field(default_factory=list)
    total: int
    by_severity: dict[str, int] = Field(default_factory=dict)
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Canonical case parties (read) — CasePartyRole resolved through canonical identity
# ---------------------------------------------------------------------------
class CasePartyOut(BaseModel):
    case_party_role_id: int
    role_type: str
    is_unknown: bool
    party_label: Optional[str] = None
    sequence_no: Optional[int] = None
    canonical_person_id: Optional[int] = None
    person_ref: Optional[str] = None
    person_label: Optional[str] = None
    canonical_organisation_id: Optional[int] = None
    org_ref: Optional[str] = None
    org_name: Optional[str] = None
    legacy_ref_table: Optional[str] = None
    legacy_ref_id: Optional[int] = None


class CasePartyListResponse(BaseModel):
    case_master_id: int
    count: int
    parties: list[CasePartyOut] = Field(default_factory=list)
