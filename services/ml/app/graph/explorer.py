"""Entity Explorer + Entity profile reads (Phase 15d — People & Entities).

Provides: paginated/filterable entity list, entity detail (identity +
criminal history + locations + gang membership), and linked-cases lookup.
All reads run under the restricted read-only role.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import db


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

    if entity_type:
        clauses.append('"EntityType"::text = %s')
        params.append(entity_type)
    if q:
        clauses.append('"SearchVector" @@ plainto_tsquery(%s)')
        params.append(q)
    if has_risk:
        clauses.append('EXISTS(SELECT 1 FROM "CrimeRiskScore" r WHERE r."EntityID"=e."EntityID")')
    if gang_affiliated:
        clauses.append('EXISTS(SELECT 1 FROM "GangMembership" gm WHERE gm."MemberEntityID"=e."EntityID")')
    if district_id:
        clauses.append('("Attributes"->>\'district_id\')::int = %s')
        params.append(district_id)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "EntityGraph" e{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "EntityID","EntityType"::text,"Label","RefTable","RefID",'
                f'("Attributes"->>\'pagerank\')::float,'
                f'("Attributes"->>\'community\')::int,'
                f'("Attributes"->>\'district_id\')::int,'
                f'"Attributes"->>\'district\' '
                f'FROM "EntityGraph" e{where} '
                f'ORDER BY "EntityID" DESC LIMIT %s OFFSET %s',
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
                'SELECT "EntityID","EntityType"::text,"Label","RefTable","RefID",'
                '"AccusedMasterID","Attributes"::text,'
                'ST_X("geom")::float, ST_Y("geom")::float,'
                '"CreatedAt"::text '
                'FROM "EntityGraph" WHERE "EntityID"=%s',
                (entity_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            import json
            attrs = json.loads(row[6]) if row[6] else {}

            detail: dict[str, Any] = {
                "entity_id": int(row[0]),
                "entity_type": row[1],
                "label": row[2],
                "ref_table": row[3],
                "ref_id": row[4],
                "accused_master_id": row[5],
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

            # Criminal history: cases linked via AccusedMasterID or RefTable/RefID
            cases: list[dict] = []
            if row[5]:  # AccusedMasterID
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
                        "case_id": int(r2[0]),
                        "crime_no": r2[1],
                        "registered_date": r2[2],
                        "crime_group": r2[3],
                        "status": r2[4],
                        "role": "accused",
                    })
            # Also try name match if label is person
            if row[1] == "person" and not cases:
                cur.execute(
                    'SELECT cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate"::text,'
                    ' ch."CrimeGroupName", st."CaseStatusName" '
                    'FROM "Accused" a '
                    'JOIN "CaseMaster" cm ON cm."CaseMasterID" = a."CaseMasterID" '
                    'LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
                    'LEFT JOIN "CaseStatusMaster" st ON st."CaseStatusID" = cm."CaseStatusID" '
                    'WHERE lower(trim(a."AccusedName")) = lower(trim(%s)) '
                    'GROUP BY cm."CaseMasterID", cm."CrimeNo", cm."CrimeRegisteredDate",'
                    ' ch."CrimeGroupName", st."CaseStatusName" '
                    'ORDER BY cm."CrimeRegisteredDate" DESC NULLS LAST LIMIT 30',
                    (row[2],),  # Label as name
                )
                for r2 in cur.fetchall():
                    cases.append({
                        "case_id": int(r2[0]),
                        "crime_no": r2[1],
                        "registered_date": r2[2],
                        "crime_group": r2[3],
                        "status": r2[4],
                        "role": "accused (name match)",
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
