"""Database access layer: connections, high-throughput COPY, sequence repair.

All bulk inserts go through ``copy_rows`` which streams rows to PostgreSQL using
COPY ... FROM STDIN (TEXT format) — the fastest generic ingestion path. Values
are serialised with a hand-rolled encoder that understands the exact wire format
PostgreSQL expects for TEXT COPY, plus the string forms accepted by the type
input functions for JSONB, PostGIS geometry (EWKT) and pgvector (bracketed list).
"""
from __future__ import annotations

import io
import json
from typing import Iterable, Sequence

import psycopg2


# ---------------------------------------------------------------------------
# Sentinels / value wrappers
# ---------------------------------------------------------------------------
class _Raw:
    """Marker base class for pre-formatted COPY values."""
    __slots__ = ("s",)

    def __init__(self, s: str):
        self.s = s


class Json(_Raw):
    """Wrap a python object to be emitted as JSON text into a jsonb column."""

    def __init__(self, obj):
        super().__init__(json.dumps(obj, separators=(",", ":"), default=str))


class Geom(_Raw):
    """PostGIS geometry as EWKT (accepted by the geometry input function)."""

    @classmethod
    def point(cls, lon: float, lat: float, srid: int = 4326) -> "Geom":
        return cls(f"SRID={srid};POINT({lon:.6f} {lat:.6f})")

    @classmethod
    def polygon(cls, ring: Sequence[tuple[float, float]], srid: int = 4326) -> "Geom":
        pts = ", ".join(f"{x:.6f} {y:.6f}" for x, y in ring)
        return cls(f"SRID={srid};POLYGON(({pts}))")


class Vector(_Raw):
    """pgvector literal, e.g. [0.1,0.2,0.3]."""

    def __init__(self, values):
        super().__init__("[" + ",".join(f"{float(v):.6f}" for v in values) + "]")


# ---------------------------------------------------------------------------
# TEXT COPY encoding
# ---------------------------------------------------------------------------
_NULL = r"\N"


def _encode(value) -> str:
    if value is None:
        return _NULL
    if isinstance(value, _Raw):
        return _escape(value.s)
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    return _escape(str(value))


def _escape(s: str) -> str:
    # Order matters: backslash first.
    if "\\" in s:
        s = s.replace("\\", "\\\\")
    if "\t" in s:
        s = s.replace("\t", "\\t")
    if "\n" in s:
        s = s.replace("\n", "\\n")
    if "\r" in s:
        s = s.replace("\r", "\\r")
    return s


def connect(dsn: str):
    if not dsn:
        raise RuntimeError(
            "No database connection configured. Set DATABASE_URL (or SUPABASE_DB_URL) "
            "to a postgres:// URL. For Supabase use Project Settings -> Database -> "
            "Connection string (URI). The API keys in .env cannot open a Postgres "
            "connection; a database password is required."
        )
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn


def copy_rows(cur, table: str, columns: Sequence[str],
              rows: Iterable[Sequence], chunk: int = 20_000) -> int:
    """Stream ``rows`` into ``table``/``columns`` via COPY. Returns row count."""
    collist = ", ".join(f'"{c}"' for c in columns)
    sql = f'COPY "{table}" ({collist}) FROM STDIN WITH (FORMAT text)'
    total = 0
    buf = io.StringIO()
    n = 0
    for row in rows:
        buf.write("\t".join(_encode(v) for v in row))
        buf.write("\n")
        n += 1
        total += 1
        if n >= chunk:
            buf.seek(0)
            cur.copy_expert(sql, buf)
            buf = io.StringIO()
            n = 0
    if n:
        buf.seek(0)
        cur.copy_expert(sql, buf)
    return total


# ---------------------------------------------------------------------------
# Maintenance helpers
# ---------------------------------------------------------------------------
def reset_identity(cur, table: str, id_column: str) -> None:
    """Advance an IDENTITY column past the max explicitly-inserted value."""
    cur.execute(f'SELECT COALESCE(MAX("{id_column}"), 0) FROM "{table}"')
    max_id = cur.fetchone()[0] or 0
    cur.execute(
        f'ALTER TABLE "{table}" ALTER COLUMN "{id_column}" RESTART WITH {max_id + 1}'
    )


def truncate_all(cur, tables: Sequence[str]) -> None:
    """TRUNCATE the given tables (RESTART IDENTITY, CASCADE) in one statement."""
    quoted = ", ".join(f'"{t}"' for t in tables)
    cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")


def fetch_all(cur, sql: str, params=None):
    cur.execute(sql, params)
    return cur.fetchall()
