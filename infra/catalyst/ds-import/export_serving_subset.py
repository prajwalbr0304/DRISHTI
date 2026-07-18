#!/usr/bin/env python3
"""Export a curated AWS PostgreSQL serving subset -> serving-export JSONL (Prompt 14 E.4/E.5).

This is the READ-ONLY, one-way bootstrap export half of
`bootstrap-catalyst-serving-data`. It reads the retained AWS RDS serving schema
and writes the curated subset the offline importer / `catalyst ds:import` consume:

  * a bounded, reproducible set of CASES (golden seed IDs first, then a
    deterministic fill up to --target-cases, never exceeding the Data Store dev
    cap of 5,000 rows/table);
  * every imported table that carries a ``CaseMasterID`` column is FK-scoped to
    that case set (referentially-linked children), auto-detected from the schema;
  * reference / geography / governance / lookup tables are exported capped and
    whole (small; needed for dashboards, filters, predictions);
  * excluded/sensitive columns (raw identifiers, raw account no, restricted text,
    raw prompt, raw audit payload) are dropped; a stable ``ExternalID`` is added;
  * synthetic-data labels, timestamps and lineage columns are preserved as-is.

It NEVER writes to the source (read-only transaction), NEVER prints secrets (the
DB target is masked), and NEVER exports protected attributes or credentials
(those tables are NOT_IMPORTED in the mapping, so they are not in the manifest).

Output: one ``serving-export/<SourceTable>.export.jsonl`` per table + a
``serving-export/_export-report.json`` with per-table source/exported/rejected
counts, dropped columns and a content SHA-256 (the reconciliation evidence).

Primary (held; live RDS + credit-neutral read):
    python export_serving_subset.py --all --target-cases 2000
Single table:
    python export_serving_subset.py --source-table CaseMaster --target-cases 2000
Offline transform self-test (no DB): import the pure helpers (see the Part E report).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ML_ROOT = REPO_ROOT / "services" / "ml"
MANIFEST = HERE / "import-manifest.json"
OUT_DIR = HERE / "serving-export"

# Consistent FK/pk column names used to build a referentially-linked subset.
CASE_FK_COLUMN = "CaseMasterID"
PERSON_FK_COLUMN = "CanonicalPersonID"
ORG_FK_COLUMN = "CanonicalOrganisationID"
CASE_SOURCE_TABLE = "CaseMaster"
PERSON_SOURCE_TABLE = "CanonicalPerson"
ORG_SOURCE_TABLE = "CanonicalOrganisation"


# --- manifest ---------------------------------------------------------------
def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def manifest_by_source(manifest: dict) -> dict[str, dict]:
    return {t["source_table"]: t for t in manifest["tables"]}


# --- pure transform helpers (unit-testable without a DB) --------------------
def external_id(prefix: str, row: dict[str, Any], pk_columns: list[str]) -> Optional[str]:
    if any(c not in row or row[c] in (None, "") for c in pk_columns):
        return None
    return f"{prefix}:{'-'.join(str(row[c]) for c in pk_columns)}"


def transform_rows(meta: dict, source_rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Drop excluded columns, add ExternalID, reject rows with an incomplete PK.

    Returns (exported, rejected). Never mutates the source rows. Order preserved
    so the content hash is reproducible for the rebuild contract."""
    excluded = set(meta.get("excluded_columns", []))
    pk = meta["pk_columns"]
    prefix = meta["external_id_prefix"]
    exported: list[dict] = []
    rejected: list[dict] = []
    for row in source_rows:
        ext = external_id(prefix, row, pk)
        if ext is None:
            rejected.append({"reason": "incomplete_pk", "pk": pk})
            continue
        clean = {k: v for k, v in row.items() if k not in excluded}
        clean["ExternalID"] = ext
        exported.append(clean)
    return exported, rejected


def _json_default(o: Any) -> str:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (bytes, memoryview)):
        return "<binary>"
    return str(o)


def content_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(r, sort_keys=True, separators=(",", ":"),
                            default=_json_default).encode())
    return h.hexdigest()


