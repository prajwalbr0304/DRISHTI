"""Typed response models for the Phase-11 money-trail endpoints.
Every envelope carries the shared AiResult contract plus the typed payload."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from ..contracts import AiResult


# ---- trace (accounts-only directed weighted flow, for a Sankey) ------------
class TraceNode(BaseModel):
    account_id: int
    label: Optional[str] = None            # holder name
    account_type: Optional[str] = None
    bank: Optional[str] = None
    is_flagged: bool = False
    owner_entity_id: Optional[int] = None  # links into EntityGraph (unified view)
    hop: int = 0                           # min hops from the start account


class TraceEdge(BaseModel):
    source_account: int
    target_account: int
    amount: float                          # summed over parallel transactions
    txn_count: int
    is_flagged: bool = False
    flag_reasons: list[str] = []
    transaction_ids: list[int] = []        # provenance
    hop: int = 1


class TraceResponse(BaseModel):
    result: AiResult
    start_account: int
    max_hops: int
    node_count: int
    edge_count: int
    total_traced_amount: float
    cycle_guarded: bool = True
    nodes: list[TraceNode]
    edges: list[TraceEdge]


# ---- detection -------------------------------------------------------------
class PatternMetric(BaseModel):
    detected: int
    ground_truth: int
    true_positive: int
    precision: float
    recall: float
    f1: float


class DetectionResponse(BaseModel):
    result: AiResult
    transactions_scanned: int
    transactions_flagged: int
    by_pattern: dict[str, int]
    alerts_written: int
    structuring_hubs: int
    layering_chains: int
    circular_flows: int
    validation: dict[str, PatternMetric]   # per-pattern precision/recall vs injected
    model_version_id: int


# ---- unified people + money subgraph ---------------------------------------
class UnifiedNode(BaseModel):
    id: str                                # 'acct:<id>' | 'ent:<id>'
    kind: str                              # 'account' | 'entity'
    label: Optional[str] = None
    account_id: Optional[int] = None
    entity_id: Optional[int] = None
    account_type: Optional[str] = None
    bank: Optional[str] = None
    is_flagged: Optional[bool] = None
    entity_type: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None


class UnifiedEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str                              # 'transaction' | 'owns'
    amount: Optional[float] = None
    txn_count: Optional[int] = None
    is_flagged: Optional[bool] = None
    flag_reason: Optional[str] = None


class UnifiedResponse(BaseModel):
    result: AiResult
    seed_kind: str                         # 'entity' | 'account'
    seed_id: int
    node_count: int
    edge_count: int
    nodes: list[UnifiedNode]
    edges: list[UnifiedEdge]


# ---- flagged-transaction feed (read) ---------------------------------------
class FlaggedTxn(BaseModel):
    transaction_id: int
    source_account: int
    destination_account: int
    amount: float
    txn_timestamp: Optional[str] = None
    channel: Optional[str] = None
    flag_reason: Optional[str] = None
    evidence_case_id: Optional[int] = None


class FlaggedFeedResponse(BaseModel):
    result: AiResult
    total: int
    page: int
    page_size: int
    by_reason: dict[str, int]
    items: list[FlaggedTxn]
