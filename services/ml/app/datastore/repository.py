"""Deployed operational data layer over Catalyst Data Store (Prompt 14 E.2/E.3).

The interface is deliberately narrow so local tests use the in-memory fake and
deployment uses the Catalyst SDK. Idempotency is by ``ExternalID``: an upsert
with the same ExternalID updates in place rather than duplicating.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Iterable, Optional


class DataStoreRepository(ABC):
    """CRUD + full-text search keyed by a stable ExternalID."""

    @abstractmethod
    def upsert(self, table: str, external_id: str, row: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a row by ExternalID. Returns the stored row."""

    @abstractmethod
    def get(self, table: str, external_id: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def query(self, table: str, *, where: Optional[dict[str, Any]] = None,
              limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def search(self, table: str, text: str, *, columns: Optional[list[str]] = None,
               limit: int = 50) -> list[dict[str, Any]]:
        """Full-text application search (case/FIR/person/evidence metadata)."""

    @abstractmethod
    def bulk_upsert(self, table: str, rows: Iterable[dict[str, Any]],
                    external_id_field: str = "ExternalID") -> dict[str, int]:
        """Idempotent bulk import. Returns {inserted, updated, rejected}."""


class InMemoryDataStore(DataStoreRepository):
    """Deterministic in-memory fake used by unit tests and local runs."""

    def __init__(self):
        # table -> {external_id -> row}
        self._t: dict[str, dict[str, dict[str, Any]]] = {}

    def _tbl(self, table: str) -> dict[str, dict[str, Any]]:
        return self._t.setdefault(table, {})

    def upsert(self, table: str, external_id: str, row: dict[str, Any]) -> dict[str, Any]:
        stored = dict(row)
        stored["ExternalID"] = external_id
        self._tbl(table)[external_id] = stored
        return stored

    def get(self, table: str, external_id: str) -> Optional[dict[str, Any]]:
        return self._tbl(table).get(external_id)

    def query(self, table, *, where=None, limit=100, offset=0):
        rows = list(self._tbl(table).values())
        if where:
            rows = [r for r in rows if all(r.get(k) == v for k, v in where.items())]
        return rows[offset:offset + limit]

    def search(self, table, text, *, columns=None, limit=50):
        needle = (text or "").lower().strip()
        if not needle:
            return []
        out = []
        for r in self._tbl(table).values():
            hay = " ".join(str(r.get(c, "")) for c in (columns or r.keys())).lower()
            if needle in hay:
                out.append(r)
            if len(out) >= limit:
                break
        return out

    def bulk_upsert(self, table, rows, external_id_field="ExternalID"):
        counts = {"inserted": 0, "updated": 0, "rejected": 0}
        for row in rows:
            ext = row.get(external_id_field)
            if not ext:
                counts["rejected"] += 1
                continue
            exists = ext in self._tbl(table)
            self.upsert(table, str(ext), row)
            counts["updated" if exists else "inserted"] += 1
        return counts


class CatalystDataStoreRepository(DataStoreRepository):
    """Deployed implementation backed by the Catalyst Python SDK (zcatalyst-sdk).

    Constructed lazily inside AppSail where the SDK + credentials exist. The SDK
    import is deferred so this module stays importable (and testable) locally.
    """

    def __init__(self, app=None):
        import zcatalyst_sdk  # deferred: only present in the AppSail image
        self._app = app or zcatalyst_sdk.initialize()
        self._ds = self._app.datastore()

    def _table(self, table: str):
        return self._ds.table(table)

    def upsert(self, table, external_id, row):
        t = self._table(table)
        existing = self.get(table, external_id)
        payload = dict(row, ExternalID=external_id)
        if existing and "ROWID" in existing:
            payload["ROWID"] = existing["ROWID"]
            return t.update_row(payload)
        return t.insert_row(payload)

    def get(self, table, external_id):
        # ZCQL parameterised lookup by ExternalID.
        zcql = self._app.zcql()
        rows = zcql.execute_query(
            f"SELECT * FROM {table} WHERE ExternalID = '{_escape(external_id)}' LIMIT 1")
        return rows[0][table] if rows else None

    def query(self, table, *, where=None, limit=100, offset=0):
        clause = ""
        if where:
            conds = " AND ".join(f"{k} = '{_escape(str(v))}'" for k, v in where.items())
            clause = f" WHERE {conds}"
        zcql = self._app.zcql()
        rows = zcql.execute_query(
            f"SELECT * FROM {table}{clause} LIMIT {int(offset)},{int(limit)}")
        return [r[table] for r in rows]

    def search(self, table, text, *, columns=None, limit=50):
        # Catalyst Data Store full-text search component.
        search = self._app.search()
        res = search.execute_search(search_query=text, table=table, max_results=limit)
        return res or []

    def bulk_upsert(self, table, rows, external_id_field="ExternalID"):
        counts = {"inserted": 0, "updated": 0, "rejected": 0}
        for row in rows:
            ext = row.get(external_id_field)
            if not ext:
                counts["rejected"] += 1
                continue
            existed = self.get(table, str(ext)) is not None
            try:
                self.upsert(table, str(ext), row)
                counts["updated" if existed else "inserted"] += 1
            except Exception:  # noqa: BLE001
                counts["rejected"] += 1
        return counts


def _escape(v: str) -> str:
    """Minimal ZCQL string escaping (single quotes)."""
    return v.replace("'", "''")


def get_repository() -> DataStoreRepository:
    """Factory: Catalyst SDK repository when running in AppSail, else the fake."""
    if os.getenv("DRISHTI_USE_CATALYST_DATASTORE", "").lower() == "true":
        return CatalystDataStoreRepository()
    return InMemoryDataStore()
