"""E.6 - compare the enabled TabFM model against baselines on the SAME held-out,
labelled split. Records quality (accuracy / ordinal MAE), latency (from the real
result envelopes) and indicative cost (T4 on-demand rate x measured time).

TabFM + the CPU fallback both run on the deployed SageMaker T4 async endpoint on
the identical context/query; the majority baseline is computed locally. The test
labels are known to the scorer but NEVER sent to the models (only unlabelled query
rows are sent), so this is a genuine held-out evaluation.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

import boto3
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "infra", "aws", "gpu-worker"))
import sagemaker_ops as ops  # config + async invoke plumbing

REGION, PROFILE, BUCKET, KMS = ops.REGION, ops.PROFILE, ops.BUCKET, ops.KMS_ARN
ENDPOINT = ops.ENDPOINT
_sess = boto3.Session(profile_name=PROFILE, region_name=REGION)
_s3 = _sess.client("s3")
_smr = _sess.client("sagemaker-runtime")

# T4 g4dn.2xlarge on-demand, ap-south-1 (indicative, USD/hour).
_T4_RATE_PER_HR = 1.006


def _dataset(seed: int = 99):
    rng = np.random.default_rng(seed)
    cols = ["fir_count_7d", "fir_count_28d", "pending_ratio", "night_share",
            "avg_response_min", "officers_on_duty"]
    n = 6

    def label(x):
        s = x[:, 0] * 0.9 + x[:, 2] * 0.8 - x[:, 5] * 0.6
        return np.clip(np.digitize(s, [-0.7, 0.1, 0.9]), 0, 3).astype(int)

    ctx_x = rng.normal(0, 1, size=(240, n))
    ctx_y = label(ctx_x)
    test_x = rng.normal(0, 1, size=(60, n))
    test_y = label(test_x)
    return cols, ctx_x, ctx_y, test_x, test_y


def _invoke(backend: str, cols, ctx_x, ctx_y, test_x) -> dict:
    env = {
        "envelope_version": "1.0.0", "request_id": f"cmp-{uuid.uuid4().hex[:10]}",
        "idempotency_key": f"station_workload_band:CMP:{backend}:{uuid.uuid4().hex[:8]}",
        "task": "station_workload_band", "requested_backend": backend,
        "feature_schema_version": "fs-cmp-1", "model_version": "cmp",
        "feature_schema_digest": "cmp", "subject_kind": "station", "subject_ids": ["CMP"],
        "observation_cutoff": "2026-07-23T00:00:00+05:30", "source_version_hash": "cmp",
        "columns": [{"name": c, "dtype": "float", "role": "feature"} for c in cols],
        "context_x": [[round(float(v), 4) for v in r] for r in ctx_x],
        "context_y": [int(y) for y in ctx_y],
        "query_rows": [[round(float(v), 4) for v in r] for r in test_x],
        "output_schema": {"n_bands": 4}, "timeout_s": 600, "max_rows": 5000,
    }
    key = f"async-io/in/{env['request_id']}.json"
    _s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(env).encode(),
                   ServerSideEncryption="aws:kms", SSEKMSKeyId=KMS)
    t0 = time.time()
    resp = _smr.invoke_endpoint_async(EndpointName=ENDPOINT, ContentType="application/json",
                                      InputLocation=f"s3://{BUCKET}/{key}",
                                      InvocationTimeoutSeconds=600)
    out = resp["OutputLocation"][len(f"s3://{BUCKET}/"):]
    for _ in range(100):
        try:
            body = _s3.get_object(Bucket=BUCKET, Key=out)["Body"].read()
            r = json.loads(body)
            r["_roundtrip_s"] = round(time.time() - t0, 2)
            return r
        except Exception:  # noqa: BLE001
            time.sleep(6)
    return {"state": "timed_out"}


def _acc_mae(preds, true_y):
    ordinals = np.array([p["band_ordinal"] for p in preds])
    acc = float((ordinals == true_y).mean())
    mae = float(np.abs(ordinals - true_y).mean())
    return round(acc, 4), round(mae, 4)


def main() -> int:
    cols, ctx_x, ctx_y, test_x, test_y = _dataset()
    report = {"n_context": len(ctx_x), "n_test": len(test_x), "n_bands": 4,
              "instance": "ml.g4dn.2xlarge (Tesla T4)", "t4_rate_usd_per_hr": _T4_RATE_PER_HR,
              "models": {}}

    for backend in ("tabfm", "incontext"):
        res = _invoke(backend, cols, ctx_x, ctx_y, test_x)
        if res.get("state") != "completed":
            report["models"][backend] = {"state": res.get("state"),
                                         "error": res.get("error_detail")}
            continue
        acc, mae = _acc_mae(res["predictions"], test_y)
        runtime_ms = res.get("runtime_ms") or 0
        report["models"][backend] = {
            "actual_backend": res.get("actual_backend"), "actual_device": res.get("actual_device"),
            "gpu_name": res.get("gpu_name"), "accuracy": acc, "ordinal_mae": mae,
            "runtime_ms": runtime_ms, "cold_start_ms": res.get("cold_start_ms"),
            "roundtrip_s": res.get("_roundtrip_s"),
            "indicative_cost_usd_per_inference": round(_T4_RATE_PER_HR * (runtime_ms / 3_600_000.0), 8),
        }

    # local majority-class baseline (no model)
    maj = int(np.bincount(ctx_y, minlength=4).argmax())
    maj_pred = np.full(len(test_y), maj)
    report["models"]["majority_baseline"] = {
        "actual_device": "cpu(local)", "accuracy": round(float((maj_pred == test_y).mean()), 4),
        "ordinal_mae": round(float(np.abs(maj_pred - test_y).mean()), 4), "runtime_ms": 0}

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
