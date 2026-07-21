"""Deployed operational data layer over Catalyst Data Store (Prompt 14 E.2/E.3).

The interface is deliberately narrow so local tests use the in-memory fake and
deployment uses the Catalyst SDK. Idempotency is by ``ExternalID``: an upsert
with the same ExternalID updates in place rather than duplicating.
"""
from __future__ import annotations

import os
import threading
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


_ADMIN_APP = None
_ADMIN_APP_LOCK = threading.Lock()


def _india_default_domain() -> str:
    return os.getenv("ZOHO_CATALYST_API_DOMAIN", "https://api.catalyst.zoho.in")


def build_admin_app(app=None):
    """Return a Catalyst SDK app initialized with ADMIN scope.

    A custom-container AppSail has no per-request Catalyst session (it only
    receives the gateway's signed HMAC context), so server-side Data Store / ZCQL
    / Cache access must use ADMIN scope via a self-client RefreshTokenCredential
    (Catalyst "integrate SDK in third-party apps"). Credentials are read from the
    server-side environment only (never committed):

      ZOHO_CATALYST_CLIENT_ID / ZOHO_CATALYST_CLIENT_SECRET /
      ZOHO_CATALYST_REFRESH_TOKEN  — self-client OAuth (admin scope);
      CATALYST_PROJECT_ID (auto-injected) or ZOHO_CATALYST_PROJECT_ID;
      ZOHO_CATALYST_ZAID           — the portal id (project_key);
      ZOHO_CATALYST_API_DOMAIN     — DC api domain (default India api.catalyst.zoho.in);
      ZOHO_CATALYST_ENVIRONMENT    — Development|Production (default Development).

    Cached process-wide. Falls back to the plain in-Catalyst initialize() (native
    functions) when no self-client credentials are configured.
    """
    global _ADMIN_APP
    if app is not None:
        return app
    if _ADMIN_APP is not None:
        return _ADMIN_APP
    with _ADMIN_APP_LOCK:
        if _ADMIN_APP is not None:
            return _ADMIN_APP
        import zcatalyst_sdk  # deferred: only present in the AppSail image
        client_id = os.getenv("ZOHO_CATALYST_CLIENT_ID")
        client_secret = os.getenv("ZOHO_CATALYST_CLIENT_SECRET")
        refresh_token = os.getenv("ZOHO_CATALYST_REFRESH_TOKEN")
        project_id = os.getenv("CATALYST_PROJECT_ID") or os.getenv("ZOHO_CATALYST_PROJECT_ID")
        project_key = os.getenv("ZOHO_CATALYST_ZAID") or os.getenv("CATALYST_PROJECT_KEY")
        if client_id and client_secret and refresh_token and project_id and project_key:
            from zcatalyst_sdk import credentials
            from zcatalyst_sdk.types import ICatalystOptions
            cred = credentials.RefreshTokenCredential({
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            })
            options = ICatalystOptions(
                project_id=project_id,
                project_key=project_key,
                project_domain=_india_default_domain(),
                environment=os.getenv("ZOHO_CATALYST_ENVIRONMENT", "Development"),
            )
            _ADMIN_APP = zcatalyst_sdk.initialize_app(
                credential=cred, options=options, name="drishti-appsail")
        else:
            # Native-function context (admin scope implicit) or misconfiguration;
            # readiness surfaces the failure if this cannot serve.
            _ADMIN_APP = zcatalyst_sdk.initialize()
    return _ADMIN_APP


class CatalystDataStoreRepository(DataStoreRepository):
    """Deployed implementation backed by the Catalyst Python SDK (zcatalyst-sdk).

    Constructed lazily inside AppSail. Initialized with ADMIN scope via a
    self-client RefreshTokenCredential (see :func:`build_admin_app`) because a
    custom-container AppSail has no per-request Catalyst session. The SDK import
    is deferred so this module stays importable (and testable) locally.
    """

    def __init__(self, app=None):
        self._app = build_admin_app(app)
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
