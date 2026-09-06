"""Prompt 21 §E — Catalyst identity + authorization at the gateway boundary.

Proves the AppSail side of the role mapper:
  * the canonical six functional roles stay in sync across hierarchy.py,
    gateway_context.py and (by mirror) the Node gateway_api mapper;
  * a signed context for each of the six roles verifies and carries its
    server-resolved organizational scope;
  * an unknown/ambiguous role or a malformed scope in a signed context is
    REJECTED (never silently coerced);
  * the browser can never smuggle a role/district/unit past the boundary
    (enforcement strips client headers and injects the trusted role + scope);
  * scope derived from the signed context matches the backend allow/deny model.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

os.environ["DRISHTI_DISABLE_DB_TESTS"] = "1"
os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402

from app import gateway_context as gc  # noqa: E402
from app.org import hierarchy, scope as scope_mod  # noqa: E402

_SECRET = "test-signing-secret-do-not-ship"


def _mint(payload: dict, secret: str = _SECRET) -> tuple[str, str]:
    """Mint a signed context exactly like the Node signers (base64url(JSON) +
    hex HMAC-SHA256 over the payload string)."""
    raw = json.dumps(payload).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return b64, sig


def _ctx(role="investigating_officer", *, scope="gateway", district_id=None, unit_id=None,
         scope_level=None, nonce="n", extra=None):
    now = gc._now_ms()
    p = {"scope": scope, "aud": gc.DEFAULT_AUDIENCE, "role": role,
         "ts": now, "exp": now + 60_000, "nonce": nonce, "request_id": "r1",
         "user_id": "u-1", "email": "u@example.gov"}
    if district_id is not None:
        p["district_id"] = district_id
    if unit_id is not None:
        p["unit_id"] = unit_id
    if scope_level is not None:
        p["scope_level"] = scope_level
    if extra:
        p.update(extra)
    return p


def test_functional_roles_in_sync():
    assert set(gc.FUNCTIONAL_ROLES) == set(hierarchy.FUNCTIONAL_ROLES)
    # Six APPLICATION roles, not ten presentation seats. ADGP and DIG share
    # senior_command and differ by scope_type; SP and CP share district_command.
    assert len(gc.FUNCTIONAL_ROLES) == 6


@pytest.mark.parametrize("role", sorted(hierarchy.FUNCTIONAL_ROLES))
def test_each_command_role_verifies(role):
    b64, sig = _mint(_ctx(role=role, nonce=f"n-{role}"))
    ctx = gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False,
                                   expected_audience=gc.DEFAULT_AUDIENCE)
    assert ctx.role == role
    assert ctx.is_user


def test_unknown_role_is_rejected():
    b64, sig = _mint(_ctx(role="administrator", nonce="n-bad"))  # not one of six
    with pytest.raises(gc.ContextError):
        gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)


def test_ambiguous_scope_is_rejected():
    b64, sig = _mint(_ctx(role="sho", district_id="not-a-number", nonce="n-amb"))
    with pytest.raises(gc.ContextError):
        gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)


def test_signed_scope_is_parsed():
    b64, sig = _mint(_ctx(role="district_command", district_id=7, unit_id=42,
                          scope_level="district", nonce="n-scope"))
    ctx = gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)
    assert ctx.role == "district_command"
    assert ctx.district_id == 7
    assert ctx.unit_id == 42
    assert ctx.scope_level == "district"


def test_superseded_role_in_a_signed_context_is_rejected():
    """Defence in depth, and a deployment tripwire.

    The gateway translates superseded role names (dysp_acp, cyber_cell, ...) before
    it mints a context, so AppSail should never see one. If it does, the two sides
    have drifted — a stale gateway function against a current AppSail — and the
    right response is to refuse rather than to guess which seat was meant.
    """
    for stale in ("dysp_acp", "cyber_cell", "adgp_igp_range", "super_admin"):
        b64, sig = _mint(_ctx(role=stale, district_id=7, unit_id=42,
                              scope_level="district", nonce=f"n-{stale}"))
        with pytest.raises(gc.ContextError):
            gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)


def test_service_scope_defaults_role_and_is_not_a_user():
    b64, sig = _mint(_ctx(role="", scope="service", nonce="n-svc",
                          extra={"source": "cron_forecast"}))
    ctx = gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)
    assert ctx.is_service and not ctx.is_user
    assert ctx.role in gc.FUNCTIONAL_ROLES  # defaulted, never invalid


def test_scope_from_gateway_context_matches_backend_model():
    b64, sig = _mint(_ctx(role="sho", district_id=3, unit_id=None,
                          scope_level="district", nonce="n-map"))
    ctx = gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=False)
    sc = scope_mod.scope_from_gateway_context(ctx)
    assert sc.role == "sho"
    assert sc.district_ids == frozenset({3})
    assert sc.source == "signed-gateway-context"


def test_enforcement_strips_client_role_and_scope_headers():
    """A browser-supplied X-Role / X-DRISHTI-District must be discarded and the
    server-trusted role + scope injected from the verified context."""
    from app.gateway_context import GatewayContext
    from app.gateway_enforcement import _inject_trusted_identity

    class _Req:
        def __init__(self, headers):
            self.scope = {"headers": headers}

    spoofed = [
        (b"x-role", b"system_admin"),               # spoofed elevation attempt
        (b"x-drishti-district", b"999"),           # spoofed scope
        (b"content-type", b"application/json"),
    ]
    req = _Req(list(spoofed))
    ctx = GatewayContext(scope="gateway", request_id="r", ts=0, exp=0, nonce="n",
                         role="investigating_officer", user_id="u-1", district_id=5,
                         scope_level="assigned_case")
    _inject_trusted_identity(req, ctx)
    hdrs = dict(req.scope["headers"])
    assert hdrs[b"x-role"] == b"investigating_officer"      # trusted role, not super_admin
    assert hdrs[b"x-drishti-district"] == b"5"     # trusted scope, not 999
    # exactly one x-role header remains (the spoofed one was stripped)
    assert sum(1 for k, _ in req.scope["headers"] if k == b"x-role") == 1


def test_authz_matrix_actual_matches_expected():
    """Repeatable in-process re-run of the Prompt 21 §E.4 allow/deny matrix:
    the REAL backend decision for every case equals the approved expectation
    (same cases the artifact generator + auth-matrix skill verify)."""
    from tools import gen_authz_matrix as g

    mismatches = []
    for role, assign, resource, action, target, expected in g._CASES:
        actual = g._actual(role, assign, resource, action, target)
        if actual != expected:
            mismatches.append(
                f"{role}/{resource}/{action}"
                f"{('/d'+str(assign)) if assign is not None else ''}"
                f"{('->t'+str(target)) if target is not None else ''}: "
                f"expected {expected}, got {actual}")
    assert not mismatches, "authz matrix mismatches:\n" + "\n".join(mismatches)
    # every one of the six roles is represented in the matrix
    assert {c[0] for c in g._CASES} == set(hierarchy.FUNCTIONAL_ROLES)


def test_nonce_replay_rejected_single_instance():
    """A signed context nonce may be consumed exactly once (Prompt 21 §G.1
    single-instance replay guard). The second use of the same nonce is rejected."""
    b64, sig = _mint(_ctx(role="investigating_officer", nonce="replay-once"))
    gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=True)  # first use ok
    with pytest.raises(gc.ContextError):
        gc.verify_signed_context(b64, sig, secret=_SECRET, check_replay=True)  # replay


def test_appsail_pinned_to_single_instance():
    """Prompt 21 §G.1 instance correctness: AppSail is pinned to exactly one
    instance so in-process ID allocation + nonce replay are correct, and
    DATABASE_URL must not be set for CRUD (§B.5)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    deploy = json.loads((root / "infra" / "catalyst" / "appsail"
                        / "appsail.deploy.json").read_text(encoding="utf-8"))
    assert deploy["instances"]["min"] == 1
    assert deploy["instances"]["max"] == 1          # pinned single instance
    # Prompt 23 Option A (documented deviation, see appsail.deploy.json
    # database_url_policy): DATABASE_URL is an OPTIONAL server-to-server RDS
    # connection for the not-yet-migrated crime-domain CRUD, never REQUIRED to
    # boot. The DB-free posture invariant (mandatory Board/Disaster/health/read
    # journeys run without a DB) is preserved: DATABASE_URL must NOT be a
    # required key. The browser never reaches RDS (gateway -> signed context ->
    # AppSail -> RDS).
    assert "DATABASE_URL" not in deploy["env_var_keys"]["required"]
    assert "DATABASE_URL" in deploy["env_var_keys"]["optional"]
    assert deploy["health_check_path"] == "/health/ready"
    assert deploy["liveness_path"] == "/health/live"


def test_allow_deny_matrix_all_command_roles():
    """Sanity-check the backend allow/deny model for every role (full matrix is
    generated + verified by the auth-matrix artifact).

    Evaluated at each role's DEFAULT scope. The two roles unpinned by remit hold
    everything; the four that must be posted hold their non-geographic
    capabilities and are refused anything geographic until they are posted.
    Containment for a POSTED seat is asserted in test_org_scope.py."""
    m = scope_mod.matrix_for_roles()
    assert set(m.keys()) == set(hierarchy.FUNCTIONAL_ROLES)

    unpinned_by_remit = {"dgp_state_command", "system_admin"}
    geographic = {"case_detail", "disaster_approval"}

    for role in hierarchy.FUNCTIONAL_ROLES:
        assert set(m[role]) == set(scope_mod.MATRIX_ACTIONS), role
        for action in scope_mod.MATRIX_ACTIONS:
            expected = role in unpinned_by_remit or action not in geographic
            assert m[role][action] is expected, (role, action)
