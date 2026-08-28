"""Protected AWS adapter entrypoint (Prompt 14 Part F, items 1,3,4,5).

Runs INSIDE the AWS VPC behind the AWS API Gateway. It is the only ingress from
Catalyst AppSail to the custom model plane:

    AppSail --(signed HTTPS)--> AWS API Gateway --> THIS adapter --> SageMaker/Batch

Security controls implemented here (F.4/F.5):
  * short-lived HMAC signature with timestamp + single-use nonce (replay + skew
    protection) — an API key alone is never accepted as authentication;
  * request-size cap + a defence-in-depth per-window rate limit (API Gateway
    throttling / WAF is the primary control);
  * bounded work, idempotency, downstream retry-with-jitter + circuit breaking
    (in ``dispatch.py``);
  * a signed result envelope the AppSail client verifies;
  * redacted structured audit logs — never a body, prediction, secret or PII;
  * fail-closed: any auth/validation failure returns an opaque error.

Two entrypoints (mirrors ``services/gpu-worker/handler.py``):
  * ``lambda_handler`` — AWS API Gateway (REST v1 or HTTP v2) proxy integration.
  * ``create_app``     — a Flask app for an ECS/Fargate deployment of the adapter.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from bedrock import (BedrockRequestError, BedrockUnavailable,
                      converse as bedrock_converse)
from dispatch import (BackendUnavailable, DispatchError, ModelDispatcher,
                      get_dispatcher)
from schema import EnvelopeError, MAX_ENVELOPE_BYTES, parse_and_validate
from signing import NonceCache, SignatureError, sign_result, verify_request


# ---------------------------------------------------------------------------
# Config + shared state
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdapterConfig:
    secret: str
    max_skew_s: int
    rate_limit_per_min: int
    max_body_bytes: int

    @classmethod
    def from_env(cls) -> "AdapterConfig":
        return cls(
            secret=os.getenv("DRISHTI_AWS_ADAPTER_SECRET", ""),
            max_skew_s=int(os.getenv("DRISHTI_ADAPTER_MAX_SKEW_S", "300")),
            rate_limit_per_min=int(os.getenv("DRISHTI_ADAPTER_RATE_PER_MIN", "600")),
            max_body_bytes=int(os.getenv("DRISHTI_ADAPTER_MAX_BODY_BYTES",
                                         str(MAX_ENVELOPE_BYTES))))


class _RateLimiter:
    """In-process fixed-window limiter (defence in depth). API Gateway usage
    plans / WAF are the primary rate control in front of the adapter."""

    def __init__(self, time_fn=time.time) -> None:
        self._now = time_fn
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}

    def allow(self, key: str, limit_per_min: int) -> bool:
        win = int(self._now() // 60)
        with self._lock:
            w, c = self._hits.get(key, (win, 0))
            if w != win:
                w, c = win, 0
            c += 1
            self._hits[key] = (w, c)
            if len(self._hits) > 8192:
                self._hits = {k: v for k, v in self._hits.items() if v[0] == win}
        return c <= limit_per_min


# Module-level singletons reused across warm Lambda invocations / ECS requests.
_DISPATCHER: Optional[ModelDispatcher] = None
_NONCES = NonceCache()
_RATE = _RateLimiter()


def _dispatcher() -> ModelDispatcher:
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = get_dispatcher()
    return _DISPATCHER


def _audit(**fields) -> None:
    """Emit one compact, redacted JSON audit line to stdout (CloudWatch)."""
    try:
        print(json.dumps({"svc": "aws-adapter", **fields}, separators=(",", ":")))
    except Exception:  # noqa: BLE001 — logging must never break the request
        pass


def _err(status: int, code: str, request_id: str) -> tuple[int, dict]:
    return status, {"error": code, "request_id": request_id}


# ---------------------------------------------------------------------------
# Transport-agnostic core
# ---------------------------------------------------------------------------
def process_request(*, method: str, path: str, headers: dict, raw_body: bytes,
                    client_ip: str = "unknown",
                    config: Optional[AdapterConfig] = None) -> tuple[int, dict]:
    """Handle one adapter request. Returns ``(status_code, response_dict)``.

    Pure w.r.t. transport (Lambda and Flask both call this), so it is directly
    verifiable offline with the fake dispatcher.
    """
    cfg = config or AdapterConfig.from_env()
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    request_id = str(h.get("x-request-id") or uuid.uuid4().hex)
    t0 = time.time()
    method = (method or "GET").upper()
    norm = _normalize_path(path)

    # Health probe: no signature (matches SageMaker /ping semantics).
    if method == "GET" and norm in ("/ping", "/health"):
        return 200, {"status": "ok"}

    # Fail closed if the shared secret is not configured server-side.
    if not cfg.secret:
        _audit(event="not_configured", request_id=request_id, path=norm)
        return _err(503, "adapter_not_configured", request_id)

    # Defence-in-depth rate limit.
    if not _RATE.allow(client_ip, cfg.rate_limit_per_min):
        _audit(event="rate_limited", request_id=request_id, ip=client_ip)
        return _err(429, "rate_limited", request_id)

    # Request-size cap (before any parsing / signature work on huge bodies).
    if len(raw_body) > cfg.max_body_bytes:
        _audit(event="too_large", request_id=request_id, bytes=len(raw_body))
        return _err(413, "payload_too_large", request_id)

    # Verify the signed request (F.4). Replay/skew/version all checked here.
    try:
        verify_request(
            cfg.secret, raw_body,
            ts=h.get("x-drishti-timestamp"), nonce=h.get("x-drishti-nonce"),
            signature=h.get("x-drishti-signature"),
            envelope_version=h.get("x-drishti-envelope-version"),
            max_skew_s=cfg.max_skew_s, nonce_cache=_NONCES)
    except SignatureError:
        # Opaque: never reveal which check failed (avoids an oracle).
        _audit(event="auth_failed", request_id=request_id, path=norm, method=method)
        return _err(401, "unauthorized", request_id)

    try:
        if method == "POST" and norm == "/predict":
            return _handle_dispatch(raw_body, request_id, cfg, t0)
        if method == "GET" and norm.startswith("/predict/"):
            return _handle_poll(norm.split("/predict/", 1)[1], request_id, cfg, t0)
        if method == "POST" and norm == "/bedrock/converse":
            return _handle_bedrock_converse(raw_body, request_id, cfg, t0)
    except BedrockRequestError:
        _audit(event="bedrock_bad_request", request_id=request_id)
        return _err(400, "bad_bedrock_request", request_id)
    except BedrockUnavailable as exc:
        _audit(event="bedrock_unavailable", request_id=request_id, error_code=exc.code)
        return _err(503, f"bedrock_{exc.code}", request_id)
    except BackendUnavailable as exc:
        _audit(event="backend_unavailable", request_id=request_id, detail=str(exc)[:120])
        return _err(503, "backend_unavailable", request_id)
    except EnvelopeError:
        # Client error: malformed / over-limit / unapproved envelope.
        _audit(event="bad_envelope", request_id=request_id)
        return _err(400, "bad_envelope", request_id)
    except DispatchError:
        _audit(event="dispatch_error", request_id=request_id)
        return _err(502, "dispatch_error", request_id)
    except Exception:  # noqa: BLE001 — never leak an internal error
        _audit(event="internal_error", request_id=request_id)
        return _err(500, "internal_error", request_id)

    return _err(404, "not_found", request_id)


def _handle_dispatch(raw_body: bytes, request_id: str, cfg: AdapterConfig,
                     t0: float) -> tuple[int, dict]:
    try:
        body = json.loads(raw_body or b"{}")
    except ValueError:
        return _err(400, "bad_json", request_id)
    view = parse_and_validate(body, raw_len=len(raw_body))
    rid = _dispatcher().dispatch(body, view)
    _audit(event="dispatched", request_id=request_id, adapter_request_id=rid,
           task=view.task, backend=view.requested_backend, mode=view.dispatch_mode,
           rows=view.n_query_rows, latency_ms=int((time.time() - t0) * 1000))
    # Dispatch response is not signed (the client only reads request_id here).
    return 200, {"request_id": rid, "state": "dispatched"}


def _handle_poll(request_id_path: str, request_id: str, cfg: AdapterConfig,
                 t0: float) -> tuple[int, dict]:
    adapter_request_id = request_id_path.strip("/")
    if not adapter_request_id:
        return _err(400, "missing_request_id", request_id)
    result = _dispatcher().poll(adapter_request_id)
    signed = sign_result(cfg.secret, result)
    _audit(event="polled", request_id=request_id, adapter_request_id=adapter_request_id,
           state=result.get("state"), latency_ms=int((time.time() - t0) * 1000))
    return 200, signed


def _handle_bedrock_converse(raw_body: bytes, request_id: str, cfg: AdapterConfig,
                             t0: float) -> tuple[int, dict]:
    try:
        body = json.loads(raw_body or b"{}")
    except ValueError:
        return _err(400, "bad_json", request_id)
    result = bedrock_converse(body)
    signed = sign_result(cfg.secret, result)
    usage = result.get("usage") or {}
    _audit(
        event="bedrock_converse",
        request_id=request_id,
        model_id=result.get("model_id"),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        latency_ms=int((time.time() - t0) * 1000),
    )
    return 200, signed


def _normalize_path(path: str) -> str:
    """Strip query string + a leading API Gateway stage segment; keep /predict*."""
    p = (path or "/").split("?", 1)[0]
    if not p.startswith("/"):
        p = "/" + p
    # Keep only from a known route anchor so an API Gateway stage prefix (for
    # example /prod/bedrock/converse) normalises to the protected operation.
    for anchor in ("/bedrock/converse", "/predict", "/ping", "/health"):
        idx = p.find(anchor)
        if idx >= 0:
            return p[idx:]
    return p


# ---------------------------------------------------------------------------
# AWS Lambda entrypoint (API Gateway REST v1 / HTTP v2 proxy)
# ---------------------------------------------------------------------------
def lambda_handler(event: dict, context=None) -> dict:  # noqa: ANN001
    method = (event.get("httpMethod")
              or event.get("requestContext", {}).get("http", {}).get("method")
              or "GET")
    path = (event.get("path") or event.get("rawPath") or "/")
    headers = event.get("headers") or {}
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64
        raw_body = base64.b64decode(raw)
    else:
        raw_body = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw or b"")
    ip = (headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or "")
    client_ip = ip.split(",")[0].strip() or "unknown"

    status, body = process_request(method=method, path=path, headers=headers,
                                   raw_body=raw_body, client_ip=client_ip)
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, separators=(",", ":")),
    }


# ---------------------------------------------------------------------------
# Flask entrypoint (ECS/Fargate alternative)
# ---------------------------------------------------------------------------
def create_app():
    from flask import Flask, Response, request

    app = Flask(__name__)

    @app.get("/ping")
    def ping():
        return Response(json.dumps({"status": "ok"}), mimetype="application/json")

    def _dispatch_flask():
        raw = request.get_data() or b""
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown")
        status, body = process_request(
            method=request.method, path=request.full_path,
            headers=dict(request.headers), raw_body=raw,
            client_ip=ip.split(",")[0].strip())
        return Response(json.dumps(body, separators=(",", ":")), status=status,
                        mimetype="application/json")

    app.add_url_rule("/predict", view_func=_dispatch_flask, methods=["POST"])
    app.add_url_rule("/predict/<path:request_id>", view_func=_dispatch_flask,
                     methods=["GET"])
    app.add_url_rule("/bedrock/converse", view_func=_dispatch_flask, methods=["POST"])
    return app


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8081"))
    create_app().run(host="0.0.0.0", port=port)
