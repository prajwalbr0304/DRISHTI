#!/usr/bin/env python3
"""DRISHTI mandatory pre-deploy preflight (Prompt 22 E.5).

Blocks a Catalyst deploy unless the environment/project binding, the synthetic
marker, the DB-free AppSail posture and the no-duplicate invariants all hold.
Run this BEFORE any `catalyst deploy` step in the pipeline (no `|| true`).

  Offline (always, mandatory):
    * the bound project is EXACTLY DHRISTI / 48361000000030003 / org 60075362708
      (India DC) — never a duplicate or a different project;
    * catalyst.json declares the intended single client + the known function set;
    * appsail.deploy.json never REQUIRES DATABASE_URL (DB-free boot posture; it is
      an explicitly-optional server-to-server RDS connection per Prompt 23 Option A),
      pins a single instance, and does NOT enable wildcard CORS;
    * the synthetic-demo marker is present (web + backend).

  Live (with --require-live, mandatory in the pipeline; needs an authenticated
  Catalyst CLI): `catalyst project:list` shows the SAME project id and NO second
  "DHRISTI" project (no accidental duplicate).

Exit 0 only when every mandatory assertion holds. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED_PROJECT_ID = "48361000000030003"
EXPECTED_PROJECT_NAME = "DHRISTI"
EXPECTED_ORG = "60075362708"
HERE = Path(__file__).resolve().parent
INFRA_CATALYST = HERE.parent
REPO = INFRA_CATALYST.parents[1]


def _fail(problems: list, msg: str):
    problems.append(msg)


def check_project_binding(problems: list) -> dict:
    rc = json.loads((INFRA_CATALYST / ".catalystrc").read_text("utf-8"))
    projects = rc.get("projects", [])
    ids = {p.get("id") for p in projects}
    names = {p.get("name") for p in projects}
    if ids != {EXPECTED_PROJECT_ID}:
        _fail(problems, f".catalystrc project ids {ids} != exactly {{{EXPECTED_PROJECT_ID}}}")
    if names != {EXPECTED_PROJECT_NAME}:
        _fail(problems, f".catalystrc project names {names} != {{{EXPECTED_PROJECT_NAME}}}")
    envs = [e for p in projects for e in p.get("env", [])]
    if not any(e.get("id") == EXPECTED_ORG for e in envs):
        _fail(problems, f".catalystrc env/org id {EXPECTED_ORG} not found")
    return {"ids": sorted(ids), "names": sorted(names)}


def check_catalyst_json(problems: list) -> dict:
    cj = json.loads((INFRA_CATALYST / "catalyst.json").read_text("utf-8"))
    if "client" not in cj or "functions" not in cj:
        _fail(problems, "catalyst.json missing client/functions")
    targets = cj.get("functions", {}).get("targets", [])
    required_fns = {"gateway_api", "cron_forecast"}
    missing = required_fns - set(targets)
    if missing:
        _fail(problems, f"catalyst.json functions missing {missing}")
    return {"function_targets": len(targets), "client": "client" in cj}


def check_appsail_posture(problems: list) -> dict:
    ad = json.loads((INFRA_CATALYST / "appsail" / "appsail.deploy.json").read_text("utf-8"))
    # DB-free BOOT invariant (Prompt 23 Option A documented deviation): the AppSail
    # must never REQUIRE a database to start + serve the mandatory journeys, so
    # DATABASE_URL must not be a required key. It is an OPTIONAL server-to-server
    # RDS connection for the not-yet-migrated crime-domain CRUD (browser never
    # reaches RDS — enforced by the web_no_db_url gate). See appsail.deploy.json
    # database_url_policy.
    keys = ad.get("env_var_keys", {})
    if "DATABASE_URL" in keys.get("required", []):
        _fail(problems, "appsail.deploy.json: DATABASE_URL is REQUIRED (breaks DB-free boot posture)")
    if "DATABASE_URL" not in keys.get("optional", []):
        _fail(problems, "appsail.deploy.json: DATABASE_URL not declared under optional "
                        "(Prompt 23 Option A: it must be an explicitly-optional RDS connection)")
    inst = ad.get("instances", {})
    if not (inst.get("min") == 1 and inst.get("max") == 1):
        _fail(problems, f"appsail.deploy.json: instances not pinned to 1 (got {inst})")
    if ad.get("platform") != "linux/amd64":
        _fail(problems, f"appsail.deploy.json: platform != linux/amd64 (got {ad.get('platform')})")
    if "DRISHTI_CORS_ALLOW_ALL" in json.dumps(ad):
        _fail(problems, "appsail.deploy.json references DRISHTI_CORS_ALLOW_ALL (wildcard CORS)")
    return {"service": ad.get("service_name"), "instances": inst}


def check_synthetic_marker(problems: list) -> dict:
    prod = (REPO / "web" / ".env.production").read_text("utf-8")
    m = re.search(r"^VITE_DEMO_BADGE=(.+)$", prod, re.MULTILINE)
    if not m or not m.group(1).strip():
        _fail(problems, "web/.env.production missing non-empty VITE_DEMO_BADGE")
    cfg = (REPO / "services" / "ml" / "app" / "config.py").read_text("utf-8")
    if "synthetic_hackathon" not in cfg:
        _fail(problems, "app/config.py missing synthetic_hackathon marker")
    return {"web_badge": bool(m), "backend_marker": "synthetic_hackathon" in cfg}


def _resolve(exe: str) -> str:
    f = shutil.which(exe)
    if f:
        return f
    if sys.platform.startswith("win"):
        for ext in (".cmd", ".exe", ".bat"):
            f = shutil.which(exe + ext)
            if f:
                return f
    return exe


def check_no_duplicate_live(problems: list, require_live: bool) -> dict:
    """Read-only Catalyst check: confirm the same project id and no duplicate
    'DHRISTI' project. Best-effort unless --require-live."""
    catalyst = _resolve("catalyst")
    # NON-INTERACTIVE: stdin=DEVNULL so the CLI cannot block on an org-selection
    # prompt (a local-CLI artifact; the pipeline runner is bound + non-interactive).
    try:
        p = subprocess.run([catalyst, "project:list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           stdin=subprocess.DEVNULL, cwd=str(INFRA_CATALYST))
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        if require_live:
            _fail(problems, f"catalyst CLI unavailable/timeout for live no-duplicate check: {e}")
        return {"live": "unavailable"}
    out = (p.stdout or "") + (p.stderr or "")
    # An interactive/org-prompt or error means we cannot confirm here.
    if p.returncode != 0 or "Select a Catalyst" in out or EXPECTED_PROJECT_ID not in out:
        if require_live:
            _fail(problems, "live no-duplicate check could not confirm non-interactively "
                            "(bind a project + authenticate the runner before deploy)")
        return {"live": "inconclusive"}
    dhristi_count = len(re.findall(r"\bDHRISTI\b", out, re.IGNORECASE))
    if dhristi_count > 1:
        _fail(problems, f"live: {dhristi_count} projects named DHRISTI (duplicate)")
    return {"live": "ok", "dhristi_count": dhristi_count, "id_present": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-live", action="store_true",
                    help="fail if the live Catalyst no-duplicate check cannot run (pipeline mode)")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    problems: list[str] = []
    detail = {
        "project_binding": check_project_binding(problems),
        "catalyst_json": check_catalyst_json(problems),
        "appsail_posture": check_appsail_posture(problems),
        "synthetic_marker": check_synthetic_marker(problems),
        "no_duplicate": check_no_duplicate_live(problems, args.require_live),
    }
    passed = not problems
    result = {"gate": "preflight_deploy", "passed": passed,
              "require_live": args.require_live, "detail": detail, "problems": problems}

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"[preflight-deploy] project={detail['project_binding']['names']} "
          f"{detail['project_binding']['ids']} | appsail={detail['appsail_posture']} | "
          f"live={detail['no_duplicate'].get('live')}")
    for p in problems:
        print(f"  BLOCK: {p}")
    print(f"[preflight-deploy] {'PASS — safe to deploy' if passed else 'FAIL — deploy blocked'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
