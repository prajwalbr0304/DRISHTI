"""Typed response models for the synthetic scenario registry API (Prompt 20 A)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ScopeDef(BaseModel):
    code: str
    label: str
    kn: str
    desc: str


class FamilyDef(BaseModel):
    code: str
    label: str
    head: str
    kn: str


class Taxonomy(BaseModel):
    jurisdiction_scopes: list[ScopeDef]
    crime_families: list[FamilyDef]
    entity_types: list[str]
    edge_bases: list[str]


class ScenariosOverview(BaseModel):
    total: int
    counts: dict[str, int]
    valid: bool
    taxonomy: Taxonomy
    note: str


class ScenarioNode(BaseModel):
    id: str
    type: str
    label: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class ScenarioEdge(BaseModel):
    source: str
    rel: str
    target: str
    basis: str
    note: str = ""


class Scenario(BaseModel):
    scenario_id: str
    title: str
    crime_family: str
    crime_subtype: str
    jurisdiction_scope: str
    gravity: str
    source_classification: str
    live_collection: bool
    summary: str
    districts: list[str] = Field(default_factory=list)
    entities: list[ScenarioNode] = Field(default_factory=list)
    edges: list[ScenarioEdge] = Field(default_factory=list)
    referral: Optional[dict[str, Any]] = None
    nl_examples: list[dict[str, str]] = Field(default_factory=list)


class ScenarioSearchResponse(BaseModel):
    total: int
    query: Optional[str] = None
    jurisdiction_scope: Optional[str] = None
    crime_family: Optional[str] = None
    items: list[Scenario] = Field(default_factory=list)


class ValidationResponse(BaseModel):
    ok: bool
    failures: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class NlExample(BaseModel):
    scenario_id: str
    lang: str
    q: str
    crime_family: str
    jurisdiction_scope: str


class NlExamplesResponse(BaseModel):
    total: int
    items: list[NlExample] = Field(default_factory=list)
