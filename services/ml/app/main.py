"""DRISHTI ML / analytics FastAPI service (Phase B0 scaffold).

Endpoints:
  GET  /health          — DB connectivity + extension availability
  POST /demo/risk-score — end-to-end proof: a typed CrimeRiskScore write + a
                          ModelInference audit row under a valid ModelVersion,
                          returned as the shared AiResult contract.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit, db, matviews, models, readiness
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
from .intake.router import router as intake_router
from .identity.router import router as identity_router
from .evidence.router import router as evidence_router
from .casework.router import router as casework_router
from .imports.router import router as imports_router
from .governance.router import router as governance_router
from .workload.router import router as workload_router
from .search.router import router as search_router
from .internal.router import router as internal_router
from .stream.router import router as stream_router
from .predict.router import router as predict_router
from .admin.router import router as admin_router
from .org.router import router as org_router
from .scenarios.router import router as scenarios_router
from .performance.router import router as performance_router
from .investigate.router import router as investigate_router
from .livefeed.router import router as livefeed_router
from .notifications.router import router as notifications_router
from .reports.router import router as reports_router
from .rag.router import router as rag_router
from .board.router import router as board_router
from .disaster.router import router as disaster_router
from .guards import HonestyMiddleware
from .hardening import (BodySizeLimitMiddleware, RateLimitMiddleware,
                        install_error_handlers, masked_db_target,
                        verify_hackathon_startup)
from .gateway_enforcement import GatewayContextEnforcementMiddleware
from .obs import AccessLogMiddleware, configure_logging
from .request_context import RequestContextMiddleware

REQUIRED_EXTENSIONS = ("postgis", "vector", "pg_trgm")
OPTIONAL_EXTENSIONS = ("pgrouting",)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Install the structured-log handler (no-op formatter until a line is emitted).
    configure_logging()
    # Phase 3: refuse to start hackathon mode against a non-synthetic database,
    # and make the (masked) DB target obvious at boot so a mis-routed
    # DATABASE_URL cannot silently point the demo at the wrong database.
    verify_hackathon_startup()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# API errors must never return SQL, stack traces or credentials.
install_error_handlers(app)

# Middleware execution order is the REVERSE of registration (last added is
# outermost). Target order, outermost -> innermost:
#   AccessLog -> CORS -> GatewayEnforcement -> RequestContext -> BodySizeLimit
#   -> RateLimit -> Honesty -> routes
# GatewayEnforcement is placed just inside CORS (so preflight still works) and
# just outside RequestContext, so it can verify the signed context and rewrite
# the trusted role BEFORE the request context + role gates read it.
app.add_middleware(HonestyMiddleware)          # innermost of the custom stack
app.add_middleware(RateLimitMiddleware)        # conservative per-IP fixed window
app.add_middleware(BodySizeLimitMiddleware)    # reject oversized bodies (413)
app.add_middleware(RequestContextMiddleware)   # request id + demo actor for audit
# Deployed trust boundary (Part D items 10/12): verify the gateway/service signed
# context and inject the server-trusted role. OFF by default (no-op) so local dev
# and tests are unaffected; the deployed AppSail sets DRISHTI_REQUIRE_GATEWAY_CONTEXT.
app.add_middleware(GatewayContextEnforcementMiddleware)
# CORS restricted to localhost + the exact configured demo origin (no wildcard).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Role", "X-Request-ID",
                   "X-Demo-Actor", "X-Idempotency-Key", "If-Match",
                   "X-Disaster-District", "X-Disaster-Unit"],
    expose_headers=["X-Request-ID", "X-DRISHTI-Causation", "X-DRISHTI-Anonymity", "X-DRISHTI-Use"],
)
# Structured redacted access log — outermost so it records the final status +
# total latency. No-op unless DRISHTI_ACCESS_LOG_ENABLED=true (deployed only).
app.add_middleware(AccessLogMiddleware)
app.include_router(graph_router)
app.include_router(geo_router)
app.include_router(analytics_router)
app.include_router(risk_router)
app.include_router(cases_router)
app.include_router(money_router)
app.include_router(forecast_router)
app.include_router(explain_router)
app.include_router(chat_router)
app.include_router(intake_router)
app.include_router(identity_router)
app.include_router(evidence_router)
app.include_router(casework_router)
app.include_router(imports_router)
app.include_router(governance_router)
app.include_router(workload_router)
# Deployed Data Store full-text metadata search (case/FIR/person/evidence).
app.include_router(search_router)
# Internal service-to-service endpoints (require a signed gateway/service context).
app.include_router(internal_router)
# Scoped SSE channel (Part F item 1): a direct browser->AppSail stream guarded by
# a short-lived channel token + strict Origin (its own auth; see stream/router).
# OFF unless DRISHTI_STREAM_CHANNEL_ENABLED=true.
app.include_router(stream_router)
# Part G prediction runtime + ML/RAG placement + dispatch-policy introspection.
# Reads are open aggregate metadata; job submit/collect are role + write-guarded.
app.include_router(predict_router)
# Phase 15 — admin/governance console, notifications/work, reports, optional RAG.
app.include_router(admin_router)
# Prompt 20 Part B — organizational hierarchy (rank->role/scope) + SUPERADMIN
# credential/role provisioning. Scope is always derived server-side.
app.include_router(org_router)
# Prompt 20 Part A — synthetic crypto/dark-web/cross-jurisdiction scenario
# registry (additive fixtures; searchable; no live collection).
app.include_router(scenarios_router)
# Prompt 20 Part C — supervisor station/officer operational performance metrics
# (scoped server-side; distinct from the ML workload-band prediction).
app.include_router(performance_router)
# Prompt 20 Part D — case-scoped investigation assistant (thin orchestration over
# existing case summary/similar/identity/leads/timeline; sends cited objects to Board).
app.include_router(investigate_router)
# Prompt 20 Part E — Live Command Center committed-FIR event flow (idempotent
# projection/freshness; no person rescore, no auto-dispatch).
app.include_router(livefeed_router)
app.include_router(notifications_router)
app.include_router(reports_router)
app.include_router(rag_router)
# Phase 16 — Investigation Board (object-backed analytical canvas). Data Store-
# native persistence; Catalyst-authenticated authorization (role-gated).
app.include_router(board_router)
# Phase 17 — Emergency Response (disaster forecasting/readiness/allocation/
# evacuation). Data Store-native; synthetic disaster_coordinator role + district
# scope; no forecast auto-publishes an alert, auto-dispatches or declares safe.
app.include_router(disaster_router)


@app.get("/health", response_model=HealthReport)
def health() -> HealthReport:
    try:
        db_ok = db.ping()
        installed = db.installed_extensions()
    except Exception:  # noqa: BLE001
        # Never echo the raw driver error (it can contain the DB host/identifiers).
        return HealthReport(
            status="degraded", app=settings.app_name, version=settings.app_version,
            database=False, extensions={}, detail="database unavailable",
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


@app.get("/health/live")
def health_live() -> dict:
    """Liveness probe (Catalyst AppSail).

    Reports only that the process is up and serving. It performs NO external
    dependency checks on purpose: a transient RDS/Data-Store/AWS outage must
    never trip the liveness probe and trigger an AppSail restart loop.
    """
    return {"status": "live", "app": settings.app_name, "version": settings.app_version}


@app.get("/health/ready")
def health_ready(response: Response) -> dict:
    """Readiness probe (Catalyst AppSail) — Prompt 21 §G.2.

    Reports whether the service can serve on its DEPLOYED OPERATIONAL DATA PLANE
    (Catalyst Data Store / Stratus +, when enforced, the gateway auth secret).
    It FAILS (HTTP 503, ready=false) when a mandatory dependency is unavailable
    so a broken operational data plane can never read as ready.

    The AWS RDS ``DATABASE_URL`` is an ADVISORY analytics dependency only: it is
    probed for visibility but its absence never flips the service to not-ready.
    """
    result = readiness.current(settings)
    if not result.ready:
        response.status_code = 503
    payload = result.payload()
    payload["app"] = settings.app_name
    payload["version"] = settings.app_version
    return payload


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

        # 4b. append an audit event for the model run (same transaction) — no
        # secrets/narratives/PII, just ids + non-sensitive references.
        audit.record(audit.Action.MODEL_RUN, resource="model_inference",
                     resource_id=inf_id, conn=conn,
                     detail={"model_version_id": mv_id, "district_id": req.district_id,
                             "risk_level": level})

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
