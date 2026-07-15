"""Unified people + money subgraph (doc 04 §6-7).

When a FinancialAccount carries an EntityID, its account node joins the SAME
canvas as its owner's people-graph node. The two graphs merge *visually* — the
tables are not merged; nodes are simply typed by `kind` ('account' | 'entity')
and an 'owns' edge connects an entity to its accounts. Money edges are aggregated
transactions. Bounded BFS + node cap keep the canvas legible (anti-hairball).
"""
from __future__ import annotations

from typing import Optional

MAX_NODES = 200


def _seed_accounts(cur, entity_id, account_id):
    if account_id is not None:
        cur.execute('SELECT "AccountID" FROM "FinancialAccount" WHERE "AccountID"=%s', (account_id,))
        return ({account_id} if cur.fetchone() else None), "account", account_id
    cur.execute('SELECT 1 FROM "EntityGraph" WHERE "EntityID"=%s', (entity_id,))
    if not cur.fetchone():
        return None, "entity", entity_id
    cur.execute('SELECT "AccountID" FROM "FinancialAccount" WHERE "EntityID"=%s', (entity_id,))
    return {int(r[0]) for r in cur.fetchall()}, "entity", entity_id


def unified_subgraph(conn, *, entity_id: Optional[int] = None, account_id: Optional[int] = None,
                     max_hops: int = 2, top_n: int = 30) -> Optional[dict]:
    max_hops = max(1, min(int(max_hops), 4))
    with conn.cursor() as cur:
        seeds, seed_kind, seed_id = _seed_accounts(cur, entity_id, account_id)
        if seeds is None:
            return None

        accounts: set[int] = set(seeds)
        edges: dict[tuple, dict] = {}
        frontier = set(seeds)
        for _ in range(max_hops):
            if not frontier or len(accounts) >= MAX_NODES:
                break
            fl = list(frontier)
            cur.execute(
                'SELECT "SourceAccountID","DestinationAccountID", SUM("Amount"), COUNT(*), '
                'bool_or("IsFlagged"), MAX("FlagReason") '
                'FROM "FinancialTransaction" '
                'WHERE "SourceAccountID" = ANY(%s) OR "DestinationAccountID" = ANY(%s) '
                'GROUP BY 1,2 ORDER BY SUM("Amount") DESC LIMIT %s',
                (fl, fl, top_n * len(fl)))
            new: set[int] = set()
            for s, d, amt, cnt, flg, reason in cur.fetchall():
                s, d = int(s), int(d)
                edges[(s, d)] = {"amount": round(float(amt), 2), "txn_count": int(cnt),
                                 "is_flagged": bool(flg), "flag_reason": reason}
                for a in (s, d):
                    if a not in accounts and len(accounts) < MAX_NODES:
                        new.add(a); accounts.add(a)
            frontier = new

        # account details + owners
        acc_ids = list(accounts)
        cur.execute(
            'SELECT "AccountID","HolderName","AccountType"::text,"Bank","IsFlagged","EntityID" '
            'FROM "FinancialAccount" WHERE "AccountID" = ANY(%s)', (acc_ids,))
        acc_rows = {int(r[0]): {"label": r[1], "account_type": r[2], "bank": r[3],
                                "is_flagged": bool(r[4]),
                                "owner": int(r[5]) if r[5] is not None else None}
                    for r in cur.fetchall()}
        owner_ids = sorted({v["owner"] for v in acc_rows.values() if v["owner"] is not None})
        entities = {}
        if owner_ids:
            cur.execute('SELECT "EntityID","Label","EntityType"::text FROM "EntityGraph" '
                        'WHERE "EntityID" = ANY(%s)', (owner_ids,))
            entities = {int(r[0]): {"label": r[1], "entity_type": r[2]} for r in cur.fetchall()}

    # keep only edges whose endpoints survived the node cap
    edges = {k: v for k, v in edges.items() if k[0] in accounts and k[1] in accounts}

    nodes = []
    for aid in acc_ids:
        d = acc_rows.get(aid, {})
        nodes.append({"id": f"acct:{aid}", "kind": "account", "account_id": aid,
                      "label": d.get("label"), "account_type": d.get("account_type"),
                      "bank": d.get("bank"), "is_flagged": d.get("is_flagged", False)})
    for eid in owner_ids:
        e = entities.get(eid, {})
        nodes.append({"id": f"ent:{eid}", "kind": "entity", "entity_id": eid,
                      "label": e.get("label"), "entity_type": e.get("entity_type")})

    edge_list = []
    for (s, d), v in sorted(edges.items(), key=lambda kv: -kv[1]["amount"]):
        edge_list.append({"id": f"txn:{s}-{d}", "source": f"acct:{s}", "target": f"acct:{d}",
                          "kind": "transaction", **v})
    # ownership edges (entity -> account) — the people/money bridge
    for aid in acc_ids:
        owner = acc_rows.get(aid, {}).get("owner")
        if owner is not None:
            edge_list.append({"id": f"owns:{owner}-{aid}", "source": f"ent:{owner}",
                              "target": f"acct:{aid}", "kind": "owns"})

    return {"seed_kind": seed_kind, "seed_id": seed_id, "nodes": nodes, "edges": edge_list,
            "account_count": len(acc_ids), "entity_count": len(owner_ids)}
