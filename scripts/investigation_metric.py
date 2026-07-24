#!/usr/bin/env python3
"""DRISHTI investigation-time demo metric (Prompt 25 Part F).

Defines a small set of GOLDEN tasks that each represent a manual
search / dashboard-comparison / reporting workflow, then measures DRISHTI's
time-to-grounded-answer by timing the ACTUAL live API round-trips that assemble
each grounded, cited answer through the public Catalyst gateway.

Honesty rule (Part F.3): we report METHODOLOGY and OBSERVED DRISHTI time only.
We do NOT fabricate a percentage reduction versus manual work — there is no
measured manual baseline / user study here, so the manual comparison is described
qualitatively only. Data is synthetic; the demo super_admin path is used.
"""
from __future__ import annotations

import argparse
import json
import ssl
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_CTX = ssl.create_default_context()

# Each golden task: (id, description, manual_equivalent, [ (method, path) ... ]).
GOLDEN_TASKS = [
    ("district_pattern_briefing",
     "Assemble a district crime-pattern briefing (trend + hotspots).",
     "Manually: query the register, tally by month/type, build a chart in a spreadsheet.",
     [("GET", "/api/analytics/patterns"), ("GET", "/api/geo/hotspots")]),
    ("recent_case_triage",
     "Find and scope recent cases with available filters.",
     "Manually: page through the FIR/case register and note candidates by hand.",
     [("GET", "/api/cases/filters"), ("GET", "/api/cases?limit=25")]),
    ("predictive_outlook",
     "Compile the predictive workload/forecast outlook (grounded, with intervals).",
     "Manually: pull counts, eyeball trends, and guess next-period load.",
     [("GET", "/api/predict/enablement"), ("GET", "/api/workload/predictions"),
      ("GET", "/api/forecast/map")]),
    ("disaster_situation",
     "Open the disaster situational overview (active hazards + zones).",
     "Manually: phone stations / consult separate spreadsheets and maps.",
     [("GET", "/api/disaster/overview")]),
]


def _timed(url, method, timeout):
    req = urllib.request.Request(url, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            r.read()
            return (time.perf_counter() - t0) * 1000.0, r.getcode()
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:  # noqa: BLE001
            pass
        return (time.perf_counter() - t0) * 1000.0, e.code
    except Exception as e:  # noqa: BLE001
        return (time.perf_counter() - t0) * 1000.0, f"ERR:{type(e).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--json", default="artifacts/phase-25/investigation-time-metric.json")
    a = ap.parse_args()

    tasks_out = []
    for tid, desc, manual, calls in GOLDEN_TASKS:
        totals, all_ok = [], True
        for _ in range(a.repeats):
            total, ok = 0.0, True
            for method, path in calls:
                ms, code = _timed(a.gateway.rstrip("/") + path, method, a.timeout)
                total += ms
                ok = ok and isinstance(code, int) and code < 400
            totals.append(total)
            all_ok = all_ok and ok
        tasks_out.append({
            "task": tid, "description": desc, "manual_equivalent": manual,
            "api_calls": [f"{m} {p}" for m, p in calls], "repeats": a.repeats,
            "grounded_answer_ok": all_ok,
            "drishti_time_to_grounded_answer_ms": {
                "median": round(statistics.median(totals), 1),
                "p95": round(sorted(totals)[max(0, int(0.95 * (len(totals) - 1)))], 1),
                "min": round(min(totals), 1), "max": round(max(totals), 1),
            },
        })
        t = tasks_out[-1]["drishti_time_to_grounded_answer_ms"]
        print(f"  {tid:26} median={t['median']:>7}ms p95={t['p95']:>7}ms ok={all_ok}")

    out = {
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "gateway": a.gateway,
        "methodology": (
            "Time-to-grounded-answer is the summed live API round-trip time to assemble "
            "each golden task's grounded, cited answer through the public Catalyst gateway "
            "(browser->API Gateway->AppSail->data). It measures server assembly latency, "
            "NOT full human reading/interpretation time. Synthetic data; demo super_admin path."),
        "honesty_note": (
            "OBSERVED DRISHTI time only. No manual baseline / user study was measured, so NO "
            "percentage-reduction claim is made. The manual_equivalent field describes the "
            "comparable manual workflow qualitatively for context, not as a measured baseline."),
        "golden_tasks": tasks_out,
        "all_tasks_grounded": all(t["grounded_answer_ok"] for t in tasks_out),
    }
    p = Path(a.json)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"[investigation-metric] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
