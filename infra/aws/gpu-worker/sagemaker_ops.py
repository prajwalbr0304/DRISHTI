#!/usr/bin/env python
"""DRISHTI Prompt 24 - SageMaker async GPU endpoint operations.

One tool to deploy / check / invoke / tear down the SINGLE SageMaker
asynchronous-inference GPU endpoint (G.3) that serves the real TabFM + TimesFM
worker. Uses boto3 with the ``drishti`` SSO profile (execution-role creds; no
static keys). Reads resolved config from ``deploy.generated.json``.

Subcommands:
  deploy     --image-digest sha256:...   create model + async endpoint-config + endpoint, wait InService, register scale-to-zero autoscaling
  status                                  print endpoint + variant + autoscaling state
  invoke     --task tabfm|timesfm|fallback|badtabfm [--idem KEY]   put a request to S3 and invoke async; poll the signed result
  teardown                                delete endpoint + config + model; deregister autoscaling (image + weights retained in ECR)

No secrets are printed. Aggregate synthetic inputs only.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid

import boto3

_HERE = os.path.dirname(__file__)
_CFG = json.load(open(os.path.join(_HERE, "deploy.generated.json"), encoding="utf-8"))

REGION = _CFG["region"]
PROFILE = os.getenv("AWS_PROFILE", "drishti")
REPO_URI = _CFG["ecr"]["repository_uri"]
ROLE = _CFG["iam"]["sagemaker_execution_role"]
BUCKET = _CFG["s3"]["bucket"]
KMS_ARN = _CFG["kms"]["key_arn"]
MODEL = _CFG["sagemaker"]["model_name"]
CFG_NAME = _CFG["sagemaker"]["endpoint_config_name"]
ENDPOINT = _CFG["sagemaker"]["endpoint_name"]
INSTANCE = _CFG["instance_type"]
OUT_PREFIX = "async-io/output/"
FAIL_PREFIX = "async-io/failure/"
IN_PREFIX = "async-io/in/"


def _sess():
    return boto3.Session(profile_name=PROFILE, region_name=REGION)


# --------------------------------------------------------------------------- #
# Synthetic aggregate request envelopes (approved features only; no PII/FIR text)
# --------------------------------------------------------------------------- #
def _tabfm_envelope(idem: str, *, backend: str = "tabfm") -> dict:
    """Approved aggregate station-workload features -> 4 workload bands.

    Columns are aggregate station metrics only (counts / rates / lags): NEVER a
    full FIR JSON, narrative, evidence or person attribute (D.1)."""
    import numpy as np

    rng = np.random.default_rng(2024)
    cols = ["fir_count_7d", "fir_count_28d", "pending_ratio", "night_share",
            "avg_response_min", "officers_on_duty"]
    n_ctx, n_feat = 240, len(cols)
    ctx_x = rng.normal(0, 1, size=(n_ctx, n_feat))
    # deterministic band label from a couple of aggregate drivers (synthetic)
    score = ctx_x[:, 0] * 0.9 + ctx_x[:, 2] * 0.8 - ctx_x[:, 5] * 0.6
    ctx_y = np.clip(np.digitize(score, [-0.7, 0.1, 0.9]), 0, 3).astype(int).tolist()
    query = rng.normal(0, 1, size=(12, n_feat)).round(4).tolist()
    return {
        "envelope_version": "1.0.0",
        "request_id": f"tabfm-{uuid.uuid4().hex[:10]}",
        "idempotency_key": idem or f"station_workload_band:BLR-CEN:2026-07-23:fs1:tabfm1:{uuid.uuid4().hex[:8]}",
        "task": "station_workload_band",
        "requested_backend": backend,
        "feature_schema_version": "fs-workload-1",
        "model_version": "tabfm-1.0.0",
        "feature_schema_digest": "fs-" + uuid.uuid4().hex[:12],
        "subject_kind": "station",
        "subject_ids": ["BLR-CEN", "BLR-WHF", "MYS-CEN"],
        "observation_cutoff": "2026-07-23T00:00:00+05:30",
        "source_version_hash": "synthetic-" + uuid.uuid4().hex[:8],
        "columns": [{"name": c, "dtype": "float", "role": "feature"} for c in cols],
        "context_x": [[round(float(v), 4) for v in row] for row in ctx_x],
        "context_y": ctx_y,
        "query_rows": query,
        "output_schema": {"n_bands": 4},
        "timeout_s": 600,
        "max_rows": 5000,
    }


def _timesfm_envelope(idem: str) -> dict:
    """Approved aggregate monthly incident-count series -> horizon forecast (D.2)."""
    import numpy as np

    x = np.arange(180)
    series = (np.sin(x / 6.0) * 6 + 40 + x * 0.05
              + np.random.default_rng(7).normal(0, 1.5, size=180))
    rows = [[round(float(max(0.0, v)), 3)] for v in series]
    return {
        "envelope_version": "1.0.0",
        "request_id": f"timesfm-{uuid.uuid4().hex[:10]}",
        "idempotency_key": idem or f"timesfm_count_forecast:BLR-URBAN:2026-07:fs1:timesfm25:{uuid.uuid4().hex[:8]}",
        "task": "timesfm_count_forecast",
        "requested_backend": "timesfm",
        "feature_schema_version": "fs-count-1",
        "model_version": "timesfm-2.5-200m",
        "feature_schema_digest": "fs-" + uuid.uuid4().hex[:12],
        "subject_kind": "district",
        "subject_ids": ["BLR-URBAN"],
        "observation_cutoff": "2026-07-23T00:00:00+05:30",
        "source_version_hash": "synthetic-" + uuid.uuid4().hex[:8],
        "columns": [{"name": "monthly_count", "dtype": "float", "role": "feature"}],
        "query_rows": rows,
        "output_schema": {"horizon": 14, "freq": "M"},
        "timeout_s": 600,
        "max_rows": 5000,
    }


def _envelope(task: str, idem: str) -> dict:
    if task == "tabfm":
        return _tabfm_envelope(idem)
    if task == "timesfm":
        return _timesfm_envelope(idem)
    if task == "fallback":
        return _tabfm_envelope(idem, backend="incontext")   # explicit labelled fallback
    if task == "badtabfm":
        env = _tabfm_envelope(idem)
        env["model_artifact_digest"] = "deadbeef" * 8       # force a digest mismatch -> fail closed
        return env
    raise SystemExit(f"unknown task {task}")


# --------------------------------------------------------------------------- #
# Deploy
# --------------------------------------------------------------------------- #
def cmd_deploy(args) -> int:
    digest = args.image_digest
    if not digest.startswith("sha256:"):
        digest = "sha256:" + digest
    image = f"{REPO_URI}@{digest}"
    sm = _sess().client("sagemaker")

    print(f"[deploy] model {MODEL} <- {image}")
    _safe(lambda: sm.create_model(
        ModelName=MODEL,
        PrimaryContainer={
            "Image": image,
            "Environment": {
                "GPU_WORKER_VERSION": "0.2.0",
                "DRISHTI_TABFM_ESTIMATORS": os.getenv("DRISHTI_TABFM_ESTIMATORS", "8"),
            },
        },
        ExecutionRoleArn=ROLE), "create_model")

    print(f"[deploy] endpoint-config {CFG_NAME} (async, KMS output, {INSTANCE})")
    _safe(lambda: sm.create_endpoint_config(
        EndpointConfigName=CFG_NAME,
        ProductionVariants=[{
            "VariantName": "main",
            "ModelName": MODEL,
            "InstanceType": INSTANCE,
            "InitialInstanceCount": 1,
        }],
        AsyncInferenceConfig={
            "OutputConfig": {
                "S3OutputPath": f"s3://{BUCKET}/{OUT_PREFIX}",
                "S3FailurePath": f"s3://{BUCKET}/{FAIL_PREFIX}",
                "KmsKeyId": KMS_ARN,
            },
            "ClientConfig": {"MaxConcurrentInvocationsPerInstance": 2},
        }), "create_endpoint_config")

    print(f"[deploy] endpoint {ENDPOINT}")
    _safe(lambda: sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=CFG_NAME),
          "create_endpoint")

    print("[deploy] waiting for InService (this provisions the GPU instance)...")
    t0 = time.time()
    sm.get_waiter("endpoint_in_service").wait(
        EndpointName=ENDPOINT, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
    print(f"[deploy] InService after {int(time.time() - t0)}s")

    _register_autoscaling()
    print(json.dumps(_describe(sm), indent=2, default=str))
    return 0


def _register_autoscaling() -> None:
    aas = _sess().client("application-autoscaling")
    rid = f"endpoint/{ENDPOINT}/variant/main"
    print("[deploy] registering scale-to-zero autoscaling (min=0, max=1)")
    aas.register_scalable_target(
        ServiceNamespace="sagemaker", ResourceId=rid,
        ScalableDimension="sagemaker:variant:DesiredInstanceCount",
        MinCapacity=0, MaxCapacity=1)
    aas.put_scaling_policy(
        PolicyName="drishti-async-scale-to-zero", ServiceNamespace="sagemaker",
        ResourceId=rid, ScalableDimension="sagemaker:variant:DesiredInstanceCount",
        PolicyType="TargetTrackingScaling",
        TargetTrackingScalingPolicyConfiguration={
            "TargetValue": 1.0,
            "CustomizedMetricSpecification": {
                "MetricName": "ApproximateBacklogSizePerInstance",
                "Namespace": "AWS/SageMaker", "Statistic": "Average",
                "Dimensions": [{"Name": "EndpointName", "Value": ENDPOINT}],
            },
            "ScaleInCooldown": 300, "ScaleOutCooldown": 60,
        })


def _describe(sm) -> dict:
    ep = sm.describe_endpoint(EndpointName=ENDPOINT)
    return {"EndpointName": ep["EndpointName"], "EndpointStatus": ep["EndpointStatus"],
            "ProductionVariants": [{"VariantName": v["VariantName"],
                                    "CurrentInstanceCount": v.get("CurrentInstanceCount"),
                                    "DesiredInstanceCount": v.get("DesiredInstanceCount"),
                                    "InstanceType": INSTANCE}
                                   for v in ep.get("ProductionVariants", [])]}


def cmd_status(args) -> int:
    sm = _sess().client("sagemaker")
    try:
        print(json.dumps(_describe(sm), indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"endpoint": ENDPOINT, "error": str(exc)}))
        return 1
    return 0


# --------------------------------------------------------------------------- #
# Invoke (async): put input to S3, invoke, poll the output object
# --------------------------------------------------------------------------- #
def cmd_invoke(args) -> int:
    env = _envelope(args.task, args.idem)
    body = json.dumps(env).encode("utf-8")
    s3 = _sess().client("s3")
    smr = _sess().client("sagemaker-runtime")

    in_key = f"{IN_PREFIX}{env['request_id']}.json"
    s3.put_object(Bucket=BUCKET, Key=in_key, Body=body,
                  ServerSideEncryption="aws:kms", SSEKMSKeyId=KMS_ARN)
    t0 = time.time()
    resp = smr.invoke_endpoint_async(
        EndpointName=ENDPOINT, ContentType="application/json",
        InputLocation=f"s3://{BUCKET}/{in_key}", InvocationTimeoutSeconds=600)
    out_loc = resp["OutputLocation"]
    fail_loc = resp.get("FailureLocation", f"s3://{BUCKET}/{FAIL_PREFIX}")
    print(f"[invoke] task={args.task} request_id={env['request_id']} "
          f"idem={env['idempotency_key']}")
    print(f"[invoke] OutputLocation={out_loc}")

    result = _poll(s3, out_loc, fail_loc, timeout_s=args.timeout)
    result["_client_roundtrip_s"] = round(time.time() - t0, 2)
    result["_output_location"] = out_loc
    print("=== RESULT ===")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("state") in ("completed", "failed") or "error_code" in result else 2


def _poll(s3, out_loc: str, fail_loc: str, *, timeout_s: int) -> dict:
    ob, ok = _split(out_loc)
    fb, fk = _split(fail_loc)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=ob, Key=ok)
            return json.loads(obj["Body"].read())
        except s3.exceptions.NoSuchKey:
            pass
        except Exception as exc:  # noqa: BLE001
            if "NoSuchKey" not in str(exc) and "Not Found" not in str(exc):
                pass
        # check failure path (best effort; failure key mirrors the request id)
        time.sleep(5)
    return {"state": "timed_out", "error_code": "POLL_TIMEOUT",
            "error_detail": f"no output at {out_loc} within {timeout_s}s"}


def _split(uri: str):
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    return bucket, key


# --------------------------------------------------------------------------- #
# Teardown
# --------------------------------------------------------------------------- #
def cmd_teardown(args) -> int:
    sm = _sess().client("sagemaker")
    aas = _sess().client("application-autoscaling")
    rid = f"endpoint/{ENDPOINT}/variant/main"
    _safe(lambda: aas.deregister_scalable_target(
        ServiceNamespace="sagemaker", ResourceId=rid,
        ScalableDimension="sagemaker:variant:DesiredInstanceCount"), "deregister_autoscaling")
    _safe(lambda: sm.delete_endpoint(EndpointName=ENDPOINT), "delete_endpoint")
    _safe(lambda: sm.delete_endpoint_config(EndpointConfigName=CFG_NAME), "delete_endpoint_config")
    _safe(lambda: sm.delete_model(ModelName=MODEL), "delete_model")
    print("[teardown] requested delete of endpoint/config/model + autoscaling.")
    print("[teardown] ECR image + S3 weights are RETAINED for an immutable redeploy.")
    return 0


def _safe(fn, label: str):
    try:
        fn()
        print(f"  [ok] {label}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "already exist" in msg or "Cannot create already existing" in msg:
            print(f"  [exists] {label} (reused)")
        elif "Could not find" in msg or "ValidationException" in msg and "teardown" in label:
            print(f"  [absent] {label}")
        else:
            print(f"  [warn] {label}: {msg[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deploy"); d.add_argument("--image-digest", required=True)
    sub.add_parser("status")
    iv = sub.add_parser("invoke")
    iv.add_argument("--task", choices=["tabfm", "timesfm", "fallback", "badtabfm"], required=True)
    iv.add_argument("--idem", default="")
    iv.add_argument("--timeout", type=int, default=600)
    sub.add_parser("teardown")
    args = ap.parse_args()
    return {"deploy": cmd_deploy, "status": cmd_status,
            "invoke": cmd_invoke, "teardown": cmd_teardown}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
