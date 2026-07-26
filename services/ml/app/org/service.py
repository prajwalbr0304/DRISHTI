"""Organizational service: SUPERADMIN credential/role provisioning + trusted
scope resolution (Prompt 20 Part B).

The SUPERADMIN provisions synthetic application credentials (rows in ``users``),
assigns each credential a functional role (``roles``) and an organizational scope
(``users.unit_id`` -> Unit -> District), and can activate/deactivate them. In the
deployed submission the actual sign-in secret is owned by Catalyst Authentication
(``must_reset_password`` marks a fresh Catalyst invite); real directory/SSO
synchronisation with the police establishment is post-hackathon.

Reads use ``db.ro_conn``; writes use ``db.rw_conn`` (or an injected connection so
the write-path tests can roll back). Every write appends an audit event.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from .. import audit, db
from ..roles import FUNCTIONAL_ROLES, ROLE_DESCRIPTIONS
from . import hierarchy
from .scope import ScopeContext

# Functional roles that SUPERADMIN may provision, and the DB seed description
# for each — the canonical command seats in app/roles.py.
_SEED_ROLES = {role: ROLE_DESCRIPTIONS.get(role, role) for role in FUNCTIONAL_ROLES}

# role_permissions resources the seed grants. INTERIM ("all roles have access to
# everything"): every seeded role receives WRITE on every resource.
_GRANT_RESOURCES = (
    "command_center", "cases", "people_entities", "network_analysis",
    "money_trail", "map", "analytics", "ask_drishti", "admin_governance", "pii",
)
_ROLE_GRANTS = {role: {resource: "write" for resource in _GRANT_RESOURCES}
                for role in FUNCTIONAL_ROLES}


class OrgError(ValueError):
    """Bad request (unknown role, duplicate username, missing user)."""


@contextmanager
def _writer(conn):
    """Yield (conn, owns): reuse an injected connection (tests roll it back) or
    open a committing rw_conn."""
    if conn is not None:
        yield conn, False
    else:
        with db.rw_conn() as c:
            yield c, True


def _role_id(cur, role_name: str, *, create: bool = False) -> Optional[int]:
    cur.execute('SELECT "role_id" FROM "roles" WHERE "role_name"=%s', (role_name,))
    r = cur.fetchone()
    if r:
        return int(r[0])
    if not create:
        return None
    if role_name not in _SEED_ROLES:
        raise OrgError(f"Unknown functional role: {role_name!r}")
    cur.execute('INSERT INTO "roles" ("role_name","description","is_system") '
                'VALUES (%s,%s,TRUE) ON CONFLICT ("role_name") DO UPDATE '
                'SET "description"=EXCLUDED."description" RETURNING "role_id"',
                (role_name, _SEED_ROLES[role_name]))
    return int(cur.fetchone()[0])


def ensure_roles(conn=None) -> dict:
    """Idempotently ensure every functional role exists with its permission
    grants (interim: full access for all). Returns a summary."""
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            created = []
            role_ids: dict[str, int] = {}
            for name in _SEED_ROLES:
                cur.execute('SELECT "role_id" FROM "roles" WHERE "role_name"=%s', (name,))
                if cur.fetchone() is None:
                    created.append(name)
                role_ids[name] = _role_id(cur, name, create=True)
            for name, grants in _ROLE_GRANTS.items():
                rid = role_ids.get(name) or _role_id(cur, name, create=True)
                for resource, action in grants.items():
                    cur.execute(
                        'INSERT INTO "role_permissions" ("role_id","resource","action") '
                        'VALUES (%s,%s,%s) ON CONFLICT ("role_id","resource","action") '
                        'DO NOTHING', (rid, resource, action))
    return {"roles_created": created, "role_ids": role_ids}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def list_roles() -> dict:
    """Roles + their permission grants + functional-role metadata."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "role_id","role_name","description","is_system" '
                        'FROM "roles" ORDER BY "role_id"')
            roles = {int(r[0]): {"role_id": int(r[0]), "role_name": r[1],
                                 "description": r[2], "is_system": bool(r[3]),
                                 "permissions": {}} for r in cur.fetchall()}
            cur.execute('SELECT "role_id","resource","action" FROM "role_permissions" '
                        'ORDER BY "role_id","resource"')
            for rid, resource, action in cur.fetchall():
                if int(rid) in roles:
                    roles[int(rid)]["permissions"][resource] = action
    items = list(roles.values())
    known = {r["role_name"] for r in items}
    return {"total": len(items), "items": items,
            "functional_roles": list(hierarchy.FUNCTIONAL_ROLES),
            "missing_roles": [r for r in hierarchy.FUNCTIONAL_ROLES if r not in known]}


