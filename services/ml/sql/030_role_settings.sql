-- DRISHTI migration 030: admin-editable per-role settings.
--
-- WHY
-- A role's display label, description and landing route are hard-coded in
-- web/src/config/roles.ts (RoleDef.label / blurb / home) and duplicated in
-- services/ml/app/roles.py (ROLE_LABELS / ROLE_DESCRIPTIONS). Changing what a
-- role is called, or where it lands after sign-in, currently needs a deploy and
-- edits in two languages that can drift apart.
--
-- Same pattern as migration 029: an ABSENT row means "use the code default".
-- Only genuinely presentational settings live here. Nothing in this table
-- changes what a role may do or see — scope stays in users.scope_type and
-- element visibility in role_ui_grants.

BEGIN;

CREATE TABLE IF NOT EXISTS "role_settings" (
    "role_name"        VARCHAR PRIMARY KEY REFERENCES "roles" ("role_name") ON DELETE CASCADE,
    "display_label"    VARCHAR,
    "description"      TEXT,
    "default_route"    VARCHAR,
    "default_board_id" VARCHAR,
    "icon_name"        VARCHAR,
    "sort_order"       INTEGER,
    "updated_by"       VARCHAR,
    "updated_at"       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "chk_role_settings_route"
        CHECK ("default_route" IS NULL OR "default_route" LIKE '/%')
);

COMMENT ON TABLE "role_settings" IS
    'Admin-editable presentation settings per role. An absent row or a NULL column means "use the code default" in web/src/config/roles.ts. Presentational only: never scope, never permission.';
COMMENT ON COLUMN "role_settings"."default_route" IS
    'Landing route after sign-in, overriding RoleDef.home. Must start with "/". Validated against the route table before it is applied.';
COMMENT ON COLUMN "role_settings"."default_board_id" IS
    'Dashboard board id this role opens on, overriding the registry default.';
COMMENT ON COLUMN "role_settings"."sort_order" IS
    'Display order in the seat picker and admin lists. NULL sorts last.';

-- Seed one row per application role, all overrides NULL, so the admin console
-- has a stable row to edit and the effective value still comes from code until
-- somebody deliberately changes it.
INSERT INTO "role_settings" ("role_name", "sort_order")
SELECT r."role_name", v.ord
  FROM "roles" r
  JOIN (VALUES
        ('dgp_state_command',     10),
        ('senior_command',        20),
        ('district_command',      30),
        ('sho',                   40),
        ('investigating_officer', 50),
        ('system_admin',          60)
       ) AS v(role_name, ord) ON v.role_name = r."role_name"
ON CONFLICT ("role_name") DO NOTHING;

ALTER TABLE "role_settings" DISABLE ROW LEVEL SECURITY;

COMMIT;
