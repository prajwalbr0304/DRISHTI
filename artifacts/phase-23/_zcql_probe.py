"""Definitively locate the SDK hang: call the exact ZCQL endpoint the SDK uses
(POST /baas/v1/project/{pid}/query) via urllib (SSL verified) and via requests
with SSL on/off, all with hard 15s timeouts. If urllib returns 200, the endpoint
+ creds + scopes are fine and the hang is purely the SDK's HTTP client (not SSL).
"""
import json
import os
import ssl
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))["AppSail (Console > AppSail drishti-api > Configuration)"]
PID = "48361000000030003"
BASE = "https://api.catalyst.zoho.in"


def refresh():
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": a["ZOHO_CATALYST_REFRESH_TOKEN"],
        "client_id": a["ZOHO_CATALYST_CLIENT_ID"],
        "client_secret": a["ZOHO_CATALYST_CLIENT_SECRET"],
    }).encode()
    req = urllib.request.Request("https://accounts.zoho.in/oauth/v2/token", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


tok = refresh()
print("access token acquired:", bool(tok), flush=True)
zcql = json.dumps({"query": "SELECT ROWID FROM State LIMIT 1"}).encode()
url = f"{BASE}/baas/v1/project/{PID}/query"

# 1) urllib POST /query (SSL verified) with 15s timeout
try:
    req = urllib.request.Request(url, data=zcql, method="POST")
    req.add_header("Authorization", "Zoho-oauthtoken " + tok)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        print("urllib POST /query ->", r.getcode(), r.read().decode()[:150], flush=True)
except Exception as e:  # noqa: BLE001
    print("urllib POST /query -> ERR", type(e).__name__, str(e)[:150], flush=True)

# 2) requests POST with SSL verify on/off (if requests present)
try:
    import requests
    for verify in (True, False):
        try:
            r = requests.post(url, data=zcql, timeout=15, verify=verify, headers={
                "Authorization": "Zoho-oauthtoken " + tok, "Content-Type": "application/json"})
            print(f"requests verify={verify} ->", r.status_code, r.text[:120], flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"requests verify={verify} -> ERR", type(e).__name__, str(e)[:150], flush=True)
except ImportError:
    print("requests not installed", flush=True)
