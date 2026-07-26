"""Server-side 'money_trail' permission gate (doc 04 §7; code-based in Prompt 21).

Financial data is sensitive, so every /money endpoint depends on this gate. It
resolves the caller's role (the server-trusted X-Role, rewritten from the signed
gateway context in deployed mode) and checks the in-code authorization matrix
for resource='money_trail'. A role whose grant is absent is refused with 403.

The matrix is enforced IN CODE (not read from AWS RDS): the versioned
AWS→Data Store map records role_permissions as NOT_IMPORTED, so the gate holds
with DATABASE_URL absent (deployed AppSail) and regardless of how a request is
phrased.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from ..config import get_settings
from ..roles import DEFAULT_ROLE, FUNCTIONAL_ROLES

MONEY_RESOURCE = "money_trail"

# Code-based 'money_trail' authorization matrix (Prompt 21 §B/§E). The versioned
# AWS→Data Store map (app/datastore/mapping.py) records role_permissions as
# NOT_IMPORTED — "authorization matrix enforced in code, not imported" — so the
# gate must NOT read AWS RDS. It mirrors the seed in
# services/ml/sql/police_fir_extensions.sql and therefore holds with
# DATABASE_URL absent (deployed AppSail).
#
# INTERIM ("all roles have access to everything"): every command role holds
# WRITE on money_trail. A role that is later denied should carry an EXPLICIT
# 'none' grant (a first-class permission_action_enum value, distinct from an
# unknown role which resolves to None below) — both deny, but 'none' means
# "known role, deliberately no money_trail access".
MONEY_TRAIL_ACTIONS: dict[str, str] = {role: "write" for role in FUNCTIONAL_ROLES}


def action_for_role(role: str) -> Optional[str]:
    """The permission action a role holds on money_trail:
    'read'|'write' for a grant, 'none' for a role deliberately denied access
    (matching the RDS seed), or None if the role is entirely unknown/unmapped.
    Enforced in code, never from RDS, so the gate holds with DATABASE_URL absent.
    Only 'read'/'write' pass the gates below; 'none' and None both deny."""
    return MONEY_TRAIL_ACTIONS.get((role or "").strip())


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


def require_money_permission(x_role: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency: allow only roles with read/write on money_trail."""
    role = _resolve_role(x_role)
    action = action_for_role(role)
    if action not in ("read", "write"):
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' is not permitted to access the money trail "
                    "(financial data is gated by the 'money_trail' permission)."))
    return role


def require_money_write(x_role: Optional[str] = Header(default=None)) -> str:
    """Stricter gate for mutating operations (e.g. running the detection job):
    the role must hold WRITE on money_trail."""
    role = _resolve_role(x_role)
    if action_for_role(role) != "write":
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' needs WRITE on 'money_trail' to run detection.")
    return role
