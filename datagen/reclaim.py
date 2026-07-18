"""Reclaim disk on the dev Supabase by truncating the (logically empty but
physically bloated) fixture tables left by a rolled-back load, then report size.
Synthetic dev DB only; reference/governance tables are preserved."""
from __future__ import annotations

import psycopg2

from .loader import TRUNCATE_TABLES
from .preflight import _with_sslmode, resolve_dsn


def main() -> int:
    conn = psycopg2.connect(_with_sslmode(resolve_dsn()), connect_timeout=30)
    conn.autocommit = True
    cur = conn.cursor()
    # A disk-full event can leave the project in read-only mode. TRUNCATE only
    # SHRINKS storage (no new pages), so override the read-only default and
    # reclaim table by table (biggest first) so partial progress still frees disk.
    try:
        cur.execute("SET default_transaction_read_only = off")
    except Exception as exc:
        print(f"note: could not clear read-only default: {exc}")
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"database size before: {cur.fetchone()[0]}")
    existing = []
    for t in TRUNCATE_TABLES:
        cur.execute("SELECT to_regclass(%s)", (f'public."{t}"',))
        if cur.fetchone()[0] is not None:
            existing.append(t)

    # order biggest-first so the first successful truncate frees the most disk,
    # giving headroom for the remaining (near-full-disk recovery).
    cur.execute(
        "SELECT c.relname, pg_total_relation_size(c.oid) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r'")
    sizes = {r[0]: r[1] for r in cur.fetchall()}
    ordered = sorted(existing, key=lambda t: sizes.get(t, 0), reverse=True)

    done, failed = 0, []
    # two passes: near-full disk sometimes needs the first frees before later ones fit
    for _pass in range(2):
        for t in list(ordered):
            try:
                cur.execute(f'TRUNCATE "{t}" RESTART IDENTITY CASCADE')
                done += 1
                ordered.remove(t)
            except Exception as exc:
                failed.append((t, str(exc)[:60]))
        if not ordered:
            break
    print(f"truncated {done} fixture tables; {len(ordered)} still pending.")
    if ordered:
        print(f"  pending: {ordered[:10]}")
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"database size now: {cur.fetchone()[0]}")
    conn.close()
    return 0 if not ordered else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
