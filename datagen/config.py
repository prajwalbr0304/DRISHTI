"""Configuration for the data generation engine.

All sizes, the random seed, the date window and the database connection are
centralised here. Values can be overridden from the CLI (see scripts/generate.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()  # load .env from CWD if present
except Exception:  # pragma: no cover - dotenv is optional
    pass


# A very large per-worker id block. Each parallel worker owns a disjoint id
# range [worker_index * ID_BLOCK, ...) for every child table, which guarantees
# globally unique primary keys and valid foreign keys without any coordination.
# 5,000,000 keeps worker_index * ID_BLOCK inside the 32-bit INTEGER range used
# by the child tables (Accused/Victim/... are INTEGER) for up to ~400 workers.
ID_BLOCK = 5_000_000


@dataclass
class GenConfig:
    """Top-level generation configuration."""

    # ---- reproducibility -----------------------------------------------------
    seed: int = 42

    # ---- parallelism ---------------------------------------------------------
    workers: int = 4            # process pool size for case expansion
    copy_chunk: int = 20_000    # rows per COPY buffer flush

    # ---- volumes (targets) ---------------------------------------------------
    n_states: int = 1
    n_districts: int = 32       # Karnataka districts (real list, see reference.py)
    n_stations: int = 1_000
    n_officers: int = 12_000    # realistic ratio: many FIRs per officer
    n_courts: int = 500
    n_firs: int = 100_000

    # Per-FIR cardinality. Base means come from each crime-type profile; these
    # global multipliers tune the totals to the requested state-wide volumes
    # (calibrated so 100k FIRs -> ~300k accused / ~250k victims / ~100k arrests /
    # ~120k complainants / ~40k chargesheets).
    accused_scale: float = 1.5            # profile accused_mean * scale
    victim_scale: float = 1.8             # profile victims_mean * scale
    complainants_per_fir_mean: float = 0.75  # Poisson lambda (>=1 for most FIRs)
    arrested_mean: float = 2.4            # extra arrested accused per cleared FIR
    chargesheet_rate: float = 0.40        # -> ~40k chargesheets

    # ---- temporal window -----------------------------------------------------
    start_date: date = date(2021, 1, 1)
    end_date: date = date(2025, 12, 31)

    # ---- criminal population -------------------------------------------------
    n_repeat_offenders: int = 18_000  # pool of recurring criminal identities
    n_gangs: int = 60                 # organized-crime gangs

    # ---- intelligence layer sampling ----------------------------------------
    embedding_dim: int = 768          # MUST match the vector(n) column in SQL
    n_case_embeddings: int = 8_000    # cases to embed (subset for size)
    n_case_summaries: int = 6_000     # cases to summarise
    entity_sample: int = 15_000       # accused promoted to graph entities
    max_network_edges: int = 120_000

    # ---- database ------------------------------------------------------------
    dsn: str = field(default_factory=lambda: _resolve_dsn())
    schema: str = "public"

    # ---- behaviour switches --------------------------------------------------
    truncate_first: bool = False      # wipe target tables before loading
    load_intelligence: bool = True    # generate the AI/analytics layer

    def worker_config(self, worker_index: int) -> "GenConfig":
        """Return a shallow copy tagged with a deterministic per-worker seed."""
        return replace(self, seed=self.seed * 1_000_003 + worker_index + 1)


def _resolve_dsn() -> str:
    """Resolve a libpq DSN / connection URL from the environment.

    Priority:
      1. DATABASE_URL  (full postgres:// URL, recommended)
      2. Individual standard PG* components

    The target is the AWS RDS PostgreSQL analytics database. Use the RDS endpoint
    as DATABASE_URL, e.g.:
        postgresql://<user>:<password>@<db>.<region>.rds.amazonaws.com:5432/drishti?sslmode=require
    AWS RDS requires TLS. (Supabase is no longer used — the project runs on AWS
    RDS + Zoho Catalyst.)
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PGHOST")
    if host:
        user = os.getenv("PGUSER") or "postgres"
        pwd = os.getenv("PGPASSWORD") or ""
        port = os.getenv("PGPORT") or "5432"
        db = os.getenv("PGDATABASE") or "drishti"
        sslmode = os.getenv("PGSSLMODE", "require")
        return (
            f"postgresql://{user}:{pwd}@{host}:{port}/{db}?sslmode={sslmode}"
        )

    # No connection info: return empty so callers can fail with a clear message.
    return ""
