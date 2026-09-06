"""Admin console routes: UI visibility, admin-created roles, role settings.

Mounted under /admin alongside app/admin/router.py. Split by job: that module is
platform operations (retention, legal holds, model review), this one is
organisation administration.

NOT AN ENFORCEMENT BOUNDARY YET. Authentication is off in this phase, so these
endpoints are reachable by any caller and the grants they write describe intent
and drive the UI. They become enforcing when the capability matrix and RLS land;
until then every response that could be mistaken for access control says so.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query

from . import service
from .schemas import (
    CreateRoleBody, PermissionCatalogue, RoleDetail, RoleListResponse, RoleOut,
    RoleSettingsBody, SetUiGrantBody, ToggleGrantBody, UiGrantOut,
    UiVisibilityResponse, UpdateGrantsBody, UserProfileBody, UserProfileOut,
)

router = APIRouter(prefix="/admin", tags=["admin-console"])


def _actor(x_demo_actor: Optional[str] = Header(default=None)) -> Optional[str]:
    """Who is making the change, for the audit trail.

    Display/audit only, exactly as elsewhere: the header is advisory and the
    gateway strips it in the deployed path. It is recorded so a grant change has a
    name against it, not used to decide whether the change is allowed.
    """
    return x_demo_actor


def _handle(exc: service.AdminConsoleError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


# --------------------------------------------------------------------------- #
# Permission catalogue                                                        #
# --------------------------------------------------------------------------- #
@router.get("/permissions", response_model=PermissionCatalogue)
def permissions():
    """The vocabulary an admin composes roles from, grouped by category.

    A catalogue rather than free text so the console offers real choices and a
    typo cannot invent a permission that nothing ever checks.
    """
    return service.permission_catalogue()


# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/roles", response_model=RoleListResponse)
def list_roles():
    """Every role with its granted-permission count, UI surface and seat count."""
    return service.list_roles()


@router.get("/roles/{role_name}", response_model=RoleDetail)
def get_role(role_name: str = Path(min_length=1)):
    try:
        return service.get_role(role_name)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.post("/roles", response_model=RoleDetail, status_code=201)
def create_role(body: CreateRoleBody, actor: Optional[str] = Depends(_actor)):
    """Create a role with any composition of catalogued permissions.

    `base_surface` is what makes this work without a deploy: the new role renders
    an existing UI surface, and role_ui_grants then trims or extends it. A role
    that rendered nothing would need new frontend code to be usable.
    """
    try:
        return service.create_role(body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.put("/roles/{role_name}/grants", response_model=RoleDetail)
def replace_grants(
    body: UpdateGrantsBody,
    role_name: str = Path(min_length=1),
    actor: Optional[str] = Depends(_actor),
):
    """Replace the whole grant set, so the console can post its checkbox state
    rather than computing a diff the server would have to trust."""
    try:
        return service.replace_grants(role_name, body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.patch("/roles/{role_name}/grants/{permission_key}",
              response_model=RoleDetail)
def toggle_grant(
    body: ToggleGrantBody,
    role_name: str = Path(min_length=1),
    permission_key: str = Path(min_length=1),
    actor: Optional[str] = Depends(_actor),
):
    """Flip a single permission — what a switch in the console does."""
    try:
        return service.toggle_grant(role_name, permission_key, body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.delete("/roles/{role_name}", status_code=204)
def delete_role(role_name: str = Path(min_length=1),
                actor: Optional[str] = Depends(_actor)):
    """Delete a custom role. Refused for built-in roles, and for any role that
    still has seats — those officers would be left holding a role that no longer
    exists."""
    try:
        service.delete_role(role_name, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.put("/roles/{role_name}/settings", response_model=RoleOut)
def update_role_settings(
    body: RoleSettingsBody,
    role_name: str = Path(min_length=1),
    actor: Optional[str] = Depends(_actor),
):
    """Label, description, landing route and sort order. Presentational only —
    nothing here changes what a role may do or how much data it may see."""
    try:
        return service.update_role_settings(role_name, body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


# --------------------------------------------------------------------------- #
# UI visibility                                                               #
# --------------------------------------------------------------------------- #
@router.get("/ui-visibility", response_model=UiVisibilityResponse)
def ui_visibility(
    role_name: Optional[str] = Query(None),
    element_kind: Optional[str] = Query(
        None, description="destination | board | kpi | widget"),
):
    """Admin OVERRIDES only, not the effective visibility of every element.

    An absent row means "use the registry default", and that default lives in the
    frontend registry. Returning a row per element would mean duplicating the
    registry here and letting the two drift; instead the client applies these
    overrides on top of its own defaults. The practical benefit is that a newly
    shipped KPI card appears per its default immediately, rather than being
    invisible until an admin remembers to enable it for every role.
    """
    return service.list_ui_grants(role_name=role_name, element_kind=element_kind)


@router.put("/ui-visibility", response_model=UiGrantOut)
def set_ui_visibility(body: SetUiGrantBody,
                      actor: Optional[str] = Depends(_actor)):
    """Turn one element on or off for a role, optionally only at one scope type —
    so a card can be hidden from wing seats while range seats keep it."""
    try:
        return service.set_ui_grant(body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.delete("/ui-visibility/{grant_id}", status_code=204)
def clear_ui_visibility(grant_id: int = Path(ge=1),
                        actor: Optional[str] = Depends(_actor)):
    """Remove an override so the element follows its registry default again.

    Distinct from switching it on: an explicit TRUE would PIN it visible, and a
    later change to the default would never reach this role.
    """
    try:
        service.clear_ui_grant(grant_id, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)


# --------------------------------------------------------------------------- #
# Per-user profile                                                            #
# --------------------------------------------------------------------------- #
@router.get("/users/{user_id}/profile", response_model=UserProfileOut)
def get_user_profile(user_id: int = Path(ge=1)):
    try:
        return service.get_user_profile(user_id)
    except service.AdminConsoleError as exc:
        _handle(exc)


@router.put("/users/{user_id}/profile", response_model=UserProfileOut)
def update_user_profile(
    body: UserProfileBody,
    user_id: int = Path(ge=1),
    actor: Optional[str] = Depends(_actor),
):
    """Edit a seat's own details: name, rank, designation, contact, posting label.

    Role, unit and scope are NOT editable here. Those are provisioning decisions
    with their own audited endpoints, and accepting them on a profile edit would
    let a display-name change quietly move a seat's jurisdiction.
    """
    try:
        return service.update_user_profile(user_id, body, actor)
    except service.AdminConsoleError as exc:
        _handle(exc)
