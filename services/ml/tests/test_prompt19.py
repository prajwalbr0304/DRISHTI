"""Prompt 19 unit tests: scope flags, provider-neutral planner labelling, the
typed visualization selector, the truthful capability advertisement and the
Zia-voice honest-disable adapter. All offline, no DB, no network."""
import pytest

from app.config import Settings, get_settings
from app.nlsql import viz
from app.nlsql.planner import (BedrockPlanner, CatalystQuickMLServingPlanner,
                               FallbackPlanner, LLMPlanner, get_planner)


# ============================ A: scope flags ================================
def test_no_commercial_default_model_and_scope_flag_defaults():
    # gpt-4o-mini is gone: the code default is provider-neutral (empty).
    assert Settings.model_fields["llm_model"].default == ""
    assert Settings.model_fields["llm_base_url"].default == ""
    # voice query is in scope; evidence extraction is not (named separately).
    assert Settings.model_fields["query_voice_enabled"].default is True
    assert Settings.model_fields["evidence_extraction_enabled"].default is False


# ==================== B: provider-neutral planner labelling =================
def test_arbitrary_quickml_provider_is_disabled():
    s = Settings(semantic_planner_provider="catalyst_quickml",
                 quickml_llm_endpoint="https://quickml.example/llm",
                 quickml_llm_model="qwen2.5-14b-instruct")
    assert s.quickml_llm_configured() is False
    assert s.primary_planner_name() == "deterministic-fallback"


def test_arbitrary_openai_compatible_provider_is_disabled():
    s = Settings(semantic_planner_provider="openai_compatible",
                 llm_api_key="k", llm_base_url="https://api.openai.com/v1",
                 llm_model="qwen2.5-14b-instruct")
    assert s.openai_compatible_configured() is False
    assert s.primary_planner_name() == "deterministic-fallback"


def test_primary_planner_name_bedrock_when_configured():
    s = Settings(semantic_planner_provider="aws_bedrock",
                 bedrock_model_id="zai.glm-4.7-flash")
    assert s.bedrock_configured() is True
    assert s.primary_planner_name() == "aws-bedrock"


def test_primary_planner_name_fails_closed_to_deterministic():
    s = Settings(semantic_planner_provider="", llm_api_key="", llm_base_url="", llm_model="",
                 quickml_llm_endpoint="", quickml_llm_model="")
    assert s.primary_planner_name() == "deterministic-fallback"


def test_planner_source_labels_are_stable():
    assert FallbackPlanner.name == "deterministic-fallback"
    assert CatalystQuickMLServingPlanner.name == "catalyst-quickml-llm"
    assert LLMPlanner.name == "openai-compatible"
    assert BedrockPlanner.name == "aws-bedrock"


def test_bedrock_planner_does_not_set_app_token_cap(monkeypatch):
    captured = {}

    class _Client:
        def converse(self, **kwargs):
            captured.update(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [
                            {"text": '{"sql":"SELECT COUNT(*) FROM \\"CaseMaster\\"","confidence":0.9}'}
                        ]
                    }
                }
            }

    p = BedrockPlanner(Settings(semantic_planner_provider="aws_bedrock",
                                bedrock_model_id="zai.glm-4.7-flash",
                                bedrock_direct_sdk_enabled=True))
    monkeypatch.setattr(p, "_client", lambda: _Client())

    plan = p.plan("how many cases", "crime_analyst", "en", [])

    assert plan.sql == 'SELECT COUNT(*) FROM "CaseMaster"'
    assert captured["inferenceConfig"] == {"temperature": 0}
    assert "maxTokens" not in captured["inferenceConfig"]


def test_get_planner_returns_an_object_with_a_name():
    # ambient config decides which; whatever it is, it must carry a source label.
    p = get_planner()
    assert getattr(p, "name", None)


# ==================== F: typed visualization selector =======================
def _viz(cols, rows, intent, language="en"):
    return viz.build_visualization(cols, rows, intent=intent, language=language,
                                   citations=[], confidence=0.7, role="crime_analyst",
                                   row_total=len(rows))


