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
_AGGREGATE_FUNCTIONS = frozenset({
    "any_value", "array_agg", "avg", "bit_and", "bit_or", "bit_xor",
    "bool_and", "bool_or", "corr", "count", "covar_pop", "covar_samp",
    "cume_dist", "dense_rank", "every", "json_agg", "json_agg_strict",
    "json_object_agg", "json_object_agg_strict", "json_object_agg_unique",
    "json_object_agg_unique_strict", "jsonb_agg", "jsonb_agg_strict",
    "jsonb_object_agg", "jsonb_object_agg_strict", "jsonb_object_agg_unique",
    "jsonb_object_agg_unique_strict", "max", "min", "mode", "percent_rank",
    "percentile_cont", "percentile_disc", "range_agg", "range_intersect_agg",
    "rank", "stddev", "stddev_pop", "stddev_samp", "string_agg", "sum",
    "var_pop", "var_samp", "variance", "xmlagg",
    # Common PostGIS aggregates available to this database.
    "st_3dextent", "st_collect", "st_clusterintersecting", "st_clusterwithin",
    "st_extent", "st_makeline", "st_memunion", "st_polygonize", "st_union",
})
_SCALAR_FUNCTIONS = frozenset({
    # Conservative allowlist for ordinary operational projections/filters.
    "abs", "age", "btrim", "cast", "ceil", "ceiling", "char_length",
    "coalesce", "concat", "concat_ws", "date", "date_part", "date_trunc",
    "extract", "floor", "greatest", "least", "left", "length", "lower",
    "ltrim", "make_date", "nullif", "position", "replace", "right", "round",
    "rtrim", "split_part", "st_x", "st_y", "substring", "time", "timestamp",
    "timestamptz", "to_char", "to_date", "to_timestamp", "trim", "upper",
})
_SQL_CALL_KEYWORDS = frozenset({
    "all", "and", "any", "as", "distinct", "exists", "filter", "from",
    "group", "in", "not", "on", "or", "over", "partition", "select",
    "some", "using", "values", "where", "within",
})
_QUOTED_CALL = re.compile(r'"((?:[^"]|"")*)"\s*\(')
_BARE_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_$]*)\s*\(")
_GROUP_BY = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)


def _referenced_names(sql: str) -> set[str]:
    """All identifier tokens (quoted + unquoted), lower-cased, with string
    literals removed first so data values never look like table references."""
    no_lits = _STRING_LITERAL.sub(" ", sql)
    quoted = {m.group(1).lower() for m in _QUOTED.finditer(no_lits)}
    unquoted_src = re.sub(r'"[^"]*"', " ", no_lits)
    unquoted = {m.group(0).lower() for m in _IDENT.finditer(unquoted_src)}
    return quoted | unquoted


def _called_functions(sql: str) -> set[str]:
    """Function-like identifiers outside literals, including quoted names."""
    code = _STRING_LITERAL.sub(" ", sql)
    quoted = {
        m.group(1).replace('""', '"').lower()
        for m in _QUOTED_CALL.finditer(code)
    }
    without_quoted = re.sub(r'"(?:[^"]|"")*"', " ", code)
    bare = {m.group(1).lower() for m in _BARE_CALL.finditer(without_quoted)}
    return (quoted | bare) - _SQL_CALL_KEYWORDS


def _is_aggregate_function(name: str) -> bool:
    return name in _AGGREGATE_FUNCTIONS or name.startswith("regr_")


def is_aggregate(sql: str) -> bool:
    """Conservatively identify built-in aggregates or explicit grouping."""
    return bool(
        _GROUP_BY.search(_STRING_LITERAL.sub(" ", sql))
        or any(_is_aggregate_function(name) for name in _called_functions(sql))
    )


def has_unclassified_function(sql: str) -> bool:
    """True for function syntax not proven to be a known scalar operation.

    At the CaseMaster execution boundary this makes unknown/custom aggregate
    names fail closed without treating ordinary column-only lists as aggregates.
    """
    return any(
        not _is_aggregate_function(name) and name not in _SCALAR_FUNCTIONS
        for name in _called_functions(sql)
    )


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
