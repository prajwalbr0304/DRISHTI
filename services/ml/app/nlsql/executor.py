"""Guarded executor for NL->SQL (doc 02 §6).

The ONLY path a model-proposed query reaches Postgres. Four independent guards:
  1. validate_select — single read-only SELECT, no DDL/DML/dangerous funcs (guard.py)
  2. enforce_scope   — role may not touch forbidden/PII tables; aggregate-only roles (scope.py)
  3. sealed origin   — CaseMaster aggregates require an exact server-authored capability
  4. db.ro_conn      — SET ROLE drishti_readonly + read-only transaction (privilege + txn)
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
from .scope import (ScopeError, enforce_scope, has_unclassified_function,
                    is_aggregate, referenced_tables)


class ExecutionError(RuntimeError):
    """A validated query failed at the database (timeout, unknown column, …)."""


_CASE_AGGREGATE_AUTHORITY = object()


class _AuthorizedCaseAggregate(str):
    """Opaque, process-local carrier for one exact server-authored query."""

    def __new__(cls, sql: str, cleaned_sql: str):
        obj = super().__new__(cls, sql)
        obj._authority = _CASE_AGGREGATE_AUTHORITY
        obj._cleaned_sql = cleaned_sql
        return obj


def _is_case_aggregate(sql: str) -> bool:
    return is_aggregate(sql) and "CaseMaster" in referenced_tables(sql)


def _requires_case_aggregate_authorization(sql: str) -> bool:
    """Fail closed for aggregates and function syntax not proven scalar."""
    return (
        "CaseMaster" in referenced_tables(sql)
        and (is_aggregate(sql) or has_unclassified_function(sql))
    )


def authorize_case_aggregate(sql: str) -> str:
    """Seal one exact server-authored aggregate over ``CaseMaster``.

    Only deterministic server code calls this factory. A model response, SQL
    comment, purpose label, or matching text cannot recreate the object identity
    carried by the returned string subclass.
    """
    raw = str(sql)
    cleaned = validate_select(raw)
    if not _is_case_aggregate(cleaned):
        raise ValueError("Case aggregate authorization requires an aggregate CaseMaster query")
    return _AuthorizedCaseAggregate(raw, cleaned)


def _has_exact_case_aggregate_authorization(proposed_sql: str, cleaned_sql: str) -> bool:
    return (
        isinstance(proposed_sql, _AuthorizedCaseAggregate)
        and getattr(proposed_sql, "_authority", None) is _CASE_AGGREGATE_AUTHORITY
        and getattr(proposed_sql, "_cleaned_sql", None) == cleaned_sql
    )


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
    """Validate → scope → authorize CaseMaster aggregates → cap → execute.

    Arbitrary/model-authored aggregate SQL over ``CaseMaster`` fails closed.
    Only an exact query sealed by :func:`authorize_case_aggregate` can cross this
    final application guard. Nonaggregate operational lookups/lists are preserved.
    """
    settings = get_settings()
    cleaned = validate_select(proposed_sql)          # GuardError
    enforce_scope(cleaned, role)                     # ScopeError
    if _requires_case_aggregate_authorization(
            cleaned) and not _has_exact_case_aggregate_authorization(proposed_sql, cleaned):
        raise ScopeError(
            "Aggregate or unclassified-function CaseMaster queries require an exact "
            "server-authored, policy-filtered plan. Arbitrary SQL is blocked."
        )
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
