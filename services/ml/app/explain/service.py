"""Explainability service: reconstruct the evidence chain for any AI row, expose
model calibration + drift, and audit contract conformance."""
from __future__ import annotations

from typing import Any, Optional

from .. import db
from ..contracts import AiResult
from .schemas import (ContractAuditResponse, ContractRoute, DriftPoint, ExplainResponse,
                      FactorBar, GaugeBars, InferenceAudit, ModelCard, ModelDetailResponse,
                      ModelInfo, ModelsResponse)

UNSUPPORTED = object()   # sentinel: table not explainable

_SEV_CONF = {"critical": 0.95, "high": 0.8, "medium": 0.6, "low": 0.4, "info": 0.3}


# ---- shared lookups --------------------------------------------------------
def _model_info(conn, mv_id: Optional[int]) -> Optional[ModelInfo]:
    if mv_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ModelVersionID","ModelName","Version","ModelType"::text,"Framework",'
            '"Status"::text,"Hyperparameters","Metrics","TrainedAt"::text,"DeployedAt"::text '
            'FROM "ModelVersion" WHERE "ModelVersionID"=%s', (mv_id,))
        r = cur.fetchone()
    if not r:
        return None
    return ModelInfo(model_version_id=int(r[0]), model_name=r[1], version=r[2], model_type=r[3],
                     framework=r[4], status=r[5], hyperparameters=r[6] or {}, metrics=r[7] or {},
                     trained_at=r[8], deployed_at=r[9])


def _find_inference(conn, mv_id: Optional[int], ref_table: Optional[str] = None,
                    ref_id: Optional[str] = None, case_master_id: Optional[int] = None) -> Optional[InferenceAudit]:
    if mv_id is None:
        return None

    def _q(where: str, args: tuple, matched_by: str):
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "InferenceID","Input","Output","Confidence","LatencyMs","InferenceAt"::text '
                'FROM "ModelInference" WHERE ' + where +
                ' ORDER BY "InferenceAt" DESC LIMIT 1', args)
            r = cur.fetchone()
        if not r:
            return None
        return InferenceAudit(inference_id=int(r[0]), matched_by=matched_by,
                              input_snapshot=r[1] or {}, output=r[2] or {},
                              confidence=float(r[3]) if r[3] is not None else None,
                              latency_ms=int(r[4]) if r[4] is not None else None,
                              inferred_at=r[5])

    if ref_table and ref_id:
        got = _q('"ModelVersionID"=%s AND "RefTable"=%s AND "RefID"=%s',
                 (mv_id, ref_table, ref_id), "exact")
        if got:
            return got
    if case_master_id:
        got = _q('"ModelVersionID"=%s AND "CaseMasterID"=%s', (mv_id, case_master_id), "case+model")
        if got:
            return got
    return _q('"ModelVersionID"=%s', (mv_id,), "model_version")


def _clean(ids: list[Optional[str]]) -> list[str]:
    out: list[str] = []
    for x in ids:
        if x and x not in out:
            out.append(x)
    return out


