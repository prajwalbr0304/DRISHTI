"""Scenario service (Prompt 20 Part A) — thin, DB-free wrapper over the
deterministic registry, plus the golden-fixture builder."""
from __future__ import annotations

from typing import Optional

from . import registry


def taxonomy() -> dict:
    return {
        "jurisdiction_scopes": [
            {"code": code, **meta} for code, meta in registry.JURISDICTION_SCOPES.items()
        ],
        "crime_families": [
            {"code": code, **meta} for code, meta in registry.CRIME_FAMILIES.items()
        ],
        "entity_types": list(registry.ENTITY_TYPES),
        "edge_bases": list(registry.EDGE_BASES),
    }


def overview() -> dict:
    v = registry.validate()
    return {
        "total": registry.scenario_count(),
        "counts": v["counts"],
        "valid": v["ok"],
        "taxonomy": taxonomy(),
        "note": ("Additive synthetic scenario fixtures — no live scraping, purchase, "
                 "credential use or illegal-content collection. Dark-web scenarios are "
                 "a manually classified source."),
    }


def search(query: Optional[str], scope: Optional[str], family: Optional[str],
           limit: int = 50) -> dict:
    items = registry.search(query, jurisdiction_scope=scope, crime_family=family, limit=limit)
    return {"total": len(items), "query": query, "jurisdiction_scope": scope,
            "crime_family": family, "items": items}


def get(scenario_id: str) -> Optional[dict]:
    for scn in registry.SCENARIOS:
        if scn["scenario_id"] == scenario_id:
            return scn
    return None


def validate() -> dict:
    return registry.validate()


def nl_examples() -> dict:
    ex = registry.nl_examples()
    return {"total": len(ex), "items": ex}


def build_fixture() -> dict:
    """The deterministic golden fixture (committed to disk as JSON)."""
    v = registry.validate()
    return {
        "fixture": "prompt20-scenarios",
        "version": "1",
        "synthetic": True,
        "live_collection": False,
        "counts": v["counts"],
        "valid": v["ok"],
        "taxonomy": taxonomy(),
        "scenarios": registry.SCENARIOS,
        "nl_examples": registry.nl_examples(),
    }
