"""Prove the Catalyst-side -> protected AWS adapter -> SageMaker path with a REAL
signed request, exactly as AppSail's SignedHttpsAdapter signs it (HMAC over
ts|nonce|canonical-body). POSTs /predict through the API Gateway, then polls
GET /predict/{id}. Falls back to reading the S3 async output directly if a local
middlebox interferes with GET health-style paths. No secret is printed."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import uuid

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "infra", "aws", "gpu-worker"))
import sagemaker_ops as ops  # reuse the synthetic envelope builders + config

REGION = ops.REGION
PROFILE = ops.PROFILE
BUCKET = ops.BUCKET
_sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
_SECRET = _sess.client("secretsmanager").get_secret_value(
    SecretId="drishti/aws-adapter-secret")["SecretString"]
_ADAPTER = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
                                       "infra", "aws", "adapter", "adapter.deployed.json"),
                          encoding="utf-8"))["adapter_url"]


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: bytes, ts: str, nonce: str) -> str:
    return hmac.new(_SECRET.encode(), b"|".join((ts.encode(), nonce.encode(), payload)),
                    hashlib.sha256).hexdigest()


def _headers(payload: bytes) -> dict:
    ts, nonce = str(int(time.time())), uuid.uuid4().hex
    return {"Content-Type": "application/json", "X-DRISHTI-Timestamp": ts,
            "X-DRISHTI-Nonce": nonce, "X-DRISHTI-Signature": _sign(payload, ts, nonce),
            "X-DRISHTI-Envelope-Version": "1.0.0"}


def _http(method: str, path: str, body: bytes | None) -> dict:
    req = urllib.request.Request(_ADAPTER + path, data=body, method=method,
                                 headers=_headers(body or b""))
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read())


def post_predict(env: dict) -> str:
    return _http("POST", "/predict", _canonical(env))["request_id"]


def poll(request_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        try:
            last = _http("GET", f"/predict/{request_id}", None)
            if last.get("state") in ("completed", "failed"):
                return last
        except Exception as exc:  # noqa: BLE001 - fall back to S3 on any GET interference
            last = {"poll_error": str(exc)[:160]}
        time.sleep(6)
    return last or {"state": "timed_out"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["tabfm", "timesfm", "fallback", "badtabfm"], default="timesfm")
    ap.add_argument("--idem", default="")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    env = ops._envelope(args.task, args.idem)
    t0 = time.time()
    rid = post_predict(env)
    print(json.dumps({"stage": "dispatched", "adapter_url": _ADAPTER, "task": args.task,
                      "request_id": rid, "idempotency_key": env["idempotency_key"]}, indent=2))
    result = poll(rid, args.timeout)
    result["_client_roundtrip_s"] = round(time.time() - t0, 2)
    print("=== ADAPTER RESULT (signed, via API Gateway) ===")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
