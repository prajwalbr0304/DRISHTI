#!/usr/bin/env python3
"""Live AppSail trust-boundary probe (Prompt 23 E.5 / C.5).

Proves the deployed AppSail enforces the signed-context boundary when hit
DIRECTLY at its public URL (i.e. an attacker bypassing the API Gateway):

  1. unsigned request                -> 401  (direct-AppSail CRUD bypass blocked)
  2. valid SERVICE context           -> 200  scope=service
  3. valid GATEWAY ctx role=super_admin -> 200 scope=gateway role=super_admin
  4. valid GATEWAY ctx role=investigator -> 200 role=investigator (trusted role)
  5. expired context (exp in past)   -> 401  (expiry enforced)
  6. future-dated context            -> 401  (clock-skew guard)
  7. wrong audience                  -> 401  (audience binding)
  8. tampered signature              -> 401  (HMAC integrity)
  9. tampered payload, old signature -> 401  (cannot forge role/scope)
 10. unknown role in gateway ctx     -> 401  (role re-validated server-side)
 11. replayed nonce (same ctx twice) -> 1st 200, 2nd 401 (replay protection)

Stdlib only. The signing secret is read from ZOHO_APPSAIL_SIGNING_SECRET (never
committed). Exit non-zero if any assertion fails.

    python security_probe.py --base-url https://drishti-api-<zaid>.development.catalystappsail.in
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
import urllib.error
import urllib.request
import uuid


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _post(url: str, headers: dict, timeout: float = 15.0):
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def sign(secret: str, ctx: dict) -> dict:
    payload = _b64url(json.dumps(ctx).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"X-DRISHTI-Context": payload, "X-DRISHTI-Signature": sig,
            "X-Request-ID": ctx.get("request_id", "")}


def base_ctx(scope: str, **over) -> dict:
    now = int(time.time() * 1000)
    ctx = {"scope": scope, "aud": "drishti-appsail", "ts": now, "exp": now + 60_000,
           "nonce": uuid.uuid4().hex, "request_id": uuid.uuid4().hex}
    if scope == "service":
        ctx["source"] = "security-probe"
    ctx.update(over)
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True, help="direct AppSail base URL")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    url = f"{base}/internal/ping"
    secret = os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")
    if not secret:
        print("FATAL: ZOHO_APPSAIL_SIGNING_SECRET not set")
        return 2

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}", flush=True)
        if not ok:
            failures.append(name)

    # 1. unsigned -> 401 (bypass blocked)
    code, body = _post(url, {})
    check("1 unsigned direct-AppSail -> 401 (bypass blocked)", code == 401, f"got {code}")

    # 2. valid service context -> 200 scope=service
    code, body = _post(url, sign(secret, base_ctx("service")))
    check("2 valid service ctx -> 200 scope=service", code == 200 and '"scope":"service"' in body.replace(" ", ""), f"got {code} {body[:90]}")

    # 3. valid gateway ctx role=super_admin -> 200
    code, body = _post(url, sign(secret, base_ctx("gateway", role="super_admin", user_id="u-sa")))
    check("3 gateway ctx super_admin -> 200 role=super_admin", code == 200 and '"role":"super_admin"' in body.replace(" ", ""), f"got {code} {body[:90]}")

    # 4. valid gateway ctx role=investigator -> 200
    code, body = _post(url, sign(secret, base_ctx("gateway", role="investigator", user_id="u-io")))
    check("4 gateway ctx investigator -> 200 role=investigator", code == 200 and '"role":"investigator"' in body.replace(" ", ""), f"got {code} {body[:90]}")

    # 5. expired context -> 401
    now = int(time.time() * 1000)
    code, body = _post(url, sign(secret, base_ctx("service", ts=now - 120_000, exp=now - 60_000)))
    check("5 expired ctx -> 401", code == 401, f"got {code}")

    # 6. future-dated context -> 401
    code, body = _post(url, sign(secret, base_ctx("service", ts=now + 600_000, exp=now + 660_000)))
    check("6 future-dated ctx -> 401", code == 401, f"got {code}")

    # 7. wrong audience -> 401
    code, body = _post(url, sign(secret, base_ctx("service", aud="someone-else")))
    check("7 wrong audience -> 401", code == 401, f"got {code}")

    # 8. tampered signature -> 401
    h = sign(secret, base_ctx("service"))
    h["X-DRISHTI-Signature"] = ("0" if h["X-DRISHTI-Signature"][0] != "0" else "1") + h["X-DRISHTI-Signature"][1:]
    code, body = _post(url, h)
    check("8 tampered signature -> 401", code == 401, f"got {code}")

    # 9. tampered payload keeping an old (now-wrong) signature -> 401
    good = sign(secret, base_ctx("gateway", role="investigator", user_id="u1"))
    forged_ctx = base_ctx("gateway", role="super_admin", user_id="u1")  # escalate role
    forged_payload = _b64url(json.dumps(forged_ctx).encode())
    code, body = _post(url, {"X-DRISHTI-Context": forged_payload,
                             "X-DRISHTI-Signature": good["X-DRISHTI-Signature"]})
    check("9 forged payload (role escalation) -> 401", code == 401, f"got {code}")

    # 10. unknown role in a valid-signed gateway ctx -> 401 (role re-validated)
    code, body = _post(url, sign(secret, base_ctx("gateway", role="root", user_id="u2")))
    check("10 unknown role -> 401 (server re-validates role)", code == 401, f"got {code}")

    # 11. replay: same nonce twice -> 1st 200, 2nd 401
    replay = sign(secret, base_ctx("service"))
    c1, _ = _post(url, replay)
    c2, _ = _post(url, replay)
    check("11 replay same nonce -> 1st 200 then 401", c1 == 200 and c2 == 401, f"got {c1},{c2}")

    print(f"\n{'SECURITY PROBE FAILED: ' + str(failures) if failures else 'SECURITY PROBE OK (11/11)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