def mask_db_target(url: str) -> str:
    """kind:host/db — no user, no password, never the full URL."""
    if not url:
        return "<no DATABASE_URL>"
    try:
        from urllib.parse import urlsplit
        u = urlsplit(url)
        host = u.hostname or "?"
        db = (u.path or "/").lstrip("/") or "?"
        kind = ("supabase" if "supabase" in host
                else "aws-rds" if "rds.amazonaws.com" in host else "other")
        return f"{kind}:{host}/{db}"
    except Exception:  # noqa: BLE001
        return "<unparseable>"


# --- read-only DB access (isolated so the transform stays testable) ---------
def _settings():
    if str(ML_ROOT) not in sys.path:
        sys.path.insert(0, str(ML_ROOT))
    from app.config import get_settings  # lightweight; no DB import
    return get_settings()


def ro_connect():
    """A strictly READ-ONLY connection (no SET ROLE, so it works whether or not
    the restricted role exists). Any DML is impossible on a read-only session."""
    import psycopg2
    s = _settings()
    if not s.database_url:
        raise RuntimeError("DATABASE_URL not set; cannot export from AWS RDS.")
    conn = psycopg2.connect(s.database_url, connect_timeout=s.db_connect_timeout)
    conn.set_session(readonly=True, autocommit=False)
    return conn


def fetch_dicts(conn, sql: str, params: tuple = ()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def table_columns(conn, source_table: str) -> set[str]:
    rows = fetch_dicts(
        conn,
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (source_table,))
    return {r["column_name"] for r in rows}


def classify_scope(source_table: str, cols: set[str]) -> str:
    """How this table is scoped into the linked subset (auto-detected from its
    columns): case-scoped (has CaseMasterID), person/org entity-scoped (has the
    canonical FK / is the canonical table), else capped whole."""
    if source_table == CASE_SOURCE_TABLE or CASE_FK_COLUMN in cols:
        return "case"
    if source_table == PERSON_SOURCE_TABLE or PERSON_FK_COLUMN in cols:
        return "person"
    if source_table == ORG_SOURCE_TABLE or ORG_FK_COLUMN in cols:
        return "org"
    return "capped"


def select_case_seed(conn, target_cases: int, seed_ids: list[int]) -> list[int]:
    """Golden seed IDs first, then a deterministic fill (ORDER BY pk) up to
    target_cases — reproducible so the serving subset rebuild is stable."""
    ids: list[int] = []
    seen: set[int] = set()
    for sid in seed_ids:
        if sid not in seen:
            ids.append(sid)
            seen.add(sid)
    if len(ids) < target_cases:
        rows = fetch_dicts(
            conn,
            'SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT %s',
            (target_cases,))
        for r in rows:
            cid = r["CaseMasterID"]
            if cid not in seen:
                ids.append(cid)
                seen.add(cid)
            if len(ids) >= target_cases:
                break
    return ids[:target_cases]


def fetch_scoped(conn, source_table: str, cap: int, col: Optional[str], ids) -> list[dict]:
    """Read one table read-only, scoped to an id set via ``col = ANY(ids)`` when
    given, else capped whole. An empty id set falls back to capped whole (so a
    single-table export without a prior pass still returns rows)."""
    if not col or not ids:
        return fetch_dicts(conn, f'SELECT * FROM "{source_table}" LIMIT {int(cap)}')
    return fetch_dicts(
        conn, f'SELECT * FROM "{source_table}" WHERE "{col}" = ANY(%s) LIMIT {int(cap)}',
        (list(ids),))


# --- export orchestration ---------------------------------------------------
def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":"), default=_json_default))
            f.write("\n")


