"""Phase 3 — hackathon access mode tests.

Covers the Definition of Done:
  * RLS + FORCE RLS disabled on every application table; zero RLS policies.
  * anon/authenticated/service_role/PUBLIC hold no direct table DML (API-only).
  * drishti_readonly stays SELECT-only.
  * FastAPI refuses to start in HACKATHON_MODE against a non-synthetic DB.
  * CORS allows the configured origin and rejects an unlisted one.
  * Conservative request-size (413) and rate (429) limits.
  * Error responses never leak SQL / stack traces / credentials.
  * The frontend source contains no DB credential / service key / Supabase query.
  * Audit events are written (same transaction) with request id + demo actor and
    without secrets/narratives/PII.

DB-integrated tests use the ``rw_rollback`` fixture (owner connection that ALWAYS
rolls back) so nothing is persisted to the synthetic development database.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import audit
from app.config import get_settings
from app.main import app
from conftest import requires_db

# services/ml/tests/test_hackathon.py -> parents[3] == repo root (…/DRISHTI)
_REPO_ROOT = Path(__file__).resolve().parents[3]

client = TestClient(app)

_DML = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")


# ===========================================================================
# RLS disabled everywhere + no policies (owner connection)
# ===========================================================================
@requires_db
def test_rls_disabled_and_no_force_on_all_app_tables(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('SELECT tablename, rls_enabled, rls_forced FROM fn_drishti_app_tables()')
        rows = cur.fetchall()
    assert len(rows) > 0, "no application tables discovered"
    offenders = [r[0] for r in rows if r[1] or r[2]]
    assert offenders == [], f"RLS/FORCE still enabled on: {offenders}"
    # the migration-owned assertion function must also pass (raises otherwise)
    with conn.cursor() as cur:
        cur.execute("SELECT fn_assert_rls_disabled()")
    conn.rollback()


@requires_db
def test_no_rls_policies_in_public(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public'")
        assert int(cur.fetchone()[0]) == 0
    rw_rollback.rollback()


# ===========================================================================
# API-only DB access: no browser/public DML grants
# ===========================================================================
@requires_db
def test_no_browser_or_public_dml_grants(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute(
            "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema='public' "
            "AND grantee IN ('anon','authenticated','service_role','PUBLIC') "
            "AND privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')")
        rows = cur.fetchall()
    assert rows == [], f"browser/public DML still present: {rows}"
    # migration-owned assertion must also pass
    with conn.cursor() as cur:
        cur.execute("SELECT fn_assert_no_browser_dml()")
    conn.rollback()


@requires_db
def test_drishti_readonly_is_select_only(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema='public' AND grantee='drishti_readonly'")
        privs = {r[0] for r in cur.fetchall()}
    assert "SELECT" in privs, "read-only role lost SELECT"
    assert privs.isdisjoint(set(_DML)), f"read-only role holds DML: {privs & set(_DML)}"
    rw_rollback.rollback()


@requires_db
def test_synthetic_marker_present_and_expected(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "Value" FROM "synthetic_meta" WHERE "Key"=%s', ("app_environment",))
        row = cur.fetchone()
    assert row and row[0] == get_settings().synthetic_env_expected
    rw_rollback.rollback()


# ===========================================================================
# Startup synthetic-database guard (monkeypatched marker — no DB needed)
# ===========================================================================
def test_startup_guard_refuses_wrong_marker(monkeypatch):
    import app.hardening as h
    monkeypatch.setattr(h, "read_db_environment_marker", lambda: (True, "production"))
    with pytest.raises(RuntimeError):
        h.verify_hackathon_startup()


def test_startup_guard_refuses_missing_marker(monkeypatch):
    import app.hardening as h
    monkeypatch.setattr(h, "read_db_environment_marker", lambda: (True, None))
    with pytest.raises(RuntimeError):
        h.verify_hackathon_startup()


def test_startup_guard_passes_for_synthetic(monkeypatch):
    import app.hardening as h
    monkeypatch.setattr(h, "read_db_environment_marker",
                        lambda: (True, get_settings().synthetic_env_expected))
    h.verify_hackathon_startup()  # must not raise


def test_startup_guard_allows_when_unreachable(monkeypatch):
    # Transient connectivity loss must not hard-crash the demo (per-request write
    # guards remain fail-closed).
    import app.hardening as h
    monkeypatch.setattr(h, "read_db_environment_marker", lambda: (False, None))
    h.verify_hackathon_startup()  # must not raise


def test_masked_db_target_hides_credentials():
    from app.hardening import masked_db_target
    masked = masked_db_target(
        "postgresql://user:SUPERSECRET@db.abc.ap-south-1.rds.amazonaws.com:5432/drishti")
    assert "SUPERSECRET" not in masked
    assert "user" not in masked
    assert "aws-rds" in masked and "rds.amazonaws.com" in masked


# ===========================================================================
# CORS: allow configured origin, reject unlisted origin
# ===========================================================================
def test_cors_allows_configured_localhost_origin():
    r = client.options("/health", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unlisted_origin():
    r = client.options("/health", headers={
        "Origin": "http://evil.example.com",
        "Access-Control-Request-Method": "GET"})
    assert r.status_code == 400
    assert r.headers.get("access-control-allow-origin") != "http://evil.example.com"


# ===========================================================================
# Request-size + rate limits (isolated apps via middleware constructor overrides)
# ===========================================================================
def test_request_body_size_limit_413():
    from app.hardening import BodySizeLimitMiddleware
    mini = FastAPI()
    mini.add_middleware(BodySizeLimitMiddleware, max_bytes=64)

    @mini.post("/echo")
    def _echo(payload: dict):
        return payload

    c = TestClient(mini)
    assert c.post("/echo", json={"a": 1}).status_code == 200
    assert c.post("/echo", json={"blob": "x" * 500}).status_code == 413


def test_rate_limit_429_after_threshold():
    from app.hardening import RateLimitMiddleware
    mini = FastAPI()
    mini.add_middleware(RateLimitMiddleware, enabled=True, per_minute=3)

    @mini.get("/ping")
    def _ping():
        return {"ok": True}

    c = TestClient(mini)
    assert [c.get("/ping").status_code for _ in range(3)] == [200, 200, 200]
    blocked = c.get("/ping")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"


# ===========================================================================
# Error responses never leak SQL / stack traces / credentials
# ===========================================================================
def test_error_response_is_sanitized():
    from app.hardening import install_error_handlers
    from app.request_context import RequestContextMiddleware
    mini = FastAPI()
    install_error_handlers(mini)
    mini.add_middleware(RequestContextMiddleware)

    @mini.get("/boom")
    def _boom():
        raise RuntimeError("SELECT * FROM users WHERE password='hunter2' -- stacktrace")

    c = TestClient(mini, raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    body = str(r.json())
    assert "Internal server error" in body
    for leak in ("SELECT", "password", "hunter2", "Traceback", "RuntimeError"):
        assert leak not in body, f"error response leaked: {leak}"


# ===========================================================================
# Frontend has no embedded secret / direct DB access
# ===========================================================================
def test_frontend_source_has_no_secret_or_direct_db_access():
    web_src = _REPO_ROOT / "web" / "src"
    assert web_src.is_dir(), f"web/src not found at {web_src}"
    forbidden = (
        "createClient(", "@supabase/", "supabase.co", "SUPABASE_SERVICE_ROLE",
        "SUPABASE_SECRET", "SERVICE_ROLE_KEY", "DATABASE_URL",
        "postgres://", "postgresql://", "sb_secret_", "sb_publishable_",
    )
    hits: list[str] = []
    for p in web_src.rglob("*"):
        if p.suffix.lower() in (".ts", ".tsx", ".js", ".jsx") and p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            for needle in forbidden:
                if needle in text:
                    hits.append(f"{p.relative_to(_REPO_ROOT)} :: {needle}")
    assert hits == [], f"forbidden patterns in frontend source: {hits}"


# ===========================================================================
# Audit: sanitisation + same-transaction write + actor resolution
# ===========================================================================
def test_sanitize_detail_drops_sensitive_and_truncates():
    out = audit.sanitize_detail({
        "case_master_id": 123,
        "crime_no": "18-digit-synthetic",   # safe id, must be kept
        "draft_key": "DR-ABC",              # safe id, must be kept
        "brief_facts": "a long narrative that must never be logged",
        "password": "x",
        "api_key": "y",
        "phone": "9999999999",
        "note": "z" * 1000,
        "nested": {"secret": "s", "ok": 1},
    })
    assert out["case_master_id"] == 123
    assert out["crime_no"] == "18-digit-synthetic"
    assert out["draft_key"] == "DR-ABC"
    for dropped in ("brief_facts", "password", "api_key", "phone"):
        assert dropped not in out
    assert len(out["note"]) <= 302            # truncated (+ ellipsis)
    assert out["nested"] == {"ok": 1}         # sensitive nested key dropped


@requires_db
def test_audit_record_written_same_transaction(rw_rollback):
    log_id = audit.record(audit.Action.MODEL_RUN, "model_inference", 999,
                          actor="io.audit.test", conn=rw_rollback,
                          detail={"foo": "bar", "brief_facts": "must be dropped"})
    assert log_id
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "action","resource","resource_id","detail" '
                    'FROM "audit_logs" WHERE "log_id"=%s', (log_id,))
        action, resource, rid, detail = cur.fetchone()
    assert action == audit.Action.MODEL_RUN
    assert resource == "model_inference"
    assert rid == "999"
    assert "brief_facts" not in detail
    assert detail.get("foo") == "bar"
    assert detail.get("demo_actor") == "io.audit.test"
    rw_rollback.rollback()


@requires_db
def test_audit_resolves_known_actor_to_user(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "username","user_id" FROM "users" LIMIT 1')
        row = cur.fetchone()
    if not row:
        pytest.skip("no users seeded")
    username, expected_uid = row[0], int(row[1])
    log_id = audit.record(audit.Action.UPDATE, "case", 1, actor=username, conn=rw_rollback)
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "user_id" FROM "audit_logs" WHERE "log_id"=%s', (log_id,))
        assert int(cur.fetchone()[0]) == expected_uid
    rw_rollback.rollback()


@requires_db
def test_intake_create_writes_audit_event(rw_rollback):
    """A sensitive intake write records an audit event in the same transaction."""
    from app.intake import service
    from app.intake.schemas import CreateDraftRequest
    conn = rw_rollback
    key = service._create_draft(conn, CreateDraftRequest(
        case_kind="fir_standard", created_by_actor="io.audit.test"))
    with conn.cursor() as cur:
        cur.execute(
            'SELECT count(*) FROM "audit_logs" WHERE "action"=%s '
            'AND "resource"=%s AND "resource_id"=%s',
            (audit.Action.INTAKE_CREATE, "intake_draft", key))
        assert int(cur.fetchone()[0]) == 1
    conn.rollback()


# ===========================================================================
# Request-context middleware: echoes request id + exposes demo actor
# ===========================================================================
def test_request_context_echoes_request_id_and_actor():
    from app.request_context import RequestContextMiddleware, current_context
    mini = FastAPI()
    mini.add_middleware(RequestContextMiddleware)

    @mini.get("/ctx")
    def _ctx():
        c = current_context()
        return {"actor": c.actor if c else None, "rid": c.request_id if c else None}

    c = TestClient(mini)
    r = c.get("/ctx", headers={"X-Request-ID": "corr-abc-123", "X-Demo-Actor": "demo.crime_analyst"})
    assert r.headers.get("X-Request-ID") == "corr-abc-123"
    body = r.json()
    assert body["actor"] == "demo.crime_analyst"
    assert body["rid"] == "corr-abc-123"


def test_request_context_generates_request_id_when_absent():
    from app.request_context import RequestContextMiddleware
    mini = FastAPI()
    mini.add_middleware(RequestContextMiddleware)

    @mini.get("/ok")
    def _ok():
        return {"ok": True}

    r = TestClient(mini).get("/ok")
    assert r.headers.get("X-Request-ID")   # generated correlation id present