# ---- per-table explainers --------------------------------------------------
def _explain_risk(conn, rid: int) -> Optional[ExplainResponse]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "RiskScoreID","CaseMasterID","UnitID","DistrictID","AccusedMasterID",'
            '"ModelVersionID","RiskScore","RiskLevel"::text,"Factors","ValidFrom"::text '
            'FROM "CrimeRiskScore" WHERE "RiskScoreID"=%s', (rid,))
        r = cur.fetchone()
    if not r:
        return None
    fac = r[8] or {}
    entity_id = fac.get("entity_id")
    mv_id = r[5]
    model = _model_info(conn, mv_id)
    inf = _find_inference(conn, mv_id, ref_table="EntityGraph",
                          ref_id=str(entity_id) if entity_id is not None else None,
                          case_master_id=r[1])
    gauge = GaugeBars(score=float(r[6]), level=r[7], band=fac.get("risk_band"),
                      class_probabilities=fac.get("probs", {}) or {},
                      factors=[FactorBar(**f) for f in fac.get("top_factors", [])])
    subject = {"risk_score": float(r[6]), "risk_level": r[7], "risk_band": fac.get("risk_band"),
               "offender": fac.get("offender"),
               "scope": {"accused_master_id": r[4], "district_id": r[3], "unit_id": r[2],
                         "case_master_id": r[1]}, "valid_from": r[9]}
    srcs = _clean([f"CrimeRiskScore:{rid}",
                   f"EntityGraph:{entity_id}" if entity_id is not None else None,
                   f"Accused:{r[4]}" if r[4] else None,
                   f"District:{r[3]}" if r[3] else None,
                   f"ModelInference:{inf.inference_id}" if inf else None,
                   f"ModelVersion:{mv_id}" if mv_id else None])
    note = (f"Re-scoring {srcs[1] if len(srcs) > 1 else 'the offender'} with "
            f"{model.model_name + '@' + model.version if model else 'the model'} on the stored "
            f"feature snapshot reproduces this {r[7].upper()} score (same inputs + version -> same output).")
    label = f"{model.model_name}@{model.version}" if model else f"unknown@{mv_id}"
    result = AiResult(
        answer=f"Evidence chain for CrimeRiskScore {rid}: {fac.get('risk_band', r[7])} risk, "
               f"{len(gauge.factors)} signed factors, reproducible from a stored inference snapshot.",
        confidence=float(r[6]), source_record_ids=srcs, reasoning_summary=note, model_version=label)
    return ExplainResponse(result=result, table="CrimeRiskScore", record_id=str(rid),
                           subject=subject, model=model, inference=inf, gauge_bars=gauge,
                           source_record_ids=srcs, reproducible=inf is not None, reproducibility_note=note)


def _explain_prediction(conn, pid: int) -> Optional[ExplainResponse]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "PredictionID","ModelVersionID","DistrictID","UnitID","CrimeHeadID",'
            '"PredictionStart"::text,"PredictionEnd"::text,"PredictedCount","Probability",'
            '"Confidence","Features" FROM "CrimePrediction" WHERE "PredictionID"=%s', (pid,))
        r = cur.fetchone()
    if not r:
        return None
    feats = r[10] or {}
    mv_id = r[1]
    model = _model_info(conn, mv_id)
    inf = _find_inference(conn, mv_id, ref_table="CrimePrediction")
    subject = {"layer": feats.get("layer"), "predicted_count": float(r[7]) if r[7] is not None else None,
               "probability": float(r[8]) if r[8] is not None else None,
               "confidence": float(r[9]) if r[9] is not None else None,
               "window": {"start": r[5], "end": r[6]}, "district_id": r[2],
               "crime_head_id": r[4], "features": feats}
    contribs = feats.get("contributing_models") or []
    srcs = _clean([f"CrimePrediction:{pid}",
                   f"District:{r[2]}" if r[2] else None,
                   f"CrimeHead:{r[4]}" if r[4] else None]
                  + [f"ModelVersion:{c.get('model_version_id')}" for c in contribs if c.get("model_version_id")]
                  + [f"ModelInference:{inf.inference_id}" if inf else None,
                     f"ModelVersion:{mv_id}" if mv_id else None])
    note = ("Reproducible: the batch inputs are in the ModelInference snapshot and every per-cell "
            "input (features / contributing models + confidence) is stored on the CrimePrediction row.")
    label = f"{model.model_name}@{model.version}" if model else f"unknown@{mv_id}"
    conf = float(r[9]) if r[9] is not None else 0.5
    result = AiResult(
        answer=f"Evidence chain for CrimePrediction {pid}: '{feats.get('layer')}' layer forecast, "
               f"contributing models + confidence recorded on the row.",
        confidence=conf, source_record_ids=srcs, reasoning_summary=note, model_version=label)
    return ExplainResponse(result=result, table="CrimePrediction", record_id=str(pid),
                           subject=subject, model=model, inference=inf,
                           source_record_ids=srcs, reproducible=True, reproducibility_note=note)


