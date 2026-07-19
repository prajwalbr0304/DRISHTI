#!/usr/bin/env python3
"""Deterministic synthetic Disaster Response fixture (Prompt 17 §C).

Disaster tables are Data Store-NATIVE (created directly in Catalyst Data Store
and populated by the AppSail disaster service at runtime), so — like the
Investigation Board (datagen/investigation_board.py) — this is NOT part of the
PostgreSQL COPY build. It emits a DETERMINISTIC fixture document (rows keyed by
Data Store table name, PascalCase columns matching
services/ml/app/datastore/disaster_schema.py) that:

  * the backend loads via ``app.disaster.seed`` (``POST /disaster/demo/seed``);
  * the backend tests load to assert scenario coverage + spatial containment.

Every coordinate/polygon is placed inside the REAL Karnataka boundary polygons
(datagen/boundaries.py — vendored GeoJSON, no DB) so all points/polygons pass
spatial containment. Everything is clearly-labelled SYNTHETIC.

Covered scenarios (Prompt 17 §C):
  * coastal cyclone/monsoon flooding — Dakshina Kannada, Udupi, Uttara Kannada;
  * Western Ghats landslide — Kodagu, Chikkamagaluru;
  * drought/heatwave — Kalaburagi, Vijayapura, Bagalkot;
  * reservoir/river-basin flooding — Cauvery (Mandya), Krishna (Bagalkot),
    Tungabhadra (Ballari/Koppal);
  * Bengaluru urban flooding;
  * normal/no-event, stale feed, missing sensor, conflicting readings, false
    alarm, low-confidence forecast, a late corrected observation;
  * available/maintenance/deployed resources + shelters at varying occupancy;
  * a route blocked by a hazard polygon + an alternate safe route, and a
    no-safe-route configuration.

Run:  python datagen/disaster.py   (writes fixtures/golden-001/disaster_response.json)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from . import boundaries as B

GOLDEN_SEED = 42
GENERATOR_VERSION = "disaster-fixture@1.0.0"
WATERMARK = "SYNTHETIC DEMO — DRISHTI Emergency Response — not real hazard data"
BASE_TIME = dt.datetime(2024, 7, 15, 6, 0, tzinfo=dt.timezone.utc)

# Synthetic DistrictID references aligned to the canonical Karnataka boundary set.
DISTRICTS = {
    "Dakshina Kannada": 24, "Udupi": 27, "Uttara Kannada": 28,
    "Kodagu": 18, "Chikkamagaluru": 9,
    "Kalaburagi": 16, "Vijayapura": 30, "Bagalkot": 1,
    "Mandya": 21, "Mysuru": 22, "Raichur": 23, "Koppal": 19, "Ballari": 2,
    "Bengaluru Urban": 5, "Davanagere": 13,
}


def _iso(hours_from_base: float) -> str:
    return (BASE_TIME + dt.timedelta(hours=hours_from_base)).isoformat()


class _Builder:
    def __init__(self, seed: int = GOLDEN_SEED):
        self.rng = np.random.default_rng(seed)
        self.bnd = B.load_boundaries()
        self.tables: dict[str, list[dict]] = {t: [] for t in (
            "HazardType", "FeedSource", "FeedIngestionRun", "HazardEvent",
            "HazardRiskZone", "HydroMetReading", "Resource", "ReliefShelter",
            "ResponsePlan", "ResponseTask", "AlertHistory")}
        self.coverage: dict[str, int] = {}
        self._ids: dict[str, int] = {}

    # -- id + coverage ------------------------------------------------------
    def _next(self, table: str) -> int:
        self._ids[table] = self._ids.get(table, 0) + 1
        return self._ids[table]

    def cover(self, key: str, n: int = 1) -> None:
        self.coverage[key] = self.coverage.get(key, 0) + n

    # -- geometry helpers ---------------------------------------------------
    def region(self, name: str) -> B.Region:
        r = self.bnd.district(name)
        if r is None:
            raise KeyError(f"district {name!r} not in boundaries")
        return r

    def point_in(self, name: str) -> tuple[float, float]:
        r = self.region(name)
        p = B.uniform_points(r.geom, r.bounds, self.rng, 1)[0]
        return round(float(p[0]), 6), round(float(p[1]), 6)

    def square_in(self, name: str, cx: float, cy: float, half: float) -> dict:
        """A closed square ring centred on (cx,cy); shrink until it fits the
        district polygon so the whole polygon passes containment."""
        r = self.region(name)
        h = half
        for _ in range(6):
            ring = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h],
                    [cx - h, cy + h], [cx - h, cy - h]]
            if all(r.contains(x, y) for x, y in ring[:-1]):
                return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)]
                        for x, y in ring]]}
            h *= 0.5
        ring = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h],
                [cx - h, cy + h], [cx - h, cy - h]]
        return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)]
                for x, y in ring]]}

    def band_in(self, name: str, cx: float, cy: float, half_w: float,
                half_h: float) -> dict:
        r = self.region(name)
        hw, hh = half_w, half_h
        for _ in range(6):
            ring = [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh],
                    [cx - hw, cy + hh], [cx - hw, cy - hh]]
            if all(r.contains(x, y) for x, y in ring[:-1]):
                break
            hw *= 0.7
            hh *= 0.7
        ring = [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh],
                [cx - hw, cy + hh], [cx - hw, cy - hh]]
        return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)]
                for x, y in ring]]}

    # -- row emitters -------------------------------------------------------
    def hazard_types(self) -> None:
        specs = [
            ("flood", "Riverine / basin flood", "hydro", 48),
            ("urban_flood", "Urban flooding", "hydro", 12),
            ("landslide", "Landslide / slope failure", "geo", 24),
            ("drought", "Drought / rainfall deficit", "climate", 720),
            ("heatwave", "Heatwave", "climate", 72),
            ("cyclone", "Cyclone / severe storm", "met", 96),
            ("forest_fire", "Forest fire", "fire", 24),
            ("dam_breach", "Dam / reservoir breach", "hydro", 6),
            ("lightning", "Lightning / thunderstorm", "met", 3),
        ]
        for code, name, cat, lead in specs:
            self.tables["HazardType"].append({
                "HazardTypeID": self._next("HazardType"), "Code": code, "Name": name,
                "Category": cat, "DefaultLeadTimeHours": lead, "Active": True,
                "CreatedAt": _iso(0)})

    def feed_sources(self) -> None:
        self.tables["FeedSource"].append({
            "FeedSourceID": self._next("FeedSource"), "Code": "synthetic_replay",
            "Name": "Synthetic deterministic replay", "Provider": "DRISHTI datagen",
            "ConnectorKind": "synthetic_replay", "Licence": "synthetic",
            "Attribution": "Synthetic hackathon data", "FreshnessSlaMinutes": 180,
            "ExternalAccessRequired": False, "CreatedAt": _iso(0)})
        self.tables["FeedSource"].append({
            "FeedSourceID": self._next("FeedSource"), "Code": "imd_rainfall_recorded",
            "Name": "IMD/KSNDMC rainfall (recorded sample)", "Provider": "IMD / KSNDMC",
            "ConnectorKind": "recorded_sample",
            "Licence": "Recorded sample — official terms apply; live access pending",
            "Attribution": "India Meteorological Department / KSNDMC (recorded sample)",
            "FreshnessSlaMinutes": 180, "ExternalAccessRequired": True, "CreatedAt": _iso(0)})
        # Read-only LIVE weather connector — Open-Meteo (no API key, CC BY 4.0).
        self.tables["FeedSource"].append({
            "FeedSourceID": self._next("FeedSource"), "Code": "open_meteo_live",
            "Name": "Open-Meteo live weather (rainfall/temp/wind/humidity)",
            "Provider": "Open-Meteo", "ConnectorKind": "live",
            "Licence": "CC BY 4.0 (open-meteo.com) — free for non-commercial use",
            "Attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
            "FreshnessSlaMinutes": 180, "ExternalAccessRequired": False, "CreatedAt": _iso(0)})

    def _reading(self, station, agency, metric, value, unit, lon, lat, district_id,
                 observed_h, quality="valid", received_h=None, feed="synthetic_replay"):
        rid = self._next("HydroMetReading")
        received_h = observed_h if received_h is None else received_h
        self.tables["HydroMetReading"].append({
            "HydroMetReadingID": rid, "StationCode": station, "SourceAgency": agency,
            "MetricType": metric, "Value": value, "Unit": unit, "Lon": round(lon, 6),
            "Lat": round(lat, 6), "DistrictID": district_id, "ObservedAt": _iso(observed_h),
            "ReceivedAt": _iso(received_h), "QualityFlag": quality,
            "SourceRecordID": f"{feed}:{station}:{metric}:{_iso(observed_h)}:{value}",
            "FeedCode": feed})
        return rid

    def _event(self, code, status, severity, district_name, geojson, desc,
               onset_h=0, peak_h=12, source="synthetic"):
        eid = self._next("HazardEvent")
        did = DISTRICTS[district_name]
        cen = _centroid(geojson)
        self.tables["HazardEvent"].append({
            "HazardEventID": eid, "HazardCode": code, "Status": status,
            "Severity": severity, "DistrictID": did, "GeoJSON": geojson,
            "CanonicalCRS": "EPSG:4326", "CentroidLon": cen[0], "CentroidLat": cen[1],
            "OnsetAt": _iso(onset_h), "PredictedPeakAt": _iso(peak_h), "Source": source,
            "SourceVersion": "synthetic-2024.07", "Description": desc, "Version": 1,
            "CreatedAt": _iso(0), "UpdatedAt": _iso(0)})
        return eid, did, cen

    def _zone(self, code, kind, district_name, geojson, level, score, factors,
              name=None):
        zid = self._next("HazardRiskZone")
        cen = _centroid(geojson)
        self.tables["HazardRiskZone"].append({
            "HazardRiskZoneID": zid, "HazardCode": code, "ZoneKind": kind,
            "Name": name or f"{district_name} {code} zone", "DistrictID": DISTRICTS[district_name],
            "GeoJSON": geojson, "CentroidLon": cen[0], "CentroidLat": cen[1],
            "RiskLevel": level, "Score": score, "Factors": factors,
            "ValidFrom": _iso(-24), "ValidTo": _iso(72), "Source": "synthetic",
            "SourceVersion": "synthetic-2024.07", "IsActive": True, "CreatedAt": _iso(0),
            "UpdatedAt": _iso(0)})
        return zid, cen

    def _resource(self, rtype, name, qty, unit, district_name, lon, lat, capacity,
                  caps, status):
        rid = self._next("Resource")
        self.tables["Resource"].append({
            "ResourceID": rid, "ResourceType": rtype, "Name": name, "Quantity": qty,
            "Unit": unit, "HomeUnitID": 1000 + DISTRICTS[district_name],
            "EmployeeID": (5000 + rid if rtype == "personnel" else None),
            "Lon": round(lon, 6), "Lat": round(lat, 6), "DistrictID": DISTRICTS[district_name],
            "Capacity": capacity, "Capabilities": caps, "Status": status, "Version": 1,
            "LastUpdatedAt": _iso(0), "CreatedAt": _iso(0)})
        return rid

    def _shelter(self, name, district_name, lon, lat, capacity, occupancy, facilities,
                 status="open"):
        sid = self._next("ReliefShelter")
        self.tables["ReliefShelter"].append({
            "ReliefShelterID": sid, "Name": name, "Lon": round(lon, 6), "Lat": round(lat, 6),
            "DistrictID": DISTRICTS[district_name], "Capacity": capacity,
            "CurrentOccupancy": occupancy, "Facilities": facilities, "Status": status,
            "Version": 1, "CreatedAt": _iso(0), "UpdatedAt": _iso(0)})
        return sid

    # -- scenarios ----------------------------------------------------------
    def feed_runs(self) -> None:
        """Two heartbeat runs so the UI freshness banner shows a fresh feed and a
        deliberately-stale one (the recorded-sample connector, external access
        required)."""
        self.tables["FeedIngestionRun"].append({
            "FeedIngestionRunID": self._next("FeedIngestionRun"), "FeedSourceID": 1,
            "FeedCode": "synthetic_replay", "StartedAt": _iso(-0.2), "FinishedAt": _iso(0),
            "Status": "ok", "AcceptedCount": 24, "DuplicateCount": 0, "RejectedCount": 0,
            "LastObservedAt": _iso(0),
            "Detail": {"connector": "synthetic_replay", "external_access_required": False},
            "CreatedAt": _iso(0)})
        self.tables["FeedIngestionRun"].append({
            "FeedIngestionRunID": self._next("FeedIngestionRun"), "FeedSourceID": 2,
            "FeedCode": "imd_rainfall_recorded", "StartedAt": _iso(-6.2),
            "FinishedAt": _iso(-6), "Status": "stale", "AcceptedCount": 2,
            "DuplicateCount": 0, "RejectedCount": 0, "LastObservedAt": _iso(-6),
            "Detail": {"connector": "recorded_sample", "external_access_required": True},
            "CreatedAt": _iso(-6)})

    def build(self) -> dict:
        self.hazard_types()
        self.feed_sources()
        self.feed_runs()
        self._coastal()
        self._ghats()
        self._north()
        self._river_basins()
        self._bengaluru_urban()
        self._normal_and_quality()
        self._plans_and_alerts()
        return {
            "generator_version": GENERATOR_VERSION, "seed": GOLDEN_SEED,
            "base_time": BASE_TIME.isoformat(), "watermark": WATERMARK,
            "districts": {v: k for k, v in DISTRICTS.items()},
            "scenario_coverage": dict(sorted(self.coverage.items())),
            "tables": self.tables,
        }

    # coastal cyclone/monsoon flooding + the blocked/alternate route demo
    def _coastal(self) -> None:
        rx, ry = self.region("Dakshina Kannada").representative()
        # rising monsoon rainfall (valid, recent) ending at BASE -> fresh forecast
        for i, mm in enumerate((22.0, 45.0, 78.0, 110.0, 150.0, 128.0)):
            self._reading("KSNDMC-DK-001", "KSNDMC(synthetic)", "rainfall", mm, "mm",
                          rx, ry, DISTRICTS["Dakshina Kannada"], observed_h=-5 + i)
        for i, lvl in enumerate((5.6, 6.4, 7.1)):
            self._reading("CWC-NETRAVATI-01", "CWC(synthetic)", "river_level", lvl, "m",
                          rx + 0.01, ry - 0.01, DISTRICTS["Dakshina Kannada"], observed_h=-2 + i)
        # blocked-but-alternate route geometry: zone SW, shelter NE, hazard square mid
        zx, zy = rx - 0.06, ry - 0.06
        sx, sy = rx + 0.06, ry + 0.06
        hazard = self.square_in("Dakshina Kannada", rx, ry, 0.02)
        self._event("flood", "warning", "severe", "Dakshina Kannada", hazard,
                    "Coastal monsoon flooding; Netravati rising.", peak_h=10)
        self._zone("flood", "dynamic", "Dakshina Kannada",
                   self.square_in("Dakshina Kannada", zx, zy, 0.01), "high", 0.72,
                   {"susceptibility": 0.7, "rule": "coastal flood plain"})
        self._zone("flood", "static", "Dakshina Kannada",
                   self.square_in("Dakshina Kannada", rx - 0.03, ry + 0.02, 0.015),
                   "medium", 0.5, {"susceptibility": 0.5, "rule": "flood plain (static)"})
        # a reachable shelter (alternate route around the square) + resources
        self._shelter("DK Govt School Shelter", "Dakshina Kannada", sx, sy, 400, 120,
                      ["water", "medical", "power"])
        self._shelter("DK Community Hall", "Dakshina Kannada", rx + 0.02, ry - 0.05, 250, 60,
                      ["water"])
        self._resource("boat", "DK Rescue Boat A", 3, "boats", "Dakshina Kannada",
                       rx - 0.02, ry - 0.02, 12, ["rescue", "flood"], "available")
        self._resource("boat", "DK Rescue Boat B", 2, "boats", "Dakshina Kannada",
                       rx + 0.03, ry + 0.01, 8, ["rescue", "flood"], "available")
        self._resource("personnel", "DK NDRF Team", 24, "personnel", "Dakshina Kannada",
                       rx, ry - 0.01, 24, ["rescue", "medical"], "available")
        self._resource("ambulance", "DK Ambulance 1", 1, "vehicle", "Dakshina Kannada",
                       rx + 0.01, ry + 0.02, 4, ["medical"], "available")
        self._resource("equipment", "DK Pump Set", 5, "pumps", "Dakshina Kannada",
                       rx - 0.01, ry, 0, ["dewatering"], "maintenance")
        self.cover("coastal_cyclone_flood")
        self.cover("blocked_route_hazard")
        self.cover("alternate_safe_route")
        self.cover("resource_available", 4)
        self.cover("resource_maintenance")
        self.cover("shelter_varying_occupancy", 2)

        # Udupi cyclone (wind) + Uttara Kannada rainfall (coastal set)
        ux, uy = self.point_in("Udupi")
        for i, w in enumerate((48.0, 66.0, 84.0)):
            self._reading("IMD-UDUPI-01", "IMD(synthetic)", "wind", w, "kmph", ux, uy,
                          DISTRICTS["Udupi"], observed_h=-3 + i)
        self._event("cyclone", "watch", "moderate", "Udupi",
                    self.square_in("Udupi", ux, uy, 0.02),
                    "Offshore system; gale winds building.", peak_h=24)
        self._shelter("Udupi Coastal Shelter", "Udupi", ux + 0.02, uy + 0.02, 300, 300,
                      ["water", "medical"], status="full")
        self._resource("personnel", "Udupi Coastal Team", 18, "personnel", "Udupi",
                       ux, uy, 18, ["rescue"], "deployed")
        self.cover("shelter_varying_occupancy")
        self.cover("resource_deployed")

        kx, ky = self.point_in("Uttara Kannada")
        # a FALSE ALARM: a watch with rainfall that does NOT cross the threshold
        for i, mm in enumerate((6.0, 9.0, 4.0)):
            self._reading("KSNDMC-UK-002", "KSNDMC(synthetic)", "rainfall", mm, "mm",
                          kx, ky, DISTRICTS["Uttara Kannada"], observed_h=-3 + i)
        self._event("flood", "watch", "minor", "Uttara Kannada",
                    self.square_in("Uttara Kannada", kx, ky, 0.02),
                    "Watch raised on early signal; rainfall not sustained (false alarm).")
        self.cover("false_alarm")

    def _ghats(self) -> None:
        for dname in ("Kodagu", "Chikkamagaluru"):
            cx, cy = self.region(dname).representative()
            # high antecedent rainfall (72h) drives landslide RTM
            for i, mm in enumerate((40.0, 55.0, 70.0, 85.0)):
                self._reading(f"KSNDMC-{dname[:3].upper()}-01", "KSNDMC(synthetic)",
                              "rainfall", mm, "mm", cx, cy, DISTRICTS[dname],
                              observed_h=-8 + i * 2)
            self._zone("landslide", "static", dname,
                       self.square_in(dname, cx, cy, 0.02), "high", 0.8,
                       {"susceptibility": 0.8, "slope_deg": 30,
                        "rule": "GSI susceptibility belt (Ghats)"})
        # an active landslide warning in Kodagu
        cx, cy = self.region("Kodagu").representative()
        self._event("landslide", "warning", "severe", "Kodagu",
                    self.square_in("Kodagu", cx, cy, 0.02),
                    "Saturated Ghats slopes; landslide risk high.", peak_h=8)
        self._shelter("Kodagu Relief Camp", "Kodagu", cx + 0.03, cy + 0.02, 200, 40,
                      ["water", "medical"])
        self._resource("personnel", "Kodagu Rescue Team", 20, "personnel", "Kodagu",
                       cx, cy, 20, ["rescue", "terrain"], "available")
        self._resource("vehicle", "Kodagu 4x4", 4, "vehicle", "Kodagu", cx + 0.01, cy,
                       16, ["terrain"], "available")
        self.cover("ghats_landslide", 2)
        self.cover("resource_available", 2)
        self.cover("shelter_varying_occupancy")

    def _north(self) -> None:
        for dname in ("Kalaburagi", "Vijayapura", "Bagalkot"):
            cx, cy = self.region(dname).representative()
            self._reading(f"IMD-{dname[:3].upper()}-T", "IMD(synthetic)", "temperature",
                          43.5, "C", cx, cy, DISTRICTS[dname], observed_h=-1)
            self._reading(f"KSNDMC-{dname[:3].upper()}-R", "KSNDMC(synthetic)", "rainfall",
                          1.0, "mm", cx, cy, DISTRICTS[dname], observed_h=-1)
        cx, cy = self.region("Kalaburagi").representative()
        self._event("heatwave", "watch", "moderate", "Kalaburagi",
                    self.square_in("Kalaburagi", cx, cy, 0.03),
                    "North-interior heatwave; temperatures above threshold.", peak_h=6)
        self._zone("drought", "dynamic", "Vijayapura",
                   self.square_in("Vijayapura", *self.region("Vijayapura").representative(), 0.03),
                   "medium", 0.55, {"spi_deficit": 0.55, "rule": "rainfall deficit"})
        self._resource("relief_material", "Water Tankers (Kalaburagi)", 10, "tankers",
                       "Kalaburagi", cx, cy, 100, ["water_supply"], "available")
        self.cover("north_drought_heatwave", 3)
        self.cover("resource_available")

    def _river_basins(self) -> None:
        # Cauvery (Mandya), Krishna (Bagalkot), Tungabhadra (Ballari)
        for dname, station, lvl in (("Mandya", "WRD-KRS", 28.5),
                                    ("Bagalkot", "WRD-ALMATTI", 29.2),
                                    ("Ballari", "WRD-TB", 27.8)):
            cx, cy = self.region(dname).representative()
            self._reading(station, "KarnatakaWRD(synthetic)", "reservoir_level", lvl, "m",
                          cx, cy, DISTRICTS[dname], observed_h=-2)
        cx, cy = self.region("Mandya").representative()
        self._event("flood", "watch", "moderate", "Mandya",
                    self.square_in("Mandya", cx, cy, 0.03),
                    "Cauvery reservoir near full; downstream watch.", peak_h=36)
        self._shelter("Mandya Basin Shelter", "Mandya", cx + 0.02, cy + 0.02, 350, 90,
                      ["water"])
        self.cover("river_basin_flood", 3)
        self.cover("shelter_varying_occupancy")

    # Bengaluru urban flooding + the NO-SAFE-ROUTE demo
    def _bengaluru_urban(self) -> None:
        rx, ry = self.region("Bengaluru Urban").representative()
        for i, mm in enumerate((30.0, 62.0, 95.0)):
            self._reading("KSNDMC-BLR-URB", "KSNDMC(synthetic)", "rainfall", mm, "mm",
                          rx, ry, DISTRICTS["Bengaluru Urban"], observed_h=-2 + i)
        # a wide hazard band separates the zone (south) from all shelters (north)
        band = self.band_in("Bengaluru Urban", rx, ry, 0.10, 0.01)
        self._event("urban_flood", "warning", "severe", "Bengaluru Urban", band,
                    "Urban flooding; arterial underpasses inundated.", peak_h=4)
        self._zone("urban_flood", "dynamic", "Bengaluru Urban",
                   self.square_in("Bengaluru Urban", rx, ry - 0.05, 0.01), "high", 0.75,
                   {"susceptibility": 0.7, "rule": "low-lying ward"})
        # shelters all NORTH of the band -> no safe route across it
        self._shelter("BLR Ward Shelter N1", "Bengaluru Urban", rx - 0.02, ry + 0.05, 500, 150,
                      ["water", "medical", "power"])
        self._shelter("BLR Ward Shelter N2", "Bengaluru Urban", rx + 0.03, ry + 0.06, 300, 80,
                      ["water"])
        self._resource("equipment", "BLR Pump Units", 8, "pumps", "Bengaluru Urban",
                       rx, ry + 0.04, 0, ["dewatering"], "available")
        self.cover("bengaluru_urban_flood")
        self.cover("no_safe_route")
        self.cover("shelter_varying_occupancy", 2)
        self.cover("resource_available")

    def _normal_and_quality(self) -> None:
        # normal / no-event district
        mx, my = self.point_in("Mysuru")
        self._reading("KSNDMC-MYS-01", "KSNDMC(synthetic)", "rainfall", 3.0, "mm", mx, my,
                      DISTRICTS["Mysuru"], observed_h=-1)
        self.cover("normal_no_event")

        # stale feed: a district whose ONLY reading is 2 days old -> a forecast
        # there is 'stale' and escalates (never an automatic all-clear)
        bx, by = self.point_in("Davanagere")
        self._reading("STALE-DVG-01", "KSNDMC(synthetic)", "rainfall", 12.0, "mm", bx, by,
                      DISTRICTS["Davanagere"], observed_h=-48)
        self.cover("stale_feed")

        # missing sensor value (recorded, not silently dropped)
        self._reading("MISS-KOP-01", "CWC(synthetic)", "river_level", None, "m",
                      *self.point_in("Koppal"), DISTRICTS["Koppal"], observed_h=-1,
                      quality="missing")
        self.cover("missing_sensor")
        self.cover("low_confidence_forecast")   # Koppal has a single/absent reading

        # conflicting readings: same station/metric/instant, two different values
        rx, ry = self.point_in("Raichur")
        self._reading("CONF-RAI-01", "IMD(synthetic)", "temperature", 41.0, "C", rx, ry,
                      DISTRICTS["Raichur"], observed_h=-1)
        self._reading("CONF-RAI-01", "IMD(synthetic)", "temperature", 44.0, "C", rx, ry,
                      DISTRICTS["Raichur"], observed_h=-1, quality="suspect")
        self.cover("conflicting_readings")

        # late corrected observation: same instant, corrected value received later
        dk_x, dk_y = self.region("Dakshina Kannada").representative()
        self._reading("LATE-DK-01", "KSNDMC(synthetic)", "rainfall", 90.0, "mm", dk_x, dk_y,
                      DISTRICTS["Dakshina Kannada"], observed_h=-4, received_h=-4)
        self._reading("LATE-DK-01", "KSNDMC(synthetic)", "rainfall", 118.0, "mm", dk_x, dk_y,
                      DISTRICTS["Dakshina Kannada"], observed_h=-4, received_h=1,
                      quality="late")
        self.cover("late_corrected_observation")

    def _plans_and_alerts(self) -> None:
        dk_event = next(e for e in self.tables["HazardEvent"]
                        if e["HazardCode"] == "flood" and e["DistrictID"] == DISTRICTS["Dakshina Kannada"])
        pid = self._next("ResponsePlan")
        self.tables["ResponsePlan"].append({
            "ResponsePlanID": pid, "HazardEventID": dk_event["HazardEventID"],
            "HazardCode": "flood", "Title": "DK Flood SOP", "TemplateCode": "flood",
            "Status": "active", "DistrictID": DISTRICTS["Dakshina Kannada"], "Version": 1,
            "CreatedAt": _iso(0), "UpdatedAt": _iso(0)})
        tasks = ["Activate district EOC + confirm feed freshness",
                 "Issue warning after human confirmation",
                 "Pre-position boats to at-risk zones",
                 "Open relief shelters + verify occupancy",
                 "Propose evacuation routes avoiding the hazard polygon",
                 "After-action review + export"]
        for i, t in enumerate(tasks, 1):
            self.tables["ResponseTask"].append({
                "ResponseTaskID": self._next("ResponseTask"), "ResponsePlanID": pid,
                "Title": t, "Sequence": i, "Status": ("in_progress" if i == 1 else "open"),
                "Version": 1, "CreatedAt": _iso(0), "UpdatedAt": _iso(0)})
        # a PROPOSED hazard alert (reviewable; not active until a human confirms)
        self.tables["AlertHistory"].append({
            "AlertID": 900001, "AlertType": "flood_warning", "Severity": "warning",
            "Title": "Proposed flood warning — Dakshina Kannada",
            "Message": "Rainfall + river thresholds breached; awaiting human confirmation.",
            "HazardEventID": dk_event["HazardEventID"], "DistrictID": DISTRICTS["Dakshina Kannada"],
            "Status": "proposed",
            "Payload": {"confidence": 0.78, "freshness": "ok", "synthetic": True,
                        "proposed_by": "system"}, "CreatedAt": _iso(1)})


def _centroid(geojson: dict) -> tuple[float, float]:
    coords = geojson.get("coordinates")
    gtype = geojson.get("type")
    pts = []
    if gtype == "Point":
        pts = [coords]
    elif gtype == "Polygon":
        pts = coords[0]
    if not pts:
        return (None, None)
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return (round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6))


def build_disaster_fixture(seed: int = GOLDEN_SEED) -> dict:
    return _Builder(seed).build()


def main() -> None:
    fx = build_disaster_fixture()
    out_dir = Path(__file__).resolve().parent / "fixtures" / "golden-001"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "disaster_response.json"
    dst.write_text(json.dumps(fx, indent=2, default=str) + "\n", encoding="utf-8")
    counts = {t: len(rows) for t, rows in fx["tables"].items()}
    print(f"wrote {dst}")
    print("row counts:", json.dumps(counts))
    print("scenario coverage:", json.dumps(fx["scenario_coverage"]))


if __name__ == "__main__":
    main()
