"""Entity Explorer + Entity profile reads (Phase 15d — People & Entities).

Provides: paginated/filterable entity list, entity detail (identity +
criminal history + locations + gang membership), and linked-cases lookup.
All reads run under the restricted read-only role.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .. import db

# EntityGraph."SearchVector" is a GENERATED tsvector built with the 'english'
# config (police_fir_intelligence.sql), which STEMS tokens (e.g. 'Syed' -> 'sy').
# A bare plainto_tsquery(text) uses the database default config (pg_catalog.simple,
# no stemming -> 'syed'), so it NEVER matches the stemmed vector. Queries MUST use
# the same 'english' config as the stored vector, or entity search returns nothing.
_FTS_CONFIG = "english"


def _prefix_tsquery(q: str) -> Optional[str]:
    """Build a safe prefix tsquery string from free text: split into alphanumeric
    tokens and AND them as prefix terms (``token:*``) so search-as-you-type works
    (typing 'kir' finds 'Kiran'). Returns None when there is no usable token."""
    tokens = re.findall(r"[A-Za-z0-9]+", q or "")
    if not tokens:
        return None
    return " & ".join(f"{t}:*" for t in tokens)


# ---------------------------------------------------------------------------
# Entity list (search + filter)
# ---------------------------------------------------------------------------

def list_entities(
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    has_risk: Optional[bool] = None,
    gang_affiliated: Optional[bool] = None,
    district_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    clauses: list[str] = []
    params: list[Any] = []

    # Every clause is qualified with the "e" alias: the row query below joins
    # CanonicalEntity, which also has "Attributes", so a bare column reference
    # would be ambiguous.
    if entity_type:
        clauses.append('e."EntityType"::text = %s')
        params.append(entity_type)
    if q:
        ts = _prefix_tsquery(q)
        if ts:
            # to_tsquery with the SAME 'english' config as the stored vector.
            clauses.append('e."SearchVector" @@ to_tsquery(%s, %s)')
            params.append(_FTS_CONFIG)
            params.append(ts)
        else:
            clauses.append("FALSE")  # q had no searchable token -> honest no-match
    if has_risk:
        clauses.append('EXISTS(SELECT 1 FROM "CrimeRiskScore" r WHERE r."EntityID"=e."EntityID")')
    if gang_affiliated:
        clauses.append('EXISTS(SELECT 1 FROM "GangMembership" gm WHERE gm."MemberEntityID"=e."EntityID")')
    if district_id:
        clauses.append('(e."Attributes"->>\'district_id\')::int = %s')
        params.append(district_id)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "EntityGraph" e{where}', params)
            total = int(cur.fetchone()[0])
            # CanonicalEntity is joined so a person row carries the canonical
            # person it resolves to. The face gallery is keyed on
            # CanonicalPersonID, so without this the explorer could not offer a
            # reference-photo action on the row the officer is already looking at.
            # LEFT, not INNER: legacy/unprovenanced nodes have no canonical link
            # and must still be listed. COUNT needs no join at all — the join is
            # on CanonicalEntity's primary key, so it cannot change the total.
            cur.execute(
                f'SELECT e."EntityID",e."EntityType"::text,e."Label",e."RefTable",e."RefID",'
                f'(e."Attributes"->>\'pagerank\')::float,'
                f'(e."Attributes"->>\'community\')::int,'
                f'(e."Attributes"->>\'district_id\')::int,'
                f'e."Attributes"->>\'district\','
                f'ce."CanonicalPersonID" '
                f'FROM "EntityGraph" e '
                f'LEFT JOIN "CanonicalEntity" ce '
                f'ON ce."CanonicalEntityID" = e."CanonicalEntityID"'
                f'{where} '
                f'ORDER BY e."EntityID" DESC LIMIT %s OFFSET %s',
                params + [page_size, offset],
            )
            rows = cur.fetchall()

    items = [
        {
            "entity_id": int(r[0]),
            "entity_type": r[1],
            "label": r[2],
            "ref_table": r[3],
            "ref_id": r[4],
            "pagerank": r[5],
            "community": r[6],
            "district_id": r[7],
            "district": r[8],
            "canonical_person_id": int(r[9]) if r[9] is not None else None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Entity detail (profile)
# ---------------------------------------------------------------------------

def entity_detail(entity_id: int) -> Optional[dict]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT e."EntityID",e."EntityType"::text,e."Label",e."RefTable",e."RefID",'
                'e."AccusedMasterID",e."Attributes"::text,'
                'ST_X(e."geom")::float, ST_Y(e."geom")::float,'
                'e."CreatedAt"::text,e."CanonicalEntityID",ce."CanonicalPersonID" '
                'FROM "EntityGraph" e '
                'LEFT JOIN "CanonicalEntity" ce '
                'ON ce."CanonicalEntityID" = e."CanonicalEntityID" '
                'WHERE e."EntityID"=%s',
                (entity_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            import json
            attrs = json.loads(row[6]) if row[6] else {}
            canonical_entity_id = row[10]

            detail: dict[str, Any] = {
                "entity_id": int(row[0]),
                "entity_type": row[1],
                "label": row[2],
                "ref_table": row[3],
                "ref_id": row[4],
                "accused_master_id": row[5],
                "canonical_entity_id": canonical_entity_id,
                # Drives the profile's reference-photo action: the face gallery
                # is keyed on CanonicalPersonID, not EntityID.
                "canonical_person_id": int(row[11]) if row[11] is not None else None,
                "attributes": attrs,
                "longitude": row[7],
                "latitude": row[8],
                "created_at": row[9],
                "pagerank": attrs.get("pagerank"),
                "betweenness": attrs.get("betweenness"),
                "community": attrs.get("community"),
                "district_id": attrs.get("district_id"),
                "district": attrs.get("district"),
            }

            # Criminal history via CANONICAL identity (Phase 4): the entity's
            # CanonicalEntityID -> CanonicalPersonID -> CasePartyRole -> cases.
            # No name matching. Falls back to a direct AccusedMasterID link only.
            cases: list[dict] = []
            if canonical_entity_id is not None:
                cur.execute(
                    'SELECT DISTINCT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate"::text,'
                    ' ch."CrimeGroupName", st."CaseStatusName", r."RoleType" '
                    'FROM "CanonicalEntity" ce '
                    'JOIN "CasePartyRole" r ON r."CanonicalPersonID" = ce."CanonicalPersonID" '
                    'JOIN "CaseMaster" cm ON cm."CaseMasterID" = r."CaseMasterID" '
                    'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
                    'LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID" '
                    'WHERE ce."CanonicalEntityID" = %s '
                    # SELECT DISTINCT requires ORDER BY expressions to appear in the
                    # select list, so order by the same cast expression (a DATE cast
                    # to 'YYYY-MM-DD' text still sorts chronologically).
                    'ORDER BY cm."CrimeRegisteredDate"::text DESC NULLS LAST LIMIT 50',
                    (canonical_entity_id,),
                )
                for r2 in cur.fetchall():
                    cases.append({
                        "case_id": int(r2[0]), "crime_no": r2[1], "registered_date": r2[2],
                        "crime_group": r2[3], "status": r2[4], "role": r2[5],
                    })
            if not cases and row[5]:  # legacy fallback: direct AccusedMasterID link
                cur.execute(
                    'SELECT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate"::text,'
                    ' ch."CrimeGroupName", st."CaseStatusName" '
                    'FROM "Accused" a '
                    'JOIN "CaseMaster" cm ON cm."CaseMasterID" = a."CaseMasterID" '
                    'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
                    'LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID" '
                    'WHERE a."AccusedMasterID" = %s '
                    'ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST',
                    (row[5],),
                )
                for r2 in cur.fetchall():
                    cases.append({
                        "case_id": int(r2[0]), "crime_no": r2[1], "registered_date": r2[2],
                        "crime_group": r2[3], "status": r2[4], "role": "accused",
                    })
            detail["cases"] = cases

            # Gang membership
            cur.execute(
                'SELECT gm."GangEntityID", eg."Label" '
                'FROM "GangMembership" gm '
                'JOIN "EntityGraph" eg ON eg."EntityID" = gm."GangEntityID" '
                'WHERE gm."MemberEntityID" = %s',
                (entity_id,),
            )
            detail["gangs"] = [{"gang_id": int(r2[0]), "gang_name": r2[1]} for r2 in cur.fetchall()]

    return detail


# ---------------------------------------------------------------------------
# Communities (Louvain labels already written to EntityGraph.Attributes.community)
# ---------------------------------------------------------------------------

def list_communities(limit: int = 40) -> dict:
    """Communities ranked by size, cross-referenced with known gangs."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT ("Attributes"->>\'community\')::int AS community, '
                'COUNT(*) AS size, '
                'COUNT(*) FILTER (WHERE EXISTS('
                '  SELECT 1 FROM "GangMembership" gm WHERE gm."MemberEntityID" = e."EntityID")) '
                '  AS gang_members '
                'FROM "EntityGraph" e '
                'WHERE "Attributes" ? \'community\' '
                'GROUP BY 1 ORDER BY size DESC LIMIT %s',
                (limit,),
            )
            rows = cur.fetchall()
    return {
        "communities": [
            {"community": int(r[0]), "size": int(r[1]), "gang_members": int(r[2])}
            for r in rows if r[0] is not None
        ]
    }


