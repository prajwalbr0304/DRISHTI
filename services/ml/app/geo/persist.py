"""Persist the versioned jurisdiction geography into the database.

Migration 009 created ``JurisdictionBoundary``/``UnitLocation``; the v2 datagen
loads state/district/unit(SHO) boundaries + station coordinates. This module
provides an IDEMPOTENT loader that ensures the state/district/taluk polygons are
persisted from the vendored KGIS geometry bundled under ``app/geo/boundaries/``
(the same simplified source datagen/geo uses), so the DATABASE — not just the
map's bundled files — is the versioned source of truth the UI reads back.

Idempotent: a boundary is inserted only when no current row of that
level/name/district already exists. State/district/SHO are usually already
present (from the v2 load); taluks are added here. Nothing is deleted.
"""
from __future__ import annotations

import json
from typing import Callable

from psycopg2.extras import Json

from . import boundaries as B

BOUNDARY_SOURCE = "datagen/geo KGIS-simplified"


def _district_id_map(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictName", "DistrictID" FROM "District"')
        return {r[0]: int(r[1]) for r in cur.fetchall()}


def _state_id(conn) -> int | None:
    with conn.cursor() as cur:
        cur.execute('SELECT "StateID" FROM "State" ORDER BY "StateID" LIMIT 1')
        r = cur.fetchone()
    return int(r[0]) if r else None


def _has_current(conn, level: str, name: str, district_id: int | None) -> bool:
    with conn.cursor() as cur:
        if district_id is None:
            cur.execute('SELECT 1 FROM "JurisdictionBoundary" WHERE "Level"=%s AND "Name"=%s '
                        'AND "IsCurrent" LIMIT 1', (level, name))
        else:
            cur.execute('SELECT 1 FROM "JurisdictionBoundary" WHERE "Level"=%s AND "Name"=%s '
                        'AND "DistrictID"=%s AND "IsCurrent" LIMIT 1', (level, name, district_id))
        return cur.fetchone() is not None


def _insert(conn, level: str, name: str, geometry: dict, *,
            state_id: int | None = None, district_id: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "JurisdictionBoundary" ("Level","Name","StateID","DistrictID","geom",'
            '"Version","IsCurrent","Source","IsSynthetic") '
            'VALUES (%s,%s,%s,%s, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326), 1, TRUE, %s, TRUE)',
            (level, name, state_id, district_id, json.dumps(geometry), BOUNDARY_SOURCE))


def ensure_boundaries(conn, log: Callable[[str], None] = print) -> dict:
    """Ensure state/district/taluk boundaries are persisted. Returns counts of
    rows INSERTED (0 when already present) per level. Never deletes/moves."""
    inserted = {"state": 0, "district": 0, "taluk": 0}
    state_id = _state_id(conn)
    dmap = _district_id_map(conn)

    # -- state --
    for f in B.load_boundary("state")["features"]:
        name = f.get("properties", {}).get("state") or "Karnataka"
        if not _has_current(conn, "state", name, None):
            _insert(conn, "state", name, f["geometry"], state_id=state_id)
            inserted["state"] += 1

    # -- districts --
    for f in B.load_boundary("districts")["features"]:
        name = f["properties"]["district"]
        did = dmap.get(name)
        if _has_current(conn, "district", name, did):
            continue
        _insert(conn, "district", name, f["geometry"], state_id=state_id, district_id=did)
        inserted["district"] += 1

    # -- taluks (administrative; keyed to their district) --
    for f in B.load_boundary("taluks")["features"]:
        props = f["properties"]
        name = props["taluk"]
        did = dmap.get(props.get("district"))
        if _has_current(conn, "taluk", name, did):
            continue
        _insert(conn, "taluk", name, f["geometry"], state_id=state_id, district_id=did)
        inserted["taluk"] += 1

    log(f"  boundaries ensured (inserted: {inserted})")
    return inserted


def summary(conn) -> dict:
    """Counts of current persisted boundaries by level + UnitLocation total."""
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute('SELECT "Level", count(*) FILTER (WHERE "IsCurrent") '
                    'FROM "JurisdictionBoundary" GROUP BY "Level"')
        out["boundaries"] = {r[0]: int(r[1]) for r in cur.fetchall()}
        cur.execute('SELECT count(*) FILTER (WHERE "IsCurrent") FROM "UnitLocation"')
        out["unit_locations"] = int(cur.fetchone()[0])
    return out
