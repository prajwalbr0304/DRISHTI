#!/usr/bin/env python3
"""Generate per-table Catalyst Data Store `ds:import` configs from the versioned
AWS PostgreSQL -> Data Store mapping (Phase 14 Part B / workflow §2
bootstrap-catalyst-serving-data).

Source of truth: services/ml/app/datastore/mapping.py.

Each `configs/<SourceTable>.import.json` is a **real `catalyst ds:import` config**
(verified against the CLI + docs 2026-07): `{table_identifier, operation:"upsert",
find_by:"ExternalID"}`. `operation:upsert` + `find_by:ExternalID` gives idempotent
upsert by the stable ExternalID unique column — exactly workflow §2's contract.
Run it as:

    catalyst ds:import <ServingTable.csv> --config configs/<SourceTable>.import.json

(the CSV — exported from AWS with an ExternalID column — is passed positionally or
uploaded to Stratus and referenced via `object_url`). `fk_mapping`/`callback` are
optional and added at import time where referential integrity or a status webhook
is needed.

`import-manifest.json` carries the RICH metadata (ExternalID prefix, pk columns,
search columns, excluded/sensitive columns, disposition, dev cap) consumed by the
serving-export step, the offline SDK importer and reconciliation.
`reserved-namespaces.json` records the Board/Disaster namespaces that are NOT
imported here (phase-order rule).

Run:  python infra/catalyst/ds-import/generate_import_configs.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
MAPPING_PY = REPO_ROOT / "services" / "ml" / "app" / "datastore" / "mapping.py"
CONFIG_DIR = HERE / "configs"


def _load_mapping():
    """Load mapping.py directly by path (no heavy `app` package import)."""
    spec = importlib.util.spec_from_file_location("drishti_ds_mapping", MAPPING_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module  # register so frozen dataclasses resolve
    spec.loader.exec_module(module)
    return module


def catalyst_import_config(m) -> dict:
    """A pure `catalyst ds:import` config for one imported TableMapping.

    Only documented ds:import keys are emitted so the file can be passed directly
    to `catalyst ds:import --config`. object_url is intentionally omitted (the CSV
    path is passed positionally at import time, which the CLI prioritises).
    """
    return {
        "table_identifier": m.datastore_table,
        "operation": "upsert",
        "find_by": "ExternalID",
    }


def manifest_entry(m, mapping) -> dict:
    """Rich metadata (NOT part of the ds:import config) for export + reconciliation."""
    return {
        "source_table": m.source_table,
        "datastore_table": m.datastore_table,
        "domain": m.domain.value,
        "disposition": m.disposition.value,
        "config": f"configs/{m.source_table}.import.json",
        "external_id_field": "ExternalID",
        "external_id_prefix": m.external_id_prefix,
        "pk_columns": list(m.pk_columns),
        "search_columns": list(m.search_columns),
        "excluded_columns": list(m.excluded_columns),
        "search": bool(m.search_columns),
        "dev_row_cap": mapping.DEV_IMPORT_ROW_CAP,
        "mapping_version": mapping.MAPPING_VERSION,
    }


def main() -> int:
    mapping = _load_mapping()
    problems = mapping.validate_mapping()
    if problems:
        print("MAPPING VALIDATION FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for old in CONFIG_DIR.glob("*.import.json"):
        old.unlink()  # clear stale configs so a mapping rename leaves no orphan

    imported = mapping.imported_tables()
    tables_meta = []
    for m in imported:
        out = CONFIG_DIR / f"{m.source_table}.import.json"
        out.write_text(json.dumps(catalyst_import_config(m), indent=2) + "\n", encoding="utf-8")
        tables_meta.append(manifest_entry(m, mapping))

    by_disp: dict[str, int] = {}
    for m in mapping.all_mappings():
        by_disp[m.disposition.value] = by_disp.get(m.disposition.value, 0) + 1

    manifest = {
        "mapping_version": mapping.MAPPING_VERSION,
        "dev_row_cap": mapping.DEV_IMPORT_ROW_CAP,
        "generated_from": "services/ml/app/datastore/mapping.py",
        "import_mechanism": "catalyst ds:import (operation=upsert, find_by=ExternalID); "
                            "offline alternative: import_serving_subset.py (SDK bulk_upsert)",
        "csv_contract": "Serving CSV must include an ExternalID column "
                        "(ExternalID = '<external_id_prefix>:<pk...>'); first row = headers; "
                        "<=5000 rows/table in the development environment.",
        "imported_table_count": len(imported),
        "search_enabled_count": len(mapping.search_enabled_tables()),
        "disposition_counts": by_disp,
        "tables": tables_meta,
    }
    (HERE / "import-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    reserved = {
        "note": "Reserved for later phases; NOT created or imported in Phase 14 "
                "(phase-order rule). Prompt 16 = Investigation Board; Prompt 17 = "
                "Disaster Response.",
        "namespaces": {d.value: list(tbls)
                       for d, tbls in mapping.reserved_namespaces().items()},
        "external_id_prefixes": dict(mapping.RESERVED_EXTERNAL_ID_PREFIXES),
    }
    (HERE / "reserved-namespaces.json").write_text(
        json.dumps(reserved, indent=2) + "\n", encoding="utf-8")

    print(f"OK mapping v{mapping.MAPPING_VERSION}: wrote {len(imported)} ds:import configs "
          f"to {CONFIG_DIR.relative_to(REPO_ROOT)}")
    print(f"   dispositions: {by_disp}")
    print(f"   search-enabled tables: {manifest['search_enabled_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
