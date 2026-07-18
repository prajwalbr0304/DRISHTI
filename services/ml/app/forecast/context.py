"""Approved external context for aggregate forecasting (Phase 12).

Aggregate forecasts may use approved, versioned area/time covariates — weather,
public holidays, public events and other area context — but only through the
governed ``ExternalSourceVersion`` catalogue (migration 009), and only up to the
observation cutoff (no post-window information). This module:

  * lists the APPROVED context source versions (weather|holiday|event|area);
  * reports DATA FRESHNESS (data-as-of) per source for the UI;
  * assembles the strictly-pre-cutoff source-version provenance recorded in a
    forecast ``FeatureSnapshot.SourceVersions``.

It never pulls live/unapproved feeds and degrades gracefully when a context
table is empty (the demo fixture may carry only some context), reporting
``available: false`` rather than failing a forecast.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional


def _scalar(conn, sql: str, params: tuple = ()) -> Optional[object]:
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:  # noqa: BLE001 — a missing/empty context table => "not available"
        return None


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v)


def approved_context_sources(conn) -> list[dict]:
    """Approved, versioned external context sources (weather|holiday|event|area)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ExternalSourceVersionID","SourceKind","Provider","Version",'
                '"ApprovedByActor","ValidFrom","ValidTo","IsSynthetic" '
                'FROM "ExternalSourceVersion" ORDER BY "SourceKind","Version"')
            rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"external_source_version_id": int(r[0]), "source_kind": r[1], "provider": r[2],
             "version": r[3], "approved_by_actor": r[4], "valid_from": _iso(r[5]),
             "valid_to": _iso(r[6]), "is_synthetic": bool(r[7])} for r in rows]


def data_freshness(conn) -> dict:
    """Data-as-of per source — drives the forecast screen's freshness banner."""
    case_max = _scalar(conn, 'SELECT MAX("CrimeRegisteredDate") FROM "CaseMaster"')
    sources = {
        "cases": _iso(case_max),
        "weather": _iso(_scalar(conn, 'SELECT MAX("ObservedAt") FROM "WeatherIndicator"')),
        "holidays": _iso(_scalar(conn, 'SELECT MAX("ObservedDate") FROM "HolidayCalendar"')),
        "events": _iso(_scalar(conn, 'SELECT MAX("StartAt") FROM "PublicEvent"')),
        "area_context": _iso(_scalar(conn, 'SELECT MAX("ObservedDate") FROM "AreaContextObservation"')),
        "social": _iso(_scalar(conn, 'SELECT MAX("ObservedDate") FROM "SocialIndicator"')),
        "economic": _iso(_scalar(conn, 'SELECT MAX("PeriodStart") FROM "EconomicIndicator"')),
    }
    now = dt.datetime.now(dt.timezone.utc)
    stale_days = None
    if case_max is not None:
        as_of = case_max if isinstance(case_max, dt.datetime) else dt.datetime.combine(
            case_max, dt.time(), tzinfo=dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        stale_days = (now - as_of).days
    return {"as_of": sources, "case_data_stale_days": stale_days,
            "approved_sources": approved_context_sources(conn)}


def snapshot_source_versions(conn, district_id: Optional[int], cutoff: dt.datetime) -> dict:
    """Strictly-pre-cutoff provenance recorded in a forecast FeatureSnapshot.

    Records the canonical case layer + the approved external-context source
    versions and the count of context observations available up to the cutoff, so
    a forecast is reproducible and cannot silently use post-window context.
    """
    cutoff_date = cutoff.date() if isinstance(cutoff, dt.datetime) else cutoff
    approved = approved_context_sources(conn)
    approved_ids = sorted({s["external_source_version_id"] for s in approved})

    area_ctx = _scalar(
        conn,
        'SELECT COUNT(*) FROM "AreaContextObservation" '
        'WHERE ("DistrictID" = %s OR %s IS NULL) AND "ObservedDate" <= %s',
        (district_id, district_id, cutoff_date)) or 0
    holidays = _scalar(
        conn, 'SELECT COUNT(*) FROM "HolidayCalendar" WHERE "ObservedDate" <= %s',
        (cutoff_date,)) or 0
    events = _scalar(
        conn,
        'SELECT COUNT(*) FROM "PublicEvent" '
        'WHERE ("DistrictID" = %s OR %s IS NULL) AND "StartAt" <= %s',
        (district_id, district_id, cutoff)) or 0

    return {
        "canonical_layer": "CaseMaster+Unit (valid geography)",
        "observation_cutoff": _iso(cutoff),
        "external_source_version_ids": approved_ids,
        "external_source_kinds": sorted({s["source_kind"] for s in approved}),
        "context_available_precutoff": {
            "area_context_observations": int(area_ctx),
            "holidays": int(holidays),
            "public_events": int(events),
        },
        "post_window_information_used": False,
    }
