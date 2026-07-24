#!/usr/bin/env python3
"""DRISHTI bounded load / performance harness (Prompt 25 Part E).

Drives representative synthetic read/write workloads against the ACTUAL public
Catalyst API-Gateway path (browser -> API Gateway -> gateway_api -> AppSail),
using concurrent synthetic users, and records concurrency, throughput, latency
percentiles (p50/p95/p99), error rate and per-status distribution per workload.

It is deliberately BOUNDED (small request budget + modest concurrency) to respect
the single-instance AppSail, the API-Gateway throttle (600/min general, 120/min
per-IP) and the hackathon credit budget. It NEVER sends secrets and reads only
synthetic data. Results feed the transparent capacity model in the Phase 25
report — extrapolation is NOT certification.

Stdlib only (urllib + ThreadPoolExecutor) so it runs on any runner.

Usage:
  python scripts/load_test.py --gateway https://<serverless-domain> \
      --concurrency 8 --per-workload 40 --json artifacts/phase-25/load/load-results.json
"""
from __future__ import annotations

import argparse
import json
import ssl
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

_CTX = ssl.create_default_context()

# Representative read workloads (probed first; only those returning a modelled
# status are load-tested). Each entry: (name, method, path, body-or-None, category).
CANDIDATES = [
    ("cases_list_map", "GET", "/api/cases?limit=25", None, "map/list"),
    ("cases_filters", "GET", "/api/cases/filters", None, "map/list"),
    ("dashboard_analytics", "GET", "/api/analytics/patterns", None, "dashboard"),
    ("prediction_status", "GET", "/api/predict/enablement", None, "prediction-status"),
    ("performance_overview", "GET", "/api/performance/overview?window_days=30", None, "dashboard"),
    ("geo_hotspots_map", "GET", "/api/geo/hotspots", None, "map"),
    ("geo_stations_map", "GET", "/api/geo/stations", None, "map"),
    ("graph_search_around", "GET", "/api/graph/neighbourhood", None, "graph"),
    ("graph_communities", "GET", "/api/graph/communities/list", None, "graph"),
    ("disaster_overview", "GET", "/api/disaster/overview", None, "dashboard"),
    ("board_list", "GET", "/api/boards", None, "board"),
    ("workload_predictions", "GET", "/api/workload/predictions", None, "prediction-status"),
    ("forecast_map", "GET", "/api/forecast/map", None, "prediction-status"),
]


def _one(url: str, method: str, body, timeout: float):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
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


def _pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return round(xs[k], 1)


def probe(gateway, timeout):
    live = []
    for name, method, path, body, cat in CANDIDATES:
        _, code = _one(gateway.rstrip("/") + path, method, body, timeout)
        ok = isinstance(code, int) and code < 500
        print(f"  probe {name:22} {method} {path} -> {code} {'[keep]' if ok else '[skip 5xx/err]'}")
        if ok:
            live.append((name, method, path, body, cat))
    return live


def run_workload(gateway, name, method, path, body, concurrency, total, timeout):
    url = gateway.rstrip("/") + path
    lat, statuses = [], {}
    t0 = time.perf_counter()

    def task(_):
        return _one(url, method, body, timeout)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for fut in as_completed(ex.submit(task, i) for i in range(total)):
            ms, code = fut.result()
            lat.append(ms)
            statuses[str(code)] = statuses.get(str(code), 0) + 1
    wall = time.perf_counter() - t0
    ok = sum(v for k, v in statuses.items() if k.isdigit() and int(k) < 400)
    return {
        "workload": name, "method": method, "path": path,
        "concurrency": concurrency, "requests": total,
        "wall_s": round(wall, 2),
        "throughput_rps": round(total / wall, 1) if wall > 0 else None,
        "ok": ok, "error_rate": round(1 - ok / total, 4) if total else None,
        "status_dist": statuses,
        "latency_ms": {"p50": _pct(lat, 50), "p95": _pct(lat, 95),
                       "p99": _pct(lat, 99), "max": round(max(lat), 1) if lat else None,
                       "mean": round(statistics.fmean(lat), 1) if lat else None},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", required=True, help="public API-Gateway origin")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--per-workload", type=int, default=40)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--json", default="artifacts/phase-25/load/load-results.json")
    a = ap.parse_args()

    print(f"[load] probing endpoints on {a.gateway} ...")
    live = probe(a.gateway, a.timeout)
    print(f"[load] {len(live)} workload(s) modelled; running bounded load "
          f"(c={a.concurrency}, n={a.per_workload}/workload) ...")
    results = []
    for name, method, path, body, _cat in live:
        r = run_workload(a.gateway, name, method, path, body,
                         a.concurrency, a.per_workload, a.timeout)
        results.append(r)
        lm = r["latency_ms"]
        print(f"  {name:22} rps={r['throughput_rps']:>6} p50={lm['p50']:>6} "
              f"p95={lm['p95']:>7} p99={lm['p99']:>7} err={r['error_rate']} {r['status_dist']}")

    all_lat_ok = all(r["error_rate"] == 0 for r in results) if results else False
    out = {
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "gateway": a.gateway,
        "bounded": True,
        "note": ("Bounded live load through the actual Catalyst API Gateway -> single-instance "
                 "AppSail. Synthetic super_admin path (DRISHTI_DEMO_AUTH). Not target-scale "
                 "certification; feeds the transparent capacity model only."),
        "concurrency": a.concurrency, "per_workload": a.per_workload,
        "workloads_modelled": len(results),
        "results": results,
        "all_workloads_error_free": all_lat_ok,
    }
    p = Path(a.json)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"[load] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
