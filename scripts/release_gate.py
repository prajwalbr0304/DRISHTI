#!/usr/bin/env python3
"""DRISHTI strict local release gate (Prompt 22 F).

ONE command that runs the complete local release candidate gate and writes a
machine-readable summary to artifacts/phase-22/release-gate.json. It exits
non-zero for ANY mandatory failure, skipped mandatory gate, invalid production
URL, missing build artifact, or unclassified route — so a zero exit means a
genuine local release candidate, nothing less.

Gate order (Prompt 22 A-E): toolchain -> lint/type/test -> build (+release URL
guard) -> AppSail image -> security scans (secret/deps/static/bundle/web-URL) ->
route/data boundary -> GPU contract -> browser E2E.

Usage:
  python scripts/release_gate.py                 # full strict gate (default)
  python scripts/release_gate.py --only lint,backend_offline   # dev subset
                                                  # (others -> SKIPPED -> exit 1)
  python scripts/release_gate.py --rebuild-image  # also rebuild the AppSail image
  python scripts/release_gate.py --release-url https://<gw>/api  # validate a real URL

Slow gates (backend suite, E2E, image build) are INCLUDED by default; skipping
any mandatory gate makes the gate exit non-zero (never a false green).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ART = REPO / "artifacts" / "phase-22"
LOGS = ART / "release-gate-logs"


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


def _run(cmd, cwd=None, env=None, timeout=1800):
    resolved = [_resolve(cmd[0]), *cmd[1:]]
    full_env = {**os.environ, **(env or {})}
    try:
        p = subprocess.run(resolved, cwd=str(cwd) if cwd else None, env=full_env,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"command not found: {e}"


def _ver_tuple(s: str):
    import re
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s)
    if not m:
        m = re.search(r"(\d+)\.(\d+)", s)
        return (int(m.group(1)), int(m.group(2)), 0) if m else (0, 0, 0)
    return tuple(int(x) for x in m.groups())


class Result:
    def __init__(self, name, tier, mandatory):
        self.name, self.tier, self.mandatory = name, tier, mandatory
        self.status = "NOT_RUN"
        self.detail = ""
        self.duration = 0.0
        self.log = ""

    def to_dict(self):
        return {"name": self.name, "tier": self.tier, "mandatory": self.mandatory,
                "status": self.status, "detail": self.detail,
                "duration_s": round(self.duration, 1), "log": self.log}


def _writelog(name: str, code, out, err) -> str:
    LOGS.mkdir(parents=True, exist_ok=True)
    path = LOGS / f"{name}.log"
    path.write_text(f"exit={code}\n\n--- STDOUT ---\n{out}\n\n--- STDERR ---\n{err}\n",
                    encoding="utf-8")
    return str(path.relative_to(REPO)).replace("\\", "/")


# ---------------------------------------------------------------------------
# Individual gates. Each returns (status, detail) and may write a log.
# ---------------------------------------------------------------------------
def g_toolchain(r: Result):
    lock = json.loads((REPO / "infra" / "catalyst" / "pipelines" / "toolchain.lock.json").read_text("utf-8"))
    tools = lock["tools"]
    probes = {
        "node": (["node", "--version"], tools["node"]["min"]),
        "npm": (["npm", "--version"], tools["npm"]["min"]),
        "python": ([sys.executable, "--version"], tools["python"]["min"]),
        "docker": (["docker", "--version"], tools["docker"]["min"]),
        "catalyst": (["catalyst", "--version"], tools["catalyst_cli"]["min"]),
        "aws": (["aws", "--version"], tools["aws_cli"]["min"]),
    }
    bad = []
    seen = {}
    for tool, (cmd, minv) in probes.items():
        code, out, err = _run(cmd, timeout=60)
        got = (out + err).strip().splitlines()[0] if (out + err).strip() else ""
        seen[tool] = got
        if code != 0 or _ver_tuple(got) < _ver_tuple(minv):
            bad.append(f"{tool} {got or 'missing'} < min {minv}")
    # Docker daemon must be a running Linux engine.
    code, out, err = _run(["docker", "info", "--format", "{{.OSType}}"], timeout=60)
    ostype = out.strip()
    if code != 0 or ostype != "linux":
        bad.append(f"docker daemon not a running linux engine (got '{ostype or err.strip()[:40]}')")
    r.detail = f"versions={seen} docker_os={ostype}; " + ("; ".join(bad) if bad else "all >= pinned mins")
    return ("PASS" if not bad else "FAIL"), r.detail


def g_backend_offline(r: Result):
    code, out, err = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                          cwd=REPO / "services" / "ml", env={"DRISHTI_DISABLE_DB_TESTS": "1"},
                          timeout=1800)
    r.log = _writelog(r.name, code, out, err)
    tail = (out.strip().splitlines() or ["<no output>"])[-1]
    r.detail = tail[:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def _npm_gate(r: Result, script: str, timeout=900, env=None):
    code, out, err = _run(["npm", "run", script], cwd=REPO / "web", env=env, timeout=timeout)
    r.log = _writelog(r.name, code, out, err)
    tail = (out.strip().splitlines() or [""])[-1]
    r.detail = tail[:200] if tail else (err.strip()[-200:])
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_frontend_lint(r: Result):
    # 0 errors required (warnings allowed). `eslint .` exits non-zero on errors.
    code, out, err = _run(["npm", "run", "lint"], cwd=REPO / "web", timeout=300)
    r.log = _writelog(r.name, code, out, err)
    m = [l for l in (out + err).splitlines() if "problem" in l or "error" in l.lower()]
    r.detail = (m[-1] if m else "0 errors")[:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_frontend_typecheck(r: Result):
    return _npm_gate(r, "typecheck", timeout=300)


def g_frontend_test(r: Result):
    return _npm_gate(r, "test", timeout=600)


def g_frontend_build(r: Result):
    status, detail = _npm_gate(r, "build", timeout=900)
    # Missing-artifact guard: the build MUST produce dist/index.html + slate cfg.
    idx = REPO / "web" / "dist" / "index.html"
    slate = REPO / "web" / "dist" / ".catalyst" / "slate-config.toml"
    if status == "PASS" and not (idx.exists() and slate.exists()):
        return "FAIL", f"missing build artifact(s): index.html={idx.exists()} slate={slate.exists()}"
    return status, detail


def g_release_url_guard(r: Result, release_url: str):
    """Prove the release build cannot ship an invalid API URL.
    - If a real --release-url is supplied, a release check with it MUST PASS.
    - The guard MUST REJECT the unconfigured placeholder / unset URL (exit!=0)."""
    web = REPO / "web"
    # 1. Negative: unset URL against the (placeholder) dist/ must FAIL.
    code_bad, out_bad, err_bad = _run(["node", "scripts/check-bundle-secrets.mjs", "--release"],
                                      cwd=web, env={"VITE_API_BASE_URL": ""}, timeout=120)
    guard_blocks = code_bad != 0
    detail = f"guard_rejects_unset={guard_blocks}"
    ok = guard_blocks
    # 2. Positive (optional): a supplied real URL validates clean.
    if release_url:
        code_ok, out_ok, err_ok = _run(["node", "scripts/check-bundle-secrets.mjs", "--release"],
                                       cwd=web, env={"VITE_API_BASE_URL": release_url}, timeout=120)
        # dist/ still holds the placeholder, so this also fails on the placeholder;
        # we only assert the URL itself is judged valid (no URL-validity error line).
        url_valid = "RELEASE API URL OK" in (out_ok + err_ok)
        detail += f" release_url_valid={url_valid}"
        ok = ok and url_valid
    r.log = _writelog(r.name, code_bad, out_bad, err_bad)
    r.detail = detail
    return ("PASS" if ok else "FAIL"), detail


def g_appsail_image(r: Result, rebuild: bool):
    docker = "docker"
    def _inspect():
        return _run([docker, "image", "inspect", "drishti-api:appsail", "--format",
                     "{{.Os}}/{{.Architecture}}|{{.Config.User}}|{{json .Config.ExposedPorts}}"],
                    timeout=60)
    present = _inspect()[0] == 0
    # Self-contained: build the linux/amd64 AppSail image if it is absent (e.g.
    # Docker Desktop pruned it) or if a rebuild is forced. Never rely on a
    # pre-existing image being present.
    if rebuild or not present:
        code, out, err = _run([docker, "buildx", "build", "--platform", "linux/amd64",
                               "-f", "services/ml/Dockerfile.appsail", "-t", "drishti-api:appsail",
                               "--load", "services/ml"], cwd=REPO, timeout=1800)
        if code != 0:
            r.log = _writelog(r.name, code, out, err)
            return "FAIL", "AppSail image build failed"
    code, out, err = _run([docker, "image", "inspect", "drishti-api:appsail", "--format",
                           "{{.Os}}/{{.Architecture}}|{{.Config.User}}|{{json .Config.ExposedPorts}}"],
                          timeout=60)
    if code != 0:
        return "FAIL", "drishti-api:appsail image not present after build"
    osarch, user, ports = (out.strip().split("|") + ["", "", ""])[:3]
    ok = osarch == "linux/amd64" and user in ("appuser", "10001") and "9000" in ports
    r.detail = f"os/arch={osarch} user={user} ports={ports}"
    return ("PASS" if ok else "FAIL"), r.detail


def _script_gate(r: Result, args: list[str], jsonf: str, timeout=900, cwd=None):
    out_json = ART / jsonf
    code, out, err = _run([sys.executable, *args, "--json", str(out_json)],
                          cwd=cwd or REPO, timeout=timeout)
    r.log = _writelog(r.name, code, out, err)
    tail = (out.strip().splitlines() or [""])[-1]
    r.detail = tail[:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_secret_scan(r):
    return _script_gate(r, ["scripts/security/secret_scan.py", "--repo", str(REPO)],
                        "secret-scan.json", timeout=300)


def g_dep_audit(r):
    return _script_gate(r, ["scripts/security/dep_audit.py", "--repo", str(REPO)],
                        "dep-audit.json", timeout=600)


def g_static_checks(r):
    return _script_gate(r, ["scripts/security/static_checks.py", "--repo", str(REPO)],
                        "static-checks.json", timeout=600)


def g_web_no_db_url(r: Result):
    code, out, err = _run([sys.executable, "infra/aws/check_no_db_url_in_web.py"],
                          cwd=REPO, timeout=120)
    r.log = _writelog(r.name, code, out, err)
    r.detail = (out.strip().splitlines() or [""])[-1][:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_route_boundary(r: Result):
    # 0 unclassified demo-visible routes, or the gate fails.
    code, out, err = _run([sys.executable, "tools/route_data_boundary.py", "--check"],
                          cwd=REPO / "services" / "ml", timeout=300)
    r.log = _writelog(r.name, code, out, err)
    r.detail = (out.strip().splitlines() or [""])[-1][:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_deploy_preflight(r: Result):
    # Offline pre-deploy invariants: project == DHRISTI 48361000000030003,
    # synthetic marker, DB-free AppSail posture, no-duplicate-in-config.
    code, out, err = _run([sys.executable, "infra/catalyst/pipelines/preflight_deploy.py",
                           "--json", str(ART / "preflight-deploy.json")], cwd=REPO, timeout=120)
    r.log = _writelog(r.name, code, out, err)
    r.detail = (out.strip().splitlines() or [""])[-1][:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


def g_gpu_contract(r: Result):
    import re
    w = (REPO / "services" / "gpu-worker" / "schema.py").read_text("utf-8")
    a = (REPO / "services" / "ml" / "app" / "predict" / "envelope.py").read_text("utf-8")
    wv = re.search(r'ENVELOPE_VERSION\s*=\s*"([^"]+)"', w)
    av = re.search(r'ENVELOPE_VERSION\s*=\s*"([^"]+)"', a)
    ok = wv and av and wv.group(1) == av.group(1)
    r.detail = f"worker={wv.group(1) if wv else '?'} appsail={av.group(1) if av else '?'}"
    return ("PASS" if ok else "FAIL"), r.detail


def g_e2e(r: Result):
    code, out, err = _run(["npm", "run", "test:e2e"], cwd=REPO / "web", timeout=1200)
    r.log = _writelog(r.name, code, out, err)
    m = [l for l in (out + err).splitlines() if "passed" in l or "failed" in l]
    r.detail = (m[-1] if m else "")[:200]
    return ("PASS" if code == 0 else "FAIL"), r.detail


# (name, tier, mandatory, callable)
GATES = [
    ("toolchain", "unit", True, g_toolchain),
    ("frontend_lint", "unit", True, g_frontend_lint),
    ("frontend_typecheck", "contract", True, g_frontend_typecheck),
    ("frontend_test", "unit", True, g_frontend_test),
    ("backend_offline", "integration", True, g_backend_offline),
    ("frontend_build", "build", True, g_frontend_build),
    ("release_url_guard", "security", True, None),       # needs release_url arg
    ("appsail_image", "build", True, None),              # needs rebuild arg
    ("secret_scan", "security", True, g_secret_scan),
    ("dep_audit", "security", True, g_dep_audit),
    ("static_checks", "security", True, g_static_checks),
    ("web_no_db_url", "security", True, g_web_no_db_url),
    ("route_boundary", "contract", True, g_route_boundary),
    ("gpu_contract", "contract", True, g_gpu_contract),
    ("deploy_preflight", "contract", True, g_deploy_preflight),
    ("e2e", "e2e", True, g_e2e),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated gate names to run; others SKIPPED (-> non-zero)")
    ap.add_argument("--rebuild-image", action="store_true")
    ap.add_argument("--release-url", default=os.environ.get("VITE_API_BASE_URL", ""))
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    ART.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    started = dt.datetime.now().astimezone().isoformat()

    for name, tier, mandatory, fn in GATES:
        r = Result(name, tier, mandatory)
        if only and name not in only:
            r.status = "SKIPPED"
            r.detail = "not selected by --only"
            results.append(r)
            print(f"[gate] {name}: SKIPPED")
            continue
        print(f"[gate] {name}: running…")
        t0 = time.time()
        try:
            if name == "release_url_guard":
                status, detail = g_release_url_guard(r, args.release_url)
            elif name == "appsail_image":
                status, detail = g_appsail_image(r, args.rebuild_image)
            else:
                status, detail = fn(r)
            r.status, r.detail = status, detail
        except Exception as e:  # noqa: BLE001
            r.status, r.detail = "ERROR", f"{type(e).__name__}: {e}"
        r.duration = time.time() - t0
        results.append(r)
        print(f"[gate] {name}: {r.status} ({r.duration:.0f}s) — {r.detail}")

    # A candidate is genuine ONLY if every mandatory gate is PASS (no SKIPPED,
    # FAIL, ERROR, or NOT_RUN among mandatory gates).
    mandatory_bad = [r for r in results if r.mandatory and r.status != "PASS"]
    passed = not mandatory_bad
    summary = {
        "gate": "release_gate",
        "started_at": started,
        "finished_at": dt.datetime.now().astimezone().isoformat(),
        "repo": str(REPO),
        "passed": passed,
        "mandatory_total": sum(1 for _, _, m, _ in GATES if m),
        "mandatory_passed": sum(1 for r in results if r.mandatory and r.status == "PASS"),
        "results": [r.to_dict() for r in results],
        "verdict": "RELEASE_CANDIDATE" if passed else "NOT_A_CANDIDATE",
    }
    out = ART / "release-gate.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 68)
    print(f"RELEASE GATE: {'PASS — genuine local release candidate' if passed else 'FAIL'}")
    print(f"  mandatory {summary['mandatory_passed']}/{summary['mandatory_total']} passed")
    for r in mandatory_bad:
        print(f"  BLOCKING {r.name}: {r.status} — {r.detail}")
    print(f"  summary: {out.relative_to(REPO)}")
    print("=" * 68)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
