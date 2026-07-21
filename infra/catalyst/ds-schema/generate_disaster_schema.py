#!/usr/bin/env python3
"""Generate the versioned Catalyst Data Store schema config for the Prompt 17
Disaster Response (Emergency Response) tables from the single source of truth
(services/ml/app/datastore/disaster_schema.py) — Prompt 21 §D.

Like the Prompt 16 board tables, the disaster tables are Data Store-NATIVE:
created directly in Catalyst Data Store and populated by the AppSail disaster
service at runtime. There is NO AWS PostgreSQL source table and NO operational
PG migration (the optional AWS PostGIS/pgRouting mirror is a reconstructable
analytics artifact keyed by the same ExternalIDs).

This emits ``disaster-tables.schema.json`` — a repeatable, versioned description
of the tables (columns, types, indexes, search columns, append-only flags) plus
a DEPENDENCY-ORDERED provisioning manifest and a bounded golden-journey demo
subset, which ``provision_disaster_tables.py`` (SDK) consumes to create/verify
the tables. Re-running is idempotent.

Run:  python infra/catalyst/ds-schema/generate_disaster_schema.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SCHEMA_PY = REPO_ROOT / "services" / "ml" / "app" / "datastore" / "disaster_schema.py"
MAPPING_PY = REPO_ROOT / "services" / "ml" / "app" / "datastore" / "mapping.py"

# Dependency-ordered provisioning: lookups + independent tables first, then the
# tables that reference them (referential order preserved by ExternalID). This
# is the create/import order the provisioner + import manifest follow (§D.3).
PROVISION_ORDER = [
    "HazardType",          # lookup
    "FeedSource",          # feed connector registry (lookup)
    "Resource",            # deployable resources (independent)
    "ReliefShelter",       # shelters (independent)
    "HazardEvent",         # references HazardType(code), District/Unit
    "HydroMetReading",     # append-only; references FeedSource(code)
    "HazardRiskZone",      # references HazardType(code), District
    "HazardPrediction",    # append-only; references HazardEvent, FeatureSnapshot
    "ResourceAllocation",  # references HazardEvent, Resource, zone
    "EvacuationRoute",     # references HazardEvent, zone, ReliefShelter
    "ResponsePlan",        # references HazardEvent
    "ResponseTask",        # references ResponsePlan
    "FeedIngestionRun",    # references FeedSource
    "DisasterActivity",    # append-only chain-of-custody (independent)
]

# Bounded golden-journey demo subset (§D.4): the minimum deterministic rows the
# mandatory disaster demo needs. Seeded deterministically by app/disaster/seed.py
# (idempotent by ExternalID). Row caps stay far under the Data Store dev import
# ceiling. Optional/empty tables carry an explicit empty-state note.
DEMO_SUBSET = {
    "HazardType": {"rows": 9, "mandatory": True,
                   "note": "all HAZARD_CODES seeded deterministically"},
    "FeedSource": {"rows": 3, "mandatory": True,
                   "note": "synthetic_replay + recorded_sample + live (Open-Meteo)"},
    "Resource": {"rows": 24, "mandatory": True, "note": "deployable resources per demo district"},
    "ReliefShelter": {"rows": 8, "mandatory": True, "note": "evacuation destinations"},
    "HazardEvent": {"rows": 6, "mandatory": True, "note": "golden-journey hazard events"},
    "HydroMetReading": {"rows": 120, "mandatory": True, "note": "recent readings window"},
    "HazardRiskZone": {"rows": 10, "mandatory": True, "note": "static + dynamic zones"},
    "HazardPrediction": {"rows": 6, "mandatory": False,
                         "note": "seeded on demand; empty until a forecast runs (Prompt 23)"},
    "ResourceAllocation": {"rows": 4, "mandatory": False,
                           "note": "empty until a coordinator proposes; human-approved before dispatch"},
    "EvacuationRoute": {"rows": 4, "mandatory": False, "note": "computed on demand; no_route surfaced"},
    "ResponsePlan": {"rows": 3, "mandatory": True, "note": "per-hazard SOP plan headers"},
    "ResponseTask": {"rows": 18, "mandatory": True, "note": "SOP checklist tasks"},
    "FeedIngestionRun": {"rows": 6, "mandatory": False, "note": "heartbeat/freshness runs"},
    "DisasterActivity": {"rows": 0, "mandatory": False,
                         "note": "append-only; grows from demo actions (empty at seed)"},
}


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    disaster_schema = _load("drishti_disaster_schema", SCHEMA_PY)
    mapping = _load("drishti_ds_mapping", MAPPING_PY)

    # Cross-check: every disaster table declared in disaster_schema.py must be a
    # DATASTORE_NATIVE mapping in the DISASTER_RESPONSE domain (and vice versa).
    native = {m.datastore_table
              for m in mapping.datastore_native_tables(mapping.Domain.DISASTER_RESPONSE)}
    declared = set(disaster_schema.table_names())
    if native != declared:
        print("DISASTER SCHEMA / MAPPING DRIFT:")
        print(f"  native-only : {sorted(native - declared)}")
        print(f"  declared-only: {sorted(declared - native)}")
        return 1

    # ExternalID prefixes must match the mapping.
    for m in mapping.datastore_native_tables(mapping.Domain.DISASTER_RESPONSE):
        t = disaster_schema.table(m.datastore_table)
        if t.external_id_prefix != m.external_id_prefix:
            print(f"PREFIX MISMATCH for {m.datastore_table}: "
                  f"schema={t.external_id_prefix} mapping={m.external_id_prefix}")
            return 1

    # Provisioning order must cover exactly the declared tables.
    if set(PROVISION_ORDER) != declared:
        print("PROVISION_ORDER drift:")
        print(f"  order-only   : {sorted(set(PROVISION_ORDER) - declared)}")
        print(f"  declared-only: {sorted(declared - set(PROVISION_ORDER))}")
        return 1
    if set(DEMO_SUBSET) != declared:
        print("DEMO_SUBSET drift:")
        print(f"  subset-only  : {sorted(set(DEMO_SUBSET) - declared)}")
        print(f"  declared-only: {sorted(declared - set(DEMO_SUBSET))}")
        return 1

    out = disaster_schema.as_provisioning_dict()
    out["mapping_version"] = mapping.MAPPING_VERSION
    out["generated_from"] = "services/ml/app/datastore/disaster_schema.py"
    out["provision_order"] = PROVISION_ORDER
    out["demo_subset"] = DEMO_SUBSET
    out["provisioning"] = {
        "mechanism": "Catalyst Data Store table create/verify via the Admin SDK "
                     "(provision_disaster_tables.py); idempotent create-if-absent.",
        "seed": "Deterministic golden-journey rows are seeded idempotently by "
                "services/ml/app/disaster/seed.py (upsert by ExternalID).",
        "rls": "AWS PostgreSQL RLS/FORCE RLS remain DISABLED; no RLS policy is "
               "created for the optional analytics mirror. Catalyst "
               "Authentication + API Gateway/AppSail authorization is the "
               "enforced access boundary.",
        "pg_migration": "NONE — Data Store-native tables. The optional AWS "
                        "PostGIS/pgRouting mirror (services/ml/sql/"
                        "023_disaster_response.sql) is a reconstructable "
                        "analytics artifact keyed by the same ExternalIDs.",
    }

    dst = HERE / "disaster-tables.schema.json"
    dst.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    idx_count = sum(len(t["indexes"]) for t in out["tables"])
    search_count = sum(1 for t in out["tables"] if t["search_columns"])
    print(f"wrote {dst.relative_to(REPO_ROOT)} "
          f"({len(out['tables'])} tables, {idx_count} indexes, "
          f"{search_count} search-enabled, schema {out['schema_version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
