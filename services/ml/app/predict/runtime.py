"""Prediction runtime orchestrator (Prompt 14 Part G prediction flow).

Implements the governed end-to-end flow, exactly as the spec draws it:

    validate input (routing gate)
      -> persist FeatureSnapshot + PredictionRequest in Data Store
      -> select dispatch mode (AWS Batch / SageMaker async|realtime)
      -> protected AWS adapter -> Batch / SageMaker
      -> validate result (fail-closed)
      -> PredictionResult in Data Store
      -> data-minimized Signal notice (Gateway polling OR the scoped SSE channel)

Design goals:
  * every dependency is injectable (adapter, Data Store repository, signal
    publisher) so the whole flow is unit-testable offline with fakes;
  * the AWS runtime NEVER writes to the browser and never becomes authoritative —
    Data Store is the system of record; the SSE/poll notice is ids + a template
    name only (never scores, narratives, evidence or PII);
  * a draft / submission / raw-upload event is refused by the routing gate before
    anything is persisted or dispatched (no model call);
  * a ``tabfm`` job that comes back as a fallback is rejected by ``validate_result``
    and NO ``PredictionResult`` is written (fail-closed).

Governance guarantees (G.4), even for the hackathon:
  * a new FIR is an INFERENCE input only — it never retrains TabFM; training and
    inference are separate paths (there is no training path in this runtime);
  * a correction creates a NEW version (new source-version hash -> new snapshot /
    request / result) and marks the prior result STALE, preserved not deleted, so
    historical predictions remain; the corrected submit is the controlled rerun;
  * duplicate events do not create duplicate GPU jobs (idempotency key -> the same
    request/result ExternalID + the adapter dedups);
  * every persisted request/result carries model, version, status and stale state
    for the UI to display.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol, Union

from ..datastore.repository import DataStoreRepository, get_repository
from .adapter import AwsModelAdapter, get_adapter
from .dispatch_policy import Purpose, select_dispatch_mode
from .enablement import is_task_enabled, task_reason
from .envelope import (ENVELOPE_VERSION, BackendKind, ColumnDef, DispatchMode,
                       JobState, ModelTask, PredictionRequestEnvelope,
                       PredictionResultEnvelope)
from .lineage import (FEATURE_SNAPSHOT_TABLE, PREDICTION_REQUEST_TABLE,
                      PREDICTION_RESULT_TABLE, PredictionLineage,
                      feature_snapshot_row, prediction_request_row,
                      prediction_result_row, subject_token)
from .routing import RoutingContext, build_idempotency_key, route
from .validation import ResultExpectation, ResultRejected, validate_result


class RuntimeRefused(RuntimeError):
    """Raised when the routing gate refuses to invoke a model (fail-safe)."""


# --- Signal publisher (data-minimized notices only) --------------------------
class SignalPublisher(Protocol):
    def publish(self, notice: dict) -> None: ...


class NullSignalPublisher:
    """Default: emit nothing (batch/offline jobs have no open UI stream)."""

    def publish(self, notice: dict) -> None:  # noqa: D401 - trivial
        return None


class InMemorySignalPublisher:
    """Test/offline publisher that records the data-minimized notices."""

    def __init__(self) -> None:
        self.notices: list[dict] = []

    def publish(self, notice: dict) -> None:
        self.notices.append(notice)


class ChannelSignalPublisher:
    """Deployed publisher: push the data-minimized notice to the scoped SSE
    channel for one (board, user). Import is deferred to avoid loading the
    FastAPI stream module unless a UI stream is actually in use."""

    def __init__(self, board_id: str, user_id: str) -> None:
        self._board_id = str(board_id)
        self._user_id = str(user_id)

    def publish(self, notice: dict) -> None:
        from ..stream.router import publish_to_channel
        publish_to_channel(self._board_id, self._user_id, notice)


# --- Job I/O -----------------------------------------------------------------
@dataclass
class PredictionJobInput:
    """Everything the runtime needs to submit ONE governed prediction job.

    The caller (a feature builder / Function / Job) supplies already-validated,
    pre-cutoff aggregate features — never raw narrative/evidence/PII.
    """
    routing_ctx: RoutingContext
    task: ModelTask
    requested_backend: BackendKind
    subject_kind: str
    subject_ids: list[str]
    columns: list[ColumnDef]
    query_rows: list[list[float]]
    feature_schema_version: str
    model_version: str
    feature_schema_digest: str
    observation_cutoff: str
    source_version_hash: str
    values: dict = field(default_factory=dict)          # FeatureSnapshot values
    purpose: Purpose = Purpose.OFFLINE_FORECAST
    context_x: Optional[list[list[float]]] = None
    context_y: Optional[list[int]] = None
    context_s3_uri: Optional[str] = None
    context_version: Optional[str] = None
    context_digest: Optional[str] = None
    model_artifact_digest: Optional[str] = None
    training_dataset_snapshot: Optional[str] = None
    output_schema: dict = field(default_factory=dict)
    latency_slo_ms: Optional[int] = None
    realtime_benchmarked: bool = False
    timeout_s: int = 900


@dataclass
class PredictionJobHandle:
    request_id: str
    idempotency_key: str
    state: str
    dispatch_mode: str
    reason: str
    feature_snapshot_external_id: str
    prediction_request_external_id: str
    superseded_prior: int = 0        # prior live results marked stale by this submit (G.4)

    def as_dict(self) -> dict:
        return {"request_id": self.request_id, "idempotency_key": self.idempotency_key,
                "state": self.state, "dispatch_mode": self.dispatch_mode,
                "reason": self.reason,
                "feature_snapshot_external_id": self.feature_snapshot_external_id,
                "prediction_request_external_id": self.prediction_request_external_id,
                "superseded_prior": self.superseded_prior}


@dataclass
class PredictionJobResult:
    request_id: str
    state: str
    persisted: bool
    result: Optional[PredictionResultEnvelope] = None
    prediction_result_external_id: Optional[str] = None
    rejected_reason: Optional[str] = None
    notice: Optional[dict] = None

    def as_dict(self) -> dict:
        return {"request_id": self.request_id, "state": self.state,
                "persisted": self.persisted,
                "prediction_result_external_id": self.prediction_result_external_id,
                "rejected_reason": self.rejected_reason, "notice": self.notice}


class PredictionRuntime:
    """Governed orchestrator around the protected AWS adapter + Data Store."""

    def __init__(self, adapter: Optional[AwsModelAdapter] = None,
                 repository: Optional[DataStoreRepository] = None, *,
                 signal_publisher: Optional[SignalPublisher] = None) -> None:
        self._adapter = adapter or get_adapter()
        self._repo = repository or get_repository()
        self._publisher = signal_publisher or NullSignalPublisher()

    # -- submit --------------------------------------------------------------
    def submit(self, job: PredictionJobInput) -> PredictionJobHandle:
        """Gate -> persist request -> select dispatch mode -> dispatch to AWS."""
        # 1. routing gate — a draft/submission/raw-upload event never gets here.
        decision = route(job.routing_ctx)
        if not decision.invokes_model:
            raise RuntimeRefused(f"routing refused: {decision.reason}")
        # 1b. demo enablement gate (G.2) — a deferred/optional-off model is refused
        #     with a crisp reason before any persistence or dispatch.
        if not is_task_enabled(job.task):
            raise RuntimeRefused(
                f"task {job.task.value!r} is deferred/not enabled for the demo: "
                f"{task_reason(job.task)}")
        if job.task not in decision.tasks:
            raise RuntimeRefused(
                f"task {job.task.value!r} is not routed for event "
                f"{job.routing_ctx.event.value!r}: {decision.reason}")

        # 2. idempotency key + a fresh request id.
        subject = subject_token(job.subject_kind, list(job.subject_ids))
        idem = build_idempotency_key(job.task, subject, job.observation_cutoff,
                                     job.feature_schema_version, job.model_version,
                                     job.source_version_hash)
        request_id = uuid.uuid4().hex

        # 3. choose the AWS dispatch mode (Batch preferred; async for measured NRT;
        #    real-time only if benchmarked; GPU never serverless).
        decision_mode = select_dispatch_mode(
            task=job.task.value, backend=job.requested_backend.value, purpose=job.purpose,
            latency_slo_ms=job.latency_slo_ms, realtime_benchmarked=job.realtime_benchmarked)

        # 4. build + shape-validate the envelope BEFORE persisting anything.
        env = self._build_envelope(job, request_id, idem, decision_mode.mode)
        env.validate_shapes()

        # 5. persist the immutable FeatureSnapshot + governed PredictionRequest.
        lin = self._build_lineage(job, request_id, idem, decision_mode.mode)
        fs_ext = lin.feature_snapshot_external_id()
        self._repo.upsert(FEATURE_SNAPSHOT_TABLE, fs_ext,
                          feature_snapshot_row(lin, values=job.values or {}))
        pr_ext = lin.prediction_request_external_id()
        self._repo.upsert(PREDICTION_REQUEST_TABLE, pr_ext, prediction_request_row(
            lin, feature_snapshot_external_id=fs_ext, state="dispatched",
            n_query_rows=len(job.query_rows)))

        # 5b. correction supersession (G.4): a NEW source version for the same
        #     subject+schema marks prior live results stale (preserved, never
        #     deleted). An idempotent re-run (same source version) supersedes
        #     nothing and reuses the same request/result ExternalID.
        superseded = self._supersede_prior(lin, pr_ext)

        # 6. dispatch to the protected AWS adapter, then record the adapter id.
        #    This is an INFERENCE request only — a new FIR never retrains TabFM;
        #    training/inference are separate paths (there is no training here).
        adapter_request_id = self._adapter.dispatch(env)
        self._repo.upsert(PREDICTION_REQUEST_TABLE, pr_ext, prediction_request_row(
            lin, feature_snapshot_external_id=fs_ext, state="dispatched",
            n_query_rows=len(job.query_rows), adapter_request_id=adapter_request_id))

        return PredictionJobHandle(
            request_id=adapter_request_id or request_id, idempotency_key=idem,
            state="dispatched", dispatch_mode=decision_mode.mode.value,
            reason=decision_mode.reason, feature_snapshot_external_id=fs_ext,
            prediction_request_external_id=pr_ext, superseded_prior=superseded)

    # -- collect -------------------------------------------------------------
    def collect(self, handle: Union[PredictionJobHandle, str], *,
                prediction_request_external_id: Optional[str] = None) -> PredictionJobResult:
        """Poll the adapter, validate the result (fail-closed) and persist a
        PredictionResult on success. Accepts a handle (sync path) or a request_id
        + request ExternalID (async collect path)."""
        if isinstance(handle, PredictionJobHandle):
            request_id = handle.request_id
            pr_ext = handle.prediction_request_external_id
        else:
            request_id = str(handle)
            pr_ext = prediction_request_external_id or ""

        req_row = self._repo.get(PREDICTION_REQUEST_TABLE, pr_ext) if pr_ext else None
        if req_row is None:
            rows = self._repo.query(PREDICTION_REQUEST_TABLE,
                                    where={"RequestID": request_id}, limit=1)
            req_row = rows[0] if rows else None
        if req_row is None:
            raise RuntimeRefused(f"no PredictionRequest found for request {request_id!r}")
        pr_ext = pr_ext or str(req_row.get("ExternalID") or "")
        fs_ext = str(req_row.get("FeatureSnapshotExternalID") or "")
        expect = ResultExpectation.from_request_row(req_row)

        res = self._adapter.poll(request_id)

        # Not yet completed: reflect state; a terminal failure is marked, not persisted.
        if res.state != JobState.COMPLETED:
            if res.state in (JobState.FAILED, JobState.TIMED_OUT, JobState.CANCELLED):
                self._mark_request(req_row, "failed")
                return PredictionJobResult(
                    request_id=request_id, state=res.state.value, persisted=False,
                    result=res, rejected_reason=res.error_code or res.state.value)
            return PredictionJobResult(request_id=request_id, state=res.state.value,
                                       persisted=False, result=res)

        # Completed: validate before trusting. Fail-closed on any violation.
        try:
            validate_result(expect, res)
        except ResultRejected as exc:
            self._mark_request(req_row, "rejected")
            return PredictionJobResult(
                request_id=request_id, state="rejected", persisted=False, result=res,
                rejected_reason=str(exc))

        # Persist the VALIDATED result as a NEW Data Store record (AWS not authoritative).
        lin = self._lineage_from_request(req_row, res)
        res_ext = lin.prediction_result_external_id()
        self._repo.upsert(PREDICTION_RESULT_TABLE, res_ext, prediction_result_row(
            lin, res, request_external_id=pr_ext, feature_snapshot_external_id=fs_ext))
        self._mark_request(req_row, "completed")

        # Data-minimized notice for Gateway polling / the scoped SSE channel.
        notice = {
            "type": "prediction.result", "template": "prediction_ready",
            "task": lin.task, "subject_kind": lin.subject_kind,
            "subject_count": len(lin.subject_ids), "state": "completed",
            "prediction_request_external_id": pr_ext,
            "prediction_result_external_id": res_ext,
        }
        self._publisher.publish(notice)
        return PredictionJobResult(
            request_id=request_id, state="completed", persisted=True, result=res,
            prediction_result_external_id=res_ext, notice=notice)

    # -- helpers -------------------------------------------------------------
    def _build_envelope(self, job: PredictionJobInput, request_id: str, idem: str,
                        mode: DispatchMode) -> PredictionRequestEnvelope:
        return PredictionRequestEnvelope(
            request_id=request_id, idempotency_key=idem, task=job.task,
            requested_backend=job.requested_backend,
            feature_schema_version=job.feature_schema_version,
            model_version=job.model_version, context_version=job.context_version,
            feature_schema_digest=job.feature_schema_digest,
            context_digest=job.context_digest,
            model_artifact_digest=job.model_artifact_digest,
            subject_kind=job.subject_kind, subject_ids=[str(x) for x in job.subject_ids],
            observation_cutoff=job.observation_cutoff,
            source_version_hash=job.source_version_hash, columns=job.columns,
            context_x=job.context_x, context_y=job.context_y,
            context_s3_uri=job.context_s3_uri, query_rows=job.query_rows,
            output_schema=job.output_schema, dispatch_mode=mode, timeout_s=job.timeout_s)

    def _build_lineage(self, job: PredictionJobInput, request_id: str, idem: str,
                       mode: DispatchMode) -> PredictionLineage:
        return PredictionLineage(
            request_id=request_id, idempotency_key=idem, task=job.task.value,
            subject_kind=job.subject_kind,
            subject_ids=tuple(str(x) for x in job.subject_ids),
            feature_schema_version=job.feature_schema_version,
            feature_schema_digest=job.feature_schema_digest,
            model_version=job.model_version, observation_cutoff=job.observation_cutoff,
            source_version_hash=job.source_version_hash, dispatch_mode=mode.value,
            requested_backend=job.requested_backend.value,
            envelope_version=ENVELOPE_VERSION,
            model_artifact_digest=job.model_artifact_digest,
            context_version=job.context_version, context_digest=job.context_digest,
            training_dataset_snapshot=job.training_dataset_snapshot)

    def _lineage_from_request(self, req_row: dict,
                              res: PredictionResultEnvelope) -> PredictionLineage:
        prov = req_row.get("Provenance") or {}
        return PredictionLineage(
            request_id=str(req_row.get("RequestID") or ""),
            idempotency_key=str(req_row.get("IdempotencyKey") or ""),
            task=str(prov.get("task") or req_row.get("Task") or ""),
            subject_kind=str(prov.get("subject_kind") or "station"),
            subject_ids=tuple(str(x) for x in (prov.get("subject_ids") or [])),
            feature_schema_version=str(prov.get("feature_schema_version") or ""),
            feature_schema_digest=str(prov.get("feature_schema_digest")
                                      or req_row.get("FeatureSchemaDigest") or ""),
            model_version=str(prov.get("model_version") or req_row.get("ModelVersion") or ""),
            observation_cutoff=str(prov.get("observation_cutoff") or ""),
            source_version_hash=str(prov.get("source_version_hash") or ""),
            dispatch_mode=str(prov.get("dispatch_mode") or req_row.get("DispatchMode") or ""),
            requested_backend=str(prov.get("requested_backend")
                                  or req_row.get("RequestedBackend") or ""),
            envelope_version=str(req_row.get("EnvelopeVersion") or ENVELOPE_VERSION),
            model_artifact_digest=res.model_artifact_digest or prov.get("model_artifact_digest"),
            context_version=prov.get("context_version"),
            training_dataset_snapshot=prov.get("training_dataset_snapshot"),
            actual_backend=res.actual_backend.value if res.actual_backend else None,
            actual_device=res.actual_device.value if res.actual_device else None)

    def _mark_request(self, req_row: dict, state: str) -> None:
        ext = str(req_row.get("ExternalID") or "")
        if not ext:
            return
        row = dict(req_row)
        row["Status"] = state
        self._repo.upsert(PREDICTION_REQUEST_TABLE, ext, row)

    def _supersede_prior(self, lin: PredictionLineage, new_request_ext: str) -> int:
        """Mark prior LIVE results (+ their requests) for the same subject+schema
        but a DIFFERENT source version as stale/superseded — preserved, never
        deleted (G.4). Returns how many results were superseded.

        IsStale is filtered in Python (not in the ``where``) so it works the same
        across the in-memory fake and the Catalyst Data Store repository."""
        key = lin.supersession_key()
        superseded = 0
        for r in self._repo.query(PREDICTION_RESULT_TABLE, where={"SupersessionKey": key},
                                  limit=500):
            if r.get("IsStale"):
                continue
            if str(r.get("SourceVersionHash") or "") == lin.source_version_hash:
                continue  # same source version (idempotent re-run) — not superseded
            row = dict(r)
            row["IsStale"] = True
            row["StaleReason"] = "superseded by a newer/corrected input version"
            row["SupersededByExternalID"] = new_request_ext
            self._repo.upsert(PREDICTION_RESULT_TABLE, str(r.get("ExternalID") or ""), row)
            superseded += 1
        # Preserve prior requests too, marked superseded.
        for r in self._repo.query(PREDICTION_REQUEST_TABLE, where={"SupersessionKey": key},
                                  limit=500):
            ext = str(r.get("ExternalID") or "")
            if ext == new_request_ext or r.get("Status") == "superseded":
                continue
            if str(r.get("SourceVersionHash") or "") == lin.source_version_hash:
                continue
            row = dict(r)
            row["Status"] = "superseded"
            self._repo.upsert(PREDICTION_REQUEST_TABLE, ext, row)
        return superseded


def get_runtime(*, board_id: Optional[str] = None,
                user_id: Optional[str] = None) -> PredictionRuntime:
    """Factory: the deployed adapter + Data Store repository, with a channel
    publisher when a (board, user) is supplied (UI stream), else no notices."""
    publisher: SignalPublisher = (ChannelSignalPublisher(board_id, user_id)
                                  if board_id and user_id else NullSignalPublisher())
    return PredictionRuntime(signal_publisher=publisher)
