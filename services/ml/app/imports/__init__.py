"""Phase 8 — template-driven digital + financial structured imports.

Upload a structured CSV/JSON file (as evidence) -> pick a template/schema version
-> parse into STAGING only -> dry-run (counts/mapping/errors/duplicates/rejected)
-> approve commit -> one SourceRecord provenance per canonical row -> resolve
phones/accounts/devices through CANDIDATE (reviewed) entity links. Idempotent,
retry-safe, with partial errors, rollback and supersession.

Digital canonical targets: CommunicationEvent (CDR/chat/IP), DeviceArtifact,
LocationObservation. Financial canonical targets: FinancialTransaction,
FinancialAccount. Money patterns are rule-based with explicit reason codes and a
reviewer disposition; no communication/financial link implies guilt.
"""
