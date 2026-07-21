#!/usr/bin/env python3
"""Generate an exact Catalyst Console setup guide (Prompt 23).

Because Catalyst Data Store tables and Stratus buckets can ONLY be created in the
Console (no SDK/API/CLI — confirmed by Catalyst docs), this script turns the
repo's authoritative schemas into a precise, copy-paste table-creation guide so
the manual Console work is fast and correct. It does NOT create anything; it only
emits Markdown.

Reads:
  - ds-schema/board-tables.schema.json      (6 Investigation Board tables)
  - ds-schema/disaster-tables.schema.json   (14 Disaster Response tables)
  - ds-import/serving-export/<T>.csv        (header row -> reference-table columns)

Emits: docs/deployment/CATALYST_CONSOLE_SETUP.md
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
INFRA_CATALYST = HERE.parent
REPO = INFRA_CATALYST.parents[1]
EXPORT = INFRA_CATALYST / "ds-import" / "serving-export"
OUT = REPO / "docs" / "deployment" / "CATALYST_CONSOLE_SETUP.md"

# schema vocabulary -> Catalyst Data Store column type
DS_TYPE = {
    "int": "BigInt", "text": "Varchar", "bigtext": "Text", "bool": "Boolean",
    "numeric": "Double", "json": "Text", "timestamp": "DateTime",
}

# Reference tables to include (name -> None means infer columns from the CSV header).
REFERENCE_TABLES = [
    "State", "District", "CaseCategory", "CaseStatusMaster", "Unit",
    "Employee", "CaseMaster",
]
# Columns that cannot be represented in Data Store (PostGIS geometry) -> excluded.
EXCLUDE_COLS = {"geom"}

# Trigger table for the ONE mandatory Signal (prediction-requested). A row_inserted
# with state='approved' fires the drishti_datastore publisher -> prediction_event.
# Not in the board/disaster schemas; defined inline. Columns match what
# infra/catalyst/functions/prediction_event/index.js reads from the event data.
PREDICTION_REQUEST_TABLE = {
    "name": "PredictionRequest",
    "primary_key": "PredictionRequestID",
    "columns": [
        {"name": "PredictionRequestID", "type": "text", "nullable": False},
        {"name": "state", "type": "text", "nullable": False},        # 'approved' triggers the rule
        {"name": "task", "type": "text", "nullable": True},
        {"name": "requested_backend", "type": "text", "nullable": True},
        {"name": "idempotency_key", "type": "text", "nullable": False},
    ],
}


def infer_type(col: str) -> str:
    c = col.lower()
    if col == "ExternalID":
        return "Varchar (Unique, Mandatory)"
    if c.endswith("id"):
        return "BigInt"
    if c in ("active",) or c.startswith("is"):
        return "Boolean"
    if c.endswith("date") or c.endswith("at") or c == "employeedob":
        return "DateTime"
    if c in ("latitude", "longitude") or c.endswith("lat") or c.endswith("lon"):
        return "Double"
    if c.endswith("fts") or c == "brieffacts":
        return "Text"
    return "Varchar"


def board_disaster_tables(schema_path: Path) -> list[dict]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    order = schema.get("provision_order") or [t["name"] for t in schema["tables"]]
    by_name = {t["name"]: t for t in schema["tables"]}
    return [by_name[n] for n in order if n in by_name]


def render_schema_table(t: dict) -> list[str]:
    lines = [f"### `{t['name']}`  (PK: `{t['primary_key']}`"
             + (", append-only" if t.get("append_only") else "") + ")",
             "", "| Column | Catalyst type | Mandatory |", "|---|---|---|"]
    for c in t["columns"]:
        ds = DS_TYPE.get(c["type"], c["type"])
        lines.append(f"| `{c['name']}` | {ds} | {'yes' if not c['nullable'] else 'no'} |")
    lines.append("| `ExternalID` | Varchar (**Unique**) | yes |")
    lines.append("")
    return lines


def render_reference_table(name: str) -> list[str]:
    csv = EXPORT / f"{name}.csv"
    if not csv.exists():
        return [f"### `{name}`", "", "_serving-export CSV missing — regenerate with "
                "`export_serving_subset.py`._", ""]
    header = csv.read_text(encoding="utf-8").splitlines()[0].split(",")
    cols = [c for c in header if c not in EXCLUDE_COLS]
    excluded = [c for c in header if c in EXCLUDE_COLS]
    lines = [f"### `{name}`", "", "| Column | Catalyst type | Mandatory |", "|---|---|---|"]
    for c in cols:
        mand = "yes" if c == "ExternalID" else "no"
        lines.append(f"| `{c}` | {infer_type(c)} | {mand} |")
    if excluded:
        lines.append(f"\n_Excluded (PostGIS geometry, not supported in Data Store): "
                     f"{', '.join('`'+e+'`' for e in excluded)} — the app derives "
                     f"lat/long separately._")
    lines.append("")
    return lines


def main() -> int:
    board = board_disaster_tables(HERE / "board-tables.schema.json")
    disaster = board_disaster_tables(HERE / "disaster-tables.schema.json")

    out: list[str] = []
    out += [
        "# DRISHTI — Catalyst Console setup guide (Prompt 23)",
        "",
        "> **Auto-generated** by `infra/catalyst/ds-schema/generate_console_guide.py` "
        "from the repo's authoritative schemas. Data Store tables and Stratus buckets "
        "can **only** be created in the Catalyst Console (no SDK/API/CLI — confirmed by "
        "Catalyst docs), so this is the exact, minimal manual checklist. Everything "
        "else (data import, deploy, verification) is automated by Kiro.",
        "",
        "**Project:** DHRISTI `48361000000030003`, org `60075362708`, India DC, Development.",
        "",
        "## Column conventions",
        "",
        "- Catalyst auto-adds `ROWID`, `CREATORID`, `CREATEDTIME`, `MODIFIEDTIME` to every "
        "table — do **not** add those.",
        "- Add **`ExternalID`** (Varchar, **Unique**, Mandatory) to every table — it is the "
        "idempotent-upsert key Kiro's `ds:import` uses.",
        "- Type mapping used below: int→**BigInt**, text→**Varchar**, bigtext→**Text**, "
        "bool→**Boolean**, numeric→**Double**, json→**Text**, timestamp→**DateTime**.",
        "",
        "---",
        "",
        "## Step 1 — Stratus buckets (Console → Stratus → Create Bucket)",
        "",
        "Create 3 **private, versioned** buckets, then give the names to Kiro:",
        "",
        "| Logical | Suggested name | Visibility | Versioning |",
        "|---|---|---|---|",
        "| evidence | `drishti-evidence` | Private | On |",
        "| import | `drishti-import` | Private | On |",
        "| report | `drishti-report` | Private | On |",
        "",
        "---",
        "",
        "## Step 2 — MVP Data Store tables (proves the full live path)",
        "",
        "Create these first. `State` is the readiness probe; the 6 Board tables are "
        "Data Store-native and the app writes them live (no import needed) — this alone "
        "proves Auth → Gateway → AppSail → Data Store → Stratus. `PredictionRequest` is "
        "the trigger table for the ONE mandatory Signal (a `row_inserted` with "
        "`state='approved'` fires `prediction_event`).",
        "",
        "> **Live-journey scope (honest):** Board + Disaster are Data Store-native and run "
        "live on the AppSail. The FIR/case/evidence-metadata/chat transactional flows are "
        "**postgres-backed** (analytics plane) and the operational AppSail is intentionally "
        "denied a `DATABASE_URL`, so those run in the local full-stack, not on the deployed "
        "AppSail. The deployed demo proves the Data Store-native operational journeys + "
        "evidence-file upload (Stratus) + the auth/gateway/security chain.",
        "",
    ]
    out += render_reference_table("State")
    for t in board:
        out += render_schema_table(t)
    # PredictionRequest — the trigger table for the ONE mandatory Signal
    # (prediction-requested: drishti_datastore row_inserted -> prediction_event).
    # Not part of the board/disaster schemas; defined inline here.
    out += render_schema_table(PREDICTION_REQUEST_TABLE)

    out += [
        "---", "",
        "## Step 3 — Reference tables (for Ask DRISHTI / dashboard reads)",
        "",
        "Create these to serve real read data; Kiro then imports the rows "
        "(`ds:import`, idempotent by `ExternalID`).",
        "",
    ]
    for name in REFERENCE_TABLES:
        if name == "State":
            continue
        out += render_reference_table(name)

    out += [
        "---", "",
        "## Step 4 — Disaster Response tables (optional journey, 14 tables)",
        "",
        "Data Store-native; the app seeds golden rows at runtime. Create if you want the "
        "Disaster demo.",
        "",
    ]
    for t in disaster:
        out += render_schema_table(t)

    out += [
        "---", "",
        "## Step 5 — hand back to Kiro",
        "",
        "Tell Kiro the **3 bucket names** and the **API Gateway URL**. Kiro then: sets "
        "function env, imports reference/operational rows, builds + deploys the frontend "
        "to Slate, and runs the full live verification (six roles, Signal + cron, "
        "Data Store/Stratus checks, CORS/replay/bypass) with evidence.",
        "",
        "Non-table Console items are listed in `docs/deployment/CATALYST_LIVE_INVENTORY.md` "
        "§3 (AppSail env from `infra/catalyst/secrets/appsail-env.local.json`, API Gateway "
        "routes, Auth users, Signals rule, cron).",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out), encoding="utf-8")
    n_tables = 1 + len(board) + 1 + (len(REFERENCE_TABLES) - 1) + len(disaster)
    print(f"wrote {OUT.relative_to(REPO)}  ({n_tables} tables documented: "
          f"1 State + {len(board)} board + 1 PredictionRequest + {len(REFERENCE_TABLES)-1} "
          f"reference + {len(disaster)} disaster)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
