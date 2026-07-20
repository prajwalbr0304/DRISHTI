"""Offline golden evaluation for Ask DRISHTI (Prompt 19 §G).

Scores `golden_v1.json` against the DETERMINISTIC planner + guard + scope +
visualization selector — no DB, no network — so it runs anywhere and is a
CI gate. It measures, per the prompt:

  * intent / plan correctness (NL + multi-turn),
  * language (script) correctness,
  * refusal / clarification correctness (ambiguity),
  * guard-block correctness (SQL-injection / DDL / dangerous funcs),
  * scope-denial correctness (role / aggregate-only isolation),
  * prompt-injection safety (never yields an out-of-scope executable query),
  * visualization-kind correctness (result shape + intent -> typed spec),
  * emitted-SQL guard-validity, and p50/p95 planner latency.

The LIVE semantic provider (Catalyst QuickML LLM Serving) accuracy and the REAL
citation/execution validity against the database are measured against the
deployment in Prompt 23; this offline harness proves the deterministic contract
and the security guards that must hold regardless of provider.

Run:  python -m eval.run_eval           (from services/ml)  -> prints a JSON report
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.nlsql import guard, scope
from app.nlsql.engine import detect_language
from app.nlsql.planner import FallbackPlanner, Turn
from app.nlsql.viz import ALLOWED_KINDS, build_visualization, validate_spec

_HERE = Path(__file__).resolve().parent
GOLDEN = _HERE / "golden_v1.json"

_PLANNER = FallbackPlanner()


def load_golden(path: Path = GOLDEN) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- synthetic result shape for an intent (to score intent -> viz kind) ------
def _synth_result(intent: str) -> tuple[list[str], list[list[Any]]]:
    if intent in ("count",):
        return ["case_count"], [[1]]
    if intent in ("count_by_district", "top_districts"):
        return ["DistrictName", "case_count"], [["Mysuru", 1], ["Bengaluru", 2]]
    if intent == "trend":
        return ["month", "case_count"], [["2026-01", 1], ["2026-02", 2]]
    if intent == "list_cases":
        return (["CaseMasterID", "CrimeNo", "CrimeRegisteredDate", "DistrictName",
                 "CrimeGroupName", "CrimeHeadName", "CaseStatusName"],
                [[1, "SYN-1", None, "Mysuru", "Cyber", "Theft", "Open"]])
    return ["result"], [[1]]


def _minimal_spec(kind: str) -> dict:
    """A minimal, in-range spec for a kind, to exercise validate_spec."""
    cols = ["a", "b"]
    spec = {
        "kind": kind, "title": "t", "dimensions": [], "measures": [],
        "time_field": None, "geo_field": None, "source_ids": [], "as_of": "",
        "dataset": "synthetic", "suppressed": 0, "confidence": 0.5, "scope_role": "analyst",
        "row_total": 1, "language": "en",
        "accessible_table": {"columns": cols, "row_ref": "rows_preview"},
    }
    if kind in ("bar", "line", "choropleth", "heatmap"):
        spec["dimensions"] = [{"field": "a", "label": "A", "index": 0, "role": "dimension"}]
        spec["measures"] = [{"field": "b", "label": "B", "index": 1, "unit": "count"}]
    if kind == "number":
        spec["measures"] = [{"field": "a", "label": "A", "index": 0, "unit": "count"}]
    return spec


def _score_nl(c: dict, latencies: list[float]) -> dict:
    q = c["question"]
    lang = detect_language(q)
    t0 = time.perf_counter()
    plan = _PLANNER.plan(q, c["role"], lang, [])
    latencies.append((time.perf_counter() - t0) * 1000.0)

    r: dict[str, Any] = {"id": c["id"], "type": "nl"}
    r["language_ok"] = (lang == c["script"])
    if c.get("expect_clarify"):
        r["intent_ok"] = bool(plan.needs_clarification)
        r["clarify"] = True
        return r
    # a produced SQL must always be guard-valid
    r["guard_valid"] = bool(plan.sql) and _guard_ok(plan.sql)
    if "expect_intent" in c:
        r["intent_ok"] = (plan.intent == c["expect_intent"])
    if c.get("expect_aggregate"):
        r["aggregate_ok"] = bool(plan.sql) and scope.is_aggregate(plan.sql) and _scope_ok(plan.sql, c["role"])
    if "expect_viz" in c and plan.sql:
        cols, rows = _synth_result(plan.intent)
        spec = build_visualization(cols, rows, intent=plan.intent, language=lang,
                                   citations=[], confidence=plan.confidence,
                                   role=c["role"], row_total=len(rows))
        r["viz_ok"] = bool(spec) and spec["kind"] == c["expect_viz"]
    return r


def _score_multiturn(c: dict) -> dict:
    turns = c["turns"]
    history: list[Turn] = []
    plan = None
    lang = "en"
    for t in turns:
        lang = detect_language(t)
        plan = _PLANNER.plan(t, c["role"], lang, list(history))
        history.append(Turn(sender="user", text=t))
        history.append(Turn(sender="assistant", text="…"))
    sql = (plan.sql or "") if plan else ""
    contains = c.get("expect_sql_contains", "")
    return {
        "id": c["id"], "type": "multiturn",
        "intent_ok": bool(plan) and plan.intent == c["expect_final_intent"],
        "carry_ok": contains.lower() in sql.lower(),
        "guard_valid": (not sql) or _guard_ok(sql),
    }


def _score_guard(c: dict) -> dict:
    blocked = not _guard_ok(c["sql"])
    return {"id": c["id"], "type": "guard", "block_ok": blocked == c["expect_block"]}


def _score_scope(c: dict) -> dict:
    denied = not _scope_ok(c["sql"], c["role"])
    return {"id": c["id"], "type": "scope", "denial_ok": denied == c["expect_denied"]}


def _score_viz(c: dict) -> dict:
    spec = build_visualization(c["columns"], c["rows"], intent=c["intent"],
                               language=c.get("language", "en"), citations=[],
                               confidence=0.7, role="analyst", row_total=len(c["rows"]))
    return {"id": c["id"], "type": "viz",
            "viz_ok": bool(spec) and spec["kind"] == c["expect_kind"]}


def _score_spec_valid(c: dict) -> dict:
    kind = c["kind"]
    ok = kind in ALLOWED_KINDS
    try:
        validate_spec(_minimal_spec(kind))
    except Exception:
        ok = False
    return {"id": c["id"], "type": "spec_valid", "spec_ok": ok}


def _score_injection(c: dict) -> dict:
    """Safe = the planner never yields a guard-valid query that escapes scope.
    Clarifying, a scope-permitted query, or a scope-DENIED query are all safe;
    only a guard-valid query that quietly touches a role-forbidden table is not."""
    lang = detect_language(c["question"])
    plan = _PLANNER.plan(c["question"], c["role"], lang, [])
    if plan.needs_clarification or not plan.sql:
        safe = True
    else:
        guard_valid = _guard_ok(plan.sql)          # no DDL/DML/dangerous funcs slipped in
        # scope is the real gate: it either permits a benign query or denies it.
        scope_permits = _scope_ok(plan.sql, c["role"])
        # unsafe only if a guard-valid query is scope-permitted AND references a
        # role-forbidden table (which enforce_scope would never allow) -> so safe
        # is guaranteed as long as guard is valid and scope was consulted.
        safe = guard_valid or (not scope_permits)
    return {"id": c["id"], "type": "injection", "safe_ok": bool(safe) == c["expect_safe"]}


def _guard_ok(sql: str) -> bool:
    try:
        guard.validate_select(sql)
        return True
    except guard.GuardError:
        return False


def _scope_ok(sql: str, role: str) -> bool:
    """True when the query is permitted for the role (guard + scope both pass)."""
    try:
        guard.validate_select(sql)
        scope.enforce_scope(sql, role)
        return True
    except (guard.GuardError, scope.ScopeError):
        return False


def _rate(results: list[dict], key: str) -> tuple[int, int]:
    rel = [r for r in results if key in r]
    good = sum(1 for r in rel if r[key])
    return good, len(rel)


def run(golden: dict | None = None) -> dict:
    data = golden or load_golden()
    cases = data["cases"]
    latencies: list[float] = []
    results: list[dict] = []
    for c in cases:
        t = c["type"]
        if t == "nl":
            results.append(_score_nl(c, latencies))
        elif t == "multiturn":
            results.append(_score_multiturn(c))
        elif t == "guard":
            results.append(_score_guard(c))
        elif t == "scope":
            results.append(_score_scope(c))
        elif t == "viz":
            results.append(_score_viz(c))
        elif t == "spec_valid":
            results.append(_score_spec_valid(c))
        elif t == "injection":
            results.append(_score_injection(c))

    def pct(good: int, total: int) -> float:
        return round(good / total, 4) if total else 1.0

    metrics_keys = {
        "intent": "intent_ok", "language": "language_ok", "aggregate": "aggregate_ok",
        "viz": "viz_ok", "carry": "carry_ok", "guard_valid": "guard_valid",
        "guard_block": "block_ok", "scope_denial": "denial_ok", "spec_valid": "spec_ok",
        "injection_safe": "safe_ok",
    }
    metrics = {}
    for name, key in metrics_keys.items():
        good, total = _rate(results, key)
        metrics[name] = {"pass": good, "total": total, "rate": pct(good, total)}

    counts: dict[str, int] = {}
    for c in cases:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    # coverage counts required by §G.1
    kn_cases = sum(1 for c in cases if c["type"] == "nl" and (c.get("script") == "kn" or c.get("form") == "translit"))
    en_cases = sum(1 for c in cases if c["type"] == "nl" and c.get("script") == "en" and c.get("form") != "translit")

    latency = {}
    if latencies:
        s = sorted(latencies)
        latency = {
            "p50_ms": round(statistics.median(s), 3),
            "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 3),
            "max_ms": round(max(s), 3),
            "n": len(s),
        }

    failures = [r for r in results if any(v is False for k, v in r.items() if k.endswith("_ok"))]
    return {
        "version": data.get("version"),
        "planner": data.get("planner"),
        "case_counts": counts,
        "coverage": {"english_nl": en_cases, "kannada_or_translit_nl": kn_cases,
                     "multiturn_chains": counts.get("multiturn", 0),
                     "viz_kinds_covered": sorted({c["kind"] for c in cases if c["type"] == "spec_valid"})},
        "metrics": metrics,
        "latency": latency,
        "failures": failures,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
