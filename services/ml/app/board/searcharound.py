"""Search Around / subgraph import (Prompt 16 §F).

Reuses the COMPLETED canonical graph service (app.graph.queries) through the
read-only connection — the same expand-on-demand, capped-fan-out, no-hairball
rule as Network Analysis. It never reintroduces name matching: expansion is over
the id-keyed EntityGraph/NetworkEdge canonical graph only.

This module is a PURE READ (query + rank + cache). The board write (importing
verified relationships as read-only evidence nodes/edges with provenance) lives
in service.import behind the standard mutation path.

Caps: 1 hop default, 3 hops max, a required max_neighbors fan-out cap. Safe
query results are cached in Catalyst Cache keyed by the graph model/version so a
graph rebuild invalidates them.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .. import db
from ..analytics_adapter import get_analytics_adapter
from ..cache import SEG_LOOKUP
from ..graph import queries
from ..graph.service import GRAPH_MODEL
from .repo import board_cache

MAX_HOPS = 3
MAX_NEIGHBORS = 50
MAX_CASE_RELATED = 100

# The case canvas is an operational work surface, so seeding a FIR must carry
# the case's governed child records too—not only the three or four graph
# entities that happen to resolve through CasePartyRole.  Every identifier in
# this tuple is server-owned (never interpolated from a client value).
_CASE_RELATED_TABLES: tuple[tuple[str, str, str, str, str, str], ...] = (
    # ref table, PK, case FK, relationship label, visual group, node kind
    ("CasePartyRole", "CasePartyRoleID", "CaseMasterID",
     "case_party_role", "people", ""),
    ("Victim", "VictimMasterID", "CaseMasterID", "victim", "people", "victim"),
    ("ComplainantDetails", "ComplainantID", "CaseMasterID",
     "complainant", "people", "complainant"),
    ("Accused", "AccusedMasterID", "CaseMasterID", "accused", "people", "accused"),
    ("ArrestSurrender", "ArrestSurrenderID", "CaseMasterID",
     "arrest_or_surrender", "legal", "note"),
    ("ChargesheetDetails", "CSID", "CaseMasterID",
     "chargesheet_or_final_report", "legal", "document"),
    ("CaseEvent", "CaseEventID", "CaseMasterID",
     "lifecycle_event", "timeline", "note"),
    ("EvidenceItem", "EvidenceItemID", "CaseMasterID",
     "evidence", "evidence", "document"),
    ("Statement", "StatementID", "CaseMasterID",
     "statement", "evidence", "note"),
    ("Seizure", "SeizureID", "CaseMasterID", "seizure", "assets", "note"),
    ("PropertyItem", "PropertyItemID", "CaseMasterID",
     "property_or_seizure_item", "assets", "vehicle"),
    ("Device", "DeviceID", "CaseMasterID", "device", "digital", "phone"),
    ("CommunicationEvent", "CommunicationEventID", "CaseMasterID",
     "communication", "digital", "phone"),
    ("LocationObservation", "LocationObservationID", "CaseMasterID",
     "location_observation", "digital", "location"),
    ("CourtEvent", "CourtEventID", "CaseMasterID",
     "court_event", "court", "note"),
    ("BailEvent", "BailEventID", "CaseMasterID", "bail_event", "court", "note"),
    ("CaseDisposition", "CaseDispositionID", "CaseMasterID",
     "case_disposition", "court", "document"),
    ("LabResult", "LabResultID", "CaseMasterID",
     "lab_result", "evidence", "document"),
)


def _cache_key(entity_id: int, hops: int, max_neighbors: int,
               types: Optional[tuple[str, ...]]) -> str:
    t = ",".join(sorted(types)) if types else "*"
    # GRAPH_MODEL is bumped when the graph is rebuilt -> natural invalidation.
    return f"board:sa:{GRAPH_MODEL}:{entity_id}:{hops}:{max_neighbors}:{t}"


def _within_window(attrs: dict, time_from: Optional[str], time_to: Optional[str]) -> bool:
    if not (time_from or time_to):
        return True
    # best-effort: entities carry a last-seen/observed date in Attributes when known
    ts = None
    for k in ("last_seen", "observed_at", "date", "created_at"):
        if attrs.get(k):
            ts = str(attrs[k])
            break
    if ts is None:
        return True                      # no temporal info -> never hide it
    if time_from and ts < time_from:
        return False
    if time_to and ts > time_to:
        return False
    return True


def expand(entity_id: int, hops: int, max_neighbors: int, *,
           types: Optional[list[str]] = None, time_from: Optional[str] = None,
           time_to: Optional[str] = None) -> dict[str, Any]:
    """Capped N-hop expansion around a canonical graph entity. Pure read."""
    hops = max(1, min(int(hops), MAX_HOPS))
    max_neighbors = max(1, min(int(max_neighbors), MAX_NEIGHBORS))
    type_filter = tuple(sorted(types)) if types else None

    cache = board_cache()
    ckey = _cache_key(entity_id, hops, max_neighbors, type_filter)
    if not (time_from or time_to):
        try:
            hit = cache.get(SEG_LOOKUP, ckey)
        except Exception:  # noqa: BLE001
            hit = None
        if hit:
            data = json.loads(hit)
            data["cached"] = True
            return data

    t0 = time.time()
    # Prompt 21 §C.3: in the deployed AppSail the graph-heavy subgraph is fetched
    # through the PROTECTED AWS analytics adapter (typed, signed, capped), never a
    # direct AppSail->RDS connection. The local read-only graph path remains ONLY
    # as the dev fallback when the adapter is not configured (board is tracked as
    # migration_pending in the route-data-boundary inventory until that is removed).
    adapter = get_analytics_adapter()
    if adapter is not None:
        exists, nodes, edges = adapter.graph_neighbourhood(
            entity_id, hops, max_neighbors, types=list(type_filter) if type_filter else None)
        fetch_source = "aws-analytics-adapter"
    else:
        with db.ro_conn() as conn:
            exists = _entity_exists(conn, entity_id)
            nodes, edges = ([], [])
            if exists:
                nodes, edges = queries.neighbourhood(conn, entity_id, hops, max_neighbors)
        fetch_source = "rds-direct(dev-fallback)"
    latency_ms = int((time.time() - t0) * 1000)

    neighbors = []
    for n in nodes:
        if int(n["entity_id"]) == int(entity_id):
            continue
        if type_filter and (n.get("entity_type") not in type_filter):
            continue
        if not _within_window(n.get("attributes") or {}, time_from, time_to):
            continue
        neighbors.append({
            "entity_id": int(n["entity_id"]), "label": n.get("label"),
            "entity_type": n.get("entity_type"), "distance": n.get("distance"),
            "relationship_type": None, "weight": 0.0,
            # curated EntityGraph/NetworkEdge projections are reviewed/provenanced
            # (candidate edges stay in AWS) -> treat as verified evidence.
            "verified": True,
        })
    # attach the heaviest incident relationship type/weight to each neighbor
    by_node: dict[int, tuple[str, float]] = {}
    for e in edges:
        for endpoint in (int(e["source"]), int(e["target"])):
            w = float(e.get("weight") or 0.0)
            cur = by_node.get(endpoint)
            if cur is None or w > cur[1]:
                by_node[endpoint] = (e.get("relationship_type"), w)
    for nb in neighbors:
        rt = by_node.get(nb["entity_id"])
        if rt:
            nb["relationship_type"], nb["weight"] = rt[0], rt[1]
    neighbors.sort(key=lambda x: x["weight"], reverse=True)

    # Final cap: the recursive BFS fans out to the top-N heaviest neighbours PER
    # HOP, so a multi-hop expansion can surface more than ``max_neighbors`` nodes
    # in total. ``max_neighbors`` is the cap on the RETURNED neighbour set, so
    # keep only the strongest by edge weight — Search Around must never return
    # more nodes than its cap (no hairball). Then reduce the induced edge set to
    # the kept nodes so the imported subgraph has no dangling edges.
    if len(neighbors) > max_neighbors:
        neighbors = neighbors[:max_neighbors]
    kept_ids = {int(entity_id)} | {int(nb["entity_id"]) for nb in neighbors}
    edges = [e for e in edges
             if int(e["source"]) in kept_ids and int(e["target"]) in kept_ids]

    focal_label = next((n.get("label") for n in nodes
                        if int(n["entity_id"]) == int(entity_id)), str(entity_id))
    result = {
        "focal_entity": entity_id, "focal_label": focal_label, "hops": hops,
        "max_neighbors": max_neighbors, "node_count": len(kept_ids),
        "edge_count": len(edges), "neighbors": neighbors, "edges": edges,
        "latency_ms": latency_ms, "cached": False, "exists": exists,
        "answer": (f"{len(neighbors)} verified neighbour(s) within {hops} hop(s) of "
                   f"{focal_label}." if exists else f"Entity {entity_id} not found."),
        "reasoning": (f"Capped recursive-CTE BFS over the canonical id-keyed graph, "
                      f"fan-out top {max_neighbors} by edge weight; no name matching."),
        "model": GRAPH_MODEL,
        "fetch_source": fetch_source,
    }
    if not (time_from or time_to):
        try:
            cache.put(SEG_LOOKUP, ckey, json.dumps(result))
        except Exception:  # noqa: BLE001
            pass
    return result


def _entity_exists(conn, entity_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "EntityGraph" WHERE "EntityID"=%s', (entity_id,))
        return cur.fetchone() is not None


def benchmark_two_hop(entity_id: int, max_neighbors: int = 15) -> dict[str, Any]:
    """Two-hop capped expansion benchmark (Prompt 16 §F.7). Records the measured
    node/edge counts + latency; the environment is documented in the report."""
    t0 = time.time()
    res = expand(entity_id, hops=2, max_neighbors=max_neighbors)
    return {
        "entity_id": entity_id, "hops": 2, "max_neighbors": max_neighbors,
        "node_count": res["node_count"], "edge_count": res["edge_count"],
        "latency_ms": int((time.time() - t0) * 1000),
        "graph_latency_ms": res["latency_ms"], "cached": res["cached"],
        "target_ms": 2000, "model": res["model"],
    }


def entities_for_case(case_master_id: int, limit: int = 12) -> list[dict[str, Any]]:
    """Best-effort: resolve a case to the EntityGraph entities of its parties.

    Joins ``CasePartyRole`` (the FIR's accused/victim/complainant/witness rows)
    to the canonical ``EntityGraph`` node for each party. Read-only, id-keyed
    (never name matching). NEVER raises into the request path: returns ``[]`` on
    any schema variation or store-unavailable condition, so a case seed always
    degrades to a plain single-node pin.

    Returns ``[{entity_id, label, entity_type, role}]`` ranked by role priority
    (accused first) then entity id, capped at ``limit``.
    """
    try:
        cid = int(case_master_id)
    except (TypeError, ValueError):
        return []
    # Parties resolve through the canonical identity bridge. CanonicalPersonID
    # and CanonicalEntityID are different key domains; comparing either value
    # directly with EntityGraph.RefID can attach an unrelated person whose
    # numeric id happens to match.
    sql = (
        'SELECT eg."EntityID", eg."Label", eg."EntityType"::text, cpr."RoleType"::text '
        'FROM "CasePartyRole" cpr '
        'JOIN "CanonicalEntity" ce '
        '  ON (ce."CanonicalPersonID" = cpr."CanonicalPersonID" '
        '      OR ce."CanonicalOrganisationID" = cpr."CanonicalOrganisationID") '
        'JOIN "EntityGraph" eg '
        '  ON eg."CanonicalEntityID" = ce."CanonicalEntityID" '
        'WHERE cpr."CaseMasterID" = %s '
        'LIMIT %s'
    )
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (cid, max(1, min(int(limit), MAX_NEIGHBORS))))
                rows = cur.fetchall()
    except Exception:  # noqa: BLE001 — must never break the seed path
        return []
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    _priority = {"accused": 0, "suspect": 0, "victim": 1, "complainant": 2}
    for r in rows:
        try:
            eid = int(r[0])
        except (TypeError, ValueError):
            continue
        if eid in seen:
            continue
        seen.add(eid)
        out.append({"entity_id": eid, "label": r[1], "entity_type": r[2],
                    "role": (r[3] or "party")})
    out.sort(key=lambda d: (_priority.get(str(d.get("role") or "").lower(), 5),
                            d["entity_id"]))
    return out


def related_records_for_case(case_master_id: int,
                             limit: int = MAX_CASE_RELATED) -> list[dict[str, Any]]:
    """Return governed records that make up the complete operational case view.

    The old seed path only resolved CasePartyRole -> EntityGraph, which is why a
    rich FIR appeared as four nodes.  This read gathers the same bounded,
    typed records surfaced by the case-file tabs (people, legal, evidence,
    property, digital, financial and court/lifecycle).  It is deliberately
    schema-tolerant: tables absent from a deployment are skipped, while the
    remaining records still seed successfully.

    Returned rows contain only source identifiers and relationship metadata;
    labels and safe snapshots are hydrated later through the reference
    whitelist.  Composite Act/Section rows are the sole exception and carry a
    small sanitised snapshot because the source table has a composite key.
    """
    try:
        cid = int(case_master_id)
        cap = max(1, min(int(limit), MAX_CASE_RELATED))
    except (TypeError, ValueError):
        return []

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def append_record(ref_table: str, ref_id: Any, relationship: str, group: str,
                      node_kind: str, *, snapshot: Optional[dict[str, Any]] = None,
                      label: Optional[str] = None) -> None:
        if ref_id is None or len(records) >= cap:
            return
        key = (ref_table, str(ref_id))
        if key in seen:
            return
        seen.add(key)
        records.append({
            "ref_table": ref_table,
            "ref_id": str(ref_id),
            "relationship": relationship,
            "group": group,
            "node_kind": node_kind,
            "snapshot": snapshot,
            "label": label,
        })

    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                # Introspect once.  A missing optional migration then degrades
                # cleanly without issuing a query that aborts the transaction.
                cur.execute(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema='public'")
                available: dict[str, set[str]] = {}
                for table_name, column_name in cur.fetchall():
                    available.setdefault(str(table_name), set()).add(str(column_name))

                for (table, pk, case_fk, relationship, group,
                     node_kind) in _CASE_RELATED_TABLES:
                    cols = available.get(table, set())
                    if pk not in cols or case_fk not in cols:
                        continue
                    cur.execute(
                        f'SELECT "{pk}" FROM "{table}" '
                        f'WHERE "{case_fk}"=%s ORDER BY "{pk}" LIMIT %s',
                        (cid, cap))
                    for row in cur.fetchall():
                        append_record(table, row[0], relationship, group, node_kind)

                # Evidence can be linked M:N even when EvidenceItem.CaseMasterID
                # is empty.  Pull those references without duplicating direct
                # evidence rows.
                if ({"EvidenceCaseLink", "EvidenceItem"} <= set(available)
                        and {"CaseMasterID", "EvidenceItemID"}
                        <= available["EvidenceCaseLink"]):
                    cur.execute(
                        'SELECT "EvidenceItemID" FROM "EvidenceCaseLink" '
                        'WHERE "CaseMasterID"=%s ORDER BY "EvidenceItemID" LIMIT %s',
                        (cid, cap))
                    for row in cur.fetchall():
                        append_record("EvidenceItem", row[0], "evidence",
                                      "evidence", "document")

                # Device artifacts inherit case scope through their parent
                # Device, but remain live references of their own.
                if ({"Device", "DeviceArtifact"} <= set(available)
                        and {"DeviceID", "CaseMasterID"} <= available["Device"]
                        and {"DeviceArtifactID", "DeviceID"}
                        <= available["DeviceArtifact"]):
                    cur.execute(
                        'SELECT da."DeviceArtifactID" FROM "DeviceArtifact" da '
                        'JOIN "Device" d ON d."DeviceID"=da."DeviceID" '
                        'WHERE d."CaseMasterID"=%s '
                        'ORDER BY da."DeviceArtifactID" LIMIT %s', (cid, cap))
                    for row in cur.fetchall():
                        append_record("DeviceArtifact", row[0], "device_artifact",
                                      "digital", "document")

                # Transactions may be linked directly or through TransactionLink.
                if ("FinancialTransaction" in available
                        and "TransactionID" in available["FinancialTransaction"]):
                    txn_ids: list[Any] = []
                    if "EvidenceCaseID" in available["FinancialTransaction"]:
                        cur.execute(
                            'SELECT "TransactionID" FROM "FinancialTransaction" '
                            'WHERE "EvidenceCaseID"=%s ORDER BY "TransactionID" LIMIT %s',
                            (cid, cap))
                        txn_ids.extend(r[0] for r in cur.fetchall())
                    if ("TransactionLink" in available
                            and {"TransactionID", "CaseMasterID"}
                            <= available["TransactionLink"]):
                        cur.execute(
                            'SELECT "TransactionID" FROM "TransactionLink" '
                            'WHERE "CaseMasterID"=%s ORDER BY "TransactionID" LIMIT %s',
                            (cid, cap))
                        txn_ids.extend(r[0] for r in cur.fetchall())
                    for txn_id in txn_ids:
                        append_record("FinancialTransaction", txn_id,
                                      "financial_transaction", "financial", "account")

                # ActSectionAssociation has a governed composite key.  Preserve
                # every section as a source-backed fact node with explicit
                # composite provenance rather than pretending CaseMasterID is a
                # unique reference.
                act_cols = available.get("ActSectionAssociation", set())
                if {"CaseMasterID", "ActID", "SectionID"} <= act_cols:
                    cur.execute(
                        'SELECT "ActID", "SectionID", "ActOrderID", "SectionOrderID" '
                        'FROM "ActSectionAssociation" WHERE "CaseMasterID"=%s '
                        'ORDER BY "ActOrderID" NULLS LAST, "SectionOrderID" NULLS LAST, '
                        '"ActID", "SectionID" LIMIT %s', (cid, cap))
                    for act_id, section_id, act_order, section_order in cur.fetchall():
                        composite_id = f"{cid}:{act_id}:{section_id}"
                        append_record(
                            "ActSectionAssociation", composite_id,
                            "act_and_section", "legal", "note",
                            snapshot={
                                "CaseMasterID": cid,
                                "ActID": act_id,
                                "SectionID": section_id,
                                "ActOrderID": act_order,
                                "SectionOrderID": section_order,
                                "SourceRef": (
                                    f"ActSectionAssociation:{cid}:{act_id}:{section_id}"
                                ),
                            },
                            label=f"{act_id} {section_id}".strip(),
                        )
    except Exception:  # noqa: BLE001 - case enrichment must never break a plain pin
        return records

    _group_order = {
        "people": 0, "legal": 1, "evidence": 2, "assets": 3,
        "digital": 4, "financial": 5, "court": 6, "timeline": 7,
    }
    records.sort(key=lambda item: (
        _group_order.get(str(item.get("group")), 99),
        str(item.get("ref_table")), str(item.get("ref_id")),
    ))
    return records[:cap]
