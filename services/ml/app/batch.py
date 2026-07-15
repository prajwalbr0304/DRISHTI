"""Batch / scheduled job entry points for the ML service.

Run as a module, e.g.:
    python -m app.batch health
    python -m app.batch refresh-matviews
    python -m app.batch register-model --name drishti-risk --type classification --version 1.0.0
    python -m app.batch demo-score --district 1 --score 0.8

These are the CLI hooks a scheduler (cron / Airflow-style) invokes for nightly
re-scoring and matview refresh (doc 02 §9). Model scoring itself lands in
Phases 6-13; this provides the runnable skeleton + the refresh step.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import db, matviews, models
from .config import get_settings


def _cmd_health(_args) -> int:
    try:
        ok = db.ping()
        exts = db.installed_extensions()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "degraded", "error": str(exc).strip()}))
        return 1
    required = {e: (e in exts) for e in ("postgis", "vector", "pg_trgm")}
    status = "ok" if ok and all(required.values()) else "degraded"
    print(json.dumps({"status": status, "database": ok,
                      "extensions": {**required, "pgrouting": "pgrouting" in exts}}))
    return 0 if status == "ok" else 1


def _cmd_refresh_matviews(args) -> int:
    names = args.views or list(matviews.ALL_MATVIEWS)
    with db.rw_conn() as conn:
        result = matviews.refresh_all(conn, names)
    print(json.dumps({"refreshed": result}))
    return 0


def _cmd_register_model(args) -> int:
    with db.rw_conn() as conn:
        mv_id = models.get_or_create_model_version(
            conn, model_name=args.name, model_type=args.type, version=args.version,
            framework=args.framework,
        )
        label = models.model_version_label(conn, mv_id)
    print(json.dumps({"model_version_id": mv_id, "model_version": label}))
    return 0


def _cmd_enrich_graph(args) -> int:
    from .graph import enrich
    print(json.dumps(enrich.run(seed=args.seed), default=str))
    return 0


def _cmd_communities(args) -> int:
    from .graph import algorithms
    with db.rw_conn() as conn:
        result = algorithms.detect_communities(conn)
    print(json.dumps(result, default=str))
    return 0


def _cmd_centrality(args) -> int:
    from .graph import algorithms
    with db.rw_conn() as conn:
        result = algorithms.compute_centrality(conn, betweenness_k=args.betweenness_k)
    print(json.dumps(result, default=str))
    return 0


def _cmd_hidden_associations(args) -> int:
    from .graph import hidden
    with db.rw_conn() as conn:
        result = hidden.materialize(conn, min_links=args.min_links)
    print(json.dumps(result, default=str))
    return 0


def _cmd_hotspots(args) -> int:
    from .geo import hotspots
    with db.rw_conn() as conn:
        result = hotspots.run_hotspots(conn, eps_m=args.eps_m, eps_days=args.eps_days,
                                       min_samples=args.min_samples)
    print(json.dumps(result, default=str))
    return 0


def _cmd_emerging_alerts(args) -> int:
    from .geo import alerts
    with db.rw_conn() as conn:
        result = alerts.detect_and_write(conn, window=args.window,
                                         threshold_sigma=args.threshold_sigma)
    print(json.dumps(result, default=str))
    return 0


def _cmd_risk_score(args) -> int:
    from .risk import scoring
    with db.rw_conn() as conn:
        result = scoring.score_all(conn, context_size=args.context_size,
                                   limit=args.limit, foundation_estimators=args.estimators)
    print(json.dumps(result, default=str))
    return 0


def _cmd_risk_calibration(args) -> int:
    from .risk import scoring
    with db.rw_conn() as conn:
        result = scoring.calibration_report(conn)
    print(json.dumps(result, default=str))
    return 0


def _cmd_embed_cases(args) -> int:
    from .cases import corpus
    with db.rw_conn() as conn:
        result = corpus.embed_corpus(conn, limit=args.limit, batch_size=args.batch_size,
                                     embedder_name=args.embedder)
    print(json.dumps(result, default=str))
    return 0


def _cmd_case_summary(args) -> int:
    from .cases import service
    resp = service.case_summary(args.case)
    if resp is None:
        print(json.dumps({"error": f"case {args.case} not found"}))
        return 1
    print(json.dumps({"summary_id": resp.summary_id, "fully_cited": resp.fully_cited,
                      "claims": resp.claim_count, "confidence": resp.confidence,
                      "model_version": resp.result.model_version}, default=str))
    return 0


def _cmd_case_leads(args) -> int:
    from .cases import service
    resp = service.case_leads(args.case)
    if resp is None:
        print(json.dumps({"error": f"case {args.case} not found"}))
        return 1
    print(json.dumps({"case": resp.case_id, "io_employee_id": resp.io_employee_id,
                      "leads": [{"rank": l.rank, "kind": l.kind, "score": l.score,
                                 "recommendation_id": l.recommendation_id} for l in resp.leads]},
                     default=str))
    return 0


def _cmd_money_detect(args) -> int:
    from .money import detection
    with db.rw_conn() as conn:
        result = detection.run_detection(
            conn, structuring_min_count=args.structuring_min_count,
            structuring_window_days=args.structuring_window_days,
            cycle_min_amount=args.cycle_min_amount, cycle_max_len=args.cycle_max_len)
    print(json.dumps(result, default=str))
    return 0


def _cmd_forecast_run(args) -> int:
    from .forecast import service
    resp = service.run_forecast(head_id=args.head_id, horizon_days=args.horizon_days)
    print(json.dumps({"head_id": resp.head_id, "horizon_days": resp.horizon_days,
                      "prediction_start": resp.prediction_start,
                      "layers": [{"layer": l.layer, "model": l.model, "written": l.written}
                                 for l in resp.layers],
                      "alerts_written": resp.alerts_written,
                      "high_severe": sum(1 for d in resp.fused if d.risk_class in ("High", "Severe")),
                      "answer": resp.result.answer}, default=str))
    return 0


def _cmd_forecast_validate(args) -> int:
    import datetime as dt
    from .forecast import service
    cut = dt.date.fromisoformat(args.cutoff) if args.cutoff else None
    resp = service.validation(cutoff=cut, horizon_months=args.horizon_months,
                              area_fraction=args.area_fraction)
    print(json.dumps({"cutoff": resp.cutoff, "overall": resp.overall,
                      "per_crime_head": resp.per_crime_head}, default=str))
    return 0


def _cmd_geo_validate(args) -> int:
    import datetime as dt
    from .geo import validation
    with db.ro_conn() as conn:
        patterns = validation.known_patterns(conn)
    with db.rw_conn() as conn:  # PAI runs clustering; rw conn (no writes though)
        pai = validation.pai_report(conn, cutoff=dt.date.fromisoformat(args.cutoff))
    print(json.dumps({"known_patterns": patterns, "pai": pai}, default=str))
    return 0


def _cmd_apply_sql(args) -> int:
    import pathlib
    sql = pathlib.Path(args.file).read_text(encoding="utf-8")
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(json.dumps({"applied": args.file}))
    return 0


def _cmd_demo_score(args) -> int:
    with db.rw_conn() as conn:
        mv_id = models.get_or_create_model_version(
            conn, "drishti-risk-demo", "classification", "0.1.0", framework="scaffold")
        risk_id, level = models.write_crime_risk_score(
            conn, mv_id, risk_score=args.score, district_id=args.district,
            factors={"demo": True, "cli": True})
        inf_id = models.log_inference(
            conn, mv_id, inputs={"district_id": args.district, "risk_score": args.score},
            outputs={"risk_level": level, "risk_score_id": risk_id},
            confidence=args.score, ref_table="District", ref_id=str(args.district))
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_district_risk_profile")
    print(json.dumps({"risk_score_id": risk_id, "risk_level": level,
                      "inference_id": inf_id, "model_version_id": mv_id}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="drishti-ml-batch", description=get_settings().app_name)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("health").set_defaults(func=_cmd_health)

    rm = sub.add_parser("refresh-matviews")
    rm.add_argument("--views", nargs="*", help="specific matviews (default: all)")
    rm.set_defaults(func=_cmd_refresh_matviews)

    reg = sub.add_parser("register-model")
    reg.add_argument("--name", required=True)
    reg.add_argument("--type", required=True)
    reg.add_argument("--version", required=True)
    reg.add_argument("--framework", default=None)
    reg.set_defaults(func=_cmd_register_model)

    ds = sub.add_parser("demo-score")
    ds.add_argument("--district", type=int, required=True)
    ds.add_argument("--score", type=float, default=0.5)
    ds.set_defaults(func=_cmd_demo_score)

    ap = sub.add_parser("apply-sql", help="apply a .sql migration file")
    ap.add_argument("--file", required=True)
    ap.set_defaults(func=_cmd_apply_sql)

    # ---- graph jobs (Phase 6) ----
    eg = sub.add_parser("enrich-graph", help="add intermediary nodes + seeded hidden associations")
    eg.add_argument("--seed", type=int, default=42)
    eg.set_defaults(func=_cmd_enrich_graph)

    cm = sub.add_parser("communities", help="Louvain communities + gang precision/recall")
    cm.set_defaults(func=_cmd_communities)

    ce = sub.add_parser("centrality", help="PageRank + betweenness -> EntityGraph.Properties")
    ce.add_argument("--betweenness-k", type=int, default=400, help="sample size for approx betweenness")
    ce.set_defaults(func=_cmd_centrality)

    ha = sub.add_parser("hidden-associations", help="materialize drishti_hidden_associations")
    ha.add_argument("--min-links", type=int, default=2)
    ha.set_defaults(func=_cmd_hidden_associations)

    # ---- geospatial jobs (Phase 7) ----
    hs = sub.add_parser("hotspots", help="ST-DBSCAN + KDE hotspots -> CrimeHotspot")
    hs.add_argument("--eps-m", type=float, default=1500.0)
    hs.add_argument("--eps-days", type=float, default=150.0)
    hs.add_argument("--min-samples", type=int, default=15)
    hs.set_defaults(func=_cmd_hotspots)

    ea = sub.add_parser("emerging-alerts", help="threshold-breach alerts -> AlertHistory")
    ea.add_argument("--window", type=int, default=6)
    ea.add_argument("--threshold-sigma", type=float, default=2.0)
    ea.set_defaults(func=_cmd_emerging_alerts)

    gv = sub.add_parser("geo-validate", help="PAI/hit-rate + known-pattern checks")
    gv.add_argument("--cutoff", default="2025-01-01")
    gv.set_defaults(func=_cmd_geo_validate)

    # ---- risk scoring (Phase 9) ----
    rs = sub.add_parser("risk-score", help="TabFM offender risk -> CrimeRiskScore")
    rs.add_argument("--context-size", type=int, default=1000)
    rs.add_argument("--limit", type=int, default=None, help="score a stratified sample (for heavy CPU models)")
    rs.add_argument("--estimators", type=int, default=None, help="TabFM ensemble members")
    rs.set_defaults(func=_cmd_risk_score)

    rc = sub.add_parser("risk-calibration", help="foundation vs baseline calibration report")
    rc.set_defaults(func=_cmd_risk_calibration)

    # ---- case decision-support (Phase 10) ----
    ec = sub.add_parser("embed-cases", help="embed a case corpus -> CrimeEmbedding (similar-case search)")
    ec.add_argument("--limit", type=int, default=12000,
                    help="cases to embed, stratified by sub-head (0 = all)")
    ec.add_argument("--batch-size", type=int, default=512)
    ec.add_argument("--embedder", default=None, help="mpnet|st|hashing (default: auto)")
    ec.set_defaults(func=_cmd_embed_cases)

    cs = sub.add_parser("case-summary", help="generate + write a cited AISummary for one case")
    cs.add_argument("--case", type=int, required=True)
    cs.set_defaults(func=_cmd_case_summary)

    cl = sub.add_parser("case-leads", help="generate + write ranked OfficerRecommendation leads for one case")
    cl.add_argument("--case", type=int, required=True)
    cl.set_defaults(func=_cmd_case_leads)

    # ---- money-trail detection (Phase 11) ----
    md = sub.add_parser("money-detect", help="flag structuring/layering/circular -> FinancialTransaction + AlertHistory")
    md.add_argument("--structuring-min-count", type=int, default=5)
    md.add_argument("--structuring-window-days", type=int, default=14)
    md.add_argument("--cycle-min-amount", type=float, default=10000)
    md.add_argument("--cycle-max-len", type=int, default=6)
    md.set_defaults(func=_cmd_money_detect)

    # ---- forecasting + early warning (Phase 12) ----
    fr = sub.add_parser("forecast-run", help="run TabFM+TimesFM+near-repeat+ST-GNN, fuse -> CrimePrediction + alerts")
    fr.add_argument("--head-id", type=int, default=None)
    fr.add_argument("--horizon-days", type=int, default=30)
    fr.set_defaults(func=_cmd_forecast_run)

    fv = sub.add_parser("forecast-validate", help="PAI/hit-rate on held-out incidents per district & head")
    fv.add_argument("--cutoff", default=None, help="YYYY-MM-DD")
    fv.add_argument("--horizon-months", type=int, default=3)
    fv.add_argument("--area-fraction", type=float, default=0.25)
    fv.set_defaults(func=_cmd_forecast_validate)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
