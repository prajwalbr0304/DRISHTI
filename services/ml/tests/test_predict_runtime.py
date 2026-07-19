"""Prompt 14 Part G — the six focused prediction-runtime tests (G.5).

Reduced, per G.5, to exactly the tests that matter for the hackathon:
  1. a FIR draft produces no prediction;
  2. an approved FIR creates ONE idempotent prediction request;
  3. one real TabFM CUDA prediction succeeds (integration — skipped unless the
     real AWS adapter + GPU plane is configured, i.e. the HELD cloud step);
  4. a TabFM failure is never labelled a success (fail-closed);
  5. an evidence upload does not invoke a model;
  6. a correction marks the previous result stale and permits a controlled rerun.

TimesFM / Disaster Response / Investigation Board tests belong to their own
phases (and Prompt 18), not here. All tests below run offline with the in-memory
fake adapter + in-memory Data Store; no DB, no cloud.
"""
import os

import pytest

from app.datastore.repository import InMemoryDataStore
from app.predict.adapter import InMemoryFakeAdapter
from app.predict.envelope import BackendKind, ColumnDef, DeviceKind, ModelTask
from app.predict.routing import InputEvent, RoutingContext, route
from app.predict.runtime import PredictionJobInput, PredictionRuntime, RuntimeRefused

_REAL_ADAPTER = bool(os.getenv("DRISHTI_AWS_ADAPTER_URL") and os.getenv("DRISHTI_AWS_ADAPTER_SECRET"))


def _job(*, task=ModelTask.STATION_WORKLOAD_BAND, backend=BackendKind.INCONTEXT,
         svh="svh-1", event=InputEvent.FIR_APPROVED, verified=True) -> PredictionJobInput:
    ctx = RoutingContext(event=event, subject_kind="district",
                         has_verified_geography=verified, has_verified_time=verified,
                         has_verified_head=verified)
    return PredictionJobInput(
        routing_ctx=ctx, task=task, requested_backend=backend, subject_kind="district",
        subject_ids=["12"], columns=[ColumnDef(name="f0"), ColumnDef(name="f1")],
        query_rows=[[1.0, 2.0], [3.0, 4.0]], feature_schema_version="tabfm-workload-band@1",
        model_version="drishti-tabfm-workload@1.0.0", feature_schema_digest="fsd-1",
        observation_cutoff="2026-01-01T00:00:00Z", source_version_hash=svh,
        values={"f0": 1.0, "f1": 2.0}, context_x=[[1.0, 2.0]], context_y=[0])


def _runtime():
    repo = InMemoryDataStore()
    return PredictionRuntime(adapter=InMemoryFakeAdapter(), repository=repo), repo


# 1 -------------------------------------------------------------------------
def test_fir_draft_produces_no_prediction():
    rt, repo = _runtime()
    assert route(RoutingContext(event=InputEvent.FIR_DRAFT_SAVED)).invokes_model is False
    with pytest.raises(RuntimeRefused):
        rt.submit(_job(event=InputEvent.FIR_DRAFT_SAVED))
    assert repo.query("FeatureSnapshot") == []
    assert repo.query("PredictionRequest") == []


# 2 -------------------------------------------------------------------------
def test_approved_fir_creates_one_idempotent_request():
    rt, repo = _runtime()
    h1 = rt.submit(_job(svh="svh-A"))
    h2 = rt.submit(_job(svh="svh-A"))  # identical inputs -> identical idempotency key
    assert h1.idempotency_key == h2.idempotency_key
    assert h1.prediction_request_external_id == h2.prediction_request_external_id
    assert len(repo.query("PredictionRequest")) == 1          # no duplicate request/GPU job
    assert h1.dispatch_mode == "sagemaker_async"              # single mechanism (G.3)


# 3 -------------------------------------------------------------------------
@pytest.mark.skipif(not _REAL_ADAPTER,
                    reason="real AWS adapter + GPU plane not configured (HELD cloud step)")
def test_real_tabfm_cuda_prediction_succeeds():
    from app.predict.adapter import get_adapter
    rt = PredictionRuntime(adapter=get_adapter(), repository=InMemoryDataStore())
    handle = rt.submit(_job(task=ModelTask.STATION_WORKLOAD_BAND,
                            backend=BackendKind.TABFM, svh="svh-real"))
    res = rt.collect(handle)
    assert res.state == "completed" and res.persisted
    assert res.result is not None
    assert res.result.actual_backend == BackendKind.TABFM
    assert res.result.actual_device == DeviceKind.CUDA


# 4 -------------------------------------------------------------------------
def test_tabfm_failure_not_labelled_success():
    # The offline fake adapter FAILS CLOSED for a real-TabFM request.
    rt, repo = _runtime()
    handle = rt.submit(_job(backend=BackendKind.TABFM, svh="svh-fail"))
    res = rt.collect(handle)
    assert res.state in ("failed", "rejected")
    assert res.persisted is False
    assert res.prediction_result_external_id is None
    assert repo.query("PredictionResult") == []              # never persisted as a result


# 5 -------------------------------------------------------------------------
def test_evidence_upload_does_not_invoke_model():
    rt, repo = _runtime()
    assert route(RoutingContext(event=InputEvent.EVIDENCE_UPLOADED)).invokes_model is False
    with pytest.raises(RuntimeRefused):
        rt.submit(_job(event=InputEvent.EVIDENCE_UPLOADED))
    assert repo.query("PredictionRequest") == []


# 6 -------------------------------------------------------------------------
def test_correction_marks_previous_stale_and_reruns():
    rt, repo = _runtime()
    # v1: approved FIR -> completed -> live result
    h1 = rt.submit(_job(svh="svh-v1"))
    r1 = rt.collect(h1)
    assert r1.persisted
    assert repo.get("PredictionResult", r1.prediction_result_external_id)["IsStale"] is False

    # correction: a NEW source version supersedes the prior result (controlled rerun)
    h2 = rt.submit(_job(svh="svh-v2"))
    assert h2.superseded_prior == 1
    assert h2.prediction_request_external_id != h1.prediction_request_external_id

    prior = repo.get("PredictionResult", r1.prediction_result_external_id)
    assert prior["IsStale"] is True                                   # marked stale
    assert prior["SupersededByExternalID"] == h2.prediction_request_external_id
    assert prior["Predictions"] is not None                           # preserved, not deleted

    r2 = rt.collect(h2)
    assert r2.persisted
    assert r2.prediction_result_external_id != r1.prediction_result_external_id
    assert repo.get("PredictionResult", r2.prediction_result_external_id)["IsStale"] is False
    assert len(repo.query("PredictionResult")) == 2                   # both versions preserved
