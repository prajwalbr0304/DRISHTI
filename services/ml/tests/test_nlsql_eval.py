"""Golden-evaluation gate for Ask DRISHTI (Prompt 19 §G).

Runs the versioned golden set (eval/golden_v1.json) through the deterministic,
offline harness and asserts the coverage the prompt requires plus the metric
thresholds. Security-critical metrics (guard block, scope denial, injection
safety, emitted-SQL guard validity) must be PERFECT; language/viz/multi-turn
carry are exact for the deterministic planner; intent has a small margin. Live
provider accuracy + real citation/execution validity are proven in Prompt 23.
"""
from eval.run_eval import run


_REPORT = run()


def test_golden_coverage_meets_prompt_requirements():
    cov = _REPORT["coverage"]
    counts = _REPORT["case_counts"]
    assert cov["english_nl"] >= 20, cov
    assert cov["kannada_or_translit_nl"] >= 20, cov
    assert cov["multiturn_chains"] >= 10, cov
    # every required visualization kind appears in the set
    for kind in ("table", "number", "bar", "line", "choropleth", "heatmap",
                 "timeline", "network", "sankey", "link"):
        assert kind in cov["viz_kinds_covered"], kind
    # denial + injection + guard categories are present
    assert counts.get("scope", 0) >= 5
    assert counts.get("guard", 0) >= 5
    assert counts.get("injection", 0) >= 2


def test_no_failures():
    assert _REPORT["failures"] == [], _REPORT["failures"]


def test_security_metrics_are_perfect():
    m = _REPORT["metrics"]
    # a proposed query never escapes the guard or role scope, and injection is safe
    assert m["guard_block"]["rate"] == 1.0, m["guard_block"]
    assert m["scope_denial"]["rate"] == 1.0, m["scope_denial"]
    assert m["injection_safe"]["rate"] == 1.0, m["injection_safe"]
    assert m["guard_valid"]["rate"] == 1.0, m["guard_valid"]


def test_quality_metrics_meet_threshold():
    m = _REPORT["metrics"]
    assert m["intent"]["rate"] >= 0.9, m["intent"]
    assert m["language"]["rate"] == 1.0, m["language"]
    assert m["viz"]["rate"] == 1.0, m["viz"]
    assert m["carry"]["rate"] == 1.0, m["carry"]
    assert m["spec_valid"]["rate"] == 1.0, m["spec_valid"]
    assert m["aggregate"]["rate"] == 1.0, m["aggregate"]


def test_latency_is_recorded_and_bounded():
    lat = _REPORT["latency"]
    assert lat["n"] >= 40
    # deterministic regex planning is sub-millisecond; a generous CI ceiling.
    assert lat["p95_ms"] < 50.0, lat
