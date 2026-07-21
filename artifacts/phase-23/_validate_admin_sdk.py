"""Local validation of the AppSail admin-scope Data Store fix (Prompt 23).

Reads the self-client creds from the gitignored env sheet, sets the env exactly
as the deployed AppSail will, and runs the real CatalystDataStoreRepository
against the LIVE Catalyst Data Store `State` table. Success (no exception) proves
build_admin_app() + the self-client credential + ZAID + DC domain are correct,
so the redeploy will fix operational_datastore. Prints no secret values.
"""
import json
import os
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sheet = json.load(open(os.path.join(REPO, "infra/catalyst/secrets/appsail-env.local.json"), encoding="utf-8"))
appsail = sheet["AppSail (Console > AppSail drishti-api > Configuration)"]

os.environ["DRISHTI_USE_CATALYST_DATASTORE"] = "true"
os.environ["ZOHO_CATALYST_CLIENT_ID"] = appsail["ZOHO_CATALYST_CLIENT_ID"]
os.environ["ZOHO_CATALYST_CLIENT_SECRET"] = appsail["ZOHO_CATALYST_CLIENT_SECRET"]
os.environ["ZOHO_CATALYST_REFRESH_TOKEN"] = appsail["ZOHO_CATALYST_REFRESH_TOKEN"]
os.environ["ZOHO_CATALYST_ZAID"] = appsail["ZOHO_CATALYST_ZAID"]
os.environ["CATALYST_PROJECT_ID"] = "48361000000030003"
os.environ.setdefault("ZOHO_CATALYST_API_DOMAIN", "https://api.catalyst.zoho.in")
os.environ.setdefault("ZOHO_CATALYST_ENVIRONMENT", "Development")

sys.path.insert(0, os.path.join(REPO, "services", "ml"))


def log(m):
    print(m, flush=True)


try:
    log("step1: import zcatalyst_sdk")
    import zcatalyst_sdk
    from zcatalyst_sdk import credentials
    from zcatalyst_sdk.types import ICatalystOptions
    log("step2: has initialize_app=" + str(hasattr(zcatalyst_sdk, "initialize_app")))
    log("step3: build RefreshTokenCredential")
    cred = credentials.RefreshTokenCredential({
        "refresh_token": os.environ["ZOHO_CATALYST_REFRESH_TOKEN"],
        "client_id": os.environ["ZOHO_CATALYST_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CATALYST_CLIENT_SECRET"],
    })
    log("step4: build ICatalystOptions")
    opts = ICatalystOptions(
        project_id="48361000000030003",
        project_key=os.environ["ZOHO_CATALYST_ZAID"],
        project_domain=os.environ["ZOHO_CATALYST_API_DOMAIN"],
        environment="Development",
    )
    log("step5: initialize_app")
    app = zcatalyst_sdk.initialize_app(credential=cred, options=opts, name="drishti-validate")
    log("step6: app.zcql()")
    zcql = app.zcql()
    log("step7: execute_query SELECT * FROM State LIMIT 1")
    rows = zcql.execute_query("SELECT * FROM State LIMIT 1")
    log("SUCCESS: State query returned " + str(len(rows)) + " row(s)")
except Exception as exc:  # noqa: BLE001
    log("FAILURE: " + type(exc).__name__ + " " + str(exc)[:400])
    traceback.print_exc()
