"""Typed request/response models for the casework API (Phase 7).

All content is entered manually. Restricted statements/lab results are redacted
for roles without sensitive access. Uploaded files are linked by id only.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class LabelledValue(BaseModel):
    value: str
    label: str


class OptionItem(BaseModel):
    id: int
    name: Optional[str] = None


class CaseworkLookups(BaseModel):
    statement_types: list[LabelledValue] = Field(default_factory=list)
    property_item_types: list[LabelledValue] = Field(default_factory=list)
    property_statuses: list[LabelledValue] = Field(default_factory=list)
    court_event_types: list[LabelledValue] = Field(default_factory=list)
    bail_statuses: list[LabelledValue] = Field(default_factory=list)
    disposition_types: list[LabelledValue] = Field(default_factory=list)
    lab_test_types: list[LabelledValue] = Field(default_factory=list)
    lab_statuses: list[LabelledValue] = Field(default_factory=list)
    access_classifications: list[LabelledValue] = Field(default_factory=list)
    courts: list[OptionItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------
class StatementCreate(BaseModel):
    statement_type: str = "witness"                 # witness|complainant|accused|expert
    canonical_person_id: Optional[int] = Field(None, ge=1)
    case_party_role_id: Optional[int] = Field(None, ge=1)
    recorded_by_actor: Optional[str] = None
    recorded_at: Optional[str] = None               # ISO datetime (manual)
    place: Optional[str] = None
    language: str = "en"
    access_classification: str = "demo_normal"       # demo_normal|restricted
    evidence_item_id: Optional[int] = Field(None, ge=1)  # linked document/audio ref
    statement_text: str
    actor: Optional[str] = None


class StatementCorrection(BaseModel):
    statement_text: Optional[str] = None
    correction_reason: str
    translation: Optional[str] = None
    redact: bool = False
    actor: Optional[str] = None


class StatementReview(BaseModel):
    actor: Optional[str] = None
    note: Optional[str] = None


class StatementVersionOut(BaseModel):
    statement_version_id: int
    version_no: int
    statement_text: Optional[str] = None            # redacted if restricted + no access
    correction_reason: Optional[str] = None
    translation: Optional[str] = None
    redacted: bool = False
    created_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class StatementOut(BaseModel):
    statement_id: int
    case_master_id: int
    statement_type: str
    canonical_person_id: Optional[int] = None
    speaker_ref: Optional[str] = None
    speaker_label: Optional[str] = None
    case_party_role_id: Optional[int] = None
    recorded_by_actor: Optional[str] = None
    recorded_at: Optional[str] = None
    place: Optional[str] = None
    language: Optional[str] = None
    access_classification: str = "demo_normal"
    state: str = "recorded"                          # draft|recorded|reviewed
    evidence_item_id: Optional[int] = None
    current_text: Optional[str] = None               # redacted-aware
    current_version_no: Optional[int] = None
    is_restricted: bool = False
    access_limited: bool = False                      # true when redacted for the caller
    versions: list[StatementVersionOut] = Field(default_factory=list)
    created_at: Optional[str] = None


class StatementListResponse(BaseModel):
    case_master_id: int
    count: int
    items: list[StatementOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Property / seizure
# ---------------------------------------------------------------------------
class PropertyItemInput(BaseModel):
    item_type: str = "property"                      # property|vehicle|weapon|substance|document
    synthetic_identifier: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    estimated_value: Optional[float] = None
    owner_canonical_person_id: Optional[int] = Field(None, ge=1)
    status: str = "seized"                            # seized|recovered|returned|disposed
    vehicle_fields: dict[str, Any] = Field(default_factory=dict)
    weapon_fields: dict[str, Any] = Field(default_factory=dict)


class SeizureCreate(BaseModel):
    seizure_type: str = "seizure"
    seized_at: Optional[str] = None
    place: Optional[str] = None
    memo_evidence_item_id: Optional[int] = Field(None, ge=1)  # seizure-memo file ref
    actor: Optional[str] = None
    items: list[PropertyItemInput] = Field(default_factory=list)


class PropertyStatusChange(BaseModel):
    status: str                                       # recovered|returned|disposed|seized
    note: Optional[str] = None
    actor: Optional[str] = None


class PropertyItemOut(BaseModel):
    property_item_id: int
    seizure_id: Optional[int] = None
    case_master_id: int
    item_type: str
    synthetic_identifier: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    estimated_value: Optional[float] = None
    owner_canonical_person_id: Optional[int] = None
    owner_label: Optional[str] = None
    status: str
    vehicle_fields: dict[str, Any] = Field(default_factory=dict)
    weapon_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class SeizureOut(BaseModel):
    seizure_id: int
    case_master_id: int
    seizure_type: str
    seized_at: Optional[str] = None
    place: Optional[str] = None
    memo_evidence_item_id: Optional[int] = None
    actor: Optional[str] = None
    created_at: Optional[str] = None
    items: list[PropertyItemOut] = Field(default_factory=list)


class SeizureListResponse(BaseModel):
    case_master_id: int
    seizures: list[SeizureOut] = Field(default_factory=list)
    unlinked_items: list[PropertyItemOut] = Field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
# Lab result (optional manual metadata)
# ---------------------------------------------------------------------------
class LabResultInput(BaseModel):
    test_type: str
    lab_name: Optional[str] = None
    synthetic_reference: Optional[str] = None
    requested_at: Optional[str] = None
    result_at: Optional[str] = None
    result_summary: Optional[str] = None
    status: str = "requested"
    report_evidence_item_id: Optional[int] = Field(None, ge=1)
    property_item_id: Optional[int] = Field(None, ge=1)
    seizure_id: Optional[int] = Field(None, ge=1)
    access_classification: str = "demo_normal"
    actor: Optional[str] = None


class LabResultUpdate(BaseModel):
    status: Optional[str] = None
    result_at: Optional[str] = None
    result_summary: Optional[str] = None
    report_evidence_item_id: Optional[int] = Field(None, ge=1)
    actor: Optional[str] = None


class LabResultOut(BaseModel):
    lab_result_id: int
    case_master_id: int
    property_item_id: Optional[int] = None
    seizure_id: Optional[int] = None
    test_type: str
    lab_name: Optional[str] = None
    synthetic_reference: Optional[str] = None
    requested_at: Optional[str] = None
    result_at: Optional[str] = None
    result_summary: Optional[str] = None
    status: str
    report_evidence_item_id: Optional[int] = None
    access_classification: str = "demo_normal"
    access_limited: bool = False
    created_by_actor: Optional[str] = None
    created_at: Optional[str] = None


class LabResultListResponse(BaseModel):
    case_master_id: int
    count: int
    items: list[LabResultOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Court / bail / disposition / outcome / lifecycle
# ---------------------------------------------------------------------------
class CourtEventInput(BaseModel):
    event_type: str                                   # chargesheet_filed|supplementary_chargesheet|hearing|remand|framing_of_charges|judgment|adjournment|bail_hearing|transfer
    court_id: Optional[int] = Field(None, ge=1)
    scheduled_at: Optional[str] = None
    occurred_at: Optional[str] = None
    outcome: Optional[str] = None
    evidence_item_id: Optional[int] = Field(None, ge=1)  # linked order/document ref
    detail: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


class CourtEventOut(BaseModel):
    court_event_id: int
    case_master_id: int
    court_id: Optional[int] = None
    court_name: Optional[str] = None
    court_reference_kind: Optional[str] = None
    event_type: str
    scheduled_at: Optional[str] = None
    occurred_at: Optional[str] = None
    outcome: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class BailInput(BaseModel):
    canonical_person_id: Optional[int] = Field(None, ge=1)
    bail_type: Optional[str] = None
    status: str = "pending"                           # granted|rejected|pending
    decided_at: Optional[str] = None
    court_id: Optional[int] = Field(None, ge=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


class BailOut(BaseModel):
    bail_event_id: int
    case_master_id: int
    canonical_person_id: Optional[int] = None
    person_label: Optional[str] = None
    bail_type: Optional[str] = None
    status: str
    decided_at: Optional[str] = None
    court_id: Optional[int] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class DispositionInput(BaseModel):
    disposition_type: str                             # convicted|acquitted|closed_b_report|closed_c_report|transferred|pending|withdrawn
    disposition_date: Optional[str] = None
    court_event_id: Optional[int] = Field(None, ge=1)
    is_final: Optional[bool] = None                    # defaulted by type when omitted
    detail: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


class DispositionOut(BaseModel):
    case_disposition_id: int
    case_master_id: int
    disposition_type: str
    disposition_date: Optional[str] = None
    court_event_id: Optional[int] = None
    is_final: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class OutcomeInput(BaseModel):
    observation_type: str = "case_outcome"
    observed_at: Optional[str] = None
    observation_window_start: Optional[str] = None
    observation_window_end: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    actor: Optional[str] = None


class OutcomeOut(BaseModel):
    outcome_observation_id: int
    case_master_id: int
    observation_type: str
    observed_at: Optional[str] = None
    observation_window_start: Optional[str] = None
    observation_window_end: Optional[str] = None
    verified: bool = True
    source_event_id: Optional[int] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class LifecycleEventInput(BaseModel):
    event_type: str
    occurred_at: Optional[str] = None
    actor_role: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TransitionMeta(BaseModel):
    event_type: str
    label: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    requires_prior_event: Optional[str] = None
    is_terminal: bool = False
    description: Optional[str] = None


class CourtLifecycleView(BaseModel):
    case_master_id: int
    category: Optional[str] = None
    current_status: Optional[str] = None
    current_status_label: Optional[str] = None
    legacy_status: Optional[str] = None
    has_case_version: bool = False
    read_only: bool = False
    read_only_reason: Optional[str] = None
    prior_event_types: list[str] = Field(default_factory=list)
    allowed_transitions: list[TransitionMeta] = Field(default_factory=list)
    court_events: list[CourtEventOut] = Field(default_factory=list)
    bail_events: list[BailOut] = Field(default_factory=list)
    dispositions: list[DispositionOut] = Field(default_factory=list)
    outcomes: list[OutcomeOut] = Field(default_factory=list)
    has_final_disposition: bool = False
    can_record_outcome: bool = False


class LifecycleEventResult(BaseModel):
    case_master_id: int
    case_event_id: int
    from_status: Optional[str] = None
    to_status: str
    is_terminal: bool = False
    legacy_status: Optional[str] = None
    bootstrapped_version: bool = False


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
class TimelineEntry(BaseModel):
    date: Optional[str] = None
    kind: str                                          # lifecycle|court|statement|seizure|disposition|outcome|bail|derived
    type: str
    label: str
    detail: Optional[str] = None
    ref_id: Optional[int] = None


class TimelineResponse(BaseModel):
    case_master_id: int
    count: int
    event_backed: bool = False
    entries: list[TimelineEntry] = Field(default_factory=list)


class NextHearingRow(BaseModel):
    """One upcoming hearing. `days_away` is counted from the corpus as-of date, not
    from today, because the synthetic dataset ends before the current date."""
    court_event_id: int
    case_id: int
    case_number: Optional[str] = None
    scheduled_on: Optional[str] = None
    days_away: Optional[int] = None
    unit_id: Optional[int] = None
    unit_name: Optional[str] = None
    district_name: Optional[str] = None
    court_name: Optional[str] = None


class NextHearingsResponse(BaseModel):
    scope: dict[str, Any] = Field(default_factory=dict)
    #: The corpus reference point — the last court event that actually happened.
    #: Reported so "in 14 days" is anchored to something the caller can see.
    as_of: Optional[str] = None
    data_age_days: Optional[int] = None
    #: None, never 0, when nothing is scheduled: "no hearing listed" and "a hearing
    #: today" are different statements and must not render identically.
    days_to_next_hearing: Optional[int] = None
    next_hearing_on: Optional[str] = None
    pending_hearings: int = 0
    cases_awaiting_hearing: int = 0
    hearings: list[NextHearingRow] = Field(default_factory=list)
    empty: bool = True
    limitations: list[str] = Field(default_factory=list)
    dataset: str = "synthetic"
