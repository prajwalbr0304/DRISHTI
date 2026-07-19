#!/usr/bin/env python
"""Deploy the DRISHTI GPU worker to AWS — SEPARATELY from the Catalyst pipeline
(Prompt 14 Part I + G.3).

The Catalyst pipeline never rebuilds GPU images. The GPU worker is built + pushed
to a PRIVATE ECR repo by immutable digest and served by ONE SageMaker asynchronous
endpoint, referenced by immutable image + model versions.

``deploy_gpu_worker.py`` validates ``gpu-worker-infra.json`` against the G.2/G.3
scoping and prints the ordered AWS CLI / SageMaker commands. The DEFAULT action is
``--plan``: fully offline, no boto3, no credentials, no AWS calls — so it runs
here as a review + guardrail gate. ``--commit`` shells out to the ``aws`` CLI and
is HELD behind ``--yes-spend-credits`` for an explicit go-ahead.

No secrets are printed. Credentials come from the environment / SSO profile /
role — never from arguments or code.

Usage (PowerShell):
    python infra/aws/gpu-worker/deploy_gpu_worker.py                 # plan (offline)
    python infra/aws/gpu-worker/deploy_gpu_worker.py --commit --yes-spend-credits   # HELD
    python infra/aws/gpu-worker/deploy_gpu_worker.py --teardown      # plan the shutdown
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(__file__)


def _load(rel: str) -> dict:
    with open(os.path.join(_HERE, rel), "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate() -> tuple[dict, list[str]]:
    """Load + validate the descriptor against the G.2/G.3 rules. Returns (infra, issues)."""
    issues: list[str] = []
    infra = _load("gpu-worker-infra.json")

    # G.3: exactly one mechanism, SageMaker async.
    if infra.get("mechanism") != "sagemaker_async":
        issues.append(f"mechanism must be 'sagemaker_async' (G.3), got {infra.get('mechanism')!r}")

    ecr = infra.get("ecr", {})
    if ecr.get("image_tag_mutability") != "IMMUTABLE":
        issues.append("ecr.image_tag_mutability must be IMMUTABLE")
    if ecr.get("reference_by") != "digest" or "@sha256:" not in str(ecr.get("image_uri", "")):
        issues.append("ecr image must be referenced by @sha256 digest, not a mutable tag")

    art = infra.get("model_artifacts", {})
    if "kms" not in str(art.get("encryption", "")).lower():
        issues.append("model artifacts must be KMS-encrypted")
    if not art.get("versioning"):
        issues.append("model artifact bucket must have versioning enabled")
    enabled = [o for o in art.get("objects", []) if o.get("enabled")]
    if not enabled:
        issues.append("at least one enabled model artifact is required")

    sm = infra.get("sagemaker", {})
    if not sm.get("execution_role", "").startswith("arn:aws:iam::"):
        issues.append("sagemaker.execution_role (IAM role) is required — no static credentials")
    variant = sm.get("production_variant", {})
    itype = variant.get("instance_type", "")
    if not itype.startswith("ml.g") and not itype.startswith("ml.p"):
        issues.append(f"instance_type must be a GPU type (ml.g*/ml.p*), got {itype!r}")
    if "serverless" in itype.lower():
        issues.append("SageMaker Serverless has no GPU — forbidden for a GPU workload (G.3)")
    if sm.get("autoscaling", {}).get("min_capacity") != 0:
        issues.append("autoscaling.min_capacity must be 0 (scale to zero)")

    # No static credential material anywhere in the descriptor.
    blob = json.dumps(infra)
    if re.search(r"AKIA[0-9A-Z]{16}", blob) or re.search(r"aws_secret_access_key", blob, re.I):
        issues.append("descriptor appears to contain static AWS credentials — forbidden")

    return infra, issues


def build_plan(infra: dict) -> list[tuple[str, str]]:
    """Ordered (description, command) steps. Placeholders are filled by the operator."""
    ecr, art, sm = infra["ecr"], infra["model_artifacts"], infra["sagemaker"]
    repo, region = ecr["repository"], infra["region"]
    endpoint = sm["endpoint_name"]
    steps = [
        ("Create the PRIVATE, IMMUTABLE, scan-on-push ECR repo (idempotent)",
         f"aws ecr create-repository --repository-name {repo} --region {region} "
         "--image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true "
         "--encryption-configuration encryptionType=KMS || true"),
        ("Build the linux/amd64 GPU image (Docker/buildx on a build host)",
         ecr["build"]),
        ("Push + capture the immutable digest (reference the image by @sha256 only)",
         f"docker push <ACCOUNT_ID>.dkr.ecr.{region}.amazonaws.com/{repo}:<VER> ; "
         f"aws ecr describe-images --repository-name {repo} --region {region} "
         "--query 'imageDetails[0].imageDigest'"),
        ("Upload each ENABLED model artifact to the KMS-encrypted, versioned S3 prefix",
         "; ".join(
             f"aws s3 cp {o['version']}/model.tar.gz s3://{art['s3_bucket']}/{o['key']} --sse aws:kms"
             for o in art["objects"] if o.get("enabled"))),
        ("Create the SageMaker model (by immutable image digest + model data URL)",
         f"aws sagemaker create-model --model-name {sm['model_name']} "
         f"--execution-role-arn {sm['execution_role']} "
         f"--primary-container Image={ecr['image_uri']},ModelDataUrl=s3://{art['s3_bucket']}/"
         f"{enabled_key(art)} --region {region}"),
        ("Create the ASYNC endpoint config (one variant, scale-to-zero autoscaling)",
         f"aws sagemaker create-endpoint-config --endpoint-config-name {endpoint}-cfg "
         f"--production-variants VariantName=main,ModelName={sm['model_name']},"
         f"InstanceType={sm['production_variant']['instance_type']},InitialInstanceCount=1 "
         f"--async-inference-config OutputConfig={{S3OutputPath={sm['async_inference']['s3_output_path']}}} "
         f"--region {region}"),
        ("Create the endpoint",
         f"aws sagemaker create-endpoint --endpoint-name {endpoint} "
         f"--endpoint-config-name {endpoint}-cfg --region {region}"),
        ("Register scale-to-zero autoscaling (min=0) for the async endpoint",
         f"aws application-autoscaling register-scalable-target --service-namespace sagemaker "
         f"--resource-id endpoint/{endpoint}/variant/main "
         "--scalable-dimension sagemaker:variant:DesiredInstanceCount "
         "--min-capacity 0 --max-capacity 2"),
        ("Point the Part F adapter at this one endpoint",
         f"set DRISHTI_SM_ASYNC_ENDPOINT={endpoint}  (on the adapter Lambda/ECS)"),
    ]
    return steps


def enabled_key(art: dict) -> str:
    for o in art.get("objects", []):
        if o.get("enabled"):
            return o["key"]
    return "<MODEL_KEY>"


def teardown_plan(infra: dict) -> list[tuple[str, str]]:
    sm = infra["sagemaker"]
    return [
        ("Stop GPU after testing — delete the endpoint (J cost safety)",
         f"aws sagemaker delete-endpoint --endpoint-name {sm['endpoint_name']} --region {infra['region']}"),
        ("Delete the endpoint config",
         f"aws sagemaker delete-endpoint-config --endpoint-config-name {sm['endpoint_name']}-cfg "
         f"--region {infra['region']}"),
        ("(Image + model artifacts are RETAINED in ECR/S3 for a later immutable redeploy)", ""),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy the DRISHTI GPU worker (SageMaker async).")
    ap.add_argument("--commit", action="store_true", help="execute via the aws CLI (HELD)")
    ap.add_argument("--yes-spend-credits", action="store_true",
                    help="required with --commit; confirms this spends AWS credits")
    ap.add_argument("--teardown", action="store_true", help="plan the shutdown/cleanup instead")
    args = ap.parse_args()

    infra, issues = validate()
    if issues:
        print("VALIDATION FAILED:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print(f"[ok] descriptor valid — one {infra['mechanism']} endpoint, "
          f"image by digest, model versioned, scale-to-zero, IAM role (no static creds).")

    steps = teardown_plan(infra) if args.teardown else build_plan(infra)
    print(f"\n{'TEARDOWN' if args.teardown else 'DEPLOY'} PLAN ({len(steps)} steps):")
    for n, (desc, cmd) in enumerate(steps, 1):
        print(f"\n  {n}. {desc}")
        if cmd:
            print(f"     $ {cmd}")

    if not args.commit:
        print("\n[plan-only] offline; no AWS calls made. Re-run with "
              "--commit --yes-spend-credits to execute (HELD).")
        return 0
    if not args.yes_spend_credits:
        print("\n[HELD] --commit requires --yes-spend-credits (this spends AWS credits + needs the account).")
        return 2
    # Real execution (HELD path): shell out to the aws CLI, step by step.
    for desc, cmd in steps:
        if not cmd or cmd.startswith("set "):
            continue
        print(f"\n$ {cmd}")
        rc = subprocess.run(cmd, shell=True).returncode
        if rc != 0:
            print(f"[abort] step failed (rc={rc}): {desc}")
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
