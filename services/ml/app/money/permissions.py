"""Server-side 'money_trail' permission gate (doc 04 §7, wired fully in Phase 14).

Financial data is sensitive, so every /money endpoint depends on this gate. It
resolves the caller's role (from the X-Role header, falling back to the
configured default until real auth lands in Phase 14) and checks the seeded
role_permissions matrix for resource='money_trail'. A role whose action is
'none' (e.g. policymaker) or unmapped is refused with 403.

This is enforced in SQL/middleware — NOT in any model prompt — so it holds
regardless of how a request is phrased.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from .. import db
from ..config import get_settings

MONEY_RESOURCE = "money_trail"


def action_for_role(role: str) -> Optional[str]:
    """The permission action ('read'|'write'|'none') a role holds on money_trail,
    or None if the role/resource is unmapped. Read under the restricted role."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT rp."action"::text FROM "role_permissions" rp '
                'JOIN "roles" r ON r."role_id" = rp."role_id" '
                'WHERE r."role_name" = %s AND rp."resource" = %s',
                (role, MONEY_RESOURCE))
            row = cur.fetchone()
    return row[0] if row else None


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


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
