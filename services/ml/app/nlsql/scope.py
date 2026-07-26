"""Server-side role scoping for NL->SQL (doc 02 §6 — "scoped server-side …
NOT in the prompt").

A user must not be able to prompt past their access. The LLM is *shown* a
role-filtered schema, but the real guarantee is here: the final SQL is
re-checked against the same forbidden-table policy, and an aggregate-only query is
forced to be aggregate-only. This runs regardless of what produced the SQL, so
a crafted or jailbroken prompt still cannot read individual PII.

Pure functions, no DB — every rule is unit-testable.
"""
from __future__ import annotations

import re

from .schema import KNOWN_TABLES, forbidden_tables, requires_aggregate


class ScopeError(PermissionError):
    """Raised when a query exceeds the caller's role scope."""


_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_QUOTED = re.compile(r'"([^"]+)"')
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_AGG = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_GROUP_BY = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)


def _referenced_names(sql: str) -> set[str]:
    """All identifier tokens (quoted + unquoted), lower-cased, with string
    literals removed first so data values never look like table references."""
    no_lits = _STRING_LITERAL.sub(" ", sql)
    quoted = {m.group(1).lower() for m in _QUOTED.finditer(no_lits)}
    unquoted_src = re.sub(r'"[^"]*"', " ", no_lits)
    unquoted = {m.group(0).lower() for m in _IDENT.finditer(unquoted_src)}
    return quoted | unquoted


def is_aggregate(sql: str) -> bool:
    """True when the query aggregates (an aggregate fn or GROUP BY), ignoring
    anything inside string literals."""
    code = _STRING_LITERAL.sub(" ", sql)
    return bool(_AGG.search(code) or _GROUP_BY.search(code))


def referenced_tables(sql: str) -> set[str]:
    """Known DB tables the query touches — used for aggregate provenance."""
    names = _referenced_names(sql)
    return {t for t in KNOWN_TABLES if t.lower() in names}


def enforce_scope(sql: str, role: str) -> str:
    """Reject SQL that exceeds the role's scope. Returns the SQL unchanged when OK."""
    names = _referenced_names(sql)
    for t in forbidden_tables(role):
        if t.lower() in names:
            raise ScopeError(
                f"Access denied: your role ('{role}') may not query '{t}'. "
                "This is enforced server-side, not by the assistant."
            )
    if requires_aggregate(role) and not is_aggregate(sql):
        raise ScopeError(
            "Your role sees aggregate views only. Rephrase for a count/total by "
            "area or period (no individual records or case lists)."
        )
    return sql
