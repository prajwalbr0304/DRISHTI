"""Graph enrichment batch job (Phase 6 prerequisite).

The generated graph has only `person` and `gang` nodes with person-person and
gang-member edges. The hidden-association detector (doc 04 §6) needs entities
that share DISTINCT *kinds* of intermediary (phone, vehicle, address, account).
This job adds those intermediary nodes + edges so every downstream algorithm has
a realistic multi-modal graph to work on, and seeds a handful of explicit
"impossible-to-spot-in-Excel" hidden associations for the demo/tests.

Design:
  * Every person gets a unique personal phone + home address (+ vehicle for ~40%)
    — degree-1 footprint, realistic, creates no false associations.
  * Each gang gets a shared safehouse (location), a shared vehicle, a burner phone
    and a mule bank_account; ALL its members link to them. Gang members therefore
    share up to 4 distinct intermediary kinds — organic hidden associations for
    every gang pair that was never co-accused.
  * A set of explicit cross-context flagship pairs (no shared gang, no co-accused
    edge) are given 2-3 fresh shared intermediaries so the ranked feed has crisp,
    non-obvious top hits.

Idempotent: deletes previously-enriched intermediary nodes (and their edges)
before rebuilding. Deterministic (fixed seed) so seeded pairs are stable.
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Tuple

from psycopg2.extras import execute_values

from .. import db

INTERMEDIARY_TYPES = ("phone", "vehicle", "location", "bank_account")
REL_FOR_TYPE = {
    "phone": "communication",
    "vehicle": "vehicle_link",
    "location": "same_location",
    "bank_account": "financial",
}
_ENRICH_TAG = "phase6_enrich"

_KA_RTO = ["KA01", "KA02", "KA03", "KA05", "KA09", "KA19", "KA51", "KA53"]
_STREETS = ["MG Road", "Brigade Rd", "Jayanagar", "Whitefield", "Hubli Rd",
            "Station Rd", "Market Rd", "Gandhi Nagar", "Vidyanagar", "Basaveshwara Nagar"]
_BANKS = ["SBIN", "CNRB", "KARB", "HDFC", "ICIC", "UTIB"]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def clear_enrichment(conn) -> dict:
    """Remove previously-enriched intermediary nodes + their edges (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT \"EntityID\" FROM \"EntityGraph\" "
            "WHERE \"EntityType\"::text = ANY(%s) AND \"Attributes\"->>'source' = %s",
            (list(INTERMEDIARY_TYPES), _ENRICH_TAG),
        )
        ids = [r[0] for r in cur.fetchall()]
        if ids:
            cur.execute(
                'DELETE FROM "NetworkEdge" WHERE "Source" = ANY(%s) OR "Target" = ANY(%s)',
                (ids, ids),
            )
            # hidden_associations FK cascades on EntityGraph delete
            cur.execute('DELETE FROM "EntityGraph" WHERE "EntityID" = ANY(%s)', (ids,))
    return {"removed_nodes": len(ids)}


def _load_context(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT \"EntityID\" FROM \"EntityGraph\" WHERE \"EntityType\"='person' ORDER BY \"EntityID\"")
        persons = [r[0] for r in cur.fetchall()]
        # gang -> [member entity ids]
        cur.execute(
            'SELECT "GangEntityID", "MemberEntityID" FROM "GangMembership" '
            'WHERE "MemberEntityID" IS NOT NULL'
        )
        gangs: Dict[int, List[int]] = {}
        gang_members = set()
        for g, m in cur.fetchall():
            gangs.setdefault(g, []).append(m)
            gang_members.add(m)
        # persons that are co-accused with someone (excluded from flagship seeding)
        cur.execute("SELECT \"Source\", \"Target\" FROM \"NetworkEdge\" WHERE \"RelationshipType\"='co_accused'")
        co_accused = set()
        for s, t in cur.fetchall():
            co_accused.add(s)
            co_accused.add(t)
        cur.execute('SELECT COALESCE(MAX("EntityID"),0) FROM "EntityGraph"')
        max_eid = cur.fetchone()[0]
        cur.execute('SELECT COALESCE(MAX("EdgeID"),0) FROM "NetworkEdge"')
        max_edge = cur.fetchone()[0]
    return persons, gangs, gang_members, co_accused, max_eid, max_edge


