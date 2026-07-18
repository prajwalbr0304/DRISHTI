"""Typed request/response models for the canonical-identity API (Phase 4)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# --- roles / kinds ----------------------------------------------------------
PARTY_ROLES = ("accused", "victim", "complainant", "witness", "informant",
               "guardian", "organisation", "unknown")
SENSITIVITIES = ("public", "demo_normal", "restricted")


# --- persons ----------------------------------------------------------------
class PersonSummary(BaseModel):
    canonical_person_id: int
    public_ref: str
    display_label: Optional[str] = None
    is_unknown: bool = False
    primary_gender_id: Optional[int] = None
    approx_birth_year: Optional[int] = None
    is_juvenile: bool = False
    resolution_status: str = "canonical"
    merged_into: Optional[int] = None
    case_count: Optional[int] = None
    alias_count: Optional[int] = None


class PersonSearchResponse(BaseModel):
    items: list[PersonSummary]
    total: int
    page: int
    page_size: int


class AliasOut(BaseModel):
    person_alias_id: int
    alias_name: str
    alias_type: str


class IdentifierOut(BaseModel):
    person_identifier_id: int
    identifier_type: str
    identifier_value: str
    sensitivity: str


class ContactOut(BaseModel):
    person_contact_id: int
    contact_type: str
    contact_value: str
    sensitivity: str


class AddressOut(BaseModel):
    person_address_id: int
    district_id: Optional[int] = None
    address_text: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sensitivity: str


class CaseRoleOut(BaseModel):
    case_party_role_id: int
    case_master_id: int
    crime_no: Optional[str] = None
    role_type: str
    is_unknown: bool = False
    party_label: Optional[str] = None
    sequence_no: Optional[int] = None


class MergeHistoryOut(BaseModel):
    entity_merge_history_id: int
    action: str
    winner_canonical_person_id: Optional[int] = None
    loser_canonical_person_id: Optional[int] = None
    reason: Optional[str] = None
    actor: Optional[str] = None
    created_at: Optional[str] = None


class PersonDetail(PersonSummary):
    attributes: dict[str, Any] = Field(default_factory=dict)
    canonical_entity_id: Optional[int] = None
    aliases: list[AliasOut] = Field(default_factory=list)
    identifiers: list[IdentifierOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)
    addresses: list[AddressOut] = Field(default_factory=list)
    case_roles: list[CaseRoleOut] = Field(default_factory=list)
    merge_history: list[MergeHistoryOut] = Field(default_factory=list)


class CreatePersonRequest(BaseModel):
    display_label: Optional[str] = Field(None, max_length=200)
    is_unknown: bool = False
    primary_gender_id: Optional[int] = Field(None, ge=1, le=3)
    approx_birth_year: Optional[int] = Field(None, ge=1900, le=2025)
    is_juvenile: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(None, max_length=120)
    actor: Optional[str] = None


class UpdatePersonRequest(BaseModel):
    display_label: Optional[str] = Field(None, max_length=200)
    primary_gender_id: Optional[int] = Field(None, ge=1, le=3)
    approx_birth_year: Optional[int] = Field(None, ge=1900, le=2025)
    is_juvenile: Optional[bool] = None
    attributes: Optional[dict[str, Any]] = None
    actor: Optional[str] = None


# --- organisations ----------------------------------------------------------
class OrgSummary(BaseModel):
    canonical_organisation_id: int
    public_ref: str
    name: str
    org_type: Optional[str] = None


class OrgSearchResponse(BaseModel):
    items: list[OrgSummary]
    total: int
    page: int
    page_size: int


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    org_type: Optional[str] = Field("unknown", max_length=40)
    attributes: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(None, max_length=120)
    actor: Optional[str] = None


# --- attribute inputs -------------------------------------------------------
class AliasInput(BaseModel):
    alias_name: str = Field(..., min_length=1, max_length=200)
    alias_type: str = Field("alias", max_length=40)
    actor: Optional[str] = None


class IdentifierInput(BaseModel):
    identifier_type: str = Field(..., min_length=1, max_length=60)
    identifier_value: str = Field(..., min_length=1, max_length=120)
    sensitivity: str = Field("restricted")
    actor: Optional[str] = None


class ContactInput(BaseModel):
    contact_type: str = Field("phone", max_length=40)
    contact_value: str = Field(..., min_length=1, max_length=120)
    sensitivity: str = Field("restricted")
    actor: Optional[str] = None


class AddressInput(BaseModel):
    district_id: Optional[int] = None
    address_text: Optional[str] = Field(None, max_length=300)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    sensitivity: str = Field("restricted")
    actor: Optional[str] = None


# --- case-party roles -------------------------------------------------------
class AddPartyRequest(BaseModel):
    canonical_person_id: Optional[int] = None
    canonical_organisation_id: Optional[int] = None
    is_unknown: bool = False
    role_type: str
    party_label: Optional[str] = Field(None, max_length=200)
    sequence_no: Optional[int] = None
    actor: Optional[str] = None


class UpdatePartyRequest(BaseModel):
    role_type: Optional[str] = None
    sequence_no: Optional[int] = None
    actor: Optional[str] = None


class PartyMutationResponse(BaseModel):
    case_party_role_id: int
    case_master_id: int
    canonical_person_id: Optional[int] = None
    canonical_organisation_id: Optional[int] = None
    role_type: str
    is_unknown: bool = False


# --- resolution candidates + review -----------------------------------------
class CandidatePersonRef(BaseModel):
    canonical_person_id: int
    public_ref: str
    display_label: Optional[str] = None
    case_count: Optional[int] = None
    alias_count: Optional[int] = None


class CandidateOut(BaseModel):
    entity_resolution_candidate_id: int
    person_a: CandidatePersonRef
    person_b: CandidatePersonRef
    method: str
    score: Optional[float] = None
    match_features: dict[str, Any] = Field(default_factory=dict)
    status: str
    reviewed_by_actor: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


class CandidateListResponse(BaseModel):
    items: list[CandidateOut]
    total: int
    page: int
    page_size: int


class GenerateCandidatesRequest(BaseModel):
    canonical_person_id: Optional[int] = None   # limit to candidates for one person
    limit: int = Field(25, ge=1, le=200)
    min_score: float = Field(0.3, ge=0, le=1)
    actor: Optional[str] = None


class GenerateCandidatesResponse(BaseModel):
    created: int
    candidates: list[CandidateOut]


class ReviewCandidateRequest(BaseModel):
    action: str = Field(..., pattern="^(accept|reject|create_new)$")
    winner_canonical_person_id: Optional[int] = None   # for accept -> merge
    reason: Optional[str] = Field(None, max_length=500)
    actor: Optional[str] = None


class MergeRequest(BaseModel):
    loser_canonical_person_id: int
    reason: Optional[str] = Field(None, max_length=500)
    actor: Optional[str] = None


class UnmergeRequest(BaseModel):
    loser_canonical_person_id: int
    reason: Optional[str] = Field(None, max_length=500)
    actor: Optional[str] = None


class MergeResult(BaseModel):
    action: str
    winner_canonical_person_id: int
    loser_canonical_person_id: int
    moved_references: dict[str, int] = Field(default_factory=dict)
    entity_merge_history_id: Optional[int] = None
    reversible: bool = True
