"""Phase 17 — Emergency Response (Disaster) behaviour.

Runs WITHOUT a database: disaster records are Data Store-native (in-memory fake).
Unit tests exercise geometry/feeds/models/allocation/routing directly; API tests
drive the FastAPI router via TestClient. The synthetic write guard is forced true
so writes do not depend on live DB reachability.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.disaster import guards
from app.disaster import repo as drepo
from app.disaster import seed as dseed
from app.disaster import feeds, models, routing, allocation, geometry, service
from app.datastore import disaster_schema, mapping

# datagen lives at the repo root; make it importable for the coverage/containment test.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

client = TestClient(app)

COORD = {"X-Role": "disaster_coordinator", "X-Demo-Actor": "demo.coord", "X-Disaster-District": "24"}
COORD5 = {"X-Role": "disaster_coordinator", "X-Demo-Actor": "demo.coord", "X-Disaster-District": "5"}
SUPER = {"X-Role": "super_admin", "X-Demo-Actor": "demo.sa"}
CRIME = {"X-Role": "investigator", "X-Demo-Actor": "demo.io"}
POLICY = {"X-Role": "policymaker", "X-Demo-Actor": "demo.pol"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    drepo.reset_disaster_repo()
    monkeypatch.setattr(guards, "synthetic_db_ok", lambda: True)
    yield
    drepo.reset_disaster_repo()


def _seed():
    r = client.post("/disaster/demo/seed", headers=COORD)
    assert r.status_code == 200, r.text
    return r.json()["seeded"]


def _dk_event():
    evs = client.get("/disaster/events", headers=COORD, params={"district_id": 24}).json()["events"]
    return next(e for e in evs if e["hazard_code"] == "flood")


# ===========================================================================
# schema / Data Store-native / RLS-disabled posture
# ===========================================================================
def test_disaster_tables_datastore_native():
    native = {m.datastore_table for m in mapping.datastore_native_tables(mapping.Domain.DISASTER_RESPONSE)}
    for t in ("HazardType", "HazardEvent", "HazardPrediction", "HazardRiskZone",
              "HydroMetReading", "Resource", "ReliefShelter", "ResourceAllocation",
              "EvacuationRoute", "ResponsePlan", "ResponseTask"):
        assert t in native
    for m in mapping.datastore_native_tables(mapping.Domain.DISASTER_RESPONSE):
        assert m.disposition == mapping.Disposition.DATASTORE_NATIVE
        assert not m.imported


def test_disaster_schema_append_only_and_rls_note():
    assert set(disaster_schema.append_only_tables()) == {
        "HazardPrediction", "HydroMetReading", "DisasterActivity"}
    d = disaster_schema.as_provisioning_dict()
    assert "rls" in d["note"].lower()
    known = {"int", "text", "bigtext", "bool", "numeric", "json", "timestamp"}
    for t in d["tables"]:
        for c in t["columns"]:
            assert c["type"] in known


def test_mapping_validation_clean():
    assert mapping.validate_mapping() == []


def test_migration_023_rls_disabled_no_policies():
    sql = (_REPO_ROOT / "services" / "ml" / "sql" / "023_disaster_response.sql").read_text(encoding="utf-8")
    assert "fn_disable_rls_all_app()" in sql and "fn_assert_rls_disabled()" in sql
    assert "CREATE POLICY" not in sql.upper()
    assert "HazardEventID" in sql          # additive AlertHistory reuse
    assert "flood_warning" in sql          # hazard alert_type_enum value


# ===========================================================================
# datagen: scenario coverage + spatial containment
# ===========================================================================
def test_datagen_scenario_coverage_and_containment():
    import datagen.disaster as dgen
    import datagen.boundaries as B

    fx = dgen.build_disaster_fixture()
    cov = fx["scenario_coverage"]
    required = {"coastal_cyclone_flood", "ghats_landslide", "north_drought_heatwave",
                "river_basin_flood", "bengaluru_urban_flood", "normal_no_event",
                "stale_feed", "missing_sensor", "conflicting_readings", "false_alarm",
                "low_confidence_forecast", "late_corrected_observation",
                "resource_available", "resource_maintenance", "resource_deployed",
                "shelter_varying_occupancy", "blocked_route_hazard",
                "alternate_safe_route", "no_safe_route"}
    assert required.issubset(set(cov)), required - set(cov)

    bnd = B.load_boundaries()
    id2name = fx["districts"]

    def contained(district_id, lon, lat):
        name = id2name.get(str(district_id)) or id2name.get(district_id)
        region = bnd.district(name)
        return region is not None and region.contains(lon, lat)

    # every resource + shelter POINT is inside its district polygon
    for r in fx["tables"]["Resource"]:
        assert contained(r["DistrictID"], r["Lon"], r["Lat"]), f"resource {r['ResourceID']}"
    for s in fx["tables"]["ReliefShelter"]:
        assert contained(s["DistrictID"], s["Lon"], s["Lat"]), f"shelter {s['ReliefShelterID']}"
    # every hazard event + risk zone CENTROID is inside its district polygon
    for e in fx["tables"]["HazardEvent"]:
        assert contained(e["DistrictID"], e["CentroidLon"], e["CentroidLat"]), f"event {e['HazardEventID']}"
    for z in fx["tables"]["HazardRiskZone"]:
        assert contained(z["DistrictID"], z["CentroidLon"], z["CentroidLat"]), f"zone {z['HazardRiskZoneID']}"


def test_datagen_deterministic():
    import datagen.disaster as dgen
    a = dgen.build_disaster_fixture()
    b = dgen.build_disaster_fixture()
    assert a["tables"]["HydroMetReading"] == b["tables"]["HydroMetReading"]
    assert a["scenario_coverage"] == b["scenario_coverage"]


# ===========================================================================
# geometry
# ===========================================================================
def test_geometry_validate_and_containment():
    poly = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
    assert geometry.validate_geojson(poly)[0]
    assert geometry.point_in_geometry(1, 1, poly)
    assert not geometry.point_in_geometry(3, 3, poly)
    # open ring / out-of-range rejected
    assert not geometry.validate_geojson({"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2]]]})[0]
    assert not geometry.validate_geojson({"type": "Point", "coordinates": [200, 0]})[0]


def test_geometry_segment_intersection():
    poly = {"type": "Polygon", "coordinates": [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}
    assert geometry.segment_intersects_geometry([0, 2], [4, 2], poly)      # crosses
    assert not geometry.segment_intersects_geometry([0, 0], [0.5, 0.5], poly)  # away
    assert geometry.haversine_km(74.8, 12.8, 74.9, 12.9) > 0


# ===========================================================================
# feeds: unit conversion, idempotency, dedup, late/conflict/missing, retry/DLQ
# ===========================================================================
def test_unit_conversion():
    assert abs(feeds.normalize_unit("river_level", 10, "ft")[0] - 3.048) < 1e-3
    assert feeds.normalize_unit("rainfall", 5, "cm")[0] == 50.0
    assert abs(feeds.normalize_unit("temperature", 100, "F")[0] - 37.7778) < 1e-2
    assert feeds.normalize_unit("wind", 10, "mps")[0] == 36.0


def _cand(station, metric, value, unit, obs_h, **kw):
    now = datetime.now(timezone.utc)
    return feeds.ReadingCandidate(
        station_code=station, metric_type=metric, value=value, unit=unit,
        observed_at=(now + timedelta(hours=obs_h)).isoformat(), lon=74.8, lat=12.9,
        district_id=24, source_agency="test", **kw)


def test_ingest_idempotent_and_dedup():
    repo = drepo.disaster_repo()
    batch = [_cand("S1", "rainfall", 20.0, "mm", -1), _cand("S1", "rainfall", 40.0, "mm", 0)]
    r1 = feeds.ingest("synthetic_replay", candidates=batch, repo=repo)
    assert r1["AcceptedCount"] == 2 and r1["DuplicateCount"] == 0
    r2 = feeds.ingest("synthetic_replay", candidates=batch, repo=repo)      # replay
    assert r2["AcceptedCount"] == 0 and r2["DuplicateCount"] == 2


def _fixed_cand(station, metric, value, unit, observed_at):
    return feeds.ReadingCandidate(station_code=station, metric_type=metric, value=value,
                                  unit=unit, observed_at=observed_at, lon=74.8, lat=12.9,
                                  district_id=24, source_agency="test")


def test_ingest_missing_conflict_and_correction():
    repo = drepo.disaster_repo()
    now = datetime.now(timezone.utc)
    # missing sensor value -> recorded with quality 'missing' (not rejected)
    r = feeds.ingest("synthetic_replay",
                     candidates=[_fixed_cand("M1", "river_level", None, "m",
                                             (now - timedelta(hours=1)).isoformat())], repo=repo)
    assert r["AcceptedCount"] == 1
    rows = repo.list("HydroMetReading", where={"StationCode": "M1"})
    assert rows[0]["QualityFlag"] == "missing"
    # conflicting readings in one batch (SAME instant, different value) -> suspect
    obs_c = (now - timedelta(hours=2)).isoformat()
    conflict = [_fixed_cand("C1", "temperature", 41.0, "C", obs_c),
                _fixed_cand("C1", "temperature", 44.0, "C", obs_c)]
    feeds.ingest("synthetic_replay", candidates=conflict, repo=repo)
    flags = {row["Value"]: row["QualityFlag"] for row in repo.list("HydroMetReading", where={"StationCode": "C1"})}
    assert 44.0 in flags and flags[44.0] == "suspect"
    # late correction: SAME instant, corrected value -> new 'late' row supersedes by derivation
    obs_l = (now - timedelta(hours=3)).isoformat()
    feeds.ingest("synthetic_replay", candidates=[_fixed_cand("L1", "rainfall", 90.0, "mm", obs_l)], repo=repo)
    feeds.ingest("synthetic_replay", candidates=[_fixed_cand("L1", "rainfall", 118.0, "mm", obs_l)], repo=repo)
    l_rows = repo.list("HydroMetReading", where={"StationCode": "L1"})
    assert len(l_rows) == 2                                    # both rows kept (append-only)
    eff = feeds.valid_readings(l_rows)
    assert len(eff) == 1 and eff[0]["Value"] == 118.0         # latest received wins


def test_ingest_retry_dlq_on_connector_failure():
    class _Boom(feeds.Connector):
        meta = feeds.ConnectorMeta(code="boom", name="boom", provider="t",
                                   connector_kind="synthetic_replay")
        def emit(self, *, now=None):
            raise RuntimeError("connector down")
    run = feeds.ingest("boom", connector=_Boom(), repo=drepo.disaster_repo())
    assert run["Status"] == "failed" and run["Detail"].get("dlq") is True


def test_ingest_rejects_invalid_metric():
    repo = drepo.disaster_repo()
    bad = feeds.ReadingCandidate("X", "not_a_metric", 1.0, "mm",
                                 datetime.now(timezone.utc).isoformat())
    run = feeds.ingest("synthetic_replay", candidates=[bad], repo=repo)
    assert run["RejectedCount"] == 1 and run["AcceptedCount"] == 0


# ===========================================================================
# models: all hazards have baselines; MVP beats baselines; calibration present
# ===========================================================================
def test_all_hazard_baselines_exist():
    assert set(models.supported_hazards()) == set(disaster_schema.HAZARD_CODES)
    for code in disaster_schema.HAZARD_CODES:
        out = models.run_model(code, {"rainfall_24h_mm": 80, "rainfall_72h_mm": 160,
                                      "river_level_m": 7, "temperature_max_c": 43,
                                      "reservoir_level_m": 29, "wind_max_kmph": 80,
                                      "humidity_pct": 80, "month": 7})
        assert 0.0 <= out["probability"] <= 1.0 and "rule" in out


def test_mvp_flood_beats_baselines_with_metrics():
    v = models.validate("flood", n_origins=120)
    assert v["skill_vs_baseline"]["beats_baselines"] is True
    m = v["metrics"]
    for k in ("precision", "recall", "false_alarm_rate", "missed_event_rate", "brier"):
        assert k in m
    assert "persistence" in v["baselines"] and "seasonal" in v["baselines"]


# ===========================================================================
# forecast pipeline: fresh vs stale / low-confidence never auto all-clears
# ===========================================================================
def test_fresh_forecast_ok_and_reproducible_snapshot():
    _seed()
    r = client.post("/disaster/forecast/run", headers=COORD,
                    json={"hazard_code": "flood", "district_id": 24, "horizon_hours": 48}).json()
    assert r["prediction"]["quality_state"] == "ok"
    assert r["prediction"]["feature_snapshot_id"]                  # immutable snapshot id
    assert r["prediction"]["model_version_label"].startswith("flood-")
    assert r["baseline_comparison"]["skill_vs_baseline"]["beats_baselines"] is True
    assert not r["escalation"]


def test_stale_feed_forecast_escalates_no_allclear():
    _seed()
    r = client.post("/disaster/forecast/run", headers={**COORD, "X-Disaster-District": "13"},
                    json={"hazard_code": "flood", "district_id": 13}).json()
    assert r["prediction"]["quality_state"] == "stale"
    assert r["escalation"] and "all-clear" in r["escalation"].lower()


def test_low_confidence_forecast_escalates():
    _seed()
    r = client.post("/disaster/forecast/run", headers={**COORD, "X-Disaster-District": "19"},
                    json={"hazard_code": "flood", "district_id": 19}).json()
    assert r["prediction"]["quality_state"] == "low_confidence"
    assert r["escalation"]


# ===========================================================================
# alerts: proposal requires a human confirmation (reuse AlertHistory)
# ===========================================================================
def test_alert_proposal_requires_human_confirmation():
    _seed()
    eid = _dk_event()["hazard_event_id"]
    prop = client.post("/disaster/alerts/propose", headers=COORD,
                       json={"hazard_event_id": eid, "alert_type": "flood_warning",
                             "title": "DK flood warning"})
    assert prop.status_code == 201, prop.text
    aid = prop.json()["id"]
    # no confirm -> 428
    assert client.post(f"/disaster/alerts/{aid}/approve", headers=COORD).status_code == 428
    # confirm -> becomes an active warning
    ok = client.post(f"/disaster/alerts/{aid}/approve", headers=COORD, params={"confirm": True})
    assert ok.status_code == 200 and ok.json()["status"] == "open"


# ===========================================================================
# allocation: human approval, fresh confirmation, capacity, no double-allocation
# ===========================================================================
def test_allocation_requires_approval_and_dispatch_confirmation():
    _seed()
    eid = _dk_event()["hazard_event_id"]
    prop = client.post("/disaster/allocations/propose", headers=COORD,
                       json={"hazard_event_id": eid, "required": {"boat": 2, "personnel": 10}}).json()
    assert len(prop["proposals"]) >= 1 and prop["unmet"] == {}
    aid = prop["proposals"][0]["resource_allocation_id"]
    # approve without confirm -> 428
    assert client.post(f"/disaster/allocations/{aid}/transition", headers=COORD,
                       params={"status": "approved"}, json={"confirm": False}).status_code == 428
    assert client.post(f"/disaster/allocations/{aid}/transition", headers=COORD,
                       params={"status": "approved"}, json={"confirm": True}).json()["status"] == "approved"
    # dispatch also needs confirmation
    assert client.post(f"/disaster/allocations/{aid}/transition", headers=COORD,
                       params={"status": "dispatched"}, json={"confirm": False}).status_code == 428
    assert client.post(f"/disaster/allocations/{aid}/transition", headers=COORD,
                       params={"status": "dispatched"}, json={"confirm": True}).json()["status"] == "dispatched"


def test_allocation_capacity_and_unmet():
    _seed()
    eid = _dk_event()["hazard_event_id"]
    # ask for far more boats than exist + a resource type with no available resource
    prop = client.post("/disaster/allocations/propose", headers=COORD,
                       json={"hazard_event_id": eid, "required": {"boat": 100, "medical": 5}}).json()
    boats = sum(p["quantity_allocated"] for p in prop["proposals"] if p["resource_type"] == "boat")
    assert boats <= 5                      # capped at available boat quantity (no over-allocation)
    assert prop["unmet"].get("boat", 0) > 0 and prop["unmet"].get("medical", 0) == 5


def test_no_double_allocation_beyond_quantity():
    _seed()
    repo = drepo.disaster_repo()
    scope = guards.DisasterScope("super_admin", "demo.sa", None, None)
    event = repo.find_one("HazardEvent", {"HazardCode": "flood", "DistrictID": 24})
    # pick a boat resource (quantity 3)
    boat = next(r for r in repo.list("Resource") if r["ResourceType"] == "boat"
                and int(r["Quantity"]) == 3)
    a1 = repo.create("ResourceAllocation", {"HazardEventID": event["HazardEventID"],
        "ResourceID": boat["ResourceID"], "QuantityAllocated": 2, "Status": "proposed",
        "DistrictID": 24})
    a2 = repo.create("ResourceAllocation", {"HazardEventID": event["HazardEventID"],
        "ResourceID": boat["ResourceID"], "QuantityAllocated": 2, "Status": "proposed",
        "DistrictID": 24})
    assert service.transition_allocation(int(a1["ResourceAllocationID"]), "approved", scope)["status"] == "approved"
    with pytest.raises(service.DisasterConflict):
        service.transition_allocation(int(a2["ResourceAllocationID"]), "approved", scope)


# ===========================================================================
# evacuation routing: hazard-avoiding safe route + explicit no-route
# ===========================================================================
def test_evacuation_route_avoids_hazard_and_no_route():
    _seed()
    dk = _dk_event()
    zones = client.get("/disaster/zones", headers=COORD,
                       params={"district_id": 24, "hazard_code": "flood"}).json()["zones"]
    zid = next(z["hazard_risk_zone_id"] for z in zones if z["zone_kind"] == "dynamic")
    route = client.post("/disaster/routes/propose", headers=COORD,
                        json={"hazard_event_id": dk["hazard_event_id"], "from_zone_id": zid}).json()
    # a safe route was found (proposed); approval/selection is a separate confirmed step
    assert route["status"] == "proposed" and route["distance_km"] > 0
    rid = route["evacuation_route_id"]
    # selecting requires a fresh confirmation
    assert client.post(f"/disaster/routes/{rid}/select", headers=COORD).status_code == 428
    assert client.post(f"/disaster/routes/{rid}/select", headers=COORD,
                       params={"confirm": True}).json()["status"] == "selected"
    # the route does not cross the hazard polygon
    line = route["geojson"]
    hazard = dk["geojson"]
    coords = line["coordinates"]
    crossed = any(geometry.segment_intersects_geometry(coords[i - 1], coords[i], hazard)
                  for i in range(1, len(coords)))
    assert not crossed

    # Bengaluru urban flood: the band separates the zone from all shelters -> no_route
    bev = client.get("/disaster/events", headers=COORD5, params={"district_id": 5}).json()["events"]
    beid = next(e["hazard_event_id"] for e in bev if e["hazard_code"] == "urban_flood")
    bz = client.get("/disaster/zones", headers=COORD, params={"district_id": 5}).json()["zones"]
    bzid = next(z["hazard_risk_zone_id"] for z in bz if z["zone_kind"] == "dynamic")
    broute = client.post("/disaster/routes/propose", headers=COORD5,
                         json={"hazard_event_id": beid, "from_zone_id": bzid}).json()
    assert broute["status"] == "no_route"


def test_routing_unit_open_avoid_noroute():
    assert routing.route(74.80, 12.85, 74.95, 12.98)["status"] == "selected"
    wall = {"type": "Polygon", "coordinates": [[[73.5, 12.905], [76.0, 12.905],
            [76.0, 12.945], [73.5, 12.945], [73.5, 12.905]]]}
    assert routing.route(74.80, 12.86, 74.95, 12.99, hazard_geom=wall)["status"] == "no_route"


# ===========================================================================
# lifecycle + append-only audit
# ===========================================================================
def test_lifecycle_and_append_only_activity():
    _seed()
    eid = _dk_event()["hazard_event_id"]
    client.post(f"/disaster/events/{eid}/transition", headers=COORD, params={"status": "active"})
    repo = drepo.disaster_repo()
    acts = repo.activity_for("hazard_event", eid)
    assert any(a["Action"] == "hazard_event.transition" for a in acts)
    # DisasterActivity is append-only: update/delete raise
    aid = acts[0]["DisasterActivityID"]
    with pytest.raises(drepo.DisasterRepoError):
        repo.update("DisasterActivity", aid, {"Action": "tamper"})
    with pytest.raises(drepo.DisasterRepoError):
        repo.soft_delete("HazardPrediction", 1)      # append-only prediction


# ===========================================================================
# role allow/deny matrix + district scope
# ===========================================================================
def test_role_allow_deny_matrix():
    _seed()
    # crime + policymaker may READ the situational view
    assert client.get("/disaster/overview", headers=CRIME).status_code == 200
    assert client.get("/disaster/overview", headers=POLICY).status_code == 200
    # crime cannot run a forecast / create an event (write) -> 403
    assert client.post("/disaster/forecast/run", headers=CRIME,
                       json={"hazard_code": "flood", "district_id": 24}).status_code == 403
    assert client.post("/disaster/events", headers=CRIME,
                       json={"hazard_code": "flood", "status": "watch", "district_id": 24,
                             "geojson": {}}).status_code == 403
    # coordinator assigned to district 24 cannot act on district 5 -> 403
    assert client.post("/disaster/events", headers=COORD,
                       json={"hazard_code": "urban_flood", "status": "watch", "district_id": 5,
                             "geojson": {}}).status_code == 403
    # super_admin may act anywhere
    assert client.post("/disaster/events", headers=SUPER,
                       json={"hazard_code": "flood", "status": "watch", "district_id": 5,
                             "geojson": {}}).status_code == 201


def test_denied_decisions_are_audited():
    _seed()
    client.post("/disaster/forecast/run", headers=CRIME,
                json={"hazard_code": "flood", "district_id": 24})
    repo = drepo.disaster_repo()
    denials = [a for a in repo.recent_activity() if a["Action"] == "access.denied"]
    assert denials, "a denied decision should be audited"


# ===========================================================================
# Send to Board (disaster object -> board node with pin-time snapshot)
# ===========================================================================
def test_send_hazard_event_to_board(monkeypatch):
    from app.board import guards as bg, repo as brepo
    monkeypatch.setattr(bg, "synthetic_db_ok", lambda: True)
    brepo.reset_board_repo()
    _seed()
    eid = _dk_event()["hazard_event_id"]
    bid = client.post("/boards", headers=CRIME, json={"title": "Hazard review"}).json()["board"]["board_id"]
    r = client.post(f"/boards/{bid}/nodes", headers=CRIME,
                    json={"node_kind": "hazard_event", "ref_table": "HazardEvent", "ref_id": str(eid)})
    assert r.status_code == 201, r.text
    node = client.get(f"/boards/{bid}", headers=CRIME).json()["nodes"][0]
    assert node["node_kind"] == "hazard_event"
    assert node["snapshot"] and node["source_hash"]        # live ref + pin-time snapshot
    meta = client.get("/boards/meta/object-kinds", headers=CRIME).json()
    assert "hazard_event" in meta["node_kinds"] and "HazardEvent" in meta["ref_tables"]
    brepo.reset_board_repo()


# ===========================================================================
# live feed connector (Open-Meteo, no API key, CC BY 4.0)
# ===========================================================================
_OPEN_METEO_SAMPLE = {
    "current_units": {"precipitation": "mm", "temperature_2m": "°C",
                      "relative_humidity_2m": "%", "wind_speed_10m": "km/h"},
    "current": {"time": "2026-07-19T07:30", "precipitation": 2.0,
                "temperature_2m": 28.6, "relative_humidity_2m": 74, "wind_speed_10m": 8.7},
}


def test_live_openmeteo_response_mapping_and_ingest():
    from app.disaster.feeds import LiveOpenMeteoConnector
    station = {"station_code": "OM-DK-MANGALURU", "district_id": 24, "lat": 12.914, "lon": 74.856}
    cands = LiveOpenMeteoConnector._map_response(_OPEN_METEO_SAMPLE, station)
    by_metric = {c.metric_type: c for c in cands}
    assert set(by_metric) == {"rainfall", "temperature", "humidity", "wind"}
    assert by_metric["rainfall"].value == 2.0 and by_metric["rainfall"].unit == "mm"
    assert by_metric["temperature"].value == 28.6
    assert by_metric["wind"].unit == "kmph"
    assert all(c.district_id == 24 and c.source_agency == "Open-Meteo" for c in cands)
    # the mapped candidates ingest cleanly (canonical units, valid quality)
    repo = drepo.disaster_repo()
    run = feeds.ingest("open_meteo_live", candidates=cands, repo=repo)
    assert run["AcceptedCount"] == 4 and run["RejectedCount"] == 0


def test_live_feed_disabled_guard(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "live_feed_enabled", False)
    with pytest.raises(service.DisasterValidation):
        service.ingest_feed("open_meteo_live")


@pytest.mark.skipif(os.getenv("DRISHTI_LIVE_FEED_TEST") != "1",
                    reason="live network smoke test (opt-in via DRISHTI_LIVE_FEED_TEST=1)")
def test_live_openmeteo_smoke():
    """Real read-only call to Open-Meteo (no API key). Opt-in to keep CI offline."""
    repo = drepo.disaster_repo()
    run = feeds.ingest("open_meteo_live", repo=repo)
    assert run["Status"] in ("ok", "stale") and run["AcceptedCount"] > 0
    fresh = {f["feed_code"]: f for f in feeds.freshness(repo)}
    assert fresh["open_meteo_live"]["connector_kind"] == "live"
    assert fresh["open_meteo_live"]["external_access_required"] is False


# ===========================================================================
# feed freshness banner (stale + external-access surfaced)
# ===========================================================================
def test_feed_freshness_surfaces_stale_and_external_access():
    _seed()
    feeds_out = client.get("/disaster/feeds/freshness", headers=COORD).json()["feeds"]
    by_code = {f["feed_code"]: f for f in feeds_out}
    assert by_code["synthetic_replay"]["status"] == "fresh"
    assert by_code["imd_rainfall_recorded"]["status"] == "stale"
    assert by_code["imd_rainfall_recorded"]["external_access_required"] is True
    # the read-only LIVE connector is registered (no external access required)
    assert by_code["open_meteo_live"]["connector_kind"] == "live"
    assert by_code["open_meteo_live"]["external_access_required"] is False
