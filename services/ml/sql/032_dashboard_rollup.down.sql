-- Rollback for DRISHTI migration 032 (dashboard rollup).
--
-- Drops the rollup and its refresh ledger. KPI endpoints must be reverted to
-- reading base tables BEFORE this runs, or every dashboard card errors.
--
-- The four supporting indexes on CaseMaster / CaseStatusMaster / CaseVersion are
-- dropped too, since they were added for this rollup. They are pure read
-- optimisations: dropping them slows the live aggregates back to their previous
-- cost but changes no result.

BEGIN;

DROP INDEX IF EXISTS "idx_caseversion_current_policy";
DROP INDEX IF EXISTS "idx_casestatusmaster_name";
DROP INDEX IF EXISTS "idx_casemaster_officer_status";
DROP INDEX IF EXISTS "idx_casemaster_station_status_date";

DROP MATERIALIZED VIEW IF EXISTS "mv_case_daily";

DELETE FROM "mv_refresh_state" WHERE "matview_name" = 'mv_case_daily';

-- Kept if other matviews have registered against it; dropped when it is only
-- ever been used by this migration.
DROP TABLE IF EXISTS "mv_refresh_state";

COMMIT;
