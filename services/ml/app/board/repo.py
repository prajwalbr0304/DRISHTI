"""Board persistence over Catalyst Data Store (Prompt 16 §A/§C).

Thin, board-specific layer on top of the shared ``DataStoreRepository``
(datastore/repository.py). It provides what the generic CRUD contract lacks for
the board:

  * a PROCESS-LEVEL singleton repository (``get_repository()`` returns a fresh
    in-memory fake each call, so board state would not survive between requests
    without this);
  * identity-PK allocation (the Data Store CRUD contract has no auto-increment)
    seeded from the current max and handed out monotonically under a lock —
    ``BoardActivityID`` is therefore monotonic, which reconnect/replay relies on;
  * stable ``ExternalID`` keys (``<prefix>:<pk>``) so writes are idempotent;
  * SOFT delete (the contract has no hard delete; a delete is a logged state
    change, which suits a chain-of-custody tool);
  * APPEND-ONLY ``BoardActivity`` — ``update``/``delete`` raise for it, in every
    code path.

Board records are the authoritative source of truth; NoSQL/Cache hold only
reconstructable layout/presence (see nosql.py / cache.py).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..datastore import board_schema
from ..datastore.repository import DataStoreRepository, get_repository

_APPEND_ONLY = set(board_schema.append_only_tables())
_MAX_SCAN = 100_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BoardRepoError(Exception):
    pass


class BoardRepo:
    """Board-scoped persistence facade over a single DataStoreRepository."""

    def __init__(self, repo: Optional[DataStoreRepository] = None):
        self._repo = repo or get_repository()
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    # -- id allocation ------------------------------------------------------
    def _seed_counter(self, table: str) -> int:
        pk = board_schema.table(table).pk
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

    def external_id(self, table: str, pk_value: Any) -> str:
        return f"{board_schema.table(table).external_id_prefix}:{pk_value}"

    # -- core CRUD ----------------------------------------------------------
    def create(self, table: str, fields: dict[str, Any]) -> dict[str, Any]:
        t = board_schema.table(table)
        pk_val = self.next_id(table)
        row = dict(fields)
        row[t.pk] = pk_val
        row.setdefault("CreatedAt", _now())
        if "UpdatedAt" in t.column_names():
            row.setdefault("UpdatedAt", row.get("CreatedAt"))
        return self._repo.upsert(table, self.external_id(table, pk_val), row)

    def get(self, table: str, pk_value: Any) -> Optional[dict[str, Any]]:
        return self._repo.get(table, self.external_id(table, pk_value))

    def update(self, table: str, pk_value: Any, patch: dict[str, Any]) -> dict[str, Any]:
        if table in _APPEND_ONLY:
            raise BoardRepoError(f"{table} is append-only; UPDATE is forbidden")
        existing = self.get(table, pk_value)
        if existing is None:
            raise BoardRepoError(f"{table} {pk_value} not found")
        merged = dict(existing)
        merged.update(patch)
        if "UpdatedAt" in board_schema.table(table).column_names():
            merged["UpdatedAt"] = _now()
        return self._repo.upsert(table, self.external_id(table, pk_value), merged)

    def soft_delete(self, table: str, pk_value: Any) -> dict[str, Any]:
        if table in _APPEND_ONLY:
            raise BoardRepoError(f"{table} is append-only; DELETE is forbidden")
        cols = board_schema.table(table).column_names()
        if "DeletedAt" not in cols:
            raise BoardRepoError(f"{table} has no soft-delete column")
        return self.update(table, pk_value, {"DeletedAt": _now()})

    # -- queries ------------------------------------------------------------
    def list_by_board(self, table: str, board_id: int, *,
                      include_deleted: bool = False,
                      limit: int = _MAX_SCAN) -> list[dict[str, Any]]:
        rows = self._repo.query(table, where={"BoardID": board_id}, limit=limit)
        pk = board_schema.table(table).pk
        has_del = "DeletedAt" in board_schema.table(table).column_names()
        out = []
        for r in rows:
            if not include_deleted and has_del and r.get("DeletedAt"):
                continue
            out.append(r)
        out.sort(key=lambda r: int(r.get(pk) or 0))
        return out

    def list_boards_for_owner(self, owner_actor: str, *, limit: int = _MAX_SCAN) -> list[dict]:
        rows = self._repo.query("InvestigationBoard",
                                where={"OwnerActor": owner_actor}, limit=limit)
        return sorted(rows, key=lambda r: int(r.get("BoardID") or 0))

    def all_boards(self, *, limit: int = _MAX_SCAN) -> list[dict]:
        return sorted(self._repo.query("InvestigationBoard", limit=limit),
                      key=lambda r: int(r.get("BoardID") or 0))

    def references_to(self, ref_table: str, ref_id: str, *, limit: int = _MAX_SCAN) -> list[dict]:
        """Reverse lookup: which board nodes reference this canonical object."""
        rows = self._repo.query("BoardNode",
                                where={"RefTable": ref_table, "RefID": str(ref_id)},
                                limit=limit)
        return [r for r in rows if not r.get("DeletedAt")]

    # -- append-only activity ----------------------------------------------
    def append_activity(self, board_id: int, actor: str, action: str, *,
                        target_type: Optional[str] = None,
                        target_id: Optional[Any] = None,
                        diff: Optional[dict] = None,
                        request_id: Optional[str] = None) -> dict[str, Any]:
        """Write one append-only BoardActivity row. Never updated/deleted."""
        aid = self.next_id("BoardActivity")
        from .. import audit  # local import: reuse the detail sanitiser
        row = {
            "BoardActivityID": aid,
            "BoardID": board_id,
            "Actor": actor,
            "Action": action,
            "TargetType": target_type,
            "TargetID": (str(target_id) if target_id is not None else None),
            "DiffJSON": audit.sanitize_detail(diff or {}),
            "RequestID": request_id,
            "CreatedAt": _now(),
        }
        return self._repo.upsert("BoardActivity", self.external_id("BoardActivity", aid), row)

    def activity_after(self, board_id: int, after_id: int = 0, *,
                       limit: int = 500) -> list[dict[str, Any]]:
        rows = self._repo.query("BoardActivity", where={"BoardID": board_id},
                                limit=_MAX_SCAN)
        rows = [r for r in rows if int(r.get("BoardActivityID") or 0) > after_id]
        rows.sort(key=lambda r: int(r.get("BoardActivityID") or 0))
        return rows[:limit]

    def latest_activity_id(self, board_id: int) -> int:
        rows = self._repo.query("BoardActivity", where={"BoardID": board_id}, limit=_MAX_SCAN)
        return max((int(r.get("BoardActivityID") or 0) for r in rows), default=0)


# --- process-level singletons (dev persistence + deployed statelessness) ----
_singleton: Optional[BoardRepo] = None
_singleton_lock = threading.Lock()
_cache_singleton = None


def board_repo() -> BoardRepo:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = BoardRepo()
    return _singleton


def board_cache():
    """Process-level cache singleton (get_cache() hands out a fresh in-memory fake
    each call, so board idempotency/export metadata need a stable instance)."""
    global _cache_singleton
    if _cache_singleton is None:
        with _singleton_lock:
            if _cache_singleton is None:
                from ..cache import get_cache
                _cache_singleton = get_cache()
    return _cache_singleton


def reset_board_repo() -> None:
    """Test hook: drop the singletons (and their in-memory data) between tests."""
    global _singleton, _cache_singleton
    with _singleton_lock:
        _singleton = None
        _cache_singleton = None
