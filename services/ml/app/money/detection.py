"""Money-laundering pattern detection (Phase 11, doc 04 §5).

Three detectors run over the (small) transaction graph and write their findings
back as typed state — FinancialTransaction.IsFlagged + FlagReason — plus
AlertHistory rows, with a ModelVersion + ModelInference audit (reproducible):

  * structuring / smurfing — an account fed by many sub-reporting-threshold
    deposits inside a short window (sliding-window fan-in of sub-threshold credits).
  * layering — large value moved THROUGH pass-through "conduit" accounts
    (in ~= out), i.e. the consolidation + cash-out legs of a chain.
  * circular — directed cycles in the flow (money returning to an origin).

The job is idempotent: it resets all flags, then re-applies them from the current
detection, so IsFlagged/FlagReason always reflect the analytics (not stale state).
Detection quality is scored against the injected ground truth (Properties->>'pattern')
as a demo metric — precision/recall per pattern, like the graph community job.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from psycopg2.extras import Json, execute_values

from .. import models

STRUCTURING_THRESHOLD = 50_000        # reporting threshold to stay under
SUBTHRESHOLD_FLOOR = 0.6              # only "just under" deposits count (>=0.6*T)


def _load(conn):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "TransactionID","SourceAccountID","DestinationAccountID","Amount",'
            '"TxnTimestamp", "Properties"->>\'pattern\', "EvidenceCaseID" '
            'FROM "FinancialTransaction"')
        txns = [(int(r[0]), int(r[1]), int(r[2]), float(r[3]), r[4], r[5],
                 int(r[6]) if r[6] is not None else None) for r in cur.fetchall()]
        cur.execute('SELECT "AccountID","EntityID","HolderName" FROM "FinancialAccount"')
        accts = {int(r[0]): {"entity_id": int(r[1]) if r[1] is not None else None,
                             "holder": r[2]} for r in cur.fetchall()}
    return txns, accts


# ---- detectors -------------------------------------------------------------
def detect_structuring(txns, threshold, min_count, window_days):
    """Destinations receiving >= min_count sub-threshold credits within any
    window_days window. Returns (flagged_txn_ids, {hub_account: info})."""
    lo = SUBTHRESHOLD_FLOOR * threshold
    win = dt.timedelta(days=window_days)
    by_dest: dict[int, list] = defaultdict(list)
    for tid, s, d, amt, ts, pat, ev in txns:
        if lo <= amt < threshold:
            by_dest[d].append((ts, tid, amt, ev))

    flagged: set[int] = set()
    hubs: dict[int, dict] = {}
    for dest, lst in by_dest.items():
        lst.sort(key=lambda x: x[0])
        times = [x[0] for x in lst]
        marked: set[int] = set()
        n = len(lst)
        for i in range(n):
            k = i
            while k + 1 < n and (times[k + 1] - times[i]) <= win:
                k += 1
            if k - i + 1 >= min_count:
                for m in range(i, k + 1):
                    marked.add(lst[m][1])
        if marked:
            flagged |= marked
            hub_txns = [x for x in lst if x[1] in marked]
            ev = next((x[3] for x in hub_txns if x[3] is not None), None)
            hubs[dest] = {"deposit_count": len(marked),
                          "total": round(sum(x[2] for x in hub_txns), 2),
                          "txn_ids": [x[1] for x in hub_txns][:25],
                          "evidence_case_id": ev}
    return flagged, hubs


def detect_layering(txns, threshold, min_conduit_amount, pass_ratio):
    """Large value moving through conduit accounts (total_in large, total_out ~
    total_in). Flags the large (>= threshold) legs into/out of conduits.
    Returns (flagged_txn_ids, conduit_accounts, chain_count)."""
    tin, tout = defaultdict(float), defaultdict(float)
    cin, cout = defaultdict(int), defaultdict(int)
    for tid, s, d, amt, ts, pat, ev in txns:
        tout[s] += amt; cout[s] += 1
        tin[d] += amt; cin[d] += 1
    conduits = {a for a in set(tin) | set(tout)
                if tin[a] >= min_conduit_amount and cin[a] >= 1 and cout[a] >= 1
                and tout[a] >= pass_ratio * tin[a]}

    flagged: set[int] = set()
    import networkx as nx
    chain = nx.DiGraph()
    for tid, s, d, amt, ts, pat, ev in txns:
        if amt >= threshold and (s in conduits or d in conduits):
            flagged.add(tid)
            if s in conduits and d in conduits:
                chain.add_edge(s, d)
    # count maximal conduit-to-conduit chains (weakly connected components of >=2)
    chain_count = sum(1 for c in nx.weakly_connected_components(chain) if len(c) >= 2)
    return flagged, conduits, chain_count


def detect_circular(txns, min_amount, max_len, max_cycles):
    """Directed cycles (money returning to an origin) over edges >= min_amount.
    Returns (flagged_txn_ids, cycles[list of node lists])."""
    import networkx as nx
    g = nx.DiGraph()
    edge_txns: dict[tuple, list] = defaultdict(list)
    for tid, s, d, amt, ts, pat, ev in txns:
        if amt >= min_amount and s != d:
            g.add_edge(s, d)
            edge_txns[(s, d)].append(tid)
    flagged: set[int] = set()
    cycles: list[list] = []
    for cyc in nx.simple_cycles(g, length_bound=max_len):
        cycles.append(cyc)
        for i in range(len(cyc)):
            for tid in edge_txns.get((cyc[i], cyc[(i + 1) % len(cyc)]), []):
                flagged.add(tid)
        if len(cycles) >= max_cycles:
            break
    return flagged, cycles


# ---- metrics vs injected ground truth --------------------------------------
def _metric(detected: set, gt: set) -> dict:
    tp = len(detected & gt)
    precision = tp / len(detected) if detected else 0.0
    recall = tp / len(gt) if gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"detected": len(detected), "ground_truth": len(gt), "true_positive": tp,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


# ---- orchestration ---------------------------------------------------------
def run_detection(conn, *, structuring_min_count: int = 5, structuring_window_days: int = 14,
                  layer_conduit_amount: float = 100_000, layer_pass_ratio: float = 0.6,
                  cycle_min_amount: float = 10_000, cycle_max_len: int = 6,
                  max_cycles: int = 200, max_alerts: int = 300) -> dict:
    txns, accts = _load(conn)
    threshold = STRUCTURING_THRESHOLD

    struct_flag, hubs = detect_structuring(txns, threshold, structuring_min_count, structuring_window_days)
    layer_flag, conduits, chain_count = detect_layering(txns, threshold, layer_conduit_amount, layer_pass_ratio)
    circ_flag, cycles = detect_circular(txns, cycle_min_amount, cycle_max_len, max_cycles)

    # single reason per txn, most-specific first
    reason: dict[int, str] = {}
    for tid in struct_flag:
        reason[tid] = "structuring"
    for tid in layer_flag:
        reason.setdefault(tid, "layering")
    for tid in circ_flag:
        reason.setdefault(tid, "circular")

    mv_id = models.get_or_create_model_version(
        conn, "drishti-money-aml", "anomaly_detection", "1.0.0", framework="networkx",
        hyperparameters={"threshold": threshold, "structuring_min_count": structuring_min_count,
                         "structuring_window_days": structuring_window_days,
                         "layer_conduit_amount": layer_conduit_amount,
                         "layer_pass_ratio": layer_pass_ratio,
                         "cycle_min_amount": cycle_min_amount, "cycle_max_len": cycle_max_len})

    # idempotent: reset then apply
    with conn.cursor() as cur:
        cur.execute('UPDATE "FinancialTransaction" SET "IsFlagged"=FALSE, "FlagReason"=NULL '
                    'WHERE "IsFlagged" OR "FlagReason" IS NOT NULL')
        if reason:
            execute_values(
                cur,
                'UPDATE "FinancialTransaction" t SET "IsFlagged"=TRUE, "FlagReason"=v.reason '
                'FROM (VALUES %s) AS v(tid, reason) WHERE t."TransactionID" = v.tid::bigint',
                list(reason.items()), template="(%s,%s)", page_size=2000)

    # ---- AlertHistory (ranked, capped) ----
    alerts: list[dict] = []
    for acct, info in hubs.items():
        owner = accts.get(acct, {}).get("entity_id")
        alerts.append({
            "type": "pattern_match", "severity": "high",
            "title": f"Structuring into account {acct}",
            "message": (f"{info['deposit_count']} sub-\u20b9{threshold:,.0f} deposits "
                        f"(\u20b9{info['total']:,.0f}) into account {acct} within {structuring_window_days} days."),
            "entity_id": owner, "case_id": info["evidence_case_id"],
            "payload": {"pattern": "structuring", "account_id": acct, **info},
            "rank": info["total"]})
    for cyc in cycles:
        alerts.append({
            "type": "pattern_match", "severity": "critical",
            "title": f"Circular flow across {len(cyc)} accounts",
            "message": f"Money returns to its origin through accounts {cyc}.",
            "entity_id": None, "case_id": None,
            "payload": {"pattern": "circular", "cycle_accounts": cyc},
            "rank": 1e12})   # cycles surface first
    for acct in list(conduits)[:max_alerts]:
        owner = accts.get(acct, {}).get("entity_id")
        alerts.append({
            "type": "pattern_match", "severity": "medium",
            "title": f"Layering conduit account {acct}",
            "message": f"Account {acct} passes large value through (in \u2248 out) — a layering conduit.",
            "entity_id": owner, "case_id": None,
            "payload": {"pattern": "layering", "account_id": acct},
            "rank": 0})

    sev_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    alerts.sort(key=lambda a: (sev_rank[a["severity"]], a["rank"]), reverse=True)
    alerts = alerts[:max_alerts]

    rows = []
    for a in alerts:
        rows.append((a["type"], a["severity"], a["title"], a["message"],
                     a["case_id"], a["entity_id"], mv_id, Json(a["payload"]), "open"))
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "AlertHistory" WHERE "ModelVersionID"=%s', (mv_id,))
        if rows:
            execute_values(
                cur,
                'INSERT INTO "AlertHistory" ("AlertType","Severity","Title","Message",'
                '"CaseMasterID","EntityID","ModelVersionID","Payload","Status") VALUES %s',
                rows, page_size=500)

    # ---- validation vs injected ground truth (Properties->>'pattern') ----
    gt_struct = {tid for tid, s, d, amt, ts, pat, ev in txns if pat == "structuring"}
    gt_layer = {tid for tid, s, d, amt, ts, pat, ev in txns if pat in ("layering", "fan_in")}
    validation = {"structuring": _metric(struct_flag, gt_struct),
                  "layering": _metric(layer_flag, gt_layer)}

    by_pattern = {"structuring": len(struct_flag), "layering": len(layer_flag),
                  "circular": len(circ_flag)}
    models.log_inference(
        conn, mv_id, ref_table="FinancialTransaction",
        inputs={"structuring_min_count": structuring_min_count,
                "structuring_window_days": structuring_window_days,
                "layer_conduit_amount": layer_conduit_amount, "cycle_min_amount": cycle_min_amount},
        outputs={"flagged": len(reason), "by_pattern": by_pattern, "validation": validation,
                 "alerts": len(rows)})

    return {"transactions_scanned": len(txns), "transactions_flagged": len(reason),
            "by_pattern": by_pattern, "alerts_written": len(rows),
            "structuring_hubs": len(hubs), "layering_chains": chain_count,
            "circular_flows": len(cycles), "validation": validation, "model_version_id": mv_id}
