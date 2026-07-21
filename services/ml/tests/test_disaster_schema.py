"""Prompt 21 §D — disaster Data Store schema + idempotent provisioner validation.

Verifies (offline, no DB/SDK):
  * the disaster schema source (app/datastore/disaster_schema.py) and the
    versioned mapping (DATASTORE_NATIVE / DISASTER_RESPONSE) do not drift;
  * every mandatory disaster table/index/search field is present and internally
    consistent (PK in columns, indexes/search over real columns);
  * append-only tables are declared so the repo blocks UPDATE/DELETE;
  * the generated infra/catalyst/ds-schema/disaster-tables.schema.json matches
    the source (regeneration is deterministic/idempotent);
  * the dependency-ordered provisioning manifest + bounded demo subset cover
    exactly the declared tables, with deterministic rows for mandatory golden-
    journey tables and explicit empty-state notes for optional ones.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"

import pytest  # noqa: E402

from app.datastore import disaster_schema as ds  # noqa: E402
from app.datastore import mapping as mp  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_JSON = _REPO_ROOT / "infra" / "catalyst" / "ds-schema" / "disaster-tables.schema.json"

# The mandatory Data Store-native disaster tables for Prompts 2-20 (Prompt 17).
_MANDATORY_TABLES = {
    "HazardType", "HazardEvent", "HazardPrediction", "HazardRiskZone",
    "HydroMetReading", "Resource", "ReliefShelter", "ResourceAllocation",
    "EvacuationRoute", "ResponsePlan", "ResponseTask", "FeedSource",
    "FeedIngestionRun", "DisasterActivity",
}
_APPEND_ONLY = {"HazardPrediction", "HydroMetReading", "DisasterActivity"}


@pytest.fixture(scope="module")
def schema_json():
    assert _SCHEMA_JSON.is_file(), (
        f"{_SCHEMA_JSON} missing — run generate_disaster_schema.py")
    return json.loads(_SCHEMA_JSON.read_text(encoding="utf-8"))


def test_all_mandatory_tables_present():
    declared = set(ds.table_names())
    missing = _MANDATORY_TABLES - declared
    assert not missing, f"missing mandatory disaster tables: {sorted(missing)}"


def test_schema_matches_datastore_native_mapping():
    native = {m.datastore_table
              for m in mp.datastore_native_tables(mp.Domain.DISASTER_RESPONSE)}
    assert native == set(ds.table_names()), "disaster schema/mapping drift"
    # ExternalID prefixes must agree between the two sources of truth.
    for m in mp.datastore_native_tables(mp.Domain.DISASTER_RESPONSE):
        assert ds.table(m.datastore_table).external_id_prefix == m.external_id_prefix


def test_append_only_tables_declared():
    assert set(ds.append_only_tables()) == _APPEND_ONLY


def test_each_table_internally_consistent():
    for t in ds.DISASTER_TABLES:
        cols = set(t.column_names())
        assert t.pk in cols, f"{t.name}: pk {t.pk} not in columns"
        assert t.external_id_prefix, f"{t.name}: empty ExternalID prefix"
        for ix in t.indexes:
            for c in ix.columns:
                assert c in cols, f"{t.name}.{ix.name}: index column {c} missing"
        for sc in t.search_columns:
            assert sc in cols, f"{t.name}: search column {sc} missing"


def test_generated_json_matches_source(schema_json):
    """Regeneration is deterministic: the committed JSON equals the source dict
    (tables/columns/indexes/search/append-only), so the provisioner never drifts."""
    src = ds.as_provisioning_dict()
    assert schema_json["schema_version"] == src["schema_version"]
    src_tables = {t["name"]: t for t in src["tables"]}
    json_tables = {t["name"]: t for t in schema_json["tables"]}
    assert set(src_tables) == set(json_tables)
    for name, st in src_tables.items():
        jt = json_tables[name]
        assert st["primary_key"] == jt["primary_key"]
        assert st["append_only"] == jt["append_only"]
        assert st["search_columns"] == jt["search_columns"]
        assert [c["name"] for c in st["columns"]] == [c["name"] for c in jt["columns"]]
        assert [i["name"] for i in st["indexes"]] == [i["name"] for i in jt["indexes"]]


def test_provision_manifest_covers_all_tables(schema_json):
    declared = set(ds.table_names())
    assert set(schema_json["provision_order"]) == declared, "provision_order drift"
    assert set(schema_json["demo_subset"]) == declared, "demo_subset drift"


def test_provision_order_respects_dependencies(schema_json):
    order = schema_json["provision_order"]
    pos = {name: i for i, name in enumerate(order)}
    # A referenced table must be provisioned before the table that references it.
    deps = {
        "ResourceAllocation": ["HazardEvent", "Resource"],
        "EvacuationRoute": ["HazardEvent", "ReliefShelter"],
        "ResponseTask": ["ResponsePlan"],
        "FeedIngestionRun": ["FeedSource"],
        "HazardEvent": ["HazardType"],
    }
    for table, requires in deps.items():
        for r in requires:
            assert pos[r] < pos[table], f"{r} must be provisioned before {table}"


def test_mandatory_golden_journey_tables_have_deterministic_rows(schema_json):
    subset = schema_json["demo_subset"]
    for name, spec in subset.items():
        if spec.get("mandatory"):
            assert spec.get("rows", 0) > 0, (
                f"mandatory golden-journey table {name} must have deterministic rows")
        else:
            # optional tables must carry an explicit empty-state note
            assert spec.get("note"), f"optional table {name} needs an empty-state note"


def test_schema_has_expected_counts(schema_json):
    assert len(schema_json["tables"]) == 14
    idx = sum(len(t["indexes"]) for t in schema_json["tables"])
    assert idx == 32
    search_enabled = [t["name"] for t in schema_json["tables"] if t["search_columns"]]
    assert len(search_enabled) == 7