# Provenanced, non-archived directed edges, both ways (undirected view).
_PROVENANCED_UD = (
    'SELECT "Source" AS a, "Target" AS b FROM "NetworkEdge" '
    'WHERE "ProvenanceStatus" IS NOT NULL AND COALESCE("IsArchived", FALSE) = FALSE '
    'UNION '
    'SELECT "Target" AS a, "Source" AS b FROM "NetworkEdge" '
    'WHERE "ProvenanceStatus" IS NOT NULL AND COALESCE("IsArchived", FALSE) = FALSE')

# Primary source: materialized hidden associations — pairs that share an
# intermediary (phone/vehicle/address/account) but are NOT directly linked, so
# the shortest path is a genuine >=2-hop chain THROUGH that shared intermediary.
# These are the most illustrative Path Finder demos (the "aha" connections).
_SUGG_HIDDEN = """
SELECT h."EntityA", ea."Label", h."EntityB", eb."Label",
       h."SharedIntermediaries"[1] AS via_id, ev."Label", ev."EntityType"::text
FROM "drishti_hidden_associations" h
JOIN "EntityGraph" ea ON ea."EntityID" = h."EntityA"
JOIN "EntityGraph" eb ON eb."EntityID" = h."EntityB"
JOIN "EntityGraph" ev ON ev."EntityID" = h."SharedIntermediaries"[1]
WHERE COALESCE(h."IsArchived", FALSE) = FALSE
  AND array_length(h."SharedIntermediaries", 1) >= 1
  AND NOT EXISTS (                              -- exclude directly-adjacent pairs
      SELECT 1 FROM "NetworkEdge" e
      WHERE e."ProvenanceStatus" IS NOT NULL AND COALESCE(e."IsArchived", FALSE) = FALSE
        AND ((e."Source" = h."EntityA" AND e."Target" = h."EntityB")
          OR (e."Source" = h."EntityB" AND e."Target" = h."EntityA")))
ORDER BY h."Score" DESC
LIMIT %s
"""

