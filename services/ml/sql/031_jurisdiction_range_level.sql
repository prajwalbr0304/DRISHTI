-- DRISHTI migration 031: allow range-level jurisdiction boundaries.
--
-- WHY
-- JurisdictionBoundary."Level" is constrained to state|district|taluk|unit|beat|sho,
-- so a DIG range seat has no polygon to render — its map view would fall back to
-- either the whole state or a single district, neither of which is its
-- jurisdiction.
--
-- No new geodata is required. Range polygons are a ST_Union of the district
-- polygons already present (32 rows at Level='district', real KGIS geometry per
-- datagen/geo/SOURCES.md), so the boundary stays exactly consistent with the
-- district layer instead of introducing a second, slightly-different outline.
--
-- The dissolve itself is NOT run here: it depends on District.RangeID, whose
-- roster is deliberately unseeded pending reconciliation against the official
-- KSP structure (see migration 026). This migration only widens the constraint
-- and provides the dissolve as a documented, re-runnable statement.

BEGIN;

ALTER TABLE "JurisdictionBoundary" DROP CONSTRAINT IF EXISTS "chk_jurisdiction_level";

ALTER TABLE "JurisdictionBoundary" ADD CONSTRAINT "chk_jurisdiction_level"
    CHECK ("Level" IN ('state', 'range', 'district', 'subdivision',
                       'taluk', 'unit', 'beat', 'sho'));

-- 'subdivision' is admitted at the same time so the deferred DySP/ACP tier does
-- not need a second constraint migration later. No rows use it yet.

ALTER TABLE "JurisdictionBoundary"
    ADD COLUMN IF NOT EXISTS "RangeID" INTEGER REFERENCES "Range" ("RangeID");

CREATE INDEX IF NOT EXISTS "idx_jurisdiction_range"
    ON "JurisdictionBoundary" ("RangeID") WHERE "RangeID" IS NOT NULL;

COMMENT ON COLUMN "JurisdictionBoundary"."RangeID" IS
    'Owning Range for a Level=''range'' polygon. NULL for every other level.';

COMMIT;

-- ---------------------------------------------------------------------------
-- Range polygon dissolve — RUN ONLY AFTER District.RangeID IS SEEDED.
-- Idempotent: supersedes any existing current range rows before inserting.
-- ---------------------------------------------------------------------------
-- BEGIN;
--
-- UPDATE "JurisdictionBoundary"
--    SET "IsCurrent" = FALSE, "ValidTo" = now()
--  WHERE "Level" = 'range' AND "IsCurrent" = TRUE;
--
-- INSERT INTO "JurisdictionBoundary"
--     ("Level", "Name", "StateID", "RangeID", geom, "Version", "IsCurrent",
--      "Source", "IsSynthetic")
-- SELECT 'range',
--        rg."RangeName",
--        rg."StateID",
--        rg."RangeID",
--        ST_Multi(ST_UnaryUnion(ST_Collect(jb.geom))),
--        1, TRUE,
--        'dissolved from Level=district (KGIS-simplified)',
--        TRUE
--   FROM "Range" rg
--   JOIN "District" d ON d."RangeID" = rg."RangeID"
--   JOIN "JurisdictionBoundary" jb
--     ON jb."DistrictID" = d."DistrictID"
--    AND jb."Level" = 'district'
--    AND jb."IsCurrent" = TRUE
--  GROUP BY rg."RangeID", rg."RangeName", rg."StateID";
--
-- COMMIT;
