"""LIVE Catalyst-side -> protected AWS adapter -> SageMaker -> Catalyst path proof,
using the REAL AppSail app code (SignedHttpsAdapter + PredictionRuntime +
validate_result) - the exact server-side client AppSail uses. No browser AWS.

Flow: routing gate -> persist (in-memory Data Store stand-in for the driver) ->
SignedHttpsAdapter.dispatch (signed POST /predict -> API Gateway -> Lambda) ->
SageMaker async on the T4 -> poll (signed GET /predict/{id}) -> validate_result
(fail-closed: tabfm must come back as tabfm on cuda) -> persist PredictionResult.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import boto3
import numpy as np

_sess = boto3.Session(profile_name="drishti", region_name="ap-south-1")
_adapter_cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
                              "infra", "aws", "adapter", "adapter.deployed.json"), encoding="utf-8"))
os.environ["DRISHTI_AWS_ADAPTER_URL"] = _adapter_cfg["adapter_url"]
os.environ["DRISHTI_AWS_ADAPTER_SECRET"] = _sess.client("secretsmanager").get_secret_value(
    SecretId="drishti/aws-adapter-secret")["SecretString"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "ml"))
from app.datastore.repository import InMemoryDataStore          # noqa: E402
from app.predict.adapter import SignedHttpsAdapter               # noqa: E402
from app.predict.envelope import BackendKind, ColumnDef, ModelTask  # noqa: E402
from app.predict.routing import InputEvent, RoutingContext        # noqa: E402
from app.predict.runtime import (PredictionJobInput,              # noqa: E402
                                 PredictionRuntime)


def _tabfm_job(svh: str) -> PredictionJobInput:
    rng = np.random.default_rng(11)
    cols = [ColumnDef(name=n) for n in ("fir_count_7d", "fir_count_28d", "pending_ratio",
                                        "night_share", "avg_response_min", "officers_on_duty")]
    ctx_x = rng.normal(0, 1, size=(240, 6))
    score = ctx_x[:, 0] * 0.9 + ctx_x[:, 2] * 0.8 - ctx_x[:, 5] * 0.6
    ctx_y = np.clip(np.digitize(score, [-0.7, 0.1, 0.9]), 0, 3).astype(int).tolist()
    query = rng.normal(0, 1, size=(10, 6)).round(4).tolist()
    return PredictionJobInput(
        routing_ctx=RoutingContext(event=InputEvent.FIR_APPROVED, subject_kind="station",
                                   has_verified_geography=True, has_verified_time=True,
                                   has_verified_head=True),
        task=ModelTask.STATION_WORKLOAD_BAND, requested_backend=BackendKind.TABFM,
        subject_kind="station", subject_ids=["BLR-CEN"], columns=cols, query_rows=query,
        feature_schema_version="fs-workload-1", model_version="tabfm-1.0.0",
        feature_schema_digest="fsd-live", observation_cutoff="2026-07-23T00:00:00+05:30",
        source_version_hash=svh, values={},
        context_x=[[round(float(v), 4) for v in r] for r in ctx_x], context_y=ctx_y,
        output_schema={"n_bands": 4})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svh", default="live-1")
    ap.add_argument("--timeout", type=int, default=480)
    args = ap.parse_args()

    rt = PredictionRuntime(adapter=SignedHttpsAdapter(), repository=InMemoryDataStore())
    t0 = time.time()
    handle = rt.submit(_tabfm_job(args.svh))     # signed dispatch to the real API Gateway
    print(json.dumps({"stage": "dispatched", "adapter_request_id": handle.request_id,
                      "idempotency_key": handle.idempotency_key,
                      "dispatch_mode": handle.dispatch_mode,
                      "prediction_request_external_id": handle.prediction_request_external_id},
                     indent=2))
    deadline = time.time() + args.timeout
    result = None
    while time.time() < deadline:
        result = rt.collect(handle)
        if result.state in ("completed", "failed", "rejected"):
            break
        time.sleep(6)

    out = {
        "state": result.state, "persisted": result.persisted,
        "actual_backend": str(result.result.actual_backend) if result.result else None,
        "actual_device": str(result.result.actual_device) if result.result else None,
        "gpu_name": getattr(result.result, "gpu_name", None) if result.result else None,
        "model_artifact_digest": getattr(result.result, "model_artifact_digest", None) if result.result else None,
        "prediction_result_external_id": result.prediction_result_external_id,
        "rejected_reason": result.rejected_reason,
        "roundtrip_s": round(time.time() - t0, 2),
        "n_predictions": len(result.result.predictions) if result.result else 0,
    }
    print("=== LIVE INTEGRATION RESULT (real app client -> API GW -> Lambda -> SageMaker T4) ===")
    print(json.dumps(out, indent=2, default=str))
    return 0 if result.state == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
