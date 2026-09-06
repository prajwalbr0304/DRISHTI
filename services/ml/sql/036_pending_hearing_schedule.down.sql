-- Rollback of DRISHTI migration 036.
--
-- 036 only INSERTED rows, each stamped Detail->>'migration' = '036', so this
-- deletes exactly that set and no pre-existing row can be caught by it. Deliberately
-- keyed on the stamp rather than on "OccurredAt IS NULL": if a later migration or a
-- live user schedules a hearing, that row is legitimately pending and must survive
-- this rollback.

BEGIN;

DELETE FROM "CourtEvent" WHERE "Detail" ->> 'migration' = '036';

DROP INDEX IF EXISTS "idx_courtevent_pending_hearing";

COMMENT ON COLUMN "CourtEvent"."ScheduledAt" IS NULL;

COMMIT;

-- Verification: expect 0 rows carrying the stamp.
--   SELECT count(*) FROM "CourtEvent" WHERE "Detail"->>'migration'='036';
