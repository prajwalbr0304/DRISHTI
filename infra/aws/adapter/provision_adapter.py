#!/usr/bin/env python
"""Provision (idempotently) the DRISHTI protected AWS adapter plane — Prompt 14 Part F.

Creates/updates, and re-applies safely:
  * the least-privilege Lambda execution role (trust + inline policy +
    AWS-managed VPC-access policy);
  * the adapter Lambda (services/aws-adapter) in PRIVATE subnets;
  * (documented final step) the HTTP API Gateway route + throttle + usage plan.

Descriptors are the single reviewed source of truth:
  * infra/aws/adapter/adapter-infra.json
  * infra/aws/adapter/iam/lambda-trust-policy.json
  * infra/aws/adapter/iam/lambda-execution-policy.json

The DEFAULT action is ``--plan``: it validates the descriptors (including a
least-privilege check that the inline policy has no unexpected ``*`` resources)
and prints the ordered actions WITHOUT any AWS call — so it runs offline with no
boto3 and no credentials. ``--commit`` performs the real, credit-/account-
affecting changes and is HELD for an explicit go-ahead.

No secrets are printed. Credentials come from the environment / SSO profile /
role — never from arguments or code.

Usage (PowerShell):
    python infra/aws/adapter/provision_adapter.py                 # plan (default, offline)
    python infra/aws/adapter/provision_adapter.py --commit --profile drishti   # HELD
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

# Resource:"*" entries that are ACCEPTED because AWS does not support
# resource-level scoping for these read-only actions (documented in the policy).
_ALLOWED_WILDCARD_ACTIONS = {"batch:DescribeJobs"}


def _load_json(rel_or_abs: str) -> dict:
    path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(_HERE, rel_or_abs)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate() -> tuple[dict, list[str]]:
    """Load + validate the descriptors. Returns (infra, issues)."""
    issues: list[str] = []
    infra = _load_json("adapter-infra.json")
    trust = _load_json("iam/lambda-trust-policy.json")
    policy = _load_json("iam/lambda-execution-policy.json")

    # Trust policy must only allow lambda to assume the role.
    principals = [s.get("Principal", {}).get("Service")
                  for s in trust.get("Statement", [])]
    if principals != ["lambda.amazonaws.com"]:
        issues.append(f"trust policy principal unexpected: {principals}")

    # Least-privilege: flag any '*' Resource not explicitly allow-listed.
    for stmt in policy.get("Statement", []):
        if not isinstance(stmt, dict):
            continue
        res = stmt.get("Resource")
        actions = stmt.get("Action", [])
        actions = [actions] if isinstance(actions, str) else actions
        res_list = [res] if isinstance(res, str) else (res or [])
        if any(r == "*" for r in res_list):
            if not set(actions).issubset(_ALLOWED_WILDCARD_ACTIONS):
                issues.append(f"statement {stmt.get('Sid')} uses Resource '*' "
                              f"for non-allow-listed actions {actions}")
        # No admin-shaped wildcards in actions.
        for a in actions:
            if a in ("*", "iam:*", "s3:*", "sagemaker:*", "kms:*"):
                issues.append(f"statement {stmt.get('Sid')} uses over-broad action {a!r}")

    # Lambda must be VPC-placed (private) and carry a scoped execution role.
    lam = infra.get("lambda", {})
    if not lam.get("vpc_config", {}).get("subnet_ids"):
        issues.append("lambda.vpc_config.subnet_ids missing (adapter must be VPC-private)")
    if "role/drishti-aws-adapter-exec" not in lam.get("execution_role", ""):
        issues.append("lambda.execution_role is not the scoped adapter role")

    # API Gateway must be HTTPS-only with TLS>=1.2 and a request-size cap.
    ag = infra.get("api_gateway", {})
    if ag.get("protocol") != "HTTPS_ONLY":
        issues.append("api_gateway.protocol must be HTTPS_ONLY")
    if ag.get("min_tls_version") not in ("TLS1_2", "TLS1_3"):
        issues.append("api_gateway.min_tls_version must be >= TLS1_2")
    if not ag.get("payload_max_bytes"):
        issues.append("api_gateway.payload_max_bytes missing (request-size cap)")
    if not ag.get("throttling"):
        issues.append("api_gateway.throttling missing")

    return infra, issues


def plan() -> int:
    infra, issues = validate()
    lam = infra["lambda"]
    ag = infra["api_gateway"]
    print("[plan] DRISHTI protected AWS adapter — validating descriptors\n")
    if issues:
        print("[plan] DESCRIPTOR ISSUES:")
        for i in issues:
            print(f"  ! {i}")
        print("\n[plan] FAILED — fix the issues above before committing.")
        return 1
    print("[plan] descriptors valid (least-privilege check passed).\n")
    steps = [
        f"create IAM role '{lam['execution_role'].split('/')[-1]}' "
        f"(trust: lambda.amazonaws.com)",
        "attach AWS-managed AWSLambdaVPCAccessExecutionRole (VPC ENI mgmt only)",
        "put inline least-privilege policy iam/lambda-execution-policy.json",
        f"package Lambda from {lam['source_dir']} (no torch/CUDA; boto3 only)",
        f"create/update Lambda '{lam['function_name']}' "
        f"({lam['runtime']}, {lam['memory_mb']}MB, {lam['timeout_s']}s, "
        f"reserved_concurrency={lam['reserved_concurrency']}, VPC-private)",
        f"create HTTP API '{infra['name']}' ({ag['protocol']}, "
        f"min TLS {ag['min_tls_version']}, payload<= {ag['payload_max_bytes']}B)",
        f"add routes: {', '.join(r['route_key'] for r in ag['routes'])}",
        f"set stage throttle rate={ag['throttling']['rate_limit_rps']}rps "
        f"burst={ag['throttling']['burst_limit']} + usage plan "
        f"(api key = throttle handle, NOT auth)",
        "enable access logging with redacted authorization/signature/body",
        "store the HMAC secret in Secrets Manager (drishti/adapter/hmac-*) and "
        "set DRISHTI_AWS_ADAPTER_SECRET_ARN on the Lambda",
    ]
    for i, s in enumerate(steps, 1):
        print(f"  {i:>2}. WOULD {s}")
    print("\n[plan] DRY-RUN — no AWS calls made. Re-run with --commit (HELD) to apply.")
    print("[plan] After apply: set DRISHTI_AWS_ADAPTER_URL (the API Gateway https "
          "invoke URL) + DRISHTI_AWS_ADAPTER_SECRET on AppSail (Console), never in the browser.")
    return 0


def commit(profile: str, region: str) -> int:
    """Apply for real (HELD — spends credits / needs the AWS account)."""
    infra, issues = validate()
    if issues:
        print("[commit] refusing: descriptor issues present. Run --plan.", file=sys.stderr)
        return 1
    try:
        import boto3  # deferred
        from botocore.exceptions import ClientError  # noqa: F401
    except Exception:  # noqa: BLE001
        print("[commit] boto3 not installed; cannot apply.", file=sys.stderr)
        return 2

    session = boto3.Session(profile_name=profile or None, region_name=region)
    iam = session.client("iam")
    lam_cfg = infra["lambda"]
    role_name = lam_cfg["execution_role"].split("/")[-1]
    trust = _load_json("iam/lambda-trust-policy.json")
    policy = _load_json("iam/lambda-execution-policy.json")

    # 1. IAM role (idempotent).
    try:
        iam.get_role(RoleName=role_name)
        print(f"[commit] OK role {role_name} exists")
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=role_name,
                        AssumeRolePolicyDocument=json.dumps(trust),
                        Description="DRISHTI protected AWS adapter execution role",
                        MaxSessionDuration=3600)
        print(f"[commit] OK created role {role_name}")
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole")
    # Strip the descriptor-only "_comment"/"_note" keys before putting the policy.
    clean = {"Version": policy["Version"],
             "Statement": [{k: v for k, v in s.items() if not k.startswith("_")}
                           for s in policy["Statement"]]}
    iam.put_role_policy(RoleName=role_name, PolicyName="drishti-adapter-least-priv",
                        PolicyDocument=json.dumps(clean))
    print("[commit] OK attached managed VPC policy + inline least-privilege policy")

    # 2. Lambda package + create/update, 3. API Gateway wiring.
    print("\n[commit] NEXT (HELD — packaging + Lambda + API Gateway):")
    print("  - zip services/aws-adapter/*.py + boto3 layer, then "
          "create_function/update_function_code for drishti-aws-adapter in the VPC;")
    print("  - create the HTTP API, routes, stage throttle + usage plan, access logging;")
    print("  - put the HMAC secret in Secrets Manager and set the Lambda env keys.")
    print("  These remaining steps spend credits and touch the live account; run them "
          "deliberately per the Part F report §'Held cloud steps'.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Provision the DRISHTI protected AWS adapter plane.")
    ap.add_argument("--plan", action="store_true",
                    help="validate descriptors + print planned actions (default; offline)")
    ap.add_argument("--commit", action="store_true",
                    help="apply for real (HELD — spends credits / needs the AWS account)")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    args = ap.parse_args(argv)
    try:
        if args.commit:
            return commit(args.profile, args.region)
        return plan()
    except FileNotFoundError as exc:
        print(f"ERROR: descriptor not found: {exc.filename}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — never print credentials/tracebacks
        print(f"ERROR: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
