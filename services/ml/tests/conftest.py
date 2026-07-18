"""Test fixtures. Ensures the `app` package is importable and DB tests skip
cleanly when no database is configured."""
import os
import sys
from pathlib import Path

import pytest

# Make `import app...` work when pytest is run from services/ml or elsewhere.
_ML_ROOT = Path(__file__).resolve().parents[1]
if str(_ML_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_ROOT))

from app.config import get_settings  # noqa: E402


def has_db() -> bool:
    return bool(get_settings().database_url)


requires_db = pytest.mark.skipif(not has_db(), reason="DATABASE_URL not configured")


@pytest.fixture(autouse=True, scope="session")
def _disable_global_rate_limit():
    """The full suite makes many requests from one TestClient IP; disable the
    main app's per-IP rate limiter for the session so functional tests are not
    throttled. The dedicated Phase-3 rate-limit test enables it on an isolated
    app via the middleware constructor override."""
    s = get_settings()
    original = s.rate_limit_enabled
    s.rate_limit_enabled = False
    yield
    s.rate_limit_enabled = original


@pytest.fixture
def rw_rollback():
    """A read-write DB connection that ALWAYS rolls back.

    Phase 2 write-path tests exercise real SQL, constraints and the full
    create -> validate -> submit -> approve canonicalisation against the live
    schema, then discard everything — nothing is persisted to the (over-quota)
    synthetic development database. Mirrors app.db.rw_conn's read-only override
    so writes are permitted, but never commits."""
    from app import db  # noqa: E402

    conn = db._connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("SET SESSION default_transaction_read_only = off")
            except Exception:  # noqa: BLE001
                pass
        conn.autocommit = False
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        conn.close()
