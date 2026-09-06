"""CCTV monitoring authorization.

Same access model as ``app/disaster/guards.py`` (AWS RLS stays disabled; the
boundary is the Catalyst-authenticated API enforced server-side in AppSail):

  * INTERIM: every command role (app/roles.py) may watch the wall and review
    alerts — a seat with an ASSIGNED synthetic district stays confined to it;
  * ``cctv_review`` and ``cctv_dispatch`` are the enforced permissions on the
    mutating actions;
  * confirming an alert and dispatching a responder each require a FRESH
    authenticated confirmation (428 without it) — two separate human decisions,
    so a single click can never both validate a detection and send a unit;
  * the whole surface has an ops kill-switch (``CCTV_ENABLED``) that reports
    unavailable rather than half-working;
  * every allow/deny decision on a sensitive action is audited (append-only
    CctvActivity).

In deployment the trusted role/actor is injected by the gateway
(gateway_enforcement.py); in dev it is the demo header, still enforced here as
defence in depth.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from ..config import get_settings
from ..intake.guards import require_localhost, synthetic_db_ok
from ..roles import ALL_ROLES, DEFAULT_ROLE, ROLE_SCOPE_LEVEL

# --- role sets --------------------------------------------------------------
# INTERIM ("all roles have access to everything"): every command role may watch
# the wall, review alerts and dispatch. District containment below still applies.
CCTV_READ_ROLES = set(ALL_ROLES)
CCTV_REVIEW_ROLES = set(ALL_ROLES)
CCTV_DISPATCH_ROLES = set(ALL_ROLES)
CCTV_ADMIN_ROLES = set(ALL_ROLES)
# Roles confined to a single assigned district/station (cannot act state-wide).
DISTRICT_SCOPED_ROLES = {r for r, lvl in ROLE_SCOPE_LEVEL.items()
                         if lvl in ("district", "subdivision", "station", "assigned_case")}

# Reasons a human may record when dismissing a proposed alert. A closed list so
# the false-positive trail is aggregatable (it is the detector's feedback signal).
DISMISS_REASONS = (
    "false_positive",     # nothing of the sort is happening in frame
    "duplicate",          # same incident already raised by another camera
    "already_handled",    # a unit is already on it / control room aware
    "not_actionable",     # real but below any police response threshold
    "poor_visibility",    # frame quality too low to judge
    "other",
)


class CctvScope:
    """The resolved actor scope for a request (the analyst seat at the wall)."""

    def __init__(self, role: str, actor: str, district_id: Optional[int],
                 unit_id: Optional[int]):
        self.role = role
        self.actor = actor
        self.district_id = district_id
        self.unit_id = unit_id
        self.is_super = role in {"system_admin"}

    def covers_district(self, district_id: Optional[int]) -> bool:
        """The platform admin covers everywhere. A district-scoped seat that has an
        ASSIGNED district covers only that district; a seat with no assignment
        asserted is not geographically narrowed (interim demo posture)."""
        if self.is_super:
            return True
        if self.role not in CCTV_READ_ROLES:
            return False
        if self.role not in DISTRICT_SCOPED_ROLES or self.district_id is None:
            return True
        return district_id is None or int(district_id) == int(self.district_id)

    def as_dict(self) -> dict:
        return {"role": self.role, "actor": self.actor,
                "district_id": self.district_id, "unit_id": self.unit_id,
                "is_super": self.is_super}


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


def resolve_actor(request: Request) -> str:
    actor = request.headers.get("x-demo-actor")
    if actor and actor.strip():
        return actor.strip()[:120]
    role = _resolve_role(request.headers.get("x-role"))
    return f"demo.{role}"


def _int_header(request: Request, name: str) -> Optional[int]:
    v = request.headers.get(name)
    if v is None or not str(v).strip():
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def resolve_scope(request: Request) -> CctvScope:
    """Resolve the caller's CCTV scope. District/unit come from the same demo
    headers the Emergency Response surface uses (``X-Disaster-District`` /
    ``X-Disaster-Unit``), which simulate the seat the Catalyst-authenticated
    operator is assigned to. Never a security boundary on their own — combined
    with the role gates below."""
    role = _resolve_role(request.headers.get("x-role"))
    return CctvScope(role=role, actor=resolve_actor(request),
                     district_id=_int_header(request, "x-disaster-district"),
                     unit_id=_int_header(request, "x-disaster-unit"))


# --- capability kill switch -------------------------------------------------
def require_cctv_enabled() -> None:
    """Ops kill-switch. When off, every /cctv route reports unavailable instead of
    returning partial data — the surface is either fully on or clearly absent."""
    if not get_settings().cctv_enabled:
        raise HTTPException(
            status_code=503,
            detail=("CCTV monitoring is disabled on this deployment "
                    "(CCTV_ENABLED=false)."))


# --- coarse role gates (FastAPI dependencies) -------------------------------
def require_cctv_read(x_role: Optional[str] = Header(default=None)) -> str:
    """Any CCTV read route (the wall, the queue, camera metadata)."""
    require_cctv_enabled()
    role = _resolve_role(x_role)
    if role not in CCTV_READ_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' has no CCTV monitoring access.")
    return role


def _require_permission(role: str, allowed: set, permission: str) -> str:
    if role not in allowed:
        _record_denied(permission, role)
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' lacks the '{permission}' permission for "
                    "CCTV monitoring actions."))
    return role


def require_cctv_review(x_role: Optional[str] = Header(default=None)) -> str:
    """Confirm / dismiss a proposed alert, or run the analytics pass."""
    require_cctv_enabled()
    return _require_permission(_resolve_role(x_role), CCTV_REVIEW_ROLES, "cctv_review")


def require_cctv_dispatch(x_role: Optional[str] = Header(default=None)) -> str:
    """Propose or advance a nearest-station dispatch."""
    require_cctv_enabled()
    return _require_permission(_resolve_role(x_role), CCTV_DISPATCH_ROLES, "cctv_dispatch")


def require_cctv_admin(x_role: Optional[str] = Header(default=None)) -> str:
    """Register/retire cameras and responders, seed the demo estate."""
    require_cctv_enabled()
    return _require_permission(_resolve_role(x_role), CCTV_ADMIN_ROLES, "cctv_admin")


# --- write posture + fresh confirmation -------------------------------------
def require_cctv_write_allowed(request: Request) -> None:
    """Validate the synthetic hackathon posture (fail-closed) for CCTV writes.

    CCTV data persists to Catalyst Data Store (not the operational PG), so this
    validates the synthetic posture: localhost-only in staging + explicit
    hackathon/demo flags, and — when an analytics PG is configured — that it too
    is marked synthetic. Testable without a live DB."""
    require_localhost(request)
    s = get_settings()
    if not (s.hackathon_mode and s.demo_data_only):
        raise HTTPException(
            status_code=503,
            detail=("Refusing CCTV write: the service is not in synthetic "
                    "hackathon posture (HACKATHON_MODE/DEMO_DATA_ONLY)."))
    if s.database_url and not synthetic_db_ok():
        raise HTTPException(
            status_code=503,
            detail=("Refusing CCTV write: the configured analytics database "
                    f"is not marked '{s.synthetic_env_expected}'."))


def require_fresh_confirmation(confirmed: bool, action: str) -> None:
    """Alert confirmation and responder dispatch each require a fresh
    authenticated confirmation (a Catalyst re-auth challenge in the product; an
    explicit audited ``confirm=true`` at the API). 428 without it."""
    if not confirmed:
        raise HTTPException(
            status_code=428,
            detail=(f"'{action}' requires a fresh authenticated confirmation. "
                    "Re-confirm (confirm=true) to proceed."))


def require_ingest_token(x_cctv_ingest_token: Optional[str] = Header(default=None)) -> None:
    """External detection ingest is authenticated by a shared secret and is
    DISABLED when no secret is configured (fail closed — an open detection sink
    would let anyone manufacture an alert in the review queue)."""
    require_cctv_enabled()
    s = get_settings()
    if not s.cctv_ingest_configured():
        raise HTTPException(
            status_code=503,
            detail=("External detection ingest is disabled: set CCTV_INGEST_TOKEN "
                    "to enable POST /cctv/detections/ingest."))
    supplied = (x_cctv_ingest_token or "").strip()
    # Constant-time compare so a wrong token cannot be discovered by timing.
    import hmac
    if not supplied or not hmac.compare_digest(supplied, s.cctv_ingest_token.strip()):
        _record_denied("cctv_ingest", "external")
        raise HTTPException(status_code=401, detail="unauthorized")


def enforce_district_scope(scope: CctvScope, district_id: Optional[int],
                           action: str) -> None:
    """A district-scoped operator may only act inside its assigned district."""
    if not scope.covers_district(district_id):
        _record_denied(action, scope.role,
                       detail={"assigned": scope.district_id, "target": district_id})
        raise HTTPException(
            status_code=403,
            detail=(f"'{action}' is outside your assigned district "
                    f"({scope.district_id}). A district-scoped seat may only act "
                    "within its assigned synthetic district/unit."))


# --- audit of allow/deny decisions ------------------------------------------
def _record_denied(action: str, role: str, detail: Optional[dict] = None) -> None:
    """Best-effort append-only audit of a DENY decision (never raises)."""
    try:
        from .repo import cctv_repo
        cctv_repo().append_activity(
            "access", f"{action}", actor=f"role:{role}", action="access.denied",
            diff={"action": action, "role": role, **(detail or {})})
    except Exception:  # noqa: BLE001 — auditing a denial must never break the request
        pass
