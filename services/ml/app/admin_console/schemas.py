"""Request/response models for the admin console."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# The four kinds of thing whose visibility an admin can override, matching
# role_ui_grants.chk_role_ui_element_kind.
ElementKind = Literal["destination", "board", "kpi", "widget"]

SCOPE_TYPES = (
    "state", "wing", "range", "district", "commissionerate",
    "station", "assigned_case", "platform",
)

BASE_SURFACES = (
    "state_command", "senior_command", "district_command",
    "station", "case_work", "platform",
)


# --------------------------------------------------------------------------- #
# Permission catalogue                                                        #
# --------------------------------------------------------------------------- #
class PermissionOut(BaseModel):
    permission_key: str
    resource: str
    action: str
    label: str
    description: Optional[str] = None
    category: str
    is_sensitive: bool
    #: Narrowest scope_type at which the permission means anything, or None for
    #: any. Drives rule 2 — a state seat is aggregate-only and cannot hold
    #: cases.detail_read.
    requires_scope: Optional[str] = None


class PermissionCatalogue(BaseModel):
    total: int
    #: Grouped for the console's grant picker, which is organised by category.
    categories: dict[str, list[PermissionOut]]
    scope_types: list[str] = Field(default_factory=lambda: list(SCOPE_TYPES))


# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #
class RoleGrantOut(BaseModel):
    permission_key: str
    granted: bool
    reason: Optional[str] = None
    granted_by: Optional[str] = None


class RoleOut(BaseModel):
    role_name: str
    description: Optional[str] = None
    is_system: bool
    base_surface: Optional[str] = None
    allowed_scope_types: Optional[list[str]] = None
    created_by: Optional[str] = None
    #: Granted permissions, not catalogued ones — what the role can actually do.
    granted_count: int
    sensitive_count: int
    #: Seats holding the role. A custom role with seats cannot be deleted.
    seat_count: int
    display_label: Optional[str] = None
    default_route: Optional[str] = None
    sort_order: Optional[int] = None


class RoleListResponse(BaseModel):
    total: int
    items: list[RoleOut]
    base_surfaces: list[str] = Field(default_factory=lambda: list(BASE_SURFACES))


class RoleDetail(RoleOut):
    grants: list[RoleGrantOut]


class CreateRoleBody(BaseModel):
    role_name: str = Field(min_length=3, max_length=64)
    description: Optional[str] = None
    #: Which built-in UI surface the role renders. Required: a role that renders
    #: nothing is not usable, and this is what lets a new role ship with no new
    #: frontend code.
    base_surface: str
    allowed_scope_types: list[str] = Field(min_length=1)
    permission_keys: list[str] = Field(default_factory=list)
    #: Required when any requested permission is flagged is_sensitive.
    reason: Optional[str] = None
    display_label: Optional[str] = None
    default_route: Optional[str] = None

    @field_validator("role_name")
    @classmethod
    def _snake_case(cls, v: str) -> str:
        """Role names are used as identifiers in URLs, config and the legacy
        role_permissions projection, so they are constrained to a safe shape
        rather than sanitised later."""
        v = v.strip().lower().replace("-", "_").replace(" ", "_")
        if not v.replace("_", "").isalnum():
            raise ValueError(
                "role_name may contain letters, digits and underscores only")
        if not v[0].isalpha():
            raise ValueError("role_name must start with a letter")
        return v

    @field_validator("base_surface")
    @classmethod
    def _known_surface(cls, v: str) -> str:
        if v not in BASE_SURFACES:
            raise ValueError(f"base_surface must be one of {', '.join(BASE_SURFACES)}")
        return v

    @field_validator("allowed_scope_types")
    @classmethod
    def _known_scopes(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in SCOPE_TYPES]
        if bad:
            raise ValueError(f"unknown scope_type(s): {', '.join(bad)}")
        return v


class UpdateGrantsBody(BaseModel):
    """Replaces the whole grant set, so the console can send the state of its
    checkbox list rather than computing a diff."""
    permission_keys: list[str]
    reason: Optional[str] = None


class ToggleGrantBody(BaseModel):
    granted: bool
    reason: Optional[str] = None


# --------------------------------------------------------------------------- #
# UI visibility                                                               #
# --------------------------------------------------------------------------- #
class UiGrantOut(BaseModel):
    id: int
    role_name: str
    #: None means the override applies to every scope_type of the role.
    scope_type: Optional[str] = None
    element_kind: ElementKind
    element_id: str
    enabled: bool
    reason: Optional[str] = None
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None


class UiVisibilityResponse(BaseModel):
    total: int
    items: list[UiGrantOut]
    #: Stated in the payload, not just the docs: while auth and RLS are off these
    #: switches govern rendering only. A hidden destination is still reachable by
    #: URL and a hidden card's endpoint still answers.
    enforcement: str = (
        "Presentation only. These switches control what is rendered, not what may "
        "be read: a hidden destination is still reachable by URL and a hidden "
        "card's endpoint still answers. They become enforcing when the capability "
        "matrix and RLS land."
    )


class SetUiGrantBody(BaseModel):
    role_name: str
    element_kind: ElementKind
    element_id: str
    enabled: bool
    scope_type: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("scope_type")
    @classmethod
    def _known_scope(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SCOPE_TYPES:
            raise ValueError(f"unknown scope_type: {v}")
        return v


# --------------------------------------------------------------------------- #
# Role settings                                                               #
# --------------------------------------------------------------------------- #
class RoleSettingsBody(BaseModel):
    """Presentational only. Nothing here changes what a role may do or see."""
    display_label: Optional[str] = None
    description: Optional[str] = None
    default_route: Optional[str] = None
    default_board_id: Optional[str] = None
    icon_name: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("default_route")
    @classmethod
    def _absolute(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("/"):
            raise ValueError("default_route must start with '/'")
        return v


class UserProfileBody(BaseModel):
    """Per-user details an admin may edit.

    Deliberately EXCLUDES role, unit, district, wing, range and scope_type. Those
    are provisioning decisions with their own audited endpoints, and folding them
    in here would let a display-name edit silently move a seat's jurisdiction.

    `is_lead_investigator` is included because it is an assignment property — may
    this officer be recorded as the IO of record — and not a rank or a scope. A
    lead IO and an assisting constable hold the same scope, so nothing else
    distinguishes them.

    Every field is optional and only the ones PRESENT in the request are written,
    so a partial edit cannot blank the fields it did not mention.
    """
    display_name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=32)
    rank_label: Optional[str] = Field(default=None, max_length=64)
    designation_label: Optional[str] = Field(default=None, max_length=120)
    posting_label: Optional[str] = Field(default=None, max_length=200)
    preferred_language: Optional[str] = Field(default=None, max_length=8)
    notes: Optional[str] = None
    is_lead_investigator: Optional[bool] = None


class UserProfileOut(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str] = None
    role: str
    scope_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    rank_label: Optional[str] = None
    designation_label: Optional[str] = None
    posting_label: Optional[str] = None
    preferred_language: Optional[str] = None
    notes: Optional[str] = None
    is_lead_investigator: bool = False
    is_active: bool = True
    updated_by: Optional[str] = None
