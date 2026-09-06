"""Materialized-view refresh helpers.

Called after batch/on-demand AI writes so downstream dashboards reflect the new
scores (doc 02 §9 step 4). Each matview has a UNIQUE index, so CONCURRENTLY is
attempted first (no read lock); falls back to a plain refresh if needed.
"""
from __future__ import annotations

import time

# Matviews that depend on AI/analytics writes, plus the operational stats view.
INTELLIGENCE_MATVIEWS = ("mv_district_risk_profile", "mv_active_hotspots")

# Rollups that are DERIVED ARTIFACTS under the case-derived-analytics policy: their
# definition embeds the fail-closed eligibility predicate, so they go stale when a
# CaseVersion changes, not only when a case is registered. Each refresh is stamped
# in mv_refresh_state with the policy attestation it ran under, and the serving
# layer refuses a rollup whose attestation is no longer current.
POLICY_DERIVED_MATVIEWS = ("mv_case_daily",)

ALL_MATVIEWS = ("mv_crime_stats",) + INTELLIGENCE_MATVIEWS + POLICY_DERIVED_MATVIEWS


def refresh_matview(conn, name: str) -> str:
    """Refresh one matview. Returns 'concurrent' | 'plain'. Commits per view.

    A policy-derived rollup also gets its attestation recorded, in the same
    transaction as the ledger write, so a refresh can never be recorded without the
    policy it was computed under.
    """
    started = time.monotonic()
    with conn.cursor() as cur:
        try:
            cur.execute(f'REFRESH MATERIALIZED VIEW CONCURRENTLY "{name}"')
            conn.commit()
            mode = "concurrent"
        except Exception:
            conn.rollback()
            cur.execute(f'REFRESH MATERIALIZED VIEW "{name}"')
            conn.commit()
            mode = "plain"

    if name in POLICY_DERIVED_MATVIEWS:
        _stamp_refresh(conn, name, elapsed=time.monotonic() - started)
    return mode


def _stamp_refresh(conn, name: str, *, elapsed: float,
                   actor: str | None = None) -> None:
    """Record the attestation this refresh ran under.

    Read AFTER the refresh, deliberately. The refresh reads CaseVersion rows, so an
    attestation taken before it could describe a policy state the rollup does not
    reflect — and the whole point of the stamp is that the serving layer can trust
    the pairing.

    Never raises into the refresh path: a rollup that refreshed but could not be
    stamped is caught by the serving check (an absent or mismatched attestation is
    refused), which is the safe direction.
    """
    from .cases import analytics_policy

    try:
        att = analytics_policy.current_attestation(conn)
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "{name}"')
            rows = int(cur.fetchone()[0] or 0)
            cur.execute(
                """
                INSERT INTO "mv_refresh_state" ("matview_name", "refreshed_at",
                        "policy_version", "policy_sha256", "source_row_count",
                        "refresh_seconds", "refreshed_by")
                VALUES (%s, now(), %s, %s, %s, %s, %s)
                ON CONFLICT ("matview_name") DO UPDATE
                    SET "refreshed_at" = now(),
                        "policy_version" = EXCLUDED."policy_version",
                        "policy_sha256" = EXCLUDED."policy_sha256",
                        "source_row_count" = EXCLUDED."source_row_count",
                        "refresh_seconds" = EXCLUDED."refresh_seconds",
                        "refreshed_by" = EXCLUDED."refreshed_by"
                """,
                (name, att.version, att.sha256, rows, round(elapsed, 3),
                 actor or "matviews.refresh"),
            )
        conn.commit()
    except Exception:  # noqa: BLE001 — never break a successful refresh
        conn.rollback()


def refresh_all(conn, names=ALL_MATVIEWS) -> dict[str, str]:
    return {name: refresh_matview(conn, name) for name in names}
