"""Orchestrates the full generation pipeline across all phases."""
from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List

from . import cases
from .config import GenConfig
from .context import Context
from .db import connect, reset_identity, truncate_all
from .intelligence import generate_intelligence
from .lookups import load_reference

# Tables in load order; also used (reversed) for truncation.
IDENTITY_TABLES = [
    ("State", "StateID"), ("District", "DistrictID"), ("UnitType", "UnitTypeID"),
    ("Unit", "UnitID"), ("Rank", "RankID"), ("Designation", "DesignationID"),
    ("Employee", "EmployeeID"), ("Court", "CourtID"),
    ("CaseCategory", "CaseCategoryID"), ("GravityOffence", "GravityOffenceID"),
    ("CrimeHead", "CrimeHeadID"), ("CrimeSubHead", "CrimeSubHeadID"),
    ("CaseStatusMaster", "CaseStatusID"), ("CasteMaster", "caste_master_id"),
    ("ReligionMaster", "ReligionID"), ("OccupationMaster", "OccupationID"),
    ("CaseMaster", "CaseMasterID"), ("ComplainantDetails", "ComplainantID"),
    ("Victim", "VictimMasterID"), ("Accused", "AccusedMasterID"),
    ("ArrestSurrender", "ArrestSurrenderID"), ("ChargesheetDetails", "CSID"),
    ("ModelVersion", "ModelVersionID"), ("ModelInference", "InferenceID"),
    ("EntityGraph", "EntityID"), ("NetworkEdge", "EdgeID"),
    ("GangMembership", "GangMembershipID"), ("CrimeRiskScore", "RiskScoreID"),
    ("CrimePrediction", "PredictionID"), ("CrimeHotspot", "HotspotID"),
    ("CrimePattern", "PatternID"), ("CrimeEmbedding", "EmbeddingID"),
    ("AISummary", "SummaryID"), ("AlertHistory", "AlertID"),
    ("OfficerRecommendation", "RecommendationID"),
    ("SocialIndicator", "SocialIndicatorID"),
    ("WeatherIndicator", "WeatherIndicatorID"),
    ("EconomicIndicator", "EconomicIndicatorID"),
    # Phase 1.5 extensions (financial sub-graph + conversational demo data).
    ("FinancialAccount", "AccountID"), ("FinancialTransaction", "TransactionID"),
    ("TransactionLink", "LinkID"), ("ChatSession", "SessionID"),
    ("ChatMessage", "MessageID"), ("VoiceTranscript", "TranscriptID"),
]

ALL_TABLES = [
    # Phase 1.5 extension children first. NOTE: the RBAC tables (roles, users,
    # role_permissions, audit_logs) and SavedQuery are intentionally NOT
    # truncated — they hold seeded governance data that must survive reloads.
    "TransactionLink", "FinancialTransaction", "FinancialAccount",
    "VoiceTranscript", "ChatMessage", "ChatSession",
    "inv_arrestsurrenderaccused", "Inv_OccuranceTime", "ChargesheetDetails",
    "ArrestSurrender", "ActSectionAssociation", "Victim", "Accused",
    "ComplainantDetails", "CrimePatternCase", "CrimeEmbedding", "AISummary",
    "OfficerRecommendation", "AlertHistory", "ModelInference", "CrimeRiskScore",
    "CrimePrediction", "CrimeHotspot", "CrimePattern", "GangMembership",
    "NetworkEdge", "EntityGraph", "SocialIndicator", "WeatherIndicator",
    "EconomicIndicator", "CaseMaster", "CrimeHeadActSection", "Section", "Act",
    "Employee", "Court", "Unit", "UnitType", "CaseStatusMaster", "CrimeSubHead",
    "CrimeHead", "GravityOffence", "CaseCategory", "OccupationMaster",
    "ReligionMaster", "CasteMaster", "Designation", "Rank", "District",
    "State", "ModelVersion",
]


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cfg: GenConfig) -> None:
    t0 = time.time()
    _log(f"DRISHTI generator | seed={cfg.seed} firs={cfg.n_firs:,} "
         f"workers={cfg.workers}")
    conn = connect(cfg.dsn)
    try:
        cur = conn.cursor()
        if cfg.truncate_first:
            _log("Truncating target tables ...")
            truncate_all(cur, ALL_TABLES)
            conn.commit()

        _log("Phase 1/4: reference & organisational tables ...")
        ctx = load_reference(cur, cfg)
        conn.commit()
        _log(f"  districts={len(ctx.districts)} stations={len(ctx.stations)} "
             f"gangs={len(ctx.gangs)} offenders={len(ctx.offenders)}")

        _log("Phase 2/4: planning FIRs ...")
        planner = cases.Planner(cfg, ctx)
        plans = planner.plan()
        _log(f"  planned {len(plans):,} FIRs")

        _log("Phase 3/4: CaseMaster + children ...")
        cases.load_casemaster(cur, cfg, ctx, plans)
        conn.commit()
        _log(f"  CaseMaster loaded ({len(plans):,})")

        totals = _expand_children(cfg, ctx, plans)
        _log("  children loaded: " +
             ", ".join(f"{k}={v:,}" for k, v in totals.items()))

        if cfg.load_intelligence:
            _log("Phase 4/4: AI / intelligence layer ...")
            icounts = generate_intelligence(conn, cfg, ctx)
            _log("  intelligence: " +
                 ", ".join(f"{k}={v:,}" for k, v in icounts.items()))
        else:
            _log("Phase 4/4: skipped (intelligence disabled)")

        _log("Resetting identity sequences ...")
        for table, col in IDENTITY_TABLES:
            try:
                reset_identity(cur, table, col)
            except Exception as exc:  # table may be empty / absent
                _log(f"  skip {table}: {exc}")
        conn.commit()

        _log("ANALYZE ...")
        old_iso = conn.isolation_level
        conn.set_isolation_level(0)
        cur.execute("ANALYZE")
        conn.set_isolation_level(old_iso)
    finally:
        conn.close()
    _log(f"Done in {time.time() - t0:.1f}s")


def _expand_children(cfg: GenConfig, ctx: Context, plans: List[tuple]) -> Dict[str, int]:
    chunks = _split(plans, cfg.workers)
    totals: Dict[str, int] = {}

    if cfg.workers <= 1:
        for cid, chunk in enumerate(chunks):
            _accumulate(totals, cases.run_chunk(cid, chunk, cfg, ctx, cfg.dsn))
        return totals

    with ProcessPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {
            pool.submit(cases.run_chunk, cid, chunk, cfg, ctx, cfg.dsn): cid
            for cid, chunk in enumerate(chunks) if chunk
        }
        for fut in as_completed(futures):
            cid = futures[fut]
            _accumulate(totals, fut.result())
            _log(f"  worker chunk {cid} complete")
    return totals


def _split(items: List, n: int) -> List[List]:
    n = max(1, n)
    size = (len(items) + n - 1) // n
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


def _accumulate(totals: Dict[str, int], counts: Dict[str, int]) -> None:
    for k, v in counts.items():
        totals[k] = totals.get(k, 0) + v
