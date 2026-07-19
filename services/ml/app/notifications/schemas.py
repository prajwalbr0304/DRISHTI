"""Typed models for Phase-15 notifications / work-task API.

Notification bodies are data-minimized synthetic SUMMARIES only — never evidence
content, full narratives, or personal identifiers (enforced in the service).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# --- preferences -------------------------------------------------------------
class NotificationPreferenceOut(BaseModel):
    actor_key: str
    in_app: bool = True
    email: bool = False
    push: bool = False
    digest_frequency: str = "immediate"
    escalation_sla_hours: int = 24


class NotificationPreferenceUpdate(BaseModel):
    in_app: bool = True
    email: bool = False
    push: bool = False
    digest_frequency: str = Field("immediate", pattern="^(immediate|hourly|daily)$")
    escalation_sla_hours: int = Field(24, ge=1, le=720)


# --- work tasks --------------------------------------------------------------
class WorkTaskOut(BaseModel):
    work_task_id: int
    task_type: str
    title: str
    related_resource: Optional[str] = None
    related_resource_id: Optional[str] = None
    case_master_id: Optional[int] = None
    unit_id: Optional[int] = None
    assignee_actor: Optional[str] = None
    assigned_by_actor: Optional[str] = None
    priority: str = "medium"
    status: str = "open"
    due_at: Optional[str] = None
    escalation_sla_hours: Optional[int] = None
    escalated_at: Optional[str] = None
    created_at: Optional[str] = None


class WorkTaskListResponse(BaseModel):
    total: int
    items: list[WorkTaskOut] = Field(default_factory=list)


class WorkTaskCreate(BaseModel):
    task_type: str = Field("general", pattern="^(case_review|evidence_review|prediction_review|entity_review|general)$")
    title: str = Field(..., min_length=3, max_length=160, description="Short non-sensitive synthetic summary.")
    related_resource: Optional[str] = Field(None, max_length=60)
    related_resource_id: Optional[str] = Field(None, max_length=60)
    case_master_id: Optional[int] = None
    unit_id: Optional[int] = None
    assignee_actor: Optional[str] = None
    priority: str = Field("medium", pattern="^(low|medium|high)$")
    due_at: Optional[str] = None
    escalation_sla_hours: Optional[int] = Field(None, ge=1, le=720)
    actor: Optional[str] = None


class WorkTaskUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(open|in_progress|done|escalated|cancelled)$")
    assignee_actor: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high)$")
    due_at: Optional[str] = None
    actor: Optional[str] = None


# --- notifications + delivery ------------------------------------------------
class NotificationDeliveryOut(BaseModel):
    notification_delivery_id: int
    channel: str
    provider: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None


class NotificationOut(BaseModel):
    notification_message_id: int
    notification_type: str
    recipient_actor: str
    summary: str
    severity: str = "info"
    related_resource: Optional[str] = None
    related_resource_id: Optional[str] = None
    work_task_id: Optional[int] = None
    read_at: Optional[str] = None
    created_at: Optional[str] = None
    deliveries: list[NotificationDeliveryOut] = Field(default_factory=list)


class NotificationListResponse(BaseModel):
    total: int
    unread: int
    items: list[NotificationOut] = Field(default_factory=list)


class EscalationRunResult(BaseModel):
    checked: int
    escalated: int
    notifications_created: int
    escalated_task_ids: list[int] = Field(default_factory=list)
