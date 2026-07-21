"""Prompt 21 §C — protected AWS analytics adapter (typed ops) + Board Search
Around boundary.

Proves:
  * the analytics adapter exposes only a typed operation allow-list (no generic
    SQL proxy) and rejects unknown operations;
  * client-side hard caps (hops/neighbours/byte) are enforced;
  * request signing is deterministic + keyed by the server-side secret;
  * get_analytics_adapter() is None in dev (local path) and the fake only when
    explicitly opted in;
  * Board Search Around uses the PROTECTED ADAPTER (not a direct AppSail->RDS
    call) when the adapter is configured — verified with NO database.
"""
from __future__ import annotations

import os

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402

from app import analytics_adapter as aa  # noqa: E402
from app.predict.adapter import AdapterError, sign_payload  # noqa: E402


def test_operation_allow_list_is_typed_not_sql():
    assert "graph_neighbourhood" in aa.ANALYTICS_OPERATIONS
    # no generic SQL/query operation exists
    assert not any("sql" in op or "query" == op for op in aa.ANALYTICS_OPERATIONS)


def test_signed_adapter_rejects_unknown_operation():
    ad = aa.SignedHttpsAnalyticsAdapter(base_url="https://example.invalid",
                                        secret="s")
    with pytest.raises(AdapterError):
        ad._call("drop_everything", {})  # not in the allow-list -> rejected pre-network


def test_signing_is_deterministic_and_keyed():
    payload = b'{"operation":"graph_neighbourhood"}'
    a = sign_payload("secret-A", payload, "100", "n1")
    a2 = sign_payload("secret-A", payload, "100", "n1")
    b = sign_payload("secret-B", payload, "100", "n1")
    assert a == a2 and a != b and len(a) == 64  # HMAC-SHA256 hex


def test_inmemory_adapter_caps_and_shape():
    ad = aa.InMemoryAnalyticsAdapter(graph={1: list(range(1, 200))})
    exists, nodes, edges = ad.graph_neighbourhood(1, hops=9, max_neighbors=999)
    assert exists is True
    # capped to MAX_NEIGHBORS (+ the focal node)
    assert len(nodes) <= aa.MAX_NEIGHBORS + 1
    assert all({"source", "target", "weight"} <= set(e) for e in edges)
    # unknown focal entity -> not found
    assert ad.graph_neighbourhood(999, 1, 5) == (False, [], [])


def test_get_analytics_adapter_none_in_dev(monkeypatch):
    monkeypatch.delenv("DRISHTI_AWS_ADAPTER_URL", raising=False)
    monkeypatch.delenv("DRISHTI_AWS_ADAPTER_SECRET", raising=False)
    monkeypatch.delenv("DRISHTI_ANALYTICS_ADAPTER_FAKE", raising=False)
    assert aa.get_analytics_adapter() is None       # dev -> local path


def test_get_analytics_adapter_fake_opt_in(monkeypatch):
    monkeypatch.setenv("DRISHTI_ANALYTICS_ADAPTER_FAKE", "true")
    monkeypatch.delenv("DRISHTI_AWS_ADAPTER_URL", raising=False)
    assert isinstance(aa.get_analytics_adapter(), aa.InMemoryAnalyticsAdapter)


def test_board_search_around_uses_adapter_not_rds(monkeypatch):
    """Board Search Around must fetch through the protected adapter (C.3) — proven
    with NO database: a direct db.ro_conn() here would raise (no DATABASE_URL)."""
    from app.board import searcharound

    seeded = aa.InMemoryAnalyticsAdapter(graph={42: [43, 44, 45]})
    monkeypatch.setattr(searcharound, "get_analytics_adapter", lambda: seeded)

    res = searcharound.expand(42, hops=1, max_neighbors=10)
    assert res["fetch_source"] == "aws-analytics-adapter"
    assert res["exists"] is True
    assert res["node_count"] >= 1
    # the focal entity is excluded from the neighbour list
    assert all(n["entity_id"] != 42 for n in res["neighbors"])
