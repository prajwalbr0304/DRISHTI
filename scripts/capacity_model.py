#!/usr/bin/env python3
"""DRISHTI transparent capacity model (Prompt 25 Part E.4).

Reads the BOUNDED measured load profile (artifacts/phase-25/load/load-results.json)
and projects, with EXPLICIT assumptions, what it would take to serve roughly
2,000 stations / 100,000 users / 1,000,000 cases. This is a transparent model
built from small live measurements on the pinned single-instance AppSail — it is
NOT a target-scale or HA certification (that is post-hackathon backlog, and is only
claimed when genuinely executed). Every assumption is printed so a reviewer can
change it and recompute.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# --- explicit, editable assumptions ----------------------------------------
ASSUMPTIONS = {
    "target_stations": 2000,
    "target_users": 100000,
    "target_cases": 1000000,
    "peak_concurrent_user_fraction": 0.03,   # 3% of users active at peak
    "requests_per_active_user_per_min": 6,   # 1 request / 10s while actively using
    "measured_instances": 1,                 # AppSail pinned min=max=1 (hackathon)
    "instance_scaling": "assumed-linear-until-DB-bound (optimistic; unproven)",
    "safety_headroom": 0.7,                  # size to 70% utilisation
}


def _blend(results):
    """Blended sustainable read throughput per instance from the error-free
    workloads (exclude non-2xx-only probes). Uses the slower, DB-backed reads
    as the conservative floor and reports both blended-mean and heavy-read floor."""
    ok = [r for r in results if r.get("error_rate") == 0 and r.get("throughput_rps")]
    if not ok:
        return None
    rps = sorted(r["throughput_rps"] for r in ok)
    mean = sum(rps) / len(rps)
    # conservative floor = mean of the slowest third (heavy RDS aggregations)
    floor = sum(rps[: max(1, len(rps) // 3)]) / max(1, len(rps) // 3)
    return {"blended_mean_rps_per_instance": round(mean, 1),
            "heavy_read_floor_rps_per_instance": round(floor, 1),
            "workloads_counted": len(ok),
            "measured_concurrency": ok[0].get("concurrency")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", default="artifacts/phase-25/load/load-results.json")
    ap.add_argument("--json", default="artifacts/phase-25/load/capacity-model.json")
    a = ap.parse_args()

    load = json.loads(Path(a.load).read_text(encoding="utf-8"))
    tp = _blend(load.get("results", []))
    A = ASSUMPTIONS

    peak_users = A["target_users"] * A["peak_concurrent_user_fraction"]
    peak_rps = peak_users * A["requests_per_active_user_per_min"] / 60.0

    model = {"required_peak_rps": round(peak_rps, 1)}
    if tp:
        for label, per in (("by_blended_mean", tp["blended_mean_rps_per_instance"]),
                           ("by_heavy_read_floor", tp["heavy_read_floor_rps_per_instance"])):
            eff = per * A["safety_headroom"]
            model[label] = {
                "sustainable_rps_per_instance_at_70pct": round(eff, 1),
                "appsail_instances_needed": round(peak_rps / eff, 1) if eff else None,
            }

    out = {
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "disclaimer": ("TRANSPARENT MODEL from a BOUNDED live measurement on a pinned "
                       "single-instance AppSail. NOT a target-scale or HA certification. "
                       "Instance scaling is assumed linear until the shared datastore/DB "
                       "becomes the bottleneck, which is unproven here. Full 1M-case / "
                       "100k-user HA certification is in POST_HACKATHON_BACKLOG."),
        "assumptions": A,
        "measured_throughput": tp,
        "projection": model,
        "gating_constraints_to_close_before_certification": [
            "AppSail is pinned min=max=1 (in-process ID allocation + nonce replay); "
            "horizontal scale needs shared monotonic ID allocation (Data Store sequence / "
            "Cache incr) — tracked in appsail.deploy.json instance_correctness + backlog.",
            "Heavy RDS aggregations (performance_overview ~1.6s, cases list ~1.2s) need "
            "materialized views (app/matviews.py) + read replicas + query indexing at 1M cases.",
            "Server-side pagination/aggregation is present; browser-side virtualization + "
            "bounded graph fan-out must be re-verified at target row counts.",
            "Catalyst Data Store ZCQL page cap (<=300) requires cursor pagination for large scans.",
            "No load test above the bounded budget was run; do not extrapolate to certification.",
        ],
    }
    p = Path(a.json)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"required_peak_rps": model["required_peak_rps"],
                      "measured": tp, "projection": {k: v for k, v in model.items()
                      if k != "required_peak_rps"}}, indent=2))
    print(f"[capacity] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
