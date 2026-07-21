"""Deployment readiness evaluation (Prompt 21 §G.2).

Liveness and readiness are DIFFERENT probes:

  * LIVENESS  (``/health/live``) is a shallow process check. It performs NO
    external dependency checks so a transient dependency outage never triggers
    an AppSail restart loop.
  * READINESS (``/health/ready``) reflects whether the service can actually serve
    traffic on its DEPLOYED OPERATIONAL DATA PLANE. It MUST fail (return
    not-ready) when a mandatory dependency is unavailable:
       - the Catalyst Data Store operational repository is unreachable;
       - gateway-context enforcement is required but no signing secret is set
         (every request would 401 — the auth plane is broken);
       - Catalyst Stratus is selected for application objects but not configured.

    AWS RDS is an ADVISORY analytics dependency only: it is probed for visibility
    but its absence NEVER flips readiness (the operational serving path is Data
    Store / Stratus, which does not need ``DATABASE_URL``).

The pure :func:`evaluate` function takes the pieces it needs so the whole matrix
is deterministic and unit-testable without a database or the Catalyst SDK.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

# A small, always-provisioned operational lookup table used as the Data Store
# reachability probe. It exists in every environment (reference data) so a
# successful bounded query means the operational store is serving.
_DATASTORE_PROBE_TABLE = "State"


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    checks: dict

    def payload(self) -> dict:
        return {"status": "ready" if self.ready else "not_ready",
                "ready": self.ready, "checks": self.checks}


def _probe_datastore(repo_factory: Callable) -> str:
    """Return 'ok' when the operational Data Store repository is reachable.

    Constructs the deployed repository and runs a bounded probe query. Any
    exception (missing SDK/creds, unreachable store) => 'unavailable'. The
    in-memory fake used locally/in tests always succeeds, so offline readiness
    stays green without a database.
    """
    try:
        repo = repo_factory()
        repo.query(_DATASTORE_PROBE_TABLE, limit=1)
        return "ok"
    except Exception:  # noqa: BLE001 — a broken data plane must read as unavailable
        return "unavailable"


def evaluate(
    settings,
    *,
    repo_factory: Optional[Callable] = None,
    gateway_required: Optional[bool] = None,
    signing_secret: Optional[str] = None,
    stratus_enabled: Optional[bool] = None,
    stratus_configured: Optional[bool] = None,
    analytics_ping: Optional[Callable[[], bool]] = None,
) -> ReadinessResult:
    """Evaluate readiness. Mandatory failures flip ``ready`` to False.

    Every argument is injectable so the readiness matrix is unit-testable without
    real Catalyst/RDS. Production wiring is supplied by :func:`current`.
    """
    checks: dict[str, str] = {
        "config": "ok",
        "environment": settings.synthetic_env_expected,
        "hackathon_mode": "on" if settings.hackathon_mode else "off",
    }
    ready = True

    # 1. MANDATORY: operational Data Store repository (the deployed serving source).
    if repo_factory is None:
        from .datastore.repository import get_repository as repo_factory  # type: ignore
    ds = _probe_datastore(repo_factory)
    checks["operational_datastore"] = ds
    if ds != "ok":
        ready = False

    # 2. MANDATORY (when enforced): gateway auth signing secret must be present.
    if gateway_required is None:
        from .gateway_enforcement import enforcement_enabled
        gateway_required = enforcement_enabled()
    if gateway_required:
        if signing_secret is None:
            from .gateway_context import signing_secret as _sig
            signing_secret = _sig()
        if signing_secret:
            checks["gateway_auth"] = "ok"
        else:
            checks["gateway_auth"] = "misconfigured"
            ready = False
    else:
        checks["gateway_auth"] = "not_required"

    # 3. MANDATORY (when selected): Stratus object store must be configured.
    if stratus_enabled is None:
        stratus_enabled = os.getenv("DRISHTI_USE_CATALYST_STRATUS", "").lower() == "true"
    if stratus_enabled:
        if stratus_configured is None:
            stratus_configured = bool(
                os.getenv("DRISHTI_STRATUS_EVIDENCE_BUCKET")
                or os.getenv("DRISHTI_STRATUS_REPORT_BUCKET")
                or os.getenv("DRISHTI_STRATUS_IMPORT_BUCKET"))
        if stratus_configured:
            checks["object_store"] = "ok"
        else:
            checks["object_store"] = "misconfigured"
            ready = False
    else:
        checks["object_store"] = "not_required"

    # 4. ADVISORY ONLY: AWS RDS analytics. Probed for visibility, NEVER fails
    #    readiness (the operational plane does not need DATABASE_URL).
    if analytics_ping is None:
        def analytics_ping() -> bool:
            from . import db
            return db.ping()
    try:
        checks["analytics_db"] = "ok" if analytics_ping() else "unavailable"
    except Exception:  # noqa: BLE001 — advisory probe must not raise or fail readiness
        checks["analytics_db"] = "unavailable"

    return ReadinessResult(ready=ready, checks=checks)


def current(settings) -> ReadinessResult:
    """Production readiness using the real Catalyst/RDS wiring."""
    return evaluate(settings)
