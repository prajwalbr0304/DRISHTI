"""Find the correct Insert Row body format + capture the 400 message."""
import json
import os
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))["AppSail (Console > AppSail drishti-api > Configuration)"]
PID = "48361000000030003"
BASE = "https://api.catalyst.zoho.in"


def refresh():
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token", "refresh_token": a["ZOHO_CATALYST_REFRESH_TOKEN"],
        "client_id": a["ZOHO_CATALYST_CLIENT_ID"], "client_secret": a["ZOHO_CATALYST_CLIENT_SECRET"]}).encode()
    r = urllib.request.Request("https://accounts.zoho.in/oauth/v2/token", data=body, method="POST")
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


tok = refresh()
url = f"{BASE}/baas/v1/project/{PID}/table/State/row"


def post(label, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", "Zoho-oauthtoken " + tok)
    req.add_header("Content-Type", "application/json")
    req.add_header("Environment", "Development")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"{label}: {resp.getcode()} {resp.read().decode()[:200]}", flush=True)
    except urllib.error.HTTPError as e:
        print(f"{label}: {e.code} {e.read().decode()[:250]}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"{label}: ERR {type(e).__name__} {str(e)[:150]}", flush=True)


row = {"ExternalID": "state:probe1", "Active": True, "NationalityID": 1, "StateID": 1, "StateName": "Karnataka"}
post("single-object", row)
post("array", [row])
post("array-strings", [{"ExternalID": "state:probe2", "Active": "true", "NationalityID": "1", "StateID": "1", "StateName": "Karnataka"}])
