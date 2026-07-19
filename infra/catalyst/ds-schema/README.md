# infra/catalyst/ds-schema — Investigation Board Data Store schema (Prompt 16)

The six **Investigation Board** tables are **Data Store-native**: created directly
in Catalyst Data Store and populated by the AppSail board service at runtime.
There is **no AWS PostgreSQL source table** and **no new operational PG migration**
(Prompt 16 §A.1). This is the counterpart to `../ds-import` (which imports curated
AWS rows) — here nothing is imported; the schema is provisioned empty and filled
by the API.

## Source of truth

`services/ml/app/datastore/board_schema.py` defines every column, type, index,
search column and the append-only flag. `services/ml/app/datastore/mapping.py`
registers the same six tables with `Disposition.DATASTORE_NATIVE` and the stable
ExternalID prefixes (`board`, `bnode`, `bedge`, `bann`, `bcollab`, `bact`).

## Files

| File | Purpose |
|---|---|
| `board-tables.schema.json` | Generated, versioned schema config (columns/indexes/limits). |
| `generate_board_schema.py` | Regenerates the JSON from `board_schema.py`; fails on drift vs `mapping.py`. |
| `provision_board_tables.py` | Repeatable, idempotent create/verify via the Admin SDK (dry-run offline). |

## Commands

```bash
# regenerate the schema config (offline, no credits)
python infra/catalyst/ds-schema/generate_board_schema.py

# inspect the exact create plan (dry run, offline-safe)
python infra/catalyst/ds-schema/provision_board_tables.py

# provision inside Catalyst (SDK + Admin creds required)
DRISHTI_USE_CATALYST_DATASTORE=true \
python infra/catalyst/ds-schema/provision_board_tables.py --apply
```

## Tables

`InvestigationBoard`, `BoardNode`, `BoardEdge`, `BoardAnnotation`,
`BoardCollaborator`, `BoardActivity` (append-only).

Indexes cover the required access paths (Prompt 16 §A.9): `BoardID` on every
child, `(RefTable, RefID)` and `CanonicalEntityID` reverse lookup on `BoardNode`,
`(BoardID, BoardActivityID)` activity ordering for reconnect/replay, and
owner/status on `InvestigationBoard`.

## RLS

AWS PostgreSQL **RLS and FORCE RLS remain disabled** as requested. No RLS policy
is created for any optional analytics mirror. The enforced access boundary is
**Catalyst Authentication + API Gateway/AppSail** authorization (see
`services/ml/app/board/guards.py`).
