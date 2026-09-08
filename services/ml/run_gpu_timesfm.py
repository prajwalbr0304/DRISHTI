"""Run the TimesFM forecast layer on the REAL SageMaker T4 endpoint and persist
GPU-backed rows into "CrimePrediction".

Uses forecast_trajectories_safe(), which is the connection-safe variant built for
the slow remote path: it reads inputs, releases the DB connection during remote
inference, then revalidates the analytics policy in a fresh write transaction.
run_forecast() instead calls forecast_trajectories(), which would hold a write
transaction open across every district's SageMaker round trip.

Run from services/ml with DRISHTI_TIMESFM_SAGEMAKER=true and the adapter env set.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    for key in ("DRISHTI_TIMESFM_SAGEMAKER", "DRISHTI_AWS_ADAPTER_URL", "DATABASE_URL"):
        if not os.getenv(key):
            print(f"[abort] {key} is not set")
            return 2
    if not os.getenv("DRISHTI_AWS_ADAPTER_SECRET"):
        print("[abort] DRISHTI_AWS_ADAPTER_SECRET is not set")
        return 2

    from app import db
    from app.forecast import timesfm

    print(f"[db] ping -> {db.ping()}")
    fc = timesfm.get_forecaster()
    print(f"[forecaster] {type(fc).__name__} name={fc.name} family={fc.family}")
    if type(fc).__name__ != "SageMakerTimesFMForecaster":
        print("[abort] resolver did not pick the SageMaker forecaster; refusing to "
              "write rows that would not be GPU-backed")
        return 3

    horizon = int(os.getenv("DRISHTI_FORECAST_HORIZON", "6"))
    t0 = time.time()
    out = timesfm.forecast_trajectories_safe(head_id=None, horizon=horizon)
    elapsed = time.time() - t0

    summary = {k: v for k, v in out.items() if k != "analytics_policy_attestation"}
    summary["elapsed_s"] = round(elapsed, 1)
    print(json.dumps(summary, indent=2, default=str))

    if out.get("actual_device") != "cuda":
        print(f"[FAIL] actual_device={out.get('actual_device')!r}, expected 'cuda'")
        return 4
    print(f"[OK] {out.get('written')} GPU-backed rows written "
          f"(device={out.get('actual_device')} gpu={out.get('gpu_name')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
