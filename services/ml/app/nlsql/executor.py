"""Guarded executor for NL->SQL (doc 02 §6).

The ONLY path a model-proposed query reaches Postgres. Four independent guards:
  1. validate_select — single read-only SELECT, no DDL/DML/dangerous funcs (guard.py)
  2. enforce_scope   — role may not touch forbidden/PII tables; aggregate-only roles (scope.py)
  3. sealed origin   — CaseMaster aggregates require an exact server-authored capability
  4. db.ro_conn      — SET ROLE drishti_readonly + read-only transaction (privilege + txn)
Plus a statement timeout and a row cap. Returns the cleaned SELECT that was run
(for the "SQL executed" proof) and the result columns + rows.

Guard 3 exists so a case aggregate can never be computed over rows the analytics
policy excludes. A model-authored aggregate therefore cannot execute as written,
but it does NOT have to be thrown away: ``authorize_model_case_aggregate`` lets the
server COMPOSE the policy around the model's SQL by pointing every ``"CaseMaster"``
reference at a server-authored, policy-filtered CTE, and seals that composition.
The seal still only ever covers a string this module built, so the guarantee is
unchanged while the semantic planner's analytical SQL actually runs.
"""
from __future__ import annotations

import datetime as dt
import decimal
import re
from typing import Any, Optional

import psycopg2

from .. import db
from ..cases import casedata
from ..config import get_settings
from .guard import GuardError, enforce_limits, validate_select  # noqa: F401 (re-exported use)
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


# --------------------------------------------------------------------------- #
# Composing the case-analytics policy around a model-authored aggregate
# --------------------------------------------------------------------------- #
_POLICY_CTE = "drishti_case_master_policy"
_POLICY_SRC_ALIAS = "cm_policy_src"
_CASE_MASTER_QUOTED = '"CaseMaster"'
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')
_BARE_CASE_MASTER = re.compile(r"\bcasemaster\b", re.IGNORECASE)


def needs_case_aggregate_seal(sql: str) -> bool:
    """True when this exact SQL would be refused by :func:`execute_select` for
    lacking the server-authored CaseMaster aggregate seal."""
    try:
        cleaned = validate_select(sql)
    except GuardError:
        return False
    return (_requires_case_aggregate_authorization(cleaned)
            and not _has_exact_case_aggregate_authorization(sql, cleaned))


def _repoint_case_master(sql: str, replacement: str) -> Optional[str]:
    """Point every ``"CaseMaster"`` relation reference at ``replacement``.

    Returns ``None`` whenever a reference cannot be rewritten with certainty
    (unquoted/case-folded, schema-qualified, or none present at all), so the
    caller fails closed rather than composing SQL it cannot fully account for.
    """
    code_only = _QUOTED_IDENT.sub(" ", _STRING_LITERAL.sub(" ", sql))
    if _BARE_CASE_MASTER.search(code_only):
        return None                     # unquoted reference: not safely rewritable
    if replacement in sql or _POLICY_SRC_ALIAS in sql:
        return None                     # the model already uses our composed names

    out: list[str] = []
    prev_code_char = ""
    replaced = 0
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":                   # copy a string literal verbatim
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            prev_code_char = "'"
            i = j
            continue
        if ch == '"':
            if sql.startswith(_CASE_MASTER_QUOTED, i):
                if prev_code_char == ".":
                    return None         # schema-qualified: not safely rewritable
                out.append(replacement)
                prev_code_char = "r"
                i += len(_CASE_MASTER_QUOTED)
                replaced += 1
                continue
            j = i + 1                   # some other quoted identifier
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            prev_code_char = '"'
            i = j
            continue
        out.append(ch)
        if not ch.isspace():
            prev_code_char = ch
        i += 1

    return "".join(out) if replaced else None


def authorize_model_case_aggregate(sql: str) -> Optional[str]:
    """Seal a model-authored CaseMaster aggregate by composing policy around it.

    The model contributes only the shape of the analysis. This function authors
    the source relation: a CTE that selects ``CaseMaster`` through the current
    analytics-eligibility predicate, with every reference in the model's SQL
    repointed at it. The sealed string is therefore server-composed, and the
    exact-object seal in :func:`execute_select` keeps its original meaning.

    Returns ``None`` (fail closed — the caller should use a server-authored plan)
    when the SQL is not the guarded shape, carries a ``WITH`` clause of its own,
    or contains a ``"CaseMaster"`` reference that cannot be rewritten exactly.
    """
    raw = str(sql)
    try:
        cleaned = validate_select(raw)
    except GuardError:
        return None
    if not _requires_case_aggregate_authorization(cleaned):
        return None
    if not cleaned.lstrip().lower().startswith("select"):
        return None      # a model-authored WITH list cannot be safely prefixed
    body = _repoint_case_master(cleaned, _POLICY_CTE)
    if body is None:
        return None

    eligible = casedata.analytics_eligible_sql(_POLICY_SRC_ALIAS)
    composed = (
        f'WITH {_POLICY_CTE} AS (SELECT {_POLICY_SRC_ALIAS}.* '
        f'FROM "CaseMaster" {_POLICY_SRC_ALIAS} WHERE {eligible}) '
        f'{body}'
    )
    try:
        composed_cleaned = validate_select(composed)
    except GuardError:
        return None
    # The composition must still be the guarded shape it is being sealed for.
    if not _requires_case_aggregate_authorization(composed_cleaned):
        return None
    return _AuthorizedCaseAggregate(composed, composed_cleaned)


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
