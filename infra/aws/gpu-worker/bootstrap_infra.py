#!/usr/bin/env python
"""DRISHTI Prompt 24 - bootstrap the non-GPU-gated foundation infra (steps 1-4).

Creates, idempotently, the four resources the GPU worker needs before an image can
be built or an endpoint created:

  1. KMS CMK + alias/drishti-model-plane      (model-plane + async-IO encryption)
  2. S3 bucket drishti-model-plane-<acct>-<region>
     - block public access, versioning, default aws:kms (CMK) + bucket keys,
       lifecycle: async-io/ expires 7d, noncurrent 3d, abort MPU 2d
  3. ECR repo drishti-gpu-worker              (IMMUTABLE tags, scan-on-push, AES256)
  4. IAM role drishti-sagemaker-exec          (scoped inline policy, no static creds)

Then writes the resolved ``kms.key_id`` / ``kms.key_arn`` back into
``deploy.generated.json`` (``sagemaker_ops.py`` reads ``key_arn`` at import time)
and regenerates ``iam/sagemaker-exec-policy.json`` so the committed policy matches
what was actually applied to this account.

Safe to re-run: every create is guarded and reports ``[exists]`` instead of failing.

Usage (PowerShell):
    $env:AWS_PROFILE='prajwal-sso'
    python infra/aws/gpu-worker/bootstrap_infra.py --plan      # default, no writes
    python infra/aws/gpu-worker/bootstrap_infra.py --commit
"""
from __future__ import annotations

import argparse
import json
import os
import time

import boto3

_HERE = os.path.dirname(os.path.abspath(__file__))
_CFG_PATH = os.path.join(_HERE, "deploy.generated.json")
_POLICY_PATH = os.path.join(_HERE, "iam", "sagemaker-exec-policy.json")

_CFG = json.load(open(_CFG_PATH, encoding="utf-8"))

REGION = _CFG["region"]
ACCOUNT = _CFG["account_id"]
PROFILE = os.getenv("AWS_PROFILE", "drishti")
BUCKET = _CFG["s3"]["bucket"]
REPO = _CFG["ecr"]["repository"]
KMS_ALIAS = _CFG["kms"]["alias"]
EXEC_ROLE_ARN = _CFG["iam"]["sagemaker_execution_role"]
EXEC_ROLE = EXEC_ROLE_ARN.rsplit("/", 1)[-1]
EXEC_POLICY_NAME = "drishti-sagemaker-exec-inline"


def _sess():
    return boto3.Session(profile_name=PROFILE, region_name=REGION)


def _ok(label: str, detail: str = "") -> None:
    print(f"  [ok] {label}" + (f" -> {detail}" if detail else ""))


def _exists(label: str, detail: str = "") -> None:
    print(f"  [exists] {label}" + (f" -> {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# 1. KMS CMK
# --------------------------------------------------------------------------- #
def ensure_kms(commit: bool) -> tuple[str | None, str | None]:
    """Create (or find) the model-plane CMK. Returns (key_id, key_arn)."""
    kms = _sess().client("kms")
    try:
        k = kms.describe_key(KeyId=KMS_ALIAS)["KeyMetadata"]
        _exists(f"kms {KMS_ALIAS}", k["KeyId"])
        return k["KeyId"], k["Arn"]
    except kms.exceptions.NotFoundException:
        pass
    if not commit:
        print(f"  [plan] create kms CMK + {KMS_ALIAS}")
        return None, None

    # Key policy: account root retains admin; SageMaker + CodeBuild use the key
    # only via the grants their execution roles carry (identity-based).
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "EnableRootAdmin", "Effect": "Allow",
             "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
             "Action": "kms:*", "Resource": "*"},
            {"Sid": "AllowServiceUseViaIam", "Effect": "Allow",
             "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
             "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
                        "kms:GenerateDataKey*", "kms:DescribeKey"],
             "Resource": "*",
             "Condition": {"StringEquals": {
                 "kms:ViaService": [f"s3.{REGION}.amazonaws.com",
                                    f"sagemaker.{REGION}.amazonaws.com"]}}},
        ],
    }
    meta = kms.create_key(
        Description="DRISHTI model-plane CMK (GPU worker async IO + S3 artifacts)",
        KeyUsage="ENCRYPT_DECRYPT", KeySpec="SYMMETRIC_DEFAULT",
        Policy=json.dumps(policy),
        Tags=[{"TagKey": "Project", "TagValue": "DRISHTI"},
              {"TagKey": "Component", "TagValue": "gpu-worker-model-plane"}],
    )["KeyMetadata"]
    kms.create_alias(AliasName=KMS_ALIAS, TargetKeyId=meta["KeyId"])
    kms.enable_key_rotation(KeyId=meta["KeyId"])
    _ok(f"kms CMK + {KMS_ALIAS}", meta["KeyId"])
    return meta["KeyId"], meta["Arn"]


