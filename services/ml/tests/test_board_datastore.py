"""Phase 16 — Data Store schema / mapping / index / search verification +
AWS RLS-disabled posture. Pure (no DB required)."""
import re

from app.datastore import board_schema, mapping


def test_board_tables_are_datastore_native():
    native = {m.datastore_table
              for m in mapping.datastore_native_tables(mapping.Domain.INVESTIGATION_BOARD)}
    assert native == {
        "InvestigationBoard", "BoardNode", "BoardEdge", "BoardAnnotation",
        "BoardCollaborator", "BoardActivity",
    }
    # every native table is DATASTORE_NATIVE and therefore NOT imported from PG
    for m in mapping.datastore_native_tables():
        assert m.disposition == mapping.Disposition.DATASTORE_NATIVE
        assert not m.imported


def test_mapping_validation_clean_after_board_added():
    assert mapping.validate_mapping() == []


def test_prompt16_and_17_no_longer_reserved():
    # Board (Prompt 16) and Disaster (Prompt 17) namespaces both moved from
    # RESERVED to live DATASTORE_NATIVE mappings.
    assert mapping.Domain.INVESTIGATION_BOARD not in mapping.reserved_namespaces()
    assert mapping.Domain.DISASTER_RESPONSE not in mapping.reserved_namespaces()
    for t in board_schema.table_names():
        assert not mapping.is_reserved(t)


def test_external_id_prefixes_match_schema_and_are_unique():
    prefixes = {}
    for m in mapping.datastore_native_tables(mapping.Domain.INVESTIGATION_BOARD):
        t = board_schema.table(m.datastore_table)
        assert t.external_id_prefix == m.external_id_prefix
        assert m.external_id_prefix not in prefixes, "duplicate board prefix"
        prefixes[m.external_id_prefix] = m.datastore_table
    assert set(prefixes) == {"board", "bnode", "bedge", "bann", "bcollab", "bact"}


def test_required_indexes_present():
    # Prompt 16 §A.9 required access paths.
    node = board_schema.table("BoardNode")
    idx_cols = [tuple(ix.columns) for ix in node.indexes]
    assert ("BoardID",) in idx_cols
    assert ("RefTable", "RefID") in idx_cols          # reverse lookup
    assert ("CanonicalEntityID",) in idx_cols
    act = board_schema.table("BoardActivity")
    assert ("BoardID", "BoardActivityID") in [tuple(ix.columns) for ix in act.indexes]
    board = board_schema.table("InvestigationBoard")
    board_idx = [tuple(ix.columns) for ix in board.indexes]
    assert ("OwnerActor",) in board_idx and ("Status",) in board_idx
    for t in board_schema.BOARD_TABLES:
        if t.name != "InvestigationBoard":
            assert any("BoardID" in ix.columns for ix in t.indexes), t.name


def test_search_columns_declared():
    assert board_schema.table("InvestigationBoard").search_columns == ("Title", "Description")
    assert board_schema.table("BoardNode").search_columns == ("Label",)


def test_board_activity_is_append_only():
    assert board_schema.append_only_tables() == ["BoardActivity"]
    assert board_schema.table("BoardActivity").append_only is True


def test_pk_and_column_shapes():
    ib = board_schema.table("InvestigationBoard")
    for col in ("BoardID", "Title", "OwnerActor", "Status", "Visibility",
                "IsLocked", "Version", "ParentBoardID"):
        assert col in ib.column_names()
    edge = board_schema.table("BoardEdge")
    for col in ("EdgeClass", "Rationale", "SourceRecordID", "PromotedStatus"):
        assert col in edge.column_names()
    # soft-delete columns on the mutable child tables (no hard delete in DS)
    for name in ("BoardNode", "BoardEdge", "BoardAnnotation", "BoardCollaborator"):
        assert "DeletedAt" in board_schema.table(name).column_names()


def test_provisioning_dict_documents_rls_disabled():
    d = board_schema.as_provisioning_dict()
    assert len(d["tables"]) == 6
    assert "RLS" in d["note"] or "rls" in d["note"].lower()
    # every column type maps to a known Data Store type vocabulary
    known = {"int", "text", "bigtext", "bool", "numeric", "json", "timestamp"}
    for t in d["tables"]:
        for c in t["columns"]:
            assert c["type"] in known


def test_snapshot_limits_are_bounded():
    assert board_schema.MAX_JSON_BYTES <= 65536
    assert board_schema.MAX_SNAPSHOT_BYTES <= 65536
    assert re.match(r"\d{4}\.\d{2}\.\d{2}", board_schema.SCHEMA_VERSION)
