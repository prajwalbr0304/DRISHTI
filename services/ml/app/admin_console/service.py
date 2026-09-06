"""Admin console service: UI visibility, admin-created roles, role settings.

Enforces the five rules recorded in the footer of sql/035_custom_roles.sql, none
of which SQL can express on its own:

  1. is_system roles cannot be renamed or deleted.
  2. A grant whose requires_scope is narrower than a role's allowed scope types is
     refused, so an aggregate-only state seat cannot receive cases.detail_read.
  3. Granting an is_sensitive permission requires a reason, written to audit_logs.
  4. A seat's scope_type must appear in its role's allowed_scope_types.
  5. role_permissions is re-projected from role_grant on every change, so the
     legacy whitelisted-SELECT executor stays consistent.
"""
from __future__ import annotations

from typing import Optional

from .. import audit, db
from .schemas import (
    BASE_SURFACES, PermissionCatalogue, PermissionOut, RoleDetail, RoleGrantOut,
    RoleListResponse, RoleOut, UiGrantOut, UiVisibilityResponse, UserProfileOut,
)


class AdminConsoleError(ValueError):
    """Rejected for a stated reason. Mapped to 400/404/409 by the router."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


# Legacy role_permissions resources, mapped from the catalogue's own resource
# names. Rule 5 re-projects onto exactly the ten values already present in that
# table — inventing an eleventh would create a row the executor never consults.
_LEGACY_RESOURCE_BY_RESOURCE = {
    "cases": "cases",
    "intake": "cases",
    "entities": "people_entities",
    "network": "network_analysis",
    "money": "money_trail",
    "board": "analytics",
    "analytics": "analytics",
    "map": "map",
    "ask": "ask_drishti",
    "dashboard": "command_center",
    "performance": "command_center",
    "export": "command_center",
    "disaster": "command_center",
    "governance": "admin_governance",
    "models": "admin_governance",
    "quality": "admin_governance",
    "audit": "admin_governance",
    "admin": "admin_governance",
}

# Catalogue actions that only READ. Anything else projects as 'write', so a role
# that can dispatch or approve is not recorded as a reader.
_READ_ONLY_ACTIONS = frozenset({
    "read", "detail_read", "pii_read", "point_read", "use",
})

# Scope breadth, widest first. Rule 2 compares a permission's requires_scope
# against the scope types a role may be issued at: a permission that needs
# district grain is meaningless on a seat that only ever sees state aggregates.
_SCOPE_BREADTH = {
    "state": 0, "wing": 1, "range": 2,
    "district": 3, "commissionerate": 3,
    "station": 4, "assigned_case": 5,
    "platform": 0,
}


def _at_least_as_narrow(scope_type: str, required: str) -> bool:
    """True when `scope_type` is at least as narrow as `required`.

    A station seat may hold a district-grain permission (a station is inside a
    district); a state seat may not. `platform` is exempt — an administrator's
    reach is not a geography.
    """
    if scope_type == "platform":
        return True
    return _SCOPE_BREADTH.get(scope_type, 0) >= _SCOPE_BREADTH.get(required, 0)


# --------------------------------------------------------------------------- #
# Permission catalogue                                                        #
# --------------------------------------------------------------------------- #
def permission_catalogue() -> PermissionCatalogue:
    with db.ro_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT "permission_key", "resource", "action", "label", "description",
                   "category", "is_sensitive", "requires_scope"
              FROM "permission_catalogue"
             ORDER BY "category", "label"
            """
        )
        rows = cur.fetchall()

    categories: dict[str, list[PermissionOut]] = {}
    for r in rows:
        perm = PermissionOut(
            permission_key=r[0], resource=r[1], action=r[2], label=r[3],
            description=r[4], category=r[5], is_sensitive=r[6],
            requires_scope=r[7],
        )
        categories.setdefault(perm.category, []).append(perm)

    return PermissionCatalogue(total=len(rows), categories=categories)


