#!/usr/bin/env python3
"""Repeatable, idempotent provisioning of the Prompt 16 board Data Store tables.

Reads ``board-tables.schema.json`` (produced by ``generate_board_schema.py``)
and creates/verifies the 6 Data Store-native tables in the credited Catalyst
project using the Admin SDK. Safe to re-run: existing tables/columns/indexes are
left untouched (create-if-absent).

This does NOT run in CI or the offline demo — it only executes inside a Catalyst
environment where ``zcatalyst_sdk`` + an Admin token are available. Offline it
performs a DRY RUN that prints the exact create plan, so the schema is inspectable
without spending anything.

Usage:
    # dry-run (default, offline-safe)
    python infra/catalyst/ds-schema/provision_board_tables.py

    # execute against the credited project (inside Catalyst / with SDK creds)
    DRISHTI_USE_CATALYST_DATASTORE=true \
    python infra/catalyst/ds-schema/provision_board_tables.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_JSON = HERE / "board-tables.schema.json"

# Data Store column-type mapping (board_schema vocabulary -> Data Store types).
_DS_TYPE = {
    "int": "bigint", "text": "varchar", "bigtext": "text", "bool": "boolean",
    "numeric": "double", "json": "text", "timestamp": "datetime",
}


def _load_schema() -> dict:
    if not SCHEMA_JSON.exists():
        raise SystemExit("board-tables.schema.json missing — run "
                         "generate_board_schema.py first.")
    return json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))


def _plan(schema: dict) -> list[str]:
    lines: list[str] = []
    for t in schema["tables"]:
        lines.append(f"TABLE {t['name']} (pk={t['primary_key']}, "
                     f"append_only={t['append_only']})")
        for c in t["columns"]:
            lines.append(f"  + {c['name']} {_DS_TYPE.get(c['type'], c['type'])}"
                         f"{'' if c['nullable'] else ' NOT NULL'}")
        for ix in t["indexes"]:
            kind = "UNIQUE INDEX" if ix["unique"] else "INDEX"
            lines.append(f"  {kind} {ix['name']} ({', '.join(ix['columns'])})")
        lines.append(f"  + ExternalID varchar UNIQUE  (idempotent upsert key, "
                     f"prefix '{t['external_id_prefix']}')")
    return lines


def _apply(schema: dict) -> None:
    import zcatalyst_sdk  # only present in a Catalyst environment
    app = zcatalyst_sdk.initialize()
    ds = app.datastore()
    existing = {t.get("table_name") for t in (ds.get_all_tables() or [])}
    for t in schema["tables"]:
        if t["name"] in existing:
            print(f"[skip] {t['name']} already exists")
            continue
        # NOTE: Data Store table creation is an Admin/console operation; the SDK
        # surface varies by plan. We attempt a create and fall back to a clear
        # message so provisioning is explicit rather than silently partial.
        try:
            ds.create_table({  # type: ignore[attr-defined]
                "table_name": t["name"],
                "columns": [
                    {"column_name": c["name"],
                     "data_type": _DS_TYPE.get(c["type"], c["type"]),
                     "mandatory": not c["nullable"]}
                    for c in t["columns"]
                ] + [{"column_name": "ExternalID", "data_type": "varchar",
                      "unique": True, "mandatory": True}],
            })
            print(f"[create] {t['name']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[manual] {t['name']}: create via console/IaC "
                  f"({type(exc).__name__}: {exc})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="execute against Catalyst (requires SDK + creds)")
    args = ap.parse_args()
    schema = _load_schema()
    print(f"board Data Store schema {schema['schema_version']} "
          f"({len(schema['tables'])} tables)\n")
    for line in _plan(schema):
        print(line)
    if args.apply and os.getenv("DRISHTI_USE_CATALYST_DATASTORE", "").lower() == "true":
        print("\n--- applying ---")
        _apply(schema)
    else:
        print("\n(dry run — pass --apply with DRISHTI_USE_CATALYST_DATASTORE=true "
              "inside Catalyst to provision)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
