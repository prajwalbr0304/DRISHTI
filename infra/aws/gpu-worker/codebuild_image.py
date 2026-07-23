#!/usr/bin/env python
"""DRISHTI Prompt 24 - build the GPU worker image IN AWS CodeBuild and push to ECR.

The local build host has limited disk + a slow residential uplink, so the image
is built in-cloud: CodeBuild pulls the CUDA base, pip-installs torch/tabfm/timesfm,
and pushes the image to the private ECR repo by digest - no local image export and
no residential push. boto3 + drishti SSO profile. Reads deploy.generated.json.

Subcommands:
  deploy   ensure CodeBuild role + upload source zip + create/update project + start build + wait
  digest   print the pushed image digest from ECR
  logs     print the last CloudWatch log lines for the most recent build
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
import zipfile

import boto3

_HERE = os.path.dirname(__file__)
_CFG = json.load(open(os.path.join(_HERE, "deploy.generated.json"), encoding="utf-8"))

REGION = _CFG["region"]
PROFILE = os.getenv("AWS_PROFILE", "drishti")
ACCOUNT = _CFG["account_id"]
REPO_URI = _CFG["ecr"]["repository_uri"]
REPO = _CFG["ecr"]["repository"]
BUCKET = _CFG["s3"]["bucket"]
PROJECT = "drishti-gpu-worker-build"
ROLE = "drishti-codebuild-role"
SRC_DIR = os.path.join(_HERE, "..", "..", "..", "services", "gpu-worker")
SRC_KEY = "codebuild/gpu-worker-source.zip"
TAG = os.getenv("DRISHTI_IMAGE_TAG", "0.2.3")

BUILDSPEC = """version: 0.2
phases:
  pre_build:
    commands:
      - echo "ECR login"
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
  build:
    commands:
      - echo "docker build"
      - docker build -f Dockerfile -t $ECR_REPO_URI:$IMAGE_TAG .
  post_build:
    commands:
      - echo "docker push"
      - docker push $ECR_REPO_URI:$IMAGE_TAG
      - aws ecr describe-images --repository-name $ECR_REPO --region $AWS_REGION --image-ids imageTag=$IMAGE_TAG --query "imageDetails[0].imageDigest" --output text
"""


def _sess():
    return boto3.Session(profile_name=PROFILE, region_name=REGION)


def _ensure_role() -> str:
    iam = _sess().client("iam")
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
             "Principal": {"Service": "codebuild.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
        {"Effect": "Allow", "Action": [
            "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
            "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage",
            "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"],
         "Resource": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{REPO}"},
        {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": f"arn:aws:s3:::{BUCKET}/*"},
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream",
                                       "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:*"},
    ]}
    try:
        arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                              Description="DRISHTI Prompt 24 CodeBuild image builder")["Role"]["Arn"]
        print("  [ok] created CodeBuild role; waiting for propagation")
        time.sleep(12)
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE, PolicyName="drishti-codebuild-inline",
                        PolicyDocument=json.dumps(policy))
    return arn


def _upload_source() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("Dockerfile", "requirements.txt", "schema.py", "backends.py",
                     "handler.py", "_tabfm_loader.py", "selftest.py"):
            zf.write(os.path.join(SRC_DIR, name), name)
        zf.writestr("buildspec.yml", BUILDSPEC)
    _sess().client("s3").put_object(Bucket=BUCKET, Key=SRC_KEY, Body=buf.getvalue(),
                                    ServerSideEncryption="aws:kms")
    print(f"  [ok] uploaded source -> s3://{BUCKET}/{SRC_KEY}")


def _ensure_project(role_arn: str) -> None:
    cb = _sess().client("codebuild")
    env = {"type": "LINUX_CONTAINER",
           "image": "aws/codebuild/amazonlinux-x86_64-standard:5.0",
           "computeType": "BUILD_GENERAL1_LARGE", "privilegedMode": True,
           "environmentVariables": [
               {"name": "AWS_REGION", "value": REGION},
               {"name": "ECR_REGISTRY", "value": f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com"},
               {"name": "ECR_REPO_URI", "value": REPO_URI},
               {"name": "ECR_REPO", "value": REPO},
               {"name": "IMAGE_TAG", "value": TAG}]}
    source = {"type": "S3", "location": f"{BUCKET}/{SRC_KEY}"}
    kwargs = dict(name=PROJECT, source=source, artifacts={"type": "NO_ARTIFACTS"},
                  environment=env, serviceRole=role_arn,
                  timeoutInMinutes=40,
                  description="DRISHTI Prompt 24 GPU worker image builder")
    try:
        cb.create_project(**kwargs)
        print("  [ok] created CodeBuild project")
    except cb.exceptions.ResourceAlreadyExistsException:
        cb.update_project(**kwargs)
        print("  [ok] updated CodeBuild project")


def cmd_deploy(args) -> int:
    role_arn = _ensure_role()
    _upload_source()
    _ensure_project(role_arn)
    cb = _sess().client("codebuild")
    build_id = cb.start_build(projectName=PROJECT)["build"]["id"]
    print(f"[codebuild] started {build_id}")
    last_phase = None
    t0 = time.time()
    while True:
        info = cb.batch_get_builds(ids=[build_id])["builds"][0]
        status = info["buildStatus"]
        phase = info.get("currentPhase")
        if phase != last_phase:
            print(f"  [{int(time.time() - t0)}s] phase={phase} status={status}")
            last_phase = phase
        if status != "IN_PROGRESS":
            print(f"[codebuild] final status={status} after {int(time.time() - t0)}s")
            if status != "SUCCEEDED":
                _print_phase_failures(info)
                return 2
            break
        time.sleep(15)
    print(cmd_digest(args))
    return 0


def _print_phase_failures(info: dict) -> None:
    for ph in info.get("phases", []):
        if ph.get("phaseStatus") in ("FAILED", "FAULT", "TIMED_OUT"):
            ctx = ph.get("contexts", [{}])
            print(f"  FAILED phase {ph.get('phaseType')}: "
                  f"{ctx[0].get('message') if ctx else ''}")


def cmd_digest(args) -> str:
    ecr = _sess().client("ecr")
    try:
        d = ecr.describe_images(repositoryName=REPO,
                                imageIds=[{"imageTag": TAG}])["imageDetails"][0]
        return f"{REPO_URI}@{d['imageDigest']}  (pushed {d.get('imagePushedAt')})"
    except Exception as exc:  # noqa: BLE001
        return f"(no image tag {TAG} yet: {exc})"


def cmd_logs(args) -> int:
    cb = _sess().client("codebuild")
    ids = cb.list_builds_for_project(projectName=PROJECT)["ids"][:1]
    if not ids:
        print("(no builds)")
        return 1
    info = cb.batch_get_builds(ids=ids)["builds"][0]
    logs_info = info.get("logs", {})
    group, stream = logs_info.get("groupName"), logs_info.get("streamName")
    if not group:
        print("(no logs yet)")
        return 1
    logs = _sess().client("logs")
    ev = logs.get_log_events(logGroupName=group, logStreamName=stream,
                             limit=args.lines, startFromHead=False)["events"]
    for e in ev:
        print(e["message"].rstrip())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deploy")
    sub.add_parser("digest")
    lg = sub.add_parser("logs")
    lg.add_argument("--lines", type=int, default=60)
    args = ap.parse_args()
    return {"deploy": cmd_deploy, "digest": lambda a: print(cmd_digest(a)) or 0,
            "logs": cmd_logs}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
