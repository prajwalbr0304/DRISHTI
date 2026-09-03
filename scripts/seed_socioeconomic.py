#!/usr/bin/env python
"""Refresh only DRISHTI's synthetic district context time series.

This leaves FIRs and every operational table untouched. Writes are permitted
only when the database carries the synthetic-development marker and the caller
passes the explicit confirmation flag.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datagen import reference
from datagen.config import GenConfig
from datagen.context import Context
from datagen.db import connect, reset_identity
from datagen.intelligence import _indicators
from datagen.loader import synthetic_marker
from datagen.preflight import SYNTHETIC_ENV_VALUE, resolve_dsn
from datagen.rng import RNG


TABLES = (
    ("SocialIndicator", "SocialIndicatorID"),
    ("EconomicIndicator", "EconomicIndicatorID"),
    ("WeatherIndicator", "WeatherIndicatorID"),
)


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _district_context(conn) -> Context:
    by_name = {
        name: {"name": name, "lat": lat, "lon": lon, "tags": tags, "pop_weight": weight}
        for name, lat, lon, tags, weight in reference.KARNATAKA_DISTRICTS
    }
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictID", "DistrictName" FROM "District" '
                    'WHERE "Active" IS TRUE ORDER BY "DistrictID"')
        db_districts = cur.fetchall()

    missing = [name for _, name in db_districts if name not in by_name]
    if missing:
        raise RuntimeError(f"No synthetic profile metadata for district(s): {', '.join(missing)}")

    ctx = Context()
    ctx.districts = [{"id": int(did), **by_name[name]} for did, name in db_districts]
    return ctx


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh synthetic district socio-economic data")
    parser.add_argument("--dsn", help="override DATABASE_URL")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=_date, default=dt.date(2021, 1, 1))
    parser.add_argument("--end", type=_date, default=dt.date(2025, 12, 31))
    parser.add_argument("--confirm-synthetic-dev-target", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirm_synthetic_dev_target:
        parser.error("--confirm-synthetic-dev-target is required")
    dsn = args.dsn or resolve_dsn()
    if not dsn:
        parser.error("DATABASE_URL or --dsn is required")

    cfg = GenConfig(seed=args.seed, start_date=args.start, end_date=args.end, dsn=dsn)
    conn = connect(dsn)
    try:
        marker = synthetic_marker(conn)
        if marker != SYNTHETIC_ENV_VALUE:
            raise RuntimeError(
                f"Refusing to write: expected synthetic marker {SYNTHETIC_ENV_VALUE!r}, got {marker!r}")
        ctx = _district_context(conn)
        with conn.cursor() as cur:
            for table, _ in TABLES:
                cur.execute(f'DELETE FROM "{table}"')
            written = _indicators(cur, cfg, ctx, RNG(args.seed * 99 + 5))
            for table, column in TABLES:
                reset_identity(cur, table, column)
        conn.commit()

        with conn.cursor() as cur:
            counts = {}
            for table, _ in TABLES:
                cur.execute(f'SELECT COUNT(*), COUNT(DISTINCT "DistrictID") FROM "{table}"')
                counts[table] = tuple(int(v) for v in cur.fetchone())
        print(f"Seeded {written:,} district-context observations across {len(ctx.districts)} districts.")
        for table, (rows, districts) in counts.items():
            print(f"  {table:<20} rows={rows:,} districts={districts}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
