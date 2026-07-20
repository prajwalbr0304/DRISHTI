#!/usr/bin/env python3
"""Durable per-module backend test ledger (Prompt 18 §D.1).

The full backend suite mixes fast pure-logic tests with slow integration tests
that hit a remote analytics database (AWS RDS) and, for a few, the live LLM. A
single ``pytest`` run can exceed several minutes and, worse, a test blocked deep
in a C-level DB socket read cannot be interrupted by pytest-timeout's thread
method on Windows — one hang stalls the whole run and yields no result.

This runner executes EACH test module in its own subprocess with a hard
wall-clock timeout backstop, so a hang in one module is recorded as TIMEOUT and
the rest still run. It writes a durable Markdown + JSON ledger so the phase
report cites real, reproducible per-module results instead of a single opaque
timeout.

    # full ledger against the live DB (excludes @slow by default):
    python scripts/test_ledger.py

    # include @slow tests and raise the per-module wall-clock budget:
    python scripts/test_ledger.py --slow --module-timeout 900

    # fast offline pass (DB tests skip cleanly, deterministic):
    python scripts/test_ledger.py --offline

Stdlib only. Exit code is non-zero if any module reports a FAIL/ERROR/TIMEOUT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ML_ROOT = Path(__file__).resolve().parents[1]
_TESTS = _ML_ROOT / "tests"
_OUT_DIR = _ML_ROOT

# pytest terminal summary line, e.g. "5 passed, 2 skipped, 1 failed in 3.2s"
_SUMMARY = re.compile(
    r"(?:(\d+) failed)?.*?(?:(\d+) passed)?.*?(?:(\d+) skipped)?.*?"
    r"(?:(\d+) errors?)?.*?(?:(\d+) deselected)?", re.IGNORECASE)


def _parse_counts(text: str) -> dict:
    """Pull the last pytest summary line into a counts dict."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "deselected": 0}
    for key in counts:
        m = re.search(rf"(\d+) {key}", text)
        if m:
            counts[key] = int(m.group(1))
    # pytest prints "error" (singular) sometimes
    if not counts["errors"]:
        m = re.search(r"(\d+) error\b", text)
        if m:
            counts["errors"] = int(m.group(1))
    return counts


def _module_status(rc: int, timed_out: bool, counts: dict) -> str:
    if timed_out:
        return "TIMEOUT"
    if counts["failed"] or counts["errors"]:
        return "FAIL"
    if rc != 0:
        return "FAIL"
    if counts["passed"]:
        return "PASS"
    return "NO-TESTS"


def run(modules: list[str], args) -> dict:
    env = dict(os.environ)
    if args.offline:
        env["DRISHTI_DISABLE_DB_TESTS"] = "1"
    results = []
    for mod in modules:
        cmd = [sys.executable, "-m", "pytest", f"tests/{mod}", "-q",
               f"--timeout={args.test_timeout}", "--timeout-method=thread",
               "-p", "no:cacheprovider"]
        if not args.slow:
            cmd += ["-m", "not slow"]
        timed_out = False
        started = dt.datetime.now(dt.timezone.utc)
        try:
            proc = subprocess.run(cmd, cwd=str(_ML_ROOT), env=env,
                                  capture_output=True, text=True,
                                  timeout=args.module_timeout)
            rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as e:
            timed_out = True
            rc, out = -1, (e.stdout or "") if isinstance(e.stdout, str) else ""
        elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        counts = _parse_counts(out)
        status = _module_status(rc, timed_out, counts)
        fails = re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.MULTILINE)
        results.append({"module": mod, "status": status, "counts": counts,
                        "elapsed_s": round(elapsed, 1), "failures": fails})
        print(f"[{status:8}] {mod:32} "
              f"{counts['passed']}p/{counts['failed']}f/{counts['skipped']}s/"
              f"{counts['errors']}e  {elapsed:.0f}s")
        for f in fails:
            print(f"             - {f}")
    return {"generated_at": started.isoformat(), "offline": args.offline,
            "slow": args.slow, "test_timeout_s": args.test_timeout,
            "module_timeout_s": args.module_timeout, "results": results}


def write_ledger(ledger: dict) -> None:
    (_OUT_DIR / ".p18-db-ledger.json").write_text(
        json.dumps(ledger, indent=2), encoding="utf-8")
    lines = ["# Prompt 18 backend per-module test ledger", "",
             f"- generated: {ledger['generated_at']}",
             f"- mode: {'offline (DB skipped)' if ledger['offline'] else 'live DB'}"
             f"{' + slow' if ledger['slow'] else ' (no slow)'}",
             f"- per-test timeout: {ledger['test_timeout_s']}s; "
             f"per-module wall-clock: {ledger['module_timeout_s']}s", "",
             "| module | status | passed | failed | skipped | errors | seconds |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for r in ledger["results"]:
        c = r["counts"]
        lines.append(f"| {r['module']} | {r['status']} | {c['passed']} | "
                     f"{c['failed']} | {c['skipped']} | {c['errors']} | {r['elapsed_s']} |")
    total = {k: sum(r["counts"][k] for r in ledger["results"])
             for k in ("passed", "failed", "skipped", "errors")}
    lines += ["", f"**Totals:** {total['passed']} passed, {total['failed']} failed, "
              f"{total['skipped']} skipped, {total['errors']} errors."]
    bad = [r for r in ledger["results"] if r["status"] in ("FAIL", "TIMEOUT")]
    if bad:
        lines += ["", "## Modules needing attention", ""]
        for r in bad:
            lines.append(f"- **{r['module']}** — {r['status']}"
                         + ("; " + ", ".join(r["failures"]) if r["failures"] else ""))
    (_OUT_DIR / ".p18-db-ledger.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="DRISHTI per-module backend test ledger.")
    ap.add_argument("--offline", action="store_true", help="skip DB tests (deterministic)")
    ap.add_argument("--slow", action="store_true", help="include @slow tests")
    ap.add_argument("--test-timeout", type=int, default=90, help="per-test timeout (s)")
    ap.add_argument("--module-timeout", type=int, default=420,
                    help="per-module wall-clock backstop (s)")
    ap.add_argument("--only", nargs="*", help="run only these module filenames")
    a = ap.parse_args()

    modules = sorted(p.name for p in _TESTS.glob("test_*.py"))
    if a.only:
        wanted = {m if m.endswith(".py") else f"{m}.py" for m in a.only}
        modules = [m for m in modules if m in wanted]
    print(f"running {len(modules)} test module(s); "
          f"{'offline' if a.offline else 'live DB'}"
          f"{' +slow' if a.slow else ''}\n" + "=" * 60)
    ledger = run(modules, a)
    write_ledger(ledger)
    bad = [r for r in ledger["results"] if r["status"] in ("FAIL", "TIMEOUT")]
    print("=" * 60)
    print(f"ledger written: .p18-db-ledger.md / .p18-db-ledger.json; "
          f"{len(bad)} module(s) need attention")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
