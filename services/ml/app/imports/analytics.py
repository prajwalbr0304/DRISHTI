"""Rule-based money-pattern alerts for Phase 8.

Reuses the Phase-11 detectors (structuring / layering / circular) but writes
reviewable, reason-coded ``MoneyAlert`` rows with transaction + source-record +
evidence provenance and a reviewer disposition (``MoneyAlertReview``).

A detected pattern is an INVESTIGATION SIGNAL, never proof of guilt — the alert
message wording is deliberately neutral and every alert is human-reviewable.
"""
from __future__ import annotations

from typing import Any, Optional

from psycopg2.extras import Json, execute_values

from .. import audit, db, models
from ..money import detection

# Explicit machine reason codes per alert type.
REASON_CODES = {
    "structuring": "STRUCT_SUBTHRESHOLD_FANIN",
    "layering": "LAYER_CONDUIT_PASSTHROUGH",
    "circular": "CIRC_RETURN_TO_ORIGIN",
}
_SEVERITY = {"structuring": "high", "layering": "medium", "circular": "critical"}

MODEL_NAME = "drishti-money-alerts"
MODEL_VERSION = "1.0.0"


class MoneyAlertError(Exception):
    pass


class MoneyAlertNotFound(MoneyAlertError):
    pass


def _txn_meta(conn, txn_ids: list[int]) -> dict[int, dict]:
    """transaction id -> {source_record_id, evidence_case_id, evidence_item_id}."""
    if not txn_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            'SELECT t."TransactionID", t."SourceRecordID", t."EvidenceCaseID", b."EvidenceItemID" '
            'FROM "FinancialTransaction" t '
            'LEFT JOIN "ImportBatch" b ON b."ImportBatchID"=t."ImportBatchID" '
            'WHERE t."TransactionID" = ANY(%s)', (txn_ids,))
        return {int(r[0]): {"source_record_id": r[1], "evidence_case_id": r[2],
                            "evidence_item_id": r[3]} for r in cur.fetchall()}


def _provenance(meta: dict[int, dict], txn_ids: list[int]) -> tuple[list[int], Optional[int], Optional[int]]:
    """Collect (source_record_ids, first evidence_item_id, first case_id) for a set of txns."""
    srcs: list[int] = []
    evidence_item = case_id = None
    for tid in txn_ids:
        m = meta.get(tid, {})
        if m.get("source_record_id") is not None:
            srcs.append(int(m["source_record_id"]))
        if evidence_item is None and m.get("evidence_item_id") is not None:
            evidence_item = int(m["evidence_item_id"])
        if case_id is None and m.get("evidence_case_id") is not None:
            case_id = int(m["evidence_case_id"])
    return srcs, evidence_item, case_id


