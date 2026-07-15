"""DRISHTI ML / analytics FastAPI service (Phase B0 scaffold).

Endpoints:
  GET  /health          — DB connectivity + extension availability
  POST /demo/risk-score — end-to-end proof: a typed CrimeRiskScore write + a
                          ModelInference audit row under a valid ModelVersion,
                          returned as the shared AiResult contract.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, matviews, models
from .config import get_settings
from .contracts import AiResult, HealthReport
from .graph.router import router as graph_router
from .geo.router import router as geo_router
from .analytics.router import router as analytics_router
from .risk.router import router as risk_router
from .cases.router import router as cases_router
from .money.router import router as money_router
from .forecast.router import router as forecast_router
from .explain.router import router as explain_router
from .chat.router import router as chat_router
from .guards import HonestyMiddleware

REQUIRED_EXTENSIONS = ("postgis", "vector", "pg_trgm")
OPTIONAL_EXTENSIONS = ("pgrouting",)

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)
# Shared honesty guard: stamp aggregate/forecast responses with causation +
# k-anonymity headers (payload-level suppression/disclaimers live in the endpoints).
app.add_middleware(HonestyMiddleware)
# CORS for the Wave-C SPA (Vite dev/preview). Added last so it is the outermost
# layer and handles preflight before the honesty guard. Tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.include_router(graph_router)
app.include_router(geo_router)
app.include_router(analytics_router)
app.include_router(risk_router)
app.include_router(cases_router)
app.include_router(money_router)
app.include_router(forecast_router)
app.include_router(explain_router)
app.include_router(chat_router)


@app.get("/health", response_model=HealthReport)
def health() -> HealthReport:
    try:
        db_ok = db.ping()
        installed = db.installed_extensions()
    except Exception as exc:  # noqa: BLE001
        return HealthReport(
            status="degraded", app=settings.app_name, version=settings.app_version,
            database=False, extensions={}, detail=str(exc).strip(),
        )
    ext_flags = {
        name: (name in installed)
        for name in REQUIRED_EXTENSIONS + OPTIONAL_EXTENSIONS
    }
    required_ok = all(ext_flags[e] for e in REQUIRED_EXTENSIONS)
    status = "ok" if (db_ok and required_ok) else "degraded"
    detail = "" if status == "ok" else "missing required extension(s)"
    return HealthReport(
        status=status, app=settings.app_name, version=settings.app_version,
        database=db_ok, extensions=ext_flags, detail=detail,
    )


class RiskScoreRequest(BaseModel):
    district_id: int = Field(..., ge=1, description="District to score (area-level, decision support).")
    risk_score: float = Field(0.5, ge=0.0, le=1.0, description="Demo risk value in [0,1].")


@app.post("/demo/risk-score", response_model=AiResult)
def demo_risk_score(req: RiskScoreRequest) -> AiResult:
    """Proof-of-plumbing: typed write + audit row + matview refresh -> AiResult."""
    t0 = time.time()
    with db.rw_conn() as conn:
        # 1. validate the district exists (never invent scope)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "DistrictName" FROM "District" WHERE "DistrictID"=%s',
                (req.district_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"District {req.district_id} not found")
        district_name = row[0]

        # 2. register/lookup the model version
        mv_id = models.get_or_create_model_version(
            conn, model_name="drishti-risk-demo", model_type="classification",
            version="0.1.0", framework="scaffold",
            metrics={"note": "B0 plumbing demo, not a trained model"},
        )
        mv_label = models.model_version_label(conn, mv_id)

        # 3. typed write: CrimeRiskScore (+ explainability factors)
        factors = {"demo": True, "district": district_name, "input_score": req.risk_score}
        risk_id, level = models.write_crime_risk_score(
            conn, mv_id, risk_score=req.risk_score,
            district_id=req.district_id, factors=factors,
        )

        # 4. audit row (ModelInference) — EntityType NULL (no 'case'/'district' member)
        latency_ms = int((time.time() - t0) * 1000)
        inf_id = models.log_inference(
            conn, mv_id,
            inputs={"district_id": req.district_id, "risk_score": req.risk_score},
            outputs={"risk_score": req.risk_score, "risk_level": level, "risk_score_id": risk_id},
            confidence=req.risk_score, ref_table="District", ref_id=str(req.district_id),
            latency_ms=latency_ms,
        )

    # 5. refresh the dependent matview (own txn/connection)
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_district_risk_profile")

    return AiResult(
        answer=f"{district_name} area risk level assessed as {level.upper()} "
               f"(score {req.risk_score:.2f}).",
        confidence=req.risk_score,
        source_record_ids=[
            f"District:{req.district_id}",
            f"CrimeRiskScore:{risk_id}",
            f"ModelInference:{inf_id}",
        ],
        reasoning_summary="Demo area-level risk written as a typed row with a "
                          "ModelVersion and an audited inference; matview refreshed.",
        model_version=mv_label,
    )
