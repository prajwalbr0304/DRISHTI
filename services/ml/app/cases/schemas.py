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
    crime_no: Optional[str] = None
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
    station: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    brief_facts: Optional[str] = None
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


class CaseCore(BaseModel):
    case_id: int
    crime_no: Optional[str] = None
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
    station: Optional[str] = None
    io_name: Optional[str] = None


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