# --------------------------------------------------------------------------- #
# 2. S3 model-plane bucket
# --------------------------------------------------------------------------- #
def ensure_bucket(commit: bool, key_arn: str | None) -> None:
    s3 = _sess().client("s3")
    try:
        s3.head_bucket(Bucket=BUCKET)
        _exists(f"s3 {BUCKET}")
        created = False
    except Exception:
        if not commit:
            print(f"  [plan] create s3 {BUCKET} (+BPA, versioning, CMK SSE, lifecycle)")
            return
        s3.create_bucket(Bucket=BUCKET,
                         CreateBucketConfiguration={"LocationConstraint": REGION})
        _ok(f"s3 {BUCKET}")
        created = True
    if not commit:
        return

    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True,
                                        "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
    if key_arn:
        s3.put_bucket_encryption(
            Bucket=BUCKET,
            ServerSideEncryptionConfiguration={"Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "aws:kms", "KMSMasterKeyID": key_arn},
                "BucketKeyEnabled": True}]})
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={"Rules": [
            {"ID": "async-io-expire-7d", "Status": "Enabled",
             "Filter": {"Prefix": "async-io/"},
             "Expiration": {"Days": 7},
             "NoncurrentVersionExpiration": {"NoncurrentDays": 3},
             "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}},
            {"ID": "abort-mpu-all", "Status": "Enabled", "Filter": {"Prefix": ""},
             "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}},
        ]})
    _ok("s3 hardening (BPA, versioning, CMK SSE + bucket keys, lifecycle)",
        "created" if created else "reapplied")


# --------------------------------------------------------------------------- #
# 3. ECR repo
# --------------------------------------------------------------------------- #
def ensure_ecr(commit: bool) -> None:
    ecr = _sess().client("ecr")
    try:
        r = ecr.describe_repositories(repositoryNames=[REPO])["repositories"][0]
        _exists(f"ecr {REPO}", r["repositoryUri"])
        return
    except ecr.exceptions.RepositoryNotFoundException:
        pass
    if not commit:
        print(f"  [plan] create ecr {REPO} (IMMUTABLE, scan-on-push, AES256)")
        return
    r = ecr.create_repository(
        repositoryName=REPO, imageTagMutability="IMMUTABLE",
        imageScanningConfiguration={"scanOnPush": True},
        encryptionConfiguration={"encryptionType": "AES256"},
        tags=[{"Key": "Project", "Value": "DRISHTI"},
              {"Key": "Component", "Value": "gpu-worker"}])["repository"]
    _ok(f"ecr {REPO}", r["repositoryUri"])


# --------------------------------------------------------------------------- #
# 4. SageMaker execution role
# --------------------------------------------------------------------------- #
def exec_policy_doc(key_arn: str) -> dict:
    """Scoped execution policy. Wildcards only where AWS requires them
    (ecr:GetAuthorizationToken and cloudwatch:PutMetricData are not
    resource-scopable)."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "EcrAuthToken", "Effect": "Allow",
             "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
            {"Sid": "EcrPullWorkerImageOnly", "Effect": "Allow",
             "Action": ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage"],
             "Resource": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{REPO}"},
            {"Sid": "S3AsyncIoModelPlaneOnly", "Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
             "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
            {"Sid": "KmsModelPlaneCmkOnly", "Effect": "Allow",
             "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
             "Resource": key_arn},
            {"Sid": "SageMakerLogs", "Effect": "Allow",
             "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                        "logs:DescribeLogStreams"],
             "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/sagemaker/*"},
            {"Sid": "SageMakerMetrics", "Effect": "Allow",
             "Action": ["cloudwatch:PutMetricData"], "Resource": "*"},
        ],
    }


def ensure_exec_role(commit: bool, key_arn: str | None) -> None:
    iam = _sess().client("iam")
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "sagemaker.amazonaws.com"},
        "Action": "sts:AssumeRole"}]}
    if not commit:
        print(f"  [plan] create iam role {EXEC_ROLE} + scoped inline policy")
        return
    if not key_arn:
        print("  [skip] exec role needs the CMK arn first")
        return
    try:
        iam.create_role(RoleName=EXEC_ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                        Description="DRISHTI GPU worker SageMaker execution role",
                        Tags=[{"Key": "Project", "Value": "DRISHTI"}])
        _ok(f"iam role {EXEC_ROLE}", "created; waiting for propagation")
        time.sleep(12)
    except iam.exceptions.EntityAlreadyExistsException:
        _exists(f"iam role {EXEC_ROLE}")
    doc = exec_policy_doc(key_arn)
    iam.put_role_policy(RoleName=EXEC_ROLE, PolicyName=EXEC_POLICY_NAME,
                        PolicyDocument=json.dumps(doc))
    _ok(f"iam inline policy {EXEC_POLICY_NAME}")
    with open(_POLICY_PATH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    _ok("rewrote iam/sagemaker-exec-policy.json to the applied document")


# --------------------------------------------------------------------------- #
# Persist resolved values
# --------------------------------------------------------------------------- #
def write_back(key_id: str | None, key_arn: str | None) -> None:
    if not key_id or not key_arn:
        return
    cfg = json.load(open(_CFG_PATH, encoding="utf-8"))
    if cfg["kms"].get("key_arn") == key_arn:
        return
    cfg["kms"]["key_id"] = key_id
    cfg["kms"]["key_arn"] = key_arn
    cfg["kms"]["_note"] = ("Created by bootstrap_infra.py; sagemaker_ops.py reads key_arn "
                           "for the async output KMS config.")
    with open(_CFG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    _ok("wrote kms.key_id/key_arn into deploy.generated.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="actually create the resources")
    ap.add_argument("--plan", action="store_true", help="default; show what would be created")
    args = ap.parse_args()
    commit = args.commit

    print(f"[bootstrap] account={ACCOUNT} region={REGION} profile={PROFILE} "
          f"mode={'COMMIT' if commit else 'PLAN'}")
    ident = _sess().client("sts").get_caller_identity()
    if ident["Account"] != ACCOUNT:
        print(f"[abort] caller account {ident['Account']} != config account {ACCOUNT}")
        return 1

    print("\n1. KMS model-plane CMK")
    key_id, key_arn = ensure_kms(commit)
    print("\n2. S3 model-plane bucket")
    ensure_bucket(commit, key_arn)
    print("\n3. ECR worker repo")
    ensure_ecr(commit)
    print("\n4. SageMaker execution role")
    ensure_exec_role(commit, key_arn)
    write_back(key_id, key_arn)

    if not commit:
        print("\n[plan-only] no resources created. Re-run with --commit.")
    else:
        print("\n[done] foundation infra ready. Next: "
              "python infra/aws/gpu-worker/codebuild_image.py deploy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
