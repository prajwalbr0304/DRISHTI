"""Database access layers.

Two clearly separated context managers:

  * ``rw_conn()``  — full read/write connection (typed AI writes + audit rows).
                     Commits on success, rolls back on error.
  * ``ro_conn()``  — restricted connection that assumes ``drishti_readonly`` via
                     SET ROLE and runs READ ONLY. Any DML is blocked twice over
                     (no privilege + read-only transaction). This is the ONLY
                     layer the NL->SQL executor may use.

Fresh connections per use keep pooled session state (SET ROLE / read-only) from
leaking between callers — correctness over micro-throughput for this service.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

import numpy as np
import psycopg2
from psycopg2.extensions import AsIs, register_adapter

from .config import get_settings

# Safety net: this is a numpy-heavy ML service, so coerce numpy scalars to native
# Python when they are used as SQL parameters (psycopg2 would otherwise emit e.g.
# `np.float64(3.0)` and fail). JSON payloads are still converted at their source.
for _t in (np.float64, np.float32, np.float16):
    register_adapter(_t, lambda v: AsIs(repr(float(v))))
for _t in (np.int64, np.int32, np.int16, np.int8):
    register_adapter(_t, lambda v: AsIs(repr(int(v))))
register_adapter(np.bool_, lambda v: AsIs("TRUE" if bool(v) else "FALSE"))

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_role(name: str) -> str:
    """Role names cannot be parametrised in SQL; validate as a plain identifier."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid role identifier: {name!r}")
    return name


def _connect():
    s = get_settings()
    if not s.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Provide the full AWS RDS PostgreSQL URI for the "
            "retained analytics/historical corpus (server-side only; never shipped to "
            "the browser). The deployed operational serving path uses Catalyst Data "
            "Store / Stratus and does NOT require DATABASE_URL."
        )
    return psycopg2.connect(s.database_url, connect_timeout=s.db_connect_timeout)


@contextmanager
def rw_conn():
    """Read/write transaction. Commits on clean exit, rolls back on exception."""
    conn = _connect()
    try:
        # Ensure this explicitly read-write layer can actually commit even when
        # the database/role carries an inherited read-only default (e.g. a
        # managed-Postgres over-quota "soft" read-only, or a read-only role
        # default). Set at session scope while autocommit is on, before the
        # working transaction begins, so the transaction inherits read-write.
        # This is a no-op on a normally-configured read-write database; ro_conn()
        # stays strictly read-only (SET ROLE + read-only session).
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("SET SESSION default_transaction_read_only = off")
            except Exception:  # noqa: BLE001 — never let the guard break writes
                pass
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def ro_conn():
    """Read-only transaction executing as the restricted ``readonly_role``."""
    role = _validated_role(get_settings().readonly_role)
    conn = _connect()
    try:
        # default_transaction_read_only = on for every txn on this connection.
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(f'SET ROLE "{role}"')
        yield conn
        conn.rollback()  # nothing to persist on a read-only connection
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def ping() -> bool:
    """Lightweight connectivity check."""
    with rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1


def installed_extensions() -> dict[str, str | None]:
    """Return {extname: version} for extensions installed in the database."""
    with rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT extname, extversion FROM pg_extension")
            return {r[0]: r[1] for r in cur.fetchall()}
