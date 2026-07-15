"""Multi-hop money-trail tracing (doc 04 §5 pattern D).

A recursive CTE walks FinancialTransaction forward from a start account, with a
cycle guard (an account already on the path is never re-entered), bounded by
max_hops. Parallel transactions between the same two accounts are aggregated into
one weighted edge, giving the directed weighted flow a Sankey renders. Read-only.
"""
from __future__ import annotations

from typing import Optional

# hop-bounded, cycle-guarded forward trace. Cycle guard: never re-enter an
# account already on the path (prevents infinite loops through cycles).
_TRACE_SQL = '''
WITH RECURSIVE trail AS (
    SELECT t."TransactionID", t."SourceAccountID", t."DestinationAccountID",
           t."Amount", t."IsFlagged", t."FlagReason", 1 AS hop,
           ARRAY[t."SourceAccountID", t."DestinationAccountID"] AS path
    FROM "FinancialTransaction" t
    WHERE t."SourceAccountID" = %(start)s
    UNION ALL
    SELECT t."TransactionID", t."SourceAccountID", t."DestinationAccountID",
           t."Amount", t."IsFlagged", t."FlagReason", tr.hop + 1,
           tr.path || t."DestinationAccountID"
    FROM "FinancialTransaction" t
    JOIN trail tr ON t."SourceAccountID" = tr."DestinationAccountID"
    WHERE tr.hop < %(max_hops)s
      AND NOT t."DestinationAccountID" = ANY(tr.path)   -- cycle guard
)
SELECT "TransactionID", "SourceAccountID", "DestinationAccountID",
       "Amount", "IsFlagged", "FlagReason", MIN(hop) AS hop
FROM trail
GROUP BY "TransactionID", "SourceAccountID", "DestinationAccountID",
         "Amount", "IsFlagged", "FlagReason"
LIMIT %(max_rows)s
'''

_MAX_IDS_PER_EDGE = 25


def _account_details(cur, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    cur.execute(
        'SELECT "AccountID","HolderName","AccountType"::text,"Bank","IsFlagged","EntityID" '
        'FROM "FinancialAccount" WHERE "AccountID" = ANY(%s)', (ids,))
    return {int(r[0]): {"label": r[1], "account_type": r[2], "bank": r[3],
                        "is_flagged": bool(r[4]),
                        "owner_entity_id": int(r[5]) if r[5] is not None else None}
            for r in cur.fetchall()}


def trace(conn, start_account: int, max_hops: int = 4, max_rows: int = 5000) -> Optional[dict]:
    """Return {nodes, edges, total_traced_amount, hops} or None if the account
    doesn't exist. Edges are (source,dest)-aggregated weighted flows."""
    max_hops = max(1, min(int(max_hops), 6))
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "FinancialAccount" WHERE "AccountID"=%s', (start_account,))
        if not cur.fetchone():
            return None
        cur.execute(_TRACE_SQL, {"start": start_account, "max_hops": max_hops, "max_rows": max_rows})
        raw = cur.fetchall()   # (txn_id, src, dst, amount, flagged, reason, hop)

        # aggregate parallel txns into weighted directed edges
        edges: dict[tuple[int, int], dict] = {}
        node_hop: dict[int, int] = {start_account: 0}
        total = 0.0
        for txn_id, src, dst, amount, flagged, reason, hop in raw:
            src, dst, amount = int(src), int(dst), float(amount)
            total += amount
            node_hop[src] = min(node_hop.get(src, hop), hop - 1 if hop else 0)
            node_hop[dst] = min(node_hop.get(dst, hop), hop)
            key = (src, dst)
            e = edges.get(key)
            if e is None:
                e = edges[key] = {"source_account": src, "target_account": dst, "amount": 0.0,
                                  "txn_count": 0, "is_flagged": False, "flag_reasons": set(),
                                  "transaction_ids": [], "hop": hop}
            e["amount"] += amount
            e["txn_count"] += 1
            e["hop"] = min(e["hop"], hop)
            if flagged:
                e["is_flagged"] = True
            if reason:
                e["flag_reasons"].add(reason)
            if len(e["transaction_ids"]) < _MAX_IDS_PER_EDGE:
                e["transaction_ids"].append(int(txn_id))

        details = _account_details(cur, list(node_hop))

    nodes = []
    for aid, hop in sorted(node_hop.items(), key=lambda kv: kv[1]):
        d = details.get(aid, {})
        nodes.append({"account_id": aid, "hop": hop, "label": d.get("label"),
                      "account_type": d.get("account_type"), "bank": d.get("bank"),
                      "is_flagged": d.get("is_flagged", False),
                      "owner_entity_id": d.get("owner_entity_id")})
    edge_list = []
    for e in sorted(edges.values(), key=lambda x: -x["amount"]):
        e["amount"] = round(e["amount"], 2)
        e["flag_reasons"] = sorted(e["flag_reasons"])
        edge_list.append(e)

    return {"nodes": nodes, "edges": edge_list, "total_traced_amount": round(total, 2),
            "hops": max_hops, "raw_txn_count": len(raw)}
