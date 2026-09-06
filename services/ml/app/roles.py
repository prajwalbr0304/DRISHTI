"""Canonical DRISHTI functional roles (single source of truth, server-side).

SIX application roles. A role answers exactly one question — which UI surface a
seat renders. How much data it sees is a separate axis, ``users.scope_type``,
resolved from the seat's posting. That split is why ADGP and DIG share
``senior_command`` (same surface, wing vs range scope) and SP and CP share
``district_command``. Superseded names are translated by
:func:`translate_legacy_role`, never silently defaulted.

They are mirrored by, and must stay in step with:

  * ``web/src/config/roles.ts``                      (UI presentation + labels)
  * ``services/ml/app/gateway_context.py``           (defence-in-depth revalidation)
  * ``infra/catalyst/functions/gateway_api/index.js`` (server-side role resolution)
  * ``services/ml/sql/028_roles_six_app_roles.sql``  (roles/users/role_permissions)

``tests/test_gateway_authz.py::test_functional_roles_in_sync`` fails if the Python
copies drift apart.

INTERIM AUTHORIZATION MODEL — every role still holds every CAPABILITY
("all roles have access to everything"), and narrowing that is the pending
capability-matrix work. What is NOT interim any more is geographic scope: it is
derived and enforced in ``app/org/scope.py``, and it FAILS CLOSED. A seat with no
posting on record resolves to ``scope_type='unresolved'`` and sees nothing, rather
than falling through to "no restriction" — which previously made an unposted SHO
indistinguishable from the DGP.

Pure data + pure functions: no DB, no I/O, importable from anywhere in the app.
"""
from __future__ import annotations

from typing import Optional

# Display order matches the UI seat picker (senior -> junior -> platform).
#
# SIX application roles, not ten presentation seats. The role answers only "which
# UI surface"; how much data a seat sees is users.scope_type + its anchor. That is
# why ADGP and DIG share `senior_command`: same surface, different scope_type
# (wing vs range). Likewise SP and CP share `district_command`.
FUNCTIONAL_ROLES: tuple[str, ...] = (
    "dgp_state_command",
    "senior_command",
    "district_command",
    "sho",
    "investigating_officer",
    "system_admin",
)

# Scope types a seat may carry, ordered broadest -> narrowest. `wing` is
# deliberately NOT in that order: it is a functional scope (state-wide geography
# narrowed by crime head), not a rung on the geographic ladder.
SCOPE_TYPES: tuple[str, ...] = (
    "state", "wing", "range", "district", "commissionerate",
    "station", "assigned_case", "platform", "unresolved",
)

# Which scope_types each application role may be issued at. Mirrors
# roles.allowed_scope_types in the database (migration 035).
ROLE_SCOPE_TYPES: dict[str, tuple[str, ...]] = {
    "dgp_state_command": ("state",),
    "senior_command": ("wing", "range"),
    "district_command": ("district", "commissionerate"),
    "sho": ("station",),
    "investigating_officer": ("assigned_case",),
    "system_admin": ("platform",),
}

# The UI surface each role renders. A custom admin-created role names one of
# these as its base_surface, which is why a new role needs no new frontend code.
ROLE_SURFACE: dict[str, str] = {
    "dgp_state_command": "state_command",
    "senior_command": "senior_command",
    "district_command": "district_command",
    "sho": "station",
    "investigating_officer": "case_work",
    "system_admin": "platform",
}

# Superseded role names -> current application role. Kept so an old token, cached
# header or stale client value resolves to the right seat instead of collapsing to
# the least-privilege default. Mirrors the remap in migration 028.
LEGACY_ROLE_ALIASES: dict[str, str] = {
    # ten-role presentation vocabulary
    "adgp_igp_range": "senior_command",
    "sp_district_command": "district_command",
    "dysp_acp": "district_command",
    "crime_analyst": "senior_command",
    "cyber_cell": "senior_command",
    "traffic_command": "senior_command",
    # pre-ten-role vocabulary
    "investigator": "investigating_officer",
    "supervisor": "sho",
    "analyst": "senior_command",
    "policymaker": "senior_command",
    "super_admin": "system_admin",
}

ALL_ROLES: frozenset[str] = frozenset(FUNCTIONAL_ROLES)

# Command/oversight seats (everything above the field IO and the staff cells).
# Used for *ownership* defaults (e.g. an oversight seat edits a station's board),
# never for access denial.
SUPERVISORY_ROLES: frozenset[str] = frozenset({
    "dgp_state_command", "senior_command", "district_command", "sho",
    "system_admin",
})

# Least-privilege default seat when no role is asserted anywhere.
DEFAULT_ROLE = "investigating_officer"

ROLE_LABELS: dict[str, str] = {
    "dgp_state_command": "DGP / State Command",
    "senior_command": "Senior Command",
    "district_command": "District Command",
    "sho": "SHO",
    "investigating_officer": "Investigating Officer",
    "system_admin": "System Admin",
}

