"""Validate the REST-backed CatalystDataStoreRepository end-to-end against the
live IN DC Data Store: query (readiness probe), upsert (also imports the State
row), get, and re-query. No SDK. Hard timeouts."""
import json
import os
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))["AppSail (Console > AppSail drishti-api > Configuration)"]

os.environ["DRISHTI_USE_CATALYST_DATASTORE"] = "true"
os.environ["ZOHO_CATALYST_CLIENT_ID"] = a["ZOHO_CATALYST_CLIENT_ID"]
os.environ["ZOHO_CATALYST_CLIENT_SECRET"] = a["ZOHO_CATALYST_CLIENT_SECRET"]
os.environ["ZOHO_CATALYST_REFRESH_TOKEN"] = a["ZOHO_CATALYST_REFRESH_TOKEN"]
os.environ["ZOHO_CATALYST_ZAID"] = a["ZOHO_CATALYST_ZAID"]
os.environ["CATALYST_PROJECT_ID"] = "48361000000030003"

sys.path.insert(0, os.path.join(REPO, "services", "ml"))

try:
    from app.datastore.repository import CatalystDataStoreRepository
    repo = CatalystDataStoreRepository()
    print("1) readiness probe query('State', limit=1):", repo.query("State", limit=1), flush=True)
    print("2) upsert state:1 ...", flush=True)
    stored = repo.upsert("State", "state:1", {
        "Active": True, "NationalityID": 1, "StateID": 1, "StateName": "Karnataka"})
    print("   stored ROWID:", (stored or {}).get("ROWID"), "StateName:", (stored or {}).get("StateName"), flush=True)
    print("3) get state:1:", repo.get("State", "state:1"), flush=True)
    print("4) query all State:", repo.query("State", limit=5), flush=True)
    print("SUCCESS", flush=True)
except Exception as exc:  # noqa: BLE001
    print("FAILURE:", type(exc).__name__, str(exc)[:400], flush=True)
    traceback.print_exc()
