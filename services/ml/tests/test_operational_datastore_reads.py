"""Prompt 21 §B — operational read/reference/authz closure to Catalyst Data
Store + code (verified with NO database).

These lock in that the demo-visible operational READ and AUTHORIZATION journeys
are served from the Catalyst Data Store operational repository (seeded from the
curated serving-export subset) or in-code config — never from AWS RDS — so they
work with DATABASE_URL absent (deployed AppSail).
"""
from __future__ import annotations

import os

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402

from app.datastore import seed as ds_seed  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_seed():
    ds_seed.reset_reference_repo()
    yield
    ds_seed.reset_reference_repo()


def test_serving_export_seeds_reference_tables():
    repo = ds_seed.reference_repo()
    # curated serving subset is present and seeded
    assert len(repo.query("CaseCategory")) == 5
    assert len(repo.query("District")) >= 30
    assert len(repo.query("ImportTemplate")) == 8


def test_intake_reference_lookups_from_datastore():
    from app.intake import lookups
    out = lookups._reference_lookups_datastore(None, 500)
    assert len(out["categories"]) == 5
    assert {c["name"] for c in out["categories"]} >= {"FIR", "UDR"}
    assert len(out["districts"]) >= 30
    assert out["party_roles"]  # static vocabulary always present


def test_imports_templates_from_datastore():
    from app.imports import service as isvc
    out = isvc._list_templates_datastore()
    assert out["count"] == 8
    codes = {t["code"] for t in out["templates"]}
    assert {"cdr_call_events", "bank_transactions", "wallet_upi", "account_kyc"} <= codes


def test_money_authorization_is_code_based():
    from app.money import permissions as mp
    assert mp.action_for_role("super_admin") == "write"
    assert mp.action_for_role("investigator") == "read"
    assert mp.action_for_role("analyst") == "read"
    assert mp.action_for_role("supervisor") == "read"
    # Known-but-denied roles carry an EXPLICIT 'none' grant, mirroring the SQL
    # seed row ('policymaker','money_trail','none'). An entirely UNKNOWN role
    # resolves to None. Both deny — only 'read'/'write' pass the gate.
    assert mp.action_for_role("policymaker") == "none"       # denied (explicit none)
    assert mp.action_for_role("disaster_coordinator") == "none"  # denied (explicit none)
    assert mp.action_for_role("intruder_role") is None       # unknown -> None (also denied)
    # the gate performs no RDS access (no db connector usage in the module body)
    import inspect
    src = inspect.getsource(mp)
    assert "ro_conn(" not in src and "rw_conn(" not in src
    assert "import db" not in src


def test_admin_feature_flags_code_based_offline(monkeypatch):
    from app.admin import service as adm
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "database_url", "")
    flags = adm.list_feature_flags()
    keys = {f["key"] for f in flags}
    assert {"rag_assistant", "notifications_email", "reports_smartbrowz"} <= keys


def test_admin_usage_plan_baseline_offline(monkeypatch):
    from app.admin import service as adm
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "database_url", "")
    u = adm.usage()
    assert u["plan_baseline"].get("envelope_inr") == 1800
    assert u["feature_flags"]


def test_financial_views_from_datastore():
    from app.imports import service as isvc
    accounts = isvc._list_accounts_datastore(None, None, 1, 25)
    assert accounts["total"] >= 1 and len(accounts["items"]) <= 25
    assert all("account_id" in a for a in accounts["items"])
    txns = isvc._list_transactions_datastore(None, None, None, 1, 25)
    assert txns["total"] >= 1 and len(txns["items"]) <= 25