def _catalogue_map(conn) -> dict[str, tuple[bool, Optional[str], str]]:
    """permission_key -> (is_sensitive, requires_scope, category)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "permission_key", "is_sensitive", "requires_scope", "category"'
            ' FROM "permission_catalogue"'
        )
        return {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}


# --------------------------------------------------------------------------- #
# Roles                                                                       #
# --------------------------------------------------------------------------- #
_ROLE_SELECT = """
    SELECT r."role_name", r."description", r."is_system", r."base_surface",
           r."allowed_scope_types", r."created_by",
           COALESCE(g."granted_count", 0), COALESCE(g."sensitive_count", 0),
           COALESCE(u."seat_count", 0),
           s."display_label", s."default_route", s."sort_order"
      FROM "roles" r
      LEFT JOIN (
            SELECT rg."role_name",
                   COUNT(*) FILTER (WHERE rg."granted") AS "granted_count",
                   COUNT(*) FILTER (WHERE rg."granted" AND pc."is_sensitive")
                       AS "sensitive_count"
              FROM "role_grant" rg
              JOIN "permission_catalogue" pc
                ON pc."permission_key" = rg."permission_key"
             GROUP BY rg."role_name"
           ) g ON g."role_name" = r."role_name"
      -- Seats join through role_id, not a role name: users.role_id is the FK and
      -- users.legacy_role_name is a historical label that can lag behind it.
      LEFT JOIN (
            SELECT "role_id", COUNT(*) AS "seat_count" FROM "users"
             GROUP BY "role_id"
           ) u ON u."role_id" = r."role_id"
      LEFT JOIN "role_settings" s ON s."role_name" = r."role_name"
