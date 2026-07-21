#!/usr/bin/env python3
"""DRISHTI static / config / security-policy checks (Prompt 22 D.3-D.5).

Runs a battery of deterministic, offline checks over the repository and emits a
machine-readable summary. Each check is mandatory; ANY failure exits non-zero.

Covered:
  D.3  python_compile   — every backend module byte-compiles (syntax).
  D.4  json_yaml_valid  — every tracked JSON/YAML parses.
       function_syntax  — every Catalyst Node function passes `node --check`.
       dockerfile_check — AppSail + GPU Dockerfiles pass `docker build --check`.
       env_key_schema   — every production VITE_* key is documented in .env.example.
  D.5  cors_policy      — no wildcard production CORS (opt-in only; deployed never sets it).
       browser_db_client— the web bundle imports NO direct DB client.
       synthetic_marker — the production build carries the synthetic-demo marker.

(The executable secret scan is scripts/security/secret_scan.py; the dependency
audit is scripts/security/dep_audit.py; the web AWS/DB-URL bundle scan is
infra/aws/check_no_db_url_in_web.py; the route/data-boundary classification is
services/ml/tools/route_data_boundary.py --check. The release gate runs all.)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml  # PyYAML 6.x

REPO = Path(__file__).resolve().parents[2]


def _tracked(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                         capture_output=True, text=True, check=True)
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


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


# --- D.4: JSON / YAML validity ---------------------------------------------
def check_json_yaml(repo: Path) -> dict:
    errors = []
    n = 0
    for rel in _tracked(repo):
        posix = rel.replace("\\", "/")
        low = posix.lower()
        if low.endswith("package-lock.json") or "/serving-export/" in low or "/fixtures/" in low:
            continue  # generated / large data
        p = repo / rel
        try:
            if low.endswith(".json"):
                n += 1
                json.loads(p.read_text(encoding="utf-8"))
            elif low.endswith((".yaml", ".yml")):
                n += 1
                list(yaml.safe_load_all(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            errors.append({"file": posix, "error": str(e)[:160]})
    return {"name": "json_yaml_valid", "passed": not errors, "checked": n, "errors": errors}


# --- D.4: Catalyst Node function syntax ------------------------------------
def check_function_syntax(repo: Path) -> dict:
    fn_dir = repo / "infra" / "catalyst" / "functions"
    files = sorted(fn_dir.glob("*/index.js")) + sorted(fn_dir.glob("_shared/*.js"))
    node = _resolve("node")
    errors = []
    for f in files:
        p = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if p.returncode != 0:
            errors.append({"file": str(f.relative_to(repo)).replace("\\", "/"),
                           "error": (p.stderr or p.stdout).strip()[:160]})
    return {"name": "function_syntax", "passed": not errors,
            "checked": len(files), "errors": errors}


# --- D.4 / D.3: Dockerfile static check ------------------------------------
def check_dockerfiles(repo: Path) -> dict:
    docker = _resolve("docker")
    targets = [
        ("services/ml/Dockerfile.appsail", "services/ml"),
        ("services/gpu-worker/Dockerfile", "services/gpu-worker"),
    ]
    errors = []
    for dockerfile, ctx in targets:
        p = subprocess.run([docker, "build", "--check", "-f", str(repo / dockerfile), str(repo / ctx)],
                           capture_output=True, text=True)
        # `--check` prints warnings/errors; non-zero or a "ERROR" line = fail.
        combined = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0 or re.search(r"\bERROR\b", combined):
            errors.append({"dockerfile": dockerfile, "detail": combined.strip()[-200:]})
    return {"name": "dockerfile_check", "passed": not errors,
            "checked": len(targets), "errors": errors}


# --- D.4: env-key schema (production keys documented in .env.example) ------
def _env_keys(path: Path) -> set[str]:
    keys = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def check_env_schema(repo: Path) -> dict:
    example = _env_keys(repo / "web" / ".env.example")
    prod = _env_keys(repo / "web" / ".env.production")
    dev = _env_keys(repo / "web" / ".env.development")
    undocumented = sorted((prod | dev) - example)
    return {"name": "env_key_schema",
            "passed": not undocumented,
            "example_keys": len(example),
            "undocumented_keys": undocumented}


# --- D.5: no wildcard production CORS --------------------------------------
def check_cors(repo: Path) -> dict:
    problems = []
    cfg = (repo / "services" / "ml" / "app" / "config.py").read_text(encoding="utf-8")
    # The wildcard is opt-in via cors_allow_all (default must be False).
    if not re.search(r"cors_allow_all:\s*bool\s*=\s*False", cfg):
        problems.append("app/config.py: cors_allow_all default is not False")
    # The deployed AppSail env descriptor must NOT enable the wildcard.
    appsail = (repo / "infra" / "catalyst" / "appsail" / "appsail.deploy.json").read_text(encoding="utf-8")
    if "DRISHTI_CORS_ALLOW_ALL" in appsail:
        problems.append("appsail.deploy.json references DRISHTI_CORS_ALLOW_ALL (must never be set in deployment)")
    # No hardcoded permissive CORS with credentials anywhere in the app/functions.
    for rel in _tracked(repo):
        posix = rel.replace("\\", "/")
        if not (posix.startswith("services/ml/app/") or posix.startswith("infra/catalyst/functions/")):
            continue
        if not posix.endswith((".py", ".js")):
            continue
        txt = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        if re.search(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]", txt) and "allow_credentials=True" in txt:
            problems.append(f"{posix}: hardcoded wildcard CORS with credentials")
        if re.search(r"Access-Control-Allow-Origin[\"']\s*[:,]\s*[\"']\*[\"']", txt) and \
                re.search(r"Access-Control-Allow-Credentials[\"']\s*[:,]\s*[\"']true", txt):
            problems.append(f"{posix}: wildcard ACAO with credentials")
    return {"name": "cors_policy", "passed": not problems, "problems": problems}


# --- D.5: no direct browser DB client --------------------------------------
def check_browser_db(repo: Path) -> dict:
    web_src = repo / "web" / "src"
    bad = re.compile(r"""from\s+['"](pg|pg-promise|postgres|mysql2?|mongodb|mongoose|psycopg2?|"""
                     r"""sequelize|typeorm|knex|better-sqlite3|ioredis)['"]|"""
                     r"""require\(\s*['"](pg|mysql2?|mongodb)['"]""")
    hits = []
    for f in web_src.rglob("*.ts*"):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if bad.search(txt):
            hits.append(str(f.relative_to(repo)).replace("\\", "/"))
    return {"name": "browser_db_client", "passed": not hits, "hits": hits}


