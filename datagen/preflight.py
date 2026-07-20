"""Safe, read-only database preflight for DRISHTI Datagen v2.

This module opens a *strictly read-only* connection to the development AWS RDS
PostgreSQL analytics database referenced by ``DATABASE_URL`` and reproduces a
schema / row-count baseline so the loader can reason about the target before
doing anything destructive.

Hard safety rules enforced here (Phase 1, prompt A):
  * The connection runs with ``default_transaction_read_only = on`` AND each
    statement runs inside a READ ONLY transaction, so no write can occur.
  * Secret values (password, keys, full DSN) are NEVER printed, logged or
    returned. Only a redacted host label is surfaced.
  * Row *contents* are never selected — only COUNT(*), catalog metadata and the
    non-secret synthetic marker.

The synthetic marker (``synthetic_meta`` / ``app_environment``) is created by
migration ``005_security_rls_audit.sql``. Until it exists the target is treated
as *unconfirmed*: the loader then requires an explicit
``--confirm-synthetic-dev-target`` flag before any reload.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import psycopg2

# The synthetic-environment marker value the whole pipeline agrees on.
SYNTHETIC_ENV_VALUE = "synthetic_hackathon"

# Legacy tables whose live counts the audit reported. Used to reproduce the
# baseline. COUNT(*) only — never row contents.
BASELINE_TABLES = [
    "CaseMaster", "ComplainantDetails", "Victim", "Accused", "ArrestSurrender",
    "ChargesheetDetails", "ActSectionAssociation", "Inv_OccuranceTime",
    "inv_arrestsurrenderaccused", "State", "District", "Unit", "Employee",
    "Court", "EntityGraph", "NetworkEdge", "GangMembership", "CrimeRiskScore",
    "CrimePrediction", "CrimeHotspot", "CrimePattern", "CrimeEmbedding",
    "AISummary", "AlertHistory", "ModelVersion", "ModelInference",
    "FinancialAccount", "FinancialTransaction", "TransactionLink",
    "CaseEvidence", "audit_logs", "SavedQuery", "users", "roles",
]


def resolve_dsn() -> str:
    """Return DATABASE_URL (the AWS RDS analytics URI; never printed)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # pragma: no cover
        pass
    return os.getenv("DATABASE_URL") or ""


def redact_target(dsn: str) -> str:
    """A safe, non-secret label for logs, e.g. ``<db>.<region>.rds.amazonaws.com:5432``.

    Never includes user, password or query string.
    """
    if not dsn:
        return "<no DATABASE_URL configured>"
    try:
        u = urlparse(dsn)
        host = u.hostname or "?"
        # Redact the middle of the project ref so logs cannot leak it fully.
        parts = host.split(".")
        if parts and len(parts[0]) > 6:
            parts[0] = parts[0][:3] + "***"
        host = ".".join(parts)
        port = f":{u.port}" if u.port else ""
        return f"{host}{port}"
    except Exception:
        return "<unparseable target>"


def _with_sslmode(dsn: str) -> str:
    """AWS RDS requires TLS; add sslmode=require if the caller omitted it."""
    if not dsn:
        return dsn
    if "sslmode=" in dsn:
        return dsn
    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}sslmode=require"


def connect_readonly(dsn: str, *, connect_timeout: int = 20):
    """Open a connection pinned to read-only at the session level.

    Two independent guards: session ``default_transaction_read_only=on`` plus a
    read-only transaction per cursor use.
    """
    if not dsn:
        raise RuntimeError(
            "No DATABASE_URL configured. Set it in .env (never commit the value)."
        )
    conn = psycopg2.connect(_with_sslmode(dsn), connect_timeout=connect_timeout)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        # Belt-and-braces: pin the session GUC too.
        cur.execute("SET default_transaction_read_only = on")
    return conn


