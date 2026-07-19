"""FastAPI router for Phase-15 notifications / work tasks.

Reads are scoped to the calling demo actor; writes require a notification_manage
role (all operational roles except policymaker) AND the hackathon write guard.
Notification bodies are data-minimized synthetic summaries only.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from ..admin.permissions import has_permission, resolve_role
from ..config import get_settings
from ..intake.guards import require_write_allowed
from . import service
from .schemas import (EscalationRunResult, NotificationListResponse, NotificationOut,
                      NotificationPreferenceOut, NotificationPreferenceUpdate, WorkTaskCreate,
                      WorkTaskListResponse, WorkTaskOut, WorkTaskUpdate)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def require_notify_manage(x_role: Optional[str] = Header(default=None)) -> str:
    role = resolve_role(x_role)
    if not has_permission(role, "notification_manage"):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' cannot manage tasks/notifications in this demo.")
    return role


def _actor(x_demo_actor: Optional[str], role: str) -> str:
    return (x_demo_actor or f"demo.{role}").strip()


# --- preferences -------------------------------------------------------------
@router.get("/preferences", response_model=NotificationPreferenceOut)
def get_preferences(x_demo_actor: Optional[str] = Header(default=None),
                    x_role: Optional[str] = Header(default=None)):
    role = resolve_role(x_role)
    return service.get_preference(_actor(x_demo_actor, role))


@router.put("/preferences", response_model=NotificationPreferenceOut)
def update_preferences(body: NotificationPreferenceUpdate, request: Request,
                       x_demo_actor: Optional[str] = Header(default=None),
                       role: str = Depends(require_notify_manage)):
    require_write_allowed(request)
    return service.upsert_preference(_actor(x_demo_actor, role), body.in_app, body.email,
                                     body.push, body.digest_frequency, body.escalation_sla_hours)


# --- notifications -----------------------------------------------------------
@router.get("", response_model=NotificationListResponse)
def list_notifications(unread_only: bool = Query(False), limit: int = Query(50, ge=1, le=200),
                       x_demo_actor: Optional[str] = Header(default=None),
                       x_role: Optional[str] = Header(default=None)):
    role = resolve_role(x_role)
    return service.list_notifications(_actor(x_demo_actor, role), unread_only, limit)


@router.post("/{message_id}/read", response_model=NotificationOut)
def mark_read(message_id: int, request: Request,
              x_demo_actor: Optional[str] = Header(default=None),
              x_role: Optional[str] = Header(default=None)):
    require_write_allowed(request)
    role = resolve_role(x_role)
    out = service.mark_read(message_id, _actor(x_demo_actor, role))
    if out is None:
        raise HTTPException(status_code=404, detail=f"Notification {message_id} not found.")
    return out


# --- work tasks --------------------------------------------------------------
@router.get("/tasks", response_model=WorkTaskListResponse)
def list_tasks(assignee: Optional[str] = Query(None), status: Optional[str] = Query(None),
               case_master_id: Optional[int] = Query(None), limit: int = Query(100, ge=1, le=200),
               _role: str = Depends(require_notify_manage)):
    return service.list_tasks(assignee, status, case_master_id, limit)


@router.post("/tasks", response_model=WorkTaskOut)
def create_task(body: WorkTaskCreate, request: Request,
                x_demo_actor: Optional[str] = Header(default=None),
                role: str = Depends(require_notify_manage)):
    require_write_allowed(request)
    return service.create_task(body, body.actor or _actor(x_demo_actor, role))


@router.get("/tasks/{work_task_id}", response_model=WorkTaskOut)
def get_task(work_task_id: int, _role: str = Depends(require_notify_manage)):
    out = service.get_task(work_task_id)
    if out is None:
        raise HTTPException(status_code=404, detail=f"Work task {work_task_id} not found.")
    return out


@router.patch("/tasks/{work_task_id}", response_model=WorkTaskOut)
def update_task(work_task_id: int, body: WorkTaskUpdate, request: Request,
                x_demo_actor: Optional[str] = Header(default=None),
                role: str = Depends(require_notify_manage)):
    require_write_allowed(request)
    out = service.update_task(work_task_id, body, body.actor or _actor(x_demo_actor, role))
    if out is None:
        raise HTTPException(status_code=404, detail=f"Work task {work_task_id} not found.")
    return out


# --- escalation --------------------------------------------------------------
@router.post("/escalations/run", response_model=EscalationRunResult)
def run_escalations(request: Request, x_demo_actor: Optional[str] = Header(default=None),
                    role: str = Depends(require_notify_manage)):
    require_write_allowed(request)
    return service.run_escalations(_actor(x_demo_actor, role))