"""


def _role_from_row(r) -> RoleOut:
    return RoleOut(
        role_name=r[0], description=r[1], is_system=r[2], base_surface=r[3],
        allowed_scope_types=list(r[4]) if r[4] else None, created_by=r[5],
        granted_count=r[6], sensitive_count=r[7], seat_count=r[8],
        display_label=r[9], default_route=r[10], sort_order=r[11],
    )


def list_roles() -> RoleListResponse:
    with db.ro_conn() as conn, conn.cursor() as cur:
        cur.execute(
            _ROLE_SELECT
            + ' ORDER BY r."is_system" DESC, s."sort_order" NULLS LAST, r."role_name"'
        )
        items = [_role_from_row(r) for r in cur.fetchall()]
    return RoleListResponse(total=len(items), items=items,
                            base_surfaces=list(BASE_SURFACES))


def get_role(role_name: str) -> RoleDetail:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_ROLE_SELECT + ' WHERE r."role_name" = %s', (role_name,))
            row = cur.fetchone()
        if row is None:
            raise AdminConsoleError(f"no such role: {role_name}", status=404)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "permission_key", "granted", "reason", "granted_by"'
                ' FROM "role_grant" WHERE "role_name" = %s'
                ' ORDER BY "permission_key"',
                (role_name,),
            )
            grants = [
                RoleGrantOut(permission_key=g[0], granted=g[1], reason=g[2],
                             granted_by=g[3])
                for g in cur.fetchall()
            ]
    return RoleDetail(**_role_from_row(row).model_dump(), grants=grants)


def _validate_grants(
    conn, permission_keys: list[str], allowed_scope_types: list[str],
    reason: Optional[str],
) -> list[str]:
    """Rules 2 and 3. Returns the validated keys.

    Rule 2 is checked against the role's WIDEST allowed scope type: if a role can
    be issued at state level, granting it a district-grain permission would let
    that state seat hold it, so the widest case is the one that has to pass.
    """
    catalogue = _catalogue_map(conn)

    unknown = [k for k in permission_keys if k not in catalogue]
    if unknown:
        raise AdminConsoleError(
            "not in the permission catalogue: " + ", ".join(sorted(unknown)))

    widest = min(allowed_scope_types,
                 key=lambda s: _SCOPE_BREADTH.get(s, 0), default="state")

    too_broad: list[str] = []
    sensitive: list[str] = []
    for key in permission_keys:
        is_sensitive, requires_scope, _ = catalogue[key]
        if requires_scope and not _at_least_as_narrow(widest, requires_scope):
            too_broad.append(f"{key} (needs {requires_scope}, role reaches {widest})")
        if is_sensitive:
            sensitive.append(key)

    if too_broad:
        raise AdminConsoleError(
            "these permissions are not meaningful at this role's widest scope, so "
            "granting them would give a seat a capability it cannot use: "
            + "; ".join(sorted(too_broad))
        )

    # Rule 3: a reason is required, and it is recorded in the audit trail.
    if sensitive and not (reason and reason.strip()):
        raise AdminConsoleError(
            "a reason is required to grant permissions that expose personal data "
            "or coercive capability: " + ", ".join(sorted(sensitive))
        )

    return list(dict.fromkeys(permission_keys))


def _reproject_role_permissions(conn, role_name: str) -> None:
    """Rule 5: rebuild the legacy role_permissions rows from role_grant.

    role_permissions.action is an enum of ('read','write','none'), so richer verbs
    cannot be represented there. The projection keeps the coarse read/write shape
    the whitelisted-SELECT executor and the RLS design read, and the fine-grained
    truth stays in role_grant. Without this the executor would keep honouring a
    permission an admin had just revoked.
    """
    with conn.cursor() as cur:
        # role_permissions keys on role_id; role_grant keys on role_name. The
        # projection has to bridge the two.
        cur.execute('SELECT "role_id" FROM "roles" WHERE "role_name" = %s',
                    (role_name,))
        row = cur.fetchone()
        if row is None:
            return
        role_id = row[0]

        cur.execute(
            """
            SELECT pc."resource", pc."action"
              FROM "role_grant" rg
              JOIN "permission_catalogue" pc
                ON pc."permission_key" = rg."permission_key"
             WHERE rg."role_name" = %s AND rg."granted"
            """,
            (role_name,),
        )
        rows = cur.fetchall()

    # A resource is 'write' if any granted permission on it mutates, else 'read'.
    # A resource with nothing granted is simply absent, which the executor already
    # treats as no access — so 'none' is never written.
    effective: dict[str, str] = {}
    for resource, action in rows:
        legacy = _LEGACY_RESOURCE_BY_RESOURCE.get(resource)
        if not legacy:
            continue
        if action in _READ_ONLY_ACTIONS:
            effective.setdefault(legacy, "read")
        else:
            effective[legacy] = "write"

    # `pii` is its own legacy resource, gated by the two PII-bearing permissions
    # rather than by a category, because it cuts across cases and entities.
    granted_keys = {f"{r}.{a}" for r, a in rows}
    if granted_keys & {"entities.pii_read", "cases.detail_read"}:
        effective["pii"] = "read"

    with conn.cursor() as cur:
        cur.execute('DELETE FROM "role_permissions" WHERE "role_id" = %s',
                    (role_id,))
        for resource, action in sorted(effective.items()):
            cur.execute(
                'INSERT INTO "role_permissions" ("role_id", "resource", "action")'
                ' VALUES (%s, %s, %s::permission_action_enum)',
                (role_id, resource, action),
            )


def create_role(body, actor: Optional[str]) -> RoleDetail:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "is_system" FROM "roles" WHERE "role_name" = %s',
                        (body.role_name,))
            if cur.fetchone() is not None:
                raise AdminConsoleError(
                    f"role already exists: {body.role_name}", status=409)

        keys = _validate_grants(conn, body.permission_keys,
                                body.allowed_scope_types, body.reason)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "roles" ("role_name", "description", "is_system",
                                     "created_by", "base_surface",
                                     "allowed_scope_types")
                VALUES (%s, %s, FALSE, %s, %s, %s)
                """,
                (body.role_name, body.description, actor, body.base_surface,
                 body.allowed_scope_types),
            )
            for key in keys:
                cur.execute(
                    'INSERT INTO "role_grant" ("role_name", "permission_key",'
                    ' "granted", "reason", "granted_by")'
                    ' VALUES (%s, %s, TRUE, %s, %s)',
                    (body.role_name, key, body.reason, actor),
                )
            # A settings row so the console has something stable to edit, matching
            # the seeding in migration 030.
            cur.execute(
                'INSERT INTO "role_settings" ("role_name", "display_label",'
                ' "description", "default_route", "updated_by")'
                ' VALUES (%s, %s, %s, %s, %s)'
                ' ON CONFLICT ("role_name") DO NOTHING',
                (body.role_name, body.display_label, body.description,
                 body.default_route, actor),
            )

        _reproject_role_permissions(conn, body.role_name)

        audit.record(
            "admin.role.create", "roles", body.role_name, actor=actor,
            detail={
                "base_surface": body.base_surface,
                "allowed_scope_types": body.allowed_scope_types,
                "permission_count": len(keys),
                "permissions": keys,
                "reason": body.reason,
            },
            conn=conn,
        )

    return get_role(body.role_name)


