"""Prompt 20 Part A — synthetic crypto / dark-web / cross-jurisdiction scenario
registry: validation gate, jurisdiction-scope taxonomy, typed edges, bilingual
searchability and the API. All offline (no DB, no network)."""
import json
import pathlib

from fastapi.testclient import TestClient

from app.main import app
from app.scenarios import registry, service

client = TestClient(app)

_FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "app" / "scenarios" / "fixtures" / "prompt20_scenarios.json"


# ============================ validation gate ==============================
def test_registry_validates_clean():
    v = registry.validate()
    assert v["ok"] is True, v["failures"]


def test_all_jurisdiction_scopes_and_families_covered():
    assert registry.scopes_covered() == set(registry.JURISDICTION_SCOPES)
    assert registry.families_covered() == set(registry.CRIME_FAMILIES)
    # jurisdiction scope is a governed dimension separate from crime type.
    assert set(registry.JURISDICTION_SCOPES) == {
        "local", "inter_district", "inter_state", "national", "international", "cross_border"}


def test_crypto_and_darkweb_present_and_safe():
    fams = registry.families_covered()
    assert any(f.startswith("crypto") for f in fams)
    assert any(f.startswith("darkweb") for f in fams)
    # dark-web scenarios are a manually classified source with NO live collection.
    for scn in registry.SCENARIOS:
        assert scn["live_collection"] is False
        if scn["crime_family"].startswith("darkweb"):
            assert scn["source_classification"] == "manual"
            assert any(n["type"] == "source_record" for n in scn["entities"])


def test_edges_are_typed_and_reference_known_nodes():
    for scn in registry.SCENARIOS:
        node_ids = {n["id"] for n in scn["entities"]}
        for e in scn["edges"]:
            assert e["basis"] in registry.EDGE_BASES
            assert e["source"] in node_ids and e["target"] in node_ids
        for n in scn["entities"]:
            assert n["type"] in registry.ENTITY_TYPES


def test_hypothetical_and_evidence_edges_both_present():
    bases = {e["basis"] for scn in registry.SCENARIOS for e in scn["edges"]}
    assert "evidence-backed" in bases and "hypothetical" in bases


# ============================ searchability ================================
def test_search_by_keyword_english():
    hits = registry.search("cryptocurrency")
    assert hits and all("crypto" in h["crime_family"] or "crypto" in h["title"].lower() for h in hits)


def test_search_by_keyword_kannada():
    # Kannada crypto term maps via the family kn label.
    hits = registry.search("ಕ್ರಿಪ್ಟೋ")
    assert len(hits) >= 1


def test_search_filters_by_scope_and_family():
    xborder = registry.search(None, jurisdiction_scope="cross_border")
    assert xborder and all(h["jurisdiction_scope"] == "cross_border" for h in xborder)
    dw = registry.search(None, crime_family="darkweb_contraband")
    assert dw and all(h["crime_family"] == "darkweb_contraband" for h in dw)


def test_nl_examples_are_bilingual():
    ex = registry.nl_examples()
    langs = {e["lang"] for e in ex}
    assert "en" in langs and "kn" in langs
    assert len(ex) >= 16


# ============================ committed fixture ============================
def test_golden_fixture_on_disk_matches_registry():
    assert _FIXTURE.exists(), "run service.build_fixture() to (re)generate the fixture"
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert data["valid"] is True
    assert data["counts"]["scenarios"] == registry.scenario_count()
    assert len(data["scenarios"]) == registry.scenario_count()
    assert data["live_collection"] is False


# ============================ API ==========================================
def test_scenarios_overview_endpoint():
    r = client.get("/scenarios")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["total"] == registry.scenario_count()
    assert {"local", "inter_state", "cross_border"} <= {
        s["code"] for s in body["taxonomy"]["jurisdiction_scopes"]}


def test_scenarios_search_endpoint():
    r = client.get("/scenarios/search", params={"scope": "inter_state"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all(i["jurisdiction_scope"] == "inter_state" for i in items)


def test_scenarios_validate_endpoint():
    r = client.get("/scenarios/validate")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_scenario_detail_and_404():
    ok = client.get("/scenarios/P20-CRYPTO-001")
    assert ok.status_code == 200 and ok.json()["crime_family"] == "crypto_fraud"
    assert client.get("/scenarios/NOPE").status_code == 404


# ============================ NL glossary integration ======================
def test_glossary_has_crypto_darkweb_jurisdiction_terms():
    from app.nlsql.glossary import glossary_text
    text = glossary_text().lower()
    assert "crypto" in text and "dark web" in text
    assert "inter-state" in text and "cross-border" in text