def _explain_summary(conn, sid: int) -> Optional[ExplainResponse]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "SummaryID","CaseMasterID","ModelVersionID","SummaryText","Confidence",'
            '"GeneratedAt"::text FROM "AISummary" WHERE "SummaryID"=%s', (sid,))
        r = cur.fetchone()
    if not r:
        return None
    mv_id = r[2]
    model = _model_info(conn, mv_id)
    inf = _find_inference(conn, mv_id, ref_table="AISummary", ref_id=str(sid), case_master_id=r[1])
    cited = (inf.input_snapshot.get("source_record_ids") if inf else None) or []
    subject = {"case_master_id": r[1], "confidence": float(r[4]) if r[4] is not None else None,
               "summary_text": r[3], "generated_at": r[5], "cited_record_count": len(cited)}
    srcs = _clean([f"AISummary:{sid}", f"CaseMaster:{r[1]}" if r[1] else None]
                  + list(cited)
                  + [f"ModelInference:{inf.inference_id}" if inf else None,
                     f"ModelVersion:{mv_id}" if mv_id else None])
    note = (f"Ontology-Augmented Generation: this brief is regenerated deterministically from the "
            f"{len(cited)} cited source records; every claim carries an inline citation, so it is "
            "fully reproducible and contestable.")
    label = f"{model.model_name}@{model.version}" if model else f"unknown@{mv_id}"
    result = AiResult(
        answer=f"Evidence chain for AISummary {sid}: cited from {len(cited)} linked records (OAG), "
               "no uncited claim.",
        confidence=float(r[4]) if r[4] is not None else 0.7,
        source_record_ids=srcs, reasoning_summary=note, model_version=label)
    return ExplainResponse(result=result, table="AISummary", record_id=str(sid), subject=subject,
                           model=model, inference=inf, source_record_ids=srcs,
                           reproducible=inf is not None, reproducibility_note=note)


def _explain_alert(conn, aid: int) -> Optional[ExplainResponse]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "AlertID","AlertType"::text,"Severity"::text,"Title","Message","CaseMasterID",'
            '"DistrictID","UnitID","EntityID","ModelVersionID","Payload","Status"::text '
            'FROM "AlertHistory" WHERE "AlertID"=%s', (aid,))
        r = cur.fetchone()
    if not r:
        return None
    mv_id = r[9]
    model = _model_info(conn, mv_id)
    inf = _find_inference(conn, mv_id, ref_table="AlertHistory", case_master_id=r[5])
    payload = r[10] or {}
    subject = {"alert_type": r[1], "severity": r[2], "title": r[3], "message": r[4],
               "status": r[11], "scope": {"case_master_id": r[5], "district_id": r[6],
                                          "unit_id": r[7], "entity_id": r[8]}, "payload": payload}
    srcs = _clean([f"AlertHistory:{aid}", f"CaseMaster:{r[5]}" if r[5] else None,
                   f"District:{r[6]}" if r[6] else None, f"EntityGraph:{r[8]}" if r[8] else None,
                   f"ModelInference:{inf.inference_id}" if inf else None,
                   f"ModelVersion:{mv_id}" if mv_id else None])
    note = ("Reproducible: the detector's inputs are in the ModelInference snapshot and the "
            "threshold/evidence detail is stored in the alert Payload.")
    label = f"{model.model_name}@{model.version}" if model else f"unknown@{mv_id}"
    result = AiResult(
        answer=f"Evidence chain for AlertHistory {aid}: {r[2]} '{r[1]}' alert with model provenance.",
        confidence=_SEV_CONF.get(r[2], 0.5), source_record_ids=srcs,
        reasoning_summary=note, model_version=label)
    return ExplainResponse(result=result, table="AlertHistory", record_id=str(aid), subject=subject,
                           model=model, inference=inf, source_record_ids=srcs,
                           reproducible=inf is not None, reproducibility_note=note)


_EXPLAINERS = {"crimeriskscore": _explain_risk, "crimeprediction": _explain_prediction,
               "aisummary": _explain_summary, "alerthistory": _explain_alert}


def explain_row(table: str, record_id: int):
    fn = _EXPLAINERS.get(table.strip().lower())
    if fn is None:
        return UNSUPPORTED
    with db.ro_conn() as conn:
        return fn(conn, record_id)