# Label shown for a seat, which depends on the scope_type rather than the role.
# A senior_command seat is an ADGP when wing-scoped and a DIG when range-scoped.
SCOPE_TYPE_LABELS: dict[str, str] = {
    "state": "DGP / State Command",
    "wing": "ADGP / Functional Wing",
    "range": "DIG / Range Command",
    "district": "SP / District Command",
    "commissionerate": "CP / City Commissionerate",
    "station": "SHO / Station",
    "assigned_case": "Investigating Officer",
    "platform": "System Admin",
    "unresolved": "Unposted seat",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "dgp_state_command": "State command: state-wide priorities, escalations and outcomes. Aggregate-only.",
    "senior_command": "Senior command. Wing-scoped (ADGP) is state-wide narrowed by crime head; range-scoped (DIG) spans the range's districts.",
    "district_command": "District command: workload, approvals and station performance. SP for a district, CP for a Commissionerate.",
    "sho": "Station chief: registration, assignment and the station review queue.",
    "investigating_officer": "Field officer: assigned cases, evidence, statements and leads.",
    "system_admin": "Platform administration: seats, roles, UI visibility, model registry and governance.",
}

# Default scope_type when a seat has no posting on record. `unresolved` is
# deliberate and must resolve to NO data — never to state-wide.
ROLE_DEFAULT_SCOPE_TYPE: dict[str, str] = {
    "dgp_state_command": "state",
    "senior_command": "unresolved",
    "district_command": "unresolved",
    "sho": "unresolved",
    "investigating_officer": "unresolved",
    "system_admin": "platform",
}

# Legacy geographic scope level per role, retained because app/org/hierarchy.py
# still expresses containment on the ordered state/range/district/... ladder.
ROLE_SCOPE_LEVEL: dict[str, str] = {
    "dgp_state_command": "state",
    "senior_command": "range",
    "district_command": "district",
    "sho": "station",
    "investigating_officer": "assigned_case",
    "system_admin": "state",
}

# Synthetic demo credential per role: role -> (username, display_name). These are
# the pre-existing seeded rows, now given a real posting by
# scripts/migrations/provision_seats.sql so they resolve to a scope instead of
# collapsing to 'unresolved'.
DEMO_USERS: dict[str, tuple[str, str]] = {
    "dgp_state_command": ("dgp.vikram", "DGP Vikram Shetty"),
    "senior_command": ("igp.meenakshi", "IGP Meenakshi Rao"),
    "district_command": ("sp.anand", "SP Anand Kumar"),
    "sho": ("sho.suresh", "SHO Suresh Patil"),
    "investigating_officer": ("io.ramesh", "PSI Ramesh Gowda"),
    "system_admin": ("admin", "Sysadmin Nikhil Jain"),
}


def scope_types_for_role(role: str) -> tuple[str, ...]:
    """scope_types a role may be issued at (empty tuple = unconstrained)."""
    return ROLE_SCOPE_TYPES.get((role or "").strip(), ())


def scope_type_allowed(role: str, scope_type: str) -> bool:
    """Rule 4 of the custom-role contract: a seat's scope_type must be one its
    role permits. An unconstrained (admin-created) role accepts any."""
    allowed = scope_types_for_role(role)
    return (not allowed) or ((scope_type or "").strip() in allowed)


def surface_for_role(role: str) -> str:
    """UI surface a role renders. Falls back to the case-work surface, the
    narrowest one, rather than to a command board."""
    return ROLE_SURFACE.get((role or "").strip(), "case_work")


def is_role(value: Optional[str]) -> bool:
    """True when ``value`` is one of the canonical functional roles."""
    return bool(value) and str(value).strip() in ALL_ROLES


def translate_legacy_role(value: Optional[str]) -> str:
    """Map a SUPERSEDED role name onto its current one, leaving anything else alone.

    Deliberately different from :func:`normalize_role`: an unrecognised role is
    returned UNCHANGED rather than coerced to a default. Scope derivation depends
    on that, because every capability check refuses a role outside ALL_ROLES — so
    an unknown or forged role must stay unknown and hold nothing. Coercing it to
    the default seat would silently grant a forged header a real seat's
    capabilities.

    Use this when deriving authority. Use :func:`normalize_role` only where a safe
    default is genuinely wanted, such as parsing a presentation header.
    """
    role = (value or "").strip()
    if role in ALL_ROLES:
        return role
    return LEGACY_ROLE_ALIASES.get(role, role)


def normalize_role(value: Optional[str], default: Optional[str] = None) -> str:
    """Coerce an asserted role to a canonical one, else the (safe) default.

    A superseded role name is translated through LEGACY_ROLE_ALIASES rather than
    silently dropped: a cached client value of ``cyber_cell`` means senior_command,
    and collapsing it to the least-privilege default would misroute the seat.
    """
    role = (value or "").strip()
    if role in ALL_ROLES:
        return role
    aliased = LEGACY_ROLE_ALIASES.get(role)
    if aliased in ALL_ROLES:
        return aliased
    fallback = (default or DEFAULT_ROLE).strip()
    return fallback if fallback in ALL_ROLES else DEFAULT_ROLE


def full_grants(resources, action: str = "write") -> dict[str, dict[str, str]]:
    """role -> {resource: action} with every role granted ``action`` everywhere.

    Used to build the interim "all roles have access to everything" permission
    matrices (admin console, money trail, role_permissions seed)."""
    return {role: {resource: action for resource in resources}
            for role in FUNCTIONAL_ROLES}


def scope_level_for_role(role: str) -> str:
    """Default scope level a role holds when no rank refinement is available."""
    return ROLE_SCOPE_LEVEL.get((role or "").strip(), "assigned_case")
