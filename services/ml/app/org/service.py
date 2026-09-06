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

import json
from contextlib import contextmanager
from typing import Optional

from .. import audit, db
from .. import roles as _roles
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


def _scope_type_for_anchor(role: str, *, unit_id: Optional[int] = None,
                           district_id: Optional[int] = None,
                           range_id: Optional[int] = None,
                           wing_id: Optional[int] = None) -> str:
    """Pick the scope_type implied by a role and the anchor being set.

    Setting an anchor without setting scope_type is the bug this exists to
    prevent: the row would keep scope_type='unresolved', which is fail-closed, so
    the seat would be posted on paper and see nothing in practice.
    """
    allowed = _roles.scope_types_for_role(role)
    if wing_id is not None:
        return "wing"
    if range_id is not None:
        return "range"
    if district_id is not None:
        # A district_command role may be either; prefer the commissionerate
        # reading only when that is the sole option its role permits.
        return "commissionerate" if allowed == ("commissionerate",) else "district"
    if unit_id is not None:
        # station vs assigned_case is a property of the ROLE, not of the anchor:
        # both anchor on a unit.
        if "station" in allowed:
            return "station"
        if "assigned_case" in allowed:
            return "assigned_case"
        return "station"
    # Anchor cleared. Fall back to whatever the role can hold without one.
    if allowed and allowed[0] in ("state", "platform"):
        return allowed[0]
    return "unresolved"


def set_scope(user_id: int, unit_id: Optional[int], *, actor: Optional[str] = None,
              district_id: Optional[int] = None, range_id: Optional[int] = None,
              wing_id: Optional[int] = None, scope_type: Optional[str] = None,
              conn=None) -> dict:
    """Assign / clear a credential's organizational scope.

    Writes scope_type alongside the anchor, and validates the pair against the
    role's allowed_scope_types (rule 4 of the custom-role contract) so the API
    cannot create a seat state the CHECK constraint would refuse.
    """
    with _writer(conn) as (c, _owns):
        with c.cursor() as cur:
            if unit_id is not None:
                cur.execute('SELECT 1 FROM "Unit" WHERE "UnitID"=%s', (int(unit_id),))
                if cur.fetchone() is None:
                    raise OrgError(f"Unit {unit_id} not found")
            if district_id is not None:
                cur.execute('SELECT 1 FROM "District" WHERE "DistrictID"=%s',
                            (int(district_id),))
                if cur.fetchone() is None:
                    raise OrgError(f"District {district_id} not found")

            cur.execute('SELECT r."role_name" FROM "users" u '
                        'JOIN "roles" r ON r."role_id"=u."role_id" '
                        'WHERE u."user_id"=%s', (int(user_id),))
            row = cur.fetchone()
            if not row:
                raise OrgError(f"user {user_id} not found")
            role = row[0]

            st = (scope_type or "").strip() or _scope_type_for_anchor(
                role, unit_id=unit_id, district_id=district_id,
                range_id=range_id, wing_id=wing_id)

            if st != "unresolved" and not _roles.scope_type_allowed(role, st):
                raise OrgError(
                    f"role {role!r} cannot be issued at scope_type {st!r} "
                    f"(allowed: {', '.join(_roles.scope_types_for_role(role)) or 'any'})")

            cur.execute('UPDATE "users" SET "unit_id"=%s, "district_id"=%s, '
                        '"range_id"=%s, "wing_id"=%s, "scope_type"=%s, '
                        '"updated_by"=%s, "UpdatedAt"=now() WHERE "user_id"=%s',
                        (unit_id, district_id, range_id, wing_id, st, actor,
                         int(user_id)))
            out = _user_row(cur, int(user_id))
            audit.record(audit.Action.UPDATE, "user_scope", user_id, actor=actor, conn=c,
                         detail={"unit_id": unit_id, "district_id": district_id,
                                 "range_id": range_id, "wing_id": wing_id,
                                 "scope_type": st})
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
_SEAT_SELECT = '''
SELECT u."user_id", u."username", r."role_name", u."scope_type",
       u."unit_id", u."wing_id", u."range_id",
       COALESCE(u."district_id", un."DistrictID") AS district_id,
       u."is_active", u."rank_label", u."designation_label", u."posting_label",
       u."is_lead_investigator", u."display_name"
  FROM "users" u
  JOIN "roles" r ON r."role_id" = u."role_id"
  LEFT JOIN "Unit" un ON un."UnitID" = u."unit_id"
 WHERE {predicate}
'''


def _range_district_ids(cur, range_id: int) -> list[int]:
    """Districts belonging to a range. A range seat is only as wide as its
    member districts, so this expansion IS the scope."""
    cur.execute('SELECT "DistrictID" FROM "District" WHERE "RangeID"=%s AND "Active"',
                (int(range_id),))
    return [int(r[0]) for r in cur.fetchall()]