def list_users() -> dict:
    """Application credentials with role name + unit/district scope."""
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT u."user_id", u."username", u."display_name", r."role_name", '
                'u."unit_id", un."UnitName", d."DistrictID", d."DistrictName", '
                'u."is_active", u."must_reset_password", u."created_at" '
                'FROM "users" u JOIN "roles" r ON r."role_id"=u."role_id" '
                'LEFT JOIN "Unit" un ON un."UnitID"=u."unit_id" '
                'LEFT JOIN "District" d ON d."DistrictID"=un."DistrictID" '
                'ORDER BY u."user_id"')
            items = []
            for row in cur.fetchall():
                role = row[3]
                items.append({
                    "user_id": int(row[0]), "username": row[1], "display_name": row[2],
                    "role": role, "unit_id": row[4], "unit_name": row[5],
                    "district_id": row[6], "district_name": row[7],
                    "is_active": bool(row[8]), "must_reset_password": bool(row[9]),
                    "created_at": row[10].isoformat() if row[10] else None,
                    "scope_level": hierarchy.scope_level_for_role(role),
                })
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# Writes (SUPERADMIN) — create credential, assign role, set scope, activate
# ---------------------------------------------------------------------------
def _user_row(cur, user_id: int) -> Optional[dict]:
    cur.execute(
        'SELECT u."user_id", u."username", u."display_name", r."role_name", '
        'u."unit_id", u."is_active", u."must_reset_password" '
        'FROM "users" u JOIN "roles" r ON r."role_id"=u."role_id" '
        'WHERE u."user_id"=%s', (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {"user_id": int(row[0]), "username": row[1], "display_name": row[2],
            "role": row[3], "unit_id": row[4], "is_active": bool(row[5]),
            "must_reset_password": bool(row[6])}


def create_user(username: str, display_name: Optional[str], role: str,
                unit_id: Optional[int] = None, *, actor: Optional[str] = None,
                conn=None) -> dict:
    """Provision a synthetic application credential and assign it a role + scope.

    This is the SUPERADMIN "create a credential for a role" action: a new
    ``users`` row, mapped to a functional role, optionally scoped to a Unit.
    ``must_reset_password`` is TRUE (a fresh Catalyst invite in the deployed
    product)."""
    username = (username or "").strip()
    if not username:
        raise OrgError("username is required")
    if role not in _SEED_ROLES:
        raise OrgError(f"Unknown functional role: {role!r}")
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            cur.execute('SELECT 1 FROM "users" WHERE "username"=%s', (username,))
            if cur.fetchone():
                raise OrgError(f"username already exists: {username!r}")
            rid = _role_id(cur, role, create=True)
            if unit_id is not None:
                cur.execute('SELECT 1 FROM "Unit" WHERE "UnitID"=%s', (int(unit_id),))
                if cur.fetchone() is None:
                    raise OrgError(f"Unit {unit_id} not found")
            cur.execute(
                'INSERT INTO "users" ("username","display_name","role_id","unit_id",'
                '"is_active","must_reset_password") VALUES (%s,%s,%s,%s,TRUE,TRUE) '
                'RETURNING "user_id"',
                (username, display_name or username, rid, unit_id))
            uid = int(cur.fetchone()[0])
            out = _user_row(cur, uid)
            audit.record(audit.Action.CREATE, "user", uid, actor=actor, conn=c,
                         detail={"username": username, "role": role, "unit_id": unit_id,
                                 "credential": "synthetic-catalyst-invite"})
    return out


def assign_role(user_id: int, role: str, *, actor: Optional[str] = None, conn=None) -> dict:
    """Assign / change the functional role of an existing credential."""
    if role not in _SEED_ROLES:
        raise OrgError(f"Unknown functional role: {role!r}")
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            rid = _role_id(cur, role, create=True)
            cur.execute('UPDATE "users" SET "role_id"=%s, "UpdatedAt"=now() '
                        'WHERE "user_id"=%s', (rid, int(user_id)))
            if cur.rowcount == 0:
                raise OrgError(f"user {user_id} not found")
            out = _user_row(cur, int(user_id))
            audit.record(audit.Action.UPDATE, "user_role", user_id, actor=actor, conn=c,
                         detail={"role": role})
    return out


def set_scope(user_id: int, unit_id: Optional[int], *, actor: Optional[str] = None,
              conn=None) -> dict:
    """Assign / clear the organizational scope (Unit -> District) of a credential."""
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            if unit_id is not None:
                cur.execute('SELECT 1 FROM "Unit" WHERE "UnitID"=%s', (int(unit_id),))
                if cur.fetchone() is None:
                    raise OrgError(f"Unit {unit_id} not found")
            cur.execute('UPDATE "users" SET "unit_id"=%s, "UpdatedAt"=now() '
                        'WHERE "user_id"=%s', (unit_id, int(user_id)))
            if cur.rowcount == 0:
                raise OrgError(f"user {user_id} not found")
            out = _user_row(cur, int(user_id))
            audit.record(audit.Action.UPDATE, "user_scope", user_id, actor=actor, conn=c,
                         detail={"unit_id": unit_id})
    return out


def set_active(user_id: int, active: bool, *, actor: Optional[str] = None, conn=None) -> dict:
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            cur.execute('UPDATE "users" SET "is_active"=%s, "UpdatedAt"=now() '
                        'WHERE "user_id"=%s', (bool(active), int(user_id)))
            if cur.rowcount == 0:
                raise OrgError(f"user {user_id} not found")
            out = _user_row(cur, int(user_id))
            audit.record(audit.Action.UPDATE, "user_active", user_id, actor=actor, conn=c,
                         detail={"is_active": bool(active)})
    return out


# ---------------------------------------------------------------------------
# Trusted scope resolution (server-side; never a browser header)
# ---------------------------------------------------------------------------
def resolve_scope_for_user(*, username: Optional[str] = None,
                           user_id: Optional[int] = None, conn=None) -> ScopeContext:
    """Derive the caller's :class:`ScopeContext` from the TRUSTED user record
    (role + unit assignment). Raises OrgError if the user is unknown/inactive."""
    from .scope import derive_scope
    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            if user_id is not None:
                cur.execute(
                    'SELECT u."user_id",u."username",r."role_name",u."unit_id",un."DistrictID",'
                    'u."is_active" FROM "users" u JOIN "roles" r ON r."role_id"=u."role_id" '
                    'LEFT JOIN "Unit" un ON un."UnitID"=u."unit_id" WHERE u."user_id"=%s',
                    (int(user_id),))
            else:
                cur.execute(
                    'SELECT u."user_id",u."username",r."role_name",u."unit_id",un."DistrictID",'
                    'u."is_active" FROM "users" u JOIN "roles" r ON r."role_id"=u."role_id" '
                    'LEFT JOIN "Unit" un ON un."UnitID"=u."unit_id" WHERE u."username"=%s',
                    ((username or "").strip(),))
            row = cur.fetchone()
    finally:
        if owns:
            c.close()
    if not row:
        raise OrgError("unknown user")
    if not bool(row[5]):
        raise OrgError("user is inactive")
    return derive_scope(row[2], user_id=int(row[0]), username=row[1],
                        district_id=row[4], unit_id=row[3],
                        source="trusted-user-record")
