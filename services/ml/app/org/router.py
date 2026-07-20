"""FastAPI router for organizational hierarchy + SUPERADMIN credential/role
management (Prompt 20 Part B).

  GET  /org/hierarchy       — synthetic police rank -> functional role + scope map
  GET  /org/scope-matrix    — role x action allow/deny matrix (server-enforced)
  GET  /org/roles           — roles + permission grants (admin read)
  GET  /org/users           — application credentials + assigned role/scope
  POST /org/roles/ensure    — idempotently seed the six functional roles
  POST /org/users           — SUPERADMIN: create a credential + assign a role
  PUT  /org/users/{id}/role — SUPERADMIN: assign / change the role
  PUT  /org/users/{id}/scope— SUPERADMIN: assign / clear the unit/district scope
  POST /org/users/{id}/active — SUPERADMIN: activate / deactivate a credential
  GET  /org/my-scope        — the caller's TRUSTED, server-derived scope

Reads require admin_read (supervisor + super_admin). All credential mutations
require admin_write (super_admin) AND the hackathon write guard (localhost +
synthetic DB). The organizational scope is always derived server-side; a browser
district/unit header is never trusted for authorization.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..admin.permissions import require_admin_read, require_admin_write
from ..intake.guards import require_write_allowed
from . import hierarchy, scope as scope_mod, service
from .schemas import (AssignRoleRequest, CreateUserRequest, HierarchyResponse,
                      MyScopeResponse, RolesResponse, ScopeMatrixResponse,
                      SetActiveRequest, SetScopeRequest, UserMutationResponse,
                      UsersResponse)

router = APIRouter(prefix="/org", tags=["org"])

_HIER_NOTE = ("Synthetic demo mapping of police rank/assignment to a functional "
              "role + organizational scope. Real directory/SSO/rank sync is "
              "post-hackathon.")
_MATRIX_NOTE = ("Server-enforced allow/deny at the role default scope. A "
                "geographically-scoped seat is additionally confined to its "
                "assigned district/unit, derived server-side (never a browser header).")
_SCOPE_NOTE = ("Derived from the trusted Catalyst user record (role + unit "
               "assignment). A browser-supplied district/unit header is ignored "
               "for authorization.")


def _err(exc: service.OrgError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# --- reads ------------------------------------------------------------------
@router.get("/hierarchy", response_model=HierarchyResponse)
def get_hierarchy(_role: str = Depends(require_admin_read)):
    return {"functional_roles": list(hierarchy.FUNCTIONAL_ROLES),
            "scope_levels": list(hierarchy.SCOPE_LEVELS),
            "mappings": hierarchy.catalog(), "note": _HIER_NOTE}


@router.get("/scope-matrix", response_model=ScopeMatrixResponse)
def get_scope_matrix(_role: str = Depends(require_admin_read)):
    return {"actions": list(scope_mod.MATRIX_ACTIONS),
            "roles": list(hierarchy.FUNCTIONAL_ROLES),
            "matrix": scope_mod.matrix_for_roles(), "note": _MATRIX_NOTE}


@router.get("/roles", response_model=RolesResponse)
def get_roles(_role: str = Depends(require_admin_read)):
    return service.list_roles()


@router.get("/users", response_model=UsersResponse)
def get_users(_role: str = Depends(require_admin_read)):
    return service.list_users()


@router.get("/my-scope", response_model=MyScopeResponse)
def my_scope(x_demo_actor: Optional[str] = Header(default=None),
             x_role: Optional[str] = Header(default=None)):
    """Resolve the caller's trusted scope. In deployed mode the gateway injects
    the authenticated actor; locally the demo actor/role stand in. Falls back to
    a role-default scope when the actor is not a known user."""
    username = (x_demo_actor or "").strip() or None
    try:
        if username:
            sc = service.resolve_scope_for_user(username=username)
        else:
            sc = scope_mod.derive_scope((x_role or "investigator").strip(),
                                        source="role-default", )
    except service.OrgError:
        sc = scope_mod.derive_scope((x_role or "investigator").strip(),
                                    source="role-default")
    except Exception:  # noqa: BLE001 — DB unavailable: fall back to role default
        sc = scope_mod.derive_scope((x_role or "investigator").strip(),
                                    source="role-default-offline")
    out = sc.as_dict()
    out["note"] = _SCOPE_NOTE
    return out


# --- writes (SUPERADMIN) ----------------------------------------------------
@router.post("/roles/ensure")
def ensure_roles(request: Request, role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    return service.ensure_roles()


@router.post("/users", response_model=UserMutationResponse, status_code=201)
def create_user(body: CreateUserRequest, request: Request,
                role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    try:
        return service.create_user(body.username, body.display_name, body.role,
                                   body.unit_id, actor=body.actor or f"demo.{role}")
    except service.OrgError as exc:
        raise _err(exc)


@router.put("/users/{user_id}/role", response_model=UserMutationResponse)
def assign_role(user_id: int, body: AssignRoleRequest, request: Request,
                role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    try:
        return service.assign_role(user_id, body.role, actor=body.actor or f"demo.{role}")
    except service.OrgError as exc:
        raise _err(exc)


@router.put("/users/{user_id}/scope", response_model=UserMutationResponse)
def set_scope(user_id: int, body: SetScopeRequest, request: Request,
              role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    try:
        return service.set_scope(user_id, body.unit_id, actor=body.actor or f"demo.{role}")
    except service.OrgError as exc:
        raise _err(exc)


@router.post("/users/{user_id}/active", response_model=UserMutationResponse)
def set_active(user_id: int, body: SetActiveRequest, request: Request,
               role: str = Depends(require_admin_write)):
    require_write_allowed(request)
    try:
        return service.set_active(user_id, body.is_active, actor=body.actor or f"demo.{role}")
    except service.OrgError as exc:
        raise _err(exc)
