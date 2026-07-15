"""Typed response models for the graph endpoints. Every envelope carries the
shared AiResult contract plus the typed graph payload."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


class GraphNode(BaseModel):
    entity_id: int
    entity_type: str
    label: Optional[str] = None
    ref_table: Optional[str] = None
    distance: Optional[int] = None
    community: Optional[int] = None
    pagerank: Optional[float] = None
    betweenness: Optional[float] = None
    attributes: Optional[dict[str, Any]] = None


class GraphEdge(BaseModel):
    edge_id: int
    source: int
    target: int
    relationship_type: str
    weight: float = 0.0
    confidence: Optional[float] = None


class SubgraphResponse(BaseModel):
    result: AiResult
    focal_entity: Optional[int] = None
    max_hops: Optional[int] = None
    top_n: Optional[int] = None
    node_count: int
    edge_count: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PathResponse(BaseModel):
    result: AiResult
    found: bool
    method: Optional[str] = None
    hops: Optional[int] = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class CommunitiesResponse(BaseModel):
    result: AiResult
    num_communities: int
    modularity: Optional[float] = None
    known_gangs: int
    precision: float
    recall: float
    f1: float
    rediscovered_gangs: int
    candidate_new_groups: int


class PersonOfInterest(BaseModel):
    entity_id: int
    label: Optional[str] = None
    entity_type: str
    pagerank: float
    betweenness: float
    community: Optional[int] = None


class CentralityResponse(BaseModel):
    result: AiResult
    computed: bool
    persons_of_interest: list[PersonOfInterest]


class HiddenAssociationCard(BaseModel):
    association_id: int
    entity_a: int
    entity_b: int
    label_a: Optional[str] = None
    label_b: Optional[str] = None
    independent_links: int
    link_kinds: list[str]
    proof_record_ids: list[str]
    shared_intermediaries: list[int]
    shared_case_count: int
    score: float


class HiddenFeedResponse(BaseModel):
    result: AiResult
    total: int
    page: int
    page_size: int
    items: list[HiddenAssociationCard]


class ProofPathResponse(BaseModel):
    result: AiResult
    entity_a: int
    entity_b: int
    link_kinds: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
