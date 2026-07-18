"""Versioned jurisdiction geography + approved external context (run once).

Persists the state / district / taluk / SHO polygons and station coordinates the
audit found missing from the database, plus approved weather/holiday/event/area
source versions and observations used as aggregate model covariates.
"""
from __future__ import annotations

import datetime as dt
from typing import List

from . import boundaries as B
from .db import Geom, Json
from . import v2common as C

C.register("JurisdictionBoundary", [
    "Level", "Name", "StateID", "DistrictID", "UnitID", "geom", "Version",
    "IsCurrent", "ValidFrom", "ValidTo", "Source", "IsSynthetic",
])
C.register("UnitLocation", [
    "UnitID", "geom", "Taluk", "Version", "IsCurrent", "ValidFrom", "ValidTo", "Source",
])
C.register("ExternalSourceVersion", [
    "ExternalSourceVersionID", "SourceKind", "Provider", "Version",
    "ApprovedByActor", "ValidFrom", "ValidTo", "Detail", "IsSynthetic",
])
C.register("HolidayCalendar", ["ObservedDate", "Name", "Region", "ExternalSourceVersionID"])
C.register("PublicEvent",
           ["EventName", "StartAt", "EndAt", "DistrictID", "geom", "ExternalSourceVersionID"])
C.register("AreaContextObservation",
           ["DistrictID", "UnitID", "ObservedDate", "Metrics", "ExternalSourceVersionID", "geom"])

_SRC = "datagen/geo KGIS-simplified (synthetic use)"
_VF = "2021-01-01 00:00:00+00"

_HOLIDAYS = [
    ("01-26", "Republic Day"), ("08-15", "Independence Day"),
    ("10-02", "Gandhi Jayanti"), ("11-01", "Kannada Rajyotsava"),
    ("10-24", "Dussehra (approx)"), ("11-12", "Deepavali (approx)"),
]


def build_context_layer(world: C.World) -> None:
    w = world
    cfg = w.cfg
    ctx = w.ctx
    bnd = B.load_boundaries()

    # --- state boundary ----------------------------------------------------
    try:
        w.add("JurisdictionBoundary", (
            "state", "Karnataka", ctx.state_id, None, None,
            Geom("SRID=4326;" + bnd.state.geom.wkt), 1, True, _VF, None, _SRC, True,
        ))
    except Exception:
        pass

    # --- district boundaries ----------------------------------------------
    for d in ctx.districts:
        region = bnd.district(d["name"])
        if region is None:
            continue
        w.add("JurisdictionBoundary", (
            "district", d["name"], ctx.state_id, d["id"], None,
            Geom("SRID=4326;" + region.geom.wkt), 1, True, _VF, None, _SRC, True,
        ))

    # --- taluk boundaries (administrative sub-district; Phase 9) -----------
    # Persist the taluk polygons too so the DATABASE is the versioned source of
    # truth for every jurisdiction level the UI reads back (state/district/taluk
    # /SHO), not just the map's bundled files. Keyed to the parent district.
    for d in ctx.districts:
        region = bnd.district(d["name"])
        for t in (bnd.taluks(d["name"]) if region is not None else []):
            # skip the district-as-taluk fallback (BBMP-style districts with no
            # sub-taluks) — that polygon is already persisted at district level.
            if region is not None and t.name == d["name"]:
                continue
            try:
                w.add("JurisdictionBoundary", (
                    "taluk", t.name, ctx.state_id, d["id"], None,
                    Geom("SRID=4326;" + t.geom.wkt), 1, True, _VF, None, _SRC, True,
                ))
            except Exception:
                pass

    # --- SHO polygons + unit locations (per station) -----------------------
    for st in ctx.stations:
        ring = st.get("sho_ring")
        if ring and len(ring) >= 4:
            try:
                w.add("JurisdictionBoundary", (
                    "sho", f"SHO {st['id']}", ctx.state_id,
                    ctx.districts[st["district_idx"]]["id"], st["id"],
                    Geom.polygon([(x, y) for x, y in ring]), 1, True, _VF, None,
                    _SRC, True,
                ))
            except Exception:
                pass
        w.add("UnitLocation", (
            st["id"], Geom.point(st["lon"], st["lat"]), st.get("taluk"), 1, True,
            _VF, None, _SRC,
        ))

    # --- approved external source versions --------------------------------
    src_ids = {}
    for kind, provider in [("holiday", "GoK Calendar"), ("weather", "IMD-synthetic"),
                           ("event", "District Admin"), ("area", "Census-synthetic")]:
        sid = w.next_id("ExternalSourceVersion")
        src_ids[kind] = sid
        w.add("ExternalSourceVersion", (
            sid, kind, provider, "v1", "admin_demo", _VF, None,
            Json({"approved": True, "synthetic": True}), True,
        ))

    # --- holidays across the case window ----------------------------------
    for year in range(cfg.start_date.year, cfg.end_date.year + 1):
        for mmdd, name in _HOLIDAYS:
            w.add("HolidayCalendar",
                  (f"{year}-{mmdd}", name, "Karnataka", src_ids["holiday"]))

    # --- a few public events ----------------------------------------------
    for d in ctx.districts[:6]:
        w.add("PublicEvent", (
            f"Festival gathering - {d['name']}",
            f"{cfg.end_date.year}-10-24 06:00:00+00",
            f"{cfg.end_date.year}-10-24 23:00:00+00",
            d["id"], Geom.point(d["lon"], d["lat"]), src_ids["event"],
        ))

    # --- area context: one approved row per district per year --------------
    for d in ctx.districts:
        for year in range(cfg.start_date.year, cfg.end_date.year + 1):
            w.add("AreaContextObservation", (
                d["id"], None, f"{year}-06-30",
                Json({"pop_weight": d["pop_weight"], "tags": d["tags"],
                      "synthetic": True}),
                src_ids["area"], None,
            ))
