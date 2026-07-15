"""Phase-13 explainability tests.

Unit (no DB): the shared honesty guards. Integration (@requires_db): the LIVE
contract audit (every AI route conforms), the /explain evidence chains for all
four explainable tables (incl. the risk gauge + factor bars and the summary's
recovered citations), and model explainability + drift.
"""
import pytest

from app import guards
from app.contracts import AiResult
from conftest import requires_db


# ---- unit: shared honesty guards -------------------------------------------
def test_k_anon_suppress():
    cells = [{"c": 3}, {"c": 12}, {"c": 9}, {"c": 50}]
    kept, suppressed = guards.k_anon_suppress(cells, "c", k=10)
    assert suppressed == 2 and len(kept) == 2
    assert all(x["c"] >= 10 for x in kept)


def test_causation_disclaimer_and_aggregate_path():
    assert "NOT causal" in guards.CAUSATION_DISCLAIMER
    assert guards.is_aggregate_path("/analytics/socioeconomic")
    assert guards.is_aggregate_path("/forecast/map")
    assert not guards.is_aggregate_path("/explain/models")
    assert not guards.is_aggregate_path("/risk/61")


def test_analytics_reexports_canonical_disclaimer():
    from app.analytics.schemas import CAUSATION_DISCLAIMER
    assert CAUSATION_DISCLAIMER is guards.CAUSATION_DISCLAIMER


# ---- integration -----------------------------------------------------------
def _assert_airesult(r: AiResult):
    assert isinstance(r.answer, str) and r.answer
    assert 0.0 <= r.confidence <= 1.0
    assert isinstance(r.source_record_ids, list)
    assert "@" in r.model_version


def _find(sql):
    from app import db
    with db.ro_conn() as c:
        with c.cursor() as cur:
            cur.execute(sql)
            r = cur.fetchone()
    return int(r[0]) if r else None


@requires_db
def test_contract_audit_every_ai_route_conforms():
    from app.explain import service
    ca = service.contract_audit()
    _assert_airesult(ca.result)
    assert ca.total >= 25
    assert ca.non_conforming == 0            # the whole point of Phase 13.1
    assert all(r.conforms for r in ca.routes)


@requires_db
def test_explain_risk_has_gauge_and_signed_factor_bars():
    from app.explain import service
    rid = _find('SELECT "RiskScoreID" FROM "CrimeRiskScore" '
                'WHERE "Factors"->\'top_factors\' IS NOT NULL LIMIT 1')
    if rid is None:
        pytest.skip("no risk scores")
    r = service.explain_row("CrimeRiskScore", rid)
    _assert_airesult(r.result)
    assert r.gauge_bars is not None
    assert 0.0 <= r.gauge_bars.score <= 1.0
    assert r.gauge_bars.factors                      # signed factor bars
    assert all(f.direction in ("increases", "decreases") for f in r.gauge_bars.factors)
    assert any(s.startswith("ModelVersion:") for s in r.source_record_ids)


@requires_db
def test_explain_summary_recovers_cited_records():
    from app.explain import service
    sid = _find('SELECT s."SummaryID" FROM "AISummary" s JOIN "ModelVersion" mv '
                'ON mv."ModelVersionID"=s."ModelVersionID" '
                'WHERE mv."ModelName"=\'drishti-oag-summary\' LIMIT 1')
    if sid is None:
        pytest.skip("no OAG summaries; run `python -m app.batch case-summary --case 82412`")
    r = service.explain_row("AISummary", sid)
    _assert_airesult(r.result)
    assert r.reproducible and r.inference is not None
    # the cited records are recovered from the stored inference input snapshot
    assert any(":" in s and s.startswith(("CaseMaster:", "Victim:", "Accused:", "ActSection"))
               for s in r.source_record_ids)


@requires_db
def test_explain_prediction_and_alert_build_chains():
    from app.explain import service
    pid = _find('SELECT "PredictionID" FROM "CrimePrediction" WHERE "Features" ? \'layer\' LIMIT 1')
    if pid is not None:
        r = service.explain_row("CrimePrediction", pid)
        _assert_airesult(r.result)
        assert r.model is not None and r.source_record_ids
    aid = _find('SELECT "AlertID" FROM "AlertHistory" WHERE "ModelVersionID" IS NOT NULL LIMIT 1')
    if aid is not None:
        r = service.explain_row("AlertHistory", aid)
        _assert_airesult(r.result)
        assert r.subject.get("alert_type") and r.source_record_ids


@requires_db
def test_explain_unsupported_and_missing():
    from app.explain import service
    assert service.explain_row("Victim", 1) is service.UNSUPPORTED
    assert service.explain_row("CrimeRiskScore", 999_999_999) is None


@requires_db
def test_model_explainability_and_drift():
    from app.explain import service
    me = service.model_explainability()
    _assert_airesult(me.result)
    assert me.count > 0
    assert any(m.calibration for m in me.models)          # calibration exposed
    mv = next((m.model_version_id for m in me.models if m.inferences > 0), me.models[0].model_version_id)
    md = service.model_detail(mv)
    _assert_airesult(md.result)
    assert md.drift_flag in ("stable", "rising_confidence", "falling_confidence", "insufficient")
    assert isinstance(md.drift, list)
