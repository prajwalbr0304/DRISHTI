"""Disaster persistence over Catalyst Data Store (Prompt 17 §B/§J).

Thin disaster-specific layer on top of the shared ``DataStoreRepository``
(datastore/repository.py), mirroring ``app/board/repo.py``:

  * a PROCESS-LEVEL singleton repository (``get_repository()`` hands out a fresh
    in-memory fake per call, so operational state would not survive between
    requests without this);
  * identity-PK allocation (the Data Store CRUD contract has no auto-increment)
    seeded from the current max and handed out monotonically under a lock;
  * stable ``ExternalID`` keys (``<prefix>:<pk>``) so writes are idempotent;
  * SOFT delete (a delete is a logged state change — suits an auditable tool);
  * APPEND-ONLY tables (``HazardPrediction`` / ``HydroMetReading`` /
    ``DisasterActivity``) — ``update``/``soft_delete`` raise for them everywhere.

Catalyst Data Store is authoritative for the submitted operational feature. The
AWS PostGIS/pgRouting mirror is reconstructable from these rows.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..datastore import disaster_schema
from ..datastore.repository import DataStoreRepository, get_repository

_APPEND_ONLY = set(disaster_schema.append_only_tables())
_MAX_SCAN = 200_000


def _now() -> str:
    # Catalyst Data Store datetime columns require 'yyyy-MM-dd HH:mm:ss'; ISO8601
    # with 'T'/timezone is rejected ("Invalid input value ... datetime value
    # expected"). Store the naive-UTC wall clock in that exact format.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class DisasterRepoError(Exception):
    pass


class DisasterRepo:
    """Disaster-scoped persistence facade over a single DataStoreRepository."""

    def __init__(self, repo: Optional[DataStoreRepository] = None):
        self._repo = repo or get_repository()
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    @property
    def store(self) -> DataStoreRepository:
        return self._repo

    # -- id allocation ------------------------------------------------------
    def _seed_counter(self, table: str) -> int:
        pk = disaster_schema.table(table).pk
        rows = self._repo.query(table, limit=_MAX_SCAN)
        mx = 0
        for r in rows:
            try:
                mx = max(mx, int(r.get(pk) or 0))
            except (TypeError, ValueError):
                continue
        return mx

    def next_id(self, table: str) -> int:
        with self._lock:
            if table not in self._counters:
                self._counters[table] = self._seed_counter(table)
            self._counters[table] += 1
            return self._counters[table]

    def reseed_counters(self) -> None:
        """Drop cached id counters so the next allocation reseeds from the current
        max (call after bulk-seeding rows with explicit pk values)."""
        with self._lock:
            self._counters.clear()

    def external_id(self, table: str, pk_value: Any) -> str:
        return f"{disaster_schema.table(table).external_id_prefix}:{pk_value}"

    # -- core CRUD ----------------------------------------------------------
    def create(self, table: str, fields: dict[str, Any], *,
               pk_value: Optional[int] = None) -> dict[str, Any]:
        t = disaster_schema.table(table)
        pk_val = pk_value if pk_value is not None else self.next_id(table)
        row = dict(fields)
        row[t.pk] = pk_val
        cols = t.column_names()
        row.setdefault("CreatedAt", _now())
        if "UpdatedAt" in cols:
            row.setdefault("UpdatedAt", row.get("CreatedAt"))
        if "Version" in cols:
            row.setdefault("Version", 1)
        return self._repo.upsert(table, self.external_id(table, pk_val), row)

    def get(self, table: str, pk_value: Any) -> Optional[dict[str, Any]]:
        return self._repo.get(table, self.external_id(table, pk_value))

    def update(self, table: str, pk_value: Any, patch: dict[str, Any]) -> dict[str, Any]:
        if table in _APPEND_ONLY:
            raise DisasterRepoError(f"{table} is append-only; UPDATE is forbidden")
        existing = self.get(table, pk_value)
        if existing is None:
            raise DisasterRepoError(f"{table} {pk_value} not found")
        merged = dict(existing)
        merged.update(patch)
        if "UpdatedAt" in disaster_schema.table(table).column_names():
            merged["UpdatedAt"] = _now()
        return self._repo.upsert(table, self.external_id(table, pk_value), merged)

    def soft_delete(self, table: str, pk_value: Any) -> dict[str, Any]:
        if table in _APPEND_ONLY:
            raise DisasterRepoError(f"{table} is append-only; DELETE is forbidden")
        cols = disaster_schema.table(table).column_names()
        if "DeletedAt" not in cols:
            raise DisasterRepoError(f"{table} has no soft-delete column")
        return self.update(table, pk_value, {"DeletedAt": _now()})

    # -- queries ------------------------------------------------------------
    def list(self, table: str, *, where: Optional[dict[str, Any]] = None,
             include_deleted: bool = False, limit: int = _MAX_SCAN) -> list[dict[str, Any]]:
        rows = self._repo.query(table, where=where, limit=limit)
        pk = disaster_schema.table(table).pk
        has_del = "DeletedAt" in disaster_schema.table(table).column_names()
        out = []
        for r in rows:
            if not include_deleted and has_del and r.get("DeletedAt"):
                continue
            out.append(r)
        out.sort(key=lambda r: int(r.get(pk) or 0))
        return out

    def find_one(self, table: str, where: dict[str, Any]) -> Optional[dict[str, Any]]:
        rows = self.list(table, where=where, limit=2)
        return rows[0] if rows else None

    def count(self, table: str, *, where: Optional[dict[str, Any]] = None) -> int:
        return len(self.list(table, where=where))

    def search(self, table: str, text: str, *, limit: int = 50) -> list[dict[str, Any]]:
        cols = list(disaster_schema.table(table).search_columns) or None
        return self._repo.search(table, text, columns=cols, limit=limit)

    # -- append-only activity ----------------------------------------------
    def append_activity(self, subject_type: str, subject_id: Any, actor: str,
                        action: str, *, diff: Optional[dict] = None,
                        request_id: Optional[str] = None) -> dict[str, Any]:
        """Write one append-only DisasterActivity row. Never updated/deleted."""
        from .. import audit  # reuse the detail sanitiser
        aid = self.next_id("DisasterActivity")
        row = {
            "DisasterActivityID": aid,
            "SubjectType": subject_type,
            "SubjectID": (str(subject_id) if subject_id is not None else None),
            "Actor": actor,
            "Action": action,
            "DiffJSON": audit.sanitize_detail(diff or {}),
            "RequestID": request_id,
            "CreatedAt": _now(),
        }
        return self._repo.upsert(
            "DisasterActivity", self.external_id("DisasterActivity", aid), row)

    def activity_for(self, subject_type: str, subject_id: Any, *,
                     limit: int = 500) -> list[dict[str, Any]]:
        rows = self._repo.query("DisasterActivity",
                                where={"SubjectType": subject_type,
                                       "SubjectID": str(subject_id)}, limit=_MAX_SCAN)
        rows.sort(key=lambda r: int(r.get("DisasterActivityID") or 0))
        return rows[:limit]

    def recent_activity(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._repo.query("DisasterActivity", limit=_MAX_SCAN)
        rows.sort(key=lambda r: int(r.get("DisasterActivityID") or 0), reverse=True)
        return rows[:limit]


# --- process-level singletons (dev persistence + deployed statelessness) ----
_singleton: Optional[DisasterRepo] = None
_singleton_lock = threading.Lock()
_cache_singleton = None


def disaster_repo() -> DisasterRepo:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = DisasterRepo()
    return _singleton


def disaster_cache():
    """Process-level cache singleton (get_cache() hands out a fresh in-memory
    fake each call, so disaster idempotency keys need a stable instance)."""
    global _cache_singleton
    if _cache_singleton is None:
        with _singleton_lock:
            if _cache_singleton is None:
                from ..cache import get_cache
                _cache_singleton = get_cache()
    return _cache_singleton


def reset_disaster_repo() -> None:
    """Test hook: drop the singletons (and their in-memory data) between tests."""
    global _singleton, _cache_singleton
    with _singleton_lock:
        _singleton = None
        _cache_singleton = None
