"""Catalyst Data Store operational layer (Prompt 14 section E).

The deployed app's operational relational records live in Catalyst Data Store,
NOT in AWS RDS. This package provides:

  * ``repository.py`` — the narrow ``DataStoreRepository`` interface, an in-memory
    fake for tests/local runs, and a Catalyst-SDK-backed implementation used in
    deployment. Every row carries a stable ``ExternalID`` so imports are
    idempotent (upsert by ExternalID).
  * ``mapping.py`` — the versioned AWS PostgreSQL -> Data Store table/column map
    covering every submitted domain, plus reserved namespaces for the
    Investigation Board / Disaster Response modules (created in later phases).

No deployed operational endpoint requires direct RDS access. The PostgreSQL
repository is retained only as an offline migration / read-only analytics adapter.
"""
