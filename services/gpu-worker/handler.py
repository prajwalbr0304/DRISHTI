"""SageMaker-compatible inference handler for the DRISHTI GPU worker (G.3).

Implements the two endpoints SageMaker custom containers must expose:
  * GET  /ping         — health; 200 when the worker can serve.
  * POST /invocations  — run one prediction envelope.

It validates the request envelope, routes to the correct typed backend, and
returns a SIGNED result envelope. TabFM fails closed when CUDA/weights are
missing (never a mislabelled fallback). AWS Batch entrypoints reuse
``handle_invocation`` directly.

This file runs ONLY on AWS GPU compute. It is never part of the AppSail image.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

import backends
from schema import (BackendKind, JobState, ModelTask,
                    PredictionRequestEnvelope, PredictionResultEnvelope)

_SECRET = os.getenv("DRISHTI_AWS_ADAPTER_SECRET", "")


def _canonical(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign_result(result: PredictionResultEnvelope) -> dict:
    """Attach an HMAC signature over the canonical result (verified by AppSail)."""
    data = result.model_dump()
    signed_at = str(int(time.time()))
    nonce = uuid.uuid4().hex
    if _SECRET:
        payload = _canonical({k: v for k, v in data.items()
                              if k not in ("signature", "_sig_nonce")})
        data["signature"] = hmac.new(
            _SECRET.encode(),
            b"|".join((signed_at.encode(), nonce.encode(), payload)),
            hashlib.sha256).hexdigest()
        data["signed_at"] = signed_at
        data["_sig_nonce"] = nonce
    return data


def _fail(env: PredictionRequestEnvelope, code: str, detail: str,
          warnings: list[str] | None = None) -> dict:
    return _sign_result(PredictionResultEnvelope(
        request_id=env.request_id, idempotency_key=env.idempotency_key, task=env.task,
        state=JobState.FAILED, error_code=code, error_detail=detail,
        warnings=warnings or []))


def handle_invocation(body: dict) -> dict:
    """Core dispatch. Returns a signed result-envelope dict."""
    try:
        env = PredictionRequestEnvelope.model_validate(body)
        env.validate_shapes()
    except Exception as exc:  # noqa: BLE001
        return _fail(PredictionRequestEnvelope.model_construct(
            request_id=body.get("request_id", "unknown"),
            idempotency_key=body.get("idempotency_key", "unknown"),
            task=body.get("task", ModelTask.STATION_WORKLOAD_BAND)),
            "SCHEMA_MISMATCH", f"invalid request envelope: {exc}")

    n_bands = int(env.output_schema.get("n_bands", 4))
    try:
        if env.requested_backend == BackendKind.TABFM:
            # Fails closed inside run_tabfm if CUDA/weights are missing.
            res = backends.run_tabfm(
                env.columns, env.context_x, env.context_y, env.query_rows,
                n_bands=n_bands, weight_digest=env.model_artifact_digest_expected())
        elif env.requested_backend == BackendKind.TIMESFM:
            res = backends.run_timesfm(env.query_rows, horizon=int(
                env.output_schema.get("horizon", 14)), freq=env.output_schema.get("freq", "D"),
                weight_digest=env.model_artifact_digest_expected())
        elif env.requested_backend in (BackendKind.TABPFN, BackendKind.INCONTEXT,
                                       BackendKind.BASELINE):
            res = backends.run_fallback(
                env.columns, env.context_x, env.context_y, env.query_rows,
                backend=env.requested_backend.value, n_bands=n_bands)
        else:
            return _fail(env, "UNSUPPORTED_BACKEND",
                         f"backend {env.requested_backend} not served by this worker")
    except backends.BackendUnavailable as exc:
        # The fail-closed path: e.g. tabfm requested but no CUDA/weights.
        return _fail(env, "CUDA_UNAVAILABLE", str(exc),
                     warnings=["fail closed: requested backend could not run as requested"])
    except Exception as exc:  # noqa: BLE001
        return _fail(env, "INFERENCE_ERROR", f"{type(exc).__name__}: {exc}")

    return _sign_result(PredictionResultEnvelope(
        request_id=env.request_id, idempotency_key=env.idempotency_key, task=env.task,
        state=JobState.COMPLETED, actual_backend=BackendKind(res.actual_backend),
        actual_device=res.actual_device, model_artifact_digest=res.model_artifact_digest,
        feature_schema_digest=env.feature_schema_digest, context_digest=env.context_digest,
        predictions=res.predictions, confidence=res.confidence, abstained=res.abstained,
        runtime_ms=res.runtime_ms, cold_start_ms=res.cold_start_ms,
        peak_gpu_mem_mb=res.peak_gpu_mem_mb, gpu_name=res.gpu_name, warnings=res.warnings))


# --- Flask app for the SageMaker real-time / async container contract ---------
def create_app():
    from flask import Flask, Response, jsonify, request
    app = Flask(__name__)

    @app.get("/ping")
    def ping():
        env = backends.report_environment()
        # 200 when the process is up; readiness detail in the body.
        return jsonify({"status": "ok", "environment": env}), 200

    @app.post("/invocations")
    def invocations():
        try:
            body = request.get_json(force=True)
        except Exception:  # noqa: BLE001
            return Response("bad json", status=400)
        return jsonify(handle_invocation(body)), 200

    return app


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)
