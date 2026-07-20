#!/usr/bin/env python3
"""DRISHTI Part K — reduced demo acceptance runner (Prompt 14).

ONE command to prove the demo. It reads ``acceptance-checklist.json`` and runs the
checks that are runnable, reporting a status per K item:

  PASS   — proven now (a real check ran and passed)
  FAIL   — a runnable check failed (this is the only thing that fails the run)
  HELD   — needs the live Catalyst deploy / AWS GPU plane (command shown)
  MANUAL — a human/ops step (command/instructions shown)

Two of the eleven are provable with NO deployment (K9 minimal event plane, K10 no
browser secrets) and run here; K8 (drafts/evidence -> no model) is proven offline
by the committed tests and re-checked live when a base URL is given. Everything
else is HELD until the deploy / GPU plane exists, and prints the exact command.

Stdlib only (urllib/hmac/subprocess), so it runs on any runner without extra deps.

    # offline (no deploy): runs K9 + K10, reports the rest HELD/MANUAL
    python infra/catalyst/verification/acceptance_check.py

    # full demo acceptance (post-deploy):
    python infra/catalyst/verification/acceptance_check.py \
        --base-url https://drishti-api-<zaid>.development.catalystappsail.com \
        --web-url  https://drishti-<...>.onslate.in \
        --read-endpoint /api/cases?limit=1 --result-endpoint /api/predictions?limit=1
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_CHECKLIST = os.path.join(_HERE, "acceptance-checklist.json")

PASS, FAIL, HELD, MANUAL = "PASS", "FAIL", "HELD", "MANUAL"


def _get(url, timeout=10.0):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - network/DNS
        return 0, str(e)


def _post(url, body, headers, timeout=10.0):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def _b64url(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _sign_service_context(secret):
    now = int(time.time() * 1000)
    ctx = {"scope": "service", "aud": "drishti-appsail", "source": "acceptance",
           "ts": now, "exp": now + 60_000, "nonce": uuid.uuid4().hex,
           "request_id": uuid.uuid4().hex}
    payload = _b64url(json.dumps(ctx).encode())
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"X-DRISHTI-Context": payload, "X-DRISHTI-Signature": sig,
            "X-Request-ID": ctx["request_id"]}


# --- per-item runners: return (status, detail) -------------------------------
def r_http_web(a):
    if not a.web_url:
        return HELD, "run with --web-url (deploy Slate/Web Client first)"
    code, _ = _get(a.web_url)
    return (PASS, f"{a.web_url} -> {code}") if code == 200 else (FAIL, f"got {code}")


def r_http_auth(a):
    if not a.base_url:
        return HELD, "run with --base-url after deploy (apig:enable + AppSail)"
    code, _ = _post(f"{a.base_url}/internal/ping", {}, {})
    if code != 401:
        return FAIL, f"unsigned /internal/ping expected 401, got {code}"
    secret = os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")
    if not secret:
        return PASS, "unsigned=401 (set ZOHO_APPSAIL_SIGNING_SECRET to also check signed=200)"
    scode, sbody = _post(f"{a.base_url}/internal/ping", {}, _sign_service_context(secret))
    if scode == 200 and "service" in sbody:
        return PASS, "unsigned=401, signed=200 (scope=service)"
    return FAIL, f"signed /internal/ping expected 200, got {scode}"


def r_http_health(a):
    if not a.base_url:
        return HELD, "run with --base-url after AppSail deploy"
    live, _ = _get(f"{a.base_url}/health/live")
    ready, _ = _get(f"{a.base_url}/health/ready")
    if live == 200 and ready == 200:
        return PASS, "live=200 ready=200"
    return FAIL, f"live={live} ready={ready}"


def r_http_read(a):
    ep = a.read_endpoint if a.read_endpoint else a.result_endpoint
    if not a.base_url or not ep:
        return HELD, "run with --base-url + --read-endpoint/--result-endpoint after ds:import"
    code, body = _get(f"{a.base_url}{ep}")
    return (PASS, f"{ep} -> {code}") if code == 200 else (FAIL, f"{ep} got {code}")


def r_http_routing(a):
    if not a.base_url:
        return HELD, ("live check needs --base-url; proven offline by "
                      "tests/test_predict_runtime.py (draft + evidence -> no model)")
    ok = True
    detail = []
    for ev in ("fir_draft_saved", "evidence_uploaded"):
        code, body = _get(f"{a.base_url}/predict/routing?event={ev}")
        invokes = code == 200 and '"invokes_model": true' in body.replace(" ", " ")
        ok = ok and code == 200 and not invokes
        detail.append(f"{ev}:{code}")
    return (PASS, "drafts+evidence invoke no model (" + ",".join(detail) + ")") if ok \
        else (FAIL, "a draft/evidence route invoked a model: " + ",".join(detail))


def r_config_minimal_events(a):
    sig = json.load(open(os.path.join(_REPO_ROOT, "infra/catalyst/jobs/signals-rules.json"),
                        encoding="utf-8"))
    cron = json.load(open(os.path.join(_REPO_ROOT, "infra/catalyst/jobs/cron-schedules.json"),
                         encoding="utf-8"))
    min_rules = [r["name"] for r in sig.get("rules", []) if r.get("tier") == "minimal"]
    min_crons = [c["name"] for c in cron.get("crons", []) if c.get("tier") == "minimal"]
    if min_rules == ["prediction-requested"] and min_crons == ["drishti-forecast-daily"]:
        return PASS, "1 Signal (prediction-requested) + 1 cron (drishti-forecast-daily)"
    return FAIL, f"minimal Signals={min_rules} crons={min_crons}"


def r_no_browser_secrets(a):
    script = os.path.join(_REPO_ROOT, "infra/aws/check_no_db_url_in_web.py")
    rc = subprocess.run([sys.executable, script], capture_output=True, text=True).returncode
    return (PASS, "no DB URL / secret in the web source") if rc == 0 \
        else (FAIL, "check_no_db_url_in_web.py found a leak")


def r_tabfm_live(a):
    if not (a.tabfm_live and a.base_url):
        return HELD, ("real TabFM/CUDA needs the GPU plane; run "
                      "pytest tests/test_predict_runtime.py::test_real_tabfm_cuda_prediction_succeeds "
                      "with the real adapter, or --tabfm-live --base-url post-deploy")
    return HELD, "live TabFM round-trip attempted only against the deployed GPU endpoint"


def r_gpu_stopped(a):
    name = a.endpoint_name
    teardown = ("after testing run: python infra/aws/gpu-worker/deploy_gpu_worker.py "
                f"--teardown (deletes endpoint {name})")
    try:
        p = subprocess.run(["aws", "sagemaker", "describe-endpoint", "--endpoint-name", name],
                           capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.SubprocessError):
        return MANUAL, f"aws CLI not available here; {teardown}"
    if p.returncode == 0:
        return FAIL, f"endpoint {name} still exists — stop it: {teardown}"
    err = (p.stderr or "").lower()
    # PASS only on a DEFINITIVE "endpoint does not exist"; anything else (auth,
    # region, connectivity) is ambiguous -> MANUAL (never a false 'stopped').
    if any(s in err for s in ("could not find", "does not exist", "resourcenotfound",
                              "validationexception")):
        return PASS, f"endpoint {name} absent (stopped)"
    return MANUAL, f"aws could not confirm (no creds/config here); {teardown}"


def r_manual(a):
    return MANUAL, None  # detail comes from the checklist 'how'


_RUNNERS = {
    "http_web": r_http_web, "http_auth": r_http_auth, "http_health": r_http_health,
    "http_read": r_http_read, "http_routing": r_http_routing,
    "config_minimal_events": r_config_minimal_events,
    "no_browser_secrets": r_no_browser_secrets, "tabfm_live": r_tabfm_live,
    "gpu_stopped": r_gpu_stopped, "manual": r_manual,
}


# release_evidence kinds that a PASS can legitimately rely on for a RELEASE claim.
# 'config_only' is deliberately excluded: a Signals/cron JSON declaration proves
# intent, never a live Signal delivery / cron execution / Data Store write / auth
# flow / GPU invocation (strict-mode rule, Prompt 18 §E.4).
_RELEASE_OK_EVIDENCE = {"live", "local_ok", "ops"}


def _release_gap(item: dict, status: str) -> str | None:
    """In strict/release mode, return None if the mandatory item is genuinely
    proven, else a short reason it is NOT release-ready."""
    if status != PASS:
        return f"{status} (not proven)"
    evidence = item.get("release_evidence", "live")
    if evidence not in _RELEASE_OK_EVIDENCE:
        # PASS but only a configuration declaration — cannot prove the live capability
        return "config declaration only — a live invocation is required"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="DRISHTI Part K reduced demo acceptance.")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--web-url", default="")
    ap.add_argument("--read-endpoint", default="")
    ap.add_argument("--result-endpoint", default="")
    ap.add_argument("--endpoint-name", default="drishti-gpu-async")
    ap.add_argument("--tabfm-live", action="store_true")
    ap.add_argument("--strict", "--release", dest="strict", action="store_true",
                    help="strict RELEASE gate: any mandatory HELD/MANUAL/FAIL/UNKNOWN/"
                         "skipped/config-only check exits non-zero (no release success).")
    a = ap.parse_args()

    mode = "STRICT RELEASE GATE" if a.strict else "diagnostic (offline-tolerant)"
    checklist = json.load(open(_CHECKLIST, encoding="utf-8"))
    print(f"DRISHTI Part K — reduced demo acceptance [{mode}]\n" + "=" * 56)
    counts = {PASS: 0, FAIL: 0, HELD: 0, MANUAL: 0}
    release_gaps: list[tuple[str, str]] = []
    for item in checklist["required"]:
        runner = _RUNNERS.get(item["runner"], r_manual)
        status, detail = runner(a)
        counts[status] += 1
        detail = detail or item["how"]
        gap = _release_gap(item, status)
        tag = ""
        if a.strict:
            tag = "  <= RELEASE-BLOCKING" if gap else "  (release-proven)"
        if gap:
            release_gaps.append((item["id"], gap))
        print(f"[{status:6}] {item['id']}  {item['proves']}{tag}")
        print(f"          {detail}")

    print("\ntest only when the feature is enabled: " +
          ", ".join(f["feature"] for f in checklist["test_only_when_enabled"]))
    print(f"\nsummary: {counts[PASS]} PASS, {counts[FAIL]} FAIL, "
          f"{counts[HELD]} HELD, {counts[MANUAL]} MANUAL")

    if a.strict:
        # Strict RELEASE gate: every mandatory check must be genuinely proven.
        if release_gaps:
            print(f"\n{len(release_gaps)} mandatory check(s) NOT release-proven:")
            for cid, why in release_gaps:
                print(f"  - {cid}: {why}")
            print("\nRELEASE ACCEPTANCE: BLOCKED — not ready for a hackathon demonstration "
                  "(mandatory checks are HELD/MANUAL/config-only or failing).")
            return 1
        print("\nRELEASE ACCEPTANCE: PASS — every mandatory check is proven by a live/real "
              "invocation. DRISHTI is ready for a synthetic hackathon demonstration.")
        return 0

    # Non-strict diagnostic mode: a runnable failure still fails; HELD/MANUAL make
    # the run INCOMPLETE. It must NEVER print release success.
    if counts[FAIL]:
        print("ACCEPTANCE: FAIL (a runnable check failed)")
        return 1
    if counts[HELD] or counts[MANUAL]:
        print("ACCEPTANCE: INCOMPLETE — all runnable checks passed, but "
              f"{counts[HELD]} HELD + {counts[MANUAL]} MANUAL check(s) await the live "
              "deploy/GPU plane. Run with --strict for the release gate (this is NOT a "
              "release-ready result).")
        return 0
    print("ACCEPTANCE: all mandatory checks passed. Run with --strict to assert the "
          "release gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
