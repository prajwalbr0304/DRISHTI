"""Generate the Phase-3 AI / intelligence & analytics layer.

Runs single-process AFTER the operational data is loaded. Everything here is
derived from the real generated cases (sampled back from the database) and from
the criminal-population context, so the AI tables are internally consistent:
  * embeddings cluster by crime type (semantic search works),
  * risk scores / hotspots / predictions follow the actual district crime counts,
  * the entity graph / network edges reflect the gangs and recurring offenders,
  * alerts and officer recommendations reference real cases and officers.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Dict, List

import numpy as np

from . import boundaries as B
from . import reference as ref
from .config import GenConfig
from .context import Context
from .db import Geom, Json, Vector, copy_rows, fetch_all
from .names import person_name
from .rng import RNG


def generate_intelligence(conn, cfg: GenConfig, ctx: Context) -> Dict[str, int]:
    cur = conn.cursor()
    rng = RNG(cfg.seed * 99 + 5)
    counts: Dict[str, int] = {}

    models = _models(cur, cfg)
    dmap = {d["id"]: d for d in ctx.districts}

    district_counts = _district_counts(cur)
    dh_counts = _district_head_counts(cur)
    sample = _sample_cases(cur, cfg)

    counts["model_versions"] = len(set(models.values()))
    counts["entities"], ent_offender, ent_gang = _entity_graph(cur, cfg, ctx, rng)
    counts["network_edges"] = _network_edges(cur, cfg, ctx, rng, ent_offender, ent_gang)
    counts["gang_memberships"] = _gang_membership(cur, ctx, rng, ent_offender, ent_gang)
    counts["risk_scores"] = _risk_scores(cur, cfg, ctx, rng, models, dmap,
                                         district_counts, sample)
    counts["predictions"] = _predictions(cur, cfg, ctx, rng, models, dmap, dh_counts)
    counts["hotspots"] = _hotspots(cur, cfg, ctx, rng, models, dmap, dh_counts)
    counts["patterns"] = _patterns(cur, cfg, ctx, rng, models, sample)
    counts["embeddings"] = _embeddings(cur, cfg, rng, models, sample)
    counts["summaries"] = _summaries(cur, cfg, rng, models, sample)
    counts["alerts"] = _alerts(cur, cfg, ctx, rng, models, dmap, sample)
    counts["officer_recs"] = _officer_recs(cur, cfg, ctx, rng, models, sample)
    counts["inferences"] = _inferences(cur, cfg, rng, models, sample)
    counts["indicators"] = _indicators(cur, cfg, ctx, rng)
    counts.update(_financial(cur, cfg, ctx, rng, ent_offender, ent_gang, sample))
    counts.update(_chat(cur, cfg, rng, models, sample))

    conn.commit()
    _refresh_matviews(cur, conn)
    return counts


# ---------------------------------------------------------------------------
def _models(cur, cfg: GenConfig) -> Dict[str, int]:
    specs = [
        ("drishti-embed", "embedding", "1.2.0", "sentence-transformers", cfg.embedding_dim),
        ("drishti-risk", "classification", "2.1.0", "xgboost", None),
        ("drishti-forecast", "forecasting", "1.0.3", "prophet", None),
        ("drishti-hotspot", "clustering", "1.1.0", "sklearn", None),
        ("drishti-graph", "graph", "0.9.1", "networkx", None),
        ("drishti-officer", "regression", "1.0.0", "lightgbm", None),
        ("drishti-summary", "nlp", "1.4.0", "transformers", None),
        ("drishti-anomaly", "anomaly_detection", "0.8.0", "sklearn", None),
    ]
    rows, ids = [], {}
    for i, (name, mtype, ver, fw, dim) in enumerate(specs, start=1):
        rows.append((i, name, mtype, ver, fw, f"s3://models/{name}/{ver}", dim,
                     Json({"seed": cfg.seed}),
                     Json({"auc": round(0.7 + 0.2 * (i % 3) / 3, 3)}),
                     "active", _ts_days_ago(120), _ts_days_ago(60)))
        ids[mtype] = i
        ids[name] = i
    copy_rows(cur, "ModelVersion",
              ["ModelVersionID", "ModelName", "ModelType", "Version", "Framework",
               "ArtifactURI", "EmbeddingDim", "Hyperparameters", "Metrics",
               "Status", "TrainedAt", "DeployedAt"], rows)
    return ids


def _entity_graph(cur, cfg, ctx: Context, rng: RNG):
    """Nodes: gangs + top recurring offenders. Returns (count, offmap, gangmap)."""
    rows = []
    eid = 0
    ent_offender: Dict[int, int] = {}
    ent_gang: Dict[int, int] = {}

    # Entity "home" points are placed inside the real home-district polygon so
    # gang/offender nodes never land in the sea or across a state border.
    bnd = B.load_boundaries()
    _region_cache: Dict[int, object] = {}

    def _home_point(dist_idx: int):
        region = _region_cache.get(dist_idx)
        if region is None:
            region = bnd.district(ctx.districts[dist_idx]["name"])
            _region_cache[dist_idx] = region
        if region is None:  # defensive: unmapped district
            dd = ctx.districts[dist_idx]
            return dd["lon"], dd["lat"]
        p = B.uniform_points(region.geom, region.bounds, rng.g, 1)[0]
        return float(p[0]), float(p[1])

    # gang nodes
    for gi, g in enumerate(ctx.gangs):
        eid += 1
        d = ctx.districts[g["home_dist"]]
        glon, glat = _home_point(g["home_dist"])
        rows.append((eid, "gang", g["name"], "Gang", str(gi), None,
                     Json({"specialty": ctx.crime_profiles[g["specialty"]]["sub"],
                           "home_district": d["name"],
                           "vehicles": g["vehicles"]}),
                     Geom.point(glon, glat)))
        ent_gang[gi] = eid

    # recurring-offender nodes (highest offense budgets first, capped)
    order = sorted(range(len(ctx.offenders)),
                   key=lambda i: ctx.offenders[i]["offense_budget"], reverse=True)
    cap = min(cfg.entity_sample, len(order))
    for off_idx in order[:cap]:
        o = ctx.offenders[off_idx]
        eid += 1
        d = ctx.districts[o["home_dist"]]
        olon, olat = _home_point(o["home_dist"])
        rows.append((eid, "person", o["name"], "Accused", str(off_idx), None,
                     Json({"specialty": ctx.crime_profiles[o["specialty"]]["sub"],
                           "home_district": d["name"],
                           "career_offenses": o["offense_budget"],
                           "juvenile": o["is_juvenile"]}),
                     Geom.point(olon, olat)))
        ent_offender[off_idx] = eid

    copy_rows(cur, "EntityGraph",
              ["EntityID", "EntityType", "Label", "RefTable", "RefID",
               "Embedding", "Attributes", "geom"], rows, chunk=cfg.copy_chunk)
    return eid, ent_offender, ent_gang


def _network_edges(cur, cfg, ctx: Context, rng: RNG, ent_offender, ent_gang) -> int:
    rows = []
    edge_id = 0
    budget = cfg.max_network_edges

    def add(src, tgt, rel, weight, conf):
        nonlocal edge_id
        if src == tgt:
            return
        edge_id += 1
        cost = round(1.0 / max(weight, 0.05), 4)
        rows.append((edge_id, src, tgt, rel, cost, cost, False,
                     round(weight, 3), round(conf, 3),
                     Json({}), None, None))

    for gi, g in enumerate(ctx.gangs):
        if edge_id >= budget:
            break
        gang_ent = ent_gang.get(gi)
        member_ents = [ent_offender[m] for m in g["members"] if m in ent_offender]
        # gang -> member
        for me in member_ents:
            add(gang_ent, me, "gang_member", 0.9, 0.85)
        # co-offending clique among gang members (sparse)
        for a in range(len(member_ents)):
            for b in range(a + 1, len(member_ents)):
                if rng.bernoulli(0.35) and edge_id < budget:
                    add(member_ents[a], member_ents[b], "co_accused",
                        float(rng.random()) * 0.6 + 0.3, 0.7)

    # random associate edges among offenders (weak ties)
    off_ents = list(ent_offender.values())
    extra = min(budget - edge_id, len(off_ents) * 2)
    for _ in range(max(0, extra)):
        if edge_id >= budget:
            break
        a, b = rng.g.integers(0, len(off_ents), 2)
        add(off_ents[int(a)], off_ents[int(b)], "associate",
            float(rng.random()) * 0.4 + 0.1, 0.5)

    copy_rows(cur, "NetworkEdge",
              ["EdgeID", "Source", "Target", "RelationshipType", "Cost",
               "ReverseCost", "Directed", "Weight", "Confidence", "Properties",
               "ValidFrom", "ValidTo"], rows, chunk=cfg.copy_chunk)
    return edge_id


def _gang_membership(cur, ctx: Context, rng: RNG, ent_offender, ent_gang) -> int:
    rows = []
    gm_id = 0
    roles = ["leader", "core", "associate", "financier", "suspect"]
    role_w = np.array([1, 4, 6, 1, 3], float)
    role_cdf = np.cumsum(role_w / role_w.sum())
    for gi, g in enumerate(ctx.gangs):
        gang_ent = ent_gang.get(gi)
        if gang_ent is None:
            continue
        for j, m in enumerate(g["members"]):
            me = ent_offender.get(m)
            gm_id += 1
            role = "leader" if j == 0 else roles[int(np.searchsorted(role_cdf, rng.g.random()))]
            joined = dt.date(2019, 1, 1) + dt.timedelta(days=int(rng.g.integers(0, 2000)))
            active = rng.bernoulli(0.8)
            rows.append((gm_id, gang_ent, me, None, role, joined.isoformat(),
                         None if active else joined + dt.timedelta(days=400),
                         active, round(float(rng.random()) * 0.4 + 0.55, 3),
                         "network-analysis"))
    copy_rows(cur, "GangMembership",
              ["GangMembershipID", "GangEntityID", "MemberEntityID",
               "AccusedMasterID", "Role", "JoinedDate", "LeftDate", "IsActive",
               "Confidence", "Source"], rows)
    return gm_id


def _risk_scores(cur, cfg, ctx: Context, rng: RNG, models, dmap,
                 district_counts, sample) -> int:
    rows = []
    rid = 0
    mv = models["classification"]
    maxc = max(district_counts.values()) if district_counts else 1
    now = _ts_days_ago(0)
    # per-district area risk (latest)
    for did, cnt in district_counts.items():
        d = dmap.get(did)
        if not d:
            continue
        score = min(0.99, 0.15 + 0.8 * (cnt / maxc))
        rid += 1
        rows.append((rid, None, None, did, mv, round(score, 5),
                     _risk_level(score),
                     Json({"case_count": cnt, "normalized": round(cnt / maxc, 3)}),
                     Geom.point(d["lon"], d["lat"]), now, None))
    # per high-gravity case risk (subset of sample)
    for c in sample[: min(len(sample), cfg.n_case_summaries)]:
        if c["gravity_id"] == ctx.gravity_id.get("Heinous") or rng.bernoulli(0.15):
            base = 0.6 if c["gravity_id"] == ctx.gravity_id.get("Heinous") else 0.3
            score = float(np.clip(base + rng.gaussian(0, 0.15), 0.02, 0.99))
            rid += 1
            geom = Geom.point(c["lon"], c["lat"]) if c["lat"] is not None else None
            rows.append((rid, c["id"], c["station_id"], c["district_id"], mv,
                         round(score, 5), _risk_level(score),
                         Json({"gravity": "high" if base > 0.5 else "medium"}),
                         geom, now, None))
    copy_rows(cur, "CrimeRiskScore",
              ["RiskScoreID", "CaseMasterID", "UnitID", "DistrictID",
               "ModelVersionID", "RiskScore", "RiskLevel", "Factors", "geom",
               "ValidFrom", "ValidTo"], rows, chunk=cfg.copy_chunk)
    return rid


def _predictions(cur, cfg, ctx: Context, rng: RNG, models, dmap, dh_counts) -> int:
    rows = []
    pid = 0
    mv = models["forecasting"]
    start = dt.datetime.combine(cfg.end_date, dt.time()) + dt.timedelta(days=1)
    end = start + dt.timedelta(days=30)
    span_days = max(1, (cfg.end_date - cfg.start_date).days)
    for (did, head_id), cnt in dh_counts.items():
        d = dmap.get(did)
        if not d:
            continue
        monthly = cnt / span_days * 30.0
        predicted = float(max(0.0, rng.g.poisson(max(0.1, monthly))))
        prob = float(np.clip(monthly / 50.0, 0.02, 0.98))
        pid += 1
        rows.append((pid, mv, did, None, head_id,
                     start.strftime("%Y-%m-%d %H:%M:%S+00"),
                     end.strftime("%Y-%m-%d %H:%M:%S+00"),
                     round(predicted, 2), round(prob, 5),
                     round(float(np.clip(0.6 + rng.gaussian(0, 0.1), 0.3, 0.95)), 5),
                     Json({"baseline_monthly": round(monthly, 2)}),
                     Geom.point(d["lon"], d["lat"])))
    copy_rows(cur, "CrimePrediction",
              ["PredictionID", "ModelVersionID", "DistrictID", "UnitID",
               "CrimeHeadID", "PredictionStart", "PredictionEnd",
               "PredictedCount", "Probability", "Confidence", "Features", "geom"],
              rows, chunk=cfg.copy_chunk)
    return pid


def _hotspots(cur, cfg, ctx: Context, rng: RNG, models, dmap, dh_counts) -> int:
    rows = []
    hid = 0
    mv = models["clustering"]
    # top (district, head) cells by count become hotspots
    top = sorted(dh_counts.items(), key=lambda kv: kv[1], reverse=True)
    for (did, head_id), cnt in top[: min(len(top), 300)]:
        d = dmap.get(did)
        if not d:
            continue
        hid += 1
        size = 0.02 + 0.03 * rng.random()
        clat = d["lat"] + float(rng.gaussian(0, 0.03))
        clon = d["lon"] + float(rng.gaussian(0, 0.03))
        ring = [(clon - size, clat - size), (clon + size, clat - size),
                (clon + size, clat + size), (clon - size, clat + size),
                (clon - size, clat - size)]
        rows.append((hid, f"{d['name']} cluster #{hid}", did, None, head_id, mv,
                     Geom.polygon(ring), Geom.point(clon, clat),
                     round(float(cnt) * (0.5 + rng.random()), 3), int(cnt),
                     cfg.start_date.isoformat(), cfg.end_date.isoformat(), True))
    copy_rows(cur, "CrimeHotspot",
              ["HotspotID", "Name", "DistrictID", "UnitID", "CrimeHeadID",
               "ModelVersionID", "geom", "Centroid", "Intensity", "CaseCount",
               "PeriodStart", "PeriodEnd", "IsActive"], rows, chunk=cfg.copy_chunk)
    return hid


def _patterns(cur, cfg, ctx: Context, rng: RNG, models, sample) -> int:
    mv = models["graph"]
    rows, link_rows = [], []
    pid = 0
    # gang network patterns
    for gi, g in enumerate(ctx.gangs[: min(len(ctx.gangs), 40)]):
        pid += 1
        sub = ctx.crime_profiles[g["specialty"]]["sub"]
        rows.append((pid, "network", f"{g['name']} organised network",
                     f"Recurring {sub.lower()} activity linked to the {g['name']} "
                     f"group across multiple jurisdictions.",
                     ctx.crime_profiles[g["specialty"]]["crime_head_id"], mv,
                     round(0.6 + float(rng.random()) * 0.35, 5),
                     Json({"members": len(g["members"]), "gang_index": gi}), None))
    # serial / MO patterns from clusters of similar sampled cases
    by_head: Dict[int, list] = {}
    for c in sample:
        by_head.setdefault(c["head_id"], []).append(c)
    for head_id, cases in by_head.items():
        if len(cases) < 5:
            continue
        pid += 1
        chosen = cases[: min(len(cases), 12)]
        rows.append((pid, "serial", f"Serial pattern (head {head_id})",
                     "A cluster of cases with similar modus operandi and timing "
                     "was detected by sequence analysis.", head_id, mv,
                     round(0.5 + float(rng.random()) * 0.4, 5),
                     Json({"support": len(chosen)}), None))
        for c in chosen:
            link_rows.append((pid, c["id"],
                              round(0.5 + float(rng.random()) * 0.5, 5)))
    copy_rows(cur, "CrimePattern",
              ["PatternID", "PatternType", "Name", "Description", "CrimeHeadID",
               "ModelVersionID", "Confidence", "Attributes", "geom"], rows,
              chunk=cfg.copy_chunk)
    if link_rows:
        copy_rows(cur, "CrimePatternCase",
                  ["PatternID", "CaseMasterID", "Relevance"], link_rows,
                  chunk=cfg.copy_chunk)
    return pid


def _embeddings(cur, cfg, rng: RNG, models, sample) -> int:
    mv = models["embedding"]
    dim = cfg.embedding_dim
    # per-crime-head cluster centre so semantically similar crimes cluster
    centers: Dict[int, np.ndarray] = {}

    def center(head_id: int) -> np.ndarray:
        if head_id not in centers:
            g = np.random.default_rng(1000 + head_id)
            v = g.normal(0, 1, dim)
            centers[head_id] = v / (np.linalg.norm(v) + 1e-9)
        return centers[head_id]

    rows = []
    eid = 0
    subset = sample[: min(len(sample), cfg.n_case_embeddings)]
    for c in subset:
        vec = center(c["head_id"]) + rng.g.normal(0, 0.35, dim)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        eid += 1
        content = f"case {c['id']} head {c['head_id']} district {c['district_id']}"
        rows.append((eid, "brief_facts", c["id"], None, None, mv,
                     Vector(vec), content,
                     hashlib.md5(content.encode()).hexdigest()))
    copy_rows(cur, "CrimeEmbedding",
              ["EmbeddingID", "SourceType", "CaseMasterID", "RefTable", "RefID",
               "ModelVersionID", "Embedding", "Content", "ContentHash"], rows,
              chunk=max(2000, cfg.copy_chunk // 4))
    return eid


def _summaries(cur, cfg, rng: RNG, models, sample) -> int:
    mv = models["nlp"]
    rows = []
    sid = 0
    subset = sample[: min(len(sample), cfg.n_case_summaries)]
    for c in subset:
        sid += 1
        text = (f"Automated brief for FIR {c['id']}: a {c['head_id']}-category "
                f"offence registered in district {c['district_id']}. Current "
                f"status code {c['status_id']}. Investigation ongoing; key "
                f"entities and timeline extracted for review.")
        rows.append((sid, "case_brief", c["id"], None, None, mv, text,
                     int(rng.g.integers(60, 260)),
                     round(0.7 + float(rng.random()) * 0.25, 5)))
    copy_rows(cur, "AISummary",
              ["SummaryID", "SummaryType", "CaseMasterID", "RefTable", "RefID",
               "ModelVersionID", "SummaryText", "TokensUsed", "Confidence"],
              rows, chunk=cfg.copy_chunk)
    return sid


def _alerts(cur, cfg, ctx: Context, rng: RNG, models, dmap, sample) -> int:
    mv = models["anomaly_detection"]
    rows = []
    aid = 0
    statuses = ["open", "acknowledged", "resolved", "dismissed"]
    status_cdf = np.cumsum(np.array([0.4, 0.3, 0.2, 0.1]))
    subset = sample[: min(len(sample), 4000)]
    for c in subset:
        if not rng.bernoulli(0.25):
            continue
        aid += 1
        sev = _risk_level(float(np.clip(rng.gaussian(0.55, 0.2), 0, 1)))
        sev = {"low": "low", "medium": "medium", "high": "high",
               "critical": "critical"}[sev]
        atype = rng.choice(["risk_threshold", "pattern_match", "prediction",
                            "anomaly", "hotspot"])
        st = statuses[int(np.searchsorted(status_cdf, rng.g.random()))]
        ack_by = int(rng.g.integers(1, cfg.n_officers + 1)) if st != "open" else None
        ack_at = _ts_days_ago(int(rng.g.integers(1, 60))) if ack_by else None
        geom = Geom.point(c["lon"], c["lat"]) if c["lat"] is not None else None
        rows.append((aid, atype, sev, f"{atype} on FIR {c['id']}",
                     f"Model {mv} flagged FIR {c['id']} ({atype}).",
                     c["id"], c["district_id"], c["station_id"], None, mv,
                     Json({"score": round(float(rng.random()), 3)}), geom, st,
                     ack_by, ack_at))
    copy_rows(cur, "AlertHistory",
              ["AlertID", "AlertType", "Severity", "Title", "Message",
               "CaseMasterID", "DistrictID", "UnitID", "EntityID",
               "ModelVersionID", "Payload", "geom", "Status", "AcknowledgedBy",
               "AcknowledgedAt"], rows, chunk=cfg.copy_chunk)
    return aid


def _officer_recs(cur, cfg, ctx: Context, rng: RNG, models, sample) -> int:
    mv = models["regression"]
    rows = []
    rid = 0
    subset = sample[: min(len(sample), 5000)]
    for c in subset:
        officers = ctx.officers_by_station.get(c["station_id"]) or []
        if not officers:
            continue
        k = min(3, len(officers))
        picks = list(rng.choice(officers, size=k, replace=False)) if k < len(officers) else officers[:k]
        for order, emp in enumerate(picks, start=1):
            rid += 1
            score = round(float(np.clip(1.0 - 0.2 * (order - 1) + rng.gaussian(0, 0.05), 0, 1)), 5)
            rows.append((rid, c["id"], int(emp), mv, score, order,
                         Json({"reason": "station proximity + workload balance",
                               "rank_order": order}),
                         "accepted" if order == 1 and rng.bernoulli(0.4) else "suggested"))
    copy_rows(cur, "OfficerRecommendation",
              ["RecommendationID", "CaseMasterID", "EmployeeID", "ModelVersionID",
               "Score", "RankOrder", "Rationale", "Status"], rows,
              chunk=cfg.copy_chunk)
    return rid


def _inferences(cur, cfg, rng: RNG, models, sample) -> int:
    rows = []
    iid = 0
    model_ids = [models["classification"], models["forecasting"],
                 models["nlp"], models["embedding"]]
    subset = sample[: min(len(sample), 6000)]
    for c in subset:
        iid += 1
        mv = int(rng.choice(model_ids))
        # EntityType is entity_type_enum (no 'case' member); a case-level
        # inference is identified by CaseMasterID, so EntityType stays NULL.
        rows.append((iid, mv, None, c["id"], None, None,
                     Json({"case_id": c["id"]}),
                     Json({"score": round(float(rng.random()), 4)}),
                     round(float(rng.random()) * 0.4 + 0.55, 5),
                     int(rng.g.integers(5, 400))))
    copy_rows(cur, "ModelInference",
              ["InferenceID", "ModelVersionID", "EntityType", "CaseMasterID",
               "RefTable", "RefID", "Input", "Output", "Confidence", "LatencyMs"],
              rows, chunk=cfg.copy_chunk)
    return iid


def _indicators(cur, cfg, ctx: Context, rng: RNG) -> int:
    """Seed stable district profiles with modest, explainable time movement.

    Values are synthetic and deliberately generated from district traits rather
    than from observed crime counts. That keeps the correlation widget useful
    without baking its answer into the covariates. Each district owns an
    independent RNG stream so upstream generator changes cannot reshuffle its
    social/economic history.
    """
    social, weather, econ = [], [], []
    sid = wid = eid = 0
    months = _month_starts(cfg.start_date, cfg.end_date)
    for d in ctx.districts:
        tags = set(d["tags"])
        metro = "metro" in tags
        urban = metro or "urban" in tags
        periurban = "periurban" in tags
        rural = "rural" in tags
        coastal = "coastal" in tags
        hilly = "hilly" in tags
        border = "border" in tags
        mining = "mining" in tags

        # Reproducible district-specific offsets; no dependence on call order.
        dseed = cfg.seed * 100_003 + d["id"] * 997
        drng = np.random.default_rng(dseed)
        offset = lambda scale: float(drng.normal(0.0, scale))

        base_pop = int(d["pop_weight"] * 1_000_000)
        annual_growth = 0.022 if metro else (0.017 if periurban else (0.012 if urban else 0.007))
        density = (8200 if metro else 1250 if urban else 720 if periurban else 260)
        if coastal:
            density += 180
        if hilly:
            density *= 0.62
        density *= 0.88 + min(d["pop_weight"], 4.0) * 0.04

        literacy = (88 if metro else 80 if urban else 75 if coastal else 69) + offset(2.2)
        if border and rural:
            literacy -= 2.5
        unemployment = (5.7 if metro else 6.8 if urban else 7.5 if periurban else 8.6) + offset(0.7)
        if border:
            unemployment += 0.5
        youth = (26.5 if metro else 28.5 if urban else 31.0) + offset(1.5)
        migration = (76 if metro else 48 if urban else 55 if periurban else 21) + offset(5)

        income = (330_000 if metro else 190_000 if urban else 155_000 if coastal
                  else 122_000 if mining else 105_000) * (1 + offset(0.06))
        poverty = (0.075 if metro else 0.14 if urban else 0.18 if coastal else 0.255)
        poverty += (0.035 if border and rural else 0) + offset(0.018)
        business = (42 if metro else 22 if urban else 15 if periurban else 8.5)
        business += (3 if coastal else 0) + (2 if mining else 0) + offset(1.5)

        for m in months:
            years = (m.year - cfg.start_date.year) + (m.month - cfg.start_date.month) / 12
            season = np.sin(2 * np.pi * (m.month - 1) / 12)
            pop = int(base_pop * ((1 + annual_growth) ** years))
            profile = {
                "synthetic": True,
                "profile_version": "district-context-v2",
                "district": d["name"],
                "tags": sorted(tags),
            }
            sid += 1
            social.append((sid, d["id"], None, m.isoformat(), pop,
                           round(float(np.clip(density * (1 + annual_growth * years)
                                               + offset(density * 0.008), 40, 15000)), 2),
                           round(float(np.clip(literacy + 0.35 * years + offset(0.22), 45, 96)), 2),
                           round(float(np.clip(unemployment + 0.45 * season + offset(0.18), 2, 18)), 2),
                           round(float(np.clip(youth - 0.12 * years + offset(0.2), 18, 40)), 2),
                           round(float(np.clip(migration + 2.0 * season + offset(0.7), 2, 95)), 2),
                           Json({**profile, "units": {"population_density": "persons_per_sq_km",
                                                      "rates": "percent",
                                                      "migration_index": "0_to_100"}}),
                           "drishti-synthetic-district-profile-v2",
                           Geom.point(d["lon"], d["lat"])))
            eid += 1
            econ.append((eid, d["id"], None, m.isoformat(),
                         (m + dt.timedelta(days=27)).isoformat(),
                         round(float(np.clip(income * ((1.055) ** years)
                                             * (1 + 0.012 * season) + offset(income * 0.008),
                                             45_000, 600_000)), 2),
                         round(float(np.clip(unemployment + 0.4 * season + offset(0.16), 2, 18)), 2),
                         round(float(np.clip(poverty - 0.006 * years + offset(0.004), 0.03, 0.45)), 3),
                         round(float(np.clip(5.4 + 0.8 * season + offset(0.25), 2.5, 9.5)), 2),
                         round(float(np.clip(business * (1 + 0.025 * years) + offset(0.3), 3, 65)), 2),
                         Json({**profile, "units": {"per_capita_income": "inr_per_year",
                                                    "poverty_index": "0_to_1",
                                                    "business_density": "establishments_per_1000"}}),
                         "drishti-synthetic-district-profile-v2",
                         Geom.point(d["lon"], d["lat"])))

        for m in months:
            wid += 1
            monsoon = m.month in (6, 7, 8, 9)
            summer = m.month in (3, 4, 5)
            temp_base = 27.5 - max(0, d["lat"] - 12) * 0.22
            if hilly:
                temp_base -= 3.5
            rain_base = 250 if (coastal or hilly) else (105 if d["lat"] < 14 else 72)
            rainfall = rain_base if monsoon else (28 if coastal else 10)
            weather.append((wid, d["id"], None,
                            m.strftime("%Y-%m-%d %H:%M:%S+00"),
                            round(float(np.clip(temp_base + (3.2 if summer else -1.2 if monsoon else 0)
                                                + offset(0.8), 14, 41)), 2),
                            round(float(np.clip((82 if monsoon else 64 if coastal else 50)
                                                + offset(4), 25, 98)), 2),
                            round(float(np.clip(rainfall * (1 + offset(0.18)), 0, 650)), 2),
                            round(float(np.clip(11 + (4 if monsoon else 0) + offset(2), 2, 35)), 2),
                            "Rain" if monsoon else "Clear",
                            Json({"synthetic": True, "profile_version": "district-climate-v2",
                                  "district": d["name"], "units": {"rainfall": "mm_monthly"}}),
                            "drishti-synthetic-district-climate-v2",
                            Geom.point(d["lon"], d["lat"])))
    copy_rows(cur, "SocialIndicator",
              ["SocialIndicatorID", "DistrictID", "UnitID", "ObservedDate",
               "Population", "PopulationDensity", "LiteracyRate",
               "UnemploymentRate", "YouthRatio", "MigrationIndex", "Metrics",
               "Source", "geom"], social, chunk=cfg.copy_chunk)
    copy_rows(cur, "EconomicIndicator",
              ["EconomicIndicatorID", "DistrictID", "UnitID", "PeriodStart",
               "PeriodEnd", "PerCapitaIncome", "UnemploymentRate", "PovertyIndex",
               "InflationRate", "BusinessDensity", "Metrics", "Source", "geom"],
              econ, chunk=cfg.copy_chunk)
    copy_rows(cur, "WeatherIndicator",
              ["WeatherIndicatorID", "DistrictID", "UnitID", "ObservedAt",
               "TemperatureC", "HumidityPct", "RainfallMm", "WindSpeedKmph",
               "Condition", "Metrics", "Source", "geom"], weather,
              chunk=cfg.copy_chunk)
    return sid + wid + eid


# ---------------------------------------------------------------------------
# Financial sub-graph (Phase 1.5 extension — doc 04 §1)
#   Mule accounts + structuring / fan-in / layering patterns tied to gang
#   entities, plus background legitimate transfers. Flagged rows carry a reason
#   and (as evidence) link to real cyber/economic fraud cases.
# ---------------------------------------------------------------------------
_BANK_CODES = {
    "State Bank of India": "SBIN", "Canara Bank": "CNRB", "Karnataka Bank": "KARB",
    "HDFC Bank": "HDFC", "ICICI Bank": "ICIC", "Axis Bank": "UTIB",
    "Kotak Mahindra Bank": "KKBK", "Bank of Baroda": "BARB",
    "Union Bank of India": "UBIN",
}
_STRUCTURING_THRESHOLD = 50_000  # deposits are kept just under this to evade reporting


def _financial(cur, cfg, ctx: Context, rng: RNG, ent_offender, ent_gang, sample) -> Dict[str, int]:
    banks = list(_BANK_CODES)
    accounts: List[tuple] = []
    txns: List[tuple] = []
    links: List[tuple] = []
    acc_id = txn_id = link_id = 0

    def add_account(atype, holder, entity_id, dist_idx, flagged, attrs):
        nonlocal acc_id
        acc_id += 1
        d = ctx.districts[dist_idx % len(ctx.districts)]
        bank = rng.choice(banks)
        ifsc = f"{_BANK_CODES[bank]}0{int(rng.g.integers(0, 1_000_000)):06d}"
        accno = str(int(rng.g.integers(10_000_000_000, 99_999_999_999)))
        geom = Geom.point(d["lon"] + float(rng.gaussian(0, 0.02)),
                          d["lat"] + float(rng.gaussian(0, 0.02)))
        accounts.append((acc_id, accno, atype, holder, entity_id, bank, ifsc,
                         geom, flagged, Json(attrs)))
        return acc_id

    def add_txn(src, dst, amount, ts, channel, flagged, reason, case_id, props):
        nonlocal txn_id
        if src is None or dst is None or src == dst:
            return None
        txn_id += 1
        txns.append((txn_id, src, dst, round(float(amount), 2), ts, channel,
                     flagged, reason, case_id, Json(props)))
        return txn_id

    def add_link(tid, case_id, ltype, conf):
        nonlocal link_id
        if tid is None or case_id is None:
            return
        link_id += 1
        links.append((link_id, tid, case_id, ltype, round(float(conf), 5)))

    # fraud cases usable as evidence targets for flagged money flows
    fraud_ids = [int(r[0]) for r in fetch_all(cur, """
        SELECT cm."CaseMasterID" FROM "CaseMaster" cm
        JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID"
        WHERE ch."CrimeGroupName" ILIKE '%cyber%' OR ch."CrimeGroupName" ILIKE '%economic%'
        ORDER BY cm."CaseMasterID" LIMIT 6000""")]

    small_channels = ["upi", "imps", "cash-deposit"]

    # background pool of ordinary public accounts (fraud money origins + noise)
    source_pool = [
        add_account("savings",
                    person_name(rng, ref.GENDER_FEMALE if rng.bernoulli(0.45) else ref.GENDER_MALE),
                    None, int(rng.g.integers(0, len(ctx.districts))), False,
                    {"role": "public"})
        for _ in range(1500)
    ]

    # per-gang mule network
    for gi, g in enumerate(ctx.gangs):
        gang_ent = ent_gang.get(gi)
        home = g["home_dist"]
        financier = add_account("business", f"{g['name']} Holdings", gang_ent,
                                home, True, {"role": "financier", "gang": g["name"]})
        mules: List[int] = []
        for m in g["members"][:8]:
            ment = ent_offender.get(m)
            holder = ctx.offenders[m]["name"] if m < len(ctx.offenders) else person_name(rng, ref.GENDER_MALE)
            di = ctx.offenders[m]["home_dist"] if m < len(ctx.offenders) else home
            add_account("savings", holder, ment, di, False, {"role": "member"})
            mules.append(add_account("mule", holder, ment, di, True,
                                     {"role": "mule", "gang": g["name"]}))
        if not mules:
            mules = [add_account("mule", f"{g['name']} Mule", gang_ent, home, True,
                                 {"role": "mule"})]

        span = max(1, (cfg.end_date - cfg.start_date).days - 10)
        for mule in mules:
            base_day = int(rng.g.integers(0, span))
            case_id = int(rng.choice(fraud_ids)) if fraud_ids and rng.bernoulli(0.8) else None
            total = 0.0
            # STRUCTURING: many sub-threshold deposits over a few days
            for k in range(int(rng.g.integers(6, 16))):
                amt = float(rng.g.integers(38_000, _STRUCTURING_THRESHOLD - 500))
                total += amt
                tid = add_txn(int(rng.choice(source_pool)), mule, amt,
                              _ts_between(cfg, base_day + k // 3, int(rng.g.integers(0, 86400))),
                              rng.choice(small_channels), True, "structuring",
                              case_id if rng.bernoulli(0.5) else None,
                              {"pattern": "structuring", "below_threshold": True})
                if tid and case_id and rng.bernoulli(0.5):
                    add_link(tid, case_id, "proceeds", 0.6 + float(rng.random()) * 0.35)
            # CONSOLIDATION: mule -> financier (rapid fan-in)
            tid = add_txn(mule, financier, total * (0.9 + 0.08 * float(rng.random())),
                          _ts_between(cfg, base_day + 6, int(rng.g.integers(0, 86400))),
                          "neft", True, "mule-consolidation", case_id,
                          {"pattern": "fan_in"})
            if tid and case_id:
                add_link(tid, case_id, "proceeds", 0.7 + float(rng.random()) * 0.25)

        # LAYERING: financier -> external business accounts (cash-out)
        for _ in range(int(rng.g.integers(1, 4))):
            ext = add_account("current", "Trading Enterprises", None,
                              int(rng.g.integers(0, len(ctx.districts))), False,
                              {"role": "layering_target"})
            add_txn(financier, ext, float(rng.g.integers(200_000, 900_000)),
                    _ts_between(cfg, int(rng.g.integers(0, span)), int(rng.g.integers(0, 86400))),
                    "rtgs", True, "layering", None, {"pattern": "layering"})

    # BACKGROUND legitimate transfers among the public pool (unflagged noise)
    span_full = max(1, (cfg.end_date - cfg.start_date).days)
    for _ in range(8000):
        add_txn(int(rng.choice(source_pool)), int(rng.choice(source_pool)),
                float(rng.g.integers(500, 40_000)),
                _ts_between(cfg, int(rng.g.integers(0, span_full)), int(rng.g.integers(0, 86400))),
                rng.choice(["upi", "imps", "neft"]), False, None, None, {})

    copy_rows(cur, "FinancialAccount",
              ["AccountID", "AccountNo", "AccountType", "HolderName", "EntityID",
               "Bank", "IFSC", "geom", "IsFlagged", "Attributes"], accounts,
              chunk=cfg.copy_chunk)
    copy_rows(cur, "FinancialTransaction",
              ["TransactionID", "SourceAccountID", "DestinationAccountID", "Amount",
               "TxnTimestamp", "Channel", "IsFlagged", "FlagReason",
               "EvidenceCaseID", "Properties"], txns, chunk=cfg.copy_chunk)
    if links:
        copy_rows(cur, "TransactionLink",
                  ["LinkID", "TransactionID", "CaseMasterID", "LinkType", "Confidence"],
                  links, chunk=cfg.copy_chunk)
    return {"fin_accounts": acc_id, "fin_txns": txn_id, "txn_links": link_id}


# ---------------------------------------------------------------------------
# Conversational demo data (Phase 1.5 extension — doc 01 §4.7)
#   A handful of Ask-DRISHTI sessions with NL->SQL exchanges honouring the
#   answer/confidence/source_record_ids/model_version contract, incl. Kannada.
# ---------------------------------------------------------------------------
def _chat(cur, cfg, rng: RNG, models, sample) -> Dict[str, int]:
    # Re-seed the demo governance users. A --truncate run wipes "users" via the
    # TRUNCATE ... CASCADE on "Unit" (users.unit_id -> Unit), so we restore the
    # per-role demo accounts here to keep chat/audit ownership valid. Idempotent.
    cur.execute("""
        INSERT INTO "users" ("username", "display_name", "role_id", "is_active", "must_reset_password")
        SELECT v.username, v.display_name, r."role_id", TRUE, TRUE
        FROM "roles" r
        JOIN (VALUES
            ('dgp.vikram',    'DGP Vikram Shetty',        'dgp_state_command'),
            ('igp.meenakshi', 'IGP Meenakshi Rao',        'adgp_igp_range'),
            ('sp.anand',      'SP Anand Kumar',           'sp_district_command'),
            ('dysp.kavya',    'Dy.SP Kavya Hegde',        'dysp_acp'),
            ('sho.suresh',    'SHO Suresh Patil',         'sho'),
            ('io.ramesh',     'PSI Ramesh Gowda',         'investigating_officer'),
            ('analyst.divya', 'Analyst Divya Naik',       'crime_analyst'),
            ('cyber.arjun',   'Insp. Arjun Bhat (CEN)',   'cyber_cell'),
            ('traffic.latha', 'Traffic ACP Latha Prasad', 'traffic_command'),
            ('admin',         'Sysadmin Nikhil Jain',     'system_admin')
        ) AS v(username, display_name, role_name) ON r."role_name" = v.role_name
        ON CONFLICT ("username") DO NOTHING
    """)
    demo = fetch_all(cur, """
        SELECT u."user_id", u."display_name", r."role_name"
        FROM "users" u JOIN "roles" r ON r."role_id" = u."role_id"
        ORDER BY u."user_id" """)
    if not demo:
        demo = [(None, "Officer", "investigating_officer")]

    def cite(n):
        return [int(sample[i]["id"]) for i in
                rng.g.integers(0, max(1, len(sample)), size=min(n, len(sample)))]

    nlp, embed = models["nlp"], models["embedding"]
    # (role_name, lang, title, user_text, generated_sql, assistant_text)
    scripts = [
        ("cyber_cell", "en", "Cyber fraud in Bengaluru City",
         "Show cyber fraud FIRs registered in Bengaluru City this year",
         'SELECT cm."CrimeNo", cm."CrimeRegisteredDate" FROM "CaseMaster" cm '
         'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
         'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
         'JOIN "CrimeHead" ch ON ch."CrimeHeadID"=cm."CrimeMajorHeadID" '
         'WHERE d."DistrictName"=\'Bengaluru City\' AND ch."CrimeGroupName" ILIKE \'%cyber%\' '
         'AND cm."CrimeRegisteredDate">=date_trunc(\'year\',CURRENT_DATE);',
         "Bengaluru City leads the state on cyber-fraud registrations this year. "
         "The matching FIRs are cited below."),
        ("crime_analyst", "en", "Active robbery gangs",
         "Which gangs are most active in robbery cases?",
         'SELECT eg."Label", COUNT(*) AS cases FROM "GangMembership" gm '
         'JOIN "EntityGraph" eg ON eg."EntityID"=gm."GangEntityID" '
         'GROUP BY eg."Label" ORDER BY cases DESC LIMIT 10;',
         "Ranked the organised networks by linked robbery activity; the top "
         "groups and their supporting cases are listed."),
        ("sho", "en", "Pending heinous cases in Kalaburagi",
         "List heinous crimes still under investigation in Kalaburagi",
         'SELECT cm."CrimeNo" FROM "CaseMaster" cm '
         'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
         'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
         'JOIN "GravityOffence" g ON g."GravityOffenceID"=cm."GravityOffenceID" '
         'JOIN "CaseStatusMaster" s ON s."CaseStatusID"=cm."CaseStatusID" '
         'WHERE d."DistrictName"=\'Kalaburagi\' AND g."LookupValue"=\'Heinous\' '
         'AND s."CaseStatusName" ILIKE \'%investigation%\';',
         "These heinous FIRs in Kalaburagi are still open for investigation."),
        ("investigating_officer", "kn", "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು",
         "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಇತ್ತೀಚಿನ ಕಳ್ಳತನ ಪ್ರಕರಣಗಳನ್ನು ತೋರಿಸಿ",
         'SELECT cm."CrimeNo", cm."CrimeRegisteredDate" FROM "CaseMaster" cm '
         'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
         'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
         'JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID" '
         'WHERE d."DistrictName" ILIKE \'Bengaluru%\' AND csh."CrimeHeadName"=\'Theft\' '
         'ORDER BY cm."CrimeRegisteredDate" DESC LIMIT 50;',
         "ಬೆಂಗಳೂರಿನ ಇತ್ತೀಚಿನ ಕಳ್ಳತನ ಪ್ರಕರಣಗಳನ್ನು ಕೆಳಗೆ ಉಲ್ಲೇಖಿಸಲಾಗಿದೆ."),
        ("dgp_state_command", "en", "Vehicle theft hotspots",
         "Top 5 districts by vehicle theft",
         'SELECT d."DistrictName", COUNT(*) n FROM "CaseMaster" cm '
         'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
         'JOIN "District" d ON d."DistrictID"=u."DistrictID" '
         'JOIN "CrimeSubHead" csh ON csh."CrimeSubHeadID"=cm."CrimeMinorHeadID" '
         'WHERE csh."CrimeHeadName"=\'Vehicle Theft\' '
         'GROUP BY d."DistrictName" ORDER BY n DESC LIMIT 5;',
         "Aggregate view only: the five districts with the highest vehicle-theft "
         "volumes are summarised (no individual PII)."),
    ]

    by_role: Dict[str, tuple] = {}
    for uid, name, role in demo:
        by_role.setdefault(role, (uid, name))

    sessions, messages, transcripts = [], [], []
    sid = mid = tid = 0
    for role, lang, title, q, sql, a in scripts:
        uid, uname = by_role.get(role, (demo[0][0], demo[0][1]))
        sid += 1
        sessions.append((sid, uid, role, lang, title))
        # user turn
        mid += 1
        user_mid = mid
        messages.append((mid, sid, "user", q, lang, None, Json([]), None, None))
        # assistant turn (honours the AI output contract)
        mid += 1
        cited = cite(int(rng.g.integers(2, 6)))
        conf = round(0.72 + float(rng.random()) * 0.24, 5)
        messages.append((mid, sid, "assistant", a, lang, sql, Json(cited), conf, nlp))
        # a voice query on the Kannada session
        if lang == "kn":
            tid += 1
            low = rng.bernoulli(0.5)
            transcripts.append((tid, user_mid, f"s3://voice/{sid}/{user_mid}.wav", q,
                                lang, round(0.55 if low else 0.9, 5), low))

    copy_rows(cur, "ChatSession",
              ["SessionID", "UserID", "Role", "Language", "Title"], sessions)
    copy_rows(cur, "ChatMessage",
              ["MessageID", "SessionID", "Sender", "ContentText", "Language",
               "GeneratedSQL", "CitedRecordIds", "Confidence", "ModelVersionID"],
              messages)
    if transcripts:
        copy_rows(cur, "VoiceTranscript",
                  ["TranscriptID", "MessageID", "RawAudioRef", "TranscriptText",
                   "Language", "Confidence", "IsLowConfidence"], transcripts)
    return {"chat_sessions": sid, "chat_messages": mid, "voice_transcripts": tid}


def _ts_between(cfg, day_offset: int, secs: int) -> str:
    span = (cfg.end_date - cfg.start_date).days
    day_offset = max(0, min(int(day_offset), span))
    d = cfg.start_date + dt.timedelta(days=day_offset)
    return (dt.datetime.combine(d, dt.time())
            + dt.timedelta(seconds=int(secs) % 86400)).strftime("%Y-%m-%d %H:%M:%S+00")


# ---------------------------------------------------------------------------
def _sample_cases(cur, cfg: GenConfig) -> List[dict]:
    limit = max(cfg.n_case_embeddings, cfg.n_case_summaries, 8000) * 2
    rows = fetch_all(cur, f"""
        SELECT cm."CaseMasterID", cm."CrimeMajorHeadID", cm."GravityOffenceID",
               cm."CaseStatusID", cm."PoliceStationID", u."DistrictID",
               cm."latitude", cm."longitude"
        FROM "CaseMaster" cm
        JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"
        ORDER BY cm."CaseMasterID"
        LIMIT {int(limit)}
    """)
    out = []
    for r in rows:
        out.append({"id": r[0], "head_id": r[1], "gravity_id": r[2],
                    "status_id": r[3], "station_id": r[4], "district_id": r[5],
                    "lat": float(r[6]) if r[6] is not None else None,
                    "lon": float(r[7]) if r[7] is not None else None})
    return out


def _district_counts(cur) -> Dict[int, int]:
    rows = fetch_all(cur, """
        SELECT u."DistrictID", COUNT(*)
        FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"
        GROUP BY u."DistrictID" """)
    return {int(r[0]): int(r[1]) for r in rows if r[0] is not None}


def _district_head_counts(cur) -> Dict[tuple, int]:
    rows = fetch_all(cur, """
        SELECT u."DistrictID", cm."CrimeMajorHeadID", COUNT(*)
        FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"
        WHERE cm."CrimeMajorHeadID" IS NOT NULL
        GROUP BY u."DistrictID", cm."CrimeMajorHeadID" """)
    return {(int(r[0]), int(r[1])): int(r[2]) for r in rows if r[0] is not None}


def _refresh_matviews(cur, conn) -> None:
    for mv in ("mv_crime_stats", "mv_district_risk_profile", "mv_active_hotspots"):
        try:
            cur.execute(f'REFRESH MATERIALIZED VIEW "{mv}"')
            conn.commit()
        except Exception:
            conn.rollback()


def _risk_level(score: float) -> str:
    if score < 0.25:
        return "low"
    if score < 0.5:
        return "medium"
    if score < 0.75:
        return "high"
    return "critical"


def _ts_days_ago(days: int) -> str:
    return (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S+00")


def _month_starts(start: dt.date, end: dt.date) -> List[dt.date]:
    out = []
    y, m = start.year, start.month
    while (y < end.year) or (y == end.year and m <= end.month):
        out.append(dt.date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out
