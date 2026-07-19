"""FastAPI router for the Phase-15 admin/governance console.

Reads require an admin_read role (supervisor + super_admin); configuration
changes require admin_write (super_admin) AND the hackathon write guard
(localhost + synthetic DB). Everything is synthetic-demo metadata; retention and
legal-hold are non-destructive.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..intake.guards import require_write_allowed
from . import permissions, service
from .permissions import require_admin_read, require_admin_write
from .schemas import (AdminStatus, AuditSearchResponse, AuthorizationMatrix, FeatureFlagUpdate,
                      LegalHoldCreate, LegalHoldOut, ModelReviewListResponse, ModelReviewUpsert,
                      QueuesResponse, ReconciliationResponse, RepairRequest, RepairResult,
                      RetentionOverview, RetentionPolicyOut, RetentionPolicyUpsert, RlsStatus,
                      SavedFilterCreate, SavedFilterOut, SourceSystemListResponse, UnitListResponse,
                      UsageResponse)

router = APIRouter(prefix="/admin", tags=["admin"])


# --- status / indicators / identity ----------------------------------------
@router.get("/status", response_model=AdminStatus)
def status(_role: str = Depends(require_admin_read)):
    return service.admin_status()


@router.get("/rls-status", response_model=RlsStatus)
def rls_status(_role: str = Depends(require_admin_read)):
    return service.rls_status()


@router.get("/identity", response_model=AuthorizationMatrix)
def identity(role: str = Depends(require_admin_read)):
    return service.identity_matrix(role)


# --- units / stations / source systems --------------------------------------
@router.get("/units", response_model=UnitListResponse)
def units(_role: str = Depends(require_admin_read)):
    return service.list_units()


@router.get("/source-systems", response_model=SourceSystemListResponse)
def source_systems(_role: str = Depends(require_admin_read)):
    return service.list_source_systems()


# --- source reconciliation + repair -----------------------------------------
@router.get("/reconciliation", response_model=ReconciliationResponse)
def reconciliation(_role: str = Depends(require_admin_read)):
    return service.reconciliation()


@router.post("/reconciliation/repair", response_model=RepairResult)
def reconciliation_repair(body: RepairRequest, request: Request,
                          role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    return service.repair_import(body.ingestion_job_id, body.source_record_ids,
                                 body.reason, body.actor or f"demo.{role}")


# --- audit search / export ---------------------------------------------------
@router.get("/audit", response_model=AuditSearchResponse)
def audit_search(action: Optional[str] = Query(None), resource: Optional[str] = Query(None),
                 actor: Optional[str] = Query(None), text: Optional[str] = Query(None),
                 since: Optional[str] = Query(None), until: Optional[str] = Query(None),
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                 _role: str = Depends(require_admin_read)):
    return service.search_audit(action, resource, actor, text, since, until, page, page_size)


@router.get("/audit/export")
def audit_export(fmt: str = Query("json", pattern="^(json|csv)$"),
                 action: Optional[str] = Query(None), resource: Optional[str] = Query(None),
                 actor: Optional[str] = Query(None), text: Optional[str] = Query(None),
                 since: Optional[str] = Query(None), until: Optional[str] = Query(None),
                 role: str = Depends(require_admin_read)):
    rows = service.export_audit_rows(action, resource, actor, text, since, until)
    if fmt == "json":
        return {"count": len(rows), "items": rows}
    # CSV export (server-side authorised).
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["audit_event_id", "occurred_at", "actor", "actor_role", "action",
                     "resource", "resource_id"])
    for r in rows:
        writer.writerow([r["audit_event_id"], r["occurred_at"], r["actor"], r["actor_role"],
                         r["action"], r["resource"], r["resource_id"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit_export.csv"})


# --- retention / legal hold (non-destructive) --------------------------------
@router.get("/retention", response_model=RetentionOverview)
def retention(_role: str = Depends(require_admin_read)):
    return service.retention_overview()


@router.post("/retention/policies", response_model=RetentionPolicyOut)
def upsert_retention_policy(body: RetentionPolicyUpsert, request: Request,
                            role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    return service.upsert_retention_policy(body, body.actor or f"demo.{role}")


@router.get("/legal-holds", response_model=list[LegalHoldOut])
def legal_holds(_role: str = Depends(require_admin_read)):
    return service.retention_overview()["legal_holds"]


@router.post("/legal-holds", response_model=LegalHoldOut)
def place_legal_hold(body: LegalHoldCreate, request: Request,
                     role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    return service.place_legal_hold(body.subject_kind, body.subject_ref_id, body.reason,
                                    body.actor or f"demo.{role}")


@router.post("/legal-holds/{legal_hold_id}/release", response_model=LegalHoldOut)
def release_legal_hold(legal_hold_id: int, request: Request,
                       role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    out = service.release_legal_hold(legal_hold_id, f"demo.{role}")
    if out is None:
        raise HTTPException(status_code=404, detail=f"Active legal hold {legal_hold_id} not found.")
    return out


# --- model lifecycle / review-due / drift ------------------------------------
@router.get("/models", response_model=ModelReviewListResponse)
def models(_role: str = Depends(require_admin_read)):
    return service.model_reviews()


@router.post("/models/{model_version_id}/review", response_model=ModelReviewListResponse)
def review_model(model_version_id: int, body: ModelReviewUpsert, request: Request,
                 role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    try:
        service.upsert_model_review(model_version_id, body.review_kind, body.status,
                                    body.findings, body.drift_signal, body.actor or f"demo.{role}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return service.model_reviews()


# --- queues (no OCR/extraction queue) ----------------------------------------
@router.get("/queues", response_model=QueuesResponse)
def queues(_role: str = Depends(require_admin_read)):
    return service.queues()


# --- usage / budgets / feature flags -----------------------------------------
@router.get("/usage", response_model=UsageResponse)
def usage(_role: str = Depends(require_admin_read)):
    return service.usage()


@router.post("/feature-flags/{key}")
def set_feature_flag(key: str, body: FeatureFlagUpdate, request: Request,
                     role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    out = service.set_feature_flag(key, body.enabled, body.actor or f"demo.{role}")
    if out is None:
        raise HTTPException(status_code=404, detail=f"Feature flag '{key}' not found.")
    return out


# --- saved filters / report templates ----------------------------------------
@router.get("/saved-filters")
def saved_filters(scope: Optional[str] = Query(None),
                  x_demo_actor: Optional[str] = Header(default=None),
                  role: str = Depends(require_admin_read)):
    actor = (x_demo_actor or f"demo.{role}").strip()
    return service.list_saved_filters(actor, scope)


@router.post("/saved-filters", response_model=SavedFilterOut)
def create_saved_filter(body: SavedFilterCreate, request: Request,
                        x_demo_actor: Optional[str] = Header(default=None),
                        role: str = Depends(require_admin_read)):
    require_write_allowed(request)
    actor = (body.actor or x_demo_actor or f"demo.{role}").strip()
    return service.create_saved_filter(actor, body.scope, body.name, body.filter_json, body.is_shared)


@router.delete("/saved-filters/{saved_filter_id}")
def delete_saved_filter(saved_filter_id: int, request: Request,
                        x_demo_actor: Optional[str] = Header(default=None),
                        role: str = Depends(require_admin_read)):
    require_write_allowed(request)
    actor = (x_demo_actor or f"demo.{role}").strip()
    ok = service.delete_saved_filter(saved_filter_id, actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved filter not found for this actor.")
    return {"deleted": True, "saved_filter_id": saved_filter_id}


@router.get("/report-templates")
def report_templates(role: str = Depends(require_admin_read)):
    return {"items": service.list_report_templates(role)}