@dataclass
class Baseline:
    ok: bool
    target: str
    server_version: Optional[str] = None
    extensions: List[str] = field(default_factory=list)
    user_table_count: int = 0
    counts: Dict[str, int] = field(default_factory=dict)
    rls_enabled_tables: List[str] = field(default_factory=list)
    synthetic_marker: Optional[str] = None
    synthetic_confirmed: bool = False
    v2_tables_present: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "DRISHTI Datagen v2 — read-only preflight",
            "=" * 70,
            f"target                 : {self.target}",
        ]
        if not self.ok:
            lines.append(f"status                 : UNREACHABLE ({self.error})")
            lines.append("=" * 70)
            return "\n".join(lines)
        lines += [
            f"server_version         : {self.server_version}",
            f"extensions             : {', '.join(self.extensions) or '(none)'}",
            f"user tables (public)   : {self.user_table_count}",
            f"synthetic marker       : {self.synthetic_marker or '(absent - unconfirmed)'}",
            f"synthetic confirmed    : {self.synthetic_confirmed}",
            f"RLS-enabled app tables : {len(self.rls_enabled_tables)}"
            + (f" -> {self.rls_enabled_tables}" if self.rls_enabled_tables else " (all disabled)"),
            f"v2 tables present      : {len(self.v2_tables_present)}",
            "-" * 70,
            "row counts (COUNT(*) only — no row contents read):",
        ]
        for t, n in self.counts.items():
            lines.append(f"  {t:<28} {n:>12,}")
        lines.append("=" * 70)
        return "\n".join(lines)


def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f'public."{name}"',))
    return cur.fetchone()[0] is not None


def gather_baseline(conn, *, extra_tables: Optional[List[str]] = None) -> Baseline:
    target = "(connected)"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('server_version')")
            server_version = cur.fetchone()[0]

            cur.execute("SELECT extname FROM pg_extension ORDER BY extname")
            extensions = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                """
            )
            user_table_count = cur.fetchone()[0]

            # RLS state across public base tables (relrowsecurity=true == enabled).
            cur.execute(
                """
                SELECT c.relname FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND c.relrowsecurity = true
                ORDER BY c.relname
                """
            )
            rls_enabled_tables = [r[0] for r in cur.fetchall()]

            # Row counts (COUNT only). Skip tables that do not exist.
            counts: Dict[str, int] = {}
            for t in BASELINE_TABLES + list(extra_tables or []):
                if _table_exists(cur, t):
                    cur.execute(f'SELECT count(*) FROM public."{t}"')
                    counts[t] = cur.fetchone()[0]

            # v2 canonical tables (created by 006-009). Report which exist.
            v2_candidates = [
                "SyntheticDataRun", "SourceSystem", "SourceRecord",
                "IngestionJob", "DataQualityIssue", "CanonicalPerson",
                "CanonicalOrganisation", "CanonicalEntity", "CasePartyRole",
                "PersonAlias", "PersonIdentifier", "CaseSource", "CaseVersion",
                "CaseEvent", "EvidenceItem", "EvidenceObject", "Statement",
                "Seizure", "PropertyItem", "Device", "CommunicationEvent",
                "LocationObservation", "CourtEvent", "BailEvent",
                "CaseDisposition", "OutcomeObservation", "JurisdictionBoundary",
                "UnitLocation", "FeatureDefinition", "FeatureSnapshot",
                "OutcomeLabel", "PredictionRequest", "PredictionResult",
            ]
            v2_present = [t for t in v2_candidates if _table_exists(cur, t)]

            # Synthetic marker (present only after migration 005).
            synthetic_marker = None
            synthetic_confirmed = False
            if _table_exists(cur, "synthetic_meta"):
                cur.execute(
                    'SELECT "Value" FROM public."synthetic_meta" '
                    "WHERE \"Key\" = 'app_environment' LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    synthetic_marker = row[0]
                    synthetic_confirmed = row[0] == SYNTHETIC_ENV_VALUE

        return Baseline(
            ok=True,
            target=target,
            server_version=server_version,
            extensions=extensions,
            user_table_count=user_table_count,
            counts=counts,
            rls_enabled_tables=rls_enabled_tables,
            synthetic_marker=synthetic_marker,
            synthetic_confirmed=synthetic_confirmed,
            v2_tables_present=v2_present,
        )
    except Exception as exc:  # pragma: no cover - reported, never raised with secrets
        return Baseline(ok=False, target=target, error=_safe_err(exc))


_SECRET_RE = re.compile(r"(postgres(?:ql)?://[^@\s]+@)|(password=\S+)", re.IGNORECASE)


def _safe_err(exc: Exception) -> str:
    """Scrub any credential-looking substring from an error message."""
    msg = str(exc)
    return _SECRET_RE.sub("<redacted>", msg)


def run_preflight(dsn: Optional[str] = None) -> Baseline:
    dsn = dsn or resolve_dsn()
    target = redact_target(dsn)
    try:
        conn = connect_readonly(dsn)
    except Exception as exc:
        return Baseline(ok=False, target=target, error=_safe_err(exc))
    try:
        base = gather_baseline(conn)
        base.target = target
        return base
    finally:
        conn.close()


if __name__ == "__main__":
    print(run_preflight().summary())
