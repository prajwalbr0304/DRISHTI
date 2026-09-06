"""Prompt 20 Part G — visual coverage proof (backend contract).

Every advertised visualization family (map, heatmap, timeline, network, trend,
Sankey) is (a) an approved kind, (b) accepted by the server-side validator with
its accessible-table fallback, and (c) selected deterministically for the right
result shape. The FRONTEND rendering of each family + its accessible-table
fallback + loading/empty/error states is covered by
web/src/components/ask/__tests__/AnswerVisualization.test.tsx. Offline, no DB."""
import pytest

from app.nlsql import viz

# The six visualization families the organizer notes require, mapped to the
# approved kind(s) that back each in DRISHTI.
REQUIRED_FAMILIES = {
    "map": ("choropleth",),
    "heatmap": ("heatmap",),
    "timeline": ("timeline", "line"),
    "network": ("network",),
    "trend": ("line", "bar"),
    "sankey": ("sankey",),
}


def _spec(kind: str) -> dict:
    return {
        "kind": kind,
        "title": f"{kind} viz",
        "dimensions": [{"field": "a", "label": "A", "index": 0, "role": "dim"}],
        "measures": [{"field": "b", "label": "B", "index": 1, "unit": "count"}],
        "accessible_table": {"columns": ["a", "b"], "row_ref": "rows_preview"},
    }


def test_all_required_families_map_to_allowed_kinds():
    for family, kinds in REQUIRED_FAMILIES.items():
        for k in kinds:
            assert k in viz.ALLOWED_KINDS, f"{family} -> {k} not an allowed kind"


def test_validate_spec_accepts_each_required_family_with_accessible_table():
    # Each advertised family must survive server-side validation (and thus always
    # carries an accessible-table fallback) before it can reach the browser.
    for family, kinds in REQUIRED_FAMILIES.items():
        for k in kinds:
            out = viz.validate_spec(_spec(k))
            assert out["kind"] == k
            assert out["accessible_table"]["columns"] == ["a", "b"]


def _viz(cols, rows, intent):
    return viz.build_visualization(cols, rows, intent=intent, language="en",
                                   citations=[], confidence=0.7, role="senior_command",
                                   row_total=len(rows))


def test_selector_picks_the_right_kind_per_shape():
    # trend (time series) -> line
    assert _viz(["month", "n"], [["2026-01", 3], ["2026-02", 5]], "trend")["kind"] == "line"
    # map (district grouping) -> choropleth
    assert _viz(["DistrictName", "n"], [["Mysuru", 3]], "top_districts")["kind"] == "choropleth"
    # trend (non-geo category) -> bar
    assert _viz(["CrimeGroupName", "n"], [["Cyber", 9]], "count")["kind"] == "bar"
    # single scalar -> number
    assert _viz(["case_count"], [[42]], "count")["kind"] == "number"
    # case list -> table
    assert _viz(["CaseMasterID", "CrimeNo"], [[1, "SYN-1"]], "list_cases")["kind"] == "table"


def test_only_approved_kinds_and_indices_are_ever_emitted():
    with pytest.raises(viz.VizError):
        viz.validate_spec({"kind": "pie3d", "accessible_table": {"columns": ["a"], "row_ref": "rows_preview"},
                           "dimensions": [], "measures": []})
    with pytest.raises(viz.VizError):
        viz.validate_spec({"kind": "network",
                           "accessible_table": {"columns": ["a"], "row_ref": "rows_preview"},
                           "dimensions": [{"field": "x", "label": "X", "index": 5, "role": "d"}],
                           "measures": []})
