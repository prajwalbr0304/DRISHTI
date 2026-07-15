"""ModelVersion / ModelInference helpers and typed intelligence writes.

Every AI write MUST go through these so it carries a ModelVersionID and leaves a
ModelInference audit row (doc 02 §10). All functions take an open read/write
connection (see db.rw_conn) so a write + its audit row commit atomically.
"""
from __future__ import annotations

from typing import Any, Optional

from psycopg2.extras import Json

# CrimeRiskScore.RiskLevel is risk_level_enum: low/medium/high/critical.
_RISK_LEVELS = ("low", "medium", "high", "critical")


def risk_level_for(score: float) -> str:
    if score < 0.25:
        return "low"
    if score < 0.5:
        return "medium"
    if score < 0.75:
        return "high"
    return "critical"


def get_or_create_model_version(
    conn,
    model_name: str,
    model_type: str,
    version: str,
    *,
    framework: Optional[str] = None,
    hyperparameters: Optional[dict] = None,
    metrics: Optional[dict] = None,
    status: str = "active",
    embedding_dim: Optional[int] = None,
) -> int:
    """Look up (ModelName, Version); create it if absent. Returns ModelVersionID.

    model_type must be a valid model_type_enum value (classification, regression,
    clustering, embedding, nlp, forecasting, anomaly_detection, graph).
    embedding_dim is stored on the row for embedding models (keeps EmbeddingDim
    in sync with the deployed encoder — doc 02 §5).
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ModelVersionID" FROM "ModelVersion" '
            'WHERE "ModelName" = %s AND "Version" = %s',
            (model_name, version),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            'INSERT INTO "ModelVersion" '
            '("ModelName","ModelType","Version","Framework","EmbeddingDim",'
            ' "Hyperparameters","Metrics","Status","DeployedAt") '
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now()) "
            'RETURNING "ModelVersionID"',
            (
                model_name,
                model_type,
                version,
                framework,
                embedding_dim,
                Json(hyperparameters or {}),
                Json(metrics or {}),
                status,
            ),
        )
        return int(cur.fetchone()[0])


def model_version_label(conn, model_version_id: int) -> str:
    """Return 'ModelName@Version' for the contract's model_version field."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ModelName","Version" FROM "ModelVersion" WHERE "ModelVersionID"=%s',
            (model_version_id,),
        )
        row = cur.fetchone()
        return f"{row[0]}@{row[1]}" if row else f"unknown@{model_version_id}"


def log_inference(
    conn,
    model_version_id: int,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    confidence: Optional[float] = None,
    case_master_id: Optional[int] = None,
    entity_type: Optional[str] = None,  # entity_type_enum or NULL (no 'case' member)
    ref_table: Optional[str] = None,
    ref_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> int:
    """Write a ModelInference audit row. Returns InferenceID."""
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "ModelInference" '
            '("ModelVersionID","EntityType","CaseMasterID","RefTable","RefID",'
            ' "Input","Output","Confidence","LatencyMs") '
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            'RETURNING "InferenceID"',
            (
                model_version_id,
                entity_type,
                case_master_id,
                ref_table,
                ref_id,
                Json(inputs),
                Json(outputs),
                confidence,
                latency_ms,
            ),
        )
        return int(cur.fetchone()[0])


def write_crime_risk_score(
    conn,
    model_version_id: int,
    *,
    risk_score: float,
    case_master_id: Optional[int] = None,
    unit_id: Optional[int] = None,
    district_id: Optional[int] = None,
    accused_master_id: Optional[int] = None,
    factors: Optional[dict] = None,
) -> tuple[int, str]:
    """Insert a typed CrimeRiskScore row. Returns (RiskScoreID, RiskLevel).

    Scope check mirrors the schema CHECK: at least one of case/unit/district must
    be set (accused is an additional offender-level dimension, Phase 9).
    """
    if not any([case_master_id, unit_id, district_id, accused_master_id]):
        raise ValueError("A CrimeRiskScore needs a case, unit, district or accused scope.")
    level = risk_level_for(risk_score)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CrimeRiskScore" '
            '("CaseMasterID","UnitID","DistrictID","AccusedMasterID","ModelVersionID",'
            ' "RiskScore","RiskLevel","Factors") '
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
            'RETURNING "RiskScoreID"',
            (
                case_master_id,
                unit_id,
                # district is required by the CHECK when others are null; keep it
                # explicit even if only accused is provided upstream.
                district_id,
                accused_master_id,
                model_version_id,
                round(float(risk_score), 5),
                level,
                Json(factors or {}),
            ),
        )
        return int(cur.fetchone()[0]), level
