"""Investigation Board Data Store schema (Prompt 16 §A).

Single source of truth for the SIX Data Store-native board tables' columns,
types, indexes and search columns. It is deliberately dependency-free (only the
stdlib) so it can be imported both by the AppSail service AND loaded by path
from the ``infra/catalyst/ds-schema`` provisioning generator (the same pattern
``ds-import`` uses for ``mapping.py``).

These tables are created DIRECTLY in Catalyst Data Store and populated by the
board service at runtime. There is NO AWS PostgreSQL source table and NO new
operational PG migration (Prompt 16 constraint). Every board/node/edge/activity
record carries a stable ``ExternalID`` (``<prefix>:<pk>``) so writes are
idempotent and cross-table references survive.

Column ``type`` vocabulary -> Catalyst Data Store column type:
    "int"       -> bigint (identity PK or numeric FK / counter)
    "text"      -> varchar (<= 255; searchable/indexable label/enum/actor)
    "bigtext"   -> text    (descriptions, rationale, sticky content)
    "bool"      -> boolean
    "numeric"   -> double  (canvas geometry, confidence)
    "json"      -> text    (serialized + size-limited at the API boundary)
    "timestamp" -> datetime (ISO-8601, UTC)
"""
from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = "2026.07.19-1"

# Hard size limits validated at the API boundary before any JSON is stored
# (requirement A.6: validate/size-limit serialized JSON).
MAX_JSON_BYTES = 16_384          # per StyleJSON / GeometryJSON / DiffJSON field
MAX_SNAPSHOT_BYTES = 32_768      # pin-time SnapshotJSON (a bounded projection)
MAX_LABEL_LEN = 255
MAX_CONTENT_LEN = 4_000          # sticky/text annotation content


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool = True
    note: str = ""


