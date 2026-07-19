#!/usr/bin/env python3
"""Generate the versioned Catalyst Data Store schema config for the Prompt 16
Investigation Board tables from the single source of truth
(services/ml/app/datastore/board_schema.py).

Unlike ds-import (which imports curated AWS PostgreSQL rows), the board tables
are Data Store-NATIVE: created directly in Data Store and populated by the
AppSail board service at runtime. There is NO AWS PostgreSQL source table and NO
new operational PG migration (Prompt 16 §A.1).

This emits ``board-tables.schema.json`` — a repeatable, versioned description of
the 6 tables (columns, types, indexes, search columns, append-only flags) that
``provision_board_tables.py`` (SDK) consumes to create/verify the tables in the
credited Catalyst project. Re-running is idempotent.

Run:  python infra/catalyst/ds-schema/generate_board_schema.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SCHEMA_PY = REPO_ROOT / "services" / "ml" / "app" / "datastore" / "board_schema.py"
MAPPING_PY = REPO_ROOT / "services" / "ml" / "app" / "datastore" / "mapping.py"


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    board_schema = _load("drishti_board_schema", SCHEMA_PY)
    mapping = _load("drishti_ds_mapping", MAPPING_PY)

    # Cross-check: every board table declared in board_schema.py must be a
    # DATASTORE_NATIVE mapping (and vice versa) so the two never drift. Scope to
    # the board domain so Prompt 17 disaster native tables don't trip the check.
    native = {m.datastore_table
              for m in mapping.datastore_native_tables(mapping.Domain.INVESTIGATION_BOARD)}
    declared = set(board_schema.table_names())
    if native != declared:
        print("BOARD SCHEMA / MAPPING DRIFT:")
        print(f"  native-only : {sorted(native - declared)}")
        print(f"  declared-only: {sorted(declared - native)}")
        return 1

    # Cross-check ExternalID prefixes match the mapping.
    for m in mapping.datastore_native_tables(mapping.Domain.INVESTIGATION_BOARD):
        t = board_schema.table(m.datastore_table)
        if t.external_id_prefix != m.external_id_prefix:
            print(f"PREFIX MISMATCH for {m.datastore_table}: "
                  f"schema={t.external_id_prefix} mapping={m.external_id_prefix}")
            return 1

    out = board_schema.as_provisioning_dict()
    out["mapping_version"] = mapping.MAPPING_VERSION
    out["generated_from"] = "services/ml/app/datastore/board_schema.py"
    out["provisioning"] = {
        "mechanism": "Catalyst Data Store table create/verify via the Admin SDK "
                     "(provision_board_tables.py); idempotent create-if-absent.",
        "rls": "AWS PostgreSQL RLS/FORCE RLS remain DISABLED; no RLS policy is "
               "created for any optional analytics mirror. Catalyst "
               "Authentication + API Gateway/AppSail authorization is the "
               "enforced access boundary.",
        "pg_migration": "NONE — these tables are Data Store-native and are never "
                        "added to the operational PostgreSQL schema.",
    }

    dst = HERE / "board-tables.schema.json"
    dst.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dst.relative_to(REPO_ROOT)} "
          f"({len(out['tables'])} tables, schema {out['schema_version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
