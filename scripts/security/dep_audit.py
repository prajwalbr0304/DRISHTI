#!/usr/bin/env python3
"""DRISHTI dependency vulnerability audit gate (Prompt 22 D.2).

Audits the SHIPPED dependency sets and BLOCKS on any high/critical finding that
is not an explicitly-accepted exception:

  * npm  — `npm audit --omit=dev` in web/ (production deps only; the static
           browser bundle). Dev-toolchain findings are out of shipped scope.
  * pip  — `pip-audit -r services/ml/requirements.appsail.txt` (the AppSail
           runtime image deps).

Accepted exceptions come from docs/deployment/security-exceptions.json (each
with a mitigation, owner and expiry). A finding whose id/alias is listed is
recorded as ACCEPTED; an EXPIRED exception fails the gate to force re-review.

Exit 0 only when there is no un-accepted high/critical finding and no expired
exception. Stdlib only (shells out to npm + pip-audit).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

BLOCKING = {"high", "critical"}


def _resolve(exe: str) -> str:
    """Resolve an executable cross-platform (npm -> npm.cmd on Windows)."""
    found = shutil.which(exe)
    if found:
        return found
    if sys.platform.startswith("win"):
        for ext in (".cmd", ".exe", ".bat"):
            found = shutil.which(exe + ext)
            if found:
                return found
    return exe


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    cmd = [_resolve(cmd[0]), *cmd[1:]]
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def _parse_json(text: str):
    """Parse the first JSON object in `text`, ignoring any trailing log lines
    (pip-audit/npm print a human summary after/around the JSON)."""
    start = text.index("{")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def _npm_audit(web: Path) -> dict:
    # Production deps only — the shipped bundle. npm audit exits non-zero when
    # vulns exist, so we parse JSON regardless of the code.
    code, stdout, stderr = _run(["npm", "audit", "--omit=dev", "--json"], cwd=web)
    try:
        data = _parse_json(stdout)
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "npm audit produced no parseable JSON", "raw": (stdout or stderr)[:400]}
    meta = data.get("metadata", {}).get("vulnerabilities", {})
    blocking = int(meta.get("high", 0)) + int(meta.get("critical", 0))
    return {"ok": blocking == 0, "severities": meta, "blocking_count": blocking}


def _pip_audit(repo: Path, req: Path, exceptions: dict) -> dict:
    accepted_ids = set()
    expired: list[str] = []
    today = dt.date.today()
    for exc in exceptions.get("pip_exceptions", []):
        exp = exc.get("expiry")
        is_expired = False
        if exp:
            try:
                is_expired = dt.date.fromisoformat(exp) < today
            except ValueError:
                is_expired = False
        for i in exc.get("ids", []):
            accepted_ids.add(i)
            if is_expired:
                expired.append(i)

    code, stdout, stderr = _run([sys.executable, "-m", "pip_audit", "-r", str(req),
                                 "--format", "json", "--progress-spinner", "off"], cwd=repo)
    try:
        data = _parse_json(stdout)
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "pip-audit produced no parseable JSON", "raw": (stdout or stderr)[:400]}

    deps = data.get("dependencies", data if isinstance(data, list) else [])
    un_accepted: list[dict] = []
    accepted: list[dict] = []
    for dep in deps:
        for v in dep.get("vulns", []):
            ids = {v.get("id", "")} | set(v.get("aliases", []))
            row = {"package": dep.get("name"), "version": dep.get("version"),
                   "id": v.get("id"), "aliases": v.get("aliases", []),
                   "fix": v.get("fix_versions", [])}
            if ids & accepted_ids:
                accepted.append(row)
            else:
                un_accepted.append(row)

    return {"ok": not un_accepted and not expired,
            "un_accepted": un_accepted, "accepted_count": len(accepted),
            "expired_exception_ids": sorted(set(expired))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    web = repo / "web"
    req = repo / "services" / "ml" / "requirements.appsail.txt"
    exc_path = repo / "docs" / "deployment" / "security-exceptions.json"
    exceptions = json.loads(exc_path.read_text(encoding="utf-8")) if exc_path.exists() else {}

    npm = _npm_audit(web)
    pip = _pip_audit(repo, req, exceptions)
    passed = bool(npm.get("ok")) and bool(pip.get("ok"))
    result = {"gate": "dependency_audit", "passed": passed, "npm": npm, "pip": pip}

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"[dep-audit] npm (production/--omit=dev): "
          f"{'PASS' if npm.get('ok') else 'FAIL'} — {npm.get('severities', npm.get('error'))}")
    if pip.get("error"):
        print(f"[dep-audit] pip-audit ERROR: {pip['error']}")
    else:
        print(f"[dep-audit] pip (AppSail runtime): {'PASS' if pip['ok'] else 'FAIL'} — "
              f"{len(pip['un_accepted'])} un-accepted, {pip['accepted_count']} accepted-exception finding(s).")
        for u in pip["un_accepted"]:
            print(f"    UN-ACCEPTED {u['package']} {u['version']} {u['id']} (fix {u['fix']})")
        if pip["expired_exception_ids"]:
            print(f"    EXPIRED exceptions (re-review required): {pip['expired_exception_ids']}")

    print(f"[dep-audit] {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