# ---- model explainability (calibration + drift) ----------------------------
def model_explainability() -> ModelsResponse:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT mv."ModelVersionID", mv."ModelName", mv."Version", mv."ModelType"::text, '
                'mv."Framework", mv."Status"::text, mv."Metrics", '
                'COUNT(mi."InferenceID"), AVG(mi."Confidence")::float, '
                'MIN(mi."InferenceAt")::text, MAX(mi."InferenceAt")::text '
                'FROM "ModelVersion" mv '
                'LEFT JOIN "ModelInference" mi ON mi."ModelVersionID"=mv."ModelVersionID" '
                'GROUP BY 1,2,3,4,5,6,7 ORDER BY mv."ModelVersionID"')
            rows = cur.fetchall()
    cards = [ModelCard(model_version_id=int(r[0]), model_name=r[1], version=r[2], model_type=r[3],
                       framework=r[4], status=r[5], calibration=r[6] or {}, inferences=int(r[7]),
                       mean_confidence=round(float(r[8]), 4) if r[8] is not None else None,
                       first_inference=r[9], last_inference=r[10]) for r in rows]
    calibrated = sum(1 for c in cards if c.calibration)
    result = AiResult(
        answer=f"{len(cards)} model version(s); {calibrated} carry calibration metrics.",
        confidence=1.0,
        source_record_ids=[f"ModelVersion:{c.model_version_id}" for c in cards],
        reasoning_summary="Per-ModelVersion calibration (stored Metrics) + inference volume/confidence "
                          "from the audit log, for the Model Explainability sub-page.",
        model_version="drishti-explain@1.0.0")
    return ModelsResponse(result=result, count=len(cards), models=cards)


def model_detail(mv_id: int) -> Optional[ModelDetailResponse]:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ModelVersionID","ModelName","Version","ModelType"::text,"Framework",'
                '"Status"::text,"Metrics" FROM "ModelVersion" WHERE "ModelVersionID"=%s', (mv_id,))
            r = cur.fetchone()
            if not r:
                return None
            cur.execute(
                'SELECT to_char(date_trunc(\'month\', "InferenceAt"),\'YYYY-MM\'), COUNT(*), '
                'AVG("Confidence")::float FROM "ModelInference" WHERE "ModelVersionID"=%s '
                'GROUP BY 1 ORDER BY 1', (mv_id,))
            drift_rows = cur.fetchall()
            cur.execute('SELECT COUNT(*), AVG("Confidence")::float FROM "ModelInference" '
                        'WHERE "ModelVersionID"=%s', (mv_id,))
            agg = cur.fetchone()
    drift = [DriftPoint(period=d[0], count=int(d[1]),
                        mean_confidence=round(float(d[2]), 4) if d[2] is not None else None)
             for d in drift_rows]
    # drift flag from confidence trajectory vs overall mean
    confs = [d.mean_confidence for d in drift if d.mean_confidence is not None]
    flag = "insufficient"
    if len(confs) >= 2:
        overall = sum(confs) / len(confs)
        last = confs[-1]
        flag = ("rising_confidence" if last > overall * 1.1 else
                "falling_confidence" if last < overall * 0.9 else "stable")
    card = ModelCard(model_version_id=int(r[0]), model_name=r[1], version=r[2], model_type=r[3],
                     framework=r[4], status=r[5], calibration=r[6] or {},
                     inferences=int(agg[0]), mean_confidence=round(float(agg[1]), 4) if agg[1] is not None else None,
                     first_inference=drift[0].period if drift else None,
                     last_inference=drift[-1].period if drift else None)
    notes = ("Calibration = the metrics recorded when the model version was registered "
             "(e.g. accuracy / macro-F1 / Brier / ECE for classifiers). Drift = inference "
             "volume and mean confidence per month from the audit log; a sustained confidence "
             "shift flags model drift for review.")
    result = AiResult(
        answer=f"{card.model_name}@{card.version}: {card.inferences} inference(s), "
               f"drift={flag}, {'calibrated' if card.calibration else 'no stored calibration'}.",
        confidence=card.mean_confidence if card.mean_confidence is not None else 1.0,
        source_record_ids=[f"ModelVersion:{mv_id}", "ModelInference"],
        reasoning_summary=notes, model_version=f"{card.model_name}@{card.version}")
    return ModelDetailResponse(result=result, model=card, calibration=card.calibration,
                               drift=drift, drift_flag=flag, notes=notes)