# Fallback (no hidden associations materialized): persons two hops apart via a
# shared neighbour, excluding any that are also directly connected.
_SUGG_TWO_HOP = """
WITH ud AS ({ud}),
pairs AS (
    SELECT u1.a AS a, u2.b AS b, u1.b AS via
    FROM ud u1 JOIN ud u2 ON u1.b = u2.a AND u1.a < u2.b
)
SELECT DISTINCT ON (p.a, p.b)
       p.a, ea."Label", p.b, eb."Label", p.via, ev."Label", ev."EntityType"::text
FROM pairs p
JOIN "EntityGraph" ea ON ea."EntityID" = p.a AND ea."EntityType" = 'person'
JOIN "EntityGraph" eb ON eb."EntityID" = p.b AND eb."EntityType" = 'person'
JOIN "EntityGraph" ev ON ev."EntityID" = p.via
WHERE NOT EXISTS (
    SELECT 1 FROM "NetworkEdge" e
    WHERE e."ProvenanceStatus" IS NOT NULL AND COALESCE(e."IsArchived", FALSE) = FALSE
      AND ((e."Source" = p.a AND e."Target" = p.b) OR (e."Source" = p.b AND e."Target" = p.a)))
ORDER BY p.a, p.b
LIMIT %s
""".format(ud=_PROVENANCED_UD)


def path_suggestions(limit: int = 6) -> dict:
    """A few ready-made, genuinely-connected entity pairs so the user can one-click
    a Path Finder demo instead of guessing two connected entities. Each pair has a
    real >=2-hop shortest path (they are NOT directly linked), shown through the
    shared intermediary that connects them."""
    limit = max(1, min(int(limit), 20))

    def _rows(cur, sql):
        cur.execute(sql, (limit,))
        return cur.fetchall()

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            rows: list = []
            try:
                rows = _rows(cur, _SUGG_HIDDEN)
            except Exception:            # noqa: BLE001 — table may not exist yet
                conn.rollback()
                rows = []
            if not rows:
                rows = _rows(cur, _SUGG_TWO_HOP)

    suggestions = [
        {
            "a": {"entity_id": int(r[0]), "label": r[1]},
            "b": {"entity_id": int(r[2]), "label": r[3]},
            "via": {"entity_id": int(r[4]), "label": r[5], "entity_type": r[6]},
        }
        for r in rows
    ]
    return {"suggestions": suggestions}


def community_subgraph(community_id: int, limit: int = 60) -> dict:
    """Top-N members of a community (by PageRank) plus their induced edges."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "EntityID","EntityType"::text,"Label",'
                '("Attributes"->>\'pagerank\')::float,'
                '("Attributes"->>\'betweenness\')::float,'
                '("Attributes"->>\'community\')::int '
                'FROM "EntityGraph" '
                'WHERE ("Attributes"->>\'community\')::int = %s '
                'ORDER BY ("Attributes"->>\'pagerank\')::float DESC NULLS LAST LIMIT %s',
                (community_id, limit),
            )
            node_rows = cur.fetchall()
            nodes = [
                {"entity_id": int(r[0]), "entity_type": r[1], "label": r[2],
                 "pagerank": r[3], "betweenness": r[4], "community": r[5]}
                for r in node_rows
            ]
            ids = [n["entity_id"] for n in nodes]
            edges = []
            if ids:
                cur.execute(
                    'SELECT "EdgeID","Source","Target","RelationshipType"::text,'
                    'COALESCE("Weight",0)::float '
                    'FROM "NetworkEdge" WHERE "Source" = ANY(%s) AND "Target" = ANY(%s)',
                    (ids, ids),
                )
                edges = [
                    {"edge_id": int(r[0]), "source": int(r[1]), "target": int(r[2]),
                     "relationship_type": r[3], "weight": r[4]}
                    for r in cur.fetchall()
                ]
    return {
        "community": community_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
