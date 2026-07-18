"""Network / demo-deployment hardening (Phase 3 hackathon access mode).

Provides:
  * ``verify_hackathon_startup()`` — refuses FastAPI startup when
    HACKATHON_MODE=true and the target database is not explicitly marked
    synthetic (fail-closed on a reachable non-synthetic DB; loud warning only on
    a transient connectivity failure, since the per-request write guards remain
    fail-closed).
  * ``masked_db_target()``          — a log-safe DB descriptor (kind + host, no
                                       user, no password) so a mis-routed
                                       DATABASE_URL is obvious at boot.
  * ``BodySizeLimitMiddleware``     — rejects over-sized request bodies (413).
  * ``RateLimitMiddleware``         — conservative per-client-IP fixed-window
                                       rate limit (429).
  * ``install_error_handlers()``    — API errors never return SQL, stack traces
                                       or credentials.

None of these log secrets.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

import psycopg2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .request_context import current_context


# ---------------------------------------------------------------------------
# Startup synthetic-database guard
# ---------------------------------------------------------------------------
def masked_db_target(url: str | None = None) -> str:
    """Log-safe descriptor of the DB target: kind + host + db only (no creds)."""
    url = url if url is not None else get_settings().database_url
    if not url:
        return "<no DATABASE_URL>"
    try:
        u = urlsplit(url)
        host = u.hostname or "?"
        db = (u.path or "/").lstrip("/") or "?"
        kind = ("supabase" if "supabase" in host
                else "aws-rds" if "rds.amazonaws.com" in host
                else "other")
        return f"{kind}:{host}/{db}"
    except Exception:  # noqa: BLE001
        return "<unparseable DATABASE_URL>"


def read_db_environment_marker() -> tuple[bool, str | None]:
    """(reachable, marker_value). Read-only; never raises. marker is None if
    unreachable or absent."""
    s = get_settings()
    if not s.database_url:
        return (False, None)
    try:
        conn = psycopg2.connect(s.database_url, connect_timeout=s.db_connect_timeout)
    except Exception:  # noqa: BLE001
        return (False, None)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute('SELECT "Value" FROM "synthetic_meta" WHERE "Key"=%s',
                        ("app_environment",))
            row = cur.fetchone()
        conn.rollback()
        return (True, row[0] if row else None)
    except Exception:  # noqa: BLE001
        return (True, None)  # reachable but marker table/row absent
    finally:
        conn.close()


def verify_hackathon_startup() -> None:
    """Refuse startup if hackathon mode is on and the DB is not synthetic.

    Raises RuntimeError when the database is reachable but its
    ``synthetic_meta.app_environment`` marker is missing or different from the
    expected value. A transient connectivity failure only logs a warning (the
    per-request write guards stay fail-closed)."""
    s = get_settings()
    target = masked_db_target()
    if not s.hackathon_mode:
        print(f"[startup] HACKATHON_MODE off. DB target: {target}")
        return
    reachable, marker = read_db_environment_marker()
    expected = s.synthetic_env_expected
    if not reachable:
        print(f"[startup] WARNING: DB unreachable at boot ({target}); "
              f"cannot confirm synthetic marker. Writes remain blocked until the "
              f"synthetic marker is confirmed per-request. Expected='{expected}'.")
        return
    if marker != expected:
        raise RuntimeError(
            "Refusing to start in HACKATHON_MODE: database "
            f"{target} is marked app_environment='{marker}', expected "
            f"'{expected}'. The server must never run hackathon mode against a "
            "database that is not explicitly marked synthetic.")
    print(f"[startup] hackathon mode OK — synthetic DB confirmed ({target}, "
          f"app_environment='{marker}').")


# ---------------------------------------------------------------------------
# Request-body size limit
# ---------------------------------------------------------------------------
class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds ``max_request_bytes`` (413)."""

    def __init__(self, app, *, max_bytes: int | None = None):
        super().__init__(app)
        self._max_bytes_override = max_bytes

    async def dispatch(self, request: Request, call_next):
        max_bytes = (self._max_bytes_override if self._max_bytes_override is not None
                     else get_settings().max_request_bytes)
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body too large (limit {max_bytes} bytes)."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length."})
        return await call_next(request)


# ---------------------------------------------------------------------------
# Per-client-IP fixed-window rate limit
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Conservative fixed-window limiter. Per-process (uvicorn worker); adequate
    for a localhost/single-edge hackathon demo. Reads settings live so tests can
    toggle it. Returns 429 with Retry-After when the window budget is spent."""

    def __init__(self, app, *, enabled: bool | None = None, per_minute: int | None = None):
        super().__init__(app)
        self._enabled_override = enabled
        self._limit_override = per_minute
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}  # ip -> (window_start_min, count)

    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        enabled = self._enabled_override if self._enabled_override is not None else s.rate_limit_enabled
        if not enabled:
            return await call_next(request)
        limit = self._limit_override if self._limit_override is not None else s.rate_limit_per_minute
        ip = request.client.host if request.client else "unknown"
        now_min = int(time.time() // 60)
        with self._lock:
            window, count = self._hits.get(ip, (now_min, 0))
            if window != now_min:
                window, count = now_min, 0
            count += 1
            self._hits[ip] = (window, count)
            # opportunistic prune so the map cannot grow without bound
            if len(self._hits) > 4096:
                self._hits = {k: v for k, v in self._hits.items() if v[0] == now_min}
        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down and retry."},
                headers={"Retry-After": "60"})
        return await call_next(request)


# ---------------------------------------------------------------------------
# Sanitised error responses (never leak SQL / stack traces / credentials)
# ---------------------------------------------------------------------------
def install_error_handlers(app: FastAPI) -> None:
    def _request_id(request: Request) -> str | None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return rid
        ctx = current_context()
        return ctx.request_id if ctx else None

    @app.exception_handler(psycopg2.Error)
    async def _db_error_handler(request: Request, exc: psycopg2.Error):  # noqa: ANN001
        # Never surface DB driver messages (they can echo SQL/identifiers).
        return JSONResponse(
            status_code=500,
            content={"detail": "A database error occurred.", "request_id": _request_id(request)})

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):  # noqa: ANN001
        # Generic, opaque message. The real error is logged server-side by the
        # ASGI server; the client sees nothing internal.
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": _request_id(request)})
