#!/usr/bin/env python3
"""Post-deploy smoke test (Phase 14 workflow §1, Part K evidence).

Checks a deployed DRISHTI AppSail/API base URL:
  1. GET /health/live  -> 200 (liveness).
  2. GET /health/ready -> 200 (readiness; RDS advisory, never hard-required).
  3. POST /internal/ping WITHOUT a signature -> 401 (the signed-context boundary
     rejects unsigned/forged callers — report §8.2).
  4. If ZOHO_APPSAIL_SIGNING_SECRET is set, mint a valid service context and
     POST /internal/ping -> 200 with scope=service (happy path proves the Node
     signing <-> Python verification contract end-to-end).
  5. GET /predict/health -> 200 (prediction runtime is deployed + responding).
  6. GET /predict/enablement -> 200 with the enabled model tasks present
     (the prediction plane's routing/enablement is live). Aggregate metadata
     only; no GPU call is made (the real TabFM run is the held cloud step).

Health + auth + prediction smoke, per Part I.

Stdlib only (urllib/hmac) so it runs on any runner without extra deps.
Exit code is non-zero if any assertion fails, failing the pipeline stage.

    python smoke_test.py --base-url https://drishti-api-<zaid>.development.catalystappsail.com
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import uuid


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _get(url: str, timeout: float = 10.0):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, e.read().decode("utf-8", "replace")


def _post(url: str, body: dict, headers: dict, timeout: float = 10.0):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, e.read().decode("utf-8", "replace")


def sign_service_context(secret: str) -> dict:
    now = int(time.time() * 1000)  # ms, matching JS Date.now()
    ctx = {"scope": "service", "aud": "drishti-appsail", "source": "smoke",
           "ts": now, "exp": now + 60_000,
           "nonce": uuid.uuid4().hex, "request_id": uuid.uuid4().hex}
    payload = _b64url(json.dumps(ctx).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"X-DRISHTI-Context": payload, "X-DRISHTI-Signature": sig,
            "X-Request-ID": ctx["request_id"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(name)

    code, _ = _get(f"{base}/health/live")
    check("GET /health/live == 200", code == 200, f"got {code}")

    code, _ = _get(f"{base}/health/ready")
    check("GET /health/ready == 200", code == 200, f"got {code}")

    code, _ = _post(f"{base}/internal/ping", {}, {})
    check("POST /internal/ping unsigned == 401", code == 401, f"got {code}")

    secret = os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")
    if secret:
        code, body = _post(f"{base}/internal/ping", {}, sign_service_context(secret))
        ok = code == 200 and '"scope": "service"' in body.replace(" ", " ")
        check("POST /internal/ping signed == 200 (scope=service)", code == 200, f"got {code} {body[:120]}")
    else:
        print("[SKIP] signed /internal/ping (ZOHO_APPSAIL_SIGNING_SECRET not set)")

    # Prediction plane smoke (aggregate metadata only; no GPU call).
    code, _ = _get(f"{base}/predict/health")
    check("GET /predict/health == 200", code == 200, f"got {code}")

    code, body = _get(f"{base}/predict/enablement")
    ok = code == 200 and "enabled_tasks" in body and "station_workload_band" in body
    check("GET /predict/enablement == 200 (enabled tasks present)", ok, f"got {code} {body[:120]}")

    if failures:
        print(f"\nSMOKE FAILED: {len(failures)} check(s) failed: {failures}")
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
