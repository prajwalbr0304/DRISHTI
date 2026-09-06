-- Rollback of DRISHTI migration 037.
--
-- Removes only the three keys 037 added, and only from rows it stamped
-- ('excluded_by' = 'migration:037'). A record excluded by a human reviewer or by a
-- later migration carries a different stamp and survives this.

BEGIN;

UPDATE "CaseVersion"
   SET "SnapshotAttributes" = "SnapshotAttributes"
                              - 'excluded_from_derived_analytics'
                              - 'exclusion_reason'
                              - 'excluded_by'
 WHERE "IsCurrent" = TRUE
   AND "SnapshotAttributes" ->> 'excluded_by' = 'migration:037';

COMMIT;

-- mv_case_daily's attestation changes again; refresh it after rolling back.
-- Verification: expect 0.
--   SELECT count(*) FROM "CaseVersion"
--    WHERE "SnapshotAttributes"->>'excluded_by' = 'migration:037';
