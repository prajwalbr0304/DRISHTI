#!/usr/bin/env python3
"""DRISHTI executable secret scanner (Prompt 22 D.1).

Replaces the previous echo-only "secret scan" pipeline step with a real,
deterministic scanner. It:

  1. scans only GIT-TRACKED files (so `.gitignore`d secrets like `.env` /
     `.env.local` / `node_modules` are never read), for high-confidence secret
     VALUE patterns (PEM keys, AWS access keys, credential-bearing DB URLs,
     provider tokens);
  2. asserts that no secret-bearing FILE is tracked by git (a committed
     `.env` / `*.pem` / `credentials.json` / `id_rsa` would leak secrets);
  3. NEVER prints a secret value — every finding is redacted to a short masked
     fingerprint.

Exit code: 0 = clean, 1 = at least one finding (or a git failure). Stdlib only.

Usage:  python scripts/security/secret_scan.py [--repo <root>] [--json <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# High-confidence secret VALUE patterns (kept tight to avoid false positives on
# env-KEY names like ZOHO_APPSAIL_SIGNING_SECRET, which are not secrets).
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PEM private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Credential-bearing DB URL", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^:/\s]+:[^@/\s]+@[^\s\"']+")),
    ("Private RSA key body", re.compile(r"\bMII[A-Za-z0-9+/]{40,}")),
    ("Generic long secret assignment",
     re.compile(r"(?i)(?:api[_-]?key|secret|token|passwd|password)\s*[:=]\s*[\"'][A-Za-z0-9+/_\-]{24,}[\"']")),
]

# Files/paths that legitimately contain secret-shaped SAMPLES or key NAMES, or
# are scanner/policy artifacts. Matched against the repo-relative posix path.
ALLOW_PATH = re.compile(
    r"(^|/)("
    r"\.env\.example$"
    r"|.*\.lock$|.*-lock\.json$|package-lock\.json$"
    r"|docs/deployment/security-exceptions\.json$"
    r"|scripts/security/secret_scan\.py$"
    r"|web/scripts/check-bundle-secrets\.mjs$"
    r")"
)

# Placeholder / template / obvious-fake markers that neutralise a finding
# (documentation examples, f-string interpolation, env indirection, test fakes).
PLACEHOLDER = re.compile(
    r"(?i)(REPLACE|EXAMPLE|CHANGE[_-]?ME|YOUR[_-]|PLACEHOLDER|DUMMY|SAMPLE|xxxx|<[^>]+>|"
    r"\{[^}]+\}|SUPERSECRET|:password@|:pass@|:pwd@|user:secret|"
    r"os\.getenv|os\.environ|process\.env|import\.meta\.env|getenv\(|\$\{)"
)

# Secret-bearing FILE names that must never be git-tracked. Only TRUE secret
# files: a bare `.env`, any `.env*.local`, private keys, credential stores.
# The committed PUBLIC env files (.env.example / .env.development /
# .env.production) hold only non-secret VITE_*-style defaults by design and are
# allowed to be tracked (they are still CONTENT-scanned for secret values).
TRACKED_FORBIDDEN = re.compile(
    r"(^|/)("
    r"\.env|\.env\.local|\.env\.[A-Za-z0-9]+\.local"
    r"|[^/]*\.pem|[^/]*\.p12|[^/]*\.pfx|[^/]*\.key"
    r"|id_rsa|id_dsa|credentials\.json|\.npmrc|\.pypirc"
    r")$"
)
TRACKED_FORBIDDEN_ALLOW = re.compile(
    r"(^|/)(\.env\.example|\.env\.development|\.env\.production|\.env\.test|\.env\.staging)$"
)
# Committed env files to CONTENT-scan even though their suffix is not in TEXT_EXT.
ENV_FILE = re.compile(r"(^|/)\.env(\.[A-Za-z0-9.]+)?$")

TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml", ".yml",
    ".toml", ".md", ".txt", ".sh", ".ps1", ".env", ".ini", ".cfg", ".sql", ".html",
    ".css", ".tf", ".conf", ".xml", ".properties",
}
MAX_BYTES = 2_000_000


def _git_tracked(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                         capture_output=True, text=True, check=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _redact(match: str) -> str:
    m = match.strip()
    if len(m) <= 8:
        return m[0] + "***"
    return f"{m[:4]}…{m[-2:]} (len={len(m)})"


def scan(repo: Path) -> dict:
    findings: list[dict] = []
    tracked_forbidden: list[str] = []
    tracked = _git_tracked(repo)
    scanned = 0

    for rel in tracked:
        posix = rel.replace("\\", "/")
        if TRACKED_FORBIDDEN.search(posix) and not TRACKED_FORBIDDEN_ALLOW.search(posix):
            tracked_forbidden.append(posix)
        path = repo / rel
        if ALLOW_PATH.search(posix):
            continue
        if path.suffix.lower() not in TEXT_EXT and not ENV_FILE.search(posix):
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for name, pat in PATTERNS:
            for m in pat.finditer(text):
                snippet = m.group(0)
                # Placeholder / template / doc-example / test-fake filtering for
                # the patterns prone to it (documentation URLs, sample creds).
                if name in ("Generic long secret assignment", "Credential-bearing DB URL",
                            "Private RSA key body"):
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    line_end = text.find("\n", m.end())
                    line = text[line_start:line_end if line_end != -1 else len(text)]
                    if PLACEHOLDER.search(line) or PLACEHOLDER.search(snippet):
                        continue
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append({"file": posix, "line": line_no,
                                 "kind": name, "redacted": _redact(snippet)})

    return {
        "gate": "secret_scan",
        "scanned_files": scanned,
        "tracked_total": len(tracked),
        "findings": findings,
        "tracked_forbidden_files": tracked_forbidden,
        "passed": not findings and not tracked_forbidden,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    try:
        result = scan(repo)
    except subprocess.CalledProcessError as exc:
        print(f"[secret-scan] git ls-files failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"[secret-scan] scanned {result['scanned_files']} tracked text file(s) "
          f"of {result['tracked_total']} tracked.")
    for f in result["findings"]:
        print(f"  FINDING {f['kind']}: {f['file']}:{f['line']}  [{f['redacted']}]")
    for f in result["tracked_forbidden_files"]:
        print(f"  FORBIDDEN TRACKED FILE (secret-bearing, should be gitignored): {f}")

    if result["passed"]:
        print("[secret-scan] PASS — no committed secret values or secret files.")
        return 0
    print(f"[secret-scan] FAIL — {len(result['findings'])} finding(s), "
          f"{len(result['tracked_forbidden_files'])} forbidden tracked file(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