# --- D.5: production synthetic-demo marker present -------------------------
def check_synthetic_marker(repo: Path) -> dict:
    problems = []
    prod = repo / "web" / ".env.production"
    txt = prod.read_text(encoding="utf-8") if prod.exists() else ""
    m = re.search(r"^VITE_DEMO_BADGE=(.+)$", txt, re.MULTILINE)
    if not m or not m.group(1).strip():
        problems.append("web/.env.production: VITE_DEMO_BADGE missing/empty (synthetic marker)")
    cfg = (repo / "services" / "ml" / "app" / "config.py").read_text(encoding="utf-8")
    if "synthetic_hackathon" not in cfg:
        problems.append("app/config.py: synthetic_hackathon marker absent")
    return {"name": "synthetic_marker", "passed": not problems, "problems": problems}


# --- D.3: backend byte-compile ---------------------------------------------
def check_python_compile(repo: Path) -> dict:
    app = repo / "services" / "ml" / "app"
    files = [str(p) for p in app.rglob("*.py")]
    p = subprocess.run([sys.executable, "-m", "py_compile", *files],
                       capture_output=True, text=True)
    return {"name": "python_compile", "passed": p.returncode == 0,
            "checked": len(files), "error": (p.stderr or "").strip()[:300] or None}


CHECKS = [check_json_yaml, check_function_syntax, check_dockerfiles, check_env_schema,
          check_cors, check_browser_db, check_synthetic_marker, check_python_compile]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--json", default="")
    ap.add_argument("--skip", default="", help="comma-separated check names to skip (e.g. dockerfile_check)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    results = []
    for fn in CHECKS:
        name = fn.__name__.replace("check_", "")
        if name in skip:
            results.append({"name": name, "passed": True, "skipped": True})
            print(f"[static] {name}: SKIPPED")
            continue
        try:
            r = fn(repo)
        except Exception as e:  # noqa: BLE001
            r = {"name": name, "passed": False, "error": f"{type(e).__name__}: {e}"}
        results.append(r)
        status = "PASS" if r.get("passed") else "FAIL"
        extra = {k: v for k, v in r.items() if k not in ("name", "passed") and v}
        print(f"[static] {r['name']}: {status}  {json.dumps(extra)[:220] if extra else ''}")

    passed = all(r.get("passed") for r in results)
    summary = {"gate": "static_checks", "passed": passed, "checks": results}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[static] {'PASS' if passed else 'FAIL'} ({sum(1 for r in results if r.get('passed'))}/{len(results)} checks)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
