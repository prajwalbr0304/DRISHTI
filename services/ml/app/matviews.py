"""Materialized-view refresh helpers.

Called after batch/on-demand AI writes so downstream dashboards reflect the new
scores (doc 02 §9 step 4). Each matview has a UNIQUE index, so CONCURRENTLY is
attempted first (no read lock); falls back to a plain refresh if needed.
"""
from __future__ import annotations

# Matviews that depend on AI/analytics writes, plus the operational stats view.
INTELLIGENCE_MATVIEWS = ("mv_district_risk_profile", "mv_active_hotspots")
ALL_MATVIEWS = ("mv_crime_stats",) + INTELLIGENCE_MATVIEWS


def refresh_matview(conn, name: str) -> str:
    """Refresh one matview. Returns 'concurrent' | 'plain'. Commits per view."""
    with conn.cursor() as cur:
        try:
            cur.execute(f'REFRESH MATERIALIZED VIEW CONCURRENTLY "{name}"')
            conn.commit()
            return "concurrent"
        except Exception:
            conn.rollback()
            cur.execute(f'REFRESH MATERIALIZED VIEW "{name}"')
            conn.commit()
            return "plain"


def refresh_all(conn, names=ALL_MATVIEWS) -> dict[str, str]:
    return {name: refresh_matview(conn, name) for name in names}
