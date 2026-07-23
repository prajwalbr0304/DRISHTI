#!/usr/bin/env python3
"""Safe deploy for the gateway_api function.

WHY THIS EXISTS: `catalyst deploy --only functions:gateway_api` applies the
`env_variables` from catalyst-config.json, which is committed as `{}` (secrets are
never committed). A bare deploy therefore WIPES the function's Console env
(ZOHO_APPSAIL_BASE_URL / ZOHO_APPSAIL_SIGNING_SECRET) and the gateway starts
returning 503 `gateway_not_configured`.

This wrapper injects the env from the gitignored secrets file
(infra/catalyst/secrets/appsail-env.local.json) into catalyst-config.json, runs the
deploy, then reverts catalyst-config.json so nothing secret is committed.

Usage (from repo root or anywhere):
    python infra/catalyst/functions/gateway_api/deploy.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
CFG = os.path.join(HERE, "catalyst-config.json")
SECRETS = os.path.join(REPO, "infra", "catalyst", "secrets", "appsail-env.local.json")
CATALYST_DIR = os.path.join(REPO, "infra", "catalyst")


def main() -> int:
    if not os.path.isfile(SECRETS):
        print(f"ERROR: secrets file not found: {SECRETS}", file=sys.stderr)
        return 2
    sec = json.load(open(SECRETS, encoding="utf-8"))
    fn = sec.get("Functions gateway_api + *_event + cron_* (Console > Functions > each > Configuration)", {})
    base_url = fn.get("ZOHO_APPSAIL_BASE_URL")
    signing = fn.get("ZOHO_APPSAIL_SIGNING_SECRET")
    if not base_url or not signing:
        print("ERROR: ZOHO_APPSAIL_BASE_URL / ZOHO_APPSAIL_SIGNING_SECRET missing in secrets file", file=sys.stderr)
        return 2

    original = open(CFG, encoding="utf-8").read()
    cfg = json.loads(original)
    cfg["deployment"]["env_variables"] = {
        "ZOHO_APPSAIL_BASE_URL": base_url,
        "ZOHO_APPSAIL_SIGNING_SECRET": signing,
        "DRISHTI_GATEWAY_PATH_PREFIX": "/api",
        # Option B synthetic-demo login. Set to "false" (or remove) to require a
        # real Catalyst session again.
        "DRISHTI_DEMO_AUTH": os.environ.get("DRISHTI_DEMO_AUTH", "true"),
    }
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("injected env keys:", list(cfg["deployment"]["env_variables"].keys()))
    try:
        rc = subprocess.call(["catalyst", "deploy", "--only", "functions:gateway_api"],
                             cwd=CATALYST_DIR, shell=(os.name == "nt"))
    finally:
        # ALWAYS restore the committed (secret-free) config.
        open(CFG, "w", encoding="utf-8").write(original)
        print("reverted catalyst-config.json (no secret left in the working tree)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
