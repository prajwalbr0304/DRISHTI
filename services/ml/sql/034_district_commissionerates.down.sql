-- Rollback for DRISHTI migration 034 (district-level Commissionerate split).
--
-- Exactly reversible because every station move was recorded in
-- DistrictSplitAudit before it was applied. Order matters: stations return to
-- their parent district BEFORE the Commissionerate rows are deleted, or the FK
-- from Unit would block the delete.
--
-- Refuses to delete a District row that any seat still anchors to, so a partial
-- rollback cannot orphan a provisioned SP/CP seat.

BEGIN;

-- 1. Retire boundary rows this migration created.
DELETE FROM "JurisdictionBoundary"
 WHERE "Source" IN ('dissolved from Level=taluk (KGIS-simplified)',
                    'district minus carved Commissionerate (KGIS-simplified)',
                    'dissolved from Level=district (KGIS-simplified)');

-- 2. Restore the superseded rural district polygons.
UPDATE "JurisdictionBoundary" jb
   SET "IsCurrent" = TRUE, "ValidTo" = NULL
 WHERE jb."Level" = 'district'
   AND jb."IsCurrent" = FALSE
   AND jb."ValidTo" IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM "JurisdictionBoundary" cur
                    WHERE cur."Level" = 'district'
                      AND cur."IsCurrent" = TRUE
                      AND cur."DistrictID" = jb."DistrictID");

-- 3. Send every moved station back to its original district.
UPDATE "Unit" u
   SET "DistrictID" = a."FromDistrictID"
  FROM "DistrictSplitAudit" a
 WHERE a."UnitID" = u."UnitID"
   AND a."MigrationTag" = '034_district_commissionerates';

-- 4. Officer establishment follows its station back.
UPDATE "Employee" e
   SET "DistrictID" = u."DistrictID"
  FROM "Unit" u
 WHERE u."UnitID" = e."UnitID"
   AND e."DistrictID" <> u."DistrictID";

-- 5. Re-parent Commissionerate HQ units back to their original district.
UPDATE "Unit" hq
   SET "DistrictID" = pd."DistrictID"
  FROM "District" cd, "District" pd
 WHERE cd."IsCommissionerate" = TRUE
   AND cd."DistrictName" IN ('Mysuru City','Mangaluru City','Hubballi-Dharwad City',
                             'Belagavi City','Kalaburagi City')
   AND hq."DistrictID" = cd."DistrictID"
   AND pd."DistrictName" = CASE cd."DistrictName"
        WHEN 'Mysuru City'           THEN 'Mysuru'
        WHEN 'Mangaluru City'        THEN 'Dakshina Kannada'
        WHEN 'Hubballi-Dharwad City' THEN 'Dharwad'
        WHEN 'Belagavi City'         THEN 'Belagavi'
        WHEN 'Kalaburagi City'       THEN 'Kalaburagi'
       END;

-- 6. Remove the six rows this migration created, only where unreferenced.
DELETE FROM "District" d
 WHERE d."DistrictName" IN ('Mysuru City','Mangaluru City','Hubballi-Dharwad City',
                            'Belagavi City','Kalaburagi City','Kolar Gold Field (KGF)')
   AND NOT EXISTS (SELECT 1 FROM "Unit" u     WHERE u."DistrictID" = d."DistrictID")
   AND NOT EXISTS (SELECT 1 FROM "Employee" e WHERE e."DistrictID" = d."DistrictID")
   AND NOT EXISTS (SELECT 1 FROM "users" us   WHERE us."district_id" = d."DistrictID");

DROP TABLE IF EXISTS "DistrictSplitAudit";

COMMIT;

-- Verification: expect 32 districts and zero station/officer drift.
-- SELECT count(*) FROM "District";
-- SELECT count(*) FROM "Employee" e JOIN "Unit" u ON u."UnitID"=e."UnitID"
--  WHERE e."DistrictID" <> u."DistrictID";
