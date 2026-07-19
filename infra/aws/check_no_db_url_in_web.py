#!/usr/bin/env python
"""Fail if a DATABASE_URL / RDS endpoint / server secret leaks into the web app.

Prompt 14 Part F, item 2 (keep RDS private): the React/Slate browser bundle must
NEVER carry a PostgreSQL connection string, a ``5432`` endpoint, an RDS host, or a
server-only secret env key. Vite inlines every ``VITE_*`` value into the static
bundle, so a leak here is a leak to every browser.

This is a SOURCE-level check (runs before a build, no Node needed) and complements
``web/scripts/check-bundle-secrets.mjs`` (which scans the built ``dist/``). It
scans the committed web env files + the web source, and exits non-zero on any
high-confidence leak.

It is careful NOT to false-positive on the many *prose* mentions of "DATABASE_URL"
in the env-file comments (those lines start with ``#`` and are ignored for the
assignment check); it flags real *values* (``postgres://``, ``*.rds.amazonaws.com``,
``:5432``, AWS keys, PEM) anywhere, and server-only KEY=VALUE assignments only.

Usage:
    python infra/aws/check_no_db_url_in_web.py            # scan ./web
    python infra/aws/check_no_db_url_in_web.py --web-dir path/to/web
"""
from __future__ import annotations

import argparse
import os
import re
import sys

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

# High-confidence *value* patterns — safe to match anywhere (they do not appear
# in the legitimate "never put a DATABASE_URL here" comments).
_VALUE_PATTERNS = [
    ("PostgreSQL connection string", re.compile(r"postgres(?:ql)?://\S+", re.I)),
    ("RDS endpoint host", re.compile(r"[a-z0-9.-]+\.rds\.amazonaws\.com", re.I)),
    ("PostgreSQL port endpoint", re.compile(r"://[^\s\"']+:5432\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("PEM private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
]

# Server-only env KEYS that must never appear as an assignment in a web env file
# (they belong to AppSail / the AWS adapter, never the browser).
_SERVER_ONLY_KEYS = {
    "DATABASE_URL", "READONLY_ROLE", "SYNTHETIC_ENV_EXPECTED",
    "ZOHO_APPSAIL_SIGNING_SECRET", "DRISHTI_AWS_ADAPTER_SECRET",
    "DRISHTI_CHANNEL_SIGNING_SECRET", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID",
}

_SCAN_SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".json"}
_SKIP_DIRS = {"node_modules", "dist", ".git", "coverage"}
_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=(.*)$")


def _iter_files(web_dir: str):
    for name in sorted(os.listdir(web_dir)):
        if name.startswith(".env"):
            yield os.path.join(web_dir, name)
    for root, dirs, files in os.walk(os.path.join(web_dir, "src")):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in sorted(files):
            if os.path.splitext(f)[1] in _SCAN_SOURCE_EXT:
                yield os.path.join(root, f)
    for cfg in ("vite.config.ts", "vitest.config.ts"):
        p = os.path.join(web_dir, cfg)
        if os.path.exists(p):
            yield p


def _scan_file(path: str) -> list[str]:
    findings: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return findings

    for label, pat in _VALUE_PATTERNS:
        m = pat.search(text)
        if m:
            findings.append(f"{label}: '{m.group(0)[:48]}'")

    if os.path.basename(path).startswith(".env"):
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # prose/comment — ignore
            m = _ASSIGN_RE.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip()
            if key in _SERVER_ONLY_KEYS:
                findings.append(f"server-only key '{key}' assigned in web env (line {lineno})")
            if ":5432" in value:
                findings.append(f"'{key}' value contains a 5432 endpoint (line {lineno})")
    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Fail if a DB URL / RDS host / server "
                                             "secret leaks into the web app (Part F item 2).")
    ap.add_argument("--web-dir", default=os.path.join(_REPO_ROOT, "web"))
    args = ap.parse_args(argv)

    web_dir = os.path.abspath(args.web_dir)
    if not os.path.isdir(web_dir):
        print(f"ERROR: web dir not found: {web_dir}", file=sys.stderr)
        return 2

    scanned = 0
    leaks: list[tuple[str, str]] = []
    for path in _iter_files(web_dir):
        scanned += 1
        for finding in _scan_file(path):
            leaks.append((os.path.relpath(path, _REPO_ROOT), finding))

    if leaks:
        print(f"[check-rds-private] FAIL — {len(leaks)} leak(s) into the web app:")
        for rel, finding in leaks:
            print(f"  - {rel}: {finding}")
        print("\nRDS must stay private (F.2): keep DATABASE_URL / 5432 / RDS host / "
              "server secrets server-side. Only public VITE_* values may ship to the browser.")
        return 1

    print(f"[check-rds-private] OK — scanned {scanned} web file(s); "
          f"no DB URL / RDS endpoint / server secret in the browser surface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
