"""Hidden-association detector — fixture-graph unit test (no DB) + light
integration checks against the materialized feed."""
import pytest

from app.graph import hidden
from conftest import requires_db


# ---- fixture graph with a KNOWN hidden association -------------------------
# Persons: 1..5. Intermediaries tagged by kind.
#   (1,2) share a phone AND a vehicle  -> KNOWN hidden association (2 kinds)
#   (1,3) share only a phone           -> below threshold (1 kind)
#   (4,5) share a phone AND a vehicle  -> but are CO-ACCUSED -> excluded
FIXTURE_LINKS = [
    (1, "phoneP", "phone"),   (2, "phoneP", "phone"),
    (1, "carV",   "vehicle"), (2, "carV",   "vehicle"),
    (1, "phoneQ", "phone"),   (3, "phoneQ", "phone"),      # only 1 shared kind
    (4, "phoneR", "phone"),   (5, "phoneR", "phone"),
    (4, "carW",   "vehicle"), (5, "carW",   "vehicle"),    # 2 kinds but co-accused
]
CO_ACCUSED = [(4, 5)]


def test_known_hidden_association_is_surfaced():
    pairs = hidden.detect_hidden_pairs(FIXTURE_LINKS, CO_ACCUSED, min_links=2)
    surfaced = {(p["a"], p["b"]) for p in pairs}
    assert (1, 2) in surfaced                      # the known hidden association
    top = pairs[0]
    assert top["a"] == 1 and top["b"] == 2
    assert set(top["link_kinds"]) == {"phone", "vehicle"}
    assert top["independent_links"] == 2
    assert set(top["shared_intermediaries"]) == {"phoneP", "carV"}


def test_single_shared_kind_not_surfaced():
    pairs = hidden.detect_hidden_pairs(FIXTURE_LINKS, CO_ACCUSED, min_links=2)
    assert (1, 3) not in {(p["a"], p["b"]) for p in pairs}


def test_co_accused_pair_excluded_even_with_two_kinds():
    pairs = hidden.detect_hidden_pairs(FIXTURE_LINKS, CO_ACCUSED, min_links=2)
    assert (4, 5) not in {(p["a"], p["b"]) for p in pairs}
    # without the co-accused exclusion it WOULD surface -> proves exclusion works
    pairs_no_excl = hidden.detect_hidden_pairs(FIXTURE_LINKS, [], min_links=2)
    assert (4, 5) in {(p["a"], p["b"]) for p in pairs_no_excl}


def test_min_links_three_filters_two_kind_pairs():
    assert hidden.detect_hidden_pairs(FIXTURE_LINKS, CO_ACCUSED, min_links=3) == []


# ---- integration: the materialized feed on the loaded graph ----------------
@requires_db
def test_materialized_feed_has_ranked_rows():
    from app import db
    with db.ro_conn() as conn:
        total, items = hidden.feed(conn, page=1, page_size=5, min_links=2)
    assert total > 0
    assert len(items) > 0
    # every surfaced pair truly has >=2 kinds and zero shared cases
    for it in items:
        assert it["independent_links"] >= 2
        assert len(set(it["link_kinds"])) >= 2
        assert it["shared_case_count"] == 0
    # ranked by score descending
    scores = [it["score"] for it in items]
    assert scores == sorted(scores, reverse=True)
