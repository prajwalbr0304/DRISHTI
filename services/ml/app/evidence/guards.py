"""Evidence access + safety guards (Phase 5, Global Contract + prompt2.md §5).

Hackathon access posture, enforced in the API (not just the UI):

  * WRITE endpoints are localhost-only unless a trusted HTTPS edge is configured
    (reuses the same ``intake_writes_localhost_only`` posture).
  * every write refuses unless the target database is explicitly marked synthetic
    (``synthetic_meta.app_environment = 'synthetic_hackathon'``).
  * file upload/download endpoints additionally require a configured private S3
    bucket; without one the API runs metadata-only (503 on upload/download).

Role gates mirror cases/intake: the X-Role header is presentation state (UX
simulation), NOT authentication — real auth is deferred — but the gates are
still enforced server-side as defence in depth.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from .. import db
from ..config import get_settings

# Local demo callers (Starlette TestClient reports host "testclient").
_LOCALHOST = {"127.0.0.1", "::1", "localhost", "testclient"}

# Roles denied individual-case evidence (aggregate-only, PII risk).
EVIDENCE_READ_DENY = {"policymaker"}
# Roles that may create/upload/edit evidence (IO / supervisor / admin register
# and manage evidence). EvidenceOfficer is a future role (post-hackathon auth).
EVIDENCE_WRITE_ROLES = {"investigator", "supervisor", "super_admin"}
# The synthetic-demo reset is destructive of synthetic objects -> admin only.
EVIDENCE_RESET_ROLES = {"super_admin"}

_synthetic_ok: Optional[bool] = None  # cached positive marker check


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


# --- role gates -------------------------------------------------------------
def require_evidence_read(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role in EVIDENCE_READ_DENY:
        raise HTTPException(
            status_code=403,
            detail=(f"Evidence is not available to the '{role}' role — this role "
                    "sees aggregate views only."))
    return role


def require_evidence_write(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role not in EVIDENCE_WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot add or manage evidence — this is an "
                    "investigating/registering-officer action."))
    return role


def require_evidence_reset(x_role: Optional[str] = Header(default=None)) -> str:
    role = _resolve_role(x_role)
    if role not in EVIDENCE_RESET_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot reset synthetic evidence — this is an "
                    "administrator-only demo action."))
    return role


# --- staging guards ---------------------------------------------------------
def require_localhost(request: Request) -> None:
    if not get_settings().intake_writes_localhost_only:
        return
    host = request.client.host if request.client else None
    if host not in _LOCALHOST:
        raise HTTPException(
            status_code=403,
            detail=("Evidence writes are restricted to localhost during the "
                    "hackathon demo (no trusted HTTPS edge configured)."))


def synthetic_db_ok() -> bool:
    """True iff the target DB is marked synthetic. Only a POSITIVE result is
    cached (a transient blip must not permanently block writes)."""
    global _synthetic_ok
    if _synthetic_ok:
        return True
    expected = get_settings().synthetic_env_expected
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT "Value" FROM "synthetic_meta" WHERE "Key"=%s',
                            ("app_environment",))
                row = cur.fetchone()
        ok = bool(row and row[0] == expected)
    except Exception:  # noqa: BLE001 — fail closed, re-check next time
        ok = False
    if ok:
        _synthetic_ok = True
    return ok


def require_synthetic_db() -> None:
    if not synthetic_db_ok():
        raise HTTPException(
            status_code=503,
            detail=("Refusing to write: the target database is not marked "
                    f"'{get_settings().synthetic_env_expected}'. Evidence operates "
                    "on synthetic hackathon data only."))


def require_write_allowed(request: Request) -> None:
    """Combined guard for every evidence write (localhost + synthetic DB)."""
    require_localhost(request)
    require_synthetic_db()


def require_s3_configured() -> None:
    """File upload/download need a provisioned object store (S3 or Catalyst Stratus)."""
    if not get_settings().storage_configured():
        raise HTTPException(
            status_code=503,
            detail=("Evidence file storage is not configured (no S3 bucket or "
                    "Catalyst Stratus evidence bucket). Metadata can still be "
                    "recorded; provision the private bucket to enable uploads/downloads."))


def hackathon_status() -> dict:
    """Flags surfaced to the UI (drives the upload affordance + demo badge)."""
    s = get_settings()
    synthetic = synthetic_db_ok()
    return {
        "hackathon_mode": s.hackathon_mode,
        "demo_data_only": s.demo_data_only,
        "synthetic_db": synthetic,
        "writes_localhost_only": s.intake_writes_localhost_only,
        "s3_configured": s.storage_configured(),
        "upload_enabled": bool(s.storage_configured() and synthetic),
        "max_bytes": s.evidence_max_bytes,
        "allowed_extensions": sorted(s.evidence_allowed_ext_set()),
        "allowed_mime_types": sorted(s.evidence_allowed_mime_set()),
        "presign_expiry_seconds": s.s3_presign_expiry_s,
        "extraction_disabled_note": "File contents are not automatically extracted.",
        "environment_label": "Synthetic Hackathon Demo",
    }
