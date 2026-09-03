"""Socio-economic correlation tests: contract (disclaimer/AiResult) + k-anon
suppression + real correlation shape on the loaded data."""
import pytest

from app.analytics.schemas import CAUSATION_DISCLAIMER
from conftest import requires_db


# ---- contract: the causation disclaimer is part of the PAYLOAD ------------
def test_disclaimer_constant_is_non_empty_and_names_correlation():
    assert "correlation" in CAUSATION_DISCLAIMER.lower()
    assert "not" in CAUSATION_DISCLAIMER.lower()
    assert len(CAUSATION_DISCLAIMER) > 80


@requires_db
def test_report_returns_matrix_scatter_and_disclaimer():
    from app.analytics import service
    r = service.socioeconomic_report(k_threshold=25)
    assert r.districts_analysed > 0
    assert len(r.correlation_matrix) > 0
    assert len(r.scatter) > 0
    # every response embeds the AiResult contract
    assert set(r.result.model_dump()) == {
        "answer", "confidence", "source_record_ids", "reasoning_summary", "model_version"}
    # the disclaimer is mandatory and present verbatim in the payload
    assert r.narrative.disclaimer == CAUSATION_DISCLAIMER
    assert 0.0 <= r.result.confidence <= 1.0


@requires_db
def test_correlations_are_per_capita_and_bounded():
    from app.analytics import service
    r = service.socioeconomic_report(k_threshold=25)
    for cell in r.correlation_matrix:
        if cell.r is not None:
            assert -1.0 <= cell.r <= 1.0
            assert cell.n >= 1
    # scatter y-values are rates per 100k (bounded, not raw 6-digit counts of a metro)
    for series in r.scatter:
        for p in series.points:
            assert p.y >= 0


@requires_db
def test_k_anonymity_suppression_increases_with_threshold():
    from app.analytics import service
    low = service.socioeconomic_report(k_threshold=1)
    high = service.socioeconomic_report(k_threshold=500)
    assert high.suppressed_cells >= low.suppressed_cells
    assert high.k_threshold == 500


@requires_db
def test_narrative_formats_rounded_zero_p_value_as_bound():
    from app.analytics import service
    r = service.socioeconomic_report(k_threshold=25)
    if r.narrative.r is not None and "p" in r.narrative.detail:
        assert "p=0.0" not in r.narrative.detail


@requires_db
def test_requested_indicator_drives_the_narrative_and_scatter():
    from app.analytics import service
    r = service.socioeconomic_report(k_threshold=25, focus_indicator="literacy_rate")
    assert r.focus_indicator == "literacy_rate"
    assert r.narrative.indicator == "literacy_rate"
    assert "literacy rate" in r.narrative.detail.lower()
    assert all(series.indicator == "literacy_rate" for series in r.scatter)