def _scan(conn, *, structuring_min_count: int = 5, structuring_window_days: int = 14,
          layer_conduit_amount: float = 100_000, layer_pass_ratio: float = 0.6,
          cycle_min_amount: float = 10_000, cycle_max_len: int = 6,
          max_cycles: int = 200, max_alerts: int = 300) -> dict:
    txns, accts = detection._load(conn)
    threshold = detection.STRUCTURING_THRESHOLD

    struct_flag, hubs = detection.detect_structuring(
        txns, threshold, structuring_min_count, structuring_window_days)
    layer_flag, conduits, chain_count = detection.detect_layering(
        txns, threshold, layer_conduit_amount, layer_pass_ratio)
    circ_flag, cycles = detection.detect_circular(txns, cycle_min_amount, cycle_max_len, max_cycles)

    # transactions-by-account for conduit provenance
    txns_by_src: dict[int, list[int]] = {}
    txns_by_dst: dict[int, list[int]] = {}
    for tid, s, d, amt, ts, pat, ev in txns:
        txns_by_src.setdefault(s, []).append(tid)
        txns_by_dst.setdefault(d, []).append(tid)

    meta = _txn_meta(conn, list(struct_flag | layer_flag | circ_flag))

    mv_id = models.get_or_create_model_version(
        conn, MODEL_NAME, "anomaly_detection", MODEL_VERSION, framework="rule_based",
        hyperparameters={"threshold": threshold, "structuring_min_count": structuring_min_count,
                         "structuring_window_days": structuring_window_days,
                         "layer_conduit_amount": layer_conduit_amount,
                         "cycle_min_amount": cycle_min_amount})

    alerts: list[dict] = []

    # --- structuring hubs ---
    for acct, info in hubs.items():
        tids = info.get("txn_ids", [])
        srcs, ev_item, case_id = _provenance(meta, tids)
        alerts.append({
            "type": "structuring", "severity": _SEVERITY["structuring"],
            "reason": REASON_CODES["structuring"], "account": acct,
            "case": info.get("evidence_case_id") or case_id, "evidence_item": ev_item,
            "title": f"Repeated sub-threshold deposits into account {acct}",
            "message": (f"{info['deposit_count']} deposits below the \u20b9{threshold:,.0f} "
                        f"reporting threshold (\u20b9{info['total']:,.0f} total) reached account "
                        f"{acct} within {structuring_window_days} days. Review required; "
                        "a pattern is not by itself evidence of an offence."),
            "txns": tids, "srcs": srcs, "rank": info["total"]})

    # --- circular flows ---
    for cyc in cycles:
        tids = []
        for i in range(len(cyc)):
            s, d = cyc[i], cyc[(i + 1) % len(cyc)]
            tids.extend([t for t in txns_by_src.get(s, []) if t in txns_by_dst.get(d, [])])
        srcs, ev_item, case_id = _provenance(meta, tids)
        alerts.append({
            "type": "circular", "severity": _SEVERITY["circular"],
            "reason": REASON_CODES["circular"], "account": cyc[0] if cyc else None,
            "case": case_id, "evidence_item": ev_item,
            "title": f"Circular fund flow across {len(cyc)} accounts",
            "message": (f"Funds return toward their origin through accounts {cyc}. Review required; "
                        "circularity alone does not establish culpability."),
            "txns": tids[:50], "srcs": srcs, "rank": 1e12})

    # --- layering conduits ---
    for acct in list(conduits)[:max_alerts]:
        tids = (txns_by_src.get(acct, []) + txns_by_dst.get(acct, []))
        tids = [t for t in tids if t in layer_flag][:50]
        srcs, ev_item, case_id = _provenance(meta, tids)
        alerts.append({
            "type": "layering", "severity": _SEVERITY["layering"],
            "reason": REASON_CODES["layering"], "account": acct, "case": case_id,
            "evidence_item": ev_item,
            "title": f"Pass-through (layering) conduit account {acct}",
            "message": (f"Account {acct} passes large value through (inflow \u2248 outflow), "
                        "consistent with layering. Review required; not proof of an offence."),
            "txns": tids, "srcs": srcs, "rank": 0})

    sev_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    alerts.sort(key=lambda a: (sev_rank[a["severity"]], a["rank"]), reverse=True)
    alerts = alerts[:max_alerts]

    # idempotent: replace this model's OPEN alerts; reviewed ones are preserved.
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "MoneyAlert" WHERE "ModelVersionID"=%s AND "Status"=\'open\'', (mv_id,))
        rows = [(a["type"], a["reason"], a["severity"], a["title"], a["message"], a["account"],
                 a["case"], a["evidence_item"], mv_id, Json(a["txns"]), Json(a["srcs"]),
                 Json({"pattern": a["type"]}), "open") for a in alerts]
        if rows:
            execute_values(
                cur,
                'INSERT INTO "MoneyAlert" ("AlertType","ReasonCode","Severity","Title","Message",'
                '"AccountID","CaseMasterID","EvidenceItemID","ModelVersionID","TransactionIDs",'
                '"SourceRecordIDs","Payload","Status") VALUES %s', rows, page_size=200)

    by_type: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for a in alerts:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        by_reason[a["reason"]] = by_reason.get(a["reason"], 0) + 1

    models.log_inference(
        conn, mv_id, ref_table="MoneyAlert",
        inputs={"structuring_min_count": structuring_min_count,
                "structuring_window_days": structuring_window_days,
                "layer_conduit_amount": layer_conduit_amount, "cycle_min_amount": cycle_min_amount},
        outputs={"alerts": len(alerts), "by_type": by_type})
    audit.record(audit.Action.MODEL_RUN, "money_alert_scan", mv_id, conn=conn,
                 detail={"alerts": len(alerts), "by_type": by_type})

    return {"transactions_scanned": len(txns), "alerts_written": len(alerts),
            "by_type": by_type, "by_reason_code": by_reason, "model_version_id": mv_id,
            "structuring_hubs": len(hubs), "layering_conduits": len(conduits),
            "circular_flows": len(cycles)}


