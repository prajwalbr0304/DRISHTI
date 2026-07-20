#!/usr/bin/env python3
"""Capture a redacted, read-only AWS inventory through the AWS CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ACCOUNT = re.compile(r"(?<!\d)\d{12}(?!\d)")


def redact(value: str) -> str:
    return ACCOUNT.sub(lambda match: f"[ACCOUNT-REDACTED-{match.group(0)[-4:]}]", value)


def invoke(profile: str, region: str, args: list[str], cwd: Path) -> dict:
    command = ["aws", *args, "--profile", profile, "--output", "json"]
    if region:
        command.extend(["--region", region])
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=45)
        output = redact(((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip())
        try:
            parsed: object = json.loads(output) if output else None
        except json.JSONDecodeError:
            parsed = output[:12000]
        return {"operation": args[:2], "exit_code": result.returncode, "result": parsed}
    except subprocess.TimeoutExpired:
        return {"operation": args[:2], "exit_code": 124, "result": "timeout"}
    except FileNotFoundError:
        return {"operation": args[:2], "exit_code": 127, "result": "aws CLI not found"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="drishti")
    parser.add_argument("--region", default="ap-south-1")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--phase", type=int, default=24)
    args = parser.parse_args()
    repo = args.repo.resolve()
    operations = [
        ["sts", "get-caller-identity"],
        ["ecr", "describe-repositories", "--max-results", "100"],
        ["s3api", "list-buckets"],
        ["kms", "list-keys", "--limit", "100"],
        ["sqs", "list-queues"],
        ["sagemaker", "list-endpoints", "--max-results", "100"],
        ["sagemaker", "list-transform-jobs", "--max-results", "100"],
        ["batch", "describe-job-queues"],
        ["lambda", "list-functions", "--max-items", "100"],
        ["apigateway", "get-rest-apis", "--limit", "100"],
        ["cloudwatch", "describe-alarms", "--max-records", "100"],
    ]
    results = [invoke(args.profile, args.region, operation, repo) for operation in operations]
    record = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "profile": args.profile,
        "region": args.region,
        "read_only": True,
        "results": results,
        "all_commands_succeeded": all(item["exit_code"] == 0 for item in results),
    }
    out = repo / f"artifacts/phase-{args.phase:02d}/aws-inventory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "all_commands_succeeded": record["all_commands_succeeded"]}, indent=2))
    return 0 if record["all_commands_succeeded"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
