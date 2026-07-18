"""Read-only DB size diagnostic (no secrets printed). Reports database size and
the largest relations so the loader footprint can be reasoned about."""
from __future__ import annotations

import psycopg2

from .preflight import _with_sslmode, resolve_dsn


def main() -> int:
    conn = psycopg2.connect(_with_sslmode(resolve_dsn()), connect_timeout=30)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())), "
                "pg_database_size(current_database())")
    pretty, raw = cur.fetchone()
    print(f"database size: {pretty} ({raw:,} bytes)")
    cur.execute(
        """
        SELECT n.nspname||'.'||c.relname AS rel,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','m','i')
        ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 25
        """)
    print("largest relations:")
    for rel, total in cur.fetchall():
        print(f"  {rel:<48} {total}")
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