def _disposition(conn, alert_id: int, disposition: str, actor: Optional[str],
                 reason: Optional[str]) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "MoneyAlert" WHERE "MoneyAlertID"=%s', (alert_id,))
        if cur.fetchone() is None:
            raise MoneyAlertNotFound(f"Money alert {alert_id} not found.")
        cur.execute(
            'INSERT INTO "MoneyAlertReview" ("MoneyAlertID","Disposition","ReviewerActor","Reason") '
            'VALUES (%s,%s,%s,%s)', (alert_id, disposition, actor, reason))
        status_map = {"acknowledge": "reviewed", "dismiss": "dismissed", "escalate": "escalated",
                      "false_positive": "false_positive", "confirm_pattern": "confirmed_pattern"}
        new_status = status_map.get(disposition, "reviewed")
        cur.execute('UPDATE "MoneyAlert" SET "Status"=%s WHERE "MoneyAlertID"=%s',
                    (new_status, alert_id))
    audit.record(audit.Action.PREDICTION_REVIEW, "money_alert", alert_id, actor=actor, conn=conn,
                 detail={"disposition": disposition, "new_status": new_status})
    return {"money_alert_id": alert_id, "status": new_status, "disposition": disposition}


# ---------------------------------------------------------------------------
# Public wrappers
# ---------------------------------------------------------------------------
def scan(**params) -> dict:
    with db.rw_conn() as conn:
        return _scan(conn, **params)


def disposition(alert_id: int, disp: str, actor: Optional[str], reason: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _disposition(conn, alert_id, disp, actor, reason)


def list_alerts(status: Optional[str], alert_type: Optional[str], case_id: Optional[int],
                page: int, page_size: int) -> dict:
    clauses, params = [], []
    if status:
        clauses.append('a."Status"=%s'); params.append(status)
    if alert_type:
        clauses.append('a."AlertType"=%s'); params.append(alert_type)
    if case_id:
        clauses.append('a."CaseMasterID"=%s'); params.append(case_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "MoneyAlert" a{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute('SELECT "Status", count(*) FROM "MoneyAlert" GROUP BY "Status"')
            by_status = {r[0]: int(r[1]) for r in cur.fetchall()}
            cur.execute(
                f'SELECT a."MoneyAlertID",a."AlertType",a."ReasonCode",a."Severity",a."Title",'
                f'a."Message",a."AccountID",a."CaseMasterID",a."EvidenceItemID",a."TransactionIDs",'
                f'a."SourceRecordIDs",a."Status",a."CreatedAt",'
                f'(SELECT r."Disposition" FROM "MoneyAlertReview" r WHERE r."MoneyAlertID"=a."MoneyAlertID" '
                f'ORDER BY r."MoneyAlertReviewID" DESC LIMIT 1) '
                f'FROM "MoneyAlert" a{where} ORDER BY a."MoneyAlertID" DESC LIMIT %s OFFSET %s',
                params + [page_size, offset])
            items = [{
                "money_alert_id": int(x[0]), "alert_type": x[1], "reason_code": x[2],
                "severity": x[3], "title": x[4], "message": x[5], "account_id": x[6],
                "case_master_id": x[7], "evidence_item_id": x[8],
                "transaction_ids": x[9] or [], "source_record_ids": x[10] or [],
                "status": x[11], "created_at": str(x[12]) if x[12] else None,
                "latest_disposition": x[13]} for x in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size,
            "by_status": by_status, "items": items}
