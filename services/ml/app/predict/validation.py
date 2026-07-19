"""Fail-closed validation of an AWS model result before it is trusted (Prompt 14 G).

The AWS custom-model plane is external and untrusted until proven: the result
envelope is signature-verified by ``adapter.SignedHttpsAdapter._verify`` on the
wire, and THIS module then validates its *content* before it is allowed to
become a ``PredictionResult`` in Data Store. Every check fails closed:

  * the result must bind to the request (request_id / idempotency_key / task);
  * the job must have actually COMPLETED (a failed/timed-out job is rejected with
    its error code — never persisted as a success);
  * the backend must be AUTHENTIC — a ``tabfm`` request must come back as
    ``tabfm`` on ``cuda`` (a fallback mislabelled as TabFM is rejected);
  * a GPU backend must report its model-artifact digest, and the feature-schema
    digest must match the request;
  * for a row-wise task the prediction count must equal the query-row count.

Validation is expressed against a small ``ResultExpectation`` so it can run both
from the live request envelope (synchronous path) and from the persisted
``PredictionRequest`` Data Store row (async collect path) without needing the
whole envelope re-hydrated.
"""
from __future__ import annotations

from dataclasses import dataclass

from .envelope import (BackendKind, DeviceKind, JobState, ModelTask,
                       PredictionRequestEnvelope, PredictionResultEnvelope)

# Tasks whose result is exactly one prediction row per query row.
_ROW_WISE_TASKS: frozenset[str] = frozenset({
    ModelTask.STATION_WORKLOAD_BAND.value,
    ModelTask.AREA_INCIDENT_FORECAST_TABFM.value,
})
# Backends that must run on a GPU and therefore report a model-artifact digest.
_GPU_BACKENDS: frozenset[str] = frozenset({
    BackendKind.TABFM.value, BackendKind.TIMESFM.value, BackendKind.STGNN.value,
})


class ResultRejected(ValueError):
    """Raised when a result fails validation. The message is safe to log (no PII)."""


@dataclass(frozen=True)
class ResultExpectation:
    """What a valid result for a request must satisfy."""
    request_id: str
    idempotency_key: str
    task: str
    requested_backend: str
    feature_schema_digest: str = ""
    n_query_rows: int = 0
    envelope_version: str = ""

    @property
    def row_wise(self) -> bool:
        return self.task in _ROW_WISE_TASKS

    @classmethod
    def from_envelope(cls, env: PredictionRequestEnvelope) -> "ResultExpectation":
        return cls(
            request_id=env.request_id, idempotency_key=env.idempotency_key,
            task=env.task.value if isinstance(env.task, ModelTask) else str(env.task),
            requested_backend=(env.requested_backend.value
                               if isinstance(env.requested_backend, BackendKind)
                               else str(env.requested_backend)),
            feature_schema_digest=env.feature_schema_digest or "",
            n_query_rows=len(env.query_rows), envelope_version=env.envelope_version)

    @classmethod
    def from_request_row(cls, row: dict) -> "ResultExpectation":
        """Rebuild the expectation from a persisted PredictionRequest Data Store row."""
        return cls(
            request_id=str(row.get("RequestID") or row.get("request_id") or ""),
            idempotency_key=str(row.get("IdempotencyKey") or row.get("idempotency_key") or ""),
            task=str(row.get("Task") or row.get("task") or ""),
            requested_backend=str(row.get("RequestedBackend") or row.get("requested_backend") or ""),
            feature_schema_digest=str(row.get("FeatureSchemaDigest")
                                      or row.get("feature_schema_digest") or ""),
            n_query_rows=int(row.get("QueryRowCount") or row.get("n_query_rows") or 0),
            envelope_version=str(row.get("EnvelopeVersion") or row.get("envelope_version") or ""))


def validate_result(expect: ResultExpectation,
                    res: PredictionResultEnvelope) -> PredictionResultEnvelope:
    """Validate a result against its expectation. Returns the result on success;
    raises ``ResultRejected`` (fail-closed) otherwise."""
    # 1. envelope version parity (both sides carry it on the wire).
    if expect.envelope_version and res.envelope_version \
            and res.envelope_version != expect.envelope_version:
        raise ResultRejected(
            f"envelope version {res.envelope_version!r} != expected {expect.envelope_version!r}")

    # 2. request binding.
    if res.request_id != expect.request_id:
        raise ResultRejected("result request_id does not match the request")
    if res.idempotency_key != expect.idempotency_key:
        raise ResultRejected("result idempotency_key does not match the request")
    res_task = res.task.value if isinstance(res.task, ModelTask) else str(res.task)
    if res_task != expect.task:
        raise ResultRejected(f"result task {res_task!r} != expected {expect.task!r}")

    # 3. the job must have COMPLETED (else reject with the reported error code).
    if res.state != JobState.COMPLETED:
        code = res.error_code or res.state.value
        raise ResultRejected(f"job not completed ({code}): {res.error_detail or 'no detail'}")

    # 4. backend authenticity — fail-closed, TabFM cannot be a mislabelled fallback.
    requested = BackendKind(expect.requested_backend)
    if not res.is_authentic_backend(requested):
        actual = res.actual_backend.value if res.actual_backend else "none"
        raise ResultRejected(
            f"backend not authentic: requested {requested.value!r}, ran {actual!r}")
    if requested == BackendKind.TABFM and res.actual_device != DeviceKind.CUDA:
        dev = res.actual_device.value if res.actual_device else "none"
        raise ResultRejected(f"TabFM must run on cuda, ran on {dev!r}")

    # 5. GPU backends must report a model-artifact digest; feature-schema digest must match.
    if expect.requested_backend in _GPU_BACKENDS and not res.model_artifact_digest:
        raise ResultRejected("GPU backend result missing model_artifact_digest")
    if expect.feature_schema_digest and res.feature_schema_digest \
            and res.feature_schema_digest != expect.feature_schema_digest:
        raise ResultRejected("feature-schema digest mismatch (stale/incompatible snapshot)")

    # 6. shape: a row-wise task returns exactly one prediction per query row.
    if expect.row_wise and expect.n_query_rows \
            and len(res.predictions) != expect.n_query_rows:
        raise ResultRejected(
            f"row-wise task returned {len(res.predictions)} predictions for "
            f"{expect.n_query_rows} query rows")

    return res
