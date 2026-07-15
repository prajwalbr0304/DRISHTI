"""Case decision-support (Phase 10 / doc 02 §5-6).

Three grounded capabilities, all returning the shared AiResult contract:

  * similar    — live semantic similar-case search over CrimeEmbedding
                 (pgvector, HNSW, cosine). The query case is embedded at query
                 time and compared against the live corpus (doc 02 §5).
  * summary    — a case summary + timeline generated STRICTLY from linked
                 records, with an inline citation on every claim
                 (Ontology-Augmented Generation, doc 02 §6). Written to AISummary.
  * leads      — ranked next investigative steps, each with the evidence behind
                 it, written to OfficerRecommendation. Suggestions, not orders.

Modules:
  casedata    — shared reads of CaseMaster + children + the canonical case text
  embeddings  — Embedder interface (multilingual sentence-transformer primary,
                deterministic hashing fallback) + corpus/query embedding
  similar     — pgvector nearest-neighbour search + outcomes
  summary     — OAG cited-summary + timeline builder
  leads       — rule-based investigative-lead ranking with evidence
  service     — AiResult envelopes + typed writes + ModelInference audit
  schemas     — typed response models
  router      — FastAPI routes
"""
