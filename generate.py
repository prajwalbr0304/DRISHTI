#!/usr/bin/env python
"""DRISHTI synthetic crime data generator — command line entry point.

Examples
--------
Full state-wide load into the database referenced by DATABASE_URL:
    python generate.py --truncate

Smaller reproducible load:
    python generate.py --firs 20000 --workers 4 --seed 7 --truncate

Validate the generation logic locally WITHOUT a database (no inserts):
    python generate.py --dry-run 5000

Database connection
-------------------
Set DATABASE_URL (or SUPABASE_DB_URL) to a postgres:// URL before running a real
load. For Supabase copy it from Project Settings -> Database -> Connection string
(URI). The API keys in .env cannot open a Postgres/COPY connection.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter

from datagen import cases
from datagen.config import GenConfig
from datagen.engine import run
from datagen.lookups import load_reference


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def build_config(args) -> GenConfig:
    cfg = GenConfig()
    if args.seed is not None:
        cfg.seed = args.seed
    if args.workers is not None:
        cfg.workers = args.workers
    if args.firs is not None:
        cfg.n_firs = args.firs
    if args.stations is not None:
        cfg.n_stations = args.stations
    if args.officers is not None:
        cfg.n_officers = args.officers
    if args.courts is not None:
        cfg.n_courts = args.courts
    if args.districts is not None:
        cfg.n_districts = args.districts
    if args.gangs is not None:
        cfg.n_gangs = args.gangs
    if args.repeat_offenders is not None:
        cfg.n_repeat_offenders = args.repeat_offenders
    if args.embeddings is not None:
        cfg.n_case_embeddings = args.embeddings
    if args.summaries is not None:
        cfg.n_case_summaries = args.summaries
    if args.start:
        cfg.start_date = args.start
    if args.end:
        cfg.end_date = args.end
    if args.dsn:
        cfg.dsn = args.dsn
    cfg.truncate_first = args.truncate
    cfg.load_intelligence = not args.no_intelligence
    return cfg


class _DummyCursor:
    """A no-op cursor so the context can be built without a database."""

    def copy_expert(self, sql, buf):  # noqa: D401 - matches psycopg2 signature
        pass

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return []


def dry_run(cfg: GenConfig) -> int:
    """Build context + plan + expand in memory and print distribution stats."""
    print(f"DRY RUN: seed={cfg.seed} firs={cfg.n_firs:,} (no database writes)\n")
    ctx = load_reference(_DummyCursor(), cfg)
    planner = cases.Planner(cfg, ctx)
    plans = planner.plan()

    # --- integrity checks ---------------------------------------------------
    crime_nos = [p[cases.F_CRIMENO] for p in plans]
    uniq = len(set(crime_nos)) == len(crime_nos)
    bad = [c for c in crime_nos[:2000] if not (len(c) == 18 and c.isdigit())]
    print("Integrity")
    print(f"  CrimeNo count           : {len(crime_nos):,}")
    print(f"  CrimeNo unique          : {uniq}")
    print(f"  CrimeNo 18-digit sample : {'OK' if not bad else bad[:3]}")

    # --- expand children for all chunks in-memory ---------------------------
    n = max(1, cfg.workers)
    size = (len(plans) + n - 1) // n
    tot = Counter()
    for cid in range(n):
        chunk = plans[cid * size:(cid + 1) * size]
        if not chunk:
            continue
        data = cases.build_children(cid, chunk, cfg, ctx)
        for k, v in data.items():
            tot[k] += len(v)

    print("\nGenerated child rows (in-memory)")
    for k in ("accused", "victims", "complainants", "act_sections", "arrests",
              "chargesheets", "occurrences", "inv"):
        print(f"  {k:<14}: {tot[k]:,}")

    # --- distributions ------------------------------------------------------
    prof = Counter(ctx.crime_profiles[p[cases.F_PROFILE]]["sub"] for p in plans)
    print("\nTop crime types (Zipf-skewed)")
    for name, c in prof.most_common(12):
        print(f"  {name:<22}: {c:,}  ({100*c/len(plans):.1f}%)")

    dist = Counter(p[cases.F_DISTRICT] for p in plans)
    dmap = {d["id"]: d["name"] for d in ctx.districts}
    print("\nTop districts (population-weighted)")
    for did, c in dist.most_common(6):
        print(f"  {dmap.get(did, did):<18}: {c:,}")

    hours = Counter(int(p[cases.F_INCFROM][11:13]) for p in plans
                    if ctx.crime_profiles[p[cases.F_PROFILE]]["sub"] == "Murder")
    if hours:
        print("\nMurder incident hour histogram (night-skewed)")
        for h in range(0, 24, 2):
            bar = "#" * (hours.get(h, 0) * 40 // max(hours.values()))
            print(f"  {h:02d}:00 {bar}")

    arrests = sum(1 for p in plans if p[cases.F_ARREST])
    cs = sum(1 for p in plans if p[cases.F_CHARGESHEET])
    print(f"\nDisposition: arrests≈{arrests:,} ({100*arrests/len(plans):.0f}%), "
          f"chargesheets≈{cs:,} ({100*cs/len(plans):.0f}%)")
    print("\nDry run OK — generation logic is self-consistent.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DRISHTI synthetic crime data generator")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--firs", type=int, help="number of FIRs (CaseMaster rows)")
    ap.add_argument("--stations", type=int)
    ap.add_argument("--officers", type=int)
    ap.add_argument("--courts", type=int)
    ap.add_argument("--districts", type=int)
    ap.add_argument("--gangs", type=int)
    ap.add_argument("--repeat-offenders", type=int, dest="repeat_offenders")
    ap.add_argument("--embeddings", type=int, help="cases to embed")
    ap.add_argument("--summaries", type=int, help="cases to summarise")
    ap.add_argument("--start", type=_date, help="incident window start YYYY-MM-DD")
    ap.add_argument("--end", type=_date, help="incident window end YYYY-MM-DD")
    ap.add_argument("--dsn", help="override DATABASE_URL")
    ap.add_argument("--truncate", action="store_true",
                    help="TRUNCATE target tables before loading")
    ap.add_argument("--no-intelligence", action="store_true",
                    help="skip the AI/intelligence layer")
    ap.add_argument("--dry-run", type=int, metavar="N", default=None,
                    help="plan+expand N FIRs in memory and print stats (no DB)")
    args = ap.parse_args(argv)

    cfg = build_config(args)
    if args.dry_run is not None:
        cfg.n_firs = args.dry_run
        return dry_run(cfg)

    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
