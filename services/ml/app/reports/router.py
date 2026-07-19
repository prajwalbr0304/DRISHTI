"""FastAPI router for Phase-15 report generation.

Generation/download require the hackathon write guard AND server-side export
authorization (role + case/unit/district scope), enforced in the service against
the template's AllowedRoles. Reports are built from structured DB fields only —
no OCR / no parsing of uploaded files.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..admin.permissions import has_permission, resolve_role
from ..intake.guards import require_write_allowed
from . import service
from .schemas import (ReportDownload, ReportGenerateRequest, ReportListResponse,
                      ReportSnapshotOut, ReportVerifyResult)

router = APIRouter(prefix="/reports", tags=["reports"])


def require_report_role(x_role: Optional[str] = Header(default=None)) -> str:
    role = resolve_role(x_role)
    if not has_permission(role, "report_generate"):
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot generate/read reports.")
    return role


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.TemplateNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, service.SubjectNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, service.ReportAuthError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, service.ScopeError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, service.ReportError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/templates")
def templates(role: str = Depends(require_report_role)):
    from ..admin.service import list_report_templates
    return {"items": list_report_templates(role)}


@router.get("", response_model=ReportListResponse)
def list_reports(scope_kind: Optional[str] = Query(None), scope_ref_id: Optional[str] = Query(None),
                 limit: int = Query(50, ge=1, le=200), _role: str = Depends(require_report_role)):
    return service.list_reports(scope_kind, scope_ref_id, limit)


@router.post("", response_model=ReportSnapshotOut)
def generate_report(body: ReportGenerateRequest, request: Request,
                    x_demo_actor: Optional[str] = Header(default=None),
                    role: str = Depends(require_report_role)):
    require_write_allowed(request)
    actor = (body.actor or x_demo_actor or f"demo.{role}").strip()
    try:
        return service.generate_report(body.template_code, body.scope_kind, body.scope_ref_id,
                                       body.title, body.filters, actor, role)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)


@router.get("/{report_snapshot_id}", response_model=ReportSnapshotOut)
def get_report(report_snapshot_id: int, _role: str = Depends(require_report_role)):
    out = service.get_report(report_snapshot_id)
    if out is None:
        raise HTTPException(status_code=404, detail=f"Report {report_snapshot_id} not found.")
    return out


@router.get("/{report_snapshot_id}/verify", response_model=ReportVerifyResult)
def verify_report(report_snapshot_id: int, _role: str = Depends(require_report_role)):
    out = service.verify_report(report_snapshot_id)
    if out is None:
        raise HTTPException(status_code=404, detail=f"Report {report_snapshot_id} not found.")
    return out


@router.post("/{report_snapshot_id}/download", response_model=ReportDownload)
def download_report(report_snapshot_id: int, request: Request,
                    x_demo_actor: Optional[str] = Header(default=None),
                    role: str = Depends(require_report_role)):
    require_write_allowed(request)
    actor = (x_demo_actor or f"demo.{role}").strip()
    try:
        out = service.download_report(report_snapshot_id, actor, role)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc)
    if out is None:
        raise HTTPException(status_code=404, detail=f"Report {report_snapshot_id} not found.")
    return out
