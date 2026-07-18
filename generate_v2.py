#!/usr/bin/env python
"""DRISHTI Datagen v2 — scenario-driven synthetic generator + safe loader.

Pipeline: read-only preflight -> build fixture -> validate (all gates) ->
[optional] apply migrations -> [optional] backup marker + truncate -> load ->
repair identities -> DB-side integrity checks -> record run.

Examples
--------
Read-only preflight only (no build, no writes):
    python generate_v2.py --preflight-only

Offline dry-run + full validation of the golden fixture (NO database writes):
    python generate_v2.py --mode golden --validate-only

Apply migrations 005-009 to the dev Supabase (additive, safe):
    python generate_v2.py --migrate --no-build

Load + validate the golden fixture (destructive synthetic reload, gated):
    python generate_v2.py --mode golden --migrate --truncate \
        --confirm-synthetic-dev-target --write-fixture-files --run-id golden-001

Load the 100k statistical/performance fixture (after golden passes):
    python generate_v2.py --mode performance --firs 100000 --truncate \
        --confirm-synthetic-dev-target --run-id perf-001
"""
from __future__ import annotations

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SQL_DIR = os.path.join(REPO_ROOT, "services", "ml", "sql")
FIXTURE_ROOT = os.path.join(REPO_ROOT, "datagen", "fixtures")

MODE_DEFAULT_FIRS = {"golden": 2000, "statistical": 60000, "performance": 100000}


