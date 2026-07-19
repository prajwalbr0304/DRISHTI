"""Admin/governance role gates + the canonical API authorization matrix (Phase 15).

The hackathon maps a Catalyst-authenticated identity to a synthetic demo role
(deployed) and, locally, reads that role from the ``X-Role`` header (UX
simulation). RLS is disabled for the hackathon, so this server-side matrix is the
authorization boundary that the admin console visualises and the API enforces.

The matrix is data (one source of truth) so it can be surfaced by
``GET /admin/identity`` AND asserted by the authorization-matrix tests.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from ..config import get_settings

ROLES = ("investigator", "analyst", "supervisor", "policymaker", "super_admin")

# Permission keys used across the app (aligned with the existing per-module gates
# in cases/permissions.py, intake/guards.py and governance/router.py).
PERMISSIONS = (
    "case_read", "case_write", "intake_write", "intake_review",
    "governance_run", "governance_review", "admin_read", "admin_write",
    "report_generate", "report_global_scope", "notification_manage", "rag_use",
)

# role -> set of granted permissions. super_admin gets everything.
_GRANTS: dict[str, set[str]] = {
    "investigator": {"case_read", "case_write", "intake_write", "governance_run",
                     "report_generate", "notification_manage", "rag_use"},
    "analyst": {"case_read", "governance_run", "report_generate",
                "notification_manage", "rag_use"},
    "supervisor": {"case_read", "intake_write", "intake_review", "governance_run",
                   "governance_review", "admin_read", "report_generate",
                   "notification_manage", "rag_use"},
    # policymaker sees aggregate only: no individual case read, no intake.
    "policymaker": {"report_generate", "rag_use"},
    "super_admin": set(PERMISSIONS),
}


def has_permission(role: str, permission: str) -> bool:
    return permission in _GRANTS.get(role, set())


def authorization_matrix() -> dict[str, dict[str, bool]]:
    """The full role x permission matrix (surfaced by /admin/identity, tested)."""
    return {role: {perm: has_permission(role, perm) for perm in PERMISSIONS}
            for role in ROLES}


def resolve_role(x_role: Optional[str]) -> str:
    role = (x_role or get_settings().default_role or "investigator").strip()
    return role if role in ROLES else (get_settings().default_role or "investigator")


# --- FastAPI dependency gates ----------------------------------------------
def require_admin_read(x_role: Optional[str] = Header(default=None)) -> str:
    """Admin console reads — supervisor + super_admin (operational oversight)."""
    role = resolve_role(x_role)
    if not has_permission(role, "admin_read"):
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot open the admin/governance console — "
                    "this is a supervisory/administration view."))
    return role


def require_admin_write(x_role: Optional[str] = Header(default=None)) -> str:
    """Admin configuration changes — super_admin only (retention/holds/flags/models)."""
    role = resolve_role(x_role)
    if not has_permission(role, "admin_write"):
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot change administration configuration — "
                    "this is a super-admin action."))
    return role