def replace_grants(role_name: str, body, actor: Optional[str]) -> RoleDetail:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "allowed_scope_types" FROM "roles" WHERE "role_name" = %s',
                (role_name,))
            row = cur.fetchone()
        if row is None:
            raise AdminConsoleError(f"no such role: {role_name}", status=404)

        allowed = list(row[0]) if row[0] else ["state"]
        keys = _validate_grants(conn, body.permission_keys, allowed, body.reason)

        with conn.cursor() as cur:
            cur.execute('SELECT "permission_key" FROM "role_grant"'
                        ' WHERE "role_name" = %s AND "granted"', (role_name,))
            before = {r[0] for r in cur.fetchall()}

            cur.execute('DELETE FROM "role_grant" WHERE "role_name" = %s',
                        (role_name,))
            for key in keys:
                cur.execute(
                    'INSERT INTO "role_grant" ("role_name", "permission_key",'
                    ' "granted", "reason", "granted_by")'
                    ' VALUES (%s, %s, TRUE, %s, %s)',
                    (role_name, key, body.reason, actor),
                )

        _reproject_role_permissions(conn, role_name)

        after = set(keys)
        audit.record(
            "admin.role.grants.replace", "roles", role_name, actor=actor,
            detail={
                "added": sorted(after - before),
                "removed": sorted(before - after),
                "total": len(after),
                "reason": body.reason,
            },
            conn=conn,
        )

    return get_role(role_name)