def _wing_crime_head_ids(cur, wing_id: int) -> Optional[list[int]]:
    """Crime heads a wing is accountable for, or None when it covers every head.

    No rows means "all heads" by design (Crime & Technical Services owns the whole
    taxonomy), which is why an empty result returns None rather than an empty list
    -- an empty list would scope the wing to nothing.
    """
    cur.execute('SELECT "CrimeHeadID" FROM "WingCrimeHead" WHERE "WingID"=%s',
                (int(wing_id),))
    heads = [int(r[0]) for r in cur.fetchall()]
    return heads or None


def resolve_scope_for_user(*, username: Optional[str] = None,
                           user_id: Optional[int] = None, conn=None) -> ScopeContext:
    """Derive the caller's :class:`ScopeContext` from the TRUSTED seat record.

    Reads users.scope_type plus whichever anchor that scope_type requires
    (wing_id / range_id / district_id / unit_id), never a browser-supplied value.
    A range seat is expanded to its member districts and a wing seat to its crime
    heads, both here, so the pure scope functions stay DB-free.

    Raises OrgError if the seat is unknown or inactive.
    """
    from .scope import derive_scope
    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            if user_id is not None:
                cur.execute(_SEAT_SELECT.format(predicate='u."user_id"=%s'),
                            (int(user_id),))
            else:
                cur.execute(_SEAT_SELECT.format(predicate='u."username"=%s'),
                            ((username or "").strip(),))
            row = cur.fetchone()
            if not row:
                raise OrgError("unknown user")
            if not bool(row[8]):
                raise OrgError("user is inactive")

            (uid, uname, role_name, scope_type, unit_id, wing_id, range_id,
             district_id, _active, rank_label, desig_label, _posting,
             is_lead, _display) = row

            district_ids = None
            crime_head_ids = None
            if scope_type == "range" and range_id is not None:
                district_ids = _range_district_ids(cur, range_id)
            elif scope_type == "wing" and wing_id is not None:
                crime_head_ids = _wing_crime_head_ids(cur, wing_id)
    finally:
        if owns:
            c.close()

    return derive_scope(
        role_name, user_id=int(uid), username=uname,
        rank=rank_label, designation=desig_label,
        scope_type=scope_type, unit_id=unit_id, wing_id=wing_id,
        range_id=range_id, district_id=district_id,
        district_ids=district_ids, crime_head_ids=crime_head_ids,
        is_lead_investigator=bool(is_lead),
        source="trusted-seat-record")


# ---------------------------------------------------------------------------
# Organizational reference reads (wings, ranges) + the seat directory
# ---------------------------------------------------------------------------
def list_wings(conn=None) -> dict:
    """Six ADGP functional wings with the crime heads each is accountable for.

    A wing with no WingCrimeHead rows covers EVERY head (Crime & Technical
    Services owns the whole taxonomy), reported as covers_all_heads rather than
    as an empty remit.
    """
    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            cur.execute('''
                SELECT w."WingID", w."WingCode", w."WingName", w."Description",
                       COALESCE(array_agg(ch."CrimeHeadID"
                                ORDER BY ch."CrimeHeadID")
                                FILTER (WHERE ch."CrimeHeadID" IS NOT NULL), '{}') AS head_ids,
                       COALESCE(array_agg(ch."CrimeGroupName"
                                ORDER BY ch."CrimeHeadID")
                                FILTER (WHERE ch."CrimeHeadID" IS NOT NULL), '{}') AS head_names,
                       (SELECT count(*) FROM "users" u WHERE u."wing_id" = w."WingID")
                  FROM "Wing" w
                  LEFT JOIN "WingCrimeHead" wch ON wch."WingID" = w."WingID"
                  LEFT JOIN "CrimeHead" ch ON ch."CrimeHeadID" = wch."CrimeHeadID"
                 WHERE w."Active"
                 GROUP BY w."WingID", w."WingCode", w."WingName", w."Description"
                 ORDER BY w."WingID"
            ''')
            rows = cur.fetchall()
    finally:
        if owns:
            c.close()

    items = []
    for wid, code, name, desc, head_ids, head_names, seats in rows:
        ids = [int(h) for h in (head_ids or [])]
        items.append({
            "wing_id": int(wid), "wing_code": code, "wing_name": name,
            "description": desc, "crime_head_ids": ids,
            "crime_head_names": list(head_names or []),
            "covers_all_heads": not ids, "seat_count": int(seats or 0),
        })
    return {"total": len(items), "items": items,
            "note": ("A wing is state-wide geographically and narrowed by crime "
                     "head. covers_all_heads means no head filter applies.")}


