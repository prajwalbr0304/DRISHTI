"""Guarded executor for NL->SQL (doc 02 §6).

The ONLY path a model-proposed query reaches Postgres. Three independent guards:
  1. validate_select — single read-only SELECT, no DDL/DML/dangerous funcs (guard.py)
  2. enforce_scope   — role may not touch forbidden/PII tables; aggregate-only roles (scope.py)
  3. db.ro_conn      — SET ROLE drishti_readonly + read-only transaction (privilege + txn)
Plus a statement timeout and a row cap. Returns the cleaned SELECT that was run
(for the "SQL executed" proof) and the result columns + rows.
"""
from __future__ import annotations

import datetime as dt
import decimal
from typing import Any

import psycopg2

from .. import db
from ..config import get_settings
from .guard import enforce_limits, validate_select  # noqa: F401 (re-exported use)
from .scope import enforce_scope


class ExecutionError(RuntimeError):
    """A validated query failed at the database (timeout, unknown column, …)."""


def _coerce(v: Any) -> Any:
    """JSON-safe scalar coercion for result cells."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    return str(v)


def execute_select(proposed_sql: str, role: str) -> tuple[str, list[str], list[list[Any]]]:
    """Validate → scope → cap → run under the read-only role. Returns
    (cleaned_sql, columns, rows). Raises GuardError / ScopeError / ExecutionError."""
    settings = get_settings()
    cleaned = validate_select(proposed_sql)          # GuardError
    enforce_scope(cleaned, role)                     # ScopeError
    wrapped = enforce_limits(cleaned, settings.nlsql_row_cap)

    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {int(settings.nlsql_statement_timeout_ms)}")
                cur.execute(wrapped)
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = [[_coerce(v) for v in row] for row in cur.fetchall()]
    except psycopg2.Error as exc:
        # Clean, non-leaky message; the raw error is available in exc for logs.
        raw = str(getattr(exc, "pgerror", None) or exc).strip()
        msg = raw.splitlines()[0] if raw else "query failed"
        raise ExecutionError(msg) from exc

    return cleaned, columns, rows