@dataclass(frozen=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class BoardTable:
    name: str                       # Data Store table name (== mapping.datastore_table)
    external_id_prefix: str         # ExternalID = "<prefix>:<pk>"
    pk: str                         # identity PK column
    columns: tuple[Column, ...]
    indexes: tuple[Index, ...] = ()
    search_columns: tuple[str, ...] = ()
    append_only: bool = False       # BoardActivity: block UPDATE/DELETE everywhere

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


def _c(name, type, nullable=True, note=""):
    return Column(name=name, type=type, nullable=nullable, note=note)


_TS = ("CreatedAt", "UpdatedAt")

BOARD_TABLES: tuple[BoardTable, ...] = (
    BoardTable(
        name="InvestigationBoard",
        external_id_prefix="board",
        pk="BoardID",
        columns=(
            _c("BoardID", "int", nullable=False, note="identity PK"),
            _c("Title", "text", nullable=False),
            _c("Description", "bigtext"),
            # Owner is the authenticated demo actor; OwnerEmployeeID is the
            # optional link to the synthetic Employee where the schema supports it.
            _c("OwnerActor", "text", nullable=False, note="Catalyst-auth demo actor key"),
            _c("OwnerEmployeeID", "int", note="optional FK->Employee (synthetic)"),
            _c("CaseMasterID", "int", note="optional case scope (FK->CaseMaster)"),
            _c("UnitID", "int", note="scope for out-of-unit share warnings"),
            _c("DistrictID", "int", note="scope for out-of-scope share warnings"),
            _c("Status", "text", nullable=False, note="active|archived|locked"),
            _c("Visibility", "text", nullable=False, note="private|shared|unit"),
            _c("IsLocked", "bool", nullable=False),
            _c("Version", "int", nullable=False, note="optimistic concurrency counter"),
            _c("ParentBoardID", "int", note="set when this board is a branch of a locked parent"),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            Index("ix_board_owner", ("OwnerActor",)),
            Index("ix_board_status", ("Status",)),
            Index("ix_board_case", ("CaseMasterID",)),
            Index("ix_board_parent", ("ParentBoardID",)),
        ),
        search_columns=("Title", "Description"),
    ),
    BoardTable(
        name="BoardNode",
        external_id_prefix="bnode",
        pk="BoardNodeID",
        columns=(
            _c("BoardNodeID", "int", nullable=False, note="identity PK"),
            _c("BoardID", "int", nullable=False),
            _c("NodeKind", "text", nullable=False, note="whitelisted object kind"),
            _c("RefTable", "text", note="whitelisted canonical object table"),
            _c("RefID", "text", note="canonical object id (string form)"),
            _c("CanonicalEntityID", "int", note="canonical graph entity id when known"),
            _c("Label", "text"),
            _c("PosX", "numeric", nullable=False),
            _c("PosY", "numeric", nullable=False),
            _c("Width", "numeric"),
            _c("Height", "numeric"),
            _c("StyleJSON", "json"),
            _c("SnapshotJSON", "json", note="pin-time projection (bounded, never file bytes)"),
            _c("SourceVersion", "text", note="source record version at pin time"),
            _c("SourceHash", "text", note="hash of the pinned projection (integrity)"),
            _c("CreatedBy", "text", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-delete (Data Store has no hard "
                                              "delete; keeps chain-of-custody)"),
        ),
        indexes=(
            Index("ix_bnode_board", ("BoardID",)),
            Index("ix_bnode_ref", ("RefTable", "RefID")),
            Index("ix_bnode_entity", ("CanonicalEntityID",)),
        ),
        search_columns=("Label",),
    ),
    BoardTable(
        name="BoardEdge",
        external_id_prefix="bedge",
        pk="BoardEdgeID",
        columns=(
            _c("BoardEdgeID", "int", nullable=False, note="identity PK"),
            _c("BoardID", "int", nullable=False),
            _c("SourceNodeID", "int", nullable=False),
            _c("TargetNodeID", "int", nullable=False),
            _c("EdgeClass", "text", nullable=False, note="evidence|hypothesis"),
            _c("Label", "text"),
            _c("RelationshipType", "text"),
            _c("Directed", "bool", nullable=False),
            _c("Confidence", "numeric"),
            _c("Rationale", "bigtext", note="required before a hypothesis can be promoted"),
            _c("EvidenceCaseID", "int", note="FK->CaseMaster for imported evidence edges"),
            _c("SourceRecordID", "text", note="provenance of an imported evidence edge"),
            _c("StyleJSON", "json"),
            _c("PromotedStatus", "text", note="null|proposed; set on promotion"),
            _c("PromotedRef", "text", note="AlertHistory/proposal id created on promotion"),
            _c("CreatedBy", "text", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-delete"),
        ),
        indexes=(
            Index("ix_bedge_board", ("BoardID",)),
            Index("ix_bedge_source", ("SourceNodeID",)),
            Index("ix_bedge_target", ("TargetNodeID",)),
            Index("ix_bedge_class", ("EdgeClass",)),
        ),
    ),
    BoardTable(
        name="BoardAnnotation",
        external_id_prefix="bann",
        pk="BoardAnnotationID",
        columns=(
            _c("BoardAnnotationID", "int", nullable=False, note="identity PK"),
            _c("BoardID", "int", nullable=False),
            _c("Kind", "text", nullable=False, note="sticky|text|frame|freehand"),
            _c("Content", "bigtext"),
            _c("GeometryJSON", "json"),
            _c("StyleJSON", "json"),
            _c("CreatedBy", "text", nullable=False),
            _c("CreatedAt", "timestamp", nullable=False),
            _c("UpdatedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-delete"),
        ),
        indexes=(Index("ix_bann_board", ("BoardID",)),),
    ),
    BoardTable(
        name="BoardCollaborator",
        external_id_prefix="bcollab",
        pk="BoardCollaboratorID",
        columns=(
            _c("BoardCollaboratorID", "int", nullable=False, note="identity PK"),
            _c("BoardID", "int", nullable=False),
            _c("Actor", "text", nullable=False, note="collaborator demo actor key"),
            _c("EmployeeID", "int", note="optional FK->Employee (synthetic)"),
            _c("Role", "text", nullable=False, note="owner|editor|viewer"),
            _c("AddedBy", "text", nullable=False),
            _c("AddedAt", "timestamp", nullable=False),
            _c("DeletedAt", "timestamp", note="soft-remove of a collaborator"),
        ),
        indexes=(
            Index("ix_bcollab_board", ("BoardID",)),
            Index("ux_bcollab_board_actor", ("BoardID", "Actor"), unique=True),
        ),
    ),
    BoardTable(
        name="BoardActivity",
        external_id_prefix="bact",
        pk="BoardActivityID",
        append_only=True,
        columns=(
            _c("BoardActivityID", "int", nullable=False, note="identity PK; monotonic per board"),
            _c("BoardID", "int", nullable=False),
            _c("Actor", "text", nullable=False, note="demo actor who made the change"),
            _c("Action", "text", nullable=False),
            _c("TargetType", "text"),
            _c("TargetID", "text"),
            _c("DiffJSON", "json", note="compact before/after (data-minimised)"),
            _c("RequestID", "text", note="X-Request-ID correlation"),
            _c("CreatedAt", "timestamp", nullable=False),
        ),
        indexes=(
            # Activity ordering / reconnect-replay: (BoardID, BoardActivityID).
            Index("ix_bact_board_seq", ("BoardID", "BoardActivityID")),
        ),
    ),
)

BOARD_TABLES_BY_NAME: dict[str, BoardTable] = {t.name: t for t in BOARD_TABLES}


def table(name: str) -> BoardTable:
    return BOARD_TABLES_BY_NAME[name]


def table_names() -> list[str]:
    return [t.name for t in BOARD_TABLES]


def append_only_tables() -> list[str]:
    return [t.name for t in BOARD_TABLES if t.append_only]


def as_provisioning_dict() -> dict:
    """Serializable schema description for the ds-schema provisioning generator."""
    return {
        "schema_version": SCHEMA_VERSION,
        "note": ("Prompt 16 Investigation Board — Data Store-native tables. "
                 "Created directly in Catalyst Data Store; app-populated at runtime; "
                 "NO AWS PostgreSQL source and NO operational PG migration. "
                 "AWS RLS/FORCE RLS remain disabled (no RLS policy is created)."),
        "limits": {
            "max_json_bytes": MAX_JSON_BYTES,
            "max_snapshot_bytes": MAX_SNAPSHOT_BYTES,
            "max_label_len": MAX_LABEL_LEN,
            "max_content_len": MAX_CONTENT_LEN,
        },
        "tables": [
            {
                "name": t.name,
                "external_id_prefix": t.external_id_prefix,
                "primary_key": t.pk,
                "append_only": t.append_only,
                "search_columns": list(t.search_columns),
                "columns": [
                    {"name": c.name, "type": c.type, "nullable": c.nullable,
                     "note": c.note} for c in t.columns
                ],
                "indexes": [
                    {"name": ix.name, "columns": list(ix.columns), "unique": ix.unique}
                    for ix in t.indexes
                ],
            }
            for t in BOARD_TABLES
        ],
    }
