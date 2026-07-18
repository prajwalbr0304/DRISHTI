"""Build vendored Karnataka boundary GeoJSON (state / districts / taluks).

Offline, one-shot preprocessing step. Reads the full-resolution KGIS maps
downloaded into ``datagen/geo/raw/`` (see SOURCES.md), then:

  * normalises district / taluk names to the police-district vocabulary used by
    ``reference.KARNATAKA_DISTRICTS``,
  * repairs invalid rings (``buffer(0)``),
  * simplifies each polygon to a controlled tolerance so point-in-polygon and
    uniform rejection sampling stay cheap while the coastline / state border
    remain faithful (the whole reason coordinates were leaking into the sea),
  * dissolves the districts into a single clean state outline,
  * rounds coordinates to 5 dp (~1.1 m) to keep the vendored files small.

Outputs (committed to the repo, consumed by ``datagen/boundaries.py``):
  datagen/geo/karnataka_state.geojson      1 feature  (MultiPolygon)
  datagen/geo/karnataka_districts.geojson  31 features
  datagen/geo/karnataka_taluks.geojson     ~230 features

Run:  python -m datagen.geo.build_boundaries      (from repo root)
This does NOT touch the database and is independent of data generation.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

# Simplification tolerance in degrees (~111 km per degree of latitude).
TALUK_TOL = 0.0012      # ~135 m — plenty for placement, ~10-30x smaller files
DISTRICT_TOL = 0.0010   # ~110 m
COORD_DP = 5            # ~1.1 m coordinate rounding

# KGIS uses a handful of spellings that differ from the generator's police
# districts. Map KGIS "name" -> the generator's canonical district name so the
# vendored files speak the same vocabulary as reference.KARNATAKA_DISTRICTS.
KGIS_TO_GEN: Dict[str, str] = {
    "BAGALKOTE": "Bagalkot",
    "BALLARI": "Ballari",
    "BELAGAVI": "Belagavi",
    "BENGALURU RURAL": "Bengaluru Rural",
    "BENGALURU URBAN": "Bengaluru Urban",
    "BIDAR": "Bidar",
    "CHAMARAJANAGARA": "Chamarajanagar",
    "CHIKKABALLAPURA": "Chikkaballapur",
    "CHIKKAMAGALURU": "Chikkamagaluru",
    "CHITRADURGA": "Chitradurga",
    "DAKSHINA KANNADA": "Dakshina Kannada",
    "DAVANGERE": "Davanagere",
    "DHARWAD": "Dharwad",
    "GADAG": "Gadag",
    "HASSAN": "Hassan",
    "HAVERI": "Haveri",
    "KALABURAGI": "Kalaburagi",
    "KODAGU": "Kodagu",
    "KOLAR": "Kolar",
    "KOPPAL": "Koppal",
    "MANDYA": "Mandya",
    "MYSURU": "Mysuru",
    "RAICHUR": "Raichur",
    "RAMANAGARA": "Ramanagara",
    "SHIVAMOGGA": "Shivamogga",
    "TUMAKURU": "Tumakuru",
    "UDUPI": "Udupi",
    "UTTARA KANNADA": "Uttara Kannada",
    "VIJAYANAGAR": "Vijayanagara",
    "VIJAYAPURA": "Vijayapura",
    "YADGIR": "Yadgir",
    # BBMP (Bengaluru city corporation) is carried as its own district-level
    # unit so the generator can distinguish the dense city from the wider
    # Bengaluru Urban district.
    "BBMP": "Bengaluru City",
}


def _round(geom):
    return transform(lambda x, y, z=None: (round(x, COORD_DP), round(y, COORD_DP)), geom)


def _clean(geom, tol):
    if not geom.is_valid:
        geom = geom.buffer(0)
    geom = geom.simplify(tol, preserve_topology=True)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return _round(geom)


def _titlecase_taluk(name: str) -> str:
    return " ".join(w.capitalize() for w in name.strip().split())


def _strip_holes(geom):
    """Drop interior rings. Karnataka has no enclaves, so any hole is a sliver
    left by independent per-district simplification. Removing holes only adds
    area, so the result stays a superset of every district polygon."""
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    return MultiPolygon([Polygon(g.exterior) for g in geom.geoms])


def build():
    dist_path = os.path.join(RAW, "state_29_districts.geojson")
    if not os.path.exists(dist_path):
        raise SystemExit("raw districts file missing — see datagen/geo/SOURCES.md to fetch")

    raw_dist = json.load(open(dist_path, encoding="utf-8"))
    district_features = []
    simplified_geoms = []  # the simplified district polygons (state = their union)
    unmapped = []
    for f in raw_dist["features"]:
        kgis = f["properties"]["name"].strip().upper()
        gen = KGIS_TO_GEN.get(kgis)
        if gen is None:
            unmapped.append(kgis)
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        cg = _clean(g, DISTRICT_TOL)
        simplified_geoms.append(cg)
        district_features.append({
            "type": "Feature",
            "geometry": mapping(cg),
            "properties": {
                "district": gen,
                "kgis_name": f["properties"]["name"].strip(),
                "region_id": f["properties"]["region_id"],
                "level": "district",
            },
        })
    if unmapped:
        print("WARNING unmapped district names:", unmapped)

    # State outline = union of the SIMPLIFIED districts, with interior slivers
    # removed. Because it is built from the very same simplified polygons that
    # get vendored, every district polygon is a subset of the state outline by
    # construction — no more "inside the district but a few metres past the
    # simplified coast" mismatches.
    print("dissolving state outline from", len(simplified_geoms), "districts ...")
    state = unary_union(simplified_geoms)
    if not state.is_valid:
        state = state.buffer(0)
    state = _round(_strip_holes(state))
    state_fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": mapping(state),
            "properties": {"name": "Karnataka", "level": "state", "state_code": 29},
        }],
    }

    # Taluks from the per-district subregion files.
    taluk_features = []
    per_district = {}
    for fp in sorted(glob.glob(os.path.join(RAW, "taluks_district_*.geojson"))):
        raw = json.load(open(fp, encoding="utf-8"))
        for f in raw["features"]:
            parent_kgis = (f["properties"].get("parent_name") or "").strip().upper()
            gen = KGIS_TO_GEN.get(parent_kgis)
            if gen is None:
                continue
            g = _clean(shape(f["geometry"]), TALUK_TOL)
            taluk_features.append({
                "type": "Feature",
                "geometry": mapping(g),
                "properties": {
                    "taluk": _titlecase_taluk(f["properties"]["name"]),
                    "district": gen,
                    "region_id": f["properties"]["region_id"],
                    "level": "taluk",
                },
            })
            per_district[gen] = per_district.get(gen, 0) + 1

    districts_fc = {"type": "FeatureCollection", "features": district_features}
    taluks_fc = {"type": "FeatureCollection", "features": taluk_features}

    out = {
        "karnataka_state.geojson": state_fc,
        "karnataka_districts.geojson": districts_fc,
        "karnataka_taluks.geojson": taluks_fc,
    }
    for fname, obj in out.items():
        p = os.path.join(HERE, fname)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, separators=(",", ":"))
        print(f"wrote {fname:32s} {len(obj['features']):4d} feature(s)  "
              f"{os.path.getsize(p)/1024:8.1f} KB")

    print("\ntaluks per district:")
    for d in sorted(per_district):
        print(f"  {d:20s} {per_district[d]}")
    print(f"\nTOTAL districts={len(district_features)} taluks={len(taluk_features)}")
    print("state bounds (minx,miny,maxx,maxy):", tuple(round(v, 3) for v in state.bounds))


if __name__ == "__main__":
    build()
