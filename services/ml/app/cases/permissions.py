"""Server-side role gates for the Cases destination (doc 01 §4.2 / §7).

Individual case files are PII-heavy, so reads and writes pass a role gate.
INTERIM ("all roles have access to everything"): every canonical command role
holds both; a role outside that set is refused. These gates resolve the
caller's role from the X-Role header (falling back to the
configured default until real auth lands in Phase 14) and are enforced in the
API — not in any model prompt — so they hold regardless of how a request is made.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from ..config import get_settings
from ..roles import ALL_ROLES, DEFAULT_ROLE

# Roles denied any access to individual case files (de-anonymisation risk).
# INTERIM: no command role is denied — every seat reads case files.
CASE_READ_DENY: set[str] = set()
# Roles permitted to add case evidence. INTERIM: every command role.
CASE_WRITE_ROLES = set(ALL_ROLES)


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


def require_case_read(x_role: Optional[str] = Header(default=None)) -> str:
    """Allow everyone except roles denied individual-case access (none, interim)."""
    role = _resolve_role(x_role)
    if role in CASE_READ_DENY:
        raise HTTPException(
            status_code=403,
            detail=("Individual case files are not available to the "
                    f"'{role}' role — this role sees aggregate views only."))
    return role


def require_case_write(x_role: Optional[str] = Header(default=None)) -> str:
    """Case-evidence writes — INTERIM: open to every command role."""
    role = _resolve_role(x_role)
    if role not in CASE_WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot add case evidence — this is an "
                    "investigating-officer action."))
    return role
