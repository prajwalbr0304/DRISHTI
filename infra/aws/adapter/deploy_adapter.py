#!/usr/bin/env python
"""DRISHTI Prompt 24 - protected AWS adapter deploy (Lambda + HTTP API Gateway).

Deploys ``services/aws-adapter`` as the ONLY ingress from Catalyst AppSail to the
SageMaker model plane:

    AppSail --(signed HTTPS)--> HTTP API Gateway --> Lambda adapter --> SageMaker async

Creates (idempotent): a shared HMAC secret (Secrets Manager), an SQS dead-letter
queue, a least-privilege execution role, the Lambda (zipped from services/aws-adapter),
an HTTP API with a catch-all route, and the invoke permission. boto3 + drishti SSO
profile; no static keys. Reads shared values from ../gpu-worker/deploy.generated.json.

Subcommands:
  deploy      create/update everything; print the invoke URL + secret ARN (never the value)
  url         print the current invoke URL
  secret      print ONLY the secret ARN (for wiring AppSail via reference)
  teardown    delete the API + Lambda + role + DLQ (secret retained unless --purge-secret)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import time
import zipfile

import boto3

_HERE = os.path.dirname(__file__)
_SHARED = json.load(open(os.path.join(_HERE, "..", "gpu-worker", "deploy.generated.json"),
                         encoding="utf-8"))

REGION = _SHARED["region"]
PROFILE = os.getenv("AWS_PROFILE", "drishti")
ACCOUNT = _SHARED["account_id"]
BUCKET = _SHARED["s3"]["bucket"]
KMS_ARN = _SHARED["kms"]["key_arn"]
ENDPOINT = _SHARED["sagemaker"]["endpoint_name"]
BEDROCK_MODEL_ID = "zai.glm-4.7-flash"

FUNCTION = "drishti-aws-adapter"
ROLE = "drishti-aws-adapter-exec"
DLQ = "drishti-adapter-dlq"
SECRET_NAME = "drishti/aws-adapter-secret"
API_NAME = "drishti-aws-adapter-api"
SRC = os.path.join(_HERE, "..", "..", "..", "services", "aws-adapter")


def _sess():
    return boto3.Session(profile_name=PROFILE, region_name=REGION)


# --------------------------------------------------------------------------- #
def _ensure_secret() -> str:
    sm = _sess().client("secretsmanager")
    try:
        d = sm.describe_secret(SecretId=SECRET_NAME)
        return d["ARN"]
    except sm.exceptions.ResourceNotFoundException:
        val = secrets.token_hex(32)
        r = sm.create_secret(Name=SECRET_NAME, SecretString=val,
                             Description="DRISHTI Prompt 24 adapter HMAC signing secret (synthetic)")
        print("  [ok] created adapter secret (Secrets Manager)")
        return r["ARN"]


def _secret_value() -> str:
    sm = _sess().client("secretsmanager")
    return sm.get_secret_value(SecretId=SECRET_NAME)["SecretString"]


def _ensure_dlq() -> str:
    sqs = _sess().client("sqs")
    try:
        return sqs.get_queue_url(QueueName=DLQ)["QueueUrl"]
    except sqs.exceptions.QueueDoesNotExist:
        r = sqs.create_queue(QueueName=DLQ, Attributes={"MessageRetentionPeriod": "1209600",
                                                        "KmsMasterKeyId": "alias/aws/sqs"})
        print("  [ok] created DLQ")
        return r["QueueUrl"]


def _dlq_arn(url: str) -> str:
    sqs = _sess().client("sqs")
    return sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])[
        "Attributes"]["QueueArn"]


def _role_arn(secret_arn: str, dlq_arn: str) -> str:
    iam = _sess().client("iam")
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
             "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "InvokeAsyncEndpointOnly", "Effect": "Allow",
             "Action": ["sagemaker:InvokeEndpointAsync", "sagemaker:InvokeEndpoint"],
             "Resource": f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:endpoint/{ENDPOINT}"},
            {"Sid": "InvokeApprovedChineseBedrockModelOnly", "Effect": "Allow",
             "Action": ["bedrock:InvokeModel"],
             "Resource": f"arn:aws:bedrock:{REGION}::foundation-model/{BEDROCK_MODEL_ID}"},
            {"Sid": "S3StagingOnly", "Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
             "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
            {"Sid": "KmsModelPlaneCmk", "Effect": "Allow",
             "Action": ["kms:Decrypt", "kms:GenerateDataKey"], "Resource": KMS_ARN},
            {"Sid": "SecretRead", "Effect": "Allow",
             "Action": ["secretsmanager:GetSecretValue"], "Resource": secret_arn},
            {"Sid": "Dlq", "Effect": "Allow", "Action": ["sqs:SendMessage"], "Resource": dlq_arn},
            {"Sid": "Logs", "Effect": "Allow",
             "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
             "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:*"},
        ],
    }
    try:
        r = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                            Description="DRISHTI Prompt 24 adapter Lambda execution role")
        arn = r["Role"]["Arn"]
        print("  [ok] created adapter role")
        time.sleep(10)  # allow role propagation
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE, PolicyName="drishti-aws-adapter-inline",
                        PolicyDocument=json.dumps(policy))
    return arn


def _zip_source() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("handler.py", "dispatch.py", "signing.py", "schema.py", "circuit.py",
                     "bedrock.py"):
            zf.write(os.path.join(SRC, name), name)
    return buf.getvalue()


def _ensure_lambda(role_arn: str, secret_val: str, dlq_arn: str) -> str:
    lam = _sess().client("lambda")
    code = _zip_source()
    env = {"Variables": {
        "DRISHTI_AWS_ADAPTER_SECRET": secret_val,
        "DRISHTI_SM_ASYNC_ENDPOINT": ENDPOINT,
        "DRISHTI_ADAPTER_S3_STAGING": f"s3://{BUCKET}/async-io",
        "DRISHTI_ADAPTER_MAX_SKEW_S": "300",
        "DRISHTI_ADAPTER_RATE_PER_MIN": "600",
        "DRISHTI_BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
    }}
    try:
        lam.get_function(FunctionName=FUNCTION)
        lam.update_function_code(FunctionName=FUNCTION, ZipFile=code, Publish=True)
        _wait_updated(lam)
        lam.update_function_configuration(
            FunctionName=FUNCTION, Environment=env, Timeout=60, MemorySize=512,
            DeadLetterConfig={"TargetArn": dlq_arn})
        print("  [ok] updated adapter Lambda")
    except lam.exceptions.ResourceNotFoundException:
        lam.create_function(
            FunctionName=FUNCTION, Runtime="python3.12", Role=role_arn,
            Handler="handler.lambda_handler", Code={"ZipFile": code},
            Timeout=60, MemorySize=512, Environment=env,
            DeadLetterConfig={"TargetArn": dlq_arn}, Publish=True,
            Description="DRISHTI Prompt 24 protected AWS adapter (signed HMAC ingress to SageMaker async)")
        print("  [ok] created adapter Lambda")
    _wait_updated(lam)
    return lam.get_function(FunctionName=FUNCTION)["Configuration"]["FunctionArn"]


def _wait_updated(lam) -> None:
    for _ in range(30):
        cfg = lam.get_function(FunctionName=FUNCTION)["Configuration"]
        if cfg.get("LastUpdateStatus") in (None, "Successful"):
            return
        if cfg.get("LastUpdateStatus") == "Failed":
            raise SystemExit("Lambda update failed")
        time.sleep(2)


def _ensure_api(fn_arn: str) -> str:
    api = _sess().client("apigatewayv2")
    lam = _sess().client("lambda")
    apis = api.get_apis().get("Items", [])
    existing = next((a for a in apis if a["Name"] == API_NAME), None)
    if existing:
        api_id = existing["ApiId"]
    else:
        r = api.create_api(Name=API_NAME, ProtocolType="HTTP",
                           Description="DRISHTI Prompt 24 protected adapter ingress")
        api_id = r["ApiId"]
        print("  [ok] created HTTP API")
    integ = api.create_integration(
        ApiId=api_id, IntegrationType="AWS_PROXY", IntegrationUri=fn_arn,
        PayloadFormatVersion="2.0", IntegrationMethod="POST")["IntegrationId"]
    for route in ("POST /predict", "GET /predict/{request_id}",
                  "POST /bedrock/converse", "GET /ping"):
        try:
            api.create_route(ApiId=api_id, RouteKey=route, Target=f"integrations/{integ}")
        except api.exceptions.ConflictException:
            pass
    try:
        api.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    except api.exceptions.ConflictException:
        pass
    try:
        lam.add_permission(FunctionName=FUNCTION, StatementId="apigw-invoke",
                           Action="lambda:InvokeFunction", Principal="apigateway.amazonaws.com",
                           SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api_id}/*/*")
    except lam.exceptions.ResourceConflictException:
        pass
    return f"https://{api_id}.execute-api.{REGION}.amazonaws.com"


def cmd_deploy(args) -> int:
    print("[adapter] ensuring secret / DLQ / role / lambda / api ...")
    secret_arn = _ensure_secret()
    secret_val = _secret_value()
    dlq_url = _ensure_dlq()
    dlq_arn = _dlq_arn(dlq_url)
    role_arn = _role_arn(secret_arn, dlq_arn)
    fn_arn = _ensure_lambda(role_arn, secret_val, dlq_arn)
    url = _ensure_api(fn_arn)
    out = {"adapter_url": url, "secret_arn": secret_arn, "function_arn": fn_arn,
           "dlq_arn": dlq_arn, "sm_async_endpoint": ENDPOINT,
           "bedrock_model_id": BEDROCK_MODEL_ID}
    print(json.dumps(out, indent=2))
    # persist non-secret wiring for the report + AppSail env (value NOT written here)
    with open(os.path.join(_HERE, "adapter.deployed.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return 0


def cmd_url(args) -> int:
    api = _sess().client("apigatewayv2")
    a = next((x for x in api.get_apis().get("Items", []) if x["Name"] == API_NAME), None)
    print(f"https://{a['ApiId']}.execute-api.{REGION}.amazonaws.com" if a else "(no api)")
    return 0


def cmd_secret(args) -> int:
    print(_ensure_secret())
    return 0


def cmd_teardown(args) -> int:
    s = _sess()
    api = s.client("apigatewayv2")
    for a in api.get_apis().get("Items", []):
        if a["Name"] == API_NAME:
            api.delete_api(ApiId=a["ApiId"]); print("  [ok] deleted API")
    lam = s.client("lambda")
    try:
        lam.delete_function(FunctionName=FUNCTION); print("  [ok] deleted Lambda")
    except lam.exceptions.ResourceNotFoundException:
        pass
    iam = s.client("iam")
    try:
        iam.delete_role_policy(RoleName=ROLE, PolicyName="drishti-aws-adapter-inline")
        iam.delete_role(RoleName=ROLE); print("  [ok] deleted role")
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] role: {str(exc)[:120]}")
    if args.purge_secret:
        s.client("secretsmanager").delete_secret(SecretId=SECRET_NAME,
                                                 ForceDeleteWithoutRecovery=True)
        print("  [ok] purged secret")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deploy")
    sub.add_parser("url")
    sub.add_parser("secret")
    td = sub.add_parser("teardown")
    td.add_argument("--purge-secret", action="store_true")
    args = ap.parse_args()
    return {"deploy": cmd_deploy, "url": cmd_url, "secret": cmd_secret,
            "teardown": cmd_teardown}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
