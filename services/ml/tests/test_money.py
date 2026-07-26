"""Phase-11 money-trail tests.

Unit (no DB): the three detectors on synthetic transaction fixtures + the
precision/recall metric. Integration (@requires_db): the money_trail permission
matrix, the cycle-guarded trace, the unified people+money subgraph, the flagged
feed, and (slow) full detection rediscovering the injected structuring pattern.
"""
import datetime as dt

import pytest
from fastapi import HTTPException

from app.contracts import AiResult
from app.money import detection, permissions, service
from app.money.schemas import DetectionResponse, TraceResponse, UnifiedResponse
from conftest import requires_db


def _txn(tid, s, d, amt, day=0, pattern=None):
    ts = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=day)
    return (tid, s, d, float(amt), ts, pattern, None)


# ---- unit: metric ----------------------------------------------------------
def test_metric_precision_recall():
    m = detection._metric({1, 2, 3}, {2, 3, 4})   # tp=2, det=3, gt=3
    assert m["true_positive"] == 2
    assert m["precision"] == round(2 / 3, 4)
    assert m["recall"] == round(2 / 3, 4)
    assert detection._metric(set(), {1})["precision"] == 0.0


# ---- unit: structuring (sliding window) ------------------------------------
def test_detect_structuring_window():
    # dest 99: 6 sub-threshold deposits inside 3 days -> structuring
    txns = [_txn(i, i + 1, 99, 45000, day=i % 3) for i in range(6)]
    # dest 88: 6 sub-threshold deposits spread over 100 days -> NOT structuring
    txns += [_txn(100 + i, i + 1, 88, 45000, day=i * 20) for i in range(6)]
    # a single large legit credit to 77 -> not sub-threshold
    txns += [_txn(200, 5, 77, 90000, day=0)]
    flagged, hubs = detection.detect_structuring(txns, 50000, 5, 14)
    assert all(t in flagged for t in range(6))
    assert 99 in hubs and 88 not in hubs and 77 not in hubs
    assert not (set(range(100, 106)) & flagged)


# ---- unit: circular --------------------------------------------------------
def test_detect_circular_finds_cycle_not_dag():
    cyc = [_txn(1, 1, 2, 20000), _txn(2, 2, 3, 20000), _txn(3, 3, 1, 20000)]
    dag = [_txn(4, 4, 5, 20000), _txn(5, 5, 6, 20000)]
    flagged, cycles = detection.detect_circular(cyc + dag, 10000, 6, 100)
    assert {1, 2, 3} <= flagged
    assert not ({4, 5} & flagged)
    assert len(cycles) >= 1
    # sub-min-amount edges are ignored
    small_flag, _ = detection.detect_circular([_txn(1, 1, 2, 500), _txn(2, 2, 1, 500)], 10000, 6, 100)
    assert not small_flag


# ---- unit: layering (conduit) ----------------------------------------------
def test_detect_layering_conduit():
    # 1 -> conduit 2 (in 200k) -> 3 (out 190k): 2 is a pass-through conduit
    txns = [_txn(1, 1, 2, 200000), _txn(2, 2, 3, 190000)]
    flagged, conduits, chains = detection.detect_layering(txns, 50000, 100000, 0.6)
    assert 2 in conduits
    assert 1 in flagged and 2 in flagged          # both large legs flagged
    # a pure sink (no outflow) is not a conduit
    txns2 = [_txn(1, 1, 2, 200000)]
    _, conduits2, _ = detection.detect_layering(txns2, 50000, 100000, 0.6)
    assert 2 not in conduits2


# ---- integration -----------------------------------------------------------
def _assert_airesult(r: AiResult):
    assert isinstance(r.answer, str) and r.answer
    assert 0.0 <= r.confidence <= 1.0
    assert isinstance(r.source_record_ids, list)
    assert "@" in r.model_version


@requires_db
def test_money_permission_matrix():
    # INTERIM ("all roles have access to everything"): every command role holds
    # WRITE on money_trail; a role outside the canonical set is unmapped.
    from app.roles import FUNCTIONAL_ROLES
    for role in FUNCTIONAL_ROLES:
        assert permissions.action_for_role(role) == "write", role
        assert permissions.require_money_permission(role) == role
        assert permissions.require_money_write(role) == role
    assert permissions.action_for_role("wizard") is None
    # An unmapped role is refused by both gates (the gate is code-based).
    with pytest.raises(HTTPException) as ex:
        permissions.require_money_permission("wizard")
    assert ex.value.status_code == 403
    with pytest.raises(HTTPException):
        permissions.require_money_write("wizard")


def _an_account_with_outflow():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "SourceAccountID" FROM "FinancialTransaction" LIMIT 1')
            return int(cur.fetchone()[0])


@requires_db
def test_trace_is_cycle_guarded_and_bounded():
    resp = service.trace(_an_account_with_outflow(), max_hops=4)
    assert isinstance(resp, TraceResponse)
    _assert_airesult(resp.result)
    assert resp.cycle_guarded is True
    assert resp.max_hops <= 6
    assert all(n.hop <= resp.max_hops for n in resp.nodes)   # depth cap honoured
    assert resp.total_traced_amount >= 0


@requires_db
def test_trace_missing_account_is_none():
    assert service.trace(2_000_000_000) is None


@requires_db
def test_unified_joins_accounts_to_owner_entities():
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "EntityID" FROM "FinancialAccount" WHERE "EntityID" IS NOT NULL '
                        'GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1')
            ent = int(cur.fetchone()[0])
    resp = service.unified(entity_id=ent, max_hops=2)
    assert isinstance(resp, UnifiedResponse)
    _assert_airesult(resp.result)
    kinds = {n.kind for n in resp.nodes}
    assert "account" in kinds and "entity" in kinds       # people + money on one canvas
    assert any(e.kind == "owns" for e in resp.edges)      # the bridge edge
    assert any(e.kind == "transaction" for e in resp.edges)


@requires_db
def test_flagged_feed_reads_persisted_flags():
    resp = service.flagged_feed(page=1, page_size=5)
    assert resp.total > 0
    assert resp.items and all(it.flag_reason for it in resp.items)
    assert sum(resp.by_reason.values()) >= resp.total


@requires_db
@pytest.mark.slow
def test_detection_rediscovers_structuring_and_flags_circular():
    resp = service.run_detection()
    assert isinstance(resp, DetectionResponse)
    _assert_airesult(resp.result)
    assert resp.by_pattern["structuring"] > 0
    assert resp.validation["structuring"].recall > 0.9      # near-perfect rediscovery
    assert resp.circular_flows > 0                           # circular patterns flagged
    assert resp.transactions_flagged <= resp.transactions_scanned
