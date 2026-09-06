-- Rollback for DRISHTI migration 035 (admin-created custom roles).
--
-- Removes every admin-created role and the permission model behind it. The six
-- built-in roles survive untouched: they are protected by is_system and are
-- deleted by 028's rollback, not this one.
--
-- Export custom roles first if they matter — this discards them:
--   \copy (SELECT r.role_name, g.permission_key, g.granted FROM roles r
--            JOIN role_grant g ON g.role_name = r.role_name
--           WHERE r.is_system = FALSE) TO 'custom_roles_backup.csv' CSV HEADER

BEGIN;

-- 1. Drop dependent rows for custom roles, then the roles themselves.
DELETE FROM "role_grant"
 WHERE "role_name" IN (SELECT "role_name" FROM "roles" WHERE "is_system" = FALSE);

DELETE FROM "role_ui_grants"
 WHERE "role_name" IN (SELECT "role_name" FROM "roles" WHERE "is_system" = FALSE);

DELETE FROM "role_settings"
 WHERE "role_name" IN (SELECT "role_name" FROM "roles" WHERE "is_system" = FALSE);

DELETE FROM "role_permissions"
 WHERE "role_id" IN (SELECT "role_id" FROM "roles" WHERE "is_system" = FALSE);

-- A custom role with users still on it is NOT deleted; it is reported below so an
-- operator can reassign those seats deliberately rather than have them orphaned.
DELETE FROM "roles" r
 WHERE r."is_system" = FALSE
   AND NOT EXISTS (SELECT 1 FROM "users" u WHERE u."role_id" = r."role_id");

-- 2. Drop the custom-role model.
ALTER TABLE "roles" DROP CONSTRAINT IF EXISTS "chk_roles_base_surface";
ALTER TABLE "roles" DROP COLUMN IF EXISTS "allowed_scope_types";
ALTER TABLE "roles" DROP COLUMN IF EXISTS "base_surface";
ALTER TABLE "roles" DROP COLUMN IF EXISTS "created_by";

DROP TABLE IF EXISTS "role_grant";
DROP TABLE IF EXISTS "permission_catalogue";

COMMIT;

-- Verification: any custom role left still has seats assigned.
-- SELECT r.role_name, count(u.user_id) AS seats
--   FROM roles r JOIN users u ON u.role_id = r.role_id
--  WHERE r.is_system = FALSE GROUP BY 1;
