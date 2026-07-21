"""Prompt 21 §G.2/§G.3 — readiness gating + shallow liveness.

Proves:
  * liveness is a shallow process check that never touches a dependency;
  * readiness PASSES offline (in-memory Data Store repo, gateway not enforced);
  * readiness FAILS when the operational Data Store plane is unreachable;
  * readiness FAILS when gateway enforcement is required but no signing secret;
  * readiness FAILS when Stratus is selected but unconfigured;
  * AWS RDS is advisory only and never flips readiness;
  * /health/ready returns HTTP 503 when not ready, 200 when ready.
"""
from __future__ import annotations

import os

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import readiness  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
settings = get_settings()


def _ok_repo_factory():
    from app.datastore.repository import InMemoryDataStore
    return lambda: InMemoryDataStore()


def _broken_repo_factory():
    def factory():
        raise RuntimeError("Catalyst Data Store unreachable")
    return factory


def test_liveness_is_shallow_and_never_fails():
    r = client.get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    # Liveness carries no dependency checks.
    assert "checks" not in body


def test_readiness_passes_offline_with_inmemory_store():
    res = readiness.evaluate(
        settings,
        repo_factory=_ok_repo_factory(),
        gateway_required=False,
        stratus_enabled=False,
        analytics_ping=lambda: False,   # RDS down is advisory only
    )
    assert res.ready is True
    assert res.checks["operational_datastore"] == "ok"
    assert res.checks["analytics_db"] == "unavailable"  # advisory, did not fail


def test_readiness_fails_when_datastore_unreachable():
    res = readiness.evaluate(
        settings,
        repo_factory=_broken_repo_factory(),
        gateway_required=False,
        stratus_enabled=False,
        analytics_ping=lambda: True,
    )
    assert res.ready is False
    assert res.checks["operational_datastore"] == "unavailable"


def test_readiness_fails_when_gateway_required_without_secret():
    res = readiness.evaluate(
        settings,
        repo_factory=_ok_repo_factory(),
        gateway_required=True,
        signing_secret="",           # required but missing -> auth plane broken
        stratus_enabled=False,
        analytics_ping=lambda: True,
    )
    assert res.ready is False
    assert res.checks["gateway_auth"] == "misconfigured"


def test_readiness_passes_when_gateway_required_with_secret():
    res = readiness.evaluate(
        settings,
        repo_factory=_ok_repo_factory(),
        gateway_required=True,
        signing_secret="a-server-side-secret",
        stratus_enabled=False,
        analytics_ping=lambda: True,
    )
    assert res.ready is True
    assert res.checks["gateway_auth"] == "ok"


def test_readiness_fails_when_stratus_selected_but_unconfigured():
    res = readiness.evaluate(
        settings,
        repo_factory=_ok_repo_factory(),
        gateway_required=False,
        stratus_enabled=True,
        stratus_configured=False,
        analytics_ping=lambda: True,
    )
    assert res.ready is False
    assert res.checks["object_store"] == "misconfigured"


def test_readiness_advisory_rds_never_fails_readiness():
    # Even if the advisory RDS ping raises, readiness stays green.
    def boom():
        raise RuntimeError("rds blew up")
    res = readiness.evaluate(
        settings,
        repo_factory=_ok_repo_factory(),
        gateway_required=False,
        stratus_enabled=False,
        analytics_ping=boom,
    )
    assert res.ready is True
    assert res.checks["analytics_db"] == "unavailable"


def test_health_ready_endpoint_returns_200_when_ready():
    # Offline default: in-memory repo, gateway not enforced -> ready.
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["status"] == "ready"


def test_health_ready_endpoint_returns_503_when_datastore_broken(monkeypatch):
    def broken():
        raise RuntimeError("Data Store down")
    # Patch the repository factory the readiness probe uses.
    monkeypatch.setattr("app.datastore.repository.get_repository", broken)
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["operational_datastore"] == "unavailable"
