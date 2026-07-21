"""Prove the surgical fix: a RefreshTokenCredential subclass whose token() does
the correct single-slash refresh (via requests), + APP_DOMAIN pointed at the IN
DC public API domain. If the ZCQL query returns cleanly, the SDK works end-to-end
for Data Store/Cache/Stratus with no full rewrite."""
import json
import os
import time

# MUST be set before importing the SDK (constants read at import).
os.environ["X_ZOHO_CATALYST_CONSOLE_URL"] = "https://api.catalyst.zoho.in"
os.environ["X_ZOHO_STRATUS_RESOURCE_SUFFIX"] = ".zohostratus.in"

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))["AppSail (Console > AppSail drishti-api > Configuration)"]

import requests
import zcatalyst_sdk
from zcatalyst_sdk import credentials
from zcatalyst_sdk.types import ICatalystOptions

ACCOUNTS = "https://accounts.zoho.in"


class FixedRefreshCredential(credentials.RefreshTokenCredential):
    """Correct single-slash token refresh (SDK's built-in path double-slashes)."""
    def __init__(self, obj):
        super().__init__(obj)
        self._tok = None
        self._exp = 0.0

    def token(self):
        if self._tok and self._exp > time.time():
            return self._tok
        r = requests.post(ACCOUNTS + "/oauth/v2/token", timeout=15, data={
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        })
        d = r.json()
        self._tok = d["access_token"]
        self._exp = time.time() + int(d.get("expires_in", 3600)) - 60
        return self._tok


cred = FixedRefreshCredential({
    "refresh_token": a["ZOHO_CATALYST_REFRESH_TOKEN"],
    "client_id": a["ZOHO_CATALYST_CLIENT_ID"],
    "client_secret": a["ZOHO_CATALYST_CLIENT_SECRET"],
})
opts = ICatalystOptions(project_id="48361000000030003", project_key=a["ZOHO_CATALYST_ZAID"],
                        project_domain="https://api.catalyst.zoho.in", environment="Development")
app = zcatalyst_sdk.initialize_app(credential=cred, options=opts, name="drishti-fixed")
print("zcql SELECT ...", flush=True)
rows = app.zcql().execute_query("SELECT ROWID FROM State LIMIT 1")
print("SUCCESS zcql rows:", rows, flush=True)
print("datastore insert probe ...", flush=True)
try:
    t = app.datastore().table("State")
    print("table handle OK:", t is not None, flush=True)
except Exception as e:  # noqa: BLE001
    print("datastore table ERR:", type(e).__name__, str(e)[:150], flush=True)
