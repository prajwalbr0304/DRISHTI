"""Guarded SQL validation (doc 02 §6 — "read-only, enforced at execution").

The LLM's SQL is a *proposal*. Before it can touch the database it must pass this
gate, which is defense-in-depth ON TOP of the drishti_readonly role + read-only
transaction (db.ro_conn). Pure functions, no DB — so every rule is unit-testable.

Rules:
  * one statement only (no stacked `;` queries),
  * must be a SELECT (or a WITH … SELECT CTE),
  * no DDL/DML or transaction/role/config keywords anywhere,
  * no dangerous server-side functions (pg_sleep, pg_read_file, dblink, …),
  * no dollar-quoted strings, no comment smuggling,
  * a hard length cap; results are wrapped in a row-capping subquery.
Keyword scanning runs on a "code-only" copy with string literals and quoted
identifiers blanked out, so data values / column names never cause a false hit.
"""
from __future__ import annotations

import re


class GuardError(ValueError):
    """Raised when a proposed SQL statement violates the read-only guard."""


MAX_SQL_LEN = 6000

# Whole-word keywords that must never appear in a read-only SELECT.
_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate", "rename",
    "grant", "revoke", "merge", "upsert", "call", "do", "copy", "vacuum", "analyze",
    "reindex", "cluster", "lock", "set", "reset", "execute", "prepare", "deallocate",
    "listen", "notify", "unlisten", "comment", "refresh", "checkpoint", "discard",
    "begin", "start", "commit", "rollback", "savepoint", "into", "returning",
    "security", "temporary", "temp", "unlogged", "owner", "password", "authorization",
)
# Dangerous functions (matched as name-followed-by-paren).
_FORBIDDEN_FUNCS = (
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "pg_read_server_files", "lo_import", "lo_export", "dblink", "dblink_exec",
    "set_config", "current_setting", "pg_terminate_backend", "pg_cancel_backend",
    "pg_reload_conf", "query_to_xml", "xmlelement", "pg_settings", "txid_current",
    "setval", "nextval", "currval",
)

_LINE_COMMENT = re.compile(r"--[^\n\r]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z0-9_]*\$")
_KEYWORD_RES = {kw: re.compile(rf"\b{kw}\b", re.IGNORECASE) for kw in _FORBIDDEN_KEYWORDS}
_FUNC_RES = {fn: re.compile(rf"\b{fn}\s*\(", re.IGNORECASE) for fn in _FORBIDDEN_FUNCS}


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql))


def _code_only(sql: str) -> str:
    """Blank string literals + quoted identifiers so keyword scanning only sees
    actual SQL syntax, never data or column names."""
    s = _STRING_LITERAL.sub(" '' ", sql)
    s = _QUOTED_IDENT.sub(' "" ', s)
    return s


def validate_select(sql: str) -> str:
    """Validate a proposed statement is a single read-only SELECT.

    Returns the cleaned SQL (comments + trailing `;` removed) ready to execute.
    Raises GuardError on any violation.
    """
    if not sql or not sql.strip():
        raise GuardError("Empty SQL.")
    if len(sql) > MAX_SQL_LEN:
        raise GuardError("SQL exceeds the maximum allowed length.")
    if _DOLLAR_QUOTE.search(sql):
        raise GuardError("Dollar-quoted strings are not allowed.")

    cleaned = _strip_comments(sql).strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    code = _code_only(cleaned)
    # No further statement separators once the (single) trailing ';' is gone.
    code_trim = code.strip()
    if code_trim.endswith(";"):
        code_trim = code_trim[:-1]
    if ";" in code_trim:
        raise GuardError("Only a single statement is allowed (no `;`).")

    low = code_trim.lstrip().lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise GuardError("Only SELECT (or WITH … SELECT) queries are allowed.")
    if not re.search(r"\bselect\b", low):
        raise GuardError("Query must be a SELECT.")

    for kw, rx in _KEYWORD_RES.items():
        if rx.search(code_trim):
            raise GuardError(f"Forbidden keyword in query: '{kw.upper()}'. Read-only SELECT only.")
    for fn, rx in _FUNC_RES.items():
        if rx.search(code_trim):
            raise GuardError(f"Forbidden function in query: '{fn}()'.")

    return cleaned


def enforce_limits(sql: str, row_cap: int) -> str:
    """Wrap a validated SELECT so it can never return more than `row_cap` rows.
    The subquery wrapper also means any trailing text would be a syntax error."""
    cap = max(1, int(row_cap))
    return f"SELECT * FROM (\n{sql}\n) AS drishti_q LIMIT {cap}"
