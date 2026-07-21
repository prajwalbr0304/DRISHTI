"""Prompt 21 §A/§B.5/§H.2 — route-to-data-boundary + static deployment check.

These tests run with NO DATABASE_URL (the deployed operational posture). They
prove:

  * the FastAPI app imports and every deployed route is classified into exactly
    one data boundary (no demo-visible route is unclassified);
  * the static deployment-boundary check passes — i.e. no domain that claims to
    be Catalyst-Data-Store-native imports/opens the PostgreSQL connector in its
    own package (Prompt 21 §B.5: an operational route must not open RDS);
  * the machine-checkable inventory the report cites is internally consistent.
"""
from __future__ import annotations

import os

import pytest

# Enforce the deployed operational posture for this module: no analytics DB.
os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""

from app import deployment_boundary as dbnd  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def report():
    return dbnd.analyze(app)


def test_app_imports_without_database_url():
    # The app object exists and exposes routes even though DATABASE_URL is unset.
    routes = dbnd.enumerate_routes(app)
    assert len(routes) > 200, "expected the full deployed route table"


def test_every_domain_is_classified(report):
    assert report["unclassified_domains"] == [], (
        f"unclassified domains must be added to deployment_boundary.REGISTRY: "
        f"{report['unclassified_domains']}")


def test_no_demo_visible_route_is_unclassified(report):
    for domain, info in report["domains"].items():
        if info["boundary"] == "UNCLASSIFIED":
            assert not info.get("demo_visible", True), (
                f"demo-visible domain {domain!r} is unclassified")


def test_static_deployment_boundary_check_passes():
    """The wired-in CI gate: native operational domains must not import the
    PostgreSQL connector; demo-visible domains must be classified."""
    violations = dbnd.check(app)
    assert violations == [], "boundary violations:\n" + "\n".join(violations)


def test_route_counts_by_class_sum_to_total(report):
    total = sum(v for v in report["route_count_by_class"].values())
    assert total == report["total_routes"]


def test_datastore_native_domains_have_no_direct_db():
    """Disaster is fully Data Store-native and must never import the connector."""
    for domain in ("disaster", "scenarios", "search", "internal"):
        offenders = dbnd.domain_direct_db_modules(domain)
        assert offenders == [], (
            f"{domain!r} is classified Data Store-native but imports the "
            f"PostgreSQL connector in: {offenders}")


def test_aws_analytics_domains_are_declared():
    """Graph/geo/forecast-style analytics must be behind the adapter boundary."""
    analytics = {d for d, b in dbnd.REGISTRY.items()
                 if b.boundary == dbnd.AWS_ANALYTICS}
    for expected in ("graph", "geo", "forecast", "analytics", "risk", "money"):
        assert expected in analytics, f"{expected} should be AWS_ANALYTICS"


def test_boundary_classes_are_valid():
    for d, b in dbnd.REGISTRY.items():
        assert b.boundary in dbnd.BOUNDARY_CLASSES, f"{d}: bad class {b.boundary}"
        assert b.migration in (dbnd.MIG_NATIVE, dbnd.MIG_PENDING, dbnd.MIG_NA)
