"""Money-trail service: AiResult envelopes over the trace / detection / unified /
flagged payloads. Reads run read-only; the detection job runs read-write. Every
finding returns provenance (record ids)."""
from __future__ import annotations

from typing import Optional

from .. import db
from ..contracts import AiResult
from . import detection, trace as trace_mod, unified as unified_mod
from .schemas import (DetectionResponse, FlaggedFeedResponse, FlaggedTxn,
                      PatternMetric, TraceEdge, TraceNode, TraceResponse,
                      UnifiedEdge, UnifiedNode, UnifiedResponse)

MONEY_MODEL = "drishti-money@1.0.0"       # deterministic trace/graph queries


# ---- 1. multi-hop trace ----------------------------------------------------
def trace(start_account: int, max_hops: int = 4) -> Optional[TraceResponse]:
    with db.ro_conn() as conn:
        t = trace_mod.trace(conn, start_account, max_hops=max_hops)
    if t is None:
        return None
    nodes = [TraceNode(**n) for n in t["nodes"]]
    edges = [TraceEdge(**e) for e in t["edges"]]
    flagged_edges = sum(1 for e in edges if e.is_flagged)
    src_ids = ([f"FinancialAccount:{n.account_id}" for n in nodes[:40]]
               + [f"FinancialTransaction:{tid}" for e in edges for tid in e.transaction_ids][:60])
    result = AiResult(
        answer=(f"Traced \u20b9{t['total_traced_amount']:,.0f} across {len(edges)} flow(s) and "
                f"{len(nodes)} account(s) from account {start_account} "
                f"(<= {t['hops']} hops, cycle-guarded)."),
        confidence=1.0,
        source_record_ids=src_ids,
        reasoning_summary=("Recursive-CTE forward trace over FinancialTransaction with a path-array "
                           "cycle guard; parallel transfers aggregated into weighted directed flows "
                           f"for a Sankey. {flagged_edges} flow(s) touch flagged transactions."),
        model_version=MONEY_MODEL,
    )
    return TraceResponse(
        result=result, start_account=start_account, max_hops=t["hops"],
        node_count=len(nodes), edge_count=len(edges),
        total_traced_amount=t["total_traced_amount"], cycle_guarded=True,
        nodes=nodes, edges=edges)


# ---- 2. detection job ------------------------------------------------------
def run_detection(**params) -> DetectionResponse:
    with db.rw_conn() as conn:
        rep = detection.run_detection(conn, **params)
    v = rep["validation"]
    result = AiResult(
        answer=(f"Flagged {rep['transactions_flagged']} transactions: "
                f"{rep['by_pattern']['structuring']} structuring, {rep['by_pattern']['layering']} layering, "
                f"{rep['by_pattern']['circular']} circular. Structuring recall "
                f"{v['structuring']['recall']:.0%} / precision {v['structuring']['precision']:.0%} "
                "vs injected patterns."),
        confidence=round(float(v["structuring"]["f1"]), 4),
        source_record_ids=["FinancialTransaction", "AlertHistory",
                           f"ModelVersion:{rep['model_version_id']}"],
        reasoning_summary=("Structuring (sliding-window sub-threshold fan-in), layering (value through "
                           "conduit accounts) and circular (directed cycles) detectors over the "
                           "transaction graph; flags written to FinancialTransaction + AlertHistory, "
                           "scored against the injected ground truth."),
        model_version=f"drishti-money-aml@1.0.0 (id {rep['model_version_id']})",
    )
    return DetectionResponse(
        result=result,
        transactions_scanned=rep["transactions_scanned"],
        transactions_flagged=rep["transactions_flagged"],
        by_pattern=rep["by_pattern"], alerts_written=rep["alerts_written"],
        structuring_hubs=rep["structuring_hubs"], layering_chains=rep["layering_chains"],
        circular_flows=rep["circular_flows"],
        validation={k: PatternMetric(**m) for k, m in v.items()},
        model_version_id=rep["model_version_id"])


# ---- 3. unified people + money subgraph ------------------------------------
def unified(entity_id: Optional[int] = None, account_id: Optional[int] = None,
            max_hops: int = 2) -> Optional[UnifiedResponse]:
    with db.ro_conn() as conn:
        u = unified_mod.unified_subgraph(conn, entity_id=entity_id, account_id=account_id,
                                         max_hops=max_hops)
    if u is None:
        return None
    nodes = [UnifiedNode(**n) for n in u["nodes"]]
    edges = [UnifiedEdge(**e) for e in u["edges"]]
    src = ([f"FinancialAccount:{n.account_id}" for n in nodes if n.kind == "account"][:40]
           + [f"EntityGraph:{n.entity_id}" for n in nodes if n.kind == "entity"][:20])
    result = AiResult(
        answer=(f"Unified people+money view around {u['seed_kind']} {u['seed_id']}: "
                f"{u['account_count']} account(s) linked to {u['entity_count']} owner entit(ies)."),
        confidence=1.0,
        source_record_ids=src,
        reasoning_summary=("Accounts and their transactions joined to their owner entities via "
                           "FinancialAccount.EntityID — people and money on one canvas without "
                           "merging the tables (nodes typed by kind; 'owns' edges bridge them)."),
        model_version=MONEY_MODEL,
    )
    return UnifiedResponse(
        result=result, seed_kind=u["seed_kind"], seed_id=u["seed_id"],
        node_count=len(nodes), edge_count=len(edges), nodes=nodes, edges=edges)


# ---- 4. flagged-transaction feed (read) ------------------------------------
def flagged_feed(page: int = 1, page_size: int = 25, reason: Optional[str] = None) -> FlaggedFeedResponse:
    offset = (max(1, page) - 1) * page_size
    where = 'WHERE "IsFlagged"'
    args: list = []
    if reason:
        where += ' AND "FlagReason" = %s'
        args.append(reason)
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "FinancialTransaction" {where}', args)
            total = int(cur.fetchone()[0])
            cur.execute('SELECT "FlagReason", COUNT(*) FROM "FinancialTransaction" '
                        'WHERE "IsFlagged" GROUP BY "FlagReason"')
            by_reason = {r[0] or "unspecified": int(r[1]) for r in cur.fetchall()}
            cur.execute(
                f'SELECT "TransactionID","SourceAccountID","DestinationAccountID","Amount",'
                f'"TxnTimestamp"::text,"Channel","FlagReason","EvidenceCaseID" '
                f'FROM "FinancialTransaction" {where} '
                f'ORDER BY "Amount" DESC LIMIT %s OFFSET %s', args + [page_size, offset])
            items = [FlaggedTxn(
                transaction_id=int(r[0]), source_account=int(r[1]), destination_account=int(r[2]),
                amount=float(r[3]), txn_timestamp=r[4], channel=r[5], flag_reason=r[6],
                evidence_case_id=int(r[7]) if r[7] is not None else None) for r in cur.fetchall()]
    result = AiResult(
        answer=f"{total} flagged transaction(s)" + (f" with reason '{reason}'." if reason else "."),
        confidence=1.0,
        source_record_ids=[f"FinancialTransaction:{it.transaction_id}" for it in items],
        reasoning_summary="Transactions flagged by the money-laundering detectors "
                          "(structuring / layering / circular), newest-value first.",
        model_version="drishti-money-aml@1.0.0",
    )
    return FlaggedFeedResponse(result=result, total=total, page=page, page_size=page_size,
                              by_reason=by_reason, items=items)
