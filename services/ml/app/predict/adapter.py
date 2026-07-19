"""Protected AWS model-adapter client (Prompt 14 F + G).

The AppSail service reaches the external AWS custom-model plane ONLY through this
narrow interface:

    Catalyst AppSail -> HTTPS AWS API Gateway -> Lambda/ECS adapter -> SageMaker/Batch

Security posture (F.4/F.5):
  * short-lived SIGNED service requests with timestamp + nonce replay protection
    (an API key alone is NOT authentication);
  * TLS, bounded timeout, retry-with-jitter, circuit-breaking and idempotency;
  * the response envelope signature is verified before the result is trusted;
  * NO DATABASE_URL / evidence bytes / narratives ever leave through here.

Two implementations:
  * ``InMemoryFakeAdapter`` — deterministic, offline, used by unit tests and local
    runs. It FAILS CLOSED for a real-TabFM request (no CUDA/weights locally) so a
    fallback can never be mislabelled as TabFM.
  * ``SignedHttpsAdapter`` — the deployed client that signs requests to the AWS
    API Gateway URL configured server-side on AppSail.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

from .circuit import CircuitBreaker, CircuitOpenError
from .envelope import (BackendKind, DeviceKind, JobState,
                       PredictionRequestEnvelope, PredictionResultEnvelope)


class AdapterError(RuntimeError):
    """Raised for transport/signature/timeout failures (never leaks secrets)."""


class AwsModelAdapter(ABC):
    """Narrow interface so local tests use a fake and deployment uses HTTPS."""

    @abstractmethod
    def dispatch(self, env: PredictionRequestEnvelope) -> str:
        """Submit a job. Returns an adapter job id. Idempotent by idempotency_key."""

    @abstractmethod
    def poll(self, request_id: str) -> PredictionResultEnvelope:
        """Fetch current job state / result envelope."""


def _canonical(env_dict: dict) -> bytes:
    """Stable canonical JSON for signing (sorted keys, no whitespace drift)."""
    return json.dumps(env_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(secret: str, payload: bytes, ts: str, nonce: str) -> str:
    """HMAC-SHA256 over ts|nonce|payload. Same routine both sides use."""
    mac = hmac.new(secret.encode("utf-8"), b"|".join((ts.encode(), nonce.encode(), payload)),
                   hashlib.sha256)
    return mac.hexdigest()


class InMemoryFakeAdapter(AwsModelAdapter):
    """Offline deterministic adapter for tests and local development.

    * Non-TabFM tasks return a deterministic aggregate result on CPU.
    * A ``tabfm`` request FAILS CLOSED (state=failed, error_code=CUDA_UNAVAILABLE)
      unless ``allow_fake_tabfm=True`` is explicitly set for a unit test — the
      real device is never faked as cuda.
    """

    def __init__(self, allow_fake_tabfm: bool = False):
        self._jobs: dict[str, PredictionResultEnvelope] = {}
        self._allow_fake_tabfm = allow_fake_tabfm

    def dispatch(self, env: PredictionRequestEnvelope) -> str:
        env.validate_shapes()
        # Idempotency: same key -> same job.
        for r in self._jobs.values():
            if r.idempotency_key == env.idempotency_key:
                return r.request_id

        if env.requested_backend == BackendKind.TABFM and not self._allow_fake_tabfm:
            self._jobs[env.request_id] = PredictionResultEnvelope(
                request_id=env.request_id, idempotency_key=env.idempotency_key,
                task=env.task, state=JobState.FAILED,
                error_code="CUDA_UNAVAILABLE",
                error_detail="Real TabFM requires CUDA + licensed weights; not available in the "
                             "local/fake adapter. Fail closed rather than return a fallback.",
                warnings=["A separately named fallback request may be run explicitly."])
            return env.request_id

        n = len(env.query_rows)
        preds = [{"row": i, "band_probabilities": [0.55, 0.25, 0.15, 0.05],
                  "workload_band": "moderate", "band_ordinal": 1} for i in range(n)]
        backend = env.requested_backend if env.requested_backend != BackendKind.TABFM \
            else BackendKind.INCONTEXT
        self._jobs[env.request_id] = PredictionResultEnvelope(
            request_id=env.request_id, idempotency_key=env.idempotency_key, task=env.task,
            state=JobState.COMPLETED, actual_backend=backend, actual_device=DeviceKind.CPU,
            model_artifact_digest="fake-deterministic", feature_schema_digest=env.feature_schema_digest,
            predictions=preds, confidence=0.55, abstained=False, runtime_ms=1,
            warnings=["in-memory fake adapter"])
        return env.request_id

    def poll(self, request_id: str) -> PredictionResultEnvelope:
        if request_id not in self._jobs:
            raise AdapterError(f"unknown request_id {request_id}")
        return self._jobs[request_id]


class SignedHttpsAdapter(AwsModelAdapter):
    """Deployed client: signed HTTPS to the protected AWS API Gateway.

    Configuration comes from the AppSail server-side environment (never the
    browser, never committed):
      * DRISHTI_AWS_ADAPTER_URL   — HTTPS base URL of the AWS API Gateway.
      * DRISHTI_AWS_ADAPTER_SECRET — shared signing secret (or use Connections).
    """

    def __init__(self, base_url: Optional[str] = None, secret: Optional[str] = None,
                 timeout_s: float = 30.0, max_retries: int = 3,
                 breaker: Optional[CircuitBreaker] = None):
        self.base_url = (base_url or os.getenv("DRISHTI_AWS_ADAPTER_URL", "")).rstrip("/")
        self._secret = secret or os.getenv("DRISHTI_AWS_ADAPTER_SECRET", "")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        # F.5 circuit breaker: after repeated backend failures, fail fast for a
        # cooldown instead of hammering the AWS plane. Tunable server-side.
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=int(os.getenv("DRISHTI_AWS_ADAPTER_CB_FAILURES", "5")),
            reset_timeout_s=float(os.getenv("DRISHTI_AWS_ADAPTER_CB_RESET_S", "30")),
            name="aws-adapter")
        if not self.base_url or not self._secret:
            raise AdapterError("AWS adapter URL/secret not configured (server-side env).")

    @property
    def circuit(self) -> CircuitBreaker:
        """Expose the breaker for redacted health/observability reporting."""
        return self._breaker

    def _headers(self, payload: bytes) -> dict[str, str]:
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        return {
            "Content-Type": "application/json",
            "X-DRISHTI-Timestamp": ts,
            "X-DRISHTI-Nonce": nonce,
            "X-DRISHTI-Signature": sign_payload(self._secret, payload, ts, nonce),
            "X-DRISHTI-Envelope-Version": PredictionRequestEnvelope.model_fields[
                "envelope_version"].default,
        }

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        # Circuit breaker admission: fail fast if the AWS plane is unhealthy so a
        # single logical request (with its retry loop) never becomes a stampede.
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            raise AdapterError(f"AWS adapter circuit open: {exc}") from None
        try:
            data = self._request_with_retries(method, path, body)
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return data

    def _request_with_retries(self, method: str, path: str,
                              body: Optional[dict] = None) -> dict:
        import httpx  # local import: keep module importable without httpx
        payload = _canonical(body) if body is not None else b""
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    resp = client.request(method, f"{self.base_url}{path}",
                                          content=payload, headers=self._headers(payload))
                if resp.status_code >= 500:
                    raise AdapterError(f"AWS adapter {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # exponential backoff with jitter — but never sleep after the
                # final attempt (it would only delay the failure).
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 8)
                               * (0.5 + 0.5 * (uuid.uuid4().int % 100) / 100))
        raise AdapterError(
            f"AWS adapter unreachable after {self.max_retries} attempts") from last_exc

    def _verify(self, data: dict) -> PredictionResultEnvelope:
        sig = data.get("signature")
        signed_at = data.get("signed_at", "")
        nonce = data.get("_sig_nonce", "")
        unsigned = {k: v for k, v in data.items() if k not in ("signature", "_sig_nonce")}
        expected = sign_payload(self._secret, _canonical(unsigned), signed_at, nonce)
        if not sig or not hmac.compare_digest(sig, expected):
            raise AdapterError("AWS result signature verification failed")
        return PredictionResultEnvelope.model_validate(unsigned)

    def dispatch(self, env: PredictionRequestEnvelope) -> str:
        env.validate_shapes()
        data = self._request("POST", "/predict", env.model_dump())
        return data.get("request_id", env.request_id)

    def poll(self, request_id: str) -> PredictionResultEnvelope:
        data = self._request("GET", f"/predict/{request_id}")
        return self._verify(data)


def get_adapter() -> AwsModelAdapter:
    """Factory: HTTPS adapter when configured, else the offline fake."""
    if os.getenv("DRISHTI_AWS_ADAPTER_URL") and os.getenv("DRISHTI_AWS_ADAPTER_SECRET"):
        return SignedHttpsAdapter()
    return InMemoryFakeAdapter()
