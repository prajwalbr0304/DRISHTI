"""Graph-analysis engine (Phase 6): Postgres-native (Option A).

Modules:
  enrich      — batch: add intermediary nodes (phone/vehicle/location/bank_account)
  queries     — recursive-CTE neighbourhood, shortest-path CTE fallback
  algorithms  — networkx: Louvain communities, PageRank / betweenness centrality
  hidden      — hidden-association materialization + proof paths
  service     — high-level functions returning typed data
  router      — FastAPI endpoints (all return the AiResult contract + typed data)
  schemas     — Pydantic response models
"""