class _DummyCursor:
    """No-op cursor so the reference Context can be built without a database."""

    def copy_expert(self, sql, buf):
        pass

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return []


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DRISHTI Datagen v2 generator + loader")
    ap.add_argument("--mode", choices=["golden", "statistical", "performance"],
                    default="golden")
    ap.add_argument("--run-id", dest="run_id", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--firs", type=int, default=None, help="override case count")
    ap.add_argument("--workers", type=int, default=None,
                    help="accepted for parity; v2 build is single-process/deterministic")
    ap.add_argument("--dsn", default=None, help="override DATABASE_URL (never logged)")
    # actions
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--no-build", action="store_true",
                    help="skip fixture build (use with --migrate to only migrate)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + validate + print stats, NO database writes")
    ap.add_argument("--validate-only", action="store_true",
                    help="build + validate only, NO database writes")
    ap.add_argument("--migrate", action="store_true", help="apply migrations 005-009")
    ap.add_argument("--truncate", action="store_true",
                    help="destructive synthetic reload (requires confirm + backup marker)")
    ap.add_argument("--confirm-synthetic-dev-target", dest="confirm",
                    action="store_true",
                    help="explicit confirmation that the target is a synthetic dev DB")
    ap.add_argument("--load-derived", action="store_true",
                    help="also seed the governed aggregate model/prediction demo")
    ap.add_argument("--write-fixture-files", action="store_true",
                    help="write small evidence fixture files (recommended for golden)")
    ap.add_argument("--backup-file", default=None,
                    help="path for the pre-reload backup snapshot/marker")
    args = ap.parse_args(argv)

    # Import here so --help works without heavy deps.
    from datagen import build as V2BUILD
    from datagen import imports as IMPORTS_DEMO
    from datagen import loader as LOADER
    from datagen import preflight as PRE
    from datagen import validation as VAL
    from datagen.config import GenConfig
    from datagen.lookups import load_reference

    dsn = args.dsn or PRE.resolve_dsn()

    # --- 1. read-only preflight -------------------------------------------
    _log("Preflight (read-only) ...")
    base = PRE.run_preflight(dsn)
    print(base.summary())
    if args.preflight_only:
        return 0 if base.ok else 2

    # --- 2. config --------------------------------------------------------
    cfg = GenConfig()
    if args.seed is not None:
        cfg.seed = args.seed
    if args.workers is not None:
        cfg.workers = args.workers
    cfg.n_firs = args.firs if args.firs is not None else MODE_DEFAULT_FIRS[args.mode]
    run_key = args.run_id or f"{args.mode}-{int(time.time())}"
    out_dir = os.path.join(FIXTURE_ROOT, run_key)

    fixture = report = None
    if not args.no_build:
        _log(f"Building context (seed={cfg.seed}) ...")
        ctx = load_reference(_DummyCursor(), cfg)
        _log(f"Building v2 fixture: mode={args.mode} firs={cfg.n_firs:,} run={run_key}")
        t0 = time.time()
        fixture, world = V2BUILD.build_fixture(
            cfg, ctx, mode=args.mode, run_key=run_key,
            write_files=args.write_fixture_files, out_dir=out_dir, log=_log)
        _log(f"Built in {time.time() - t0:.1f}s. Domain totals:")
        for t, n in sorted(fixture.totals.items(), key=lambda kv: -kv[1]):
            print(f"    {t:<28} {n:>10,}")

        _log("Validating fixture (all integrity gates) ...")
        ok, report = VAL.validate(world, mode=args.mode)
        print(VAL.summarize(report))
        if not ok:
            _log("VALIDATION FAILED — refusing to load. Fix gates above.")
            return 3

    if args.dry_run or args.validate_only:
        _log("Offline run complete (no database writes).")
        return 0

    # --- 3. database phase ------------------------------------------------
    if not base.ok:
        _log("Cannot reach the database; aborting the load phase.")
        return 2

    conn = LOADER.connect(dsn)
    try:
        if args.migrate:
            _log("Applying migrations 005-009 ...")
            LOADER.apply_migrations(conn, SQL_DIR, log=_log)

        marker = LOADER.synthetic_marker(conn)
        if marker != PRE.SYNTHETIC_ENV_VALUE and not args.confirm:
            _log(f"Refusing to write: synthetic marker is {marker!r} and "
                 "--confirm-synthetic-dev-target was not supplied.")
            return 4

        if args.no_build:
            _log("No fixture built (--no-build); migrations/marker step done.")
            return 0

        ref_ok, got, exp = LOADER.reference_matches(conn, cfg)
        if not ref_ok:
            _log(f"Reference tables do not match config: got={got} expected={exp}. "
                 "A synthetic reference reload is required (not implemented in this "
                 "phase to protect governance seed). Aborting.")
            return 5
        # Preserved reference tables need the v2 lifecycle statuses added (additive).
        LOADER.ensure_reference_extensions(conn, log=_log)

        if args.truncate:
            if not args.confirm:
                _log("--truncate requires --confirm-synthetic-dev-target. Aborting.")
                return 4
            backup_path = args.backup_file or os.path.join(
                out_dir, "pre_reload_backup_marker.json")
            LOADER.create_backup_marker(conn, run_key, backup_path, log=_log)
            if not LOADER.has_backup_marker(conn):
                _log("No backup marker present after attempt; aborting reload.")
                return 6
            _log("Truncating fixture-populated tables (synthetic reload) ...")
            LOADER.truncate_fixture_tables(conn, log=_log)

        _log("Loading fixture ...")
        loaded = LOADER.load_fixture(conn, fixture, cfg, log=_log)

        if args.load_derived:
            _log("Seeding governed aggregate model + prediction demo ...")
            LOADER.seed_governed_model_demo(conn, log=_log)
            _log("Seeding Phase-8 golden import batches ...")
            IMPORTS_DEMO.seed_import_demo(conn, log=_log)

        LOADER.record_run(conn, fixture, report or {}, "loaded", log=_log)

        _log("Running DB-side integrity checks ...")
        checks = LOADER.db_integrity_checks(conn)
        print("=" * 70)
        print("DB INTEGRITY CHECKS (expect 0 everywhere)")
        print("=" * 70)
        bad = 0
        for name, n in checks.items():
            flag = "ok" if n == 0 else (f"FAIL={n}" if n > 0 else "SKIPPED")
            if n > 0:
                bad += 1
            print(f"  {name:<38} {flag}")
        print("=" * 70)
        if bad:
            _log(f"{bad} DB-side integrity check(s) failed.")
            return 7
        _log("Load complete. All DB-side integrity checks passed.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
