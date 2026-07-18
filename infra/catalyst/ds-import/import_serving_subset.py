#!/usr/bin/env python3
"""Offline / CI alternative to `catalyst ds:import` (Phase 14 workflow §2).

The PRIMARY deployed import path is the real CLI:
    catalyst ds:import <ServingTable.csv> --config configs/<SourceTable>.import.json
(`operation:upsert`, `find_by:ExternalID`). This script is the OFFLINE equivalent
for local/CI use where Stratus CSV upload is not available: it reads a
serving-export JSONL, computes ExternalID from the manifest metadata, drops
excluded (sensitive) columns, enforces the dev row cap, and upserts BY ExternalID
via `CatalystDataStoreRepository.bulk_upsert` (same idempotency contract). One-way
bootstrap only (AWS -> Data Store); never a two-way sync. No credentials/PII.

Repository selection (services/ml/app/datastore/repository.py):
  * default -> InMemoryDataStore (safe dry-run / CI).
  * DRISHTI_USE_CATALYST_DATASTORE=true -> CatalystDataStoreRepository (SDK).

Run (dry-run, in-memory):
    python infra/catalyst/ds-import/import_serving_subset.py \
        --source-table CaseMaster \
        --export serving-export/CaseMaster.export.jsonl
Add --commit to write through the selected repository.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ML_APP = REPO_ROOT / "services" / "ml" / "app"
MANIFEST = HERE / "import-manifest.json"


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_repo_module():
    # repository.py is stdlib-only at import time (SDK import deferred).
    return _load("drishti_ds_repo", ML_APP / "datastore" / "repository.py")


def manifest_entry(source_table: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for t in manifest["tables"]:
        if t["source_table"] == source_table:
            return t
    raise KeyError(f"{source_table} not found in {MANIFEST.name} (run generate_import_configs.py)")


def external_id(prefix: str, row: dict[str, Any], pk_columns: list[str]) -> str:
    return f"{prefix}:{'-'.join(str(row[c]) for c in pk_columns)}"


def prepare_rows(meta: dict, source_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    rejected: list[dict] = []
    cap = int(meta.get("dev_row_cap", 5000))
    pk = meta["pk_columns"]
    excluded = set(meta.get("excluded_columns", []))
    for row in source_rows:
        if any(c not in row or row[c] in (None, "") for c in pk):
            rejected.append({"reason": "missing_pk", "row": row})
            continue
        clean = {k: v for k, v in row.items() if k not in excluded}
        clean["ExternalID"] = external_id(meta["external_id_prefix"], row, pk)
        accepted.append(clean)
        if len(accepted) >= cap:
            break
    return accepted, rejected


def content_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(r, sort_keys=True, separators=(",", ":"), default=str).encode())
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline idempotent Data Store serving-subset import.")
    ap.add_argument("--source-table", required=True, help="AWS source table name (manifest key)")
    ap.add_argument("--export", required=True, help="path to serving-export JSONL")
    ap.add_argument("--commit", action="store_true", help="write via repository (else dry-run)")
    args = ap.parse_args()

    meta = manifest_entry(args.source_table)
    export_path = Path(args.export)
    if not export_path.exists():
        print(f"export not found: {export_path} (nothing to import)")
        return 2

    source_rows = load_jsonl(export_path)
    accepted, rejected = prepare_rows(meta, source_rows)
    digest = content_hash(accepted)

    summary = {
        "source_table": meta["source_table"],
        "datastore_table": meta["datastore_table"],
        "mapping_version": meta.get("mapping_version"),
        "source_rows": len(source_rows),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "capped_at": meta.get("dev_row_cap"),
        "find_by": "ExternalID",
        "operation": "upsert",
        "content_sha256": digest,
        "committed": False,
    }

    if args.commit:
        repo = _load_repo_module().get_repository()
        summary["committed"] = True
        summary["repository"] = type(repo).__name__
        summary["upsert_counts"] = repo.bulk_upsert(meta["datastore_table"], accepted)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
