"""DRISHTI GPU worker self-test: run REAL tabfm + timesfm inference and print a
JSON report (device, weight digests, cold/inference latency, sample predictions).

Used to validate the built image before deploy:
  * on a CPU-only host:  python selftest.py --device cpu   (proves the model code +
    real weights load and run; TabFM predict is slow on CPU by design);
  * on the CUDA instance: python selftest.py --device cuda  (the real CUDA proof,
    via the same fail-closed run_tabfm / run_timesfm the handler uses).
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

import backends


def _tabfm(device: str) -> dict:
    rng = np.random.default_rng(7)
    cols = [{"name": f"f{i}", "dtype": "float", "role": "feature"} for i in range(4)]
    xc = rng.normal(size=(80, 4))
    yc = np.clip(((xc[:, 0] + xc[:, 1]) > 0).astype(int) + (xc[:, 2] > 0.5).astype(int), 0, 3)
    query = rng.normal(size=(5, 4))
    if device == "cuda":
        res = backends.run_tabfm(cols, xc.tolist(), yc.tolist(), query.tolist(),
                                 n_bands=4, weight_digest="")
        data = dict(res.__dict__)
        data["predictions"] = data["predictions"][:3]
        return data
    preds, digest, license_id, timings = backends._tabfm_infer_core(
        "cpu", xc.tolist(), yc.tolist(), query.tolist(), n_bands=4, weight_digest="", chunk=512)
    return {"actual_backend": "tabfm", "actual_device": "cpu", "model_artifact_digest": digest,
            "license": license_id, "timings": timings, "predictions": preds[:3]}


def _timesfm(device: str) -> dict:
    x = np.arange(240)
    series = np.sin(x / 6.0) * 5 + 20 + np.random.default_rng(1).normal(0, 0.5, 240)
    rows = [[float(v)] for v in series]
    if device == "cuda":
        res = backends.run_timesfm(rows, horizon=14, freq="D", weight_digest="")
        data = dict(res.__dict__)
        data["predictions"] = data["predictions"][:3]
        return data
    preds, digest, dev, timings = backends._timesfm_infer_core("cpu", rows, horizon=14)
    return {"actual_backend": "timesfm", "actual_device": dev, "model_artifact_digest": digest,
            "timings": timings, "predictions": preds[:3]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto")
    parser.add_argument("--model", choices=["tabfm", "timesfm", "both"], default="both")
    args = parser.parse_args()

    env = backends.report_environment()
    device = args.device
    if device == "auto":
        device = "cuda" if env.get("cuda") else "cpu"

    out = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "environment": env, "device": device, "results": {}}
    if args.model in ("tabfm", "both"):
        try:
            out["results"]["tabfm"] = _tabfm(device)
        except Exception as exc:  # noqa: BLE001
            out["results"]["tabfm"] = {"error": f"{type(exc).__name__}: {exc}"}
    if args.model in ("timesfm", "both"):
        try:
            out["results"]["timesfm"] = _timesfm(device)
        except Exception as exc:  # noqa: BLE001
            out["results"]["timesfm"] = {"error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
