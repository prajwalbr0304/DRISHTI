"""Append-only audit trail for sensitive actions (Phase 3 hackathon access mode).

Writes one row to the existing ``audit_logs`` table (police_fir_extensions.sql)
for create/update/delete, import, evidence upload/download, entity changes,
model runs, prediction reviews and exports. Each row carries:

  * request id   (from the per-request context / X-Request-ID)
  * demo actor   (UX-simulation actor key — NOT authentication)
  * action, resource, resource id
  * client ip + timestamp (audit_logs.created_at default)

Safety:
  * NEVER logs secrets, full narratives, uploaded file contents, or obviously
    sensitive fields — the detail payload is sanitised (sensitive keys dropped,
    strings truncated, size capped) before it is stored.
  * When a DB connection is passed the audit row is written in the SAME
    transaction as the action (so a rolled-back action rolls back its audit and
    a committed action always has its audit event). Without a connection it is a
    best-effort background write that never raises into the request path.
"""
from __future__ import annotations

import ipaddress
import sys
from typing import Any, Optional

from psycopg2.extras import Json

from . import db
from .request_context import current_context


# --- canonical action names (Phase 3 §5) -----------------------------------
class Action:
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    IMPORT = "import"
    EVIDENCE_UPLOAD = "evidence.upload"
    EVIDENCE_DOWNLOAD = "evidence.download"
    ENTITY_CHANGE = "entity.change"
    MODEL_RUN = "model.run"
    PREDICTION_REVIEW = "prediction.review"
    EXPORT = "export"
    # intake lifecycle
    INTAKE_CREATE = "intake.create"
    INTAKE_SUBMIT = "intake.submit"
    INTAKE_APPROVE = "intake.approve"
    INTAKE_REJECT = "intake.reject"
    INTAKE_RETURN = "intake.return"
    CASE_EVENT = "case.event"


# Substrings that mark a detail key as sensitive -> the value is never stored.
# Precise on purpose: catch secrets/PII/free-text without dropping safe ids like
# "draft_key" or "crime_no" (which merely contain the letters "key"/"no").
_SENSITIVE_KEY_PARTS = (
    "password", "passwd", "secret", "token", "apikey", "api_key", "access_key",
    "private_key", "credential", "authorization", "cookie", "session", "jwt",
    "narrative", "brief_facts", "facts", "statement", "content", "file_bytes",
    "raw_payload", "date_of_birth", "dob", "phone", "mobile", "email",
    "aadhaar", "aadhar", "passport", "biometric", "latitude", "longitude",
    "address", "database_url", "connection_string", "conn_str",
)
_MAX_STR = 300          # truncate any stored string value
_MAX_KEYS = 25          # cap the number of detail keys


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(part in k for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        v = value.replace("\r", " ").replace("\n", " ")
        return v[:_MAX_STR] + ("…" if len(v) > _MAX_STR else "")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return sanitize_detail(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in list(value)[:_MAX_KEYS]]
    return _sanitize_value(str(value))


def sanitize_detail(detail: Optional[dict]) -> dict:
    """Drop sensitive keys, truncate strings and cap size. Non-mutating."""
    if not detail:
        return {}
    out: dict[str, Any] = {}
    for i, (k, v) in enumerate(detail.items()):
        if i >= _MAX_KEYS:
            break
        key = str(k)
        if _is_sensitive_key(key):
            continue
        out[key] = _sanitize_value(v)
    return out


def _resolve_user_id(conn, actor: Optional[str]) -> Optional[int]:
    """Best-effort demo actor -> users.user_id (audit FK). None if unmatched."""
    if not actor:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "user_id" FROM "users" WHERE "username"=%s LIMIT 1', (actor,))
            r = cur.fetchone()
        return int(r[0]) if r else None
    except Exception:  # noqa: BLE001 — never let actor resolution break audit
        return None


def _safe_ip(value: Optional[str]) -> Optional[str]:
    """An address PostgreSQL's `inet` will accept, or None.

    audit_logs.ip_address is `inet`, and this row is written in the SAME
    transaction as the operation it records so the two are atomic. That makes an
    unparseable address destructive out of proportion to its worth: the operation
    is rolled back because its audit note had a bad IP. Anything that is not an
    address is therefore dropped to NULL and the caller is still recorded in the
    detail payload.

    Not hypothetical — a proxy or test harness can supply a hostname rather than
    an address (Starlette's TestClient sends the literal "testclient"), which
    failed every audited write behind it.
    """
    if not value:
        return None
    host = str(value).strip()
    # X-Forwarded-For style lists: the first hop is the client.
    if "," in host:
        host = host.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def _write(conn, action: str, resource: Optional[str], resource_id: Optional[str],
           actor: Optional[str], detail: dict) -> Optional[int]:
    ctx = current_context()
    eff_actor = actor or (ctx.actor if ctx else None)
    safe = sanitize_detail(detail)
    # attach request context (never secret)
    if ctx:
        safe.setdefault("request_id", ctx.request_id)
        if ctx.role:
            safe.setdefault("demo_role", ctx.role)
    if eff_actor:
        safe.setdefault("demo_actor", eff_actor)
    raw_ip = ctx.client_ip if ctx else None
    ip = _safe_ip(raw_ip)
    # Keep what was actually seen when it could not be stored as an address, so
    # the trail does not silently lose the origin.
    if raw_ip and ip is None:
        safe.setdefault("client_host", _sanitize_value(raw_ip))
    user_id = _resolve_user_id(conn, eff_actor)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "audit_logs" ("user_id","action","resource","resource_id",'
            '"ip_address","detail") VALUES (%s,%s,%s,%s,%s,%s) RETURNING "log_id"',
            (user_id, action, resource,
             (str(resource_id) if resource_id is not None else None),
             ip, Json(safe)))
        return int(cur.fetchone()[0])


def record(action: str, resource: Optional[str] = None,
           resource_id: Optional[Any] = None, *,
           actor: Optional[str] = None, detail: Optional[dict] = None,
           conn=None) -> Optional[int]:
    """Record an audit event.

    * With ``conn`` — writes in that transaction (raises on failure so the
      action + its audit are atomic; inputs are sanitised so this does not fail
      in practice).
    * Without ``conn`` — best-effort background write on its own connection that
      never raises into the request path.
    """
    rid = str(resource_id) if resource_id is not None else None
    if conn is not None:
        return _write(conn, action, resource, rid, actor, detail or {})
    try:
        with db.rw_conn() as c:
            return _write(c, action, resource, rid, actor, detail or {})
    except Exception as exc:  # noqa: BLE001 — audit must not break the request
        print(f"[audit] background write failed: {type(exc).__name__}", file=sys.stderr)
        return None
