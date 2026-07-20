"""Typed request/response models for the organizational hierarchy + SUPERADMIN
credential/role management API (Prompt 20 Part B)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RankMappingOut(BaseModel):
    rank: str
    abbr: str
    functional_role: str
    scope_level: str
    note: str = ""


class HierarchyResponse(BaseModel):
    functional_roles: list[str]
    scope_levels: list[str]
    mappings: list[RankMappingOut]
    note: str


class ScopeMatrixResponse(BaseModel):
    actions: list[str]
    roles: list[str]
    matrix: dict[str, dict[str, bool]]
    note: str


class RoleOut(BaseModel):
    role_id: int
    role_name: str
    description: Optional[str] = None
    is_system: bool = True
    permissions: dict[str, str] = Field(default_factory=dict)


class RolesResponse(BaseModel):
    total: int
    items: list[RoleOut] = Field(default_factory=list)
    functional_roles: list[str] = Field(default_factory=list)
    missing_roles: list[str] = Field(default_factory=list)


class UserOut(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str] = None
    role: str
    unit_id: Optional[int] = None
    unit_name: Optional[str] = None
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    is_active: bool = True
    must_reset_password: bool = True
    created_at: Optional[str] = None
    scope_level: Optional[str] = None


class UsersResponse(BaseModel):
    total: int
    items: list[UserOut] = Field(default_factory=list)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    display_name: Optional[str] = Field(None, max_length=120)
    role: str = Field(..., description="One of the six functional roles.")
    unit_id: Optional[int] = Field(None, ge=1, description="Optional Unit scope.")
    actor: Optional[str] = None


class AssignRoleRequest(BaseModel):
    role: str = Field(..., description="One of the six functional roles.")
    actor: Optional[str] = None


class SetScopeRequest(BaseModel):
    unit_id: Optional[int] = Field(None, ge=1, description="Unit scope (null clears it).")
    actor: Optional[str] = None


class SetActiveRequest(BaseModel):
    is_active: bool
    actor: Optional[str] = None


class UserMutationResponse(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str] = None
    role: str
    unit_id: Optional[int] = None
    is_active: bool = True
    must_reset_password: bool = True


class MyScopeResponse(BaseModel):
    role: str
    scope_level: str
    district_ids: Optional[list[int]] = None
    unit_ids: Optional[list[int]] = None
    assigned_case_scoped: bool = False
    user_id: Optional[int] = None
    username: Optional[str] = None
    rank: Optional[str] = None
    source: str
    trusted: bool
    note: str