def toggle_grant(role_name: str, permission_key: str, body,
                 actor: Optional[str]) -> RoleDetail:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "allowed_scope_types" FROM "roles" WHERE "role_name" = %s',
                (role_name,))
            row = cur.fetchone()
        if row is None:
            raise AdminConsoleError(f"no such role: {role_name}", status=404)

        if body.granted:
            allowed = list(row[0]) if row[0] else ["state"]
            _validate_grants(conn, [permission_key], allowed, body.reason)
        else:
            # Revoking needs no scope check, but the key must still be real so a
            # typo cannot leave a phantom revocation in the audit trail.
            if permission_key not in _catalogue_map(conn):
                raise AdminConsoleError(
                    f"not in the permission catalogue: {permission_key}")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "role_grant" ("role_name", "permission_key",
                                          "granted", "reason", "granted_by")
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT ("role_name", "permission_key") DO UPDATE
                    SET "granted" = EXCLUDED."granted",
                        "reason" = EXCLUDED."reason",
                        "granted_by" = EXCLUDED."granted_by",
                        "granted_at" = now()
                """,
                (role_name, permission_key, body.granted, body.reason, actor),
            )

        _reproject_role_permissions(conn, role_name)

        audit.record(
            "admin.role.grant.toggle", "roles", role_name, actor=actor,
            detail={"permission_key": permission_key, "granted": body.granted,
                    "reason": body.reason},
            conn=conn,
        )

    return get_role(role_name)


def delete_role(role_name: str, actor: Optional[str]) -> None:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "is_system" FROM "roles" WHERE "role_name" = %s',
                        (role_name,))
            row = cur.fetchone()
            if row is None:
                raise AdminConsoleError(f"no such role: {role_name}", status=404)
            # Rule 1: the six built-in roles are referenced by name in the
            # frontend registry, the gateway and roles.py, so deleting one would
            # break rendering for every seat holding it.
            if row[0]:
                raise AdminConsoleError(
                    f"{role_name} is a built-in role and cannot be deleted",
                    status=409)

            cur.execute(
                'SELECT COUNT(*) FROM "users" u JOIN "roles" r'
                ' ON r."role_id" = u."role_id" WHERE r."role_name" = %s',
                (role_name,))
            seats = cur.fetchone()[0]
            if seats:
                raise AdminConsoleError(
                    f"{seats} seat(s) still hold {role_name}. Reassign them first, "
                    "or those officers would be left with a role that no longer "
                    "exists.",
                    status=409)

            # role_grant and role_settings cascade from role_name; role_permissions
            # keys on role_id and is cleared explicitly.
            cur.execute(
                'DELETE FROM "role_permissions" WHERE "role_id" ='
                ' (SELECT "role_id" FROM "roles" WHERE "role_name" = %s)',
                (role_name,))
            cur.execute('DELETE FROM "roles" WHERE "role_name" = %s', (role_name,))

        audit.record("admin.role.delete", "roles", role_name, actor=actor,
                     conn=conn)


# --------------------------------------------------------------------------- #
# UI visibility                                                               #
# --------------------------------------------------------------------------- #
def list_ui_grants(role_name: Optional[str] = None,
                   element_kind: Optional[str] = None) -> UiVisibilityResponse:
    sql = [
        'SELECT "id", "role_name", "scope_type", "element_kind", "element_id",',
        '       "enabled", "reason", "updated_by", "updated_at"',
        '  FROM "role_ui_grants"',
    ]
    where, params = [], []
    if role_name:
        where.append('"role_name" = %s')
        params.append(role_name)
    if element_kind:
        where.append('"element_kind" = %s')
        params.append(element_kind)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(' ORDER BY "role_name", "element_kind", "element_id"')

    with db.ro_conn() as conn, conn.cursor() as cur:
        cur.execute("\n".join(sql), tuple(params))
        items = [
            UiGrantOut(
                id=r[0], role_name=r[1], scope_type=r[2], element_kind=r[3],
                element_id=r[4], enabled=r[5], reason=r[6], updated_by=r[7],
                updated_at=r[8].isoformat() if r[8] else None,
            )
            for r in cur.fetchall()
        ]
    return UiVisibilityResponse(total=len(items), items=items)


def set_ui_grant(body, actor: Optional[str]) -> UiGrantOut:
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "roles" WHERE "role_name" = %s',
                        (body.role_name,))
            if cur.fetchone() is None:
                raise AdminConsoleError(f"no such role: {body.role_name}",
                                        status=404)

            # COALESCE(scope_type,'*') matches the unique index, which was written
            # that way deliberately: NULLS NOT DISTINCT needs PostgreSQL 15+ and
            # would otherwise allow two role-wide rows for the same element, making
            # the effective value depend on row order.
            cur.execute(
                """
                INSERT INTO "role_ui_grants" ("role_name", "scope_type",
                        "element_kind", "element_id", "enabled", "reason",
                        "updated_by")
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("role_name", COALESCE("scope_type", '*'),
                             "element_kind", "element_id")
                DO UPDATE SET "enabled" = EXCLUDED."enabled",
                              "reason" = EXCLUDED."reason",
                              "updated_by" = EXCLUDED."updated_by",
                              "updated_at" = now()
                RETURNING "id", "role_name", "scope_type", "element_kind",
                          "element_id", "enabled", "reason", "updated_by",
                          "updated_at"
                """,
                (body.role_name, body.scope_type, body.element_kind,
                 body.element_id, body.enabled, body.reason, actor),
            )
            r = cur.fetchone()

        audit.record(
            "admin.ui_visibility.set", "role_ui_grants", r[0], actor=actor,
            detail={"role_name": body.role_name, "scope_type": body.scope_type,
                    "element_kind": body.element_kind,
                    "element_id": body.element_id, "enabled": body.enabled,
                    "reason": body.reason},
            conn=conn,
        )

    return UiGrantOut(
        id=r[0], role_name=r[1], scope_type=r[2], element_kind=r[3],
        element_id=r[4], enabled=r[5], reason=r[6], updated_by=r[7],
        updated_at=r[8].isoformat() if r[8] else None,
    )


def clear_ui_grant(grant_id: int, actor: Optional[str]) -> None:
    """Delete an override, returning the element to its registry default.

    Deletion rather than enabled=TRUE: an absent row means "use the code default",
    so writing TRUE would PIN the element visible and a later default change would
    not reach this role.
    """
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM "role_ui_grants" WHERE "id" = %s'
                ' RETURNING "role_name", "element_kind", "element_id"',
                (grant_id,))
            row = cur.fetchone()
        if row is None:
            raise AdminConsoleError(f"no such override: {grant_id}", status=404)

        audit.record(
            "admin.ui_visibility.clear", "role_ui_grants", grant_id, actor=actor,
            detail={"role_name": row[0], "element_kind": row[1],
                    "element_id": row[2], "note": "reverted to registry default"},
            conn=conn,
        )


# --------------------------------------------------------------------------- #
# Role settings + user profile                                                #
# --------------------------------------------------------------------------- #
def update_role_settings(role_name: str, body, actor: Optional[str]) -> RoleOut:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise AdminConsoleError("no settings supplied")

    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "roles" WHERE "role_name" = %s',
                        (role_name,))
            if cur.fetchone() is None:
                raise AdminConsoleError(f"no such role: {role_name}", status=404)

            cols = list(fields.keys())
            assignments = ", ".join(f'"{c}" = %s' for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            cur.execute(
                f'INSERT INTO "role_settings" ("role_name", {", ".join(chr(34) + c + chr(34) for c in cols)}, "updated_by")'
                f" VALUES (%s, {placeholders}, %s)"
                f' ON CONFLICT ("role_name") DO UPDATE SET {assignments},'
                f' "updated_by" = %s, "updated_at" = now()',
                (role_name, *[fields[c] for c in cols], actor,
                 *[fields[c] for c in cols], actor),
            )

        audit.record("admin.role_settings.update", "role_settings", role_name,
                     actor=actor, detail=fields, conn=conn)

    with db.ro_conn() as conn, conn.cursor() as cur:
        cur.execute(_ROLE_SELECT + ' WHERE r."role_name" = %s', (role_name,))
        return _role_from_row(cur.fetchone())


_PROFILE_COLUMNS = (
    "display_name", "email", "phone", "rank_label", "designation_label",
    "posting_label", "preferred_language", "notes", "is_lead_investigator",
)


def update_user_profile(user_id: int, body, actor: Optional[str]) -> UserProfileOut:
    # exclude_unset so a partial edit writes only what was sent. Without it every
    # unmentioned field would arrive as None and blank a rank or a phone number
    # that the admin never touched.
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()
              if k in _PROFILE_COLUMNS}
    if not fields:
        raise AdminConsoleError("no profile fields supplied")

    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "username" FROM "users" WHERE "user_id" = %s',
                        (user_id,))
            row = cur.fetchone()
            if row is None:
                raise AdminConsoleError(f"no such user: {user_id}", status=404)

            cols = list(fields.keys())
            assignments = ", ".join(f'"{c}" = %s' for c in cols)
            cur.execute(
                f'UPDATE "users" SET {assignments}, "updated_by" = %s'
                f' WHERE "user_id" = %s',
                (*[fields[c] for c in cols], actor, user_id),
            )

        audit.record("admin.user.profile.update", "users", user_id, actor=actor,
                     detail={"username": row[0], "fields": sorted(cols)},
                     conn=conn)

    return get_user_profile(user_id)


def get_user_profile(user_id: int) -> UserProfileOut:
    with db.ro_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT u."user_id", u."username", u."display_name",
                   COALESCE(r."role_name", u."legacy_role_name", ''),
                   u."scope_type", u."email", u."phone", u."rank_label",
                   u."designation_label", u."posting_label",
                   u."preferred_language", u."notes", u."is_lead_investigator",
                   u."is_active", u."updated_by"
              FROM "users" u
              LEFT JOIN "roles" r ON r."role_id" = u."role_id"
             WHERE u."user_id" = %s
            """,
            (user_id,),
        )
        r = cur.fetchone()
    if r is None:
        raise AdminConsoleError(f"no such user: {user_id}", status=404)
    return UserProfileOut(
        user_id=r[0], username=r[1], display_name=r[2], role=r[3], scope_type=r[4],
        email=r[5], phone=r[6], rank_label=r[7], designation_label=r[8],
        posting_label=r[9], preferred_language=r[10], notes=r[11],
        is_lead_investigator=r[12], is_active=r[13], updated_by=r[14],
    )
