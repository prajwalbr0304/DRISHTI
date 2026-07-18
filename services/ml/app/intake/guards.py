"""Intake access + safety guards (Phase 2/3, prompt2.md §F + Global Contract).

Hackathon access posture, enforced in the API (not just the UI):

  * WRITE endpoints are restricted to localhost callers unless a trusted HTTPS
    edge is configured (no accidental public exposure).
  * every write refuses unless the target database is explicitly marked
    synthetic (synthetic_meta.app_environment = 'synthetic_hackathon') — the
    server must never mutate a database that is not marked synthetic.
  * the canonical case-creating transitions (submit-for-review + approve) are
    enabled by ``intake_submit_enabled`` (Phase 3 turns this on by default now
    that hackathon mode is verified: API-only DB access, synthetic-data guards,
    restricted CORS, RLS disabled). They can be re-gated by env if needed.

Role gates mirror cases/permissions.py: the X-Role header is presentation state
(UX simulation / demo view), NOT authentication or a security boundary — real
auth/authorization is deferred post-hackathon — but the gates are still enforced
server-side as defence in depth.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from .. import db
from ..config import get_settings

# Local demo callers (Starlette TestClient reports host "testclient").
_LOCALHOST = {"127.0.0.1", "::1", "localhost", "testclient"}

# Roles denied individual-case intake (aggregate-only, PII risk) — as in cases.
INTAKE_READ_DENY = {"policymaker"}
# Roles that may create/edit an intake draft (SHO/IO/admin register FIRs).
INTAKE_WRITE_ROLES = {"investigator", "supervisor", "super_admin"}
# Roles that may approve/reject/return a submitted draft (supervisory review).
INTAKE_REVIEW_ROLES = {"supervisor", "super_admin"}

_synthetic_ok: Optional[bool] = None  # cached marker check


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


# --- role gates -------------------------------------------------------------
def require_intake_read(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role in INTAKE_READ_DENY:
        raise HTTPException(
            status_code=403,
            detail=(f"Intake is not available to the '{role}' role — this role "
                    "sees aggregate views only."))
    return role


def require_intake_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role not in INTAKE_WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot create or edit FIR/case intake — "
                    "this is an investigating/registering-officer action."))
    return role


def require_intake_review(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role not in INTAKE_REVIEW_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot review intake submissions — approval/"
                    "return is a supervisory action."))
    return role


# --- staging guards ---------------------------------------------------------
def require_localhost(request: Request) -> None:
    """Intake writes are localhost-only until Prompt 3 (prompt2.md §F)."""
    if not get_settings().intake_writes_localhost_only:
        return
    host = request.client.host if request.client else None
    if host not in _LOCALHOST:
        raise HTTPException(
            status_code=403,
            detail=("Intake writes are restricted to localhost during the "
                    "hackathon staging phase (Prompt 3 owns the governed access path)."))


def synthetic_db_ok() -> bool:
    """True iff the target DB is marked synthetic_meta.app_environment=expected.

    Only a POSITIVE result is cached: the synthetic marker never changes once
    confirmed, but a transient connectivity blip must not poison the guard into
    permanently blocking writes (fail-closed, but self-healing on re-check)."""
    global _synthetic_ok
    if _synthetic_ok:
        return True
    expected = get_settings().synthetic_env_expected
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT "Value" FROM "synthetic_meta" WHERE "Key"=%s',
                    ("app_environment",))
                row = cur.fetchone()
        ok = bool(row and row[0] == expected)
    except Exception:  # noqa: BLE001 — fail closed, re-check next time
        ok = False
    if ok:
        _synthetic_ok = True
    return ok


def require_synthetic_db() -> None:
    """Refuse a write unless the DB is explicitly marked synthetic (Contract §18)."""
    if not synthetic_db_ok():
        raise HTTPException(
            status_code=503,
            detail=("Refusing to write: the target database is not marked "
                    f"'{get_settings().synthetic_env_expected}'. Intake operates on "
                    "synthetic hackathon data only."))


def require_write_allowed(request: Request) -> None:
    """Combined guard for every intake write (localhost + synthetic DB)."""
    require_localhost(request)
    require_synthetic_db()


def require_submit_enabled() -> None:
    """Gate the canonical case-creating transitions.

    Phase 3 enables these by default (hackathon-mode verification is complete:
    API-only DB access, synthetic-data guards, restricted CORS, RLS disabled).
    They can be re-gated by setting INTAKE_SUBMIT_ENABLED=false."""
    if not get_settings().intake_submit_enabled:
        raise HTTPException(
            status_code=409,
            detail=("Submit/approve is disabled by server configuration "
                    "(INTAKE_SUBMIT_ENABLED=false). Drafts can still be saved and "
                    "validated."))


def hackathon_status() -> dict:
    """Flags surfaced to the UI (drives the submit-gate + 'Synthetic Demo' badge)."""
    s = get_settings()
    synthetic = synthetic_db_ok()
    submit_enabled = bool(s.intake_submit_enabled and synthetic)
    reasons: list[str] = []
    if not s.intake_submit_enabled:
        reasons.append("Submit is disabled by server configuration "
                       "(INTAKE_SUBMIT_ENABLED=false).")
    if not synthetic:
        reasons.append("Target database is not marked synthetic.")
    return {
        "hackathon_mode": s.hackathon_mode,
        "demo_data_only": s.demo_data_only,
        "synthetic_db": synthetic,
        "writes_localhost_only": s.intake_writes_localhost_only,
        "submit_enabled": submit_enabled,
        "submit_disabled_reason": " ".join(reasons) or None,
        "environment_label": "Synthetic Hackathon Demo",
    }