def test_viz_number_for_single_scalar():
    spec = _viz(["case_count"], [[42]], "count")
    assert spec["kind"] == "number"
    assert spec["measures"][0]["index"] == 0
    assert spec["accessible_table"]["row_ref"] == "rows_preview"


def test_viz_line_for_time_series():
    spec = _viz(["month", "case_count"], [["2026-01", 5], ["2026-02", 9]], "trend")
    assert spec["kind"] == "line"
    assert spec["time_field"] == "month"


def test_viz_choropleth_for_district_measure():
    spec = _viz(["DistrictName", "case_count"], [["Mysuru", 3], ["Bengaluru", 8]], "top_districts")
    assert spec["kind"] == "choropleth"
    assert spec["geo_field"] == "DistrictName"


def test_viz_bar_for_nongeo_category_measure():
    spec = _viz(["CrimeGroupName", "n"], [["Cyber", 9], ["Property", 4]], "count")
    assert spec["kind"] == "bar"


def test_viz_table_for_case_list_and_briefing():
    assert _viz(["CaseMasterID", "CrimeNo"], [[1, "SYN-1"]], "list_cases")["kind"] == "table"
    assert _viz(["Metric", "Value"], [["FIRs", 10]], "briefing")["kind"] == "table"


def test_viz_localised_title_kn():
    spec = _viz(["case_count"], [[7]], "count", language="kn")
    assert spec["kind"] == "number"
    assert any("\u0c80" <= ch <= "\u0cff" for ch in spec["title"])   # Kannada title


def test_validate_spec_rejects_disallowed_kind():
    bad = {"kind": "pie3d", "accessible_table": {"columns": ["a"], "row_ref": "rows_preview"},
           "dimensions": [], "measures": []}
    with pytest.raises(viz.VizError):
        viz.validate_spec(bad)


def test_validate_spec_rejects_out_of_range_index():
    bad = {"kind": "bar", "accessible_table": {"columns": ["a"], "row_ref": "rows_preview"},
           "dimensions": [{"field": "x", "label": "X", "index": 9, "role": "dim"}], "measures": []}
    with pytest.raises(viz.VizError):
        viz.validate_spec(bad)


def test_all_allowed_kinds_are_the_prompt_set():
    assert viz.ALLOWED_KINDS == frozenset({
        "table", "number", "bar", "line", "choropleth", "heatmap",
        "timeline", "network", "sankey", "link"})


# ==================== E: voice capability (honest disable) ==================
def test_zia_voice_unavailable_by_default():
    from app import zia_voice
    v = zia_voice.get_zia_voice()
    assert isinstance(v, zia_voice.UnavailableZiaVoice)
    assert v.available is False
    # no fabricated translation when Zia translation is unavailable
    assert v.translate("hello", target="kn") is None


def test_voice_capability_status_is_truthful_browser_not_zia():
    from app import zia_voice
    st = zia_voice.voice_capability_status()
    assert st["provider"] == "browser-web-speech"      # never labelled Zia
    assert st["zia_voice_available"] is False
    assert st["bilingual_text"] is True
    assert st["evidence_extraction_enabled"] is False  # OCR/extraction stays off
    assert st["platform_limitation"] and st["evidence"]  # recorded honestly


# ==================== capability advertisement endpoint =====================
def test_capabilities_advertises_planner_voice_and_viz():
    from app.chat import service
    cap = service.capabilities()
    assert cap.semantic_planner.fallback == "deterministic-fallback"
    assert cap.semantic_planner.primary                     # non-empty label
    assert cap.voice["provider"] == "browser-web-speech"
    assert "en" in cap.languages and "kn" in cap.languages
    for kind in ("number", "bar", "line", "choropleth", "table"):
        assert kind in cap.visualization_kinds
    assert cap.scope.query_voice_enabled is True
    assert cap.scope.evidence_extraction_enabled is False
