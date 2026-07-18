"""Isolate/archive the OLD synthetic identity-graph rows (Phase 11).

The v2 canonical rebuild replaced the legacy intelligence graph. Any row that
belongs to the OLD space — an EntityGraph node with no CanonicalEntityID, a
NetworkEdge with no provenance status, an embedding that is not a canonical
case-corpus vector — is ISOLATED here by setting IsArchived (never deleted, so
the decision is auditable and reversible). The runtime analytics read only the
canonical, non-archived graph, so old and new spaces never mix.

Idempotent: only ever touches rows that are not already archived.
"""
from __future__ import annotations

from typing import Optional

from .. import audit, db

# (table, legacy predicate, archive reason) — the definition of "old/invalid".
_LEGACY_RULES = [
    ("EntityGraph", '"CanonicalEntityID" IS NULL', "legacy_non_canonical_node"),
    ("NetworkEdge", '"ProvenanceStatus" IS NULL', "legacy_unprovenanced_edge"),
    ("CrimeEmbedding", '"SourceType" <> \'case\'', "legacy_non_case_embedding"),
]


def _archive_legacy(conn, actor: Optional[str] = None) -> dict:
    archived: dict[str, int] = {}
    with conn.cursor() as cur:
        for table, predicate, reason in _LEGACY_RULES:
            cur.execute(
                f'UPDATE "{table}" SET "IsArchived"=TRUE, "ArchivedAt"=now(), "ArchiveReason"=%s '
                f'WHERE {predicate} AND "IsArchived"=FALSE', (reason,))
            archived[table] = cur.rowcount
    total = sum(archived.values())
    audit.record(audit.Action.UPDATE, "graph_archive_legacy", None, actor=actor, conn=conn,
                 detail={"archived": archived, "total": total})
    return {"archived": archived, "total_archived": total}


def _archive_status(conn) -> dict:
    out: dict[str, dict] = {}
    with conn.cursor() as cur:
        for table, predicate, _reason in _LEGACY_RULES:
            cur.execute(f'SELECT count(*), count(*) FILTER (WHERE "IsArchived"), '
                        f'count(*) FILTER (WHERE ({predicate}) AND "IsArchived"=FALSE) FROM "{table}"')
            total, arch, legacy_live = cur.fetchone()
            out[table] = {"total": int(total), "archived": int(arch),
                          "live": int(total) - int(arch), "legacy_still_live": int(legacy_live)}
    # the mixed-spaces invariant: no legacy row may remain live after archival
    out["clean"] = all(v["legacy_still_live"] == 0 for v in out.values())
    return out


# --- public wrappers --------------------------------------------------------
def archive_legacy(actor: Optional[str] = None) -> dict:
    with db.rw_conn() as conn:
        return _archive_legacy(conn, actor)


def archive_status() -> dict:
    with db.ro_conn() as conn:
        return _archive_status(conn)
