"""AiResult contract tests — the shared shape every AI endpoint must return."""
import pytest
from pydantic import ValidationError

from app.contracts import AiResult


def test_airesult_has_all_contract_fields():
    r = AiResult(
        answer="Bengaluru City risk HIGH",
        confidence=0.82,
        source_record_ids=["District:1", "CrimeRiskScore:99"],
        reasoning_summary="demo",
        model_version="drishti-risk@1.0.0",
    )
    d = r.model_dump()
    assert set(d) == {
        "answer", "confidence", "source_record_ids", "reasoning_summary", "model_version",
    }
    assert d["confidence"] == 0.82
    assert d["source_record_ids"][0] == "District:1"


def test_confidence_must_be_within_unit_interval():
    for bad in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            AiResult(answer="x", confidence=bad, model_version="m@1")


def test_source_record_ids_defaults_to_empty_list():
    r = AiResult(answer="x", confidence=0.5, model_version="m@1")
    assert r.source_record_ids == []
    assert r.reasoning_summary == ""


def test_answer_and_model_version_required():
    with pytest.raises(ValidationError):
        AiResult(confidence=0.5)  # type: ignore[call-arg]
