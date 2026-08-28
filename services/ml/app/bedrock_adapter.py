"""Signed AppSail -> AWS adapter client for Bedrock Converse.

Catalyst AppSail normally crosses the existing protected adapter boundary for
semantic planning:

    AppSail -> signed HTTPS -> API Gateway -> Lambda role -> Amazon Bedrock

Only a data-minimised role-scoped schema/glossary, bounded chat history, and the
question are sent. The response is HMAC-signed and verified before it is parsed.
A dedicated least-privilege IAM user can provide direct failover; both paths are
fail-closed to the reviewed Chinese-origin Bedrock allow-list.
"""
from __future__ import annotations

import hmac
import os
import time
import uuid
from typing import Optional

from .config import is_approved_chinese_bedrock_model
from .predict.adapter import AdapterError, _canonical, sign_payload
from .predict.circuit import CircuitBreaker, CircuitOpenError
from .predict.envelope import ENVELOPE_VERSION

_MAX_RESPONSE_BYTES = 1_000_000
_MAX_SIGNATURE_SKEW_S = 300


class BedrockAdapterError(AdapterError):
    """A sanitized Bedrock adapter transport, validation, or signature error."""


def bedrock_adapter_configured() -> bool:
    """Whether the signed AWS boundary is available in this AppSail runtime."""
    return bool(os.getenv("DRISHTI_AWS_ADAPTER_URL", "").strip()
                and os.getenv("DRISHTI_AWS_ADAPTER_SECRET", "").strip())


def catalyst_runtime_detected() -> bool:
    """Detect AppSail/Catalyst so direct boto3 can never be enabled there."""
    markers = (
        "CATALYST_PROJECT_ID",
        "CATALYST_USER_ENVIRONMENT",
        "X_ZOHO_CATALYST_LISTEN_PORT",
    )
    return any(os.getenv(name, "").strip() for name in markers)


class SignedHttpsBedrockAdapter:
    """Invoke the adapter's narrow, Chinese-model-only Bedrock operation."""

    def __init__(self, base_url: Optional[str] = None, secret: Optional[str] = None,
                 timeout_s: float = 30.0, breaker: Optional[CircuitBreaker] = None):
        self.base_url = (base_url or os.getenv("DRISHTI_AWS_ADAPTER_URL", "")).rstrip("/")
        self._secret = secret or os.getenv("DRISHTI_AWS_ADAPTER_SECRET", "")
        self.timeout_s = timeout_s
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=int(os.getenv("DRISHTI_AWS_ADAPTER_CB_FAILURES", "5")),
            reset_timeout_s=float(os.getenv("DRISHTI_AWS_ADAPTER_CB_RESET_S", "30")),
            name="aws-bedrock-adapter",
        )
        if not self.base_url or not self._secret:
            raise BedrockAdapterError("AWS Bedrock adapter is not configured.")

    def converse(self, *, model_id: str, system: list[dict], messages: list[dict],
                 inference_config: Optional[dict] = None) -> str:
        if not is_approved_chinese_bedrock_model(model_id):
            raise BedrockAdapterError("Bedrock model is not in the Chinese-model allow-list.")
        request_id = uuid.uuid4().hex
        body = {
            "request_id": request_id,
            "model_id": model_id.strip().lower(),
            "system": system,
            "messages": messages,
            # Keep NL->SQL deterministic. The AWS boundary independently forces
            # this value and refuses unsupported parameters.
            "inference_config": {"temperature": 0, **(inference_config or {})},
        }
        data = self._call(body)
        if data.get("request_id") != request_id:
            raise BedrockAdapterError(
                "AWS Bedrock adapter response is not bound to this request.")
        if data.get("model_id") != body["model_id"]:
            raise BedrockAdapterError("Bedrock adapter returned an unexpected model identity.")
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise BedrockAdapterError("Bedrock adapter returned no text content.")
        return content.strip()

    def _call(self, body: dict) -> dict:
        payload = _canonical(body)
        ts, nonce = str(int(time.time())), uuid.uuid4().hex
        headers = {
            "Content-Type": "application/json",
            "X-DRISHTI-Timestamp": ts,
            "X-DRISHTI-Nonce": nonce,
            "X-DRISHTI-Signature": sign_payload(self._secret, payload, ts, nonce),
            "X-DRISHTI-Envelope-Version": ENVELOPE_VERSION,
        }
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            raise BedrockAdapterError(f"AWS Bedrock adapter circuit open: {exc}") from None

        try:
            import httpx

            with httpx.Client(timeout=self.timeout_s) as client:
                response = client.post(
                    f"{self.base_url}/bedrock/converse", content=payload, headers=headers)
            if response.status_code != 200:
                try:
                    code = str(response.json().get("error") or "adapter_error")
                except Exception:  # noqa: BLE001 - response may not be JSON
                    code = "adapter_error"
                raise BedrockAdapterError(
                    f"AWS Bedrock adapter rejected the request ({code}).")
            if len(response.content) > _MAX_RESPONSE_BYTES:
                raise BedrockAdapterError("AWS Bedrock adapter response exceeds the byte cap.")
            data = response.json()
            self._verify(data)
        except BedrockAdapterError:
            self._breaker.record_failure()
            raise
        except Exception as exc:  # noqa: BLE001 - sanitize transport details
            self._breaker.record_failure()
            raise BedrockAdapterError("AWS Bedrock adapter is unreachable.") from exc

        self._breaker.record_success()
        return {k: v for k, v in data.items()
                if k not in ("signature", "_sig_nonce", "signed_at")}

    def _verify(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise BedrockAdapterError("AWS Bedrock adapter returned an invalid response.")
        signature = data.get("signature")
        signed_at = str(data.get("signed_at") or "")
        nonce = str(data.get("_sig_nonce") or "")
        unsigned = {k: v for k, v in data.items()
                    if k not in ("signature", "_sig_nonce")}
        expected = sign_payload(self._secret, _canonical(unsigned), signed_at, nonce)
        if not signature or not hmac.compare_digest(str(signature), expected):
            raise BedrockAdapterError("AWS Bedrock adapter response signature is invalid.")
        try:
            age = abs(int(time.time()) - int(signed_at))
        except (TypeError, ValueError):
            raise BedrockAdapterError("AWS Bedrock adapter response timestamp is invalid.") from None
        if age > _MAX_SIGNATURE_SKEW_S:
            raise BedrockAdapterError("AWS Bedrock adapter response signature has expired.")
