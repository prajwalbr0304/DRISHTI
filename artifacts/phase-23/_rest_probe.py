"""Probe the Catalyst Data Store REST API (IN DC) with the self-client refresh
token, with hard timeouts so nothing hangs. Finds the working base domain +
confirms admin data access. Prints statuses only (no token values)."""
import json
import os
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sheet = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))
a = sheet["AppSail (Console > AppSail drishti-api > Configuration)"]
PID = "48361000000030003"


def post(url, data, timeout=15):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")


def get(url, token, timeout=15, extra=None):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Zoho-oauthtoken " + token)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:  # noqa: BLE001
        return "ERR", f"{type(e).__name__}: {str(e)[:120]}"


print("== refresh access token (accounts.zoho.in) ==", flush=True)
code, body = post("https://accounts.zoho.in/oauth/v2/token", {
    "grant_type": "refresh_token",
    "refresh_token": a["ZOHO_CATALYST_REFRESH_TOKEN"],
    "client_id": a["ZOHO_CATALYST_CLIENT_ID"],
    "client_secret": a["ZOHO_CATALYST_CLIENT_SECRET"],
})
tok = json.loads(body).get("access_token", "")
print("refresh status:", code, "access_token_len:", len(tok), flush=True)

candidates = [
    "https://api.catalyst.zoho.in",
    "https://console.catalyst.zoho.in",
]
for base in candidates:
    url = f"{base}/baas/v1/project/{PID}/table/State/row?max_rows=1"
    for hdrs in ({}, {"ENVIRONMENT": "Development"}):
        code, body = get(url, tok, timeout=12, extra=hdrs)
        print(f"GET {base} hdrs={list(hdrs)} -> {code} :: {body[:180]}", flush=True)