def _csv_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"), default=_json_default)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return "<binary>"
    return str(v)


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write the ds:import CSV (ExternalID column first). Complex values are
    JSON-encoded so the CSV stays flat and re-importable."""
    if not rows:
        path.write_text("ExternalID\n", encoding="utf-8")
        return
    keys: set[str] = set()
    for r in rows:
        keys.update(r.keys())
    header = ["ExternalID"] + sorted(k for k in keys if k != "ExternalID")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_value(r.get(k)) for k in header})


def run_export(source_tables: list[str], target_cases: int, seed_ids: list[int]) -> dict:
    manifest = load_manifest()
    by_source = manifest_by_source(manifest)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = ro_connect()
    report: dict[str, Any] = {
        "mapping_version": manifest.get("mapping_version"),
        "dev_row_cap": manifest.get("dev_row_cap"),
        "db_target": mask_db_target(_settings().database_url),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "target_cases": target_cases,
        "tables": [],
    }
    try:
        # 1. resolve the reproducible case seed set once.
        case_ids = select_case_seed(conn, target_cases, seed_ids)
        report["case_seed_count"] = len(case_ids)

        # 2. classify each requested table's scope from its columns, then export
        #    in dependency order: case-scoped first (collecting the person/org
        #    ids they reference), then those entity tables, then capped tables.
        kind_by_src = {src: classify_scope(src, table_columns(conn, src)) for src in source_tables}
        person_ids: set = set()
        org_ids: set = set()
        pass_order = {"case": 0, "person": 1, "org": 2, "capped": 3}

        for src in sorted(source_tables, key=lambda s: pass_order[kind_by_src[s]]):
            meta = by_source[src]
            cap = int(meta.get("dev_row_cap", 5000))
            kind = kind_by_src[src]
            if kind == "case":
                raw = fetch_scoped(conn, src, cap, CASE_FK_COLUMN, case_ids)
                # collect the canonical entities these linked rows reference.
                for r in raw:
                    pv = r.get(PERSON_FK_COLUMN)
                    ov = r.get(ORG_FK_COLUMN)
                    if pv not in (None, ""):
                        person_ids.add(pv)
                    if ov not in (None, ""):
                        org_ids.add(ov)
            elif kind == "person":
                raw = fetch_scoped(conn, src, cap, PERSON_FK_COLUMN, person_ids)
            elif kind == "org":
                raw = fetch_scoped(conn, src, cap, ORG_FK_COLUMN, org_ids)
            else:
                raw = fetch_scoped(conn, src, cap, None, None)

            exported, rejected = transform_rows(meta, raw)
            jsonl_path = OUT_DIR / f"{src}.export.jsonl"
            csv_path = OUT_DIR / f"{src}.csv"
            write_jsonl(jsonl_path, exported)          # offline importer + reconcile
            write_csv(csv_path, exported)              # catalyst ds:import (CSV + ExternalID)
            report["tables"].append({
                "source_table": src,
                "datastore_table": meta["datastore_table"],
                "disposition": meta["disposition"],
                "scope": kind,
                "source_rows": len(raw),
                "exported": len(exported),
                "rejected": len(rejected),
                "dropped_columns": meta.get("excluded_columns", []),
                "content_sha256": content_hash(exported),
                "jsonl_file": str(jsonl_path.relative_to(REPO_ROOT)),
                "csv_file": str(csv_path.relative_to(REPO_ROOT)),
            })
        report["entity_seed"] = {"persons": len(person_ids), "organisations": len(org_ids)}
    finally:
        conn.rollback()
        conn.close()

    (OUT_DIR / "_export-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only curated AWS -> serving-export.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--source-table", help="export a single manifest table")
    g.add_argument("--all", action="store_true", help="export every imported table")
    ap.add_argument("--target-cases", type=int, default=2000,
                    help="bound for the case seed set (<= dev cap 5000)")
    ap.add_argument("--seed-cases", help="optional file of golden CaseMasterIDs (one per line)")
    args = ap.parse_args()

    manifest = load_manifest()
    by_source = manifest_by_source(manifest)
    if args.source_table:
        if args.source_table not in by_source:
            print(f"unknown table {args.source_table!r} (not an imported manifest table)")
            return 2
        tables = [args.source_table]
    else:
        tables = [t["source_table"] for t in manifest["tables"]]

    seed_ids: list[int] = []
    if args.seed_cases and Path(args.seed_cases).exists():
        for line in Path(args.seed_cases).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.isdigit():
                seed_ids.append(int(line))

    target = min(max(1, args.target_cases), int(manifest.get("dev_row_cap", 5000)))
    report = run_export(tables, target, seed_ids)
    # Redacted summary (no secrets, no row content).
    print(json.dumps({
        "db_target": report["db_target"],
        "mapping_version": report["mapping_version"],
        "case_seed_count": report.get("case_seed_count"),
        "tables_exported": len(report["tables"]),
        "total_rows": sum(t["exported"] for t in report["tables"]),
        "report": str((OUT_DIR / "_export-report.json").relative_to(REPO_ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
