-- Rollback for DRISHTI migration 031 (range-level jurisdiction boundaries).
--
-- Deletes any range and subdivision polygons FIRST, because the original CHECK
-- constraint does not admit those levels and would reject the ALTER while such
-- rows exist.

BEGIN;

DELETE FROM "JurisdictionBoundary" WHERE "Level" IN ('range', 'subdivision');

DROP INDEX IF EXISTS "idx_jurisdiction_range";

ALTER TABLE "JurisdictionBoundary" DROP COLUMN IF EXISTS "RangeID";

ALTER TABLE "JurisdictionBoundary" DROP CONSTRAINT IF EXISTS "chk_jurisdiction_level";

ALTER TABLE "JurisdictionBoundary" ADD CONSTRAINT "chk_jurisdiction_level"
    CHECK ("Level" IN ('state', 'district', 'taluk', 'unit', 'beat', 'sho'));

COMMIT;
