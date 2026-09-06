-- Rollback for DRISHTI migration 026 (organizational Wing and Range tiers).
--
-- Drops the two reference tiers and the three District columns. Safe to run
-- only while no users row anchors to a wing_id/range_id — migration 027's
-- rollback must run FIRST, or the FK from users will block the table drops.

BEGIN;

DROP INDEX IF EXISTS "idx_district_range";

ALTER TABLE "District" DROP COLUMN IF EXISTS "CommandRank";
ALTER TABLE "District" DROP COLUMN IF EXISTS "IsCommissionerate";
ALTER TABLE "District" DROP COLUMN IF EXISTS "RangeID";

DROP TABLE IF EXISTS "WingCrimeHead";
DROP TABLE IF EXISTS "Wing";
DROP TABLE IF EXISTS "Range";

COMMIT;
