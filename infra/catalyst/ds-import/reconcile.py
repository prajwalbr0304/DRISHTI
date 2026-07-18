#!/usr/bin/env python3
"""Serving-subset reconciliation + rebuild contract (Prompt 14 E.12).

Runs the scheduled count / hash / version reconciliation between the AWS source
export and the Catalyst Data Store serving layer, plus the referential
relationship checks item 5 requires. It is deterministic and read-only.

Checks (all computable from the export files alone):
  1. mapping_version — the export report, the manifest and the live mapping.py
     agree on MAPPING_VERSION (a serving-subset rebuild is reproducible).
  2. file integrity — each <Table>.export.jsonl line count == the count the
     export report recorded, and its recomputed content SHA-256 matches (drift /
     tamper detection; the basis of the repeatable rebuild).
  3. referential relationships —
       - every case-scoped row's CaseMasterID resolves to an exported Case
         (FK-scoping is validated, not assumed);
       - CasePartyRole.CanonicalPersonID / .CanonicalOrganisationID resolve to an
         exported CanonicalPerson / CanonicalOrganisation (dangling refs from the
         bounded person/org cap are counted, never hidden).
  4. dev cap — no table exceeds the Data Store development ceiling (5,000).

Optional target reconciliation (`--against-datastore`, held/credit path): counts
rows currently in Data Store per table via the repository and compares to the
exported source counts. Uses the in-memory fake unless
DRISHTI_USE_CATALYST_DATASTORE=true.

The rebuild contract: re-run `export_serving_subset.py` then re-import
(`ds:import` or `import_serving_subset.py`); upsert BY ExternalID makes it
idempotent, so a rebuild converges without duplicates. This is a ONE-WAY
AWS -> Data Store bootstrap; never a two-way sync, never last-write-wins.

Exit code is non-zero if any hard check fails (CI gate). Never prints secrets.
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
EXPORT_DIR = HERE / "serving-export"
EXPORT_REPORT = EXPORT_DIR / "_export-report.json"
DEV_CAP = 5000


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def content_hash(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(r, sort_keys=True, separators=(",", ":"), default=str).encode())
    return h.hexdigest()


def pk_value_set(rows: list[dict], pk_columns: list[str]) -> set[str]:
    """Set of the RAW pk join values (matches the tail of ExternalID)."""
    out: set[str] = set()
    for r in rows:
        if all(c in r and r[c] not in (None, "") for c in pk_columns):
            out.add("-".join(str(r[c]) for c in pk_columns))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Serving-subset reconciliation.")
    ap.add_argument("--against-datastore", action="store_true",
                    help="also count rows in the Data Store target (held/credit path)")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_source = {t["source_table"]: t for t in manifest["tables"]}
    mapping = _load("drishti_ds_mapping", ML_APP / "datastore" / "mapping.py")

    checks: list[dict[str, Any]] = []
    failures = 0

    def record(name: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        nonlocal failures
        checks.append({"check": name, "ok": ok, "detail": detail, "hard": hard})
        if hard and not ok:
            failures += 1

    # 1. mapping_version consistency
    live_v = mapping.MAPPING_VERSION
    man_v = manifest.get("mapping_version")
    record("mapping_version manifest==live", man_v == live_v, f"{man_v} vs {live_v}")
    export_report = json.loads(EXPORT_REPORT.read_text(encoding="utf-8")) if EXPORT_REPORT.exists() else None
    if export_report:
        record("mapping_version export==live", export_report.get("mapping_version") == live_v,
               f"{export_report.get('mapping_version')} vs {live_v}")
    else:
        record("export report present", False,
               f"no {EXPORT_REPORT.name}; run export_serving_subset.py first", hard=False)

    # Build the exported case + person + org PK sets for relationship checks.
    case_meta = by_source.get("CaseMaster")
    case_ids = pk_value_set(load_jsonl(EXPORT_DIR / "CaseMaster.export.jsonl"),
                            case_meta["pk_columns"]) if case_meta else set()
    person_ids = pk_value_set(load_jsonl(EXPORT_DIR / "CanonicalPerson.export.jsonl"),
                              ["CanonicalPersonID"])
    org_ids = pk_value_set(load_jsonl(EXPORT_DIR / "CanonicalOrganisation.export.jsonl"),
                           ["CanonicalOrganisationID"])

    per_table: list[dict[str, Any]] = []
    reported = {t["source_table"]: t for t in (export_report["tables"] if export_report else [])}

    for src, meta in by_source.items():
        path = EXPORT_DIR / f"{src}.export.jsonl"
        if not path.exists():
            continue
        rows = load_jsonl(path)
        n = len(rows)
        entry: dict[str, Any] = {"source_table": src, "exported": n}

        # 2. file integrity vs the export report
        if src in reported:
            rep = reported[src]
            record(f"{src}: count matches report", rep["exported"] == n,
                   f"{rep['exported']} vs {n}")
            record(f"{src}: content hash matches report",
                   rep["content_sha256"] == content_hash(rows), "", hard=False)

        # 4. dev cap
        record(f"{src}: within dev cap {DEV_CAP}", n <= DEV_CAP, f"{n} rows")

        # 3. referential relationships
        if src != "CaseMaster" and case_ids and rows and (CASE := "CaseMasterID") in rows[0]:
            orphans = sum(1 for r in rows if str(r.get(CASE)) not in case_ids and r.get(CASE) not in (None, ""))
            entry["case_orphans"] = orphans
            record(f"{src}: all CaseMasterID resolve to an exported Case", orphans == 0,
                   f"{orphans} orphan rows")
        if src == "CasePartyRole" and rows:
            dangling_p = sum(1 for r in rows
                             if r.get("CanonicalPersonID") not in (None, "")
                             and str(r["CanonicalPersonID"]) not in person_ids)
            dangling_o = sum(1 for r in rows
                             if r.get("CanonicalOrganisationID") not in (None, "")
                             and str(r["CanonicalOrganisationID"]) not in org_ids)
            entry["dangling_person_refs"] = dangling_p
            entry["dangling_org_refs"] = dangling_o
            # Soft: the bounded person/org cap can legitimately omit some parties;
            # surfaced (not hidden) so the operator can raise --target-cases/cap.
            record("CasePartyRole: person refs resolve", dangling_p == 0,
                   f"{dangling_p} dangling person refs", hard=False)
            record("CasePartyRole: org refs resolve", dangling_o == 0,
                   f"{dangling_o} dangling org refs", hard=False)

        per_table.append(entry)

    # Optional: compare to the Data Store target counts (held/credit path).
    target_counts: dict[str, int] = {}
    if args.against_datastore:
        repo = _load("drishti_ds_repo", ML_APP / "datastore" / "repository.py").get_repository()
        for entry in per_table:
            ds_table = by_source[entry["source_table"]]["datastore_table"]
            try:
                target_counts[ds_table] = len(repo.query(ds_table, limit=DEV_CAP + 1))
            except Exception as e:  # noqa: BLE001
                target_counts[ds_table] = -1
            record(f"{entry['source_table']}: target>=source",
                   target_counts[ds_table] >= entry["exported"],
                   f"target {target_counts[ds_table]} vs source {entry['exported']}", hard=False)

    report = {
        "mapping_version": live_v,
        "tables_reconciled": len(per_table),
        "hard_failures": failures,
        "checks": checks,
        "per_table": per_table,
        "target_counts": target_counts or None,
        "rebuild": "re-run export_serving_subset.py then import (ds:import / import_serving_subset.py); "
                   "upsert by ExternalID is idempotent. One-way AWS -> Data Store only.",
    }
    out = EXPORT_DIR / "_reconcile-report.json"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "mapping_version": live_v,
        "tables_reconciled": len(per_table),
        "hard_failures": failures,
        "report": str(out.relative_to(REPO_ROOT)),
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
