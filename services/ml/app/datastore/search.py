"""Deployed metadata search over Catalyst Data Store full-text search (Prompt 14 E.6).

Item 6: the deployed case / FIR / person / evidence metadata search MUST use
Catalyst Data Store full-text search and MUST NOT be sent to an external search
service. This module is that capability. It searches only the mapping's
search-enabled Data Store tables and delegates to ``DataStoreRepository.search``:

  * deployed -> ``CatalystDataStoreRepository.search`` = the Catalyst Data Store
    full-text search component (``app.search().execute_search``); never an
    external service;
  * local / tests -> ``InMemoryDataStore.search`` (deterministic substring fake).

The retained AWS PostgreSQL FTS/pg_trgm path is used only by the offline
analytics/rich list endpoints, never by this deployed operational search.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .mapping import search_enabled_tables
from .repository import DataStoreRepository, get_repository

# The item-6 metadata-search kinds -> Data Store tables. "all" spans every
# search-enabled table declared in the mapping.
KIND_TABLES: dict[str, tuple[str, ...]] = {
    "case": ("Case",),
    "person": ("CanonicalPerson", "PersonAlias"),
    "evidence": ("EvidenceItem",),
}


@dataclass(frozen=True)
class SearchHit:
    external_id: Optional[str]
    datastore_table: str
    domain: str
    snippet: str

    def as_dict(self) -> dict:
        return {"external_id": self.external_id, "table": self.datastore_table,
                "domain": self.domain, "snippet": self.snippet}


def _search_columns_by_table() -> dict[str, tuple[list[str], str]]:
    """{datastore_table: (search_columns, domain)} for the search-enabled tables."""
    return {m.datastore_table: (list(m.search_columns), m.domain.value)
            for m in search_enabled_tables()}


class MetadataSearch(ABC):
    backend_name = "abstract"

    @abstractmethod
    def search(self, query: str, *, kind: str = "all", limit: int = 50) -> list[SearchHit]:
        ...


class RepositoryMetadataSearch(MetadataSearch):
    """Data Store full-text search via the repository contract (Catalyst FTS in
    deployment, in-memory fake locally). Never calls an external service."""

    def __init__(self, repo: Optional[DataStoreRepository] = None):
        self._repo = repo or get_repository()
        self.backend_name = type(self._repo).__name__
        self._cols = _search_columns_by_table()

    def _target_tables(self, kind: str) -> list[str]:
        if kind == "all":
            return list(self._cols.keys())
        return [t for t in KIND_TABLES.get(kind, ()) if t in self._cols]

    def search(self, query: str, *, kind: str = "all", limit: int = 50) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []
        hits: list[SearchHit] = []
        for table in self._target_tables(kind):
            cols, domain = self._cols[table]
            try:
                rows = self._repo.search(table, q, columns=cols, limit=limit)
            except Exception:  # noqa: BLE001 — a single table must not break search
                rows = []
            for r in rows:
                snippet = next((str(r[c]) for c in cols if r.get(c)), "")
                hits.append(SearchHit(external_id=r.get("ExternalID"),
                                      datastore_table=table, domain=domain,
                                      snippet=snippet[:200]))
                if len(hits) >= limit:
                    return hits
        return hits


def get_metadata_search() -> MetadataSearch:
    """Factory: the repository-backed Data Store FTS search (Catalyst when
    DRISHTI_USE_CATALYST_DATASTORE=true, else the in-memory fake)."""
    return RepositoryMetadataSearch()
