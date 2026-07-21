"""Seed the Catalyst Data Store operational repository from the curated
serving-export subset (Prompt 21 §B / §D.4).

The deployed AppSail runs WITHOUT ``DATABASE_URL``; its operational reference/read
data comes from Catalyst Data Store, imported from the reviewed serving subset in
``infra/catalyst/ds-import/serving-export/*.export.jsonl`` (produced by
``export_serving_subset.py``, keyed by the same ExternalIDs as the AWS mirror).

Offline (tests / local), the same JSONL seeds an in-memory Data Store so the
operational read journeys work with no database. This module is the single
loader used by both paths; it is idempotent (upsert by ExternalID).
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from ..datapaths import repo_data_path
from .repository import DataStoreRepository, InMemoryDataStore

# The serving-export dir exists in the repo checkout at
# infra/catalyst/ds-import/serving-export; it is ABSENT in the minimal AppSail
# image (only app/ + sql/ are copied), where repo_data_path returns None and the
# loaders below degrade to empty. The deployed reference source is the real
# Catalyst Data Store (imported via infra/catalyst/ds-import), not this dir.
_EXPORT_DIR = repo_data_path("infra", "catalyst", "ds-import", "serving-export")

# Operational reference tables the deployed read journeys need without RDS.
# Names match the serving-export files (source table == Data Store table for
# these reference/lookup tables).
REFERENCE_TABLES = (
    "CaseCategory", "District", "Unit", "UnitType", "GravityOffence",
    "CrimeHead", "CrimeSubHead", "CaseStatusMaster", "Act", "Section",
    "Employee", "CaseCategoryWorkflow", "Rank", "Designation",
    "ImportTemplate", "ImportTemplateVersion",
)


def export_path(table: str) -> Optional[Path]:
    return (_EXPORT_DIR / f"{table}.export.jsonl") if _EXPORT_DIR else None


def load_export(table: str) -> list[dict]:
    """Read a serving-export JSONL file into a list of row dicts (empty if absent
    or when the repo data tree is not present, e.g. the minimal AppSail image)."""
    p = export_path(table)
    if not p or not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def seed_repository(repo: DataStoreRepository,
                    tables: Optional[Iterable[str]] = None) -> dict[str, int]:
    """Idempotently upsert the serving-export rows for ``tables`` into ``repo``.
    Returns {table: rows_seeded}. Rows without an ExternalID are skipped."""
    counts: dict[str, int] = {}
    for table in (tables or REFERENCE_TABLES):
        n = 0
        for row in load_export(table):
            ext = row.get("ExternalID")
            if not ext:
                continue
            repo.upsert(table, str(ext), row)
            n += 1
        counts[table] = n
    return counts


# Larger operational data tables seeded on demand (kept out of the always-loaded
# reference set so a process only pays for them when a financial view is served).
FINANCIAL_TABLES = ("FinancialAccount", "FinancialTransaction")

# --- process-level seeded repos (offline / deployed read fallback) ----------
_ref_repo: Optional[DataStoreRepository] = None
_fin_repo: Optional[DataStoreRepository] = None
_lock = threading.Lock()


def reference_repo() -> DataStoreRepository:
    """A process-singleton in-memory Data Store seeded from the serving-export
    reference subset. Used as the operational reference source when no RDS
    ``DATABASE_URL`` is configured (deployed AppSail / offline tests)."""
    global _ref_repo
    if _ref_repo is None:
        with _lock:
            if _ref_repo is None:
                r = InMemoryDataStore()
                seed_repository(r)
                _ref_repo = r
    return _ref_repo


def financial_repo() -> DataStoreRepository:
    """A process-singleton in-memory Data Store seeded from the financial serving
    subset (accounts + transactions), used for the operational financial views
    when no RDS DATABASE_URL is configured. Seeded on first use only."""
    global _fin_repo
    if _fin_repo is None:
        with _lock:
            if _fin_repo is None:
                r = InMemoryDataStore()
                seed_repository(r, FINANCIAL_TABLES)
                _fin_repo = r
    return _fin_repo


def reset_reference_repo() -> None:
    """Test hook: drop the seeded singletons so the next call reseeds."""
    global _ref_repo, _fin_repo
    with _lock:
        _ref_repo = None
        _fin_repo = None


@lru_cache(maxsize=1)
def available_reference_tables() -> tuple[str, ...]:
    """Reference tables that actually have exported rows (non-empty)."""
    return tuple(t for t in REFERENCE_TABLES if load_export(t))
