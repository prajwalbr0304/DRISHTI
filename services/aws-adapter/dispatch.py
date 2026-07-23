"""Model-backend dispatch for the protected AWS adapter (Part F, items 3+5).

Topology (F.3):

    Catalyst AppSail --(signed HTTPS)--> AWS API Gateway --> THIS adapter
        --> SageMaker (async / real-time) | AWS Batch | Batch Transform
        --> (only where necessary) read-only PostGIS/pgRouting analytics RDS

The adapter never runs a model itself and holds no GPU stack; it authenticates,
chooses the right backend for the requested ``dispatch_mode``, applies
idempotency, retry-with-jitter and a circuit breaker, and returns a signed result
the AppSail client verifies.

Two implementations (mirrors the app's fake/real split):
  * ``FakeDispatcher`` — deterministic, offline, no AWS. TabFM fails CLOSED when
    no real GPU endpoint is configured, so a fallback is never mislabelled as
    TabFM. Used by local runs / verification.
  * ``AwsDispatcher`` — the deployed router using boto3 execution-role creds
    (never static keys). boto3 is imported lazily so this module stays importable
    without it.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Callable, Optional

from circuit import CircuitBreaker, CircuitOpenError
from schema import RoutingView


class DispatchError(RuntimeError):
    """Transport/backend failure (never carries a secret or request body)."""


class BackendUnavailable(DispatchError):
    """Requested backend cannot run as requested (fail-closed, e.g. no GPU)."""


def _retry_with_jitter(fn: Callable[[], object], *, attempts: int, base: float = 0.2,
                       cap: float = 8.0, sleep: Callable[[float], None] = time.sleep):
    """Run ``fn`` with bounded exponential backoff + full jitter."""
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1:
                delay = min(cap, base * (2 ** i)) * (0.5 + 0.5 * (uuid.uuid4().int % 100) / 100)
                sleep(delay)
    raise DispatchError("backend call failed after retries") from last


class IdempotencyStore:
    """Maps idempotency_key -> request_id (+ cached result) with a TTL.

    Deployment note: back this with DynamoDB (conditional put on the key) so the
    same logical request is dispatched exactly once across adapter instances.
    """

    def __init__(self, ttl_s: int = 86_400, time_fn: Callable[[], float] = time.time) -> None:
        self._ttl = ttl_s
        self._now = time_fn
        self._lock = threading.Lock()
        self._by_key: dict[str, tuple[str, float]] = {}          # idem -> (request_id, exp)
        self._results: dict[str, dict] = {}                      # request_id -> unsigned result

    def existing(self, idem: str) -> Optional[str]:
        now = self._now()
        with self._lock:
            hit = self._by_key.get(idem)
            if hit and hit[1] >= now:
                return hit[0]
            if hit:
                self._by_key.pop(idem, None)
            return None

    def remember(self, idem: str, request_id: str) -> None:
        with self._lock:
            self._by_key[idem] = (request_id, self._now() + self._ttl)

    def put_result(self, request_id: str, result: dict) -> None:
        with self._lock:
            self._results[request_id] = result

    def get_result(self, request_id: str) -> Optional[dict]:
        with self._lock:
            return self._results.get(request_id)


class ModelDispatcher(ABC):
    """Narrow interface: dispatch a validated request, poll for its result."""

    @abstractmethod
    def dispatch(self, body: dict, view: RoutingView) -> str: ...

    @abstractmethod
    def poll(self, request_id: str) -> dict: ...


def _result(view: RoutingView, *, state: str, **extra) -> dict:
    """Build an UNSIGNED result-envelope dict (handler signs it)."""
    base = {
        "envelope_version": "1.0.0",
        "request_id": view.request_id,
        "idempotency_key": view.idempotency_key,
        "task": view.task,
        "state": state,
    }
    base.update(extra)
    return base


class FakeDispatcher(ModelDispatcher):
    """Offline deterministic dispatcher. No AWS, no GPU.

    * TabFM -> FAILS CLOSED (state=failed, CUDA_UNAVAILABLE) because there is no
      real GPU endpoint here; a fallback must never masquerade as TabFM.
    * Other backends -> a deterministic aggregate result on CPU.
    """

    def __init__(self) -> None:
        self._store = IdempotencyStore()

    def dispatch(self, body: dict, view: RoutingView) -> str:
        prior = self._store.existing(view.idempotency_key)
        if prior:
            return prior  # idempotent: same key -> same request
        if view.requested_backend == "tabfm":
            result = _result(
                view, state="failed", error_code="CUDA_UNAVAILABLE",
                error_detail="Real TabFM needs CUDA + licensed weights; the offline "
                             "adapter fails closed instead of returning a fallback.",
                warnings=["offline fake dispatcher"])
        else:
            preds = [{"row": i, "band_probabilities": [0.55, 0.25, 0.15, 0.05],
                      "workload_band": "moderate", "band_ordinal": 1}
                     for i in range(max(view.n_query_rows, 1))]
            result = _result(
                view, state="completed", actual_backend=view.requested_backend,
                actual_device="cpu", model_artifact_digest="fake-deterministic",
                predictions=preds, confidence=0.55, abstained=False, runtime_ms=1,
                warnings=["offline fake dispatcher"])
        self._store.remember(view.idempotency_key, view.request_id)
        self._store.put_result(view.request_id, result)
        return view.request_id

    def poll(self, request_id: str) -> dict:
        res = self._store.get_result(request_id)
        if res is None:
            raise DispatchError(f"unknown request_id {request_id}")
        return res


class AwsDispatcher(ModelDispatcher):
    """Deployed router to SageMaker / AWS Batch using execution-role credentials.

    Configuration comes from the Lambda/ECS environment (never static keys):
      * DRISHTI_SM_REALTIME_ENDPOINT  — SageMaker real-time endpoint name
      * DRISHTI_SM_ASYNC_ENDPOINT     — SageMaker async endpoint name
      * DRISHTI_BATCH_JOB_QUEUE       — AWS Batch job queue ARN/name
      * DRISHTI_BATCH_JOB_DEFINITION  — AWS Batch job definition ARN/name
      * DRISHTI_ADAPTER_S3_STAGING    — s3://bucket/prefix for async/batch I/O
      * AWS_REGION                    — region (default ap-south-1)

    boto3 is imported lazily; a downstream circuit breaker + retry-with-jitter
    wrap every AWS call. Idempotency dedups by ``idempotency_key``.
    """

    def __init__(self, *, region: Optional[str] = None,
                 breaker: Optional[CircuitBreaker] = None) -> None:
        self.region = region or os.getenv("AWS_REGION", "ap-south-1")
        self.realtime_endpoint = os.getenv("DRISHTI_SM_REALTIME_ENDPOINT", "")
        self.async_endpoint = os.getenv("DRISHTI_SM_ASYNC_ENDPOINT", "")
        self.batch_queue = os.getenv("DRISHTI_BATCH_JOB_QUEUE", "")
        self.batch_def = os.getenv("DRISHTI_BATCH_JOB_DEFINITION", "")
        self.s3_staging = os.getenv("DRISHTI_ADAPTER_S3_STAGING", "")
        self._store = IdempotencyStore()
        self._jobs: dict[str, dict] = {}          # request_id -> {mode, ...backend refs}
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=int(os.getenv("DRISHTI_ADAPTER_CB_FAILURES", "5")),
            reset_timeout_s=float(os.getenv("DRISHTI_ADAPTER_CB_RESET_S", "30")),
            name="model-plane")
        self._boto = None

    # -- lazy boto3 ----------------------------------------------------------
    def _clients(self):
        if self._boto is None:
            import boto3  # deferred: module stays importable without boto3
            self._boto = {
                "smr": boto3.client("sagemaker-runtime", region_name=self.region),
                "sm": boto3.client("sagemaker", region_name=self.region),
                "batch": boto3.client("batch", region_name=self.region),
                "s3": boto3.client("s3", region_name=self.region),
            }
        return self._boto

    def _guarded(self, fn: Callable[[], object]):
        """Run a downstream call through the circuit breaker + retry-with-jitter."""
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            raise DispatchError(f"model plane circuit open: {exc}") from None
        try:
            out = _retry_with_jitter(fn, attempts=3)
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return out

    # -- stateless persistence (Lambda-safe): job + idempotency in S3 --------
    # A Lambda adapter is stateless across invocations, so dispatch() and poll()
    # run in different processes. Persist the async job mapping + idempotency map
    # to the encrypted S3 staging prefix so poll() and duplicate dispatch() work
    # correctly across invocations (the in-memory store is a warm-instance cache).
    def _s3_put_json(self, key: str, obj: dict) -> None:
        import json
        bucket, prefix = _split_s3(self.s3_staging)
        self._clients()["s3"].put_object(
            Bucket=bucket, Key=f"{prefix}/{key}",
            Body=json.dumps(obj).encode("utf-8"), ServerSideEncryption="aws:kms")

    def _s3_get_json(self, key: str) -> Optional[dict]:
        import json
        bucket, prefix = _split_s3(self.s3_staging)
        try:
            obj = self._clients()["s3"].get_object(Bucket=bucket, Key=f"{prefix}/{key}")
            return json.loads(obj["Body"].read())
        except Exception:  # noqa: BLE001 — treat any miss as "not found"
            return None

    @staticmethod
    def _idem_hash(idem: str) -> str:
        return hashlib.sha256(idem.encode("utf-8")).hexdigest()

    def _persist_idem(self, idem: str, request_id: str) -> None:
        try:
            self._s3_put_json(f"idem/{self._idem_hash(idem)}.json", {"request_id": request_id})
        except Exception:  # noqa: BLE001 — persistence is best-effort defence in depth
            pass

    def _lookup_idem(self, idem: str) -> Optional[str]:
        rec = self._s3_get_json(f"idem/{self._idem_hash(idem)}.json")
        return rec.get("request_id") if rec else None

    def _persist_job(self, request_id: str, job: dict) -> None:
        try:
            self._s3_put_json(f"jobs/{request_id}.json", job)
        except Exception:  # noqa: BLE001
            pass

    def _load_job(self, request_id: str) -> Optional[dict]:
        return self._jobs.get(request_id) or self._s3_get_json(f"jobs/{request_id}.json")

    # -- dispatch ------------------------------------------------------------
    def dispatch(self, body: dict, view: RoutingView) -> str:
        # Idempotency: warm-instance cache first, then the durable S3 map. The
        # same idempotency_key always resolves to one logical request/result.
        prior = self._store.existing(view.idempotency_key) or self._lookup_idem(
            view.idempotency_key)
        if prior:
            return prior
        if view.requested_backend == "tabfm" and not (
                self.realtime_endpoint or self.async_endpoint or self.batch_queue):
            raise BackendUnavailable("TabFM requested but no GPU endpoint/queue configured")

        if view.is_realtime:
            request_id = self._dispatch_realtime(body, view)
        elif view.is_async:
            request_id = self._dispatch_async(body, view)
        else:
            request_id = self._dispatch_batch(body, view)
        self._store.remember(view.idempotency_key, request_id)
        self._persist_idem(view.idempotency_key, request_id)
        return request_id

    def _dispatch_realtime(self, body: dict, view: RoutingView) -> str:
        import json
        clients = self._clients()
        resp = self._guarded(lambda: clients["smr"].invoke_endpoint(
            EndpointName=self.realtime_endpoint, ContentType="application/json",
            Body=json.dumps(body).encode("utf-8")))
        payload = resp["Body"].read()
        result = json.loads(payload)
        self._store.put_result(view.request_id, result)
        self._persist_job(view.request_id, {"mode": "result", "result": result})
        return view.request_id

    def _dispatch_async(self, body: dict, view: RoutingView) -> str:
        import json
        clients = self._clients()
        bucket, prefix = _split_s3(self.s3_staging)
        in_key = f"{prefix}/in/{view.request_id}.json"
        self._guarded(lambda: clients["s3"].put_object(
            Bucket=bucket, Key=in_key, Body=json.dumps(body).encode("utf-8"),
            ServerSideEncryption="aws:kms"))
        resp = self._guarded(lambda: clients["smr"].invoke_endpoint_async(
            EndpointName=self.async_endpoint, ContentType="application/json",
            InputLocation=f"s3://{bucket}/{in_key}"))
        job = {"mode": "sagemaker_async", "output": resp.get("OutputLocation", ""),
               "failure": resp.get("FailureLocation", ""),
               "task": view.task, "idempotency_key": view.idempotency_key}
        self._jobs[view.request_id] = job
        self._persist_job(view.request_id, job)
        return view.request_id

    def _dispatch_batch(self, body: dict, view: RoutingView) -> str:
        import json
        clients = self._clients()
        bucket, prefix = _split_s3(self.s3_staging)
        in_key = f"{prefix}/in/{view.request_id}.json"
        out_key = f"{prefix}/out/{view.request_id}.json"
        self._guarded(lambda: clients["s3"].put_object(
            Bucket=bucket, Key=in_key, Body=json.dumps(body).encode("utf-8"),
            ServerSideEncryption="aws:kms"))
        resp = self._guarded(lambda: clients["batch"].submit_job(
            jobName=f"drishti-{view.task}-{view.request_id}"[:120],
            jobQueue=self.batch_queue, jobDefinition=self.batch_def,
            containerOverrides={"environment": [
                {"name": "DRISHTI_INPUT_S3", "value": f"s3://{bucket}/{in_key}"},
                {"name": "DRISHTI_OUTPUT_S3", "value": f"s3://{bucket}/{out_key}"},
            ]},
            timeout={"attemptDurationSeconds": max(60, view.timeout_s)}))
        job = {"mode": "aws_batch", "job_id": resp.get("jobId", ""),
               "out": f"s3://{bucket}/{out_key}",
               "task": view.task, "idempotency_key": view.idempotency_key}
        self._jobs[view.request_id] = job
        self._persist_job(view.request_id, job)
        return view.request_id

    # -- poll ----------------------------------------------------------------
    def poll(self, request_id: str) -> dict:
        import json
        cached = self._store.get_result(request_id)
        if cached is not None:
            return cached
        job = self._load_job(request_id)
        if job is None:
            raise DispatchError(f"unknown request_id {request_id}")
        clients = self._clients()
        if job.get("mode") == "result":              # realtime / cached completed result
            return job["result"]
        if job["mode"] == "sagemaker_async":
            bucket, key = _split_s3(job["output"])
            try:
                obj = clients["s3"].get_object(Bucket=bucket, Key=key)
            except Exception as exc:  # noqa: BLE001
                if _is_not_found(exc):
                    return _running(request_id, job)  # output not written yet -> still running
                raise DispatchError("async output read failed") from exc
            result = json.loads(obj["Body"].read())
            self._store.put_result(request_id, result)
            self._persist_job(request_id, {"mode": "result", "result": result})
            return result
        # aws_batch: check job state; return running until the output object exists.
        desc = self._guarded(lambda: clients["batch"].describe_jobs(jobs=[job["job_id"]]))
        status = (desc.get("jobs") or [{}])[0].get("status", "SUBMITTED")
        if status in ("SUCCEEDED",):
            bucket, key = _split_s3(job["out"])
            obj = self._guarded(lambda: clients["s3"].get_object(Bucket=bucket, Key=key))
            result = json.loads(obj["Body"].read())
            self._store.put_result(request_id, result)
            return result
        if status in ("FAILED",):
            out = _running(request_id, job)
            out.update({"state": "failed", "error_code": "BATCH_FAILED",
                        "error_detail": "AWS Batch job failed"})
            return out
        return _running(request_id, job)


def _split_s3(uri: str) -> tuple[str, str]:
    """Split an ``s3://bucket/key`` URI. Raises if the staging URI is unset."""
    if not uri.startswith("s3://"):
        raise DispatchError("S3 staging location not configured")
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    return bucket, key.strip("/")


def _is_not_found(exc: Exception) -> bool:
    """True if an S3 get looks like a missing key (async output not written yet)."""
    s = str(exc)
    return any(m in s for m in ("NoSuchKey", "Not Found", "404", "does not exist"))


def _running(request_id: str, job: Optional[dict] = None) -> dict:
    """A 'still running' result envelope for an async poll before the output lands.
    Carries the real task + idempotency_key from the stored job so the AppSail
    client can parse it as a valid (non-terminal) PredictionResultEnvelope."""
    job = job or {}
    return {"envelope_version": "1.0.0", "request_id": request_id,
            "idempotency_key": job.get("idempotency_key", ""),
            "task": job.get("task") or "station_workload_band", "state": "running"}


def get_dispatcher() -> ModelDispatcher:
    """Factory: the real AWS router when a backend is configured, else the fake."""
    if os.getenv("DRISHTI_SM_REALTIME_ENDPOINT") or os.getenv("DRISHTI_SM_ASYNC_ENDPOINT") \
            or os.getenv("DRISHTI_BATCH_JOB_QUEUE"):
        return AwsDispatcher()
    return FakeDispatcher()
