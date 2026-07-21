"""Deployed operational data layer over Catalyst Data Store (Prompt 14 E.2/E.3).

The interface is deliberately narrow so local tests use the in-memory fake and
deployment uses the Catalyst REST API (see :mod:`app.catalyst_rest`). We use the
documented REST API rather than the zcatalyst SDK because the SDK is unusable in
a custom-container AppSail with a self-client refresh token (it defaults to
internal ``*.localzoho.com`` domains and its token refresh double-slashes the
accounts URL). Idempotency is by ``ExternalID``: an upsert with the same
ExternalID updates in place rather than duplicating.
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
    """Deployed implementation over the Catalyst REST API (Admin scope).

    Uses :mod:`app.catalyst_rest` (self-client refresh token, hard timeouts)
    rather than the zcatalyst SDK. A custom-container AppSail has no per-request
    Catalyst session, so all access is admin-scope via the self-client. ZCQL is
    used for reads; the row API for writes. Idempotent by ExternalID.
    """

    def __init__(self, client=None):
        from ..catalyst_rest import get_rest_client
        self._c = client or get_rest_client()

    def upsert(self, table, external_id, row):
        payload = dict(row, ExternalID=external_id)
        existing = self.get(table, external_id)
        if existing and existing.get("ROWID"):
            payload["ROWID"] = existing["ROWID"]
            return self._c.update_row(table, payload)
        return self._c.insert_row(table, payload)

    def get(self, table, external_id):
        rows = self._c.zcql(
            f"SELECT * FROM {table} WHERE ExternalID = '{_escape(external_id)}' LIMIT 1")
        return _unwrap(rows[0], table) if rows else None

    def query(self, table, *, where=None, limit=100, offset=0):
        clause = ""
        if where:
            conds = " AND ".join(f"{k} = '{_escape(str(v))}'" for k, v in where.items())
            clause = f" WHERE {conds}"
        rows = self._c.zcql(f"SELECT * FROM {table}{clause} LIMIT {int(offset)},{int(limit)}")
        return [_unwrap(r, table) for r in rows]

    def search(self, table, text, *, columns=None, limit=50):
        res = self._c.search(text, table, columns, max_results=limit)
        return res.get(table, []) if isinstance(res, dict) else []

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


def _unwrap(row: dict, table: str) -> dict:
    """ZCQL rows come wrapped as {TableName: {...columns...}}; unwrap defensively."""
    if isinstance(row, dict) and table in row and isinstance(row[table], dict):
        return row[table]
    return row


def _escape(v: str) -> str:
    """Minimal ZCQL string escaping (single quotes)."""
    return str(v).replace("'", "''")


def get_repository() -> DataStoreRepository:
    """Factory: Catalyst REST repository when running in AppSail, else the fake."""
    if os.getenv("DRISHTI_USE_CATALYST_DATASTORE", "").lower() == "true":
        return CatalystDataStoreRepository()
    return InMemoryDataStore()
