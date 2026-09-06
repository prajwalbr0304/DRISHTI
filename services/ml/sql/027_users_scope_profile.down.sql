-- Rollback for DRISHTI migration 027 (seat scope anchors + profile on users).
--
-- Run this BEFORE 026's rollback: the wing_id/range_id foreign keys here
-- reference the Wing and Range tables that 026 drops.
--
-- Lossy by nature: scope anchors and profile values written after the migration
-- are discarded. `unit_id` is left untouched because it predates this migration.

BEGIN;

ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_language";
ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_scope_anchor";
ALTER TABLE "users" DROP CONSTRAINT IF EXISTS "chk_users_scope_type";

DROP INDEX IF EXISTS "idx_users_lead_investigator";
DROP INDEX IF EXISTS "idx_users_employee";
DROP INDEX IF EXISTS "idx_users_wing";
DROP INDEX IF EXISTS "idx_users_range";
DROP INDEX IF EXISTS "idx_users_district";
DROP INDEX IF EXISTS "idx_users_scope_type";

ALTER TABLE "users" DROP COLUMN IF EXISTS "is_lead_investigator";
ALTER TABLE "users" DROP COLUMN IF EXISTS "updated_by";
ALTER TABLE "users" DROP COLUMN IF EXISTS "notes";
ALTER TABLE "users" DROP COLUMN IF EXISTS "avatar_url";
ALTER TABLE "users" DROP COLUMN IF EXISTS "preferred_language";
ALTER TABLE "users" DROP COLUMN IF EXISTS "posting_label";
ALTER TABLE "users" DROP COLUMN IF EXISTS "designation_label";
ALTER TABLE "users" DROP COLUMN IF EXISTS "rank_label";
ALTER TABLE "users" DROP COLUMN IF EXISTS "phone";
ALTER TABLE "users" DROP COLUMN IF EXISTS "email";

ALTER TABLE "users" DROP COLUMN IF EXISTS "employee_id";
ALTER TABLE "users" DROP COLUMN IF EXISTS "district_id";
ALTER TABLE "users" DROP COLUMN IF EXISTS "range_id";
ALTER TABLE "users" DROP COLUMN IF EXISTS "wing_id";
ALTER TABLE "users" DROP COLUMN IF EXISTS "scope_type";

COMMIT;
