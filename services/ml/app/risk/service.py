"""Risk service: read a stored offender score (or re-score on demand) and wrap
it in the AiResult contract with full provenance."""
from __future__ import annotations

from .. import db
from ..contracts import AiResult
from . import scoring
from .schemas import CalibrationResponse, RiskFactor, RiskResponse


def _to_response(row: dict, rescored: bool = False) -> RiskResponse:
    factors = row["factors"]
    band = factors.get("risk_band", "Low")
    probs = factors.get("probs", {})
    fac = [RiskFactor(**f) for f in factors.get("top_factors", [])]
    reasons = ", ".join(f"{f.label} {f.direction} risk" for f in fac[:3])
    result = AiResult(
        answer=f"{factors.get('offender', 'Offender')} risk assessed as {band} "
               f"(score {row['risk_score']:.2f}).",
        confidence=round(float(max(probs.values())) if probs else row["risk_score"], 4),
        source_record_ids=[f"EntityGraph:{row['entity_id']}",
                           f"CrimeRiskScore:{row.get('risk_score_id', '')}".rstrip(":"),
                           (f"Accused:{row['accused_master_id']}" if row.get("accused_master_id") else "Accused:unmapped")],
        reasoning_summary=(f"TabFM-family risk classification into 5 ordinal bands from "
                           f"offender features; top drivers: {reasons}. Decision support only."),
        model_version=f"{factors.get('model', 'drishti-tabfm')}@1.0.0",
    )
    return RiskResponse(
        result=result, entity_id=row["entity_id"], accused_master_id=row.get("accused_master_id"),
        offender_name=factors.get("offender"), district_id=row.get("district_id"),
        risk_band=band, risk_level=row["risk_level"], risk_score=row["risk_score"],
        class_probabilities=probs, factors=fac,
        model_version=f"{factors.get('model', 'drishti-tabfm')}@1.0.0",
        scored_at=row.get("scored_at"), rescored=rescored)


def get_by_accused(accused_id: int) -> RiskResponse | None:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "RiskScoreID","AccusedMasterID","DistrictID","RiskScore",'
                '"RiskLevel"::text,"Factors","ValidFrom" '
                'FROM "CrimeRiskScore" WHERE "AccusedMasterID"=%s '
                'ORDER BY "ValidFrom" DESC LIMIT 1', (accused_id,))
            r = cur.fetchone()
    if not r:
        return None
    factors = r[5] or {}
    row = {"risk_score_id": r[0], "accused_master_id": r[1], "district_id": r[2],
           "risk_score": float(r[3]), "risk_level": r[4], "factors": factors,
           "entity_id": factors.get("entity_id"), "scored_at": str(r[6]) if r[6] else None}
    return _to_response(row)


def get_by_entity(entity_id: int) -> RiskResponse | None:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "RiskScoreID","AccusedMasterID","DistrictID","RiskScore",'
                '"RiskLevel"::text,"Factors","ValidFrom" '
                'FROM "CrimeRiskScore" WHERE "Factors"->>\'entity_id\' = %s '
                'ORDER BY "ValidFrom" DESC LIMIT 1', (str(entity_id),))
            r = cur.fetchone()
    if not r:
        return None
    factors = r[5] or {}
    row = {"risk_score_id": r[0], "accused_master_id": r[1], "district_id": r[2],
           "risk_score": float(r[3]), "risk_level": r[4], "factors": factors,
           "entity_id": entity_id, "scored_at": str(r[6]) if r[6] else None}
    return _to_response(row)


def rescore_entity(entity_id: int) -> RiskResponse | None:
    with db.rw_conn() as conn:
        row = scoring.score_one(conn, entity_id)
    if not row:
        return None
    return _to_response(row, rescored=True)


def calibration() -> CalibrationResponse:
    with db.rw_conn() as conn:
        rep = scoring.calibration_report(conn)
    result = AiResult(
        answer=(f"Foundation {rep['foundation']['model']} acc={rep['foundation']['accuracy']} "
                f"vs baseline {rep['baseline']['model']} acc={rep['baseline']['accuracy']}; "
                f"{rep['agreement']:.0%} agreement."),
        confidence=round(float(rep["foundation"]["accuracy"]), 4),
        source_record_ids=["CrimeRiskScore", "EntityGraph"],
        reasoning_summary=("Held-out calibration: accuracy, macro-F1, Brier and ECE for the "
                           "TabFM-family model vs the gradient-boosted baseline."),
        model_version=f"{rep['foundation']['model']}@1.0.0",
    )
    return CalibrationResponse(result=result, n_train=rep["n_train"], n_test=rep["n_test"],
                              foundation=rep["foundation"], baseline=rep["baseline"],
                              agreement=rep["agreement"])
