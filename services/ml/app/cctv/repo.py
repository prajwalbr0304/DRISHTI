"""CCTV persistence over Catalyst Data Store.

Thin CCTV-specific layer on top of the shared ``DataStoreRepository``
(datastore/repository.py), mirroring ``app/disaster/repo.py`` and
``app/board/repo.py``:

  * a PROCESS-LEVEL singleton repository (``get_repository()`` hands out a fresh
    in-memory fake per call, so camera/alert state would not survive between
    requests without this);
  * identity-PK allocation (the Data Store CRUD contract has no auto-increment)
    seeded from the current max and handed out monotonically under a lock;
  * stable ``ExternalID`` keys (``<prefix>:<pk>``) so writes are idempotent;
  * SOFT delete (retiring a camera is a logged state change, not a data loss);
  * APPEND-ONLY tables (``CctvDetection`` / ``CctvActivity``) — ``update`` and
    ``soft_delete`` raise for them everywhere, so a detection can never be
    rewritten after the fact to match a review decision.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..datastore import cctv_schema
from ..datastore.repository import (DataStoreRepository, InMemoryDataStore,
                                    get_repository)

_log = logging.getLogger(__name__)

_APPEND_ONLY = set(cctv_schema.append_only_tables())
_MAX_SCAN = 200_000

# Table probed to decide whether the CCTV tables exist in the target project.
_PROBE_TABLE = "Camera"


def _now() -> str:
    # Catalyst Data Store datetime columns require 'yyyy-MM-dd HH:mm:ss'; ISO8601
    # with 'T'/timezone is rejected. Store the naive-UTC wall clock in that format.
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class CctvRepoError(Exception):
    pass


def _select_store() -> DataStoreRepository:
    """Choose the backing store for the CCTV tables, preferring Catalyst Data Store.

    These tables are Data Store-native, but a Catalyst Data Store table can ONLY be
    created from the Console — there is no SDK/API/CLI path for it (see
    ``infra/catalyst/ds-schema/generate_console_guide.py``). When they have not been
    provisioned in the target project, every CCTV read raises ``No such Table`` and
    the entire watch wall reports a bare 500 instead of a diagnosable state.

    The CCTV surface is ENTIRELY synthetic demo data — a deterministic camera estate
    plus whatever the replay detector proposes — so an unprovisioned project falls
    back to the in-process store (and seeds it, see ``_ensure_demo_estate``) rather
    than leaving the feature dead. Two things make that sound here rather than a
    papering-over:

      * AppSail is pinned to ONE instance with a single Uvicorn worker
        (``infra/catalyst/appsail/appsail.deploy.json`` — ``PINNED_SINGLE_INSTANCE``),
        which the disaster/board modules already rely on for in-process id
        allocation, so one process-level store is consistent for every request;
      * the estate is deterministic, so a cold start rebuilds an identical wall.

    What it costs is honest to state: rows live only for the life of the process, so
    a redeploy or instance restart resets review state. Data Store stays PREFERRED —
    create the six tables in the Console and the next start picks them up with no
    code change.
    """
    try:
        store = get_repository()
    except Exception as exc:  # noqa: BLE001 — misconfigured creds must not kill the wall
        _log.warning("CCTV: Data Store repository unavailable (%s: %s) — using the "
                     "in-process store for the synthetic estate.",
                     type(exc).__name__, exc)
        return InMemoryDataStore()
    if isinstance(store, InMemoryDataStore):
        return store
    try:
        store.query(_PROBE_TABLE, limit=1)
        return store
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "CCTV: Data Store table %r is not provisioned in this project (%s: %s). "
            "Falling back to the in-process store and seeding the synthetic demo "
            "estate. Create the CCTV tables in the Catalyst Console to persist "
            "them across restarts.", _PROBE_TABLE, type(exc).__name__, exc)
        return InMemoryDataStore()


class CctvRepo:
    """CCTV-scoped persistence facade over a single DataStoreRepository."""

    def __init__(self, repo: Optional[DataStoreRepository] = None):
        self._repo = repo if repo is not None else _select_store()
        self._lock = threading.RLock()
        self._counters: dict[str, int] = {}

    @property
    def store(self) -> DataStoreRepository:
        return self._repo

    @property
    def is_ephemeral(self) -> bool:
        """True when rows live only in THIS process (demo fallback / local dev),
        so callers know the estate has to be seeded on every cold start."""
        return isinstance(self._repo, InMemoryDataStore)

    # -- id allocation ------------------------------------------------------
    def _seed_counter(self, table: str) -> int:
        pk = cctv_schema.table(table).pk
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
        return f"{cctv_schema.table(table).external_id_prefix}:{pk_value}"

    # -- core CRUD ----------------------------------------------------------
    def create(self, table: str, fields: dict[str, Any], *,
               pk_value: Optional[int] = None) -> dict[str, Any]:
        t = cctv_schema.table(table)
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
            raise CctvRepoError(f"{table} is append-only; UPDATE is forbidden")
        existing = self.get(table, pk_value)
        if existing is None:
            raise CctvRepoError(f"{table} {pk_value} not found")
        merged = dict(existing)
        merged.update(patch)
        if "UpdatedAt" in cctv_schema.table(table).column_names():
            merged["UpdatedAt"] = _now()
        return self._repo.upsert(table, self.external_id(table, pk_value), merged)

    def soft_delete(self, table: str, pk_value: Any) -> dict[str, Any]:
        if table in _APPEND_ONLY:
            raise CctvRepoError(f"{table} is append-only; DELETE is forbidden")
        cols = cctv_schema.table(table).column_names()
        if "DeletedAt" not in cols:
            raise CctvRepoError(f"{table} has no soft-delete column")
        return self.update(table, pk_value, {"DeletedAt": _now()})

    # -- queries ------------------------------------------------------------
    def list(self, table: str, *, where: Optional[dict[str, Any]] = None,
             include_deleted: bool = False, limit: int = _MAX_SCAN) -> list[dict[str, Any]]:
        rows = self._repo.query(table, where=where, limit=limit)
        pk = cctv_schema.table(table).pk
        has_del = "DeletedAt" in cctv_schema.table(table).column_names()
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
        cols = list(cctv_schema.table(table).search_columns) or None
        return self._repo.search(table, text, columns=cols, limit=limit)

    # -- append-only activity ----------------------------------------------
    def append_activity(self, subject_type: str, subject_id: Any, actor: str,
                        action: str, *, diff: Optional[dict] = None,
                        request_id: Optional[str] = None) -> dict[str, Any]:
        """Write one append-only CctvActivity row. Never updated/deleted."""
        from .. import audit  # reuse the detail sanitiser
        aid = self.next_id("CctvActivity")
        row = {
            "CctvActivityID": aid,
            "SubjectType": subject_type,
            "SubjectID": (str(subject_id) if subject_id is not None else None),
            "Actor": actor,
            "Action": action,
            "DiffJSON": audit.sanitize_detail(diff or {}),
            "RequestID": request_id,
            "CreatedAt": _now(),
        }
        return self._repo.upsert(
            "CctvActivity", self.external_id("CctvActivity", aid), row)

    def activity_for(self, subject_type: str, subject_id: Any, *,
                     limit: int = 500) -> list[dict[str, Any]]:
        rows = self._repo.query("CctvActivity",
                                where={"SubjectType": subject_type,
                                       "SubjectID": str(subject_id)}, limit=_MAX_SCAN)
        rows.sort(key=lambda r: int(r.get("CctvActivityID") or 0))
        return rows[:limit]

    def recent_activity(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._repo.query("CctvActivity", limit=_MAX_SCAN)
        rows.sort(key=lambda r: int(r.get("CctvActivityID") or 0), reverse=True)
        return rows[:limit]


# --- process-level singletons (dev persistence + deployed statelessness) ----
_singleton: Optional[CctvRepo] = None
_singleton_lock = threading.Lock()
_cache_singleton = None
_estate_ready = False
_estate_lock = threading.Lock()


def cctv_repo() -> CctvRepo:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = CctvRepo()
    # Deliberately OUTSIDE the singleton lock: seeding calls back into the repo,
    # and _singleton_lock is a plain (non-reentrant) Lock.
    _ensure_demo_estate(_singleton)
    return _singleton


def _ensure_demo_estate(repo: CctvRepo) -> None:
    """Seed the deterministic synthetic estate once, when rows are process-local.

    Without this an ephemeral store comes up EMPTY on every cold start and the wall
    is blank until an operator with ``cctv_admin`` presses "Seed camera estate" —
    which is exactly the wrong thing to discover mid-demo.

    Only runs for the ephemeral store. Against a provisioned Data Store the estate
    is already persisted, and re-seeding would be ~50 needless REST writes on the
    first request after every boot.
    """
    global _estate_ready
    if _estate_ready or not repo.is_ephemeral:
        return
    with _estate_lock:
        if _estate_ready:
            return
        # Set BEFORE seeding: a failed seed must degrade to an empty wall, not
        # retry ~50 writes on every subsequent request.
        _estate_ready = True
        try:
            from .seed import seed_demo_estate
            counts = seed_demo_estate(repo=repo, actor="system.autoseed")
            _log.info("CCTV: seeded ephemeral demo estate (%s cameras, %s responders, "
                      "%s with footage).", counts.get("Camera"),
                      counts.get("PatrolUnit"), counts.get("CamerasWithFootage"))
        except Exception:  # noqa: BLE001 — an unseeded wall beats a 500 on every read
            _log.exception("CCTV: demo estate auto-seed failed")


def cctv_cache():
    """Process-level cache singleton (get_cache() hands out a fresh in-memory fake
    each call, so CCTV idempotency keys need a stable instance)."""
    global _cache_singleton
    if _cache_singleton is None:
        with _singleton_lock:
            if _cache_singleton is None:
                from ..cache import get_cache
                _cache_singleton = get_cache()
    return _cache_singleton


def reset_cctv_repo() -> None:
    """Test hook: drop the singletons (and their in-memory data) between tests."""
    global _singleton, _cache_singleton, _estate_ready
    with _singleton_lock:
        _singleton = None
        _cache_singleton = None
    with _estate_lock:
        # The auto-seed guard belongs to the singleton it seeded, so the next
        # cctv_repo() behaves like a real cold start. A test that needs an EMPTY
        # estate should build CctvRepo(InMemoryDataStore()) directly instead.
        _estate_ready = False