# ---- live contract audit ---------------------------------------------------
def contract_audit() -> ContractAuditResponse:
    from ..contracts import AiResult as _AiResult
    from pydantic import BaseModel
    from ..main import app  # lazy import to avoid a circular import at module load

    def _via(model) -> str:
        if model is _AiResult:
            return "direct"
        if isinstance(model, type) and issubclass(model, BaseModel):
            for fname, field in model.model_fields.items():
                if field.annotation is _AiResult:
                    return f"via '{fname}'"
        return "MISSING"

    prefixes = ("/graph", "/geo", "/analytics", "/risk", "/cases", "/money", "/forecast",
                "/demo", "/explain", "/chat")
    # Plain OPERATIONAL-DATA resources (Case/Entity explorers, raw map points,
    # community/entity lists, chat history). These are NOT model outputs — they
    # are raw reads documented to NOT wear the AiResult contract — so the audit
    # exempts them, just as it exempts its own /explain/contract route. Every
    # actual AI/analytics route still MUST embed an AiResult.
    exempt = {
        "/cases", "/cases/filters", "/cases/{case_id}/detail", "/cases/{case_id}/network",
        "/cases/{case_id}/evidence",
        "/geo/points", "/geo/stations", "/geo/case-links",
        # Phase 9 jurisdiction/boundary endpoints are raw OPERATIONAL geodata +
        # data-quality workflow (GeoJSON boundaries, containment scan/issues,
        # reviewed reassignment, freshness) — not model outputs, so they are
        # exempt like the other raw geo reads above. The forecast's own
        # /forecast/freshness DOES carry an AiResult.
        "/geo/boundaries/{level}", "/geo/db-boundaries/{level}", "/geo/sho-regions",
        "/geo/jurisdiction/freshness", "/geo/jurisdiction/issues",
        "/geo/jurisdiction/scan", "/geo/jurisdiction/reassign",
        "/graph/entities", "/graph/entities/{entity_id}",
        "/graph/communities/list", "/graph/communities/{community_id}/subgraph",
        "/chat/sessions", "/chat/sessions/{session_id}",
        "/chat/translate",   # a mechanical EN<->KN utility for PDF export, not an AI answer
        # Command Center caseload pipeline + geo date-coverage + graph path-finder
        # seed list (added with the caseload / geospatial / graph enhancement).
        # These are raw OPERATIONAL reads — present-state lifecycle-stage counts,
        # dataset min/max-date metadata, and ready-made connected entity pairs for
        # a one-click demo — NOT model/analytic outputs, so they are exempt exactly
        # like the raw reads above (/cases, /geo/points, /graph/entities).
        "/cases/caseload", "/geo/coverage", "/graph/path/suggestions",
    }
    routes: list[ContractRoute] = []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith(prefixes) or path.startswith("/explain/contract") or path in exempt:
            continue
        rm = getattr(r, "response_model", None)
        via = _via(rm) if rm else "NO_RESPONSE_MODEL"
        routes.append(ContractRoute(
            path=path, methods=",".join(sorted(getattr(r, "methods", []) or [])),
            response_model=rm.__name__ if rm else None,
            conforms=via not in ("MISSING", "NO_RESPONSE_MODEL"), via=via))
    routes.sort(key=lambda x: x.path)
    conforming = sum(1 for x in routes if x.conforms)
    result = AiResult(
        answer=f"{conforming}/{len(routes)} AI routes conform to the AiResult contract.",
        confidence=1.0 if conforming == len(routes) else round(conforming / max(1, len(routes)), 4),
        source_record_ids=[], reasoning_summary="Live introspection of every AI route's response "
        "model for the {answer,confidence,source_record_ids,reasoning_summary,model_version} contract.",
        model_version="drishti-explain@1.0.0")
    return ContractAuditResponse(result=result, total=len(routes), conforming=conforming,
                                 non_conforming=len(routes) - conforming, routes=routes)
