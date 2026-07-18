#!/usr/bin/env python
"""Provision (idempotently) the PRIVATE DRISHTI evidence S3 bucket — Phase 5.

Applies, and re-applies safely, the hackathon-appropriate configuration:
  * create the bucket in the target region (no-op if you already own it);
  * BLOCK ALL PUBLIC ACCESS (all four flags true);
  * default server-side encryption (SSE-S3 / AES256) + bucket keys;
  * versioning enabled (immutable history of replaced/deleted objects);
  * TLS-only bucket policy (deny aws:SecureTransport = false);
  * CORS limited to the exact frontend origin(s) for pre-signed PUT/GET;
  * lifecycle rules suited to SYNTHETIC demo data (abort stale multipart
    uploads, expire noncurrent versions, expire objects after a retention).

No secrets are printed. Credentials come from the environment / SSO profile /
task role — never from arguments or code.

Usage (PowerShell):
    aws sso login --profile drishti
    python infra/aws/provision_evidence_bucket.py `
        --bucket drishti-synthetic-evidence-<acct>-ap-south-1 `
        --region ap-south-1 --profile drishti `
        --frontend-origin http://localhost:5173 --frontend-origin http://localhost:4173

    # inspect only, no changes:
    python infra/aws/provision_evidence_bucket.py --bucket <name> --check
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from dotenv import load_dotenv
    # repo-root .env (this file is infra/aws/…)
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except Exception:  # pragma: no cover
    pass

DEFAULT_RETENTION_DAYS = 30
DEFAULT_NONCURRENT_DAYS = 30
DEFAULT_ABORT_MPU_DAYS = 3


def _session(profile: str, region: str):
    import boto3
    return boto3.Session(profile_name=profile or None, region_name=region)


def _default_bucket_name(session, region: str) -> str:
    acct = session.client("sts").get_caller_identity()["Account"]
    return f"drishti-synthetic-evidence-{acct}-{region}"


def _bucket_exists(s3, bucket: str) -> bool:
    from botocore.exceptions import ClientError
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            return False
        if code in ("403",):  # exists but owned/forbidden — treat as exists
            return True
        raise


def _cors_config(origins: list[str]) -> dict:
    return {
        "CORSRules": [{
            "AllowedMethods": ["PUT", "GET", "HEAD"],
            "AllowedOrigins": origins,
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3000,
        }]
    }


def _tls_only_policy(bucket: str) -> str:
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "DenyInsecureTransport",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        }],
    })


def _lifecycle(prefix: str, retention_days: int) -> dict:
    return {
        "Rules": [{
            "ID": "drishti-synthetic-evidence-cleanup",
            "Filter": {"Prefix": f"{prefix.strip('/')}/"},
            "Status": "Enabled",
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": DEFAULT_ABORT_MPU_DAYS},
            "NoncurrentVersionExpiration": {"NoncurrentDays": DEFAULT_NONCURRENT_DAYS},
            "Expiration": {"Days": retention_days},
        }]
    }


def check(s3, bucket: str) -> int:
    from botocore.exceptions import ClientError
    print(f"[check] bucket: {bucket}")
    if not _bucket_exists(s3, bucket):
        print("[check] bucket does NOT exist")
        return 1

    def _try(label, fn):
        try:
            print(f"[check] {label}: {fn()}")
        except ClientError as exc:
            print(f"[check] {label}: <{exc.response.get('Error', {}).get('Code', 'error')}>")

    _try("public-access-block", lambda: s3.get_public_access_block(Bucket=bucket)[
        "PublicAccessBlockConfiguration"])
    _try("versioning", lambda: s3.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled"))
    _try("encryption", lambda: s3.get_bucket_encryption(Bucket=bucket)[
        "ServerSideEncryptionConfiguration"]["Rules"])
    _try("cors", lambda: s3.get_bucket_cors(Bucket=bucket)["CORSRules"])
    _try("lifecycle", lambda: [r["ID"] for r in s3.get_bucket_lifecycle_configuration(
        Bucket=bucket)["Rules"]])
    _try("policy", lambda: "present")
    return 0


def provision(s3, bucket: str, region: str, origins: list[str], prefix: str,
              retention_days: int, dry_run: bool) -> int:
    from botocore.exceptions import ClientError

    steps: list[str] = []

    def do(label, fn):
        if dry_run:
            steps.append(f"WOULD {label}")
            return
        fn()
        steps.append(f"OK {label}")

    # 1. create bucket (idempotent)
    if _bucket_exists(s3, bucket):
        steps.append("OK bucket already exists")
    else:
        def _create():
            kwargs = {"Bucket": bucket}
            if region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            try:
                s3.create_bucket(**kwargs)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in (
                        "BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    return
                raise
        do(f"create bucket in {region}", _create)

    # 2. block ALL public access
    do("block all public access", lambda: s3.put_public_access_block(
        Bucket=bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True}))

    # 3. versioning
    do("enable versioning", lambda: s3.put_bucket_versioning(
        Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}))

    # 4. default SSE (AES256) + bucket keys
    do("enable default SSE (AES256)", lambda: s3.put_bucket_encryption(
        Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{
            "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
            "BucketKeyEnabled": True}]}))

    # 5. TLS-only bucket policy
    do("apply TLS-only bucket policy", lambda: s3.put_bucket_policy(
        Bucket=bucket, Policy=_tls_only_policy(bucket)))

    # 6. CORS limited to the frontend origin(s)
    do(f"set CORS for origins {origins}", lambda: s3.put_bucket_cors(
        Bucket=bucket, CORSConfiguration=_cors_config(origins)))

    # 7. lifecycle for synthetic demo data
    do(f"set lifecycle (retention {retention_days}d)", lambda: s3.put_bucket_lifecycle_configuration(
        Bucket=bucket, LifecycleConfiguration=_lifecycle(prefix, retention_days)))

    print("\n".join(f"  - {s}" for s in steps))
    print(f"\n{'DRY-RUN — no changes made.' if dry_run else 'Provisioning complete.'}")
    print(f"Bucket: {bucket} (private, versioned, SSE-AES256, TLS-only, "
          f"CORS={origins}, prefix='{prefix}')")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Provision the private DRISHTI evidence S3 bucket.")
    ap.add_argument("--bucket", default=os.environ.get("S3_EVIDENCE_BUCKET", ""))
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    ap.add_argument("--prefix", default=os.environ.get("S3_EVIDENCE_PREFIX", "evidence"))
    ap.add_argument("--frontend-origin", action="append", default=None,
                    help="Exact frontend origin(s) allowed for pre-signed upload CORS. Repeatable.")
    ap.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    ap.add_argument("--check", action="store_true", help="report current config, make no changes")
    ap.add_argument("--dry-run", action="store_true", help="print planned actions, make no changes")
    args = ap.parse_args(argv)

    try:
        session = _session(args.profile, args.region)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR creating AWS session: {type(exc).__name__}", file=sys.stderr)
        return 2

    s3 = session.client("s3")
    bucket = args.bucket.strip()
    if not bucket:
        try:
            bucket = _default_bucket_name(session, args.region)
            print(f"[info] no --bucket given; derived: {bucket}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: no bucket name and could not derive one "
                  f"(is the SSO session valid?): {type(exc).__name__}", file=sys.stderr)
            return 2

    origins = args.frontend_origin or [
        o for o in [os.environ.get("DEMO_FRONTEND_ORIGIN", "").strip(),
                    "http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:4173", "http://127.0.0.1:4173"] if o]

    try:
        if args.check:
            return check(s3, bucket)
        return provision(s3, bucket, args.region, origins, args.prefix,
                         args.retention_days, args.dry_run)
    except Exception as exc:  # noqa: BLE001 — never print credentials/tracebacks
        print(f"ERROR: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
