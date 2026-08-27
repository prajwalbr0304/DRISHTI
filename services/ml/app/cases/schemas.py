"""Typed response models for the Phase-10 case decision-support endpoints.
Every envelope carries the shared AiResult contract plus the typed payload."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class SimilarCase(BaseModel):
    case_id: int
    crime_no: Optional[str] = None
    crime_group: Optional[str] = None
    crime_subhead: Optional[str] = None
    gravity: Optional[str] = None
    district: Optional[str] = None
    status: Optional[str] = None
    disposition: Optional[str] = None          # outcome (chargesheet disposition)
    accused_count: int = 0
    arrest_count: int = 0
    registered_date: Optional[str] = None
    similarity: float                           # 1 - cosine distance, clamped [0,1]
    distance: float
    why_match: list[str] = []                   # shared context/MO (never outcome)
    source_links: list[str] = []                # provenance: CaseMaster refs


class SimilarResponse(BaseModel):
    result: AiResult
    query_case_id: int
    model_name: str
    model_version_id: int
    corpus_size: int
    scope: str = "district"                     # demo case/unit context filter applied
    scope_district_id: Optional[int] = None
    limitations: str = ""
    results: list[SimilarCase]


class TimelineEvent(BaseModel):
    date: str
    label: str
    citations: list[str]


class SummaryClaim(BaseModel):
    text: str
    citations: list[str]


class SummaryResponse(BaseModel):
    result: AiResult
    case_id: int
    crime_no: Optional[str] = None
    summary_id: Optional[int] = None            # written AISummary row
    summary_text: str
    sentences: list[SummaryClaim]
    timeline: list[TimelineEvent]
    claim_count: int
    cited_claim_count: int
    fully_cited: bool                           # OAG guarantee: no uncited claim
    confidence: float


class Lead(BaseModel):
    recommendation_id: Optional[int] = None     # written OfficerRecommendation row
    rank: int
    kind: str
    step: str
    score: float
    evidence: list[str]                         # source record ids behind the lead
    why: str


class LeadsResponse(BaseModel):
    result: AiResult
    case_id: int
    crime_no: Optional[str] = None
    io_employee_id: Optional[int] = None
    leads: list[Lead]


# ---- Phase 15c: Case Explorer + Case-file reads (raw data; no AiResult) -----

class CaseListItem(BaseModel):
    case_id: int
    crime_no: Optional[str] = None                 # presentation-safe public reference
    internal_crime_no: Optional[str] = None        # deterministic fixture key, when different
    case_no: Optional[str] = None
    registered_date: Optional[str] = None
    status_id: Optional[int] = None
    status: Optional[str] = None
    crime_group: Optional[str] = None
    crime_subhead: Optional[str] = None
    gravity: Optional[str] = None
    district_id: Optional[int] = None
    district: Optional[str] = None
    station_id: Optional[int] = None
    station: Optional[str] = None                  # proxy-safe display label
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    brief_facts: Optional[str] = None
    record_origin: str = "synthetic_fixture"
    is_synthetic: bool = True
    reference_mapping_kind: Optional[str] = None
    location_label: Optional[str] = None
    location_precision: Optional[str] = None
    not_exact_incident_scene: bool = False
    location_uncertainty_radius_m: Optional[int] = None
    location_attribution: Optional[str] = None
    victim_count: int = 0
    accused_count: int = 0
    has_arrest: bool = False
    has_chargesheet: bool = False


class CaseListResponse(BaseModel):
    items: list[CaseListItem]
    total: int
    page: int
    page_size: int


class FilterOption(BaseModel):
    id: int
    name: Optional[str] = None


class FilterOptionsResponse(BaseModel):
    districts: list[FilterOption]
    stations: list[FilterOption]
    crime_heads: list[FilterOption]
    sub_heads: list[FilterOption]
    statuses: list[FilterOption]
    gravities: list[FilterOption]


class CaseloadStage(BaseModel):
    key: str                              # canonical stage key (matches the UI pipeline)
    label: str
    count: int


class CaseloadStatusBreakdown(BaseModel):
    status: str                           # raw CaseStatusMaster name
    stage: str                            # canonical stage it folds into
    count: int


class CaseloadResponse(BaseModel):
    """Per-stage caseload counts for the Command Center pipeline. Each case sits
    in exactly one stage, so ``stages`` counts sum to ``total``."""
    stages: list[CaseloadStage]
    by_status: list[CaseloadStatusBreakdown]
    total: int
    open_total: int                       # total minus disposed
    disposed_total: int


class CaseCore(BaseModel):
    case_id: int
    crime_no: Optional[str] = None                 # presentation-safe public reference
    internal_crime_no: Optional[str] = None        # deterministic fixture key, when different
    registered_date: Optional[str] = None
    incident_from: Optional[str] = None
    incident_to: Optional[str] = None
    brief_facts: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    station_id: Optional[int] = None
    io_employee_id: Optional[int] = None
    major_head_id: Optional[int] = None
    minor_head_id: Optional[int] = None
    crime_group: Optional[str] = None
    crime_subhead: Optional[str] = None
    gravity: Optional[str] = None
    status: Optional[str] = None
    district_id: Optional[int] = None
    district: Optional[str] = None
    station: Optional[str] = None                  # proxy-safe display label
    io_name: Optional[str] = None                  # suppressed when the FK is a proxy
    record_origin: str = "synthetic_fixture"
    is_synthetic: bool = True
    reference_mapping_kind: Optional[str] = None
    location_label: Optional[str] = None
    location_precision: Optional[str] = None
    not_exact_incident_scene: bool = False
    location_uncertainty_radius_m: Optional[int] = None
    location_attribution: Optional[str] = None


class CasePerson(BaseModel):
    id: int
    name: Optional[str] = None
    age: Optional[int] = None
    person_id: Optional[str] = None       # accused sort key (A1, A2, ...)


class CaseSectionRow(BaseModel):
    act: Optional[str] = None
    section: Optional[str] = None
    description: Optional[str] = None
    act_name: Optional[str] = None


class CaseArrest(BaseModel):
    id: int
    accused_id: Optional[int] = None
    date: Optional[str] = None
    io_id: Optional[int] = None
    type: Optional[int] = None


class CaseChargesheet(BaseModel):
    id: int
    date: Optional[str] = None
    cstype: Optional[str] = None


class TimelineEntry(BaseModel):
    date: str
    type: str
    label: str
    detail: Optional[str] = None


class CaseCurrentVersion(BaseModel):
    case_version_id: int
    version_no: int
    status_code: str
    record_origin: str
    is_synthetic: bool = True
    read_only: bool = False
    excluded_from_derived_analytics: bool = False
    source_cutoff: Optional[str] = None
    official_references: dict[str, Any] = {}
    reference_mapping: dict[str, Any] = {}
    location: dict[str, Any] = {}
    change_reason: Optional[str] = None


class CaseSourceSummary(BaseModel):
    source_record_id: int
    external_ref: Optional[str] = None
    record_kind: Optional[str] = None
    source_system_code: Optional[str] = None
    source_system_name: Optional[str] = None
    public_source_id: Optional[str] = None
    title: Optional[str] = None
    publisher: Optional[str] = None
    published_date: Optional[str] = None
    source_url: Optional[str] = None
    authenticity: Optional[str] = None
    presentation_use: Optional[str] = None
    rights_and_handling: Optional[str] = None
    last_checked: Optional[str] = None


class CaseNotice(BaseModel):
    code: str
    severity: str
    title: str
    message: str


class CaseDetailResponse(BaseModel):
    core: CaseCore
    sections: list[CaseSectionRow]
    section_labels: list[str]
    victims: list[CasePerson]
    accused: list[CasePerson]
    complainants: list[CasePerson]
    arrests: list[CaseArrest]
    chargesheets: list[CaseChargesheet]
    timeline: list[TimelineEntry]
    current_version: Optional[CaseCurrentVersion] = None
    sources: list[CaseSourceSummary] = []
    notices: list[CaseNotice] = []


class CaseNetworkNode(BaseModel):
    id: str
    kind: str
    label: Optional[str] = None
    sub: Optional[str] = None
    root: bool = False
    case_id: Optional[int] = None


class CaseNetworkEdge(BaseModel):
    source: str
    target: str
    type: str
    label: Optional[str] = None


class CaseNetworkResponse(BaseModel):
    case_id: int
    crime_no: Optional[str] = None
    node_count: int
    edge_count: int
    linked_case_count: int
    nodes: list[CaseNetworkNode]
    edges: list[CaseNetworkEdge]


class EvidenceItem(BaseModel):
    evidence_id: int
    evidence_type: str
    title: str
    description: Optional[str] = None
    reference: Optional[str] = None
    created_by_role: Optional[str] = None
    created_at: Optional[str] = None


class EvidenceListResponse(BaseModel):
    available: bool                       # False if the CaseEvidence table isn't provisioned yet
    items: list[EvidenceItem]


class EvidenceCreateRequest(BaseModel):
    evidence_type: str = "note"
    title: str
    description: Optional[str] = None
    reference: Optional[str] = None


class EvidenceCreateResponse(BaseModel):
    evidence: EvidenceItem