def list_ranges(conn=None) -> dict:
    """Seven police ranges with their member districts, plus the Commissionerates
    that sit outside the range hierarchy."""
    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            cur.execute('''
                SELECT r."RangeID", r."RangeCode", r."RangeName", r."HQDistrictID",
                       COALESCE(json_agg(json_build_object(
                           'district_id', d."DistrictID",
                           'district_name', d."DistrictName")
                           ORDER BY d."DistrictName")
                           FILTER (WHERE d."DistrictID" IS NOT NULL), '[]') AS districts,
                       (SELECT count(*) FROM "Unit" u
                          JOIN "District" dd ON dd."DistrictID" = u."DistrictID"
                         WHERE dd."RangeID" = r."RangeID" AND u."TypeID" = 1),
                       (SELECT count(*) FROM "users" us WHERE us."range_id" = r."RangeID")
                  FROM "Range" r
                  LEFT JOIN "District" d
                         ON d."RangeID" = r."RangeID" AND d."Active"
                 WHERE r."Active"
                 GROUP BY r."RangeID", r."RangeCode", r."RangeName", r."HQDistrictID"
                 ORDER BY r."RangeCode"
            ''')
            rows = cur.fetchall()
            cur.execute('''SELECT "DistrictID", "DistrictName" FROM "District"
                            WHERE "IsCommissionerate" AND "Active"
                            ORDER BY "DistrictName"''')
            comms = [{"district_id": int(a), "district_name": b}
                     for a, b in cur.fetchall()]
    finally:
        if owns:
            c.close()

    items = []
    for rid, code, name, hq, districts, stations, seats in rows:
        ds = districts if isinstance(districts, list) else json.loads(districts or "[]")
        items.append({
            "range_id": int(rid), "range_code": code, "range_name": name,
            "hq_district_id": (int(hq) if hq is not None else None),
            "districts": ds, "district_count": len(ds),
            "station_count": int(stations or 0), "seat_count": int(seats or 0),
        })
    return {"total": len(items), "items": items, "commissionerates": comms,
            "note": ("Commissionerates report outside the range hierarchy, so "
                     "they are listed separately rather than as a range with no "
                     "parent.")}


_SEAT_ORDER = ("state", "wing", "range", "commissionerate", "district",
               "station", "assigned_case", "platform", "unresolved")


def list_seats(*, q: Optional[str] = None, role: Optional[str] = None,
               scope_type: Optional[str] = None, active_only: bool = True,
               page: int = 1, page_size: int = 50, conn=None) -> dict:
    """Paginated, searchable seat directory for the login picker.

    Paginated because there are ~11,800 seats: the previous ten-card grid does
    not scale, and neither does shipping the whole list to the browser.
    """
    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))

    where = []
    params: list = []
    if active_only:
        where.append('u."is_active"')
    if role:
        where.append('r."role_name" = %s')
        params.append(role.strip())
    if scope_type:
        where.append('u."scope_type" = %s')
        params.append(scope_type.strip())
    if q:
        # Search the seat, its holder and its posting together, so "Jayanagar",
        # "sho.101" and "Ramesh" all find the same seat.
        where.append('(u."username" ILIKE %s OR u."display_name" ILIKE %s '
                     'OR u."posting_label" ILIKE %s)')
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            cur.execute(f'''SELECT count(*) FROM "users" u
                             JOIN "roles" r ON r."role_id" = u."role_id"{clause}''',
                        params)
            total = int(cur.fetchone()[0])

            cur.execute(f'''
                SELECT u."user_id", u."username", u."display_name", r."role_name",
                       u."scope_type", u."posting_label", u."rank_label",
                       u."designation_label", u."is_lead_investigator", u."is_active",
                       u."wing_id", u."range_id", u."district_id", u."unit_id"
                  FROM "users" u
                  JOIN "roles" r ON r."role_id" = u."role_id"{clause}
                 ORDER BY array_position(%s::text[], u."scope_type"),
                          u."posting_label" NULLS LAST, u."username"
                 LIMIT %s OFFSET %s
            ''', params + [list(_SEAT_ORDER), page_size, (page - 1) * page_size])
            rows = cur.fetchall()

            cur.execute(f'''SELECT u."scope_type", count(*) FROM "users" u
                             JOIN "roles" r ON r."role_id" = u."role_id"{clause}
                             GROUP BY u."scope_type"''', params)
            counts = {k: int(v) for k, v in cur.fetchall()}
    finally:
        if owns:
            c.close()

    items = [{
        "user_id": int(r[0]), "username": r[1], "display_name": r[2], "role": r[3],
        "scope_type": r[4],
        "scope_label": _roles.SCOPE_TYPE_LABELS.get(r[4], r[4]),
        "posting_label": r[5], "rank_label": r[6], "designation_label": r[7],
        "is_lead_investigator": bool(r[8]), "is_active": bool(r[9]),
        "wing_id": r[10], "range_id": r[11], "district_id": r[12], "unit_id": r[13],
    } for r in rows]

    return {"total": total, "page": page, "page_size": page_size, "items": items,
            "scope_type_counts": counts,
            "note": ("Selecting a seat chooses a VIEW. The server re-derives that "
                     "seat's scope on every request and never trusts this choice "
                     "for authorization.")}
