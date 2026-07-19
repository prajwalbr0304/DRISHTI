"""Board authorization (Prompt 16 authorization section).

Because AWS PostgreSQL RLS/FORCE RLS remain DISABLED (as requested), the access
boundary is the Catalyst-authenticated API. This module enforces it server-side
in AppSail for every board read, mutation, collaboration and export route:

  * Catalyst Authentication identities map to synthetic IO (investigator),
    Analyst, Supervisor and policymaker/demo-lead roles (the trusted role is the
    server-injected X-Role — see gateway_enforcement.py; in dev it is the demo
    header, still enforced as defence in depth).
  * policymakers/demo-leads have NO board access (boards model sensitive
    investigative material even though all data is synthetic).
  * IOs own/edit assigned-case boards; Analysts use explicitly shared boards;
    Supervisors can share, lock, branch and promote.
  * `investigation_board` (read/write), `board_share` and `board_promote` are
    the enforced permissions.
  * lock, promotion and export require a fresh authenticated confirmation.

Per-BOARD authorization (owner/editor/viewer, out-of-scope share) needs the
board record + collaborator list and lives in service.py; these dependencies are
the coarse role gate (defence in depth), matching the intake/graph pattern.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from ..config import get_settings
from ..intake.guards import require_localhost, synthetic_db_ok

# --- role sets --------------------------------------------------------------
# Boards carry PII-equivalent investigative material -> policymaker/demo-lead
# has NO access at all.
BOARD_DENY_ROLES = {"policymaker"}
# Any role that may touch boards at all (everything except the denied set).
BOARD_ROLES = {"investigator", "analyst", "supervisor", "super_admin"}
# Who may create/own a board.
BOARD_CREATE_ROLES = {"investigator", "analyst", "supervisor", "super_admin"}
# board_share: share/visibility changes are an owner + supervisory action.
BOARD_SHARE_ROLES = {"supervisor", "super_admin"}
# Locking / branching a locked board.
BOARD_LOCK_ROLES = {"supervisor", "super_admin"}
# board_promote: hypothesis -> review proposal.
BOARD_PROMOTE_ROLES = {"supervisor", "super_admin"}


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


def resolve_actor(request: Request) -> str:
    """The demo actor for attribution (audit/BoardActivity). Not a security
    boundary in dev; in deployment the gateway injects the trusted actor."""
    actor = request.headers.get("x-demo-actor")
    if actor and actor.strip():
        return actor.strip()[:120]
    role = _resolve_role(request.headers.get("x-role"))
    return f"demo.{role}"


# --- coarse role gates (FastAPI dependencies) -------------------------------
def require_board_role(x_role: Optional[str] = Header(default=None)) -> str:
    """Any board route: deny the policymaker/demo-lead role entirely."""
    role = _resolve_role(x_role)
    if role in BOARD_DENY_ROLES:
        raise HTTPException(
            status_code=403,
            detail=("Investigation Boards are not available to the "
                    f"'{role}' role — boards model sensitive investigative "
                    "material (aggregate-only roles have no board access)."))
    return role


def require_board_create(x_role: Optional[str] = Header(default=None)) -> str:
    role = require_board_role(x_role)
    if role not in BOARD_CREATE_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' cannot create boards.")
    return role


def require_board_share(x_role: Optional[str] = Header(default=None)) -> str:
    role = require_board_role(x_role)
    if role not in BOARD_SHARE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot share boards (board_share). Sharing, "
                    "visibility changes and collaborator management are an "
                    "owner/supervisor action."))
    return role


def require_board_lock(x_role: Optional[str] = Header(default=None)) -> str:
    role = require_board_role(x_role)
    if role not in BOARD_LOCK_ROLES:
        raise HTTPException(status_code=403,
                            detail=(f"Role '{role}' cannot lock/branch boards — "
                                    "this is an owner/supervisor action."))
    return role


def require_board_promote(x_role: Optional[str] = Header(default=None)) -> str:
    role = require_board_role(x_role)
    if role not in BOARD_PROMOTE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot promote a hypothesis (board_promote). "
                    "Promotion to a review proposal is a supervisory action."))
    return role


# --- write posture guard ----------------------------------------------------
def require_board_write_allowed(request: Request) -> None:
    """Validate the synthetic database / hackathon write guard for board writes.

    Boards persist to Catalyst Data Store (not the operational PG), so this
    validates the synthetic HACKATHON POSTURE (fail-closed): localhost-only in
    staging + explicit hackathon/demo flags, and — when an analytics PG is
    configured — that it too is marked synthetic. Testable without a live DB.
    """
    require_localhost(request)
    s = get_settings()
    if not (s.hackathon_mode and s.demo_data_only):
        raise HTTPException(
            status_code=503,
            detail=("Refusing board write: the service is not in synthetic "
                    "hackathon posture (HACKATHON_MODE/DEMO_DATA_ONLY)."))
    if s.database_url and not synthetic_db_ok():
        raise HTTPException(
            status_code=503,
            detail=("Refusing board write: the configured analytics database is "
                    f"not marked '{s.synthetic_env_expected}'."))


def require_fresh_confirmation(confirmed: bool, action: str) -> None:
    """Lock / promotion / export require a fresh authenticated confirmation.

    In the deployed product this maps to a Catalyst re-auth challenge; at the API
    it is enforced as an explicit, audited second step (``confirm=true``). Without
    it the action is refused with 428 Precondition Required."""
    if not confirmed:
        raise HTTPException(
            status_code=428,
            detail=(f"'{action}' requires a fresh authenticated confirmation. "
                    "Re-confirm (confirm=true) to proceed."))