def enrich(conn, seed: int = 42, vehicle_fraction: float = 0.4,
           n_flagship: int = 12, n_secondary: int = 40) -> dict:
    rng = _rng(seed)
    clear_enrichment(conn)
    persons, gangs, gang_members, co_accused, max_eid, max_edge = _load_context(conn)

    nodes: List[tuple] = []   # (EntityID, EntityType, Label, RefTable, RefID, Attributes)
    edges: List[tuple] = []   # (EdgeID, Source, Target, RelationshipType, Cost, ReverseCost, Weight, Confidence, Properties)
    eid = max_eid
    edge_id = max_edge

    def new_node(etype: str, label: str, attrs: dict) -> int:
        nonlocal eid
        eid += 1
        attrs = {**attrs, "source": _ENRICH_TAG}
        nodes.append((eid, etype, label, etype, str(eid), json.dumps(attrs)))
        return eid

    def link(person: int, inter: int, etype: str, weight: float, props: dict) -> None:
        nonlocal edge_id
        edge_id += 1
        cost = round(1.0 / max(weight, 0.05), 4)
        edges.append((edge_id, person, inter, REL_FOR_TYPE[etype], cost, cost,
                      round(weight, 3), 0.9, json.dumps({**props, "source": _ENRICH_TAG})))

    def phone_no() -> str:
        return "9" + "".join(str(rng.randint(0, 9)) for _ in range(9))

    def plate() -> str:
        return f"{rng.choice(_KA_RTO)}{chr(rng.randint(65,90))}{chr(rng.randint(65,90))}{rng.randint(1000,9999)}"

    def address() -> str:
        return f"#{rng.randint(1,400)}, {rng.choice(_STREETS)}"

    def acct_no(prefix: str) -> str:
        return f"{rng.choice(_BANKS)}-{prefix}-{rng.randint(10**7, 10**8 - 1)}"

    # 1. personal footprint (degree-1, no false sharing)
    for p in persons:
        link(p, new_node("phone", phone_no(), {"role": "personal"}), "phone", 0.6, {"kind": "personal"})
        link(p, new_node("location", address(), {"role": "home"}), "location", 0.55, {"kind": "home"})
        if rng.random() < vehicle_fraction:
            link(p, new_node("vehicle", plate(), {"role": "owner"}), "vehicle", 0.6, {"kind": "owned"})

    # 2. gang overlay — members share safehouse + vehicle + burner + mule account
    gang_pairs = 0
    for gi, members in gangs.items():
        if len(members) < 2:
            continue
        safehouse = new_node("location", address(), {"role": "safehouse", "gang_entity": gi})
        gvehicle = new_node("vehicle", plate(), {"role": "gang_vehicle", "gang_entity": gi})
        burner = new_node("phone", phone_no(), {"role": "burner", "gang_entity": gi})
        mule = new_node("bank_account", acct_no("MULE"), {"role": "mule", "gang_entity": gi})
        for m in members:
            link(m, safehouse, "location", 0.85, {"kind": "safehouse", "gang_entity": gi})
            link(m, gvehicle, "vehicle", 0.8, {"kind": "gang_vehicle", "gang_entity": gi})
            link(m, burner, "phone", 0.8, {"kind": "burner", "gang_entity": gi})
            link(m, mule, "bank_account", 0.85, {"kind": "mule", "gang_entity": gi})
        gang_pairs += len(members) * (len(members) - 1) // 2

    # 3. flagship + secondary seeded hidden associations (cross-context, non-obvious)
    clean = [p for p in persons if p not in gang_members and p not in co_accused]
    rng.shuffle(clean)
    seeded: List[Tuple[int, int, List[str]]] = []
    it = iter(clean)

    def _pair():
        return next(it), next(it)

    try:
        for _ in range(n_flagship):  # share 3 kinds -> top of the feed
            a, b = _pair()
            ph = new_node("phone", phone_no(), {"role": "shared", "seed_pair": [a, b]})
            ve = new_node("vehicle", plate(), {"role": "shared", "seed_pair": [a, b]})
            lo = new_node("location", address(), {"role": "shared", "seed_pair": [a, b]})
            for inter, t in ((ph, "phone"), (ve, "vehicle"), (lo, "location")):
                link(a, inter, t, 0.9, {"kind": "seeded_flagship"})
                link(b, inter, t, 0.9, {"kind": "seeded_flagship"})
            seeded.append((min(a, b), max(a, b), ["phone", "vehicle", "location"]))
        for _ in range(n_secondary):  # share 2 kinds
            a, b = _pair()
            ph = new_node("phone", phone_no(), {"role": "shared", "seed_pair": [a, b]})
            ac = new_node("bank_account", acct_no("SHR"), {"role": "shared", "seed_pair": [a, b]})
            for inter, t in ((ph, "phone"), (ac, "bank_account")):
                link(a, inter, t, 0.85, {"kind": "seeded_secondary"})
                link(b, inter, t, 0.85, {"kind": "seeded_secondary"})
            seeded.append((min(a, b), max(a, b), ["phone", "bank_account"]))
    except StopIteration:
        pass

    # bulk insert
    with conn.cursor() as cur:
        execute_values(
            cur,
            'INSERT INTO "EntityGraph" ("EntityID","EntityType","Label","RefTable","RefID","Attributes") VALUES %s',
            nodes, page_size=5000,
        )
        execute_values(
            cur,
            'INSERT INTO "NetworkEdge" ("EdgeID","Source","Target","RelationshipType",'
            '"Cost","ReverseCost","Weight","Confidence","Properties") VALUES %s',
            edges, page_size=5000,
        )
        # advance identity sequences past explicit ids
        cur.execute(f'ALTER TABLE "EntityGraph" ALTER COLUMN "EntityID" RESTART WITH {eid + 1}')
        cur.execute(f'ALTER TABLE "NetworkEdge" ALTER COLUMN "EdgeID" RESTART WITH {edge_id + 1}')

    return {
        "intermediary_nodes": len(nodes),
        "intermediary_edges": len(edges),
        "gangs_overlaid": sum(1 for m in gangs.values() if len(m) >= 2),
        "approx_gang_pairs": gang_pairs,
        "seeded_pairs": len(seeded),
        "seeded_examples": seeded[:5],
    }


def run(seed: int = 42) -> dict:
    with db.rw_conn() as conn:
        return enrich(conn, seed=seed)
