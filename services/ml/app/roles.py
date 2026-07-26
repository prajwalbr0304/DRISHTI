"""Canonical DRISHTI functional roles (single source of truth, server-side).

The ten police-command seats below replace the earlier six generic roles
(investigator/analyst/supervisor/policymaker/disaster_coordinator/super_admin).
They are mirrored by:

  * ``web/src/config/roles.ts``                      (UI presentation + labels)
  * ``services/ml/app/gateway_context.py``           (defence-in-depth revalidation)
  * ``infra/catalyst/functions/gateway_api/index.js`` (server-side role resolution)
  * ``services/ml/sql/police_fir_extensions.sql``    (roles/users/role_permissions seed)

INTERIM AUTHORIZATION MODEL — every role currently holds EVERY capability
("all roles have access to everything"). The enforcement points (guards,
permission matrices, allow/deny matrix) all derive their allow-lists from
``ALL_ROLES`` / :func:`full_grants` here, so tightening the policy later is a
change to THIS module plus the per-module sets that reference it, not a hunt
through every router. Geographic scope (state/range/district/... ) is still
derived and enforced separately in ``app/org/scope.py``.

Pure data + pure functions: no DB, no I/O, importable from anywhere in the app.
"""
from __future__ import annotations

from typing import Optional

# Display order matches the UI role picker (senior -> junior -> staff cells).
FUNCTIONAL_ROLES: tuple[str, ...] = (
    "dgp_state_command",
    "adgp_igp_range",
    "sp_district_command",
    "dysp_acp",
    "sho",
    "investigating_officer",
    "crime_analyst",
    "cyber_cell",
    "traffic_command",
    "system_admin",
)

ALL_ROLES: frozenset[str] = frozenset(FUNCTIONAL_ROLES)

# Command/oversight seats (everything above the field IO and the staff cells).
# Used for *ownership* defaults (e.g. an oversight seat edits a station's board),
# never for access denial.
SUPERVISORY_ROLES: frozenset[str] = frozenset({
    "dgp_state_command", "adgp_igp_range", "sp_district_command", "dysp_acp",
    "sho", "system_admin",
})

# Least-privilege default seat when no role is asserted anywhere.
DEFAULT_ROLE = "investigating_officer"

ROLE_LABELS: dict[str, str] = {
    "dgp_state_command": "DGP / State Command",
    "adgp_igp_range": "ADGP / IGP Range",
    "sp_district_command": "SP / District Command",
    "dysp_acp": "DySP / ACP",
    "sho": "SHO",
    "investigating_officer": "Investigating Officer",
    "crime_analyst": "Crime Analyst",
    "cyber_cell": "Cyber Cell",
    "traffic_command": "Traffic Command",
    "system_admin": "System Admin",
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "dgp_state_command": "State command: state-wide priorities, escalations and outcomes.",
    "adgp_igp_range": "Range command: oversight and comparison across the range's districts.",
    "sp_district_command": "District command: workload, approvals and station performance.",
    "dysp_acp": "Sub-divisional oversight: case review, quality and escalation.",
    "sho": "Station chief: registration, assignment and the station review queue.",
    "investigating_officer": "Field IO: assigned cases, evidence, statements and leads.",
    "crime_analyst": "Crime analysis: patterns, networks, hotspots and forecasting.",
    "cyber_cell": "Cyber / financial crime: money trail, devices and accounts.",
    "traffic_command": "Traffic command: road-safety hotspots and enforcement load.",
    "system_admin": "Platform administration: credentials, model registry and governance.",
}

# Default (broadest) organizational scope level per role. Ordered levels live in
# app/org/hierarchy.py SCOPE_LEVELS.
ROLE_SCOPE_LEVEL: dict[str, str] = {
    "dgp_state_command": "state",
    "adgp_igp_range": "range",
    "sp_district_command": "district",
    "dysp_acp": "subdivision",
    "sho": "station",
    "investigating_officer": "assigned_case",
    "crime_analyst": "state",
    "cyber_cell": "state",
    "traffic_command": "district",
    "system_admin": "state",
}

# Synthetic demo credential per role: role -> (username, display_name). Mirrors
# the seeded "users" rows (SQL seed + datagen) and web/src/config/roles.ts.
DEMO_USERS: dict[str, tuple[str, str]] = {
    "dgp_state_command": ("dgp.vikram", "DGP Vikram Shetty"),
    "adgp_igp_range": ("igp.meenakshi", "IGP Meenakshi Rao"),
    "sp_district_command": ("sp.anand", "SP Anand Kumar"),
    "dysp_acp": ("dysp.kavya", "Dy.SP Kavya Hegde"),
    "sho": ("sho.suresh", "SHO Suresh Patil"),
    "investigating_officer": ("io.ramesh", "PSI Ramesh Gowda"),
    "crime_analyst": ("analyst.divya", "Analyst Divya Naik"),
    "cyber_cell": ("cyber.arjun", "Insp. Arjun Bhat (CEN)"),
    "traffic_command": ("traffic.latha", "Traffic ACP Latha Prasad"),
    "system_admin": ("admin", "Sysadmin Nikhil Jain"),
}


def is_role(value: Optional[str]) -> bool:
    """True when ``value`` is one of the canonical functional roles."""
    return bool(value) and str(value).strip() in ALL_ROLES


def normalize_role(value: Optional[str], default: Optional[str] = None) -> str:
    """Coerce an asserted role to a canonical one, else the (safe) default."""
    role = (value or "").strip()
    if role in ALL_ROLES:
        return role
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
